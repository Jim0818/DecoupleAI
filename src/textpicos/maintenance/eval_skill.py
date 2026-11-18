#!/usr/bin/env python3
"""Prepare evaluation inputs without pretending a model has executed.

Supervisor tasks reuse the production context assembler. An isolated runtime
handoff can be replayed verbatim with --handoff; expectations stay separate
from the worker prompt. --validate-only checks structure, never prose quality.
Legacy Agent directories remain available for compatibility rule inspection.
"""
from __future__ import annotations
from textpicos.paths import ProjectPaths as _ProjectPaths

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from textpicos.context import assemble_context, context_prompt, load_capabilities
from textpicos.host import checked_ref, validate_task_paths

REPO = _ProjectPaths.discover().root
AGENTS = REPO / "agents"

# 加权公式特征：`X = a(0-40) + b(0-30)` 或 `分 = ... + ...（含数字权重）`。
FORMULA_RE = re.compile(r"=\s*[^=\n]*\(\s*0\s*-\s*\d+\s*\)|分\s*=\s*[^=\n]*[0-9][^=\n]*\+")


def find_cases(agent_dir: Path) -> Path | None:
    p = agent_dir / "evaluation" / "quality-cases.json"
    return p if p.is_file() else None


def validate(cases_path: Path) -> list[str]:
    """Return a list of structural problems (empty = ok)."""
    probs: list[str] = []
    try:
        data = json.loads(cases_path.read_text())
    except Exception as e:
        return [f"JSON 解析失败: {e}"]
    if not isinstance(data, dict):
        return ["顶层应为对象"]
    if not data.get("skill_name"):
        probs.append("缺 skill_name")
    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        probs.append("缺 evals[] 或为空")
        return probs
    seen_ids = set()
    for i, ev in enumerate(evals):
        tag = f"evals[{i}]"
        if not isinstance(ev, dict):
            probs.append(f"{tag} 非对象")
            continue
        if "id" not in ev:
            probs.append(f"{tag} 缺 id")
        elif not isinstance(ev["id"], (str, int)) or isinstance(ev["id"], bool):
            probs.append(f"{tag} id 应为字符串或整数")
        elif ev["id"] in seen_ids:
            probs.append(f"{tag} id 重复: {ev['id']}")
        else:
            seen_ids.add(ev["id"])
        if not isinstance(ev.get("prompt"), str) or not ev["prompt"].strip():
            probs.append(f"{tag} 缺 prompt")
        if "task" in ev and not isinstance(ev["task"], dict):
            probs.append(f"{tag} task 应为对象")
        exps = ev.get("expectations")
        if not isinstance(exps, list) or not exps:
            probs.append(f"{tag} 缺 expectations[] 或为空")
        else:
            # C8 守护：拦的是 expectation 里**开了加权公式**（如 `分 = d1(0-40)+d2(0-30)`），
            # 不是提到"加权"二字——"未输出加权总分"这类否定式是合规的好 expectation。
            for e in exps:
                if isinstance(e, str) and FORMULA_RE.search(e):
                    probs.append(f"{tag} expectation 内联加权评分公式，违 C8: {e[:40]}")
    return probs


def _exclusions(paths):
    # Share the maintenance boundary used by the actual supervisor CLI.
    from textpicos.cli import _exclusions as production_exclusions
    return production_exclusions(paths)


def prepare_evaluation(paths, task: Mapping[str, Any], *, expectations=()) -> dict:
    """Assemble the production task prompt; no model call or result is implied."""
    if (not isinstance(task, Mapping) or not isinstance(task.get("goal"), (str, dict))
            or not task["goal"] or isinstance(task["goal"], str) and not task["goal"].strip()):
        raise ValueError("An evaluation task requires a nonempty goal")
    validate_task_paths(paths, task, exclusions=_exclusions(paths))
    context = assemble_context(paths, task, exclusions=_exclusions(paths))
    return {
        "input_mode": "supervisor_context",
        "execution_started": False,
        "context": context,
        "prompt": context_prompt(context),
        "assessment": {"status": "not_run", "expectations": list(expectations)},
    }


