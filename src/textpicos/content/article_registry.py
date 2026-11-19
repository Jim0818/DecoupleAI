#!/usr/bin/env python3
"""Idempotent pending/published article registry maintenance."""
from __future__ import annotations
from textpicos.paths import ProjectPaths as _ProjectPaths

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import sys as _sys
_sys.path.append(str(_ProjectPaths.discover().root / "scripts" / "_deps"))

import yaml
import textpicos.content.article_contract as article_contract

REPO = _ProjectPaths.discover().root
PENDING = REPO / "articles/pending"
ARTIFACTS = REPO / "artifacts"

REGISTRIES = {
    ("decoupleai", "foundation"): "foundation-topic-registry.md",
    ("decoupleai", "practical_workshop"): "practical-workshop-topic-registry.md",
    ("decoupleai", "intelligence"): "intelligence-topic-registry.md",
    ("studio", "github-vault"): "studio-github-vault-registry.md",
    ("studio", "agent-mcp-engineering"): "studio-agent-mcp-registry.md",
    ("studio", "classic-python"): "studio-classic-python-registry.md",
    ("studio", "ai-data-infra"): "studio-ai-data-infra-registry.md",
    ("studio", "python-x-ai"): "studio-python-x-ai-registry.md",
    ("studio", "workflow-automation"): "studio-workflow-automation-registry.md",
    ("studio", "ai-monetization"): "studio-ai-monetization-registry.md",
    ("studio", "ai-visual-office"): "studio-ai-visual-office-registry.md",
    ("intellifuture", "hands-on-lab"): "intellifuture-hands-on-lab-registry.md",
    ("intellifuture", "signal-tower"): "intellifuture-signal-tower-registry.md",
    ("intellifuture", "ai-and-us"): "intellifuture-ai-and-us-registry.md",
}
COLUMN_ALIASES = {
    "经典 Python": "classic-python",
    "GitHub藏经阁": "github-vault",
    "AI 数据基础设施": "ai-data-infra",
    "实战工场": "practical_workshop",
    "解耦情报": "intelligence",
    "基石解耦": "foundation",
    # Public column rename; retain the existing storage/registry identity.
    "AI 上手坊": "hands-on-lab",
    "AI上手坊": "hands-on-lab",
    "手把手实验室": "hands-on-lab",
}
FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
STANDARD_NAME = re.compile(
    r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*(?:_(?:studio|intellifuture))?\.md$"
)


def frontmatter(path: Path) -> dict:
    match = FM_RE.match(path.read_text(encoding="utf-8", errors="replace"))
    return yaml.safe_load(match.group(1)) or {} if match else {}


def identity(path: Path, account_override: str = "", column_override: str = "") -> dict:
    try:
        rel = path.resolve().relative_to(PENDING.resolve())
        if len(rel.parts) < 3:
            raise ValueError(f"article is not under account/column: {rel}")
        path_account, path_column = rel.parts[0], rel.parts[1]
    except ValueError:
        if not account_override or not column_override:
            raise ValueError(f"article outside pending requires account/column: {path}")
        path_account, path_column = account_override, column_override
    fm = frontmatter(path)
    account = str(account_override or fm.get("account_id") or fm.get("account") or path_account)
    raw_column = str(column_override or fm.get("column") or path_column)
    column = COLUMN_ALIASES.get(raw_column, raw_column)
    stem = path.stem
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
    stem = re.sub(r"_(studio|intellifuture)$", "", stem)
    slug = str(fm.get("slug") or stem)
    article_date = str(fm.get("date") or "")
    if not article_date:
        match = re.match(r"^(\d{4}-\d{2}-\d{2})-", path.name)
        article_date = match.group(1) if match else date.today().isoformat()
    return {
        "account": account,
        "column": column,
        "slug": slug,
        "date": article_date,
        "title": str(fm.get("title") or slug),
        "path": str(path),
    }


def registry_path(info: dict) -> Path:
    name = REGISTRIES.get((info["account"], info["column"]))
    if not name:
        raise ValueError(f"no registry mapping for {info['account']}/{info['column']}")
    return ARTIFACTS / name


def upsert(path: Path, info: dict, status: str) -> bool:
    if not path.is_file():
        raise FileNotFoundError(f"registry missing: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    row_index = next(
        (i for i, line in enumerate(lines)
         if line.startswith("|") and f"| {info['slug']} |" in line),
        None,
    )
    if path.name == "foundation-topic-registry.md":
        row = f"| {info['date']} | {info['slug']} | {info['slug']} | {info['title']} | {status} |"
    else:
        row = f"| {info['date']} | {info['slug']} | {info['title']} | {status} |"
    if row_index is not None:
        if lines[row_index] == row:
            return False
        lines[row_index] = row
    else:
        separator = next(
            (i for i, line in enumerate(lines)
             if line.startswith("|") and set(line.replace("|", "").replace(":", "").replace("-", "").strip()) == set()),
            None,
        )
        if separator is None:
            raise ValueError(f"registry table header not found: {path}")
        lines.insert(separator + 1, row)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def register(article: Path, status: str, account: str = "", column: str = "") -> dict:
    info = identity(article, account, column)
    registry = registry_path(info)
    changed = upsert(registry, info, status)
    return {**info, "registry": str(registry), "status": status, "changed": changed}


def pending_articles() -> list[Path]:
    return sorted(
        path for path in PENDING.rglob("*.md")
        if "visuals" not in path.parts and path.name not in {"README.md", "TL;DR.md"}
    )


def audit() -> dict:
    findings = []
    for article in pending_articles():
        try:
            info = identity(article)
            registry = registry_path(info)
            text = registry.read_text(encoding="utf-8") if registry.is_file() else ""
            if f"| {info['slug']} |" not in text:
                findings.append({"severity": "error", "kind": "registry_orphan_article",
                                 "article": str(article.relative_to(REPO))})
            if not STANDARD_NAME.match(article.name):
                findings.append({"severity": "error", "kind": "naming_convention_violation",
                                 "article": str(article.relative_to(REPO))})
            contract = article_contract.validate_article(article, "draft")
            findings.extend({
                "severity": "error",
                "kind": item["kind"],
                "article": str(article.relative_to(REPO)),
                "message": item["message"],
            } for item in contract["findings"] if item.get("kind") != "narrative_risk_candidate")
        except Exception as exc:
            findings.append({"severity": "error", "kind": "registry_mapping_error",
                             "article": str(article.relative_to(REPO)), "message": str(exc)})
    return {"articles": len(pending_articles()), "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("register-pending", "mark-published"):
        item = sub.add_parser(command)
        item.add_argument("article", type=Path)
        item.add_argument("--account", default="")
        item.add_argument("--column", default="")
    sub.add_parser("audit")
    args = parser.parse_args()
    if args.command == "audit":
        result = audit()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if any(f["severity"] == "error" for f in result["findings"]) else 0
    status = "pending" if args.command == "register-pending" else "published"
    print(json.dumps(register(args.article, status, args.account, args.column), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
