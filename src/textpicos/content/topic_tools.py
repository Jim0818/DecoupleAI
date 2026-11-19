"""Task-local topic tools: selected sources, planning, candidates and feedback.

One JSON request on stdin; no daemon, automatic scheduling or editorial score.
The bridge remains the external planning entry. Candidate mutations use its
service's revision checks; this module never treats selection as publication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from textpicos.paths import ProjectPaths
from textpicos.runtime import RuntimeError as TaskRuntimeError
from textpicos.runtime.storage import atomic_json, file_lock, file_version

SOURCE_CONFIG = "config/system/topic-sources.json"
PLANNING_CONFIG = "config/system/topic-planning.json"
SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
SUCCESS = {"ok", "empty", "not_modified", "partial"}
STATE_SUCCESS = {"ok", "empty", "not_modified"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def _item_digest(item):
    return _digest({key: value for key, value in item.items() if key != "item_sha256"})


def _bind_item_versions(result):
    """Keep a selectable version for each source behind a deduplicated item."""
    selections = {}
    for source in result["sources"]:
        versioned = []
        for raw in source.get("items", []):
            item = dict(raw)
            item["item_sha256"] = _item_digest(item)
            versioned.append(item)
            identity = item.get("canonical_url") or item["id"]
            selections.setdefault(identity, []).append({
                "source_id": source["source_id"], "item_id": item["id"],
                "expected_item_sha256": item["item_sha256"]})
        source["items"] = versioned
    result["items"] = [{**item, "evidence_selections": selections.get(
        item.get("canonical_url") or item["id"], [])} for item in result.get("items", [])]


def _selected_path(paths, relative, *, prefix):
    """Reject excluded names and links before probing a selected file."""
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or not raw.parts:
        raise ValueError("Select a relative project file")
    if any(p.casefold() in {"articles", "archive", ".git"} for p in raw.parts):
        raise ValueError("Excluded content path")
    boundary = Path(prefix)
    if not raw.is_relative_to(boundary) or raw == boundary:
        raise ValueError(f"File must be below {prefix}")
    current = paths.root
    for part in raw.parts:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ValueError("Selected file contains a symlink")
    return current


def _json_file(path, *, missing=None):
    try:
        with path.open("rb") as stream:
            raw = stream.read(8_000_001)
    except FileNotFoundError:
        if missing is not None:
            return missing
        raise
    if len(raw) > 8_000_000:
        raise ValueError("Selected JSON exceeds the read budget")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Selected JSON must be an object")
    return result


def _config(paths, relative):
    value = _json_file(_selected_path(paths, relative, prefix="config"))
    if value.get("schema_version") != 1:
        raise ValueError("Unsupported topic configuration")
    return value


def _source_specs(paths, request):
    configuration = _config(paths, SOURCE_CONFIG)
    entries = configuration.get("sources")
    if not isinstance(entries, list):
        raise ValueError("sources configuration must be a list")
    by_id = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError("Each source requires an id")
        if not SOURCE_ID.fullmatch(entry["id"]) or entry["id"] in by_id:
            raise ValueError("Invalid or duplicate source id")
        if not isinstance(entry.get("enabled", True), bool):
            raise ValueError("source.enabled must be a boolean")
        by_id[entry["id"]] = entry
    selected = request.get("source_ids")
    if selected is None:
        selected = [name for name, item in by_id.items() if item.get("enabled", True)]
    if (not isinstance(selected, list) or not selected or len(selected) > 20
            or any(not isinstance(name, str) or name not in by_id for name in selected)):
        raise ValueError("source_ids must select one to twenty configured sources")
    return [dict(by_id[name]) for name in dict.fromkeys(selected)]


def _cache_path(paths, source_id):
    if not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id):
        raise ValueError("Invalid source id")
    return _selected_path(paths, f"workspace/cache/topic-sources/{source_id}.json",
                          prefix="workspace/cache/topic-sources")


def fetch(paths, request):
    from textpicos.content.topic_sources import collect_sources
    specs = _source_specs(paths, request)
    states, before, caches = {}, {}, {}
    for spec in specs:
        source_id = spec["id"]
        cache = _cache_path(paths, source_id)
        before[source_id] = file_version(cache)
        cached = _json_file(cache, missing={})
        caches[source_id] = cache
        if cached.get("spec_fingerprint") == _digest(spec):
            states[source_id] = cached.get("state", {})
    cursors = request.get("cursors")
    if cursors is not None and not isinstance(cursors, dict):
        raise ValueError("cursors must be an object keyed by source id")
    result = collect_sources(specs, states=states, cursors=cursors)
    returned_states = result.pop("states", {})
    _bind_item_versions(result)
    statuses = {item["source_id"]: item for item in result["sources"]}
    for spec in specs:
        source_id = spec["id"]
        item = statuses[source_id]
        state = returned_states.get(source_id, item.pop("state", None))
        item.pop("state", None)
        if item["status"] in STATE_SUCCESS:
            next_state = state or {}
        elif item["status"] == "partial" and item.get("items"):
            # Available discovery records remain selectable, while a partial
            # request never advances the last successful incremental state.
            next_state = states.get(source_id, {})
        else:
            continue
        cache = caches[source_id]
        lock = _selected_path(paths, f"workspace/cache/topic-sources/{source_id}.lock",
                              prefix="workspace/cache/topic-sources")
        with file_lock(lock):
            if file_version(cache) != before[source_id]:
                item.setdefault("warnings", []).append("cache_changed_concurrently; result not stored")
                item["cache_status"] = "changed_concurrently"
                continue
            item["cache_status"] = "stored"
            atomic_json(cache, {"schema_version": 1, "spec_fingerprint": _digest(spec),
                                "stored_at": _now(), "state": next_state, "result": item})
    return result


def cached_sources(paths, request):
    sources = []
    for spec in _source_specs(paths, request):
        cached = _json_file(_cache_path(paths, spec["id"]), missing={})
        if not cached:
            sources.append({"source_id": spec["id"], "status": "not_available", "items": []})
        else:
            sources.append({"source_id": spec["id"], "status": "cached",
                            "config_matches": cached.get("spec_fingerprint") == _digest(spec),
                            "stored_at": cached["stored_at"], "result": cached["result"]})
    return {"status": "cached", "sources": sources,
            "note": "Cached discovery material; current source health and source claims are not verified."}


def planning(paths, request, operation):
    configuration = _config(paths, PLANNING_CONFIG)
    account = request.get("account_id")
    accounts = configuration.get("accounts", {})
    if account not in accounts:
        raise ValueError("Select a configured account_id")
    key = "topic_sources" if operation == "planning" else "strategy_sources"
    selected = request.get("sources", accounts[account].get(key, []))
    payload = {key: value for key, value in request.items()
               if key in {"account_id", "run_id", "query", "limit", "max_chars", "optional"}}
    payload.update(op="list-topics" if operation == "planning" else "read-topic-strategy",
                   sources=selected)
    env = dict(os.environ)
    env["TEXTPICOS_ROOT"] = str(paths.root)
    configured_root = (env.get("TEXTPICOS_AI_WIKI_ROOT") or env.get("AI_WIKI_ROOT")
                       or configuration.get("vault_root"))
    if configured_root:
        if not isinstance(configured_root, str):
            raise ValueError("vault_root must be an explicitly configured path")
        env["TEXTPICOS_AI_WIKI_ROOT"] = configured_root
    # Keep the caller's maintenance scope; external access must still be denied
    # by the current bridge during system maintenance.
    result = subprocess.run([sys.executable, str(paths.root / "skills/kb-bridge/dispatch.py")],
                            input=json.dumps(payload), text=True, capture_output=True, env=env)
    stream = result.stdout.strip() or result.stderr.strip()
    try:
        output = json.loads(stream)
    except json.JSONDecodeError:
        raise ValueError("Planning bridge returned no structured result") from None
    if not isinstance(output, dict):
        raise ValueError("Planning bridge returned an invalid result")
    return output, result.returncode


def _catalogs(paths, request):
    refs = request.get("catalog_refs")
    if refs is not None:
        return refs
    accounts = _config(paths, PLANNING_CONFIG).get("accounts", {})
    selected = request.get("account_id")
    if selected is not None and selected not in accounts:
        raise ValueError("Unknown account_id")
    entries = [accounts[selected]] if selected else list(accounts.values())
    refs, seen = [], set()
    for account in entries:
        for ref in account.get("catalog_refs", []):
            fingerprint = _digest(ref)
            if fingerprint not in seen:
                seen.add(fingerprint)
                refs.append(ref)
    if not refs:
        raise ValueError("Select catalog_refs explicitly")
    return refs


def save_evidence(paths, request):
    """Persist only selected cached items in an existing active native run."""
    from textpicos.runtime import Runtime
    selected = request.get("items")
    if not isinstance(selected, list) or not 1 <= len(selected) <= 50:
        raise ValueError("Select one to fifty versioned source_id/item_id records")
    run_id = request.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("An existing active run_id is required")
    records, seen = [], set()
    for selection in selected:
        if not isinstance(selection, dict) or not isinstance(selection.get("item_id"), str):
            raise ValueError("Each item requires source_id and item_id")
        expected = selection.get("expected_item_sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Each item requires the selected expected_item_sha256")
        source_id = selection.get("source_id")
        cache = _json_file(_cache_path(paths, source_id))
        item = next((item for item in cache["result"].get("items", [])
                     if item["id"] == selection["item_id"]), None)
        if item is None:
            raise ValueError("Selected item is absent from the source cache")
        actual_item = _item_digest(item)
        if expected != actual_item or item.get("item_sha256") != actual_item:
            raise ValueError("Selected source item version changed; read the current item before selecting")
        identity = (source_id, item["id"])
        if identity not in seen:
            records.append({"source_id": source_id, "item": item,
                            "source_fetched_at": cache["result"].get("fetched_at"),
                            "item_sha256": actual_item})
            seen.add(identity)
    runtime = Runtime(paths)
    with runtime._locked(run_id):
        state = runtime._read(run_id)
        if state["lifecycle"] != "active":
            raise ValueError("Evidence cannot modify a completed run")
        target = runtime._run_dir(run_id) / "evidence/topic-source-items.json"
        runtime._check_components(target)
        before = file_version(target)
        actual = before["sha256"] if before else None
        if request.get("expected_sha256") != actual:
            raise ValueError("Evidence version changed; provide current expected_sha256")
        payload = {"schema_version": 1, "run_id": run_id, "saved_at": _now(),
                   "verification": "source_not_checked", "items": records}
        atomic_json(target, payload)
    return {"status": "ok", "path": str(target.relative_to(paths.root)),
            "version": file_version(target), "count": len(records),
            "verification": "source_not_checked"}


def execute(request, *, paths=None):
    if not isinstance(request, dict):
        raise ValueError("stdin request must be a JSON object")
    paths = paths or ProjectPaths.discover()
    operation = request.get("op")
    if operation == "sources":
        return {"status": "ok", "sources": _config(paths, SOURCE_CONFIG)["sources"]}, 0
    if operation in {"planning", "strategy"}:
        return planning(paths, request, operation)
    if operation == "fetch":
        result = fetch(paths, request)
        return result, 0 if result["status"] in SUCCESS else 2
    if operation == "cache":
        return cached_sources(paths, request), 0
    if operation == "save-evidence":
        return save_evidence(paths, request), 0
    from textpicos.content import topic_candidates as candidates
    common = {"index_path": request.get("index_path")}
    if operation == "candidates":
        result = candidates.list_candidates(paths, account_id=request.get("account_id"),
                                            decision=request.get("decision"), **common)
        if request.get("format") == "markdown":
            result = {"status": "ok", "revision": result["revision"],
                      "markdown": candidates.render_candidates(result)}
    elif operation == "candidate-upsert":
        result = candidates.upsert_candidate(paths, request.get("record"),
                    expected_revision=request.get("expected_revision"),
                    request_id=request.get("request_id"), **common)
    elif operation == "feedback":
        result = candidates.record_feedback(paths, request.get("topic_id"), request.get("event"),
                    expected_revision=request.get("expected_revision"),
                    request_id=request.get("request_id"), **common)
    elif operation == "registry":
        result = candidates.registry_view(paths, _catalogs(paths, request), **common)
    elif operation == "resolve-conflict":
        result = candidates.resolve_registry_conflict(paths, _catalogs(paths, request),
                    request.get("resolution"), expected_revision=request.get("expected_revision"),
                    request_id=request.get("request_id"), **common)
    elif operation == "source-summary":
        result = candidates.source_summary(paths, **common)
    else:
        raise ValueError("Unknown topic operation")
    return result, 0


def main():
    try:
        if len(sys.argv) > 1:
            if sys.argv[1:] == ["--help"]:
                print("Pass one stdin JSON request; see skills/research/references/topic-tools.md")
                return 0
            raise ValueError("Only --help or a stdin JSON request is supported")
        raw = sys.stdin.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Request exceeds the input budget")
        result, code = execute(json.loads(raw))
    except (OSError, ValueError, TypeError, KeyError, TaskRuntimeError) as exc:
        result, code = {"status": "error", "error": getattr(exc, "code", "TOPIC_REQUEST_FAILED"),
                        "message": str(exc)}, 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
