#!/usr/bin/env python3
"""kb-bridge-write-topic-qual — style-analyst --topic-strategy competitor topic strategy writer.

Input: {slug, competitor_account, source_url, publish_date, medium?, viral_score?,
        topic_qual_version?, analyst?, qual_body, topic_strategy_fit, topic_metrics,
        topic_technique_ids?}
Output: {qual_path, operation}

Companion to kb-bridge-write-qual:
  - write-qual = competitor-account qualitative 8-dim technique analysis (how to write)
  - write-topic-qual (this) = competitor-account 6-dim topic strategy analysis (what/when/who first)
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
    topic_strategy_fit = inp.get("topic_strategy_fit")
    topic_metrics = inp.get("topic_metrics")

    # Required field validation
    missing = [k for k, v in {
        "slug": slug,
        "competitor_account": competitor_account,
        "source_url": source_url,
        "publish_date": publish_date,
        "qual_body": qual_body,
        "topic_strategy_fit": topic_strategy_fit,
        "topic_metrics": topic_metrics,
    }.items() if not v]
    if missing:
        err(f"missing required fields: {','.join(missing)}", code="BAD_INPUT")

    # Validate topic_strategy_fit has all 3 accounts
    required_accounts = ["decoupleai", "studio", "intellifuture"]
    fit_missing = [a for a in required_accounts if a not in topic_strategy_fit]
    if fit_missing:
        err(f"topic_strategy_fit missing accounts: {','.join(fit_missing)}", code="BAD_INPUT")

    # Validate topic_metrics required sub-fields
    required_metrics = [
        "publish_timing_lag_days", "parallel_account_count",
        "differentiation_angle", "topic_domain_tags",
    ]
    metrics_missing = [k for k in required_metrics if k not in topic_metrics]
    if metrics_missing:
        err(f"topic_metrics missing fields: {','.join(metrics_missing)}", code="BAD_INPUT")

    require_vault()

    # Soft whitelist warning
    raw_dir = AI_WIKI_ROOT / "03_raw" / "wechat" / competitor_account
    soft_warning = None
    if not raw_dir.exists():
        soft_warning = (
            f"competitor_account '{competitor_account}' has no matching dir under "
            f"03_raw/wechat/ — proceeding anyway, but consider verifying spelling"
        )

    qual_path = AI_WIKI_ROOT / "exemplars" / competitor_account / f"{slug}-topic-qual.md"
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
            "title": f"{slug} — topic strategy analysis",
            "type": "topic-qual",
            "status": "v1.0-sample",
            "created": today,
            "tags": ["topic-qual", "topic-strategy", "3C"],
        }
        operation = "created"

    # Merge updates
    fm["updated"] = today
    fm["slug"] = slug
    fm["source_account"] = competitor_account
    fm["source_url"] = source_url
    fm["publish_date"] = publish_date

    # Required blocks
    fm["topic_strategy_fit"] = topic_strategy_fit
    fm["topic_metrics"] = topic_metrics

    optional_fields = (
        "medium", "viral_score", "topic_qual_version", "analyst",
        "topic_technique_ids",
    )
    for k in optional_fields:
        v = inp.get(k)
        if v is not None:
            fm[k] = v

    # Default medium = wechat
    fm.setdefault("medium", "wechat")
    fm.setdefault("topic_qual_version", "1.0")

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

    # BODY_SHRINK_GUARD
    if operation == "updated":
        try:
            _existing_fm, existing_body = read_md(qual_path)
            if len(existing_body.strip()) > 2000 and len(body.strip()) < 500:
                err(
                    f"refusing to overwrite {len(existing_body)} chars of existing topic-qual body "
                    f"with only {len(body)} chars; pass dry_run=true to test, or "
                    f"set force_overwrite=true if intentional",
                    code="BODY_SHRINK_GUARD"
                )
        except Exception:
            pass

    if inp.get("force_overwrite"):
        pass

    write_md_atomic(qual_path, fm, body)

    append_log("kb-bridge-write-topic-qual", slug, {
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
