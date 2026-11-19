"""Isolated regressions for current discovery and explicit legacy boundaries."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import URLError

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOT = ROOT / ".agents/skills/aihot-researcher"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = load_module("topic_aihot_fetch", HOT / "fetch.py")
strategy = load_module("topic_strategy", ROOT / "skills/kb-bridge/handlers/read_topic_strategy.py")


@pytest.fixture
def config():
    return json.loads((HOT / "config.json").read_text(encoding="utf-8"))


def page_opener(payload, calls):
    raw = json.dumps(payload).encode()

    def open_page(request, *, timeout):
        calls.append((request, timeout))
        return io.BytesIO(raw)

    return open_page


def one_item():
    return {"id": "release-1", "title": "A small useful tutorial",
            "url": "https://example.org/tutorial", "publishedAt": "2026-11-19T00:00:00Z",
            "summary": "Official task walkthrough", "source": "Example docs",
            "category": "tutorial", "final_score": 99.9}


def test_one_unscored_lead_is_success_without_minimum(config):
    calls = []
    outcome, code = fetch.fetch_page(config, opener=page_opener({"items": [one_item()]}, calls))
    assert code == 0 and outcome["status"] == "ok"
    assert len(outcome["items"]) == 1 and len(calls) == 1
    assert outcome["items"][0]["verification"] == "source_not_checked"
    assert "final_score" not in outcome["items"][0]
    assert calls[0][1] == config["fetch"]["timeout_seconds"]


def test_empty_page_is_success_without_retry_or_window_expansion(config):
    calls = []
    outcome, code = fetch.fetch_page(config, opener=page_opener({"items": [], "hasNext": False}, calls))
    assert code == 0 and outcome["status"] == "empty"
    assert outcome["count"] == 0 and len(calls) == 1
    assert outcome["request"]["window_hours"] == config["fetch"]["default_window_hours"]


def test_failed_source_is_not_empty_success(config):
    calls = []

    def unavailable(request, *, timeout):
        calls.append(request)
        raise URLError("unavailable source")

    outcome, code = fetch.fetch_page(config, opener=unavailable)
    assert code != 0 and outcome["status"] == "unavailable"
    assert outcome["error"] == "transport_error" and len(calls) == 1


@pytest.mark.parametrize("payload", [
    {}, {"items": "wrong"}, {"items": ["wrong"]},
    {"items": [{**one_item(), "url": "javascript:alert(1)"}]},
    {"items": [{**one_item(), "publishedAt": "not a date"}]},
    {"items": [], "hasNext": "false"},
])
def test_invalid_page_is_not_consumed_or_reported_empty(config, payload):
    outcome, code = fetch.fetch_page(config, opener=page_opener(payload, []))
    assert code != 0 and outcome["status"] == "invalid_response"
    assert outcome["items"] == []


def test_response_byte_budget_is_enforced(config):
    config["fetch"]["max_response_bytes"] = 20
    outcome, code = fetch.fetch_page(config, opener=page_opener({"items": [one_item()]}, []))
    assert code != 0 and outcome["status"] == "invalid_response"


def test_bad_fetch_argument_does_not_call_network(config):
    def forbidden(*args, **kwargs):
        raise AssertionError("Bad input must fail before a request")

    outcome, code = fetch.fetch_page(config, take=0, opener=forbidden)
    assert code != 0 and outcome["status"] == "invalid_config"


def test_retired_optimizer_help_needs_no_third_party_dependencies(tmp_path):
    result = subprocess.run([
        sys.executable, "-S", str(ROOT / "scripts/topic-optimizer/optimizer.py"), "--help",
    ], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0
    assert "research/discover" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_retired_optimizer_fails_instead_of_writing_empty_success(tmp_path):
    result = subprocess.run([
        sys.executable, "-S", str(ROOT / "scripts/topic-optimizer/optimizer.py"), "--account", "Example competitor",
    ], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    error = json.loads(result.stderr)
    assert error["error"] == "LEGACY_TOPIC_OPTIMIZER_RETIRED"
    assert error["replacement"]["mode"] == "discover"
    assert not result.stdout and list(tmp_path.iterdir()) == []


def test_current_strategy_is_explicitly_unverified_and_never_legacy():
    outcome, code = strategy.read_strategy({"account_id": "intellifuture"})
    assert code != 0 and outcome["status"] == "not_available"
    assert outcome["source_status"] == "not_read" and outcome["legacy_fallback"] is False
    assert [item["path"] for item in outcome["baseline_refs"]] == [
        "config/accounts/intellifuture/L1_identity.md", "config/accounts/intellifuture/L2_values.md",
    ]
    assert all(item["verification"] == "reference_only" for item in outcome["baseline_refs"])
    assert "TOP1" not in json.dumps(outcome)


def test_optional_strategy_degrades_honestly_without_guessing_account():
    outcome, code = strategy.read_strategy({"optional": True})
    assert code == 0 and outcome["status"] == "not_available"
    assert outcome["account_id"] is None and outcome["baseline_refs"] == []


@pytest.mark.parametrize("optional, exit_code", [(False, 2), (True, 0)])
def test_strategy_dispatcher_preserves_required_or_optional_failure(tmp_path, optional, exit_code):
    result = subprocess.run([
        sys.executable, "-S", str(ROOT / "skills/kb-bridge/dispatch.py"),
    ], cwd=tmp_path, input=json.dumps({
        "op": "read-topic-strategy", "account_id": "studio", "optional": optional,
    }), capture_output=True, text=True)
    assert result.returncode == exit_code
    assert json.loads(result.stdout)["status"] == "not_available"
    assert list(tmp_path.iterdir()) == []


def test_strategy_operation_has_no_file_or_receipt_side_effects(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("This handler must not probe files or write receipts")

    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({
        "optional": True, "account_id": "studio", "run_id": "not-a-vault-write",
    })))
    strategy.main()
    assert json.loads(capsys.readouterr().out)["source_status"] == "not_read"


def test_legacy_strategy_requires_explicit_mode_and_retains_provenance():
    result, code = strategy.read_strategy({"strategy_mode": "legacy_snapshot", "top_n": 1})
    assert code == 0 and len(result) == 1
    assert result[0]["cluster_id"] == "TOP1"
    assert result[0]["strategy_status"] == "historical_snapshot"
    assert result[0]["source_verified"] is False
    assert result[0]["policy_authority"] == "reference_only"


@pytest.mark.parametrize("payload", [
    {"account_id": "unknown"}, {"account_id": []}, {"optional": "false"},
    {"query": []}, {"top_n": True}, {"top_n": 0}, {"strategy_mode": "auto"}, {"strategy_mode": []},
])
def test_bad_strategy_input_is_rejected(payload):
    with pytest.raises(ValueError):
        strategy.read_strategy(payload)
