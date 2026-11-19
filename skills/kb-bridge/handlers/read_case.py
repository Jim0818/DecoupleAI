#!/usr/bin/env python3
"""kb-bridge-read-case — read deep_research/{slug}/ assets.

Input:  {slug}
Output: {exists, slug, summary, sections, key_decisions, artifacts, created, updated}
        or {exists: false, slug}
"""
import sys
from datetime import datetime
from common.lib import (  # noqa: E402
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault, read_md,
    first_h2_outline, tldr_from_body,
)

SUMMARY_CANDIDATES = ["summary.md", "README.md", "process.md", "scout_brief.md"]


def main():
    inp = read_stdin_json()
    slug = (inp.get("slug") or "").strip()
    if not slug:
        err("slug required", code="BAD_INPUT")
    require_vault()

    case_dir = AI_WIKI_ROOT / "deep_research" / slug
    if not case_dir.is_dir():
        emit({"exists": False, "slug": slug})

    summary_path = None
    for cand in SUMMARY_CANDIDATES:
        p = case_dir / cand
        if p.exists():
            summary_path = p
            break

    summary = ""
    sections = []
    key_decisions = []
    created = updated = None

    if summary_path:
        try:
            fm, body = read_md(summary_path)
            summary = tldr_from_body(body, max_chars=800)
            sections = [{"h2": h} for h in first_h2_outline(body)[:20]]
            key_decisions = fm.get("key_decisions") or []
            created = fm.get("created")
            updated = fm.get("updated")
        except Exception:
            pass

    artifacts = []
    for p in sorted(case_dir.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            artifacts.append({
                "name": p.name,
                "path": str(p.relative_to(AI_WIKI_ROOT)),
                "size": p.stat().st_size,
            })

    if not created:
        created = datetime.fromtimestamp(case_dir.stat().st_birthtime).date().isoformat() \
            if hasattr(case_dir.stat(), 'st_birthtime') else None
    if not updated:
        updated = datetime.fromtimestamp(case_dir.stat().st_mtime).date().isoformat()

    emit({
        "exists": True,
        "slug": slug,
        "summary": summary,
        "sections": sections,
        "key_decisions": key_decisions,
        "artifacts": artifacts,
        "created": created,
        "updated": updated,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