def prepare_handoff_evaluation(paths, value, *, expectations=()) -> dict:
    """Use an actual isolated host handoff unchanged, including its boundary."""
    path = checked_ref(paths, value, must_exist=True, exclusions=_exclusions(paths))
    handoff = json.loads(path.read_text(encoding="utf-8"))
    context, prompt = handoff.get("context"), handoff.get("prompt")
    if (not isinstance(context, dict)
            or context.get("orchestration_mode") != "supervisor"
            or not isinstance(prompt, str) or not prompt.strip()):
        raise ValueError("Expected an actual supervisor host handoff with context and prompt")
    validate_task_paths(paths, context.get("task", {}), exclusions=_exclusions(paths))
    return {
        "input_mode": "production_handoff",
        "handoff_ref": str(path),
        "execution_started": False,
        "context": context,
        "prompt": prompt,
        "assessment": {"status": "not_run", "expectations": list(expectations)},
    }


def _role_for_directory(paths, agent_dir: Path) -> str | None:
    selected = (agent_dir / "SKILL.md").resolve()
    for role, spec in load_capabilities(paths)["roles"].items():
        if (paths.root / spec["entrypoint"]).resolve() == selected:
            return role
    return None


def evaluation_cases(paths, cases_path, *, role=None, defaults=None) -> dict:
    problems = validate(cases_path)
    if problems:
        raise ValueError("; ".join(problems))
    data = json.loads(cases_path.read_text(encoding="utf-8"))
    prepared = []
    for case in data["evals"]:
        task = dict(case.get("task") or {})
        task.setdefault("goal", case["prompt"])
        if role:
            task["role"] = role
        task.update(defaults or {})
        item = prepare_evaluation(paths, task, expectations=case["expectations"])
        item["case_id"] = case["id"]
        if "expected_output" in case:
            item["assessment"]["expected_output"] = case["expected_output"]
        prepared.append(item)
    return {"skill_name": data["skill_name"], "evaluation_mode": "supervisor", "evals": prepared}


def render_prepared(data: dict) -> str:
    items = data.get("evals", [data])
    lines = ["# 执行输入与评估材料", "",
             "结构预检不代表模型行为通过。将每项 prompt 原样交给执行员工；",
             "assessment 只交给独立评估者，不放进写作上下文。", ""]
    for item in items:
        lines.extend([f"## 用例 {item.get('case_id', 'task')}", "",
                      f"输入方式：{item['input_mode']}；模型执行状态：尚未运行", "",
                      "### 执行 prompt", "", item["prompt"], "",
                      "### 独立评估材料", "",
                      json.dumps(item["assessment"], ensure_ascii=False, indent=2), ""])
    return "\n".join(lines)


def render_worksheet(agent_dir: Path, cases_path: Path) -> str:
    paths = _ProjectPaths.discover()
    role = _role_for_directory(paths, agent_dir)
    if role:
        return render_prepared(evaluation_cases(paths, cases_path, role=role))
    data = json.loads(cases_path.read_text(encoding="utf-8"))
    lines = [f"# 历史规则检查 · {data['skill_name']}", "",
             f"历史材料：{agent_dir / 'SKILL.md'}", "",
             "本工单仅用于历史规则检查，未装配真实派发输入，不能作为当前生产效果验收。",
             "当前员工使用 --role/--task；真实执行回放使用隔离运行的 --handoff。", ""]
    if data.get("acceptance_source"):
        lines.extend([f"检查依据：{data['acceptance_source']}", ""])
    for case in data["evals"]:
        lines.extend([f"## 用例 {case['id']}", "", case["prompt"], "",
                      "检查材料（不可泄漏给生成模型）："])
        lines.extend(f"- {expectation}" for expectation in case["expectations"])
        if case.get("expected_output"):
            lines.append(f"参考产出：{case['expected_output']}")
        lines.append("")
    return "\n".join(lines)


def collect_agents() -> list[Path]:
    paths = _ProjectPaths.discover()
    registered = [paths.root / spec["entrypoint"] for spec in load_capabilities(paths)["roles"].values()]
    candidates = [path.parent for path in registered] + sorted(AGENTS.glob("decouple-*"))
    result, seen = [], set()
    for directory in candidates:
        resolved = directory.resolve()
        if resolved not in seen and find_cases(directory):
            seen.add(resolved)
            result.append(directory)
    return result


