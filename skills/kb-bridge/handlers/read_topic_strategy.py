#!/usr/bin/env python3
"""Report the availability of current topic strategy without guessing policy.

Input: {account_id?, optional?: bool, strategy_mode?: "current",
        query?: str, top_n?: positive int, topic_type?: str}
The external manual is not fetched or claimed current. A not_available result
retains selected account L1/L2 references for the caller. No vault or receipt
files are read or written by this local operation.
"""
from __future__ import annotations

import json
import sys

def read_strategy(inp):
    """Return (outcome, exit code) without probing any external or project file."""
    if not isinstance(inp, dict):
        raise ValueError("request must be an object")
    mode = inp.get("strategy_mode", "current")
    if not isinstance(mode, str) or mode != "current":
        raise ValueError("strategy_mode must be current; historical snapshot execution has been removed")
    optional = inp.get("optional", False)
    if not isinstance(optional, bool):
        raise ValueError("optional must be a boolean")
    account = inp.get("account_id")
    if account is not None and (not isinstance(account, str) or account not in {
        "studio", "intellifuture", "decoupleai"
    }):
        raise ValueError("account_id must be studio, intellifuture or decoupleai")
    query = inp.get("query", "")
    top_n = inp.get("top_n", 5)
    topic_type = inp.get("topic_type")
    if not isinstance(query, str) or (topic_type is not None and not isinstance(topic_type, str)):
        raise ValueError("query and topic_type must be text")
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    refs = [f"config/accounts/{account}/{name}.md" for name in
            ("L1_identity", "L2_values")] if account else []
    return {
        "status": "not_available", "error": "TOPIC_STRATEGY_UNVERIFIED",
        "message": "外部选题策略尚未读取核验；旧 TOP 片段不作为当前账号策略。",
        "account_id": account,
        "source_status": "not_read",
        "baseline_refs": [{"path": path, "verification": "reference_only"} for path in refs],
        "next_action": "Read the selected account L1/L2 and task-selected scope references before choosing topics.",
        "legacy_fallback": False,
    }, 0 if optional else 2


def main():
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            raise ValueError("stdin JSON required")
        outcome, code = read_strategy(json.loads(raw))
    except (TypeError, ValueError) as exc:
        print(json.dumps({"error": "BAD_INPUT", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
