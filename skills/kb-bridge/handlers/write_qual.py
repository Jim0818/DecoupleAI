#!/usr/bin/env python3
"""kb-bridge-write-qual — style-analyst --qualitative competitor analysis writer.

Input: {slug, competitor_account, source_url, publish_date, medium?, viral_score?,
        qual_version?, analyst?, qual_body, account_fit?, technique_ids?}
Output: {qual_path, operation}

Companion to kb-bridge-write-fingerprint:
  - write-fingerprint = own-account statistical fingerprint
  - write-qual (this) = competitor-account qualitative 8-dim analysis
"""
import sys
from datetime import date as date_cls
from common.lib import (  # noqa: E402
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault,
    read_md, write_md_atomic, append_log,
)


def main():
    inp = read_stdin_json()
    slug = inp.get("slug")
    competitor_account = inp.get("competitor_account")
    source_url = inp.get("source_url")
    publish_date = inp.get("publish_date")
    qual_body = inp.get("qual_body")

    # Required field validation
    missing = [k for k, v in {
        "slug": slug,
        "competitor_account": competitor_account,
        "source_url": source_url,
        "publish_date": publish_date,
        "qual_body": qual_body,
    }.items() if not v]
    if missing:
        err(f"missing required fields: {','.join(missing)}", code="BAD_INPUT")

    require_vault()

    # Soft whitelist warning (not enforced): check if competitor_account dir exists under 03_raw/wechat
    raw_dir = AI_WIKI_ROOT / "03_raw" / "wechat" / competitor_account
    soft_warning = None
    if not raw_dir.exists():
        soft_warning = (
            f"competitor_account '{competitor_account}' has no matching dir under "
            f"03_raw/wechat/ — proceeding anyway, but consider verifying spelling"
        )

    qual_path = AI_WIKI_ROOT / "exemplars" / competitor_account / f"{slug}-qual.md"
    qual_path.parent.mkdir(parents=True, exist_ok=True)

    today = str(date_cls.today())
    dry_run = bool(inp.get("dry_run", False))

    if qual_path.exists():
        try:
            fm, _old_body = read_md(qual_path)
        except Exception:
            fm = {}
        operation = "updated"
    else:
        fm = {
            "title": f"{slug} — qualitative analysis",
            "type": "qual",
            "status": "v1.0-sample",
            "created": today,
            "tags": ["qual", "competitor-analysis", "3C"],
        }
        operation = "created"

    # Merge updates
    fm["updated"] = today
    fm["slug"] = slug
    fm["source_account"] = competitor_account
    fm["source_url"] = source_url
    fm["publish_date"] = publish_date

    optional_fields = (
        "medium", "viral_score", "qual_version", "analyst",
        "account_fit", "technique_ids",
    )
    for k in optional_fields:
        v = inp.get(k)
        if v is not None:
            fm[k] = v

    # Default medium = wechat if not provided
    fm.setdefault("medium", "wechat")
    fm.setdefault("qual_version", "1.0")

    body = qual_body.strip() + "\n"

    if dry_run:
        result = {
            "qual_path": str(qual_path.relative_to(AI_WIKI_ROOT)),
            "operation": f"dry_run_would_{operation}",
            "body_chars": len(body),
            "frontmatter_keys": sorted(fm.keys()),
        }
        if soft_warning:
            result["warning"] = soft_warning
        emit(result)
        return

    # Safety check: if updating, refuse to overwrite a substantive existing body with a tiny one
    # (catches smoke-test accidents like the 2026-05-27 incident)
    if operation == "updated":
        try:
            _existing_fm, existing_body = read_md(qual_path)
            if len(existing_body.strip()) > 2000 and len(body.strip()) < 500:
                err(
                    f"refusing to overwrite {len(existing_body)} chars of existing qual body "
                    f"with only {len(body)} chars; pass dry_run=true to test, or "
                    f"set force_overwrite=true if intentional",
                    code="BODY_SHRINK_GUARD"
                )
        except Exception:
            pass

    # Allow explicit force
    if inp.get("force_overwrite"):
        pass  # bypass the check above (only matters on next call after BODY_SHRINK_GUARD trips)

    write_md_atomic(qual_path, fm, body)

    append_log("kb-bridge-write-qual", slug, {
        "qual_path": str(qual_path.relative_to(AI_WIKI_ROOT)),
        "competitor_account": competitor_account,
        "operation": operation,
    })

    result = {
        "qual_path": str(qual_path.relative_to(AI_WIKI_ROOT)),
        "operation": operation,
    }
    if soft_warning:
        result["warning"] = soft_warning
    emit(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
