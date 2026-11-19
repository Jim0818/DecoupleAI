#!/usr/bin/env python3
"""List individual topics from explicitly selected files; never scan the vault.

Input: {account_id?, sources: [{scope: project|vault, path: relative-file}],
        query?, limit?, optional?, run_id?}. Sources can include format,
heading_level or expected_sha256. Output includes items and source states.
Full parsing and path rules live in textpicos.content.topic_planning.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

_SOURCE = Path(os.environ.get("TEXTPICOS_ROOT") or Path(__file__).resolve().parents[3]) / "src"
if str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))
from textpicos.content.topic_planning import list_topics, uses_vault


def main():
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            raise ValueError("stdin JSON required")
        request = json.loads(raw)
        outcome, code = list_topics(request)
        if uses_vault(request):
            from common.lib import prepare_request, _write_receipt
            prepare_request(request)
            _write_receipt(outcome["status"], outcome["count"], outcome.get("error"))
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"error": getattr(exc, "code", "BAD_INPUT"), "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
