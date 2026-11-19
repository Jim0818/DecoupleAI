#!/usr/bin/env python3
"""Reject the retired scoring entry; current discovery uses fetch.py.

This endpoint never reads supplied paths, calculates rankings, or writes an
output. Historical records are data only, not an executable fallback.
"""
from __future__ import annotations

import json
import sys


def main(argv=None) -> int:
    print(json.dumps({
        "status": "not_available",
        "error": "AIHOT_SCORING_RETIRED",
        "message": "旧热点评分与历史回放已停用。请使用 fetch.py 获取线索，再按当前账号范围研究；不输出历史排名。",
        "replacement": "fetch.py",
    }, ensure_ascii=False), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
