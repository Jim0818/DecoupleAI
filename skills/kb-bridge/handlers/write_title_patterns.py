#!/usr/bin/env python3
"""kb-bridge-write-title-patterns — title-ingest pattern writer.

Input: {account, source, pattern_stats, title_cluster_distribution, titles[],
        dry_run?, force_overwrite?}
Output: {output_path, operation}

Writes to: AI-WIKI/05_synthesis/title-patterns-library/{account}.md
"""
import sys
from datetime import date as date_cls
from pathlib import Path

from common.lib import (
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault,
    write_md_atomic, append_log,
)

OUTPUT_DIR = AI_WIKI_ROOT / "05_synthesis/title-patterns-library"


def main():
    inp = read_stdin_json()
    account = inp.get("account")
    pattern_stats = inp.get("pattern_stats")
    title_cluster_distribution = inp.get("title_cluster_distribution")
    titles = inp.get("titles", [])

    missing = [k for k, v in {
        "account": account,
        "pattern_stats": pattern_stats,
        "title_cluster_distribution": title_cluster_distribution,
    }.items() if not v]
    if missing:
        err(f"missing required fields: {','.join(missing)}", code="BAD_INPUT")

    require_vault()

    output_path = OUTPUT_DIR / f"{account}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    today = str(date_cls.today())
    dry_run = bool(inp.get("dry_run", False))
    source = inp.get("source", "title-ingest")
    covered_month = inp.get("covered_month")

    if output_path.exists():
        operation = "updated"
    else:
        operation = "created"

    # Build frontmatter
    fm = {
        "account": account,
        "source": source,
        "updated": today,
        "total_titles": len(titles),
        "pattern_stats": pattern_stats,
        "title_cluster_distribution": title_cluster_distribution,
    }
    if covered_month:
        fm["covered_months"] = [covered_month]

    # Build body: raw titles + TT breakdown
    body_lines = [
        f"# {account} · Title Patterns",
        "",
        "## Raw Titles",
        "",
    ]
    for i, t in enumerate(titles, 1):
        body_lines.append(f"{i}. {t}")
    body_lines.append("")
    body_lines.append("## TT Cluster Distribution")
    body_lines.append("")

    for tt_id in sorted(title_cluster_distribution.keys()):
        count = title_cluster_distribution[tt_id]
        body_lines.append(f"- **{tt_id}**: {count} titles")
    body_lines.append("")

    body = "\n".join(body_lines) + "\n"

    if dry_run:
        emit({
            "output_path": str(output_path.relative_to(AI_WIKI_ROOT)),
            "operation": f"dry_run_would_{operation}",
            "body_chars": len(body),
        })
        return

    write_md_atomic(output_path, fm, body)

    append_log("kb-bridge-write-title-patterns", account, {
        "output_path": str(output_path.relative_to(AI_WIKI_ROOT)),
        "operation": operation,
    })

    emit({
        "output_path": str(output_path.relative_to(AI_WIKI_ROOT)),
        "operation": operation,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
