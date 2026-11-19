"""Explicit candidate decisions and selected catalog views; never read articles.

The caller chooses candidates and provides feedback. This module supplies stable
identity, durable optimistic updates and traceable views, not editorial scores
or authority to write/publish content. Only a selected catalog index is writable.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from textpicos.runtime.storage import atomic_json, file_lock

SCHEMA_VERSION = 1
MAX_BYTES = 10 * 1024 * 1024
DECISIONS = {"proposed", "selected", "needs_research", "observe", "rejected"}
FEEDBACK_KINDS = {
    "selected", "needs_research", "observe", "rejected", "angle_changed",
    "materials_missing", "duplicate", "off_scope", "not_worth_it", "used",
    "production_result", "source_review",
}
TEXT_FIELDS = {"title", "reader_task", "practical_output", "rationale", "angle", "column"}
LIST_FIELDS = {"evidence_refs", "scope_refs", "material_gaps", "duplicate_refs", "run_refs", "article_refs"}


class CandidateError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)

    def as_dict(self):
        return {"status": "error", "error": self.code, "message": str(self)}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise CandidateError("invalid_request", f"{name} must be a nonempty string")
    return value.strip()


def _strings(value, name, *, required=False):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise CandidateError("invalid_request", f"{name} must be a list of nonempty strings")
    if required and not value:
        raise CandidateError("missing_evidence", f"{name} cannot be empty")
    return list(dict.fromkeys(v.strip() for v in value))


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise CandidateError("invalid_request", f"{name} must be finite and nonnegative")
    return value


def _json_digest(value):
    try:
        body = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))
    except (ValueError, TypeError) as exc:
        raise CandidateError("invalid_request", "Request must contain finite JSON values") from exc
    return hashlib.sha256(body.encode()).hexdigest()


def _local_path(paths, value):
    root = Path(paths.root)
    if not isinstance(value, (str, Path)) or not str(value):
        raise CandidateError("path_not_allowed", "Select an explicit local catalog path")
    raw = Path(value)
    if ".." in raw.parts:
        raise CandidateError("path_not_allowed", "Parent traversal is not a catalog reference")
    path = Path(os.path.abspath(raw if raw.is_absolute() else root / raw))
    if not path.is_relative_to(root):
        raise CandidateError("path_not_allowed", "Catalog operations stay inside the selected project")
    relative = path.relative_to(root)
    if {part.casefold() for part in relative.parts}.intersection({"articles", "archive"}):
        raise CandidateError("path_not_allowed", "Articles and archives are not catalog inputs")
    current = root
    for part in relative.parts:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            break
        if stat.S_ISLNK(mode):
            raise CandidateError("path_not_allowed", "Catalog paths cannot contain symbolic links")
    return path


def _catalog_path(paths, value, suffix):
    boundary = _local_path(paths, Path(paths.resources) / "catalogs")
    path = _local_path(paths, value)
    if not path.is_relative_to(boundary) or path == boundary or path.suffix.lower() != suffix:
        raise CandidateError("path_not_allowed", f"Select a {suffix} file inside resources/catalogs")
    return path


def _index_path(paths, index_path):
    selected = Path(paths.resources) / "catalogs/topic-candidates.json" if index_path is None else index_path
    return _catalog_path(paths, selected, ".json")


def _read_bytes(path):
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None, None
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise CandidateError("invalid_file", "Selected catalog must be a bounded regular file")
        body = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(body) > MAX_BYTES:
        raise CandidateError("invalid_file", "Selected catalog exceeds the byte budget")
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise CandidateError("version_conflict", "Selected catalog changed while reading")
    return body, {"sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CandidateError("invalid_index", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _empty():
    return {"schema_version": SCHEMA_VERSION, "revision": 0, "candidates": {}, "resolutions": {}, "requests": {}}


def _read_index(path):
    body, version = _read_bytes(path)
    if body is None:
        return _empty(), None
    try:
        data = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    except (ValueError, UnicodeError) as exc:
        raise CandidateError("invalid_index", f"Cannot read candidate index: {exc}") from exc
    if (not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION
            or type(data.get("revision")) is not int or data["revision"] < 0
            or any(not isinstance(data.get(k), dict) for k in ("candidates", "resolutions", "requests"))):
        raise CandidateError("invalid_index", "Unsupported or malformed candidate index")
    for key, record in data["candidates"].items():
        if (not isinstance(record, dict) or record.get("id") != key
                or record.get("decision") not in DECISIONS
                or not isinstance(record.get("feedback"), list)
                or not isinstance(record.get("history"), list)
                or type(record.get("record_version")) is not int):
            raise CandidateError("invalid_index", "Malformed stored candidate")
        try:
            _record({k: v for k, v in record.items() if k in TEXT_FIELDS | LIST_FIELDS | {"account_id", "key", "decision", "sources"}})
            if candidate_id(record["account_id"], record["key"]) != key:
                raise ValueError("Candidate identity does not match its stable key")
            for event in record["feedback"]:
                if not isinstance(event, dict):
                    raise ValueError("Malformed feedback event")
                _text(event.get("id"), "feedback id")
                _text(event.get("recorded_at"), "feedback time")
                _clean_feedback({k: v for k, v in event.items() if k not in {"id", "recorded_at"}})
        except (ValueError, KeyError, TypeError) as exc:
            raise CandidateError("invalid_index", f"Malformed stored candidate: {exc}") from exc
    for key, history in data["resolutions"].items():
        if not isinstance(history, list):
            raise CandidateError("invalid_index", "Malformed stored resolution history")
        for record in history:
            try:
                if not isinstance(record, dict):
                    raise ValueError("Resolution must be an object")
                clean = _clean_resolution({k: v for k, v in record.items()
                                           if k not in {"recorded_at", "request_id", "observations"}})
                _text(record.get("recorded_at"), "resolution time")
                _text(record.get("request_id"), "resolution request")
                if (key != clean["account_id"] + "/" + clean["slug"]
                        or not isinstance(record.get("observations"), list)
                        or _json_digest(record["observations"]) != clean["observed_fingerprint"]):
                    raise ValueError("Resolution identity or observed evidence fingerprint does not match")
            except (ValueError, TypeError) as exc:
                raise CandidateError("invalid_index", f"Malformed stored resolution: {exc}") from exc
    for request_id, receipt in data["requests"].items():
        if (not isinstance(receipt, dict) or type(receipt.get("revision")) is not int
                or not 1 <= receipt["revision"] <= data["revision"]
                or not isinstance(receipt.get("fingerprint"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", receipt["fingerprint"])):
            raise CandidateError("invalid_index", "Malformed idempotency receipt")
        candidate_ref, resolution_ref = receipt.get("candidate_id"), receipt.get("resolution_key")
        if candidate_ref is not None:
            valid = isinstance(candidate_ref, str) and candidate_ref in data["candidates"] and resolution_ref is None
        else:
            valid = (isinstance(resolution_ref, str) and resolution_ref in data["resolutions"]
                     and any(r["request_id"] == request_id for r in data["resolutions"][resolution_ref]))
        if not valid:
            raise CandidateError("invalid_index", "Idempotency receipt refers to a missing result")
    return data, version


def _public(data, version, path):
    return {"status": "ok" if data["candidates"] else "empty", "initialized": version is not None,
            "revision": data["revision"], "version": version, "index_path": str(path),
            "candidates": deepcopy(list(data["candidates"].values())),
            "resolutions": deepcopy(data["resolutions"])}


def load_index(paths, *, index_path=None):
    path = _index_path(paths, index_path)
    data, version = _read_index(path)
    return _public(data, version, path)


def list_candidates(paths, *, index_path=None, account_id=None, decision=None):
    if decision is not None and decision not in DECISIONS:
        raise CandidateError("invalid_request", "Unknown candidate decision")
    view = load_index(paths, index_path=index_path)
    view["candidates"] = [c for c in view["candidates"]
                          if (account_id is None or c["account_id"] == account_id)
                          and (decision is None or c["decision"] == decision)]
    view["status"] = "ok" if view["candidates"] else "empty"
    return view


def candidate_id(account_id, key):
    account_id, key = _text(account_id, "account_id"), _text(key, "key")
    return "topic-" + _json_digest([account_id, key])[:24]


def _mutate(paths, index_path, expected_revision, request_id, operation, payload, apply):
    if type(expected_revision) is not int or expected_revision < 0:
        raise CandidateError("invalid_request", "expected_revision must be a nonnegative integer")
    request_id = _text(request_id, "request_id")
    path = _index_path(paths, index_path)
    fingerprint = _json_digest({"operation": operation, "payload": payload})
    lock = _local_path(paths, Path(paths.cache) / "topic-candidates" /
                       (hashlib.sha256(str(path).encode()).hexdigest() + ".lock"))
    with file_lock(lock):
        _index_path(paths, path)
        data, before = _read_index(path)
        prior = data["requests"].get(request_id)
        if prior is not None:
            if not isinstance(prior, dict) or prior.get("fingerprint") != fingerprint:
                raise CandidateError("idempotency_conflict", "request_id already names a different operation")
            if "candidate_id" in prior:
                result = {"candidate": deepcopy(data["candidates"][prior["candidate_id"]])}
            else:
                result = {"resolution": next(r for r in data["resolutions"][prior["resolution_key"]]
                                             if r["request_id"] == request_id)}
            return {"status": "ok", "changed": False, "replayed": True,
                    "revision": data["revision"], "applied_revision": prior["revision"],
                    **deepcopy(result)}
        if data["revision"] != expected_revision:
            raise CandidateError("version_conflict", f"Expected revision {expected_revision}; found {data['revision']}")
        result, changed = apply(data)
        data["revision"] += 1
        receipt = {"candidate_id": result["candidate"]["id"]} if "candidate" in result else {
            "resolution_key": result["resolution"]["account_id"] + "/" + result["resolution"]["slug"]}
        data["requests"][request_id] = {"fingerprint": fingerprint, "revision": data["revision"], **receipt}
        if len(json.dumps(data, ensure_ascii=False, allow_nan=False).encode()) > MAX_BYTES:
            raise CandidateError("invalid_index", "Candidate index exceeds the byte budget")
        _index_path(paths, path)
        if _read_bytes(path)[1] != before:
            raise CandidateError("version_conflict", "Candidate index was edited outside this transaction")
        atomic_json(path, data)
        return {"status": "ok", "changed": changed, "replayed": False,
                "revision": data["revision"], "applied_revision": data["revision"], **deepcopy(result)}


def _record(record):
    if not isinstance(record, dict):
        raise CandidateError("invalid_request", "record must be an object")
    allowed = TEXT_FIELDS | LIST_FIELDS | {"account_id", "key", "decision", "sources"}
    if set(record) - allowed:
        raise CandidateError("invalid_request", "Unknown candidate fields: " + ", ".join(sorted(set(record) - allowed)))
    result = {name: _text(record.get(name), name) for name in ("account_id", "key", "title", "reader_task")}
    for name in TEXT_FIELDS - {"title", "reader_task"}:
        if name in record:
            result[name] = _text(record[name], name)
    for name in LIST_FIELDS:
        if name in record:
            result[name] = _strings(record[name], name)
    if "decision" in record:
        if record["decision"] not in DECISIONS:
            raise CandidateError("invalid_request", "Unknown candidate decision")
        result["decision"] = record["decision"]
    if "sources" in record:
        if not isinstance(record["sources"], list):
            raise CandidateError("invalid_request", "sources must be a list")
        result["sources"] = []
        for source in record["sources"]:
            if not isinstance(source, dict) or set(source) - {"source_id", "item_id", "url"}:
                raise CandidateError("invalid_request", "Invalid candidate source")
            clean = {k: _text(v, k) for k, v in source.items()}
            _text(clean.get("source_id"), "source_id")
            if clean not in result["sources"]:
                result["sources"].append(clean)
    return result


def upsert_candidate(paths, record, *, expected_revision, request_id, index_path=None):
    clean = _record(record)
    identity = candidate_id(clean["account_id"], clean["key"])

    def apply(data):
        previous = data["candidates"].get(identity)
        candidate = deepcopy(previous) if previous else {
            "id": identity, "record_version": 0, "decision": "proposed", "sources": [],
            "feedback": [], "history": [], "created_at": _now(),
        }
        changes = {k: {"before": candidate.get(k), "after": v}
                   for k, v in clean.items() if candidate.get(k) != v}
        if changes:
            candidate.update(clean)
            candidate["record_version"] += 1
            candidate["updated_at"] = _now()
            candidate["history"].append({"record_version": candidate["record_version"],
                                         "at": candidate["updated_at"], "changes": changes})
            data["candidates"][identity] = candidate
        return {"candidate": candidate}, bool(changes)

    return _mutate(paths, index_path, expected_revision, request_id, "upsert", clean, apply)


def _clean_feedback(event):
    if not isinstance(event, dict) or event.get("kind") not in FEEDBACK_KINDS:
        raise CandidateError("invalid_request", "Unknown feedback kind")
    allowed = {"kind", "reason", "actor", "evidence_refs", "source_ids", "effort_minutes", "assessment", "outcome"}
    if set(event) - allowed:
        raise CandidateError("invalid_request", "Unknown feedback fields")
    clean = {name: _text(event.get(name), name) for name in ("kind", "reason", "actor")}
    for name in ("evidence_refs", "source_ids"):
        if name in event:
            clean[name] = _strings(event[name], name)
    if "effort_minutes" in event:
        clean["effort_minutes"] = _number(event["effort_minutes"], "effort_minutes")
        _strings(clean.get("evidence_refs", []), "evidence_refs", required=True)
    if "outcome" in event:
        clean["outcome"] = _text(event["outcome"], "outcome")
    if clean["kind"] in {"used", "production_result", "source_review"}:
        _strings(clean.get("evidence_refs", []), "evidence_refs", required=True)
    if clean["kind"] in {"used", "source_review"}:
        _strings(clean.get("source_ids", []), "source_ids", required=True)
    if clean["kind"] == "source_review":
        if event.get("assessment") not in {"useful_topic", "reduced_verification", "no_increment"}:
            raise CandidateError("invalid_request", "source_review needs an explicit assessment")
        clean["assessment"] = event["assessment"]
    elif "assessment" in event:
        raise CandidateError("invalid_request", "assessment belongs to source_review")

    return clean


def record_feedback(paths, topic_id, event, *, expected_revision, request_id, index_path=None):
    topic_id = _text(topic_id, "topic_id")
    request_id = _text(request_id, "request_id")
    clean = _clean_feedback(event)

    def apply(data):
        if topic_id not in data["candidates"]:
            raise CandidateError("candidate_not_found", "The selected candidate does not exist")
        candidate = data["candidates"][topic_id]
        known_sources = {source["source_id"] for source in candidate.get("sources", [])}
        if set(clean.get("source_ids", [])).difference(known_sources):
            raise CandidateError("invalid_request", "Feedback source_ids must refer to this candidate's sources")
        stored = {**clean, "id": request_id, "recorded_at": _now()}
        candidate["feedback"].append(stored)
        decisions = {"selected": "selected", "needs_research": "needs_research", "observe": "observe",
                     "rejected": "rejected", "materials_missing": "needs_research", "duplicate": "rejected",
                     "off_scope": "rejected", "not_worth_it": "rejected"}
        if clean["kind"] in decisions:
            candidate["decision"] = decisions[clean["kind"]]
        candidate["record_version"] += 1
        candidate["updated_at"] = stored["recorded_at"]
        return {"candidate": candidate}, True

    return _mutate(paths, index_path, expected_revision, request_id, "feedback", {"id": topic_id, "event": clean}, apply)


def _cells(line):
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _status(raw):
    match = re.match(r"^(pending|published)(?:\s|[（(]|$)", raw, re.I)
    if match:
        return match[1].lower()
    return {"已发布": "published", "待发布": "pending"}.get(raw, "unknown")


def _catalog_observations(paths, catalog_refs):
    if not isinstance(catalog_refs, list) or len(catalog_refs) > 64:
        raise CandidateError("invalid_request", "catalog_refs must be an explicit list of at most 64 files")
    observations, sources, seen = [], [], set()
    for ref in catalog_refs:
        ref = {"path": ref} if isinstance(ref, str) else ref
        if not isinstance(ref, dict) or set(ref) - {"path", "account_id"}:
            raise CandidateError("invalid_request", "Catalog reference needs path and optional account_id")
        if "account_id" in ref:
            _text(ref["account_id"], "account_id")
        path = _catalog_path(paths, _text(ref.get("path"), "catalog path"), ".md")
        identity = (str(path), ref.get("account_id"))
        if identity in seen:
            continue
        seen.add(identity)
        body, version = _read_bytes(path)
        if body is None:
            raise CandidateError("catalog_not_found", f"Selected catalog does not exist: {path}")
        try:
            lines = body.decode("utf-8").splitlines()
        except UnicodeError as exc:
            raise CandidateError("invalid_catalog", "Selected catalog is not UTF-8") from exc
        source = {"path": str(path.relative_to(paths.root)), "sha256": version["sha256"]}
        sources.append(source)
        header, fenced, recognized = None, False, False
        for index, line in enumerate(lines):
            if line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
                header = None
                continue
            if fenced or not line.strip().startswith("|"):
                header = None
                continue
            cells = _cells(line)
            lower = [c.casefold() for c in cells]
            if "slug" in lower and ("状态" in cells or "status" in lower):
                header = lower
                recognized = True
                continue
            if header is None or all(re.fullmatch(r":?-+:?", c) for c in cells):
                continue
            if len(cells) != len(header):
                raise CandidateError("invalid_catalog", f"Malformed catalog row at {source['path']}:{index + 1}")
            row = dict(zip(header, cells))
            account = row.get("账号") or row.get("account_id") or ref.get("account_id")
            if not account:
                raise CandidateError("invalid_catalog", "A selected catalog must declare account_id or contain an account column")
            if ref.get("account_id") and (row.get("账号") or row.get("account_id")) and account != ref["account_id"]:
                continue
            raw_status = row.get("状态", row.get("status", ""))
            slug = _text(row.get("slug"), "catalog slug").strip("`")
            observations.append({"account_id": account, "slug": slug, "status": _status(raw_status),
                                 "raw_status": raw_status, "title": row.get("标题", row.get("title")),
                                 "source_ref": source["path"], "line": index + 1, "source_sha256": source["sha256"]})
        if not recognized:
            raise CandidateError("invalid_catalog", f"No slug/status catalog table found: {source['path']}")
    return observations, sources


def _registry_records(observations, resolutions):
    groups = {}
    for observation in observations:
        groups.setdefault((observation["account_id"], observation["slug"]), []).append(observation)
    records = []
    for (account, slug), values in sorted(groups.items()):
        values = sorted(values, key=lambda x: (x["source_ref"], x["line"]))
        fingerprint = _json_digest(values)
        states = {v["status"] for v in values}
        conflict = len(states) > 1 or "unknown" in states
        key = account + "/" + slug
        history = resolutions.get(key, [])
        latest = history[-1] if history else None
        resolution_status = "none" if latest is None else (
            "current" if latest["observed_fingerprint"] == fingerprint else "stale_resolution")
        effective = latest["status"] if resolution_status == "current" else (None if conflict else next(iter(states)))
        records.append({"account_id": account, "slug": slug, "observations": values,
                        "observed_fingerprint": fingerprint, "status_conflict": conflict,
                        "catalog_status": None if conflict else next(iter(states)), "effective_status": effective,
                        "status_basis": "documented_resolution" if resolution_status == "current" else "catalog_record",
                        "resolution_status": resolution_status, "resolution_history": deepcopy(history),
                        "unresolved": conflict and resolution_status != "current"})
    return records


def registry_view(paths, catalog_refs, *, index_path=None):
    observations, sources = _catalog_observations(paths, catalog_refs)
    index = load_index(paths, index_path=index_path)
    records = _registry_records(observations, index["resolutions"])
    return {"status": "ok" if records else "empty", "sources": sources, "records": records,
            "conflicts": [r for r in records if r["status_conflict"]], "revision": index["revision"],
            "article_accessed": False}


def _clean_resolution(resolution):
    if not isinstance(resolution, dict):
        raise CandidateError("invalid_request", "resolution must be an object")
    required = {"account_id", "slug", "status", "observed_fingerprint", "reason", "actor", "evidence_kind", "evidence_refs"}
    if set(resolution) != required:
        raise CandidateError("invalid_request", "Resolution requires identity, fingerprint, status, actor, reason and evidence")
    clean = {k: _text(v, k) for k, v in resolution.items() if k != "evidence_refs"}
    clean["evidence_refs"] = _strings(resolution["evidence_refs"], "evidence_refs", required=True)
    if clean["status"] not in {"pending", "published"} or clean["evidence_kind"] not in {
        "explicit_user_confirmation", "publication_receipt", "verified_public_url"
    }:
        raise CandidateError("invalid_request", "Resolution needs an explicit supported evidence kind and status")

    return clean


def resolve_registry_conflict(paths, catalog_refs, resolution, *, expected_revision, request_id, index_path=None):
    request_id = _text(request_id, "request_id")
    clean = _clean_resolution(resolution)

    def apply(data):
        observations, _ = _catalog_observations(paths, catalog_refs)
        records = _registry_records(observations, data["resolutions"])
        selected = next((r for r in records if (r["account_id"], r["slug"]) == (clean["account_id"], clean["slug"])), None)
        if selected is None or selected["observed_fingerprint"] != clean["observed_fingerprint"]:
            raise CandidateError("version_conflict", "Catalog observations no longer match the resolution")
        if not selected["status_conflict"]:
            raise CandidateError("invalid_request", "The selected observations do not have a conflict")
        stored = {**clean, "recorded_at": _now(), "request_id": request_id,
                  "observations": selected["observations"]}
        data["resolutions"].setdefault(clean["account_id"] + "/" + clean["slug"], []).append(stored)
        return {"resolution": stored}, True

    return _mutate(paths, index_path, expected_revision, request_id, "resolve",
                   {"catalog_refs": catalog_refs, "resolution": clean}, apply)


def render_candidates(view):
    def cell(value):
        return str(value or "—").replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = ["| 选题 | 账号 | 读者任务与交付 | 理由与材料缺口 | 决策 |", "|---|---|---|---|---|"]
    for c in view["candidates"]:
        task = c["reader_task"] + ("；" + c["practical_output"] if c.get("practical_output") else "")
        reason = c.get("rationale", "")
        if c.get("material_gaps"):
            reason += "；待补：" + "、".join(c["material_gaps"])
        lines.append("| " + " | ".join(cell(x) for x in (c["title"], c["account_id"], task, reason, c["decision"])) + " |")
    return "\n".join(lines) + "\n"


def source_summary(paths, *, index_path=None):
    view = load_index(paths, index_path=index_path)
    sources, total_effort = {}, 0
    for candidate in view["candidates"]:
        current_ids = {s["source_id"] for s in candidate.get("sources", [])}
        ids = current_ids | {s for e in candidate["feedback"] for s in e.get("source_ids", [])}
        for source_id in ids:
            item = sources.setdefault(source_id, {"source_id": source_id, "candidate_ids": [],
                                                  "selected_candidate_ids": [], "used_candidate_ids": [], "feedback": []})
            if source_id in current_ids:
                item["candidate_ids"].append(candidate["id"])
            if source_id in current_ids and candidate["decision"] == "selected":
                item["selected_candidate_ids"].append(candidate["id"])
        for event in candidate["feedback"]:
            if event["kind"] == "production_result":
                total_effort += event.get("effort_minutes", 0)
            for source_id in event.get("source_ids", []):
                item = sources[source_id]
                if event["kind"] == "used" and candidate["id"] not in item["used_candidate_ids"]:
                    item["used_candidate_ids"].append(candidate["id"])
                item["feedback"].append({"candidate_id": candidate["id"], **deepcopy(event)})
    return {"status": "ok" if sources else "empty", "revision": view["revision"],
            "sources": list(sources.values()), "recorded_production_minutes": total_effort,
            "basis": "explicit_candidate_feedback", "automatic_source_decisions": False}
