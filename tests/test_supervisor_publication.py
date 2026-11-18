from pathlib import Path
import io
import json
import os
import re
import shlex
import subprocess
import sys
import pytest
from textpicos.paths import ProjectPaths
from textpicos.runtime import Runtime
from textpicos.content import article_contract as contract
from textpicos.content import publication
from textpicos.maintenance import hooks


@pytest.fixture
def native_article(tmp_path, monkeypatch):
    source_policy = ProjectPaths.discover().root / "config/policies/forbidden-words.yaml"
    policy = tmp_path / "workflows/governance/forbidden-words.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_bytes(source_policy.read_bytes())
    monkeypatch.setattr(contract, "REPO", tmp_path)
    monkeypatch.setattr(contract, "PENDING", tmp_path / "articles/pending")
    monkeypatch.setattr(contract, "VISUALS", tmp_path / "articles/pending/visuals")
    path = tmp_path / "articles/pending/studio/classic-python/2026-11-18-check-columns_studio.md"
    path.parent.mkdir(parents=True)
    text = '''---
title: 读 CSV 前先检查列名
slug: check-columns
run_id: publication-test
account_id: studio
column: classic-python
date: "2026-11-18"
tags: [Python]
published_to: []
writing_policy_version: v4_2_content_first
---
# 读 CSV 前先检查列名

先读取表头，再检查 order_id 和 amount 是否存在。缺列时报告缺少的列名。
'''
    paths = ProjectPaths.from_root(tmp_path)
    runtime = Runtime(paths)
    ref = str(path.relative_to(tmp_path))
    runtime.create("publication-test", "Deliver an article", deliverables=[ref])
    runtime.add("publication-test", "write", role="writer", goal="Write a short article",
                allowed_write_roots=[ref], deliverables=[ref])
    job = runtime.dispatch("publication-test", "write")
    staged = Path(job["staging_dir"]) / "article.md"
    staged.write_text(text)
    runtime.submit("publication-test", "write", job["token"],
                   outputs=[{"staged_path": "article.md", "target_path": ref}])
    return runtime, path, tmp_path


def test_native_draft_does_not_require_legacy_reports(native_article):
    runtime, path, root = native_article
    result = contract.validate_article(path, "draft")
    assert result["valid"], result
    assert result["runtime"] == "supervisor"
    assert not (root / "artifacts").exists()


def test_native_final_requires_current_completed_delivery(native_article):
    runtime, path, root = native_article
    pending = contract.validate_article(path, "final")
    assert not pending["valid"]
    runtime.finish("publication-test", completion="Supervisor checked the article")
    result = contract.validate_article(path, "final")
    assert result["valid"], result
    assert not (root / "articles/pending/visuals").exists()


def test_changed_delivery_cannot_be_published(native_article):
    runtime, path, root = native_article
    runtime.finish("publication-test", completion="Checked")
    path.write_text(path.read_text() + "\nChanged after delivery.\n")
    result = contract.validate_article(path, "final")
    assert not result["valid"]
    assert any(x["kind"] == "delivered_version_changed" for x in result["findings"])


def test_explicit_missing_image_is_reported(native_article):
    runtime, path, root = native_article
    path.write_text(path.read_text() + "\n![missing](missing.png)\n")
    result = contract.validate_article(path, "draft")
    assert any(x["kind"] == "visual_asset_missing" for x in result["findings"])


def _update_delivery(runtime, path, root, text, images=()):
    article_ref = str(path.relative_to(root))
    refs = [article_ref, *[ref for ref, _ in images]]
    runtime.add("publication-test", "edit", role="writer", goal="Amend the deliverable",
                allowed_write_roots=refs, deliverables=refs)
    job = runtime.dispatch("publication-test", "edit")
    staging = Path(job["staging_dir"])
    (staging / "article.md").write_text(text)
    outputs = [{"staged_path": "article.md", "target_path": article_ref}]
    for index, (ref, data) in enumerate(images):
        (staging / f"asset-{index}").write_bytes(data)
        outputs.append({"staged_path": f"asset-{index}", "target_path": ref})
    runtime.submit("publication-test", "edit", job["token"], outputs=outputs)
    runtime.finish("publication-test", completion="Checked the current delivery")


