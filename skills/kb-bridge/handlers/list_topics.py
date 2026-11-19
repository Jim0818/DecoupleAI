#!/usr/bin/env python3
"""kb-bridge-list-topics — list 选题库 candidates.

Input:  {account?, column?, status="captured", limit=50}
Output: [{slug, title, account, column, created, status, path, references?}]

Note: returns ONE entry per 选题库 .md file (file-level granularity). When
REFERENCE_INDEX.json (built by kb-reference-index) is present, each entry is
joined to the参考素材 mapped to that file via `references[]`.
"""
import json
import sys
from datetime import datetime
from common.lib import (  # noqa: E402
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault, read_md, iter_md,
)

ACCT_DIR = {
    "decoupleai":   "DecoupleAI",
    "studio":       "数据STUDIO",
    "intellifuture":"智性未来",
}

REFERENCE_INDEX = "/Users/jim/.claude/skills/kb-reference-index/REFERENCE_INDEX.json"
MAX_REFS = 12  # cap references per topic to avoid context bloat


def load_references_by_file():
    """Map vault-relative 分文件 path -> [{file,title,url,summary}] from REFERENCE_INDEX.json.
    Returns {} if the index is absent (graceful degradation)."""
    try:
        with open(REFERENCE_INDEX, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    by_file = {}
    for a in data.get("articles", []):
        ref = {"file": a.get("file"), "title": a.get("title"),
               "url": a.get("url"), "summary": a.get("summary")}
        for tf in a.get("target_topic_files", []):
            by_file.setdefault(tf, []).append(ref)
    return by_file


def main():
    inp = read_stdin_json()
    require_vault()

    account = inp.get("account") or "all"
    column = inp.get("column")
    status_filter = inp.get("status") or "captured"
    limit = int(inp.get("limit") or 50)

    topiclib_root = AI_WIKI_ROOT / "选题库"
    if not topiclib_root.is_dir():
        err(f"选题库 dir not found: {topiclib_root}", code="PATH_NOT_FOUND")

    if account == "all":
        roots = [topiclib_root]
    else:
        sub = ACCT_DIR.get(account)
        if not sub:
            err(f"unknown account: {account}", code="INVALID_ACCOUNT")
        roots = [topiclib_root / sub]

    refs_by_file = load_references_by_file()

    out = []
    for root in roots:
        for path in iter_md(root):
            try:
                fm, _body = read_md(path)
            except Exception:
                continue
            # Allow files without explicit frontmatter (legacy topic lists)
            doc_status = fm.get("status", "captured")
            if status_filter != "any" and doc_status != status_filter:
                continue
            doc_column = fm.get("column") or path.parent.name
            if column and doc_column != column:
                continue
            # Account inferred from path if not in frontmatter
            doc_account = fm.get("account")
            if not doc_account:
                try:
                    rel_parts = path.relative_to(topiclib_root).parts
                    if rel_parts:
                        for k, v in ACCT_DIR.items():
                            if rel_parts[0] == v:
                                doc_account = k
                                break
                except ValueError:
                    pass
            rel_path = str(path.relative_to(AI_WIKI_ROOT))
            entry = {
                "slug": path.stem,
                "title": str(fm.get("title") or path.stem),
                "account": doc_account or "all",
                "column": doc_column,
                "created": str(fm.get("created") or ""),
                "status": doc_status,
                "path": rel_path,
            }
            refs = refs_by_file.get(rel_path)
            if refs:
                entry["references"] = refs[:MAX_REFS]
            out.append(entry)

    out.sort(key=lambda x: x.get("created") or "", reverse=True)
    emit(out[:limit])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
