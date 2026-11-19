"""Host shell entries delegate to native commands without implicit data access."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from textpicos.paths import ProjectPaths
from textpicos.runtime import Runtime
from textpicos.maintenance import hooks


SOURCE = Path(__file__).resolve().parents[1]


def environment(root):
    env = dict(os.environ, TEXTPICOS_ROOT=str(root), TEXTPICOS_PYTHON=sys.executable,
               PYTHONPATH=str(SOURCE / "src"), PYTHONDONTWRITEBYTECODE="1")
    for key in ("AI_WIKI_ROOT", "TEXTPICOS_AI_WIKI_ROOT", "TEXTPICOS_RUN_ID",
                "TEXTPICOS_MAINTENANCE_SCOPE"):
        env.pop(key, None)
    return env


@pytest.fixture
def spy_python(tmp_path):
    spy = tmp_path / "python-spy"
    spy.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        "print(json.dumps({'args':sys.argv[1:],'input':sys.stdin.read(),"
        "'root':os.environ.get('TEXTPICOS_ROOT'),"
        "'pythonpath':os.environ.get('PYTHONPATH')}))\n"
    )
    spy.chmod(0o755)
    return spy


@pytest.mark.parametrize("hook", [".claude/hooks/stop.sh", ".agents/hooks/stop.sh"])
def test_stop_hooks_delegate_payload_to_the_current_native_module(tmp_path, spy_python, hook):
    env = environment(tmp_path)
    env["TEXTPICOS_PYTHON"] = str(spy_python)
    payload = '{"session_id":"selected-session"}'
    result = subprocess.run(["bash", str(SOURCE / hook)], cwd=tmp_path, env=env,
                            input=payload, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["args"] == ["-m", "textpicos.maintenance.hooks", "stop"]
    assert observed["input"] == payload
    assert observed["root"] == str(tmp_path)
    assert observed["pythonpath"].split(os.pathsep)[0] == str(tmp_path / "src")


def test_stop_hook_only_reports_the_explicit_temporary_native_run(tmp_path):
    config = tmp_path / "config/system/paths.json"
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    Runtime(ProjectPaths.from_root(tmp_path)).create("selected", "Fixture planning")
    env = environment(tmp_path)
    script = str(SOURCE / ".claude/hooks/stop.sh")
    unbound = subprocess.run(["bash", script], cwd=tmp_path, env=env, input="{}",
                             text=True, capture_output=True, timeout=15)
    assert unbound.returncode == 0 and unbound.stdout == ""
    bound = subprocess.run(["bash", script], cwd=tmp_path, env=env,
                           input='{"run_id":"selected"}', text=True, capture_output=True, timeout=15)
    assert bound.returncode == 0, bound.stderr
    outcome = json.loads(bound.stdout)
    assert outcome["decision"] == "block"
    assert "selected is planning" in outcome["reason"]


def test_audit_shell_delegates_only_to_the_current_cli(tmp_path, spy_python):
    env = environment(tmp_path)
    env["TEXTPICOS_PYTHON"] = str(spy_python)
    result = subprocess.run(["bash", str(SOURCE / "scripts/audit.sh"), "--help"],
                            cwd=tmp_path, env=env, text=True, input="",
                            capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["args"] == [str(SOURCE / "scripts/textpicos.py"), "audit", "--help"]


def test_audit_rejects_the_retired_full_mode_before_running_an_audit(tmp_path):
    env = environment(tmp_path)
    env["TEXTPICOS_MAINTENANCE_SCOPE"] = "system"
    result = subprocess.run(["bash", str(SOURCE / "scripts/audit.sh"), "--legacy-full"],
                            cwd=tmp_path, env=env, text=True, capture_output=True, timeout=15)
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert not (tmp_path / "workspace").exists()


@pytest.mark.parametrize("system_scope", [False, True])
def test_retired_topic_sync_stops_before_external_access(tmp_path, system_scope):
    env = environment(tmp_path)
    if system_scope:
        env["TEXTPICOS_MAINTENANCE_SCOPE"] = "system"
        env["AI_WIKI_ROOT"] = str(tmp_path / "unopened-vault")
    result = subprocess.run(["bash", str(SOURCE / "src/textpicos/content/sync_topics.sh")],
                            cwd=tmp_path, env=env, text=True, capture_output=True, timeout=15)
    assert result.returncode == 2
    assert "TOPIC_SYNC_RETIRED" in result.stderr
    assert "scripts/topics.py" in result.stderr
    assert not (tmp_path / "unopened-vault").exists()
    assert not (tmp_path / "resources").exists()


@pytest.mark.parametrize("arguments", [["post-write"], ["unknown"], ["stop", "extra"]])
def test_hooks_reject_retired_or_unknown_actions_before_reading_payload(arguments, monkeypatch, capsys):
    monkeypatch.setenv("TEXTPICOS_MAINTENANCE_SCOPE", "system")
    class UnreadableInput:
        def read(self, *args):
            raise AssertionError("Retired action must not consume a hook payload")
    monkeypatch.setattr(sys, "stdin", UnreadableInput())
    assert hooks.main(arguments) == 2
    assert "stop or forbidden" in capsys.readouterr().err