def _mutate_state(root, change):
    path = root / "workspace/runs/publication-test/engine-state.json"
    state = json.loads(path.read_text())
    change(state)
    path.write_text(json.dumps(state))


def test_native_parse_never_requests_legacy_metadata(native_article, monkeypatch):
    runtime, path, root = native_article
    def forbidden(*args, **kwargs):
        raise AssertionError("Legacy metadata was probed")
    monkeypatch.setattr(contract, "metadata_file_for", forbidden)
    runtime.finish("publication-test", completion="Checked")
    assert contract.validate_article(path, "final")["valid"]


@pytest.mark.parametrize("replacement", ["unknown-account", "[studio]"])
def test_invalid_required_schema_returns_findings(native_article, replacement):
    _, path, _ = native_article
    path.write_text(path.read_text().replace("account_id: studio", "account_id: " + replacement))
    result = contract.validate_article(path, "draft")
    assert not result["valid"]
    assert any(x["kind"] == "schema_violation" for x in result["findings"])


def test_heading_alone_is_not_a_finished_article(native_article):
    _, path, _ = native_article
    text = path.read_text().split("\n# 读 CSV", 1)[0] + "\n# Title only\n<!-- no body -->\n"
    path.write_text(text)
    result = contract.validate_article(path, "draft")
    assert any(x["kind"] == "empty_body" for x in result["findings"])


def test_native_does_not_drop_authenticity_contradictions(native_article):
    _, path, _ = native_article
    text = path.read_text().replace("tags: [Python]", "tags: [Python]\nskill_verification_mode: static_review")
    path.write_text(text + "\n本文实测，完整跑测后结果如下。\n")
    result = contract.validate_article(path, "draft")
    assert any(x["kind"] == "skill_fake_measured_language" for x in result["findings"])


def test_public_title_markers_are_checked(native_article):
    _, path, _ = native_article
    path.write_text(path.read_text().replace("title: 读 CSV 前先检查列名", 'title: "[Craft Review] 未清理"'))
    result = contract.validate_article(path, "draft")
    assert any(x["kind"] == "craft_review_leak" and x["field"] == "frontmatter.title" for x in result["findings"])


@pytest.mark.parametrize("change,kind", [
    (lambda state: state.update(pending_commit={}), "supervisor_commit_pending"),
    (lambda state: state["tasks"]["write"].update(status="running"), "supervisor_tasks_incomplete"),
    (lambda state: state["completion"].update(epoch=2), "supervisor_not_completed"),
])
def test_damaged_completed_state_cannot_bypass_delivery(native_article, change, kind):
    runtime, path, root = native_article
    runtime.finish("publication-test", completion="Checked")
    _mutate_state(root, change)
    result = contract.validate_article(path, "final")
    assert not result["valid"]
    assert any(x["kind"] == kind for x in result["findings"])


def test_malformed_native_state_does_not_fall_back_to_legacy(native_article):
    _, path, root = native_article
    (root / "workspace/runs/publication-test/engine-state.json").write_text("{broken")
    result = contract.validate_article(path, "final")
    assert result["runtime"] == "supervisor"
    assert any(x["kind"] == "supervisor_state_invalid" for x in result["findings"])


def test_final_checks_only_this_article_and_referenced_images(native_article, monkeypatch):
    runtime, path, root = native_article
    runtime.finish("publication-test", completion="Checked")
    _mutate_state(root, lambda state: state["completion"]["deliverables"].update({
        "resources/unrelated-private-note.md": {"sha256": "0" * 64, "size": 42}}))
    original = publication.file_version
    def guarded(value):
        assert Path(value) == path
        return original(value)
    monkeypatch.setattr(publication, "file_version", guarded)
    assert contract.validate_article(path, "final")["valid"]


def test_unregistered_article_cannot_borrow_a_completed_run(native_article):
    runtime, path, root = native_article
    runtime.finish("publication-test", completion="Checked")
    _mutate_state(root, lambda state: state["completion"].update(deliverables={}))
    result = contract.validate_article(path, "final")
    assert any(x["kind"] == "unregistered_deliverable" for x in result["findings"])


