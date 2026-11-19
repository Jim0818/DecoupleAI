#!/usr/bin/env python3
"""Route one stdin-JSON bridge request to an operation handler."""
from __future__ import annotations

import importlib
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from registry import LOCAL_OPS, OPS  # noqa: E402


def fail(message: str, code: str = "BAD_INPUT") -> int:
    print(json.dumps({"error": code, "message": message}, ensure_ascii=False), file=sys.stderr)
    return 2


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        return fail("stdin JSON required")
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        return fail(f"invalid JSON: {exc.msg}")
    if not isinstance(request, dict):
        return fail("request must be a JSON object")
    op = request.pop("op", None)
    if not op:
        return fail("op required")
    module_name = OPS.get(str(op))
    if not module_name:
        return fail(f"unknown op: {op}", code="UNKNOWN_OP")

    os.environ["KB_BRIDGE_OP"] = str(op)
    os.environ["KB_BRIDGE_NAME"] = "kb-bridge"
    if op not in LOCAL_OPS:
        if os.environ.get("TEXTPICOS_MAINTENANCE_SCOPE") == "system":
            return fail("External vault operations are outside system maintenance scope", code="OUT_OF_SCOPE")
        if not (os.environ.get("AI_WIKI_ROOT") or os.environ.get("TEXTPICOS_AI_WIKI_ROOT")):
            return fail("Set AI_WIKI_ROOT or TEXTPICOS_AI_WIKI_ROOT explicitly", code="VAULT_NOT_CONFIGURED")
        from common.lib import prepare_request, require_vault
        try:
            prepare_request(request)
        except Exception as exc:
            return fail(str(exc), code="INVALID_RUN")
        require_vault()
    sys.stdin = io.StringIO(json.dumps(request, ensure_ascii=False))
    module = importlib.import_module(module_name)
    module.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
