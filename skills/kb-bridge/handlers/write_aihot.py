#!/usr/bin/env python3
"""kb-bridge-write-aihot — write aihot-researcher scored items to raw.

Input:  {date, items:[{title, url, score, evidence, dimensions?}]}
Output: {raw_path, items_written, items_skipped_dedup}
"""
import sys
from datetime import date as date_cls, datetime
from common.lib import (  # noqa: E402
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault,
    read_md, write_md_atomic, append_log,
)


def main():
    inp = read_stdin_json()
    d = inp.get("date") or str(date_cls.today())
    items = inp.get("items") or []
    if not items:
        emit({"raw_path": None, "items_written": 0, "items_skipped_dedup": 0})
    require_vault()

    raw_path = AI_WIKI_ROOT / "03_raw" / "aihot" / f"{d}.md"

    # Load existing urls for dedup
    existing_urls = set()
    existing_fm, existing_body = {}, ""
    if raw_path.exists():
        try:
            existing_fm, existing_body = read_md(raw_path)
        except Exception:
            existing_body = raw_path.read_text(encoding="utf-8")
        # crude url extraction
        import re
        for m in re.finditer(r"url:\s*(\S+)", existing_body):
            existing_urls.add(m.group(1).rstrip(",)"))

    new_items = [it for it in items if (it.get("url") or "") not in existing_urls]
    skipped = len(items) - len(new_items)

    fm = existing_fm or {
        "title": f"aihot {d}",
        "type": "source",
        "status": "captured",
        "created": d,
        "updated": str(date_cls.today()),
        "source": "aihot",
        "confidence": "extracted",
        "tags": ["aihot", "raw"],
        "account": "all",
    }
    fm["updated"] = str(date_cls.today())

    new_items_sorted = sorted(new_items, key=lambda x: float(x.get("score") or 0), reverse=True)
    block_lines = []
    for it in new_items_sorted:
        block_lines.append(f"### {it.get('title','(untitled)')}")
        block_lines.append(f"- url: {it.get('url','')}")
        block_lines.append(f"- score: {it.get('score', 0)}")
        if it.get("dimensions"):
            block_lines.append(f"- dimensions: {it['dimensions']}")
        if it.get("evidence"):
            block_lines.append(f"- evidence: > {it['evidence']}")
        block_lines.append("")

    sep = "\n" if existing_body and not existing_body.endswith("\n") else ""
    new_body = (existing_body or "") + sep + "\n".join(block_lines)
    write_md_atomic(raw_path, fm, new_body)

    append_log("kb-bridge-write-aihot", d, {
        "raw_path": str(raw_path.relative_to(AI_WIKI_ROOT)),
        "items_written": len(new_items),
        "items_skipped_dedup": skipped,
    })
    emit({
        "raw_path": str(raw_path.relative_to(AI_WIKI_ROOT)),
        "items_written": len(new_items),
        "items_skipped_dedup": skipped,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