def test_local_image_must_be_delivered_and_unchanged(native_article):
    runtime, path, root = native_article
    image_ref = "articles/pending/visuals/publication-test/figure.png"
    text = path.read_text() + "\n![图](../../visuals/publication-test/figure.png)\n"
    _update_delivery(runtime, path, root, text, [(image_ref, b"fixture-image")])
    assert contract.validate_article(path, "final")["valid"]
    (root / image_ref).write_bytes(b"changed-image")
    result = contract.validate_article(path, "final")
    assert any(x["kind"] == "delivered_version_changed" for x in result["findings"])


def test_local_image_without_a_completion_version_is_rejected(native_article):
    runtime, path, root = native_article
    image = root / "articles/pending/visuals/publication-test/figure.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"fixture-image")
    _update_delivery(runtime, path, root, path.read_text() + "\n![图](../../visuals/publication-test/figure.png)\n")
    result = contract.validate_article(path, "final")
    assert any(x["kind"] == "unregistered_visual_asset" for x in result["findings"])


def test_noncanonical_local_publication_image_is_explicitly_rejected(native_article):
    runtime, path, root = native_article
    image = "workspace/figures/diagram.png"
    _update_delivery(runtime, path, root, path.read_text() + f"\n![图]({root / image})\n", [(image, b"fixture-image")])
    result = contract.validate_article(path, "final")
    assert any(x["kind"] == "visual_publish_scope" for x in result["findings"])


