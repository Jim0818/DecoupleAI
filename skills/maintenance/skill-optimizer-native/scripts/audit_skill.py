#!/usr/bin/env python3
"""audit_skill.py — deterministic structural audit for TextPicOS skills.

Reports *mechanical* facts about a skill (line count,
frontmatter completeness, presence of examples/tables/checklists, bundled
scripts/references, evaluation cases, hardcoded-secret heuristics, risky shell
ops). It does NOT judge quality — "is the description good?", "are the examples
right?" are LLM-territory. Frontmatter and budgets use PyYAML installed in the project's Python environment. For repository skills, line budgets come from
config/system/complexity-budget.yaml; external skills have no local
line budget. This is not a substitute for the host's Skill validator.

Usage:
    python3 audit_skill.py <path> [<path> ...] [--json] [--gate]

<path> may be:
  - a SKILL.md file
  - a skill directory (contains SKILL.md or skill.md)
  - a parent directory holding many skill subdirectories (audited recursively,
    one level deep by default; use --deep to recurse further)

Missing/empty targets always return non-zero. `--gate` also returns non-zero
when any ERROR exists.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = next((parent for parent in Path(__file__).resolve().parents if (parent / "config/system/capabilities.json").is_file()), None)
if REPO_ROOT is None:
    raise SystemExit("ERROR: TextPicOS capability registry not found above the native audit tool")
BUDGET_PATH = REPO_ROOT / "config/system/complexity-budget.yaml"
try:
    import yaml
except ImportError as exc:
    raise SystemExit(f"ERROR: 无法加载 PyYAML，请在已配置项目依赖的 Python 环境中执行: {exc}") from exc

NAME_MAX_CHARS = 64
DESCRIPTION_MAX_CHARS = 1024

SECRET_QUOTED_RE = re.compile(
    r"""(?ix)
    (api[_-]?key|secret|password|passwd|token|access[_-]?key|private[_-]?key)
    \s*[:=]\s*
    ['"][^'"\s]{12,}['"]
    """,
    re.VERBOSE,
)
SECRET_BARE_RE = re.compile(
    r"""(?ix)
    (api[_-]?key|secret|password|passwd|token|access[_-]?key|private[_-]?key)
    \s*[:=]\s*
    [A-Za-z0-9_/+\-]{12,}(?![A-Za-z0-9_/+\-])
    """,
    re.VERBOSE,
)
RISKY_RE = re.compile(
    r"(?i)(rm\s+-rf|drop\s+table|truncate\s+table|delete\s+from|"
    r"\bmv\s+|>\s*/|-{2}force|chmod\s+777)"
)
RUNTIME_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
FRONTMATTER_RE = re.compile(r"\A(?:\ufeff)?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(.*)", re.DOTALL)
KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEPRECATED_PATH_RE = re.compile(
    r"(\.Codex/skills|docs/issues/todo-update|runbooks/retro-logs|runbooks/sync-matrix\.md)"
)
HOST_TOOL_RE = re.compile(
    r"\b(TaskCreate|TaskUpdate|AskUserQuestion|ExitPlanMode|EnterPlanMode)\b"
)


def find_skill_md(d: Path) -> Path | None:
    for name in ("SKILL.md", "skill.md"):
        p = d / name
        if p.is_file():
            return p
    return None


class UniqueKeyLoader(yaml.SafeLoader):
    """Fail on duplicate YAML keys rather than silently taking the last value."""


def _construct_unique_mapping(loader, node):
    explicit_keys = set()
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=True)
        try:
            duplicate = key in explicit_keys
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                None, None, "unhashable key", key_node.start_mark
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                None, None, "duplicate key", key_node.start_mark
            )
        explicit_keys.add(key)
    return yaml.constructor.SafeConstructor.construct_mapping(loader, node)


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _yaml_location(exc: yaml.YAMLError) -> str:
    mark = getattr(exc, "problem_mark", None)
    return f"（第 {mark.line + 1} 行，第 {mark.column + 1} 列）" if mark else ""


def parse_frontmatter(text: str) -> tuple[dict | None, str, list[str]]:
    """Return parsed YAML mapping, body, and syntax findings without raw input."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text, ["缺少 YAML frontmatter（--- 包裹的头信息）"]
    raw, body = m.group(1), m.group(2)
    try:
        meta = yaml.load(raw, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        return None, body, [f"frontmatter YAML 无效{_yaml_location(exc)}"]
    if not isinstance(meta, dict):
        return None, body, ["frontmatter 必须是 YAML 映射"]
    return meta, body, []


def line_budget(skill_md: Path) -> tuple[int, int] | None:
    """Read this repository's target/hard limit; external paths are ungoverned."""
    try:
        rel = Path(os.path.abspath(skill_md)).relative_to(REPO_ROOT)
    except ValueError:
        return None
    parts = rel.parts
    if parts[0] == "agents":
        key = "incubating_agent_skill_lines" if "_incubating" in parts else "production_agent_skill_lines"
    elif parts[0] == "skills" or parts[:2] in {
        (".agents", "skills"), (".claude", "skills")
    }:
        key = "tool_skill_lines"
    else:
        return None
    data = yaml.load(BUDGET_PATH.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    budgets = data.get("budgets") if isinstance(data, dict) else None
    entry = budgets.get(key) if isinstance(budgets, dict) else None
    if not isinstance(entry, dict):
        raise ValueError(f"预算缺少 {key}: {BUDGET_PATH}")
    target, hard_max = entry.get("target"), entry.get("hard_max")
    if any(type(value) is not int or value <= 0 for value in (target, hard_max)):
        raise ValueError(f"预算 {key} 的 target/hard_max 无效: {BUDGET_PATH}")
    if target > hard_max:
        raise ValueError(f"预算 {key} 的 target 大于 hard_max: {BUDGET_PATH}")
    return target, hard_max


def scan_scripts(skill_dir: Path):
    """Heuristic secret + risky-op scan across bundled script files."""
    findings = []
    exts = {".sh", ".py", ".js", ".ts", ".mjs", ".cjs", ".rb", ".pl", ".bash", ".zsh"}
    shell_exts = {".sh", ".bash", ".zsh"}
    for f in sorted(skill_dir.rglob("*")):
        rel = f.relative_to(skill_dir)
        if any(part in RUNTIME_DIRS for part in rel.parts):
            continue
        if f.is_symlink() and (f.suffix in exts or f.is_dir() or "scripts" in rel.parts):
            try:
                target = f.resolve(strict=True)
            except OSError:
                findings.append(("ERROR", f"脚本符号链接失效 {rel}"))
                continue
            if not target.is_relative_to(skill_dir.resolve()):
                findings.append(("ERROR", f"脚本符号链接越界 {rel}"))
                continue
            if f.is_dir():
                findings.append(("ERROR", f"脚本目录符号链接无法完整扫描 {rel}"))
                continue
        if not f.is_file() or f.suffix not in exts:
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            reason = getattr(exc, "strerror", None) or type(exc).__name__
            findings.append(("ERROR", f"无法读取脚本 {rel}: {reason}"))
            continue
        for i, ln in enumerate(lines, 1):
            if SECRET_QUOTED_RE.search(ln) or (
                f.suffix in shell_exts and SECRET_BARE_RE.search(ln)
            ):
                findings.append(("ERROR", f"疑似硬编码密钥 {rel}:{i}（源码已脱敏）"))
            if RISKY_RE.search(ln):
                findings.append(("WARN", f"危险操作待人工核对 {rel}:{i}（源码已脱敏）"))
    return findings


def audit_one(skill_md: Path) -> dict:
    skill_dir = skill_md.parent
    if skill_md.is_symlink():
        target = skill_md.resolve(strict=True)
        if not target.is_relative_to(skill_dir.resolve()):
            raise ValueError(f"SKILL.md 符号链接越界: {skill_md}")
    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    nlines = len(lines)
    meta, body, parse_errors = parse_frontmatter(text)
    findings: list[tuple[str, str]] = []

    # frontmatter
    findings.extend(("ERROR", message) for message in parse_errors)
    if meta is None:
        meta = {}
    name = meta.get("name")
    if not isinstance(name, str) or not name.strip():
        findings.append(("ERROR", "frontmatter name 必须是非空字符串"))
    elif not KEBAB_RE.fullmatch(name):
        findings.append(("ERROR", f"name 非小写连字符格式: {name}"))
    elif len(name) > NAME_MAX_CHARS:
        findings.append(("ERROR", f"name 超过 {NAME_MAX_CHARS} 字符"))
    desc = meta.get("description")
    if not isinstance(desc, str) or not desc.strip():
        findings.append(("ERROR", "frontmatter description 必须是非空字符串"))
    elif len(desc) > DESCRIPTION_MAX_CHARS:
        findings.append(("ERROR", f"description 超过 {DESCRIPTION_MAX_CHARS} 字符"))
    elif desc.lstrip().startswith("[TODO:"):
        findings.append(("ERROR", "description 含未完成 TODO 占位"))
    if skill_md.name != "SKILL.md":
        findings.append(("ERROR", "技能入口文件名必须为 SKILL.md"))

    # size
    budget = line_budget(skill_md)
    if budget:
        target, hard_max = budget
        if nlines > hard_max:
            findings.append(("ERROR", f"SKILL.md {nlines} 行 > {hard_max}（仓库预算硬上限）"))
        elif nlines > target:
            findings.append(("WARN", f"SKILL.md {nlines} 行 > {target}（仓库预算目标）"))

    # body content heuristics
    has_code = body.count("```") >= 2
    has_table = bool(re.search(r"^\s*\|.+\|\s*$", body, re.MULTILINE))
    has_checklist = "- [ ]" in body or "- [x]" in body.lower()
    has_beforeafter = bool(re.search(r"(?i)(before|after|改之前|改之后|之前|之后|❌|✅)", body))
    for match in DEPRECATED_PATH_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        findings.append(("WARN", f"旧路径提及 {match.group(0)}（line {line}；需核对语境）"))
    for match in HOST_TOOL_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        findings.append((
            "WARN",
            f"宿主工具名提及 {match.group(0)}（line {line}；需核对语境）",
        ))

    parts = skill_md.resolve().parts
    if ".agents" in parts and "skills" in parts:
        repo = skill_md.resolve().parents[3]
        mirror = repo / ".claude" / "skills" / skill_dir.name / skill_md.name
        if mirror.is_file() and mirror.read_bytes() != skill_md.read_bytes():
            findings.append(("ERROR", f"Skill 镜像 hash 不一致: {mirror}"))

    # bundled assets
    subdirs = {p.name for p in skill_dir.iterdir() if p.is_dir()}
    has_refs = "references" in subdirs or "reference" in subdirs
    script_exts = {".sh", ".py", ".js", ".ts", ".mjs", ".cjs", ".rb", ".pl", ".bash", ".zsh"}
    has_scripts = "scripts" in subdirs or any(
        f.suffix in script_exts for f in skill_dir.iterdir() if f.is_file()
    )
    has_eval = any(
        (skill_dir / e).exists() for e in ("evaluation", "evals", "eval")
    ) or bool(list(skill_dir.rglob("*trigger-cases*"))) or bool(
        list(skill_dir.rglob("*quality-cases*"))
    ) or bool(list(skill_dir.rglob("evals.json")))

    # script safety
    findings.extend(scan_scripts(skill_dir))

    counts = {"ERROR": 0, "WARN": 0, "INFO": 0}
    for sev, _ in findings:
        counts[sev] += 1
    return {
        "skill": name if isinstance(name, str) and name else skill_dir.name,
        "path": str(skill_md),
        "lines": nlines,
        "has_frontmatter": not parse_errors,
        "has_examples": has_code or has_beforeafter,
        "has_table": has_table,
        "has_checklist": has_checklist,
        "has_references": has_refs,
        "has_scripts": has_scripts,
        "has_eval": has_eval,
        "counts": counts,
        "findings": [{"severity": s, "msg": m} for s, m in findings],
    }


def collect_targets(path: Path, deep: bool) -> list[Path]:
    """Resolve a path argument to a list of SKILL.md files."""
    if path.is_file() and path.name.lower() == "skill.md":
        return [path]
    if path.is_dir():
        direct = find_skill_md(path)
        if direct and not deep:
            return [direct]
        # treat as a parent of skills
        out = []
        if deep:
            if direct:
                out.append(direct)
            for smd in path.rglob("SKILL.md"):
                if smd not in out:
                    out.append(smd)
            for smd in path.rglob("skill.md"):
                if smd not in out:
                    out.append(smd)
        else:
            for child in sorted(path.iterdir()):
                if child.is_dir():
                    smd = find_skill_md(child)
                    if smd:
                        out.append(smd)
        return out
    return []


def main():
    ap = argparse.ArgumentParser(description="Deterministic structural audit for TextPicOS skills.")
    ap.add_argument("paths", nargs="+", help="SKILL.md / skill dir / parent dir")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--deep", action="store_true", help="recurse fully when given a parent dir")
    ap.add_argument("--gate", action="store_true", help="exit non-zero when ERROR findings exist")
    args = ap.parse_args()

    reports = []
    input_errors = []
    for raw in args.paths:
        p = Path(raw).expanduser()
        if not p.exists():
            input_errors.append(f"路径不存在: {p}")
            continue
        targets = collect_targets(p, args.deep)
        if not targets:
            input_errors.append(f"未找到 SKILL.md: {p}")
            continue
        for smd in targets:
            try:
                reports.append(audit_one(smd))
            except (OSError, ValueError, yaml.YAMLError) as exc:
                input_errors.append(f"审计失败 {smd}: {exc}")
    for error in input_errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        if input_errors:
            raise SystemExit(2)
        if args.gate and any(r["counts"]["ERROR"] for r in reports):
            raise SystemExit(1)
        return

    if not reports:
        raise SystemExit(2)

    icon = {"ERROR": "🔴", "WARN": "🟡", "INFO": "🔵"}
    tot = {"ERROR": 0, "WARN": 0, "INFO": 0}
    for r in reports:
        print(f"\n=== {r['skill']}  ({r['lines']} 行) ===")
        print(f"  {r['path']}")
        flags = []
        flags.append("示例:" + ("有" if r["has_examples"] else "无"))
        flags.append("表格:" + ("有" if r["has_table"] else "无"))
        flags.append("references:" + ("有" if r["has_references"] else "无"))
        flags.append("scripts:" + ("有" if r["has_scripts"] else "无"))
        flags.append("评估:" + ("有" if r["has_eval"] else "无"))
        print("  结构: " + "  ".join(flags))
        if not r["findings"]:
            print("  ✅ 无机械问题")
        for f in r["findings"]:
            print(f"  {icon[f['severity']]} {f['severity']}: {f['msg']}")
        for k in tot:
            tot[k] += r["counts"][k]

    print(f"\n=== 汇总：{len(reports)} 个 skill ===")
    print(f"  🔴 ERROR {tot['ERROR']}  🟡 WARN {tot['WARN']}  🔵 INFO {tot['INFO']}")
    print("  注：本脚本只报机械事实；description/示例的质量需另行判断。")
    if input_errors:
        raise SystemExit(2)
    if args.gate and tot["ERROR"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
