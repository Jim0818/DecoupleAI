#!/usr/bin/env python3
"""audit_skill.py — deterministic structural audit for Claude skills.

Portable, stdlib-only. Reports *mechanical* facts about a skill (line count,
frontmatter completeness, presence of examples/tables/checklists, bundled
scripts/references, evaluation cases, hardcoded-secret heuristics, risky shell
ops). It does NOT judge quality — "is the description good?", "are the examples
right?" are LLM-territory (the skill-optimizer Phase 1 handles those). Keeping
the deterministic split here is the same discipline a good skill follows:
same input -> same output belongs in a script, not a prompt.

Usage:
    python3 audit_skill.py <path> [<path> ...] [--json]

<path> may be:
  - a SKILL.md file
  - a skill directory (contains SKILL.md or skill.md)
  - a parent directory holding many skill subdirectories (audited recursively,
    one level deep by default; use --deep to recurse further)

Exit code is always 0 (this is a report, not a gate). Findings are tagged
ERROR / WARN / INFO; severity is advisory.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# --- thresholds (tunable; sourced from the bundled handbook) ---
LINE_HARD = 500          # Anthropic's suggested SKILL.md body ceiling
LINE_WARN = 300          # comfort/warning band
DESC_MIN_CHARS = 40      # very short description -> likely too vague to trigger well
DESC_MAX_CHARS = 1024    # extremely long -> Level-1 token bloat

SECRET_RE = re.compile(
    r"""(?ix)
    (api[_-]?key|secret|password|passwd|token|access[_-]?key|private[_-]?key)
    \s*[:=]\s*
    ['"][A-Za-z0-9_\-/.+]{12,}['"]
    """,
    re.VERBOSE,
)
# obvious placeholders / env reads are not real secrets
SECRET_ALLOW_RE = re.compile(
    r"(?i)(os\.environ|getenv|process\.env|\$\{|\$[A-Z_]+|input\(|argparse|"
    r"required|example|示例|placeholder|replace[-_ ]?me|your[-_ ]|xxxx|<your|test[-_])"
)
RISKY_RE = re.compile(
    r"(?i)(rm\s+-rf|drop\s+table|truncate\s+table|delete\s+from|"
    r"\bmv\s+|>\s*/|--force|git\s+push\s+--force|chmod\s+777)"
)
CONFIRM_RE = re.compile(r"(?i)(read\s+-p|confirm|are you sure|y/N|确认|备份|backup)")

FRONTMATTER_RE = re.compile(r"^﻿?---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def find_skill_md(d: Path) -> Path | None:
    for name in ("SKILL.md", "skill.md"):
        p = d / name
        if p.is_file():
            return p
    return None


def parse_frontmatter(text: str):
    """Return (meta: dict, body: str). meta is a flat dict from a *lenient*
    line parser (no yaml dep): top-level `key: value` and `key:` block heads."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    raw, body = m.group(1), m.group(2)
    meta: dict[str, str] = {}
    cur_key = None
    buf: list[str] = []
    for line in raw.splitlines():
        if re.match(r"^[A-Za-z0-9_\-]+\s*:", line) and not line.startswith(" "):
            if cur_key is not None:
                meta[cur_key] = "\n".join(buf).strip()
            cur_key, _, rest = line.partition(":")
            cur_key = cur_key.strip()
            buf = [rest.strip()]
        else:
            buf.append(line)
    if cur_key is not None:
        meta[cur_key] = "\n".join(buf).strip()
    # strip yaml block scalar markers (| or >) left as the value
    for k, v in list(meta.items()):
        if v in ("|", ">", "|-", ">-", "|+", ">+"):
            meta[k] = ""  # block body collapsed by lenient parser; treat as present-but-multiline
    return meta, body


def scan_scripts(skill_dir: Path):
    """Heuristic secret + risky-op scan across bundled script files."""
    findings = []
    exts = {".sh", ".py", ".js", ".ts", ".rb", ".pl", ".bash", ".zsh"}
    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file() or f.suffix not in exts:
            continue
        try:
            lines = f.read_text(errors="replace").splitlines()
        except Exception:
            continue
        rel = f.relative_to(skill_dir)
        for i, ln in enumerate(lines, 1):
            if SECRET_RE.search(ln) and not SECRET_ALLOW_RE.search(ln):
                findings.append(("ERROR", f"疑似硬编码密钥 {rel}:{i}: {ln.strip()[:80]}"))
            if RISKY_RE.search(ln):
                # only flag if no confirmation/backup keyword nearby (±3 lines)
                lo, hi = max(0, i - 4), min(len(lines), i + 3)
                if not any(CONFIRM_RE.search(x) for x in lines[lo:hi]):
                    findings.append(("WARN", f"危险操作无确认/备份 {rel}:{i}: {ln.strip()[:80]}"))
    return findings


def audit_one(skill_md: Path) -> dict:
    skill_dir = skill_md.parent
    text = skill_md.read_text(errors="replace")
    lines = text.splitlines()
    nlines = len(lines)
    meta, body = parse_frontmatter(text)
    findings: list[tuple[str, str]] = []

    # frontmatter
    if meta is None:
        findings.append(("ERROR", "缺少 YAML frontmatter（--- 包裹的头信息）"))
        meta = {}
    if "name" not in meta or not meta.get("name"):
        findings.append(("ERROR", "frontmatter 缺 name"))
    elif not KEBAB_RE.match(meta["name"]):
        findings.append(("WARN", f"name 非小写连字符格式: {meta['name']}"))
    desc = meta.get("description", "")
    if not desc:
        findings.append(("ERROR", "frontmatter 缺 description（决定自动触发）"))
    else:
        dlen = len(desc)
        if dlen and dlen < DESC_MIN_CHARS:
            findings.append(("WARN", f"description 偏短({dlen}字)，可能触发不准；补使用场景关键词"))
        if dlen > DESC_MAX_CHARS:
            findings.append(("WARN", f"description 过长({dlen}字)，Level-1 常驻成本高；精简"))
        neg = bool(re.search(r"(?i)(不要在|不要触发|do not (use|trigger)|don't|不适用|不处理)", desc))
        if not neg:
            findings.append(("INFO", "description 无反例触发说明（'不要在…时触发'），易与近义 skill 抢触发"))
    if "version" not in (meta or {}):
        findings.append(("INFO", "无 version 元数据（生命周期管理；按宿主项目约定决定是否需要）"))

    # size
    if nlines > LINE_HARD:
        findings.append(("ERROR", f"SKILL.md {nlines} 行 > {LINE_HARD}（硬上限），应拆分/外置 references"))
    elif nlines > LINE_WARN:
        findings.append(("WARN", f"SKILL.md {nlines} 行 > {LINE_WARN}（警戒），考虑外置 references"))

    # body content heuristics
    body_l = body.lower()
    has_code = body.count("```") >= 2
    has_table = bool(re.search(r"^\s*\|.+\|\s*$", body, re.MULTILINE))
    has_checklist = "- [ ]" in body or "- [x]" in body.lower()
    has_beforeafter = bool(re.search(r"(?i)(before|after|改之前|改之后|之前|之后|❌|✅)", body))
    if not has_code and not has_beforeafter:
        findings.append(("WARN", "正文无代码示例/Before-After（反模式3：纯文字描述，AI 易瞎发挥）"))
    if not has_table:
        findings.append(("INFO", "正文无表格（结构化信息用表格 AI 读得更准）"))

    # bundled assets
    subdirs = {p.name for p in skill_dir.iterdir() if p.is_dir()}
    has_refs = "references" in subdirs or "reference" in subdirs
    script_exts = {".sh", ".py", ".js", ".ts", ".rb", ".pl", ".bash", ".zsh"}
    has_scripts = "scripts" in subdirs or any(
        f.suffix in script_exts for f in skill_dir.iterdir() if f.is_file()
    )
    has_eval = any(
        (skill_dir / e).exists() for e in ("evaluation", "evals", "eval")
    ) or bool(list(skill_dir.rglob("*trigger-cases*"))) or bool(
        list(skill_dir.rglob("*quality-cases*"))
    ) or bool(list(skill_dir.rglob("evals.json")))
    if not has_eval:
        findings.append(("INFO", "无评估用例（evaluation/ 或 evals.json）；无回归基线，改动好坏无法证伪"))

    # script safety
    findings.extend(scan_scripts(skill_dir))

    counts = {"ERROR": 0, "WARN": 0, "INFO": 0}
    for sev, _ in findings:
        counts[sev] += 1
    return {
        "skill": meta.get("name") or skill_dir.name,
        "path": str(skill_md),
        "lines": nlines,
        "has_frontmatter": meta is not None and bool(meta),
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
        if direct:
            return [direct]
        # treat as a parent of skills
        out = []
        globber = path.rglob if deep else (lambda *_: [c for c in path.iterdir() if c.is_dir()])
        if deep:
            for smd in path.rglob("SKILL.md"):
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
    ap = argparse.ArgumentParser(description="Deterministic structural audit for Claude skills.")
    ap.add_argument("paths", nargs="+", help="SKILL.md / skill dir / parent dir")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--deep", action="store_true", help="recurse fully when given a parent dir")
    args = ap.parse_args()

    reports = []
    for raw in args.paths:
        p = Path(raw).expanduser()
        if not p.exists():
            print(f"WARN: 路径不存在: {p}", file=sys.stderr)
            continue
        for smd in collect_targets(p, args.deep):
            reports.append(audit_one(smd))

    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return

    if not reports:
        print("未找到任何 SKILL.md。")
        return

    icon = {"ERROR": "🔴", "WARN": "🟡", "INFO": "🔵"}
    tot = {"ERROR": 0, "WARN": 0, "INFO": 0}
    for r in reports:
        print(f"\n=== {r['skill']}  ({r['lines']} 行) ===")
        print(f"  {r['path']}")
        flags = []
        flags.append("示例" + ("✓" if r["has_examples"] else "✗"))
        flags.append("表格" + ("✓" if r["has_table"] else "✗"))
        flags.append("references" + ("✓" if r["has_references"] else "✗"))
        flags.append("scripts" + ("✓" if r["has_scripts"] else "✗"))
        flags.append("评估" + ("✓" if r["has_eval"] else "✗"))
        print("  结构: " + "  ".join(flags))
        if not r["findings"]:
            print("  ✅ 无机械问题")
        for f in r["findings"]:
            print(f"  {icon[f['severity']]} {f['severity']}: {f['msg']}")
        for k in tot:
            tot[k] += r["counts"][k]

    print(f"\n=== 汇总：{len(reports)} 个 skill ===")
    print(f"  🔴 ERROR {tot['ERROR']}  🟡 WARN {tot['WARN']}  🔵 INFO {tot['INFO']}")
    print("  注：本脚本只报确定性结构事实；description/示例的『好不好』由 LLM 在问题分析阶段判断。")


if __name__ == "__main__":
    main()
