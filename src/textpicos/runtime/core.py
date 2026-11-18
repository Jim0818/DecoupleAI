"""Durable, phase-free tasks for a supervisor and host-provided workers.

The runtime never starts a model or decides editorial work. Workers receive a
private staging directory; only submit() promotes results. This is a cooperative
filesystem boundary, not a sandbox for arbitrary host tools. A write-ahead
transaction in engine-state.json makes interrupted multi-file commits recoverable.
Each file replacement is atomic; external readers must use committed references
instead of expecting a multi-file filesystem transaction.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from textpicos.context import ContextError, normalize_input_reference

from .storage import atomic_json, durable_copy, file_lock, file_version, replace_from_copy


class RuntimeError(Exception):
    def __init__(self, code: str, message: str, **details: Any):
        self.code = code
        self.details = details
        super().__init__(message)

    def as_dict(self) -> dict:
        return {"error": self.code, "message": str(self), **self.details}


class StateError(RuntimeError):
    pass


class ConflictError(RuntimeError):
    pass


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_LIVE = {"pending", "running", "blocked", "waiting_user", "failed"}
_TERMINAL = {"succeeded", "cancelled", "superseded"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _identifier(value: str, kind: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise StateError("invalid_identifier", f"Invalid {kind}: {value!r}")
    return value


def _sha(value: dict | None) -> str | None:
    return value.get("sha256") if value else None


class Runtime:
    """Use Runtime(ProjectPaths.from_root(project_root)). No discovery is implicit.

    Path strings are project-relative or absolute within the configured project.
    A string write scope means one exact file. Directory scopes explicitly use
    {"path": "output/figures", "kind": "directory"}; they permit *new* descendants
    only. Updating an existing file requires an exact-file scope and a dispatch
    baseline. This avoids recursive snapshots of broad project directories.
    """

    def __init__(self, paths: Any):
        self.paths = paths
        self.root = Path(paths.root).resolve()
        self.runs = Path(paths.runs).resolve()
        if not self.root.is_dir():
            raise StateError("missing_root", f"Project root does not exist: {self.root}")
        self._check_components(self.root)
        self._check_components(self.runs)

    def _check_components(self, path: Path) -> None:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current /= part
            try:
                info = current.lstat()
            except FileNotFoundError:
                break
            if stat.S_ISLNK(info.st_mode):
                raise StateError("symlink_path", f"Symlink paths are not accepted: {current}")

    def _path(self, value: str | Path) -> Path:
        path = Path(value)
        if ".." in path.parts:
            raise StateError("path_escape", f"Parent traversal is not accepted: {value}")
        path = path if path.is_absolute() else self.root / path
        path = path.absolute()
        if not path.is_relative_to(self.root):
            raise StateError("path_escape", f"Path is outside the project: {value}")
        self._check_components(path)
        return path

    def _ref(self, value: str | Path) -> str:
        return str(self._path(value).relative_to(self.root))

    def _run_dir(self, run_id: str) -> Path:
        path = self.runs / _identifier(run_id, "run id")
        self._check_components(path)
        return path

    def _state_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "engine-state.json"

    @contextmanager
    def _locked(self, run_id: str, *, creating: bool = False):
        path = self._state_path(run_id)
        if not creating and not path.is_file():
            raise StateError("run_not_found", f"No supervisor run: {run_id}")
        # Global lock serializes short control/commit operations, not workers.
        # It also makes CAS safe between different runs writing the same target.
        with file_lock(self.runs / ".locks" / "control.lock"):
            with file_lock(self.runs / ".locks" / f"{run_id}.lock"):
                self._check_components(path)
                yield

    def _read(self, run_id: str) -> dict:
        try:
            state = json.loads(self._state_path(run_id).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise StateError("run_not_found", f"No supervisor run: {run_id}") from exc
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise StateError("invalid_state", "The persisted state is not valid JSON") from exc
        if not isinstance(state, dict):
            raise StateError("invalid_state", "The persisted state must be an object")
        if state.get("orchestration_mode") != "supervisor" or state.get("schema_version") != 1:
            raise StateError("wrong_runtime", "Refusing to take ownership of a legacy/unknown run")
        if state.get("run_id") != run_id:
            raise StateError("run_mismatch", "Persisted run id does not match its directory")
        if not isinstance(state.get("tasks"), dict) or not isinstance(state.get("epoch"), int):
            raise StateError("invalid_state", "The persisted tasks/epoch fields are invalid")
        return state

    def _save(self, state: dict) -> None:
        state["revision"] += 1
        state["updated_at"] = _now()
        atomic_json(self._state_path(state["run_id"]), state)

    def _active(self, state: dict) -> None:
        if state["lifecycle"] != "active":
            raise StateError("run_closed", "Explicitly revise the run before doing further work")
        if state.get("pending_commit"):
            raise StateError("commit_pending", "Recover or abort the pending commit before changing the run")

    def _task(self, state: dict, task_id: str) -> dict:
        try:
            return state["tasks"][task_id]
        except KeyError as exc:
            raise StateError("task_not_found", f"Unknown task: {task_id}") from exc

    def _inputs(self, values: Iterable) -> list[dict]:
        result, scopes = [], {}
        for value in values:
            try:
                item = normalize_input_reference(value)
            except ContextError as exc:
                raise StateError("invalid_input_reference", str(exc)) from exc
            scope = item.get("version_scope", "file")
            if scope not in ("file", "article_content"):
                raise StateError("invalid_version_scope", "Input version_scope must be file or article_content")
            reference = self._ref(item["path"])
            if reference in scopes and scopes[reference] != scope:
                raise StateError("conflicting_version_scope", "One input cannot request different version scopes")
            scopes[reference] = scope
            result.append({**item, "path": reference, "required": bool(item.get("required", True))})
        return result

    def _input_version(self, reference: str, expected: dict | None) -> dict | None:
        """Compare against the input projection fixed by the dispatched attempt."""
        scope = (expected or {}).get("version_scope", "file")
        return file_version(self._path(reference), version_scope=scope)

    def _scopes(self, values: Iterable) -> list[dict]:
        result = []
        for value in values:
            item = {"path": value, "kind": "file"} if isinstance(value, (str, Path)) else dict(value)
            if item.get("kind", "file") not in {"file", "directory"}:
                raise StateError("invalid_scope", "Write scope kind must be file or directory")
            result.append({"path": self._ref(item["path"]), "kind": item.get("kind", "file")})
        return result

    def create(self, run_id: str, goal: str | dict, *, metadata: dict | None = None,
               deliverables: Iterable[str] = ()) -> dict:
        if not isinstance(goal, (str, dict)) or not goal:
            raise StateError("missing_goal", "A nonempty goal is required")
        with self._locked(run_id, creating=True):
            if self._state_path(run_id).exists():
                raise ConflictError("run_exists", f"Run already exists: {run_id}")
            now = _now()
            state = {"schema_version": 1, "orchestration_mode": "supervisor", "run_id": run_id,
                     "goal": _json_copy(goal), "metadata": _json_copy(metadata or {}),
                     "deliverables": [self._ref(p) for p in deliverables], "epoch": 1,
                     "lifecycle": "active", "revision": 0, "created_at": now, "updated_at": now,
                     "tasks": {}, "artifacts": {}, "revisions": [], "pending_commit": None,
                     "cleanup_pending": [], "completion": None}
            self._save(state)
            return self._view(state)

    def add(self, run_id: str, task_id: str, *, goal: str | dict, role: str | None = None,
            owner: str | None = None, depends_on: Iterable[str] = (), required: bool = True,
            input_refs: Iterable = (), inputs: Iterable | None = None,
            allowed_write_roots: Iterable = (), write_scopes: Iterable | None = None,
            mode: str | None = None, account_id: str | None = None, skill_ids: Iterable[str] | None = None,
            deliverables: Iterable[str] = (), acceptance_criteria: Any = None,
            metadata: dict | None = None, max_attempts: int = 3) -> dict:
        _identifier(task_id, "task id")
        if not role and not owner:
            raise StateError("missing_role", "A task role/owner is required")
        if not goal or not isinstance(goal, (str, dict)):
            raise StateError("missing_goal", "A nonempty task goal is required")
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise StateError("invalid_attempt_budget", "max_attempts must be a positive integer")
        with self._locked(run_id):
            state = self._read(run_id)
            self._active(state)
            if task_id in state["tasks"]:
                raise ConflictError("task_exists", "Use a new task id; dispatch retries the existing task")
            dependencies = list(dict.fromkeys(_identifier(v, "dependency") for v in depends_on))
            task = {"id": task_id, "epoch": state["epoch"], "role": role or owner,
                    "mode": mode, "account_id": account_id or state["metadata"].get("account_id"),
                    "skill_ids": None if skill_ids is None else list(skill_ids), "goal": _json_copy(goal),
                    "input_refs": self._inputs(inputs if inputs is not None else input_refs),
                    "allowed_write_roots": self._scopes(write_scopes if write_scopes is not None else allowed_write_roots),
                    "deliverables": [self._ref(p) for p in deliverables],
                    "acceptance_criteria": _json_copy(acceptance_criteria or []),
                    "metadata": _json_copy(metadata or {}), "depends_on": dependencies,
                    "required": bool(required), "status": "pending", "attempt": 0,
                    "max_attempts": max_attempts, "dispatch": None, "result": None,
                    "last_error": None, "created_at": _now(), "blockers": [],
                    "host_cancel_pending": False}
            state["tasks"][task_id] = task
            self._validate_dag(state)
            self._save(state)
            return _json_copy(task)

    def update(self, run_id: str, task_id: str, *, reason: str, **changes) -> dict:
        """Supervisor changes are explicit; dispatched inputs never change silently."""
        if not reason:
            raise StateError("missing_reason", "Explain the task adjustment")
        allowed = {"role", "mode", "account_id", "skill_ids", "goal", "input_refs",
                   "allowed_write_roots", "deliverables", "acceptance_criteria", "metadata",
                   "depends_on", "required", "max_attempts"}
        unknown = set(changes).difference(allowed)
        if unknown:
            raise StateError("unknown_task_fields", "Cannot update runtime-owned fields", fields=sorted(unknown))
        with self._locked(run_id):
            state = self._read(run_id)
            self._active(state)
            task = self._task(state, task_id)
            if task["epoch"] != state["epoch"]:
                raise StateError("old_epoch", "Historical tasks are immutable")
            if task["status"] == "running":
                raise StateError("task_in_flight", "Cancel or supersede the execution before changing its task")
            if task["status"] in _TERMINAL and set(changes).difference({"required"}):
                raise StateError("terminal_task", "Create a new task to change completed/cancelled work")
            values = _json_copy(changes)
            if "input_refs" in values:
                values["input_refs"] = self._inputs(values["input_refs"])
            if "allowed_write_roots" in values:
                values["allowed_write_roots"] = self._scopes(values["allowed_write_roots"])
            if "deliverables" in values:
                values["deliverables"] = [self._ref(p) for p in values["deliverables"]]
            if "depends_on" in values:
                values["depends_on"] = list(dict.fromkeys(_identifier(p, "dependency") for p in values["depends_on"]))
            if "goal" in values and (not values["goal"] or not isinstance(values["goal"], (str, dict))):
                raise StateError("missing_goal", "A task goal must be nonempty")
            if "required" in values and not isinstance(values["required"], bool):
                raise StateError("invalid_required", "required must be a boolean")
            if "max_attempts" in values:
                budget = values["max_attempts"]
                if not isinstance(budget, int) or isinstance(budget, bool) or budget < max(1, task["attempt"]):
                    raise StateError("invalid_attempt_budget", "The retry budget cannot be below attempts already made")
            task.update(values)
            if task["status"] in {"blocked", "waiting_user", "failed"}:
                task.update(status="pending", blockers=[])
            task["last_adjustment"] = {"reason": reason, "fields": sorted(values), "at": _now()}
            self._validate_dag(state)
            self._save(state)
            return _json_copy(task)

    def _validate_dag(self, state: dict) -> None:
        visiting, done = set(), set()
        def visit(key: str):
            if key in visiting:
                raise StateError("dependency_cycle", f"Dependency cycle includes {key}")
            if key in done or key not in state["tasks"]:
                return
            visiting.add(key)
            for dependency in state["tasks"][key]["depends_on"]:
                visit(dependency)
            visiting.remove(key)
            done.add(key)
        for key in state["tasks"]:
            visit(key)

    def _dependency_blocks(self, state: dict, task: dict) -> list[str]:
        blocks = []
        for dependency in task["depends_on"]:
            record = state["tasks"].get(dependency)
            if not record:
                blocks.append(f"missing_dependency:{dependency}")
            elif record["status"] != "succeeded":
                blocks.append(f"dependency:{dependency}:{record['status']}")
        return blocks

    def dispatch(self, run_id: str, task_id: str, *, host_id: str | None = None) -> dict:
        with self._locked(run_id):
            state = self._read(run_id)
            self._active(state)
            task = self._task(state, task_id)
            if task["epoch"] != state["epoch"]:
                raise StateError("old_epoch", "Create a task in the current revision")
            if task["status"] in {"running", "succeeded", "cancelled", "superseded", "waiting_user"}:
                raise StateError("not_dispatchable", f"Task is {task['status']}")
            blocks = self._dependency_blocks(state, task)
            if blocks:
                task.update(status="blocked", blockers=blocks)
                self._save(state)
                raise StateError("dependencies_blocked", "Task dependencies are not ready", blockers=blocks)
            if task["attempt"] >= task["max_attempts"]:
                raise StateError("attempts_exhausted", "Task retry budget is exhausted")
            versions = {}
            for item in task["input_refs"]:
                version = file_version(self._path(item["path"]),
                                       version_scope=item.get("version_scope", "file"))
                if version is None and item["required"]:
                    task.update(status="blocked", blockers=[f"missing_input:{item['path']}"])
                    self._save(state)
                    raise StateError("missing_input", f"Required input is missing: {item['path']}")
                versions[item["path"]] = version
            writes = {}
            for scope in task["allowed_write_roots"]:
                self._validate_target(state, self._path(scope["path"]), directory=scope["kind"] == "directory")
                if scope["kind"] == "file":
                    writes[scope["path"]] = file_version(self._path(scope["path"]))
            task["attempt"] += 1
            token = secrets.token_hex(24)
            stage = self._run_dir(run_id) / "staging" / task_id / f"{task['attempt']}-{token}"
            stage.mkdir(parents=True)
            dispatch = {"task_id": task_id, "attempt": task["attempt"], "epoch": state["epoch"],
                        "token": token, "host_id": str(host_id) if host_id is not None else None, "staging_dir": str(stage),
                        "input_versions": versions, "write_versions": writes, "started_at": _now()}
            task.update(status="running", dispatch=dispatch, blockers=[], last_error=None)
            self._save(state)
            return {**_json_copy(dispatch), "run_id": run_id, "task": _json_copy(task)}

    def bind_host(self, run_id: str, task_id: str, token: str, host_id: str) -> dict:
        with self._locked(run_id):
            state = self._read(run_id)
            task = self._authorized(state, task_id, token)
            if task["dispatch"].get("host_id") not in (None, host_id):
                raise ConflictError("host_already_bound", "This attempt is already bound to another host execution")
            task["dispatch"]["host_id"] = str(host_id)
            self._save(state)
            return {"task_id": task_id, "host_id": str(host_id)}

    def _authorized(self, state: dict, task_id: str, token: str) -> dict:
        if state["lifecycle"] != "active":
            raise ConflictError("fenced_result", "This delivery epoch is closed")
        if state.get("pending_commit"):
            raise StateError("commit_pending", "Recover the pending commit first")
        task = self._task(state, task_id)
        dispatch = task.get("dispatch") or {}
        if (task["status"] != "running" or task["epoch"] != state["epoch"]
                or dispatch.get("epoch") != state["epoch"] or dispatch.get("token") != token):
            raise ConflictError("fenced_result", "Attempt, token, epoch or task status no longer authorizes submission")
        return task

    def _validate_target(self, state: dict, path: Path, *, directory: bool = False) -> None:
        if path == self.root:
            raise StateError("protected_target", "The whole project is not a write scope")
        if path.is_relative_to(self.runs):
            relative = path.relative_to(self.runs).parts
            if (not relative or relative[0].startswith(".") or relative[0] != state["run_id"]
                    or len(relative) < 2 or relative[1] in {"engine-state.json", "staging", "_transactions"}):
                raise StateError("protected_target", "Task output cannot overwrite runtime control or another run")
        if not directory and path.is_dir():
            raise StateError("directory_output", "A submitted output must be one regular file")

    def _request(self, state: dict, task: dict, outputs: Iterable, summary: str, blockers: Iterable) -> dict:
        stage = Path((task.get("dispatch") or {}).get("staging_dir", "/nonexistent"))
        normalized = []
        for raw in outputs:
            staged = Path(raw["staged_path"])
            staged = staged if staged.is_absolute() else stage / staged
            if ".." in staged.parts or not staged.is_relative_to(stage):
                raise StateError("staging_escape", "Output source must be inside this attempt's staging directory")
            normalized.append({"staged_path": str(staged), "target_path": self._ref(raw["target_path"])})
        if len({v["target_path"] for v in normalized}) != len(normalized):
            raise StateError("duplicate_output", "A submission cannot write the same target twice")
        return {"outputs": normalized, "summary": str(summary), "blockers": list(blockers)}

    def submit(self, run_id: str, task_id: str, token: str, *, outputs: Iterable = (),
               summary: str = "", blockers: Iterable[str] = ()) -> dict:
        with self._locked(run_id):
            state = self._read(run_id)
            if state.get("pending_commit"):
                self._complete_commit(state)
                state = self._read(run_id)
            task = self._task(state, task_id)
            request = self._request(state, task, outputs, summary, blockers)
            fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            previous = task.get("result")
            if previous and previous.get("token") == token:
                if previous["request_fingerprint"] != fingerprint:
                    raise ConflictError("idempotency_conflict", "The same submission token was reused with a different request")
                return {**_json_copy(previous), "idempotent": True}
            task = self._authorized(state, task_id, token)
            if request["blockers"]:
                if request["outputs"]:
                    raise StateError("blocked_with_outputs", "Submit blockers separately; do not promote incomplete outputs")
                task.update(status="blocked", blockers=request["blockers"], last_error={"code": "worker_blocked", "summary": summary})
                self._save(state)
                return {"status": "blocked", "task_id": task_id, "blockers": request["blockers"]}
            self._check_input_versions(task)
            transaction_id = secrets.token_hex(16)
            transaction_dir = self._run_dir(run_id) / "_transactions" / transaction_id
            entries = []
            try:
                for index, item in enumerate(request["outputs"]):
                    staged = Path(item["staged_path"])
                    self._check_components(staged)
                    source_version = file_version(staged)
                    if source_version is None:
                        raise StateError("missing_output", f"Staged output is missing: {staged}")
                    target = self._path(item["target_path"])
                    self._validate_target(state, target)
                    baseline = self._allowed_baseline(task, item["target_path"])
                    if file_version(target) != baseline:
                        raise ConflictError("write_conflict", f"Output target changed since dispatch: {item['target_path']}")
                    prepared = transaction_dir / f"new-{index}"
                    durable_copy(staged, prepared)
                    if file_version(prepared) != source_version:
                        raise ConflictError("staging_changed", "Worker changed its output while submitting")
                    backup = None
                    if baseline is not None:
                        backup = transaction_dir / f"old-{index}"
                        durable_copy(target, backup)
                        if file_version(backup) != baseline:
                            raise ConflictError("write_conflict", "Output target changed during preparation")
                    entries.append({"target_path": item["target_path"], "baseline": baseline,
                                    "version": source_version, "prepared": str(prepared),
                                    "backup": str(backup) if backup else None})
            except BaseException:
                if transaction_dir.is_dir():
                    shutil.rmtree(transaction_dir)
                raise
            try:
                self._check_input_versions(task)
            except Exception:
                if transaction_dir.is_dir():
                    shutil.rmtree(transaction_dir)
                raise
            state["pending_commit"] = {"id": transaction_id, "task_id": task_id,
                "token": token, "epoch": state["epoch"], "attempt": task["attempt"],
                "request_fingerprint": fingerprint, "summary": request["summary"],
                "entries": entries, "transaction_dir": str(transaction_dir),
                "staging_dir": task["dispatch"]["staging_dir"], "prepared_at": _now()}
            self._save(state)
            result = self._complete_commit(state)
            return {**result, "idempotent": False}

    def _allowed_baseline(self, task: dict, reference: str) -> dict | None:
        writes = task["dispatch"]["write_versions"]
        if reference in writes:
            return writes[reference]
        path = self._path(reference)
        for scope in task["allowed_write_roots"]:
            root = self._path(scope["path"])
            if scope["kind"] == "directory" and path != root and path.is_relative_to(root):
                return None  # Directory grants never authorize replacing existing files.
        raise StateError("outside_write_scope", f"Output is not in an allowed write scope: {reference}")

    def _check_input_versions(self, task: dict) -> None:
        for reference, expected in task["dispatch"]["input_versions"].items():
            if self._input_version(reference, expected) != expected:
                raise ConflictError("input_conflict", f"Input changed since dispatch: {reference}")

    def _complete_commit(self, state: dict) -> dict:
        transaction = state["pending_commit"]
        task = state["tasks"][transaction["task_id"]]
        if (state["lifecycle"] != "active" or transaction["epoch"] != state["epoch"]
                or task["status"] != "running" or task["dispatch"]["token"] != transaction["token"]):
            raise ConflictError("commit_fenced", "Pending commit is no longer authorized; explicit recovery is required")
        try:
            # Inputs that this transaction intentionally replaces may now have
            # either their old or newly committed version during crash recovery.
            replacement_versions = {item["target_path"]: item["version"] for item in transaction["entries"]}
            for reference, expected in task["dispatch"]["input_versions"].items():
                current = self._input_version(reference, expected)
                if (current != expected
                        and file_version(self._path(reference)) != replacement_versions.get(reference, object())):
                    raise ConflictError("commit_conflict", f"Input changed while recovering: {reference}")
            for item in transaction["entries"]:
                target = self._path(item["target_path"])
                current = file_version(target)
                if current == item["version"]:
                    continue
                if current != item["baseline"]:
                    raise ConflictError("commit_conflict", f"Preserving externally changed target: {item['target_path']}")
                prepared = Path(item["prepared"])
                self._check_components(prepared)
                if file_version(prepared) != item["version"]:
                    raise ConflictError("commit_corrupt", "Prepared commit data is missing or changed")
                replace_from_copy(prepared, target)
        except Exception as exc:
            transaction["error"] = {"code": getattr(exc, "code", "commit_io_error"), "message": str(exc)}
            self._save(state)
            raise
        outputs = []
        for item in transaction["entries"]:
            reference = item["target_path"]
            previous_version = state["artifacts"].get(reference, {}).get("version", 0)
            artifact = {"path": reference, **item["version"], "version": previous_version + 1,
                        "task_id": task["id"], "epoch": state["epoch"]}
            state["artifacts"][reference] = artifact
            outputs.append(artifact)
        result = {"status": "succeeded", "task_id": task["id"], "epoch": state["epoch"],
                  "attempt": transaction["attempt"], "token": transaction["token"],
                  "request_fingerprint": transaction["request_fingerprint"],
                  "outputs": outputs, "summary": transaction["summary"], "accepted_at": _now()}
        task.update(status="succeeded", result=result, blockers=[], last_error=None)
        changed = {entry["target_path"] for entry in transaction["entries"]}
        self._invalidate_readers(state, changed, task["id"])
        state["pending_commit"] = None
        state["cleanup_pending"].extend([transaction["transaction_dir"], transaction["staging_dir"]])
        self._save(state)
        self._cleanup(state)
        return _json_copy(result)

    def _invalidate_readers(self, state: dict, changed: set[str], producer: str) -> None:
        for task in state["tasks"].values():
            if task["id"] == producer or task["epoch"] != state["epoch"] or task["status"] != "succeeded":
                continue
            consumed = (task.get("dispatch") or {}).get("input_versions", {})
            own_outputs = {item["path"] for item in (task.get("result") or {}).get("outputs", [])}
            affected = {p for p in changed.intersection(consumed).difference(own_outputs)
                        if self._input_version(p, consumed[p]) != consumed[p]}
            if affected:
                task.update(status="blocked", blockers=[f"input_version_changed:{p}" for p in sorted(affected)])

    def _cleanup(self, state: dict) -> None:
        pending = state.get("cleanup_pending") or []
        if not pending:
            return
        allowed = [self._run_dir(state["run_id"]) / name for name in ("staging", "_transactions")]
        remaining = []
        for value in pending:
            path = Path(value)
            if not any(path != root and path.is_relative_to(root) for root in allowed):
                raise StateError("invalid_cleanup", "Cleanup may only remove declared private attempt/transaction directories")
            self._check_components(path)
            try:
                if path.is_dir():
                    shutil.rmtree(path)
            except OSError:
                remaining.append(value)
        state["cleanup_pending"] = remaining
        self._save(state)

    def _view(self, state: dict) -> dict:
        current = [task for task in state["tasks"].values() if task["epoch"] == state["epoch"]]
        ready = [task["id"] for task in current
                 if task["status"] in {"pending", "blocked", "failed"}
                 and not task["blockers"] and not self._dependency_blocks(state, task)
                 and task["attempt"] < task["max_attempts"]]
        if state["lifecycle"] != "active":
            status = state["lifecycle"]
        elif state.get("pending_commit"):
            status = "blocked"
        elif any(task["status"] == "running" for task in current):
            status = "running"
        elif any(task["status"] == "waiting_user" for task in current):
            status = "waiting_user"
        elif ready:
            status = "ready"
        elif not current:
            status = "planning"
        elif any(task["required"] and task["status"] != "succeeded" for task in current):
            status = "blocked"
        else:
            status = "awaiting_completion"
        result = _json_copy(state)
        result.update(status=status, ready_tasks=ready)
        return result

    def status(self, run_id: str) -> dict:
        with self._locked(run_id):
            return self._view(self._read(run_id))

    def task(self, run_id: str, task_id: str) -> dict:
        with self._locked(run_id):
            return _json_copy(self._task(self._read(run_id), task_id))

    def fail(self, run_id: str, task_id: str, token: str, *, reason: str,
             waiting_user: bool = False) -> dict:
        with self._locked(run_id):
            state = self._read(run_id)
            task = self._authorized(state, task_id, token)
            task.update(status="waiting_user" if waiting_user else "failed",
                        blockers=[reason] if waiting_user else [],
                        last_error={"code": "worker_failed", "message": reason})
            self._save(state)
            return _json_copy(task)

    def unblock(self, run_id: str, task_id: str, *, resolution: str) -> dict:
        if not resolution:
            raise StateError("missing_resolution", "Record why the task can continue")
        with self._locked(run_id):
            state = self._read(run_id)
            self._active(state)
            task = self._task(state, task_id)
            if task["epoch"] != state["epoch"] or task["status"] not in {"blocked", "waiting_user", "failed"}:
                raise StateError("not_blocked", "Only a current blocked/waiting/failed task can be released")
            task.update(status="pending", blockers=[], resolution=resolution)
            self._save(state)
            return _json_copy(task)

    def _fence(self, task: dict, status: str, reason: str) -> dict | None:
        dispatch = task.get("dispatch") or {}
        notification = None
        if task["status"] == "running":
            task["host_cancel_pending"] = True
            notification = {"task_id": task["id"], "host_id": dispatch.get("host_id"),
                            "epoch": task["epoch"], "attempt": task["attempt"], "reason": reason}
        task.update(status=status, blockers=[], last_error={"code": status, "message": reason})
        return notification

    def cancel(self, run_id: str, task_id: str | None = None, *, reason: str = "cancelled by supervisor") -> dict:
        with self._locked(run_id):
            state = self._read(run_id)
            if state["lifecycle"] != "active":
                return {"status": state["lifecycle"], "cancel_requests": []}
            if state.get("pending_commit"):
                self._abort_commit(state, reason="cancel requested during interrupted commit")
            notifications = []
            tasks = [self._task(state, task_id)] if task_id else list(state["tasks"].values())
            for task in tasks:
                if task["epoch"] == state["epoch"] and task["status"] in _LIVE:
                    note = self._fence(task, "cancelled", reason)
                    if note:
                        notifications.append(note)
            if task_id is None:
                state["lifecycle"] = "cancelled"
            self._save(state)
            return {"status": self._view(state)["status"], "cancel_requests": notifications}

    def revise(self, run_id: str, *, feedback: str, goal: str | dict | None = None) -> dict:
        if not feedback:
            raise StateError("missing_feedback", "A revision needs the user's requested change")
        with self._locked(run_id):
            state = self._read(run_id)
            if state.get("pending_commit"):
                raise StateError("commit_pending", "Recover or abort the pending commit before revising")
            notifications = []
            for task in state["tasks"].values():
                if task["epoch"] == state["epoch"] and task["status"] in _LIVE:
                    note = self._fence(task, "superseded", "new revision")
                    if note:
                        notifications.append(note)
            state["revisions"].append({"epoch": state["epoch"], "feedback": feedback,
                                       "base_artifacts": _json_copy(state["artifacts"]), "at": _now()})
            state["epoch"] += 1
            state["lifecycle"] = "active"
            state["completion"] = None
            if goal is not None:
                if not goal or not isinstance(goal, (str, dict)):
                    raise StateError("missing_goal", "A replacement goal must be nonempty")
                state["goal"] = _json_copy(goal)
            self._save(state)
            return {**self._view(state), "cancel_requests": notifications}

    def finish(self, run_id: str, *, completion: str | dict, deliverables: Iterable[str] | None = None,
               cancel_optional: bool = True) -> dict:
        if not completion or not isinstance(completion, (str, dict)):
            raise StateError("missing_completion", "The supervisor must explicitly confirm the user goal is met")
        with self._locked(run_id):
            state = self._read(run_id)
            self._active(state)
            tasks = [v for v in state["tasks"].values() if v["epoch"] == state["epoch"]]
            incomplete = [v["id"] for v in tasks if v["required"] and v["status"] != "succeeded"]
            if incomplete:
                raise StateError("unfinished_tasks", "Required tasks have not succeeded", tasks=incomplete)
            required_refs = set(state["deliverables"])
            required_refs.update(self._ref(p) for p in (deliverables or ()))
            for task in tasks:
                if task["required"]:
                    required_refs.update(task["deliverables"])
            versions = {}
            for reference in sorted(required_refs):
                version = file_version(self._path(reference))
                if version is None:
                    raise StateError("missing_deliverable", f"Required deliverable is missing: {reference}")
                expected = state["artifacts"].get(reference)
                if expected and _sha(expected) != _sha(version):
                    raise ConflictError("deliverable_conflict", f"Deliverable changed after submission: {reference}")
                versions[reference] = version
            # A review of a changed file is not a review of the delivered version.
            for task in tasks:
                if not task["required"] or task["status"] != "succeeded":
                    continue
                own_outputs = {v["path"] for v in (task.get("result") or {}).get("outputs", [])}
                for reference, expected in (task.get("dispatch") or {}).get("input_versions", {}).items():
                    if reference not in own_outputs and self._input_version(reference, expected) != expected:
                        raise ConflictError("review_version_conflict", f"A required task consumed an outdated input: {reference}")
            optional_live = [task for task in tasks if not task["required"] and task["status"] in _LIVE]
            if optional_live and not cancel_optional:
                raise StateError("optional_tasks_running", "Wait for or cancel outstanding optional tasks")
            notifications = []
            for task in optional_live:
                note = self._fence(task, "cancelled", "delivery epoch closed")
                if note:
                    notifications.append(note)
            state["lifecycle"] = "completed"
            state["completion"] = {"statement": _json_copy(completion), "deliverables": versions,
                                   "epoch": state["epoch"], "at": _now()}
            self._save(state)
            # No blanket rmtree(run): only private attempts known to this epoch.
            for task in tasks:
                stage = (task.get("dispatch") or {}).get("staging_dir")
                if stage and task["status"] in _TERMINAL and not task.get("host_cancel_pending"):
                    state["cleanup_pending"].append(stage)
            self._save(state)
            self._cleanup(state)
            return {**self._view(state), "cancel_requests": notifications}

    def _abort_commit(self, state: dict, *, reason: str) -> dict:
        transaction = state.get("pending_commit")
        if not transaction:
            return {"status": "no_pending_commit"}
        conflicts = []
        for item in reversed(transaction["entries"]):
            target = self._path(item["target_path"])
            current = file_version(target)
            if current == item["baseline"]:
                continue
            if current != item["version"]:
                conflicts.append(item["target_path"])
                continue  # Never erase a user's edit while aborting.
            if item["backup"]:
                backup = Path(item["backup"])
                self._check_components(backup)
                if file_version(backup) != item["baseline"]:
                    raise ConflictError("rollback_corrupt", "Cannot restore a missing/changed rollback copy")
                replace_from_copy(backup, target)
            else:
                target.unlink()
        task = state["tasks"][transaction["task_id"]]
        task.update(status="failed", last_error={"code": "commit_aborted", "message": reason,
                                                 "preserved_external_changes": conflicts}, blockers=[])
        state["pending_commit"] = None
        state["cleanup_pending"].append(transaction["transaction_dir"])
        self._save(state)
        self._cleanup(state)
        return {"status": "commit_aborted", "preserved_external_changes": conflicts}

    def resume(self, run_id: str, *, host_states: dict[str, str] | None = None,
               abort_conflict: bool = False) -> dict:
        """Reconcile, never assume an unknown host is dead or repeat its effects.

        host_states maps recorded host execution IDs (or unbound task IDs) to running/completed/lost/
        failed/cancelled. Completed means its result still needs submit(); it is
        not a substitute for a validated result. Unknown hosts remain in-flight.
        """
        with self._locked(run_id):
            state = self._read(run_id)
            recovery = None
            if state.get("pending_commit"):
                recovery = self._abort_commit(state, reason="explicit recovery abort") if abort_conflict else self._complete_commit(state)
                state = self._read(run_id)
            self._cleanup(state)
            awaiting = []
            for task in state["tasks"].values():
                host_id = (task.get("dispatch") or {}).get("host_id")
                observed = (host_states or {}).get(host_id or task["id"], "unknown")
                if task.get("host_cancel_pending"):
                    if observed in {"lost", "failed", "cancelled", "completed"}:
                        task["host_cancel_pending"] = False
                        state["cleanup_pending"].append(task["dispatch"]["staging_dir"])
                    else:
                        awaiting.append({"task_id": task["id"], "host_id": host_id,
                                         "observed": observed, "action": "cancel_host"})
                    continue
                if task["status"] != "running" or task["epoch"] != state["epoch"]:
                    continue
                if observed in {"lost", "failed", "cancelled"}:
                    task.update(status="failed", blockers=[], last_error={"code": "host_" + observed,
                                "message": "Host execution ended without an accepted submission"})
                elif observed not in {"running", "completed", "unknown"}:
                    raise StateError("invalid_host_state", f"Unknown host state: {observed}")
                else:
                    awaiting.append({"task_id": task["id"], "host_id": host_id, "observed": observed,
                                     "action": "collect_result" if observed == "completed" else "reconcile_host"})
            self._save(state)
            self._cleanup(state)
            return {**self._view(state), "recovery": recovery, "awaiting_hosts": awaiting}