def test_image_escape_is_rejected_before_target_metadata(native_article, monkeypatch):
    _, path, root = native_article
    outside = root.parent / "never-read-image.png"
    path.write_text(path.read_text() + f"\n![外部]({outside})\n")
    original = Path.lstat
    def guarded(value, *args, **kwargs):
        assert value != outside, "Outside image was probed"
        return original(value, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", guarded)
    result = contract.validate_article(path, "draft")
    assert any(x["kind"] == "visual_path_scope" for x in result["findings"])


def test_publish_copy_collects_only_referenced_images_and_rewrites_only_their_links(native_article):
    runtime, path, root = native_article
    image_ref = "articles/pending/visuals/publication-test/nested/figure.png"
    link = "../../visuals/publication-test/nested/figure.png"
    text = path.read_text() + f'\n![图](<{link}> "caption")\n\n```markdown\n![example]({link})\n```\n'
    _update_delivery(runtime, path, root, text, [(image_ref, b"fixture-image")])
    unrelated = root / "articles/pending/visuals/publication-test/internal-note.md"
    unrelated.write_text("not a publishable asset")
    target = root / "isolated-vault/article.md"
    publication.copy_supervisor_publication(path, target, target.parent / "visual", api=contract)
    result = target.read_text()
    assert '<visual/check-columns/nested/figure.png> "caption"' in result
    assert f"![example]({link})" in result
    assert (target.parent / "visual/check-columns/nested/figure.png").read_bytes() == b"fixture-image"
    assert not (target.parent / "visual/internal-note.md").exists()
    assert path.read_text() == text and unrelated.read_text() == "not a publishable asset"


def test_publish_preflight_preserves_existing_destinations(native_article):
    runtime, path, root = native_article
    runtime.finish("publication-test", completion="Checked")
    target = root / "isolated-vault/article.md"
    target.parent.mkdir()
    target.write_text("previous publication")
    with pytest.raises(ValueError, match="already exists"):
        publication.copy_supervisor_publication(path, target, target.parent / "visual", api=contract)
    assert target.read_text() == "previous publication" and path.is_file()


def _hook(monkeypatch, paths, action, payload):
    monkeypatch.setattr(hooks.ProjectPaths, "discover", lambda: paths)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.delenv("TEXTPICOS_MAINTENANCE_SCOPE", raising=False)
    monkeypatch.delenv("TEXTPICOS_RUN_ID", raising=False)
    return hooks.main([action])


def test_stop_reads_only_explicit_run_and_never_article_outputs(native_article, monkeypatch, capsys):
    runtime, _, root = native_article
    paths = ProjectPaths.from_root(root)
    def forbidden(*args, **kwargs):
        raise AssertionError("A hook attempted file discovery or output hashing")
    monkeypatch.setattr(Path, "rglob", forbidden)
    monkeypatch.setattr(Path, "glob", forbidden)
    monkeypatch.setattr(publication, "file_version", forbidden)
    assert _hook(monkeypatch, paths, "stop", {}) == 0
    assert capsys.readouterr().out == ""
    assert _hook(monkeypatch, paths, "stop", {"run_id": "publication-test"}) == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "block"


def test_session_pointer_is_explicit_and_finished_stop_is_allowed(native_article, monkeypatch, capsys):
    runtime, _, root = native_article
    runtime.finish("publication-test", completion="Checked")
    paths = ProjectPaths.from_root(root)
    hooks.bind_session(paths, "fixture-session", "publication-test")
    assert _hook(monkeypatch, paths, "stop", {"session_id": "fixture-session"}) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("kind", ["parent", "file_link", "directory_link"])
def test_forbidden_hook_cannot_follow_escape_paths(native_article, monkeypatch, capsys, kind):
    _, _, root = native_article
    paths = ProjectPaths.from_root(root)
    secret = root / "private/note.md"
    secret.parent.mkdir()
    secret.write_text("not authorized by this hook")
    if kind == "parent":
        ref = root / "workspace/../private/note.md"
    elif kind == "file_link":
        ref = root / "workspace/link.md"
        ref.symlink_to(secret)
    else:
        (root / "workspace/alias").symlink_to(secret.parent, target_is_directory=True)
        ref = root / "workspace/alias/note.md"
    original = Path.read_text
    def guarded(path, *args, **kwargs):
        assert path != secret, "Hook escaped its explicit root"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", guarded)
    assert _hook(monkeypatch, paths, "forbidden", {"tool_input": {"file_path": str(ref)}}) == 0
    assert capsys.readouterr().out == ""


def test_system_hook_scope_does_not_even_read_payload(monkeypatch):
    monkeypatch.setenv("TEXTPICOS_MAINTENANCE_SCOPE", "system")
    monkeypatch.setattr(json, "load", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Payload read")))
    assert hooks.main(["forbidden"]) == 0


def test_post_write_has_no_file_probe(native_article, monkeypatch):
    _, _, root = native_article
    monkeypatch.setattr(hooks, "confined_path", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("File probed")))
    assert _hook(monkeypatch, ProjectPaths.from_root(root), "post-write", {"tool_input": {"file_path": "workspace/anything.md"}}) == 0


@pytest.mark.parametrize("valid,force,expected", [(False, True, 1), (True, False, 0)])
def test_publish_shell_uses_native_contract_without_legacy_size_or_metadata_gates(native_article, valid, force, expected):
    _, path, root = native_article
    project = ProjectPaths.discover().root
    canonical = project / "src/textpicos/content/publish.sh"
    original = canonical if canonical.is_file() else project / "scripts/publish.sh"
    script = original.read_text()
    script = re.sub(r'^REPO_ROOT=.*$', "REPO_ROOT=" + shlex.quote(str(root)), script, flags=re.MULTILINE)
    script = re.sub(r'^AI_WIKI_ROOT=.*$', "AI_WIKI_ROOT=" + shlex.quote(str(root / "isolated-vault")), script, flags=re.MULTILINE)
    runner = root / "publish-fixture.sh"
    runner.write_text(script)
    library = root / "scripts/lib/pipeline_phases.sh"
    library.parent.mkdir(parents=True)
    library.write_text("article_run_id() { printf '%s\\n' publication-test; }\nmissing_mandatory() { printf '%s\\n' legacy-phase; }\n")
    report = {"runtime": "supervisor", "valid": valid, "findings": [] if valid else [{"message": "Delivered version changed"}], "visual_assets": []}
    validator = root / "scripts/article_contract.py"
    validator.write_text("import json,sys\nprint(json.dumps(" + repr(report) + "))\nraise SystemExit(" + ("0" if valid else "1") + ")\n")
    env = dict(os.environ, TEXTPICOS_ROOT=str(root), TEXTPICOS_PYTHON=sys.executable)
    # Exercise publication only inside this isolated fixture. The real project
    # remains excluded by the test audit hook and is never a publishing target.
    assert root != project and project not in root.parents
    env.pop("TEXTPICOS_MAINTENANCE_SCOPE", None)
    command = ["bash", str(runner), "studio", "classic-python", "check-columns", "--dry-run", "--no-visuals"]
    if force:
        command.append("--force")
    result = subprocess.run(command, env=env, text=True, capture_output=True)
    assert result.returncode == expected, result.stdout + result.stderr
    assert path.is_file() and not (root / "isolated-vault").exists()
    if not valid:
        assert "final contract 失败" in result.stdout + result.stderr
