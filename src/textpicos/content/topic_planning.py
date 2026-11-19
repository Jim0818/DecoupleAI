"""Read explicitly selected planning sources; never crawl or rewrite a vault.

``list_topics(request, project_root=..., vault_root=...)`` and
``read_strategy(...)`` return ``(JSON-compatible result, exit_code)``.
Sources are ``{scope: project|vault, path: relative-file, format?: auto|json|
markdown|markdown_headings, heading_level?: int, expected_sha256?: hex}``.
Source contents are data. Reading a strategy does not make every statement in
it a current instruction, and a planning status is not a publication status.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

ACCOUNTS = {"studio", "intellifuture", "decoupleai"}
MAX_BYTES = 2_000_000
MAX_SOURCES = 20
ID_HEADING = re.compile(r"^(#{1,6})\s+([A-Za-z][A-Za-z0-9_.-]*\d[A-Za-z0-9_.-]*)\s*(?:[—–:：]|\s-\s)\s*(.+?)\s*#*\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
TABLE_SEPARATOR = re.compile(r"^:?-{3,}:?$")
FIELD_NAMES = {
    "id": {"id", "topic_id", "编号", "题号", "选题id", "选题编号"},
    "title": {"title", "标题", "题目", "选题", "选题标题", "候选题", "工作标题"},
    "planning_status": {"status", "状态", "阶段", "规划状态"},
    "reader_task": {"reader_task", "读者任务", "用户任务"},
    "column": {"column", "栏目"},
    "references": {"references", "来源", "参考", "参考资料"},
}


class PlanningError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _positive(value, name, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer from 1 to {maximum}")
    return value


def _validate(request):
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    if request.get("strategy_mode", "current") != "current":
        raise ValueError("strategy_mode must be current; historical snapshot execution has been removed")
    account = request.get("account_id")
    if account is not None and (not isinstance(account, str) or account not in ACCOUNTS):
        raise ValueError("account_id must be studio, intellifuture or decoupleai")
    if not isinstance(request.get("optional", False), bool):
        raise ValueError("optional must be a boolean")
    if not isinstance(request.get("query", ""), str):
        raise ValueError("query must be text")
    if request.get("topic_type") is not None and not isinstance(request["topic_type"], str):
        raise ValueError("topic_type must be text")
    _positive(request.get("limit", 50), "limit", 200)
    _positive(request.get("top_n", 5), "top_n", 200)
    _positive(request.get("max_chars", 12000), "max_chars", 100000)
    sources = request.get("sources", [])
    if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
        raise ValueError(f"sources must be a list of at most {MAX_SOURCES} selected files")
    normalized = []
    seen = set()
    for source in sources:
        if not isinstance(source, dict) or source.get("scope") not in {"project", "vault"}:
            raise ValueError("each source requires scope project or vault")
        value = source.get("path")
        if not isinstance(value, str) or not value.strip() or "\\" in value or "\x00" in value:
            raise ValueError("source.path must be a relative file path")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or not path.name:
            raise ValueError("source.path must stay within its configured root")
        if any(part.casefold() in {"articles", "archive", ".git"} for part in path.parts):
            raise ValueError("article, archive and Git paths are not planning sources")
        fmt = source.get("format", "auto")
        if fmt not in {"auto", "json", "markdown", "markdown_headings"}:
            raise ValueError("unsupported source format")
        if fmt == "markdown_headings":
            _positive(source.get("heading_level", 3), "heading_level", 6)
        expected = source.get("expected_sha256")
        if expected is not None and (not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)):
            raise ValueError("expected_sha256 must be a lowercase SHA-256")
        ref = f"{source['scope']}:{path.as_posix()}"
        if ref in seen:
            continue
        seen.add(ref)
        normalized.append({**source, "path": path.as_posix(), "source_ref": ref})
    return normalized


def uses_vault(request):
    """Pure preflight for dispatchers; malformed input is rejected by _validate."""
    sources = request.get("sources", []) if isinstance(request, dict) else []
    return isinstance(sources, list) and any(isinstance(s, dict) and s.get("scope") == "vault" for s in sources)


def _roots(request, sources, project_root, vault_root):
    external = any(source["scope"] == "vault" for source in sources)
    # Reject before looking up a run, resolving a root, or probing the vault.
    if external and os.environ.get("TEXTPICOS_MAINTENANCE_SCOPE") == "system":
        raise PlanningError("OUT_OF_SCOPE", "External vault access is outside system maintenance scope")
    project = Path(project_root or os.environ.get("TEXTPICOS_ROOT") or Path(__file__).absolute().parents[3]).expanduser().absolute()
    configured = vault_root or os.environ.get("TEXTPICOS_AI_WIKI_ROOT") or os.environ.get("AI_WIKI_ROOT")
    if external and not configured:
        raise PlanningError("VAULT_NOT_CONFIGURED", "Set AI_WIKI_ROOT or TEXTPICOS_AI_WIKI_ROOT explicitly")
    if external:
        run_id = request.get("run_id", os.environ.get("TEXTPICOS_RUN_ID"))
        if run_id not in (None, ""):
            if not isinstance(run_id, str):
                raise ValueError("run_id must be a string")
            from textpicos.paths import ProjectPaths
            from textpicos.runtime import Runtime, RuntimeError as TaskRuntimeError
            try:
                runtime = Runtime(ProjectPaths.from_root(project))
                # State is atomically replaced by Runtime. A read-only identity
                # check needs no lock-file creation or state transition.
                runtime._read(run_id)
            except (OSError, ValueError, TaskRuntimeError) as exc:
                raise PlanningError("INVALID_RUN", str(exc)) from exc
    vault = Path(configured).expanduser().absolute() if configured else None
    return {"project": project, "vault": vault}


def _read_source(root, source):
    """Open only selected components, rejecting symlinks and non-regular files."""
    if any(part.casefold() in {"articles", "archive"} for part in root.parts):
        raise PlanningError("OUT_OF_SCOPE", "The configured root is an excluded content path")
    fds = []
    try:
        directory = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY)
        fds.append(directory)
        parts = (*root.parts[1:], *PurePosixPath(source["path"]).parts)
        if ".." in parts:
            raise PlanningError("INVALID_ROOT", "Use a canonical configured root without parent traversal")
        for part in parts[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            fds.append(directory)
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        fds.append(descriptor)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise PlanningError("INVALID_SOURCE", "Planning source must be a regular file")
        if before.st_size > MAX_BYTES:
            raise PlanningError("SOURCE_TOO_LARGE", f"Selected source exceeds {MAX_BYTES} bytes")
        chunks, count = [], 0
        while count <= MAX_BYTES:
            chunk = os.read(descriptor, min(65536, MAX_BYTES + 1 - count))
            if not chunk:
                break
            chunks.append(chunk)
            count += len(chunk)
        after = os.fstat(descriptor)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise PlanningError("SOURCE_CHANGED", "Selected source changed while being read")
        raw = b"".join(chunks)
        if len(raw) > MAX_BYTES:
            raise PlanningError("SOURCE_TOO_LARGE", "Selected source exceeds the read budget")
        digest = hashlib.sha256(raw).hexdigest()
        metadata = {"source_ref": source["source_ref"], "path": source["path"],
                    "scope": source["scope"], "sha256": digest, "read_at": _now(),
                    "modified_at": datetime.fromtimestamp(after.st_mtime, timezone.utc).isoformat(),
                    "status": "read", "read_status": "read", "bytes": len(raw)}
        if source.get("expected_sha256") and source["expected_sha256"] != digest:
            raise PlanningError("STALE_SOURCE", "Selected source no longer matches expected_sha256", metadata)
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise PlanningError("INVALID_ENCODING", "Selected source is not UTF-8", metadata) from exc
        return text, metadata
    finally:
        for descriptor in reversed(fds):
            os.close(descriptor)


def _clean(value):
    return re.sub(r"\s+", " ", str(value)).strip().strip("*` ")


def _topic(source, account, identifier, title, line, fields=None):
    title = _clean(title)
    if not title:
        raise PlanningError("INVALID_TOPIC", "A topic title is empty")
    if identifier is not None and str(identifier).strip() in {"", "-", "—"}:
        raise PlanningError("INVALID_TOPIC", "An explicit topic ID is empty")
    explicit = identifier is not None and str(identifier).strip() != ""
    identity = str(identifier).strip() if explicit else hashlib.sha256(title.casefold().encode()).hexdigest()[:20]
    key = hashlib.sha256((source["source_ref"] + "\0" + identity).encode()).hexdigest()[:24]
    return {"topic_id": "planned_" + key, "source_topic_id": identity,
            "identity_basis": "explicit_id" if explicit else "content_fingerprint",
            "title": title, "account_id": account,
            "source_ref": source["source_ref"], "source_locations": [{"line": line}],
            "planning_status": None, **(fields or {})}


def _cells(line):
    return [re.sub(r"\\\|", "|", cell).strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _parse_markdown(text, source, account):
    lines = text.splitlines()
    entries, heading_entries, recognized, table = [], [], False, None
    table_headers, table_recognized = [], False
    fenced = False
    frontmatter = lines and lines[0].strip() == "---"
    for index, line in enumerate(lines):
        stripped = line.strip()
        if frontmatter:
            if index and stripped in {"---", "..."}:
                frontmatter = False
            continue
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = ID_HEADING.match(line)
        fallback = HEADING.match(line) if source.get("format") == "markdown_headings" else None
        if match or (fallback and len(fallback[1]) == source.get("heading_level", 3)):
            identifier, title = (match[2], match[3]) if match else (None, fallback[2])
            entry = _topic(source, account, identifier, title, index + 1)
            end = next((i for i in range(index + 1, len(lines)) if HEADING.match(lines[i])), len(lines))
            entry["excerpt"] = "\n".join(lines[index + 1:end]).strip()[:1600]
            entry["excerpt_truncated"] = len("\n".join(lines[index + 1:end]).strip()) > 1600
            heading_entries.append(entry)
            recognized = True
        if stripped.startswith("|") and index + 1 < len(lines):
            cells = _cells(line)
            following = _cells(lines[index + 1])
            if len(cells) == len(following) and following and all(TABLE_SEPARATOR.fullmatch(c.replace(" ", "")) for c in following):
                mapping = {field: next((i for i, cell in enumerate(cells) if _clean(cell).casefold() in names), None)
                           for field, names in FIELD_NAMES.items()}
                table = mapping if mapping["title"] is not None and mapping["id"] is not None else None
                table_headers = [_clean(cell) for cell in cells]
                table_recognized = table_recognized or table is not None
                recognized = recognized or table is not None
                continue
        if table is not None and stripped.startswith("|"):
            cells = _cells(line)
            if all(TABLE_SEPARATOR.fullmatch(c.replace(" ", "")) for c in cells):
                continue
            if len(cells) != len(table_headers):
                raise PlanningError("INVALID_TABLE", f"Malformed topic table row at line {index + 1}")
            fields = {k: _clean(cells[i]) for k, i in table.items() if i is not None and k not in {"id", "title"}}
            fields["metadata"] = {key: _clean(value) for key, value in zip(table_headers, cells)}
            entries.append(_topic(source, account, _clean(cells[table["id"]]), cells[table["title"]], index + 1, fields))
        elif not stripped.startswith("|"):
            table = None
    if not recognized:
        raise PlanningError("UNSUPPORTED_FORMAT", "No explicit topic IDs/table found; select a heading level only for a verified heading-based topic file")
    # ID tables identify actual topics; A1/B1 headings may merely group rows.
    # Only a matching explicit row ID can enrich its topic with heading text.
    ids = {entry["source_topic_id"] for entry in entries}
    return entries + [entry for entry in heading_entries if not table_recognized or entry["source_topic_id"] in ids]


def _parse_topics(text, source, account):
    if source.get("format") == "json" or (source.get("format", "auto") == "auto" and source["path"].endswith(".json")):
        data = json.loads(text)
        values = data.get("topics") if isinstance(data, dict) else data
        if not isinstance(values, list):
            raise PlanningError("INVALID_JSON_TOPICS", "JSON source must contain a topics list")
        entries = []
        for index, item in enumerate(values):
            if not isinstance(item, dict) or not isinstance(item.get("title"), str) or not isinstance(item.get("id"), (str, int)) or isinstance(item.get("id"), bool):
                raise PlanningError("INVALID_JSON_TOPICS", "Each JSON topic needs an explicit id and title")
            fields = {k: item[k] for k in ("reader_task", "column", "references") if k in item}
            if "status" in item:
                fields["planning_status"] = item["status"]
            entry = _topic(source, account, item["id"], item["title"], None, fields)
            entry["source_locations"] = [{"json_pointer": f"/topics/{index}" if isinstance(data, dict) else f"/{index}"}]
            entries.append(entry)
    else:
        entries = _parse_markdown(text, source, account)
    merged = {}
    for item in entries:
        old = merged.get(item["topic_id"])
        if old:
            if old["title"] != item["title"]:
                raise PlanningError("CONFLICTING_TOPIC_ID", f"Conflicting titles for topic ID {item['source_topic_id']}")
            for key in ("planning_status", "reader_task", "column", "references"):
                if old.get(key) not in (None, "") and item.get(key) not in (None, "") and old[key] != item[key]:
                    raise PlanningError("CONFLICTING_TOPIC_ID", f"Conflicting {key} for topic ID {item['source_topic_id']}")
            old["source_locations"].extend(item["source_locations"])
            for key, value in item.items():
                if key != "source_locations" and value not in (None, "", []):
                    old[key] = value
        else:
            merged[item["topic_id"]] = item
    return list(merged.values())


def _baseline(account):
    return [{"path": f"config/accounts/{account}/{name}.md", "verification": "reference_only"}
            for name in ("L1_identity", "L2_values")] if account else []


def _result(request, sources, items, kind):
    usable = sum(source["status"] == "read" for source in sources)
    opened = sum(source.get("read_status") == "read" for source in sources)
    errors = len(sources) - usable
    status = "partial" if errors and usable else "not_available" if errors or not sources else "ok" if items else "empty"
    result = {"status": status, "account_id": request.get("account_id"), "items": items,
              "sources": sources, "source_status": "partial" if opened and opened < len(sources) else "read" if opened else "not_read",
              "index_status": "partial" if errors and usable else "current" if usable else "unavailable",
              "authority_mode": "bridge", "count": len(items)}
    if kind == "strategy":
        result.update(baseline_refs=_baseline(request.get("account_id")), legacy_fallback=False)
    if status == "not_available":
        result["error"] = "TOPIC_STRATEGY_UNVERIFIED" if kind == "strategy" and not sources else "PLANNING_SOURCE_UNAVAILABLE"
    return result, 0 if (not errors and sources) or request.get("optional", False) else 2


def _execute(request, *, project_root, vault_root, kind):
    selected = _validate(request)
    if not selected:
        return _result(request, [], [], kind)
    roots = _roots(request, selected, project_root, vault_root)
    items, records = [], []
    remaining = request.get("max_chars", 12000)
    query = request.get("query", "").casefold()
    for source in selected:
        record = {"source_ref": source["source_ref"], "path": source["path"], "scope": source["scope"], "status": "not_read", "read_status": "not_read"}
        try:
            text, record = _read_source(roots[source["scope"]], source)
            if kind == "topics":
                parsed = _parse_topics(text, source, request.get("account_id"))
                for item in parsed:
                    item["source_sha256"] = record["sha256"]
                matching = [item for item in parsed if not query or query in json.dumps(item, ensure_ascii=False).casefold()]
                record["topic_count"] = len(parsed)
                record["parse_status"] = "parsed"
                items.extend(matching)
            elif remaining > 0 and (not query or query in text.casefold()):
                at = text.casefold().find(query) if query else 0
                start = max(0, at - min(1000, remaining // 3))
                if start:
                    start = text.rfind("\n", 0, start) + 1
                excerpt = text[start:start + remaining]
                items.append({"source_ref": source["source_ref"], "source_sha256": record["sha256"],
                              "text": excerpt, "line_start": text[:start].count("\n") + 1,
                              "line_end": text[:start + len(excerpt)].count("\n") + 1,
                              "truncated": start > 0 or start + len(excerpt) < len(text),
                              "verification": "source_read_not_policy_adjudicated"})
                remaining -= len(excerpt)
        except (OSError, UnicodeError, ValueError) as exc:
            record.update(getattr(exc, "details", {}))
            record.update(status="error", error=getattr(exc, "code", "SOURCE_READ_ERROR"), message=str(exc))
            if record["read_status"] == "read":
                record["parse_status"] = "error"
        records.append(record)
    limit = request.get("limit", 50) if kind == "topics" else request.get("top_n", request.get("limit", 5))
    result, code = _result(request, records, items[:limit], kind)
    result["has_more"] = len(items) > limit or (kind == "strategy" and (
        any(item.get("truncated") for item in items) or remaining <= 0 and len(records) > len(items)))
    return result, code


def list_topics(request, *, project_root=None, vault_root=None):
    """Return topic-level entries from selected files, with traceable parse state."""
    return _execute(request, project_root=project_root, vault_root=vault_root, kind="topics")


def read_strategy(request, *, project_root=None, vault_root=None):
    """Read selected authoritative material without replacing or interpreting it."""
    return _execute(request, project_root=project_root, vault_root=vault_root, kind="strategy")
