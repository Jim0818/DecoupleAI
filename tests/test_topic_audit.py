"""Mode-local account resources are audited without inspecting live content."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from textpicos.context import ContextError
from textpicos.maintenance.system_audit import _Audit, _capabilities, audit_system


def registry_fixture(tmp_path):
    files = ["agents/supervisor/SKILL.md", "agents/reviewer/SKILL.md",
             "config/accounts/sample/L1.md"]
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    return {
        "orchestration_mode": "supervisor",
        "roles": {
            "supervisor": {"entrypoint": files[0], "default_mode": "coordinate",
                           "modes": {"coordinate": {"account_files": ["L2.md"]}},
                           "account_files": ["L1.md"]},
            "reviewer": {"entrypoint": files[1], "default_mode": "review",
                         "modes": {"review": {}}, "independent_context": True},
        },
        "skills": {}, "accounts": {"sample": {"directory": "config/accounts/sample"}},
    }


def test_missing_mode_only_account_reference_is_audited(tmp_path):
    registry = registry_fixture(tmp_path)
    audit = _Audit(SimpleNamespace(root=tmp_path))
    assert not _capabilities(audit, registry)
    assert any("L2.md" in error for error in audit.errors)
    (tmp_path / "config/accounts/sample/L2.md").write_text("current scope")
    fresh = _Audit(SimpleNamespace(root=tmp_path))
    assert _capabilities(fresh, registry)


def test_invalid_mode_account_list_fails_even_without_accounts(tmp_path):
    registry = registry_fixture(tmp_path)
    registry["accounts"] = {}
    registry["roles"]["supervisor"]["modes"]["coordinate"]["account_files"] = "L2.md"
    with pytest.raises(ContextError):
        _capabilities(_Audit(SimpleNamespace(root=tmp_path)), registry)


def test_mode_reference_does_not_follow_protected_alias(tmp_path):
    registry = registry_fixture(tmp_path)
    link = tmp_path / "config/accounts/sample/L2.md"
    link.symlink_to(tmp_path / "articles/never-read.md")
    original = Path.lstat

    def guarded(path, *args, **kwargs):
        if "articles" in path.parts:
            raise AssertionError("Protected target metadata accessed")
        return original(path, *args, **kwargs)

    audit = _Audit(SimpleNamespace(root=tmp_path))
    with patch.object(Path, "lstat", guarded):
        assert not _capabilities(audit, registry)
    assert not any("Protected target metadata accessed" in error for error in audit.errors)


def test_native_runtime_uses_current_cli_without_requiring_legacy_entry(tmp_path):
    import json

    registry = registry_fixture(tmp_path)
    for name in ["AGENTS.md", "CLAUDE.md", "README.md", "GETTING_STARTED.md",
                 "scripts/audit.sh", "scripts/textpicos.py", "src/textpicos/cli.py",
                 "config/accounts/sample/L2.md"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pass\n")
    for directory in ["skills", "docs", "config/system"]:
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    settings = {
        "capabilities": registry,
        "paths": {"paths": {"runs": "workspace/runs", "articles": "articles"}},
        "runtime": {"default_mode": "supervisor", "host_adapter": "native",
                    "output_policy": "summary_and_refs", "automatic_publish": False},
    }
    for name, value in settings.items():
        (tmp_path / f"config/system/{name}.json").write_text(json.dumps(value))
    paths = SimpleNamespace(root=tmp_path, config=tmp_path / "config")
    result = audit_system(paths)
    assert result["ok"], result["errors"]
    assert not (tmp_path / "scripts/run_pipeline.sh").exists()
    (tmp_path / "scripts/textpicos.py").unlink()
    result = audit_system(paths)
    assert not result["ok"]
    assert any("scripts/textpicos.py" in error for error in result["errors"])
