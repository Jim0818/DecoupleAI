#!/usr/bin/env python3
"""Fetch one bounded page of optional news leads, without editorial scoring.

The source URL, timeout and byte budget are configured in config.json. This
adapter never fetches article URLs, retries for a candidate quota, writes a
vault, or asserts that a source's claims have been verified. A valid empty page
is success; transport/shape failures remain distinguishable and nonzero.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


def _positive(value, name, *, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} exceeds the supported limit {maximum}")
    return value


def _http_url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return False
    try:
        parsed = urlparse(value)
        parsed.port
        return parsed.scheme in {"https", "http"} and bool(parsed.hostname)
    except ValueError:
        return False


def normalize_items(payload):
    """Validate a page; return only source fields, never inherited LLM scores."""
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("Response must contain an items array")
    if "hasNext" in payload and not isinstance(payload["hasNext"], bool):
        raise ValueError("hasNext must be a boolean")
    result = []
    seen = set()
    for item in payload["items"]:
        if not isinstance(item, dict):
            raise ValueError("Each item must be an object")
        for key in ("id", "title", "publishedAt"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"Item requires a nonempty {key}")
        if not _http_url(item.get("url")):
            raise ValueError("Item requires an HTTP(S) source URL")
        stamp = datetime.fromisoformat(item["publishedAt"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("publishedAt requires a timezone")
        for key in ("summary", "category", "source"):
            if item.get(key) is not None and not isinstance(item[key], str):
                raise ValueError(f"Item {key} must be text or null")
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        result.append({
            "id": item["id"], "title": item["title"], "url": item["url"],
            "published_at": item["publishedAt"],
            "summary": item.get("summary") or "", "source": item.get("source"),
            "category": item.get("category"), "verification": "source_not_checked",
        })
    return result


def fetch_page(config, *, mode=None, window_hours=None, take=None, now=None, opener=urlopen):
    """Return (JSON outcome, exit code); opener permits offline transport tests."""
    now = now or datetime.now(timezone.utc)
    outcome = {"source": "aihot", "fetched_at": now.isoformat(), "items": []}
    try:
        cfg = config["fetch"]
        mode = mode if mode is not None else cfg["default_mode"]
        if mode not in {"selected", "all"}:
            raise ValueError("mode must be selected or all")
        window = _positive(window_hours if window_hours is not None else cfg["default_window_hours"], "window_hours")
        limit = _positive(take if take is not None else cfg["default_take"], "take", maximum=50)
        timeout = _positive(cfg["timeout_seconds"], "timeout_seconds", maximum=60)
        byte_limit = _positive(cfg["max_response_bytes"], "max_response_bytes", maximum=10000000)
        base_url = cfg["base_url"]
        if not _http_url(base_url) or urlparse(base_url).scheme != "https":
            raise ValueError("base_url must be an HTTPS URL")
        if not isinstance(cfg["user_agent"], str) or not cfg["user_agent"].strip():
            raise ValueError("user_agent must be text")
        since = (now - timedelta(hours=window)).isoformat()
        url = base_url + "?" + urlencode({"mode": mode, "since": since, "take": limit})
        request = Request(url, headers={"User-Agent": cfg["user_agent"], "Accept": "application/json"})
        outcome["request"] = {"mode": mode, "window_hours": window, "take": limit}
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return {**outcome, "status": "invalid_config", "error": str(exc)}, 2
    try:
        with opener(request, timeout=timeout) as response:
            data = response.read(byte_limit + 1)
        if len(data) > byte_limit:
            raise ValueError("Response exceeded the configured byte budget")
        payload = json.loads(data)
        items = normalize_items(payload)
        return {**outcome, "status": "ok" if items else "empty", "items": items,
                "count": len(items), "has_more": payload.get("hasNext", False)}, 0
    except HTTPError as exc:
        return {**outcome, "status": "unavailable", "error": f"http_{exc.code}"}, 2
    except (URLError, OSError, TimeoutError):
        return {**outcome, "status": "unavailable", "error": "transport_error"}, 2
    except (ValueError, TypeError, UnicodeError):
        return {**outcome, "status": "invalid_response", "error": "invalid_source_payload"}, 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["selected", "all"])
    parser.add_argument("--window-hours", type=int)
    parser.add_argument("--take", type=int)
    args = parser.parse_args(argv)
    try:
        config = json.loads(Path(__file__).with_name("config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(json.dumps({"status": "invalid_config", "error": "config_unreadable", "items": []}))
        return 2
    outcome, code = fetch_page(config, mode=args.mode, window_hours=args.window_hours, take=args.take)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
