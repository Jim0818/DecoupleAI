#!/usr/bin/env python3
"""kb-bridge-write-retro — write pipeline retrospective.

Input: {date, run_id, pipeline?, friction_points[], fixes_applied[], queued_for_next_batch[]}
Output: {retro_path}
"""
import sys
from datetime import date as date_cls
from common.lib import (  # noqa: E402
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault,
    write_md_atomic, append_log,
)

SEV_ORDER = {"high": 0, "med": 1, "low": 2}


def main():
    inp = read_stdin_json()
    d = inp.get("date") or str(date_cls.today())
    run_id = inp.get("run_id")
    if not run_id:
        err("run_id required", code="BAD_INPUT")
    require_vault()

    pipeline = inp.get("pipeline") or "unspecified"
    friction = inp.get("friction_points") or []
    fixes = inp.get("fixes_applied") or []
    queued = inp.get("queued_for_next_batch") or []

    retro_dir = AI_WIKI_ROOT / "05_synthesis" / "retros"
    if not retro_dir.parent.is_dir():
        err(f"05_synthesis dir not found: {retro_dir.parent}", code="PATH_NOT_FOUND")
    retro_dir.mkdir(parents=True, exist_ok=True)
    retro_path = retro_dir / f"{d}-{run_id}.md"

    fm = {
        "title": f"Retro {d} {run_id}",
        "type": "synthesis",
        "status": "stable",
        "created": d,
        "updated": str(date_cls.today()),
        "tags": ["retro", "pipeline", pipeline],
        "account": "all",
        "run_id": run_id,
        "pipeline": pipeline,
    }

    friction_sorted = sorted(
        friction, key=lambda x: SEV_ORDER.get(str(x.get("severity","low")).lower(), 9)
    )
    body_lines = [
        f"## Pipeline\n\n`{pipeline}` — run_id `{run_id}`",
        "\n## Friction Points\n",
    ]
    if friction_sorted:
        for f in friction_sorted:
            sev = f.get("severity", "low")
            where = f.get("where", "?")
            what = f.get("what", "?")
            body_lines.append(f"- **[{sev.upper()}]** `{where}` — {what}")
    else:
        body_lines.append("_(none)_")

    body_lines += ["\n## Fixes Applied\n"]
    body_lines += [f"- {x}" for x in fixes] if fixes else ["_(none)_"]
    body_lines += ["\n## Queued for Next Batch\n"]
    body_lines += [f"- [ ] {x}" for x in queued] if queued else ["_(none)_"]
    body = "\n".join(body_lines) + "\n"

    write_md_atomic(retro_path, fm, body)
    append_log("kb-bridge-write-retro", run_id, {
        "retro_path": str(retro_path.relative_to(AI_WIKI_ROOT)),
        "friction": len(friction),
        "fixes": len(fixes),
        "queued": len(queued),
    })
    emit({"retro_path": str(retro_path.relative_to(AI_WIKI_ROOT))})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
