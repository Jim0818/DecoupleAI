#!/usr/bin/env python3
"""kb-bridge-write-case — case-* unified write channel.

Input: {slug, filename, content, frontmatter?, phase?, agent?}
Output: {written_path, bytes_written, is_new}
"""
import os
import sys
from pathlib import Path
from common.lib import (  # noqa: E402
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault,
    parse_frontmatter, dump_frontmatter, write_md_atomic, append_log,
)


def main():
    inp = read_stdin_json()
    slug = inp.get("slug")
    filename = inp.get("filename")
    content = inp.get("content")
    if not slug or not filename or content is None:
        err("slug/filename/content required", code="BAD_INPUT")
    require_vault()

    # Path safety: must be relative, no .., must stay under {slug}/
    if os.path.isabs(filename) or ".." in Path(filename).parts:
        err(f"unsafe filename: {filename}", code="UNSAFE_PATH")

    case_root = AI_WIKI_ROOT / "deep_research" / slug
    target = (case_root / filename).resolve()
    try:
        target.relative_to(case_root.resolve())
    except ValueError:
        err(f"filename escapes case dir: {filename}", code="UNSAFE_PATH")

    is_new = not target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)

    if filename.endswith(".md"):
        fm_override = inp.get("frontmatter")
        existing_fm, body = parse_frontmatter(content)
        fm = {**existing_fm, **(fm_override or {})}
        write_md_atomic(target, fm, body)
    else:
        # Atomic write for non-md too
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)

    bytes_written = target.stat().st_size

    append_log("kb-bridge-write-case", slug, {
        "filename": filename,
        "phase": inp.get("phase") or "-",
        "agent": inp.get("agent") or "-",
        "bytes": bytes_written,
        "is_new": is_new,
    })
    emit({
        "written_path": str(target.relative_to(AI_WIKI_ROOT)),
        "bytes_written": bytes_written,
        "is_new": is_new,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
