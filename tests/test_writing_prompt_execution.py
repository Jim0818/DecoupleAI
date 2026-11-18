"""Exercise actual writing payloads using isolated files, never user articles."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from textpicos.context import ContextError, assemble_context, context_prompt
from textpicos.host import prepare_dispatch
from textpicos.maintenance import eval_skill
from textpicos.paths import ProjectPaths
from textpicos.runtime import Runtime


def write(root, ref, text):
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def evaluation_project(tmp_path, monkeypatch):
    registry = {
        "orchestration_mode": "supervisor",
        "roles": {"writer": {
            "entrypoint": "agents/workers/writer/SKILL.md",
            "default_mode": "compose",
            "modes": {"compose": {}, "edit": {}},
            "required_skills": ["writing"], "default_skills": ["natural-prose"],
            "account_files": ["L1_identity.md"],
        }},
        "skills": {
            "writing": {"kind": "production", "entrypoint": "skills/writing/SKILL.md",
                        "mode_refs": {"edit": ["skills/writing/references/editing.md"]}},
            "natural-prose": {"kind": "production", "entrypoint": "skills/natural-prose/SKILL.md"},
        },
        "accounts": {"studio": {"directory": "config/accounts/studio"}},
    }
    write(tmp_path, "config/system/capabilities.json", json.dumps(registry))
    for ref in (
        "agents/workers/writer/SKILL.md", "skills/writing/SKILL.md",
        "skills/writing/references/editing.md", "skills/natural-prose/SKILL.md",
        "config/accounts/studio/L1_identity.md",
    ):
        write(tmp_path, ref, f"# Current method {ref}\n")
    write(tmp_path, "inputs/source.md", "REAL_SOURCE_BODY_SENTINEL")
    monkeypatch.setenv("TEXTPICOS_ROOT", str(tmp_path))
    monkeypatch.setenv("TEXTPICOS_MAINTENANCE_SCOPE", "system")
    return ProjectPaths.from_root(tmp_path)


def task():
    return {
        "role": "writer", "mode": "edit", "account_id": "studio",
        "goal": "修订提供的原稿，保留有效技术细节。",
        "input_refs": ["inputs/source.md"],
        "allowed_write_roots": ["outputs/result.md"],
    }


def test_evaluation_uses_production_context_and_keeps_judging_separate(evaluation_project):
    paths = evaluation_project
    expected = assemble_context(paths, task())
    result = eval_skill.prepare_evaluation(paths, task(), expectations=["HIDDEN_GRADING_SENTINEL"])
    assert result["context"] == expected
    assert result["prompt"] == context_prompt(expected)
    assert result["assessment"] == {"status": "not_run", "expectations": ["HIDDEN_GRADING_SENTINEL"]}
    assert "HIDDEN_GRADING_SENTINEL" not in result["prompt"]
    assert "REAL_SOURCE_BODY_SENTINEL" not in result["prompt"]
    assert result["execution_started"] is False
    assert any(item["id"] == "method:writing:0" for item in result["context"]["resources"])


def test_missing_production_method_cannot_be_replaced_by_full_legacy_skill(evaluation_project):
    paths = evaluation_project
    (paths.root / "skills/writing/references/editing.md").unlink()
    write(paths.root, "agents/legacy/decouple-writer/SKILL.md", "A complete old prompt")
    with pytest.raises(ContextError, match="Required method"):
        eval_skill.prepare_evaluation(paths, task())


def test_evaluation_keeps_structured_runtime_goal(evaluation_project):
    value = {**task(), "goal": {"request": "只改开头", "constraints": ["保留代码"]}}
    result = eval_skill.prepare_evaluation(evaluation_project, value)
    assert result["context"]["task"]["goal"] == value["goal"]


def test_actual_host_handoff_is_replayed_without_prompt_reconstruction(evaluation_project):
    paths = evaluation_project
    runtime = Runtime(paths)
    runtime.create("eval", "An isolated writing evaluation", metadata={"account_id": "studio"})
    runtime.add("eval", "write", **task())
    dispatch = prepare_dispatch(paths, runtime, "eval", "write")
    handoff = json.loads(Path(dispatch["handoff_path"]).read_text())
    result = eval_skill.prepare_handoff_evaluation(paths, dispatch["handoff_path"])
    assert result["prompt"] == handoff["prompt"]
    assert result["context"] == handoff["context"]
    preview = eval_skill.prepare_evaluation(paths, runtime.task("eval", "write"))
    assert preview["context"] == handoff["context"]
    assert handoff["prompt"].startswith(preview["prompt"])
    assert "natural-prose" in handoff["context"]["skill_ids"]
    assert "Execution boundary:" in result["prompt"]
    assert result["input_mode"] == "production_handoff"
    assert result["execution_started"] is False


def test_cases_keep_expected_answers_out_of_worker_prompt(evaluation_project):
    paths = evaluation_project
    cases = write(paths.root, "evaluation/cases.json", json.dumps({
        "skill_name": "writer", "evals": [{
            "id": "edit", "prompt": "Edit the source", "task": task(),
            "expectations": ["ASSESSOR_ONLY"], "expected_output": "EXPECTED_ONLY",
        }],
    }))
    result = eval_skill.evaluation_cases(paths, cases)["evals"][0]
    assert "ASSESSOR_ONLY" not in result["prompt"]
    assert "EXPECTED_ONLY" not in result["prompt"]
    assert result["assessment"]["expected_output"] == "EXPECTED_ONLY"


def test_current_cli_supports_role_mode_account_and_explicit_input(evaluation_project, capsys):
    assert eval_skill.main([
        "--role", "writer", "--mode", "edit", "--account", "studio",
        "--input", "inputs/source.md", "--goal", "Edit the supplied draft", "--json",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["context"]["mode"] == "edit"
    assert result["context"]["account_id"] == "studio"
    assert result["context"]["task"]["input_refs"][0]["path"].endswith("inputs/source.md")
    assert result["assessment"]["status"] == "not_run"


def test_validate_only_reports_structure_not_generation(evaluation_project, capsys):
    assert eval_skill.main(["--role", "writer", "--goal", "Explain supplied facts", "--validate-only"]) == 0
    assert "模型行为尚未验证" in capsys.readouterr().out


def test_maintenance_input_boundary_matches_production(evaluation_project):
    value = {**task(), "input_refs": ["articles/DO_NOT_PROBE.md"]}
    with pytest.raises(ValueError, match="excluded"):
        eval_skill.prepare_evaluation(evaluation_project, value)


def test_task_file_and_invalid_mode_are_checked(evaluation_project, capsys):
    paths = evaluation_project
    write(paths.root, "evaluation/task.json", json.dumps(task()))
    assert eval_skill.main(["--task", "evaluation/task.json", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["context"]["role"] == "writer"
    assert eval_skill.main(["--role", "writer", "--mode", "legacy", "--goal", "Edit"]) == 1
    assert "Unknown mode" in capsys.readouterr().err


def test_legacy_rule_inspection_is_not_presented_as_production(evaluation_project):
    paths = evaluation_project
    agent_dir = paths.root / "agents/legacy/example"
    write(paths.root, "agents/legacy/example/SKILL.md", "Old method")
    cases = write(paths.root, "agents/legacy/example/evaluation/quality-cases.json", json.dumps({
        "skill_name": "old", "evals": [{"id": "legacy", "prompt": "Old task", "expectations": ["Check"]}],
    }))
    rendered = eval_skill.render_worksheet(agent_dir, cases)
    assert "历史规则检查" in rendered
    assert "不能作为当前生产效果验收" in rendered
    assert "加载上面 SKILL.md 作为" not in rendered


@pytest.fixture
def refiner_project(tmp_path, monkeypatch):
    from textpicos.legacy import refiner_runner
    from textpicos.legacy.engine import dispatch as legacy_dispatch

    monkeypatch.setattr(refiner_runner, "REPO", tmp_path)
    monkeypatch.setattr(refiner_runner, "PENDING", tmp_path / "articles/pending")
    monkeypatch.setattr(refiner_runner, "SKILL", tmp_path / "agents/decouple-refiner/SKILL.md")
    monkeypatch.setattr(legacy_dispatch, "REPO", tmp_path)
    write(tmp_path, "agents/decouple-refiner/SKILL.md", "FULL_LEGACY_FALLBACK_SENTINEL")
    write(tmp_path, "agents/decouple-refiner/runtime-v4_2.md", "# Runtime\nLOCAL_REPAIR_METHOD_SENTINEL")
    write(tmp_path, "skills/natural-prose/SKILL.md", "# Shared\nSHARED_PROSE_METHOD_SENTINEL")
    original = "---\ntitle: Test\n---\n# Test\n\nKeep this exact supplied body.\n"
    write(tmp_path, "articles/pending/studio/test.md", original)
    write(tmp_path, "run/input.json", json.dumps({
        "typed_input_ref": "run/typed.json",
        "semantic_refs": {"article_path": "articles/pending/studio/test.md"},
    }))
    write(tmp_path, "run/typed.json", json.dumps({
        "body_review_report_ref": "run/review.json", "allowed_finding_ids": ["BR-1"],
    }))
    write(tmp_path, "run/review.json", json.dumps({
        "verdict": "REPAIR", "findings": [{"id": "BR-1", "problem": "An unclear transition"}],
    }))
    envelope = {
        "phase": "V42_REFINER", "model_route": "highest_quality_text", "tool_permissions": [],
        "account_id": "studio", "context": {"writing_policy_version": "v4_2_content_first"},
        "input_bundle_ref": "run/input.json", "staging_dir": "run/staging",
    }
    path = write(tmp_path, "run/dispatch.json", json.dumps(envelope))
    return refiner_runner, path, original


def test_refiner_final_payload_contains_actual_shared_method(refiner_project):
    runner, path, original = refiner_project
    manifest = runner.prepare(path)
    payload = json.loads((runner.REPO / manifest["payload_path"]).read_text())
    assert "LOCAL_REPAIR_METHOD_SENTINEL" in payload["system"]
    assert "SHARED_PROSE_METHOD_SENTINEL" in payload["system"]
    assert "FULL_LEGACY_FALLBACK_SENTINEL" not in payload["system"]
    assert json.loads(payload["user"])["article_markdown"] == original
    assert manifest["system_resource_refs"] == [
        "agents/decouple-refiner/runtime-v4_2.md", "skills/natural-prose/SKILL.md",
    ]


@pytest.mark.parametrize("ref", ["agents/decouple-refiner/runtime-v4_2.md", "skills/natural-prose/SKILL.md"])
def test_refiner_missing_required_method_fails_without_old_skill_fallback(refiner_project, ref):
    runner, path, _ = refiner_project
    (runner.REPO / ref).unlink()
    with pytest.raises(runner.RefinerError, match="missing required skill resources"):
        runner.prepare(path)
    assert not (runner.REPO / "run/staging/llm-payload.json").exists()


def test_refiner_alias_does_not_duplicate_method(refiner_project):
    runner, path, _ = refiner_project
    alias = runner.REPO / "agents/decouple-refiner/capsules/core.md"
    alias.parent.mkdir()
    alias.symlink_to("../runtime-v4_2.md")
    manifest = runner.prepare(path)
    payload = json.loads((runner.REPO / manifest["payload_path"]).read_text())
    assert payload["system"].count("LOCAL_REPAIR_METHOD_SENTINEL") == 1


def test_refiner_empty_resource_is_not_successful_loading(refiner_project):
    runner, path, _ = refiner_project
    (runner.REPO / "skills/natural-prose/SKILL.md").write_text("")
    with pytest.raises(runner.RefinerError, match="empty"):
        runner.prepare(path)


def test_refiner_does_not_infer_a_missing_policy_version(refiner_project):
    runner, path, _ = refiner_project
    envelope = json.loads(path.read_text())
    envelope.pop("context")
    path.write_text(json.dumps(envelope))
    with pytest.raises(runner.RefinerError, match="explicit v4_2_content_first"):
        runner.prepare(path)
