"""Read-only system audit: explicit configuration and code, never content trees.

This is not an article/publication gate. No production run, external vault,
resource crawler, legacy audit, or recursive run discovery is invoked.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import stat
from typing import Callable


_PROTECTED = "未命名文件夹---这里内容不要动"
_EXCLUDED = {"articles", "artifacts", "resources", "archive", "node_modules", ".git"}
_SYSTEM_TOPS = {"src", "scripts", "config", "agents", "skills", "docs", "tests",
                "workflows", "runbooks", "platforms", "ai-as-me", ".agents", ".claude"}
_ROOT_FILES = {"AGENTS.md", "CLAUDE.md", "README.md", "GETTING_STARTED.md",
               "CHANGELOG.md", "VIDEO-MIGRATED.md", "package.json", "package-lock.json",
               "pytest.ini", "pyproject.toml", "requirements.txt"}


class ScopeError(ValueError):
    pass


class _Audit:
    def __init__(self, paths):
        self.paths = paths
        self.root = Path(os.path.abspath(paths.root))
        self.checks = []
        self.errors = []
        self.warnings = []

    def record(self, name: str, detail: str, *, status: str = "pass") -> None:
        self.checks.append({"id": name, "status": status, "detail": detail})
        if status == "fail":
            self.errors.append(f"{name}: {detail}")
        elif status == "warning":
            self.warnings.append(f"{name}: {detail}")

    def run(self, name: str, operation: Callable):
        previous_errors = len(self.errors)
        try:
            value = operation()
        except Exception as exc:
            self.record(name, f"{type(exc).__name__}: {exc}", status="fail")
            return None
        self.record(name, "See failed detail checks" if len(self.errors) > previous_errors else "checked",
                    status="fail" if len(self.errors) > previous_errors else "pass")
        return value

    def lexical(self, value: str | Path, *, receipt=False) -> Path:
        p = Path(value)
        p = Path(os.path.abspath(p if p.is_absolute() else self.root / p))
        try:
            relative = p.relative_to(self.root)
        except ValueError as exc:
            raise ScopeError("Reference leaves the project; external locations are not inspected") from exc
        parts = relative.parts
        if not parts or any(part.casefold() in _EXCLUDED or part == _PROTECTED for part in parts):
            raise ScopeError("Reference is outside the system-only audit scope")
        migration_receipt = receipt and len(parts) >= 3 and parts[:2] == ("workspace", "migrations")
        if not migration_receipt and parts[0] not in _SYSTEM_TOPS and relative.as_posix() not in _ROOT_FILES:
            raise ScopeError(f"Not an allowed system location: {relative}")
        return p

    def resolve(self, value: str | Path, *, receipt=False) -> Path:
        """Resolve each link lexically before touching its target."""
        pending = self.lexical(value, receipt=receipt)
        for _ in range(32):
            current = self.root
            parts = pending.relative_to(self.root).parts
            restarted = False
            for index, part in enumerate(parts):
                current /= part
                try:
                    info = current.lstat()
                except FileNotFoundError:
                    raise FileNotFoundError(str(pending.relative_to(self.root))) from None
                if stat.S_ISLNK(info.st_mode):
                    raw = Path(os.readlink(current))
                    target = raw if raw.is_absolute() else current.parent / raw
                    pending = self.lexical(target.joinpath(*parts[index + 1:]), receipt=receipt)
                    restarted = True
                    break
            if not restarted:
                return pending
        raise ScopeError("Too many symbolic links in a system reference")

    def file(self, value: str | Path, *, receipt=False) -> Path:
        p = self.resolve(value, receipt=receipt)
        if not p.is_file():
            raise ValueError(f"Required file is not a regular file: {value}")
        return p

    def directory(self, value: str | Path) -> Path:
        p = self.resolve(value)
        if not p.is_dir():
            raise ValueError(f"Required directory is missing: {value}")
        return p

    def json(self, value: str | Path, *, receipt=False):
        return json.loads(self.file(value, receipt=receipt).read_text(encoding="utf-8"))


def _expect(condition, detail):
    if not condition:
        raise ValueError(detail)


def _path_settings(audit: _Audit, data: dict) -> None:
    values = data.get("paths", data)
    _expect(isinstance(values, dict), "paths must be an object")
    def path(key, default):
        value = Path(values.get(key, default))
        return Path(os.path.abspath(value if value.is_absolute() else audit.root / value))
    runs = path("runs", "workspace/runs")
    legacy = path("legacy_runs", "artifacts")
    _expect(runs != legacy and runs not in legacy.parents and legacy not in runs.parents,
            "New and legacy run roots must be distinct and non-overlapping")
    for location in (runs, legacy):
        _expect(location.is_relative_to(audit.root), "Run roots must stay within the project")
    # Compare strings only. The article directory is not stat'ed or opened.
    _expect(path("articles", "articles") == audit.root / "articles", "Article root must retain its original location")
    for key, default in (("agents", "agents"), ("skills", "skills"), ("config", "config"), ("docs", "docs")):
        audit.directory(path(key, default))


def _runtime_settings(data: dict) -> None:
    expected = {"default_mode": "supervisor",
                "host_adapter": "native", "output_policy": "summary_and_refs", "automatic_publish": False}
    for key, value in expected.items():
        _expect(data.get(key) == value and (key != "automatic_publish" or data.get(key) is False),
                f"{key} must be {value!r}")
    # Older installations may still declare an explicit compatibility entry.
    # A native-only installation need not restore that removed capability.
    if "legacy_new_runs" in data:
        _expect(data["legacy_new_runs"] == "explicit", "legacy_new_runs must be 'explicit' when declared")
    for key in ("required_phases", "mandatory_stages", "default_phase_graph"):
        _expect(not data.get(key), f"Default supervisor runtime must not impose {key}")


def _registered_ref(audit: _Audit, ref, name: str) -> bool:
    if isinstance(ref, str):
        path, required = ref, True
    elif isinstance(ref, dict) and isinstance(ref.get("path"), str):
        path, required = ref["path"], ref.get("required", True)
    else:
        audit.record(name, "Reference must be a path or {path, required}", status="fail")
        return False
    try:
        audit.file(path)
    except Exception as exc:
        audit.record(name, str(exc), status="fail" if required else "warning")
        return False
    return True


def _capabilities(audit: _Audit, data: dict) -> bool:
    from textpicos.context import account_file_names

    initial = len(audit.errors)
    _expect(data.get("orchestration_mode") == "supervisor", "Capability registry must select supervisor orchestration")
    roles, skills = data.get("roles"), data.get("skills")
    _expect(isinstance(roles, dict) and isinstance(skills, dict), "roles and skills must be mappings")
    _expect("supervisor" in roles and "reviewer" in roles, "Supervisor and independent review capabilities are required")
    sources = {}
    account_names = set()
    for role_id, role in roles.items():
        name = f"role:{role_id}"
        _expect(isinstance(role, dict), f"{name} must be a mapping")
        account_names.update(account_file_names(role, name))
        if _registered_ref(audit, role.get("entrypoint"), name):
            canonical = str(audit.file(role["entrypoint"]))
            if canonical in sources:
                audit.record(name, f"Role source duplicates {sources[canonical]}", status="fail")
            sources[canonical] = role_id
        modes = role.get("modes", {})
        if not isinstance(modes, dict) or role.get("default_mode") not in modes:
            audit.record(name, "Default mode is not registered", status="fail")
            continue
        for mode_name, mode in modes.items():
            _expect(isinstance(mode, dict), f"{name}:{mode_name} must be a mapping")
            account_names.update(account_file_names(mode, f"{name}:{mode_name}"))
            selected = [*role.get("required_skills", []), *mode.get("default_skills", role.get("default_skills", []))]
            for skill in selected:
                if skill not in skills:
                    audit.record(name, f"Unknown skill in {mode_name}: {skill}", status="fail")
            for ref in [*role.get("policy_refs", []), *mode.get("policy_refs", [])]:
                _registered_ref(audit, ref, name + ":policy")
        if role_id == "reviewer" and role.get("independent_context") is not True:
            audit.record(name, "Independent review must request separate context", status="fail")
    skill_sources = {}
    for skill_id, skill in skills.items():
        _expect(skill.get("kind") == "production", f"Default skill {skill_id} is not a production method")
        if _registered_ref(audit, skill.get("entrypoint"), f"skill:{skill_id}"):
            canonical = str(audit.file(skill["entrypoint"]))
            if canonical in skill_sources:
                audit.record(f"skill:{skill_id}", f"Production method duplicates {skill_sources[canonical]}", status="fail")
            skill_sources[canonical] = skill_id
        for mode, refs in skill.get("mode_refs", {}).items():
            for ref in refs:
                _registered_ref(audit, ref, f"skill:{skill_id}:{mode}")
    for account_id, account in data.get("accounts", {}).items():
        base = audit.directory(account["directory"])
        for filename in sorted(account_names):
            _registered_ref(audit, str(base / filename), f"account:{account_id}")
    for ident, item in data.get("optional_capabilities", {}).items():
        if item.get("default_loaded") is not False:
            audit.record(f"optional:{ident}", "Optional or maintenance capability is loaded by default", status="fail")
        try:
            directory = audit.directory(item["path"])
            if item.get("structure") == "skill":
                audit.file(directory / "SKILL.md")
        except Exception as exc:
            audit.record(f"optional:{ident}", f"Unavailable on request: {exc}", status="warning")
    maintenance = data.get("maintenance", {})
    if maintenance and maintenance.get("default_loaded") is not False:
        audit.record("maintenance", "Maintenance methods must not be default context", status="fail")
    for key, value in maintenance.items():
        if isinstance(value, str):
            _registered_ref(audit, value, f"maintenance:{key}")
    for ident, item in data.get("host_entries", {}).items():
        source = audit.directory(item["source"])
        for host, path in item.get("names", {}).items():
            target = audit.directory(path)
            if target != source:
                audit.record(f"host:{host}:{ident}", "Host entry has a separate writable source; use a verified canonical link", status="fail")
    for ident, item in data.get("legacy_roles", {}).items():
        if item.get("default_loaded") is not False:
            audit.record(f"legacy:{ident}", "Legacy role cannot be default-loaded", status="fail")
        canonical = audit.directory(item["source"])
        compatibility = audit.directory(item["compatible_path"])
        kind = item.get("compatibility_kind", "directory_link")
        if kind == "entry_links":
            # Some old parents contain a protected archive and must stay in
            # place. Check only declared active entries, never that archive.
            for filename in dict.fromkeys(["SKILL.md", *item.get("compatibility_files", [])]):
                _expect(isinstance(filename, str) and not Path(filename).is_absolute()
                        and ".." not in Path(filename).parts, "Compatibility entries must be relative files")
                _expect(audit.file(canonical / filename) == audit.file(compatibility / filename),
                        f"Legacy compatibility entry duplicates its source: {ident}/{filename}")
        else:
            _expect(kind == "directory_link", f"Unknown compatibility kind: {ident}/{kind}")
            _expect(canonical == compatibility, f"Legacy compatibility path duplicates its source: {ident}")
    audit.record("capability-references", f"Checked {len(roles)} role and {len(skills)} production-skill definitions")
    return len(audit.errors) == initial


def _assembled_contexts(audit: _Audit, capabilities: dict, assembler: Callable) -> None:
    for ident, role in capabilities["roles"].items():
        result = assembler(audit.paths, {}, role=ident, mode=role["default_mode"], account_id=None,
                           exclusions=[audit.root / value for value in ("articles", "artifacts", "resources", "archive")])
        _expect(result.get("load_policy", {}).get("execution_started") is False, "Context audit must not start execution")
        resources = result.get("resources", [])
        _expect(resources, f"Empty default context for {ident}")
        for resource in resources:
            audit.file(resource.get("resolved_path") or resource["path"])
        if ident == "reviewer":
            _expect(result.get("requires_independent_context") is True, "Reviewer assembly lost context isolation requirement")
        audit.record(f"assembly:{ident}", f"{len(resources)} actual resources available; execution not started")


def _source_registry(audit: _Audit) -> None:
    ref = "config/system/source-registry.yaml"
    try:
        registry = audit.file(ref)
    except FileNotFoundError:
        audit.record("source-registry", "No optional historical source registry at its canonical location", status="warning")
        return
    import yaml
    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    sources = data.get("sources", {})
    _expect(isinstance(sources, dict), "Source registry must contain a sources mapping")
    source_types = data.get("source_types", {})
    _expect(isinstance(source_types, dict), "source_types must be a mapping")
    _expect(set(source_types).issubset(sources), "source_types contains an unknown source key")
    _expect(all(kind in {"file", "directory"} for kind in source_types.values()), "Unknown source type")
    checked, deferred = 0, []
    for key, value in sources.items():
        if not isinstance(value, str):
            raise ValueError(f"Source registry value is not a string: {key}")
        path = value.split("#", 1)[0]
        if any(mark in path for mark in ("{", "}", "~", "://")):
            deferred.append(key)
            continue
        try:
            audit.lexical(path)
        except ScopeError:
            deferred.append(key)
            continue
        if source_types.get(key, "file") == "directory":
            audit.directory(path)  # Check this directory only; never discover its contents.
        else:
            audit.file(path)
        checked += 1
    audit.record("source-registry:local", f"Verified {checked} concrete system references (files or declared directories)")
    if deferred:
        audit.record("source-registry:scope", f"Not opened (templates, historical data or external references): {', '.join(deferred)}", status="warning")


def _system_syntax(audit: _Audit) -> None:
    root = audit.directory("src/textpicos")
    checked = 0
    skipped = _EXCLUDED | {"__pycache__", ".venv", "venv", "_deps", "yaml", "worktrees"}
    pending = [root]
    while pending:
        base = pending.pop()
        with os.scandir(base) as entries:
            for entry in entries:
                # Inspect the name before even asking for entry metadata. Unlike
                # os.walk, this also avoids classifying/following directory links.
                if entry.name.casefold() in skipped or entry.name == _PROTECTED:
                    continue
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(Path(base) / entry.name)
                elif stat.S_ISREG(info.st_mode) and entry.name.endswith(".py"):
                    path = audit.file(Path(base) / entry.name)
                    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                    checked += 1
    _expect(checked, "No package implementation found")
    audit.record("package-syntax:files", f"Parsed {checked} Python source files without importing/executing them")


def _migration_receipt(audit: _Audit) -> None:
    ref = "workspace/migrations/20261118-supervisor/resource-migration.json"
    try:
        path = audit.file(ref, receipt=True)
    except FileNotFoundError:
        audit.record("migration-receipt", "No historical migration receipt required for normal use")
        return
    receipt = json.loads(path.read_text(encoding="utf-8"))
    _expect(receipt.get("kind") == "resource-migration", "Unknown migration receipt kind")
    _expect(receipt.get("status") in {"completed", "rolled_back"}, "Resource migration is incomplete")
    from .migrate_resources import default_moves
    allowlist = {move.source: move.target for move in default_moves()}
    for source, item in receipt.get("entries", {}).items():
        _expect(allowlist.get(source) == item.get("target"), "Receipt contains an unapproved resource migration")
        _expect(item.get("status") in {"verified", "rolled_back"}, f"Incomplete resource entry: {source}")
    audit.record("migration-receipt:state", "Historical journal consistent; resource contents and source directories were not opened")


def audit_system(paths, *, assembler: Callable | None = None) -> dict:
    audit = _Audit(paths)
    path_config = audit.run("paths-json", lambda: audit.json("config/system/paths.json"))
    if path_config is not None:
        audit.run("path-boundaries", lambda: _path_settings(audit, path_config))
    runtime = audit.run("runtime-json", lambda: audit.json("config/system/runtime.json"))
    if runtime is not None:
        audit.run("supervisor-defaults", lambda: _runtime_settings(runtime))
    capabilities = audit.run("capabilities-json", lambda: audit.json("config/system/capabilities.json"))
    if capabilities is not None:
        valid = audit.run("capability-definitions", lambda: _capabilities(audit, capabilities))
        if valid:
            if assembler is None:
                try:
                    from ..context import assemble_context
                    assembler = assemble_context
                except Exception as exc:
                    audit.record("context-loader", str(exc), status="fail")
            if assembler is not None:
                audit.run("default-context-assembly", lambda: _assembled_contexts(audit, capabilities, assembler))
    cli_entry = ("scripts/run_pipeline.sh" if runtime and "legacy_new_runs" in runtime
                 else "scripts/textpicos.py")
    for entry in ("AGENTS.md", "CLAUDE.md", "README.md", "GETTING_STARTED.md",
                  "scripts/audit.sh", cli_entry, "src/textpicos/cli.py"):
        audit.run(f"entry:{entry}", lambda entry=entry: audit.file(entry))
    audit.run("source-registry", lambda: _source_registry(audit))
    audit.run("package-syntax", lambda: _system_syntax(audit))
    audit.run("optional-migration-journal", lambda: _migration_receipt(audit))
    return {"ok": not audit.errors, "scope": "system", "checks": audit.checks,
            "errors": audit.errors, "warnings": audit.warnings,
            "exclusions": ["articles", "artifacts", "resources", "archive", "external vaults"],
            "run_data_inspected": False, "production_executed": False,
            "run_root_check": "configuration only; no recursive run discovery"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", "--root", type=Path)
    args = parser.parse_args(argv)
    from ..paths import ProjectPaths
    paths = ProjectPaths.from_root(args.repo) if args.repo else ProjectPaths.discover()
    result = audit_system(paths)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