def _task_overrides(args) -> dict:
    result = {}
    for arg, key in (("role", "role"), ("mode", "mode"), ("account", "account_id"), ("goal", "goal")):
        if getattr(args, arg) is not None:
            result[key] = getattr(args, arg)
    if args.input is not None:
        result["input_refs"] = args.input
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="生产一致的评测输入；不调用模型、不代称行为通过")
    ap.add_argument("agent", nargs="?", help="当前员工目录，或需检查的历史 Agent 目录")
    ap.add_argument("--all", action="store_true", help="检查已登记员工与兼容 Agent 的既有用例")
    ap.add_argument("--validate-only", action="store_true", help="只检查结构与装配，不判定模型行为")
    ap.add_argument("--json", action="store_true", help="机读输出，prompt 与 assessment 分开")
    ap.add_argument("--role", help="当前岗位，如 writer、reviewer")
    ap.add_argument("--mode", help="该岗位已登记的工作模式")
    ap.add_argument("--account", help="已登记账号，如 studio")
    ap.add_argument("--goal", help="本次评测任务，或覆盖用例的目标")
    ap.add_argument("--input", action="append", help="显式材料引用，可重复")
    ap.add_argument("--task", help="项目内任务 JSON 文件，字段与生产任务一致")
    ap.add_argument("--cases", help="项目内 quality-cases JSON；每项可带 task 上下文")
    ap.add_argument("--handoff", help="隔离运行实际生成的 handoff.json；保持原 prompt")
    args = ap.parse_args(argv)
    paths = _ProjectPaths.discover()
    overrides = _task_overrides(args)
    current_request = bool(args.role or args.task or args.cases or args.handoff)
    if current_request and (args.agent or args.all):
        ap.error("当前任务参数不能与 agent 目录或 --all 混用")
    if args.handoff and (args.task or args.cases or overrides):
        ap.error("--handoff 使用真实输入，不能同时覆盖任务参数")
    if args.task and args.cases:
        ap.error("--task 与 --cases 选择一个")
    try:
        if current_request:
            if args.handoff:
                result = prepare_handoff_evaluation(paths, args.handoff)
            elif args.cases:
                path = checked_ref(paths, args.cases, must_exist=True, exclusions=_exclusions(paths))
                result = evaluation_cases(paths, path, defaults=overrides)
            else:
                task = {}
                if args.task:
                    path = checked_ref(paths, args.task, must_exist=True, exclusions=_exclusions(paths))
                    task = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(task, dict):
                        raise ValueError("Task JSON must be an object")
                task.update(overrides)
                result = prepare_evaluation(paths, task)
            if args.validate_only:
                print("PASS: 结构与实际上下文装配可用；模型行为尚未验证")
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render_prepared(result))
            return 0

        if overrides:
            ap.error("任务参数需要 --role、--task 或 --cases")
        targets = collect_agents() if args.all else ([Path(args.agent).resolve()] if args.agent else [])
        if not args.agent and not args.all:
            ap.error("需提供当前 --role/--task/--handoff，或 agent 目录/--all")
        if not targets:
            print("未发现任何含 evaluation/quality-cases.json 的 Agent")
            return 0
        bad, results = 0, []
        for directory in targets:
            cases = find_cases(directory)
            problems = validate(cases) if cases else [f"缺 evaluation/quality-cases.json: {directory}"]
            if problems:
                print(f"FAIL: {directory.name}: {'; '.join(problems)}", file=sys.stderr)
                bad += 1
                continue
            if args.validate_only:
                print(f"PASS: {directory.name} 结构合法；模型行为尚未验证")
            elif args.json:
                role = _role_for_directory(paths, directory)
                result = evaluation_cases(paths, cases, role=role) if role else {
                    **json.loads(cases.read_text(encoding="utf-8")),
                    "evaluation_mode": "legacy_rule_inspection", "execution_started": False,
                }
                results.append(result)
            else:
                print(render_worksheet(directory, cases))
        if args.json and not args.validate_only:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        return 1 if bad else 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
