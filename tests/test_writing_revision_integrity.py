"""Version associations use synthetic documents in isolated temporary projects."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from textpicos.runtime import ConflictError, Runtime, StateError
from textpicos.runtime.storage import file_version


ARTICLE = """---
title: 分批读取与内存
date: 2026-11-18
author: supplied-notes
tags: [Python]
workflow_status: draft
prose_policy_revision: 2
source_ref: inputs/evidence.md
---
# 分批读取与内存

读取方式需要和下游处理一起看。

逐行读取后，把所有记录追加到列表中，列表占用仍会增长。

按处理需求决定是否保留已经读过的记录。
"""
REF = "deliverables/draft.md"


@pytest.fixture
def project(tmp_path):
    root = tmp_path.resolve()
    path = root / REF
    path.parent.mkdir()
    path.write_text(ARTICLE, encoding="utf-8")
    runtime = Runtime(SimpleNamespace(root=root, runs=root / "workspace/runs"))
    runtime.create("writing", "Deliver the requested revision", deliverables=[REF])
    return runtime, path


def add_consumer(runtime, task_id="review", role="reviewer", mode="review", *, scoped=True):
    source = {"path": REF, "version_scope": "article_content"} if scoped else REF
    runtime.add("writing", task_id, role=role, mode=mode, goal="Check this supplied version",
                input_refs=[source])
    return runtime.dispatch("writing", task_id)


def commit_text(runtime, text, *, task_id="metadata"):
    runtime.add("writing", task_id, role="writer", mode="edit", goal="Apply the selected change",
                allowed_write_roots=[REF], deliverables=[REF])
    dispatch = runtime.dispatch("writing", task_id)
    (Path(dispatch["staging_dir"]) / "draft.md").write_text(text, encoding="utf-8")
    return runtime.submit("writing", task_id, dispatch["token"], outputs=[
        {"staged_path": "draft.md", "target_path": REF}])


def test_metadata_only_commit_preserves_scoped_review_and_surface_results(project):
    runtime, path = project
    for task_id, role, mode in [("review", "reviewer", "review"),
                                ("summary", "writer", "summary"),
                                ("title", "reviewer", "title")]:
        dispatch = add_consumer(runtime, task_id, role, mode)
        version = dispatch["input_versions"][REF]
        assert version["version_scope"] == "article_content"
        assert version["projection"] == "frontmatter_body_v1"
        runtime.submit("writing", task_id, dispatch["token"], summary="Checked supplied content")
    changed = ARTICLE.replace("tags: [Python]", "tags: [Python, IO]")
    changed = changed.replace("workflow_status: draft", "workflow_status: queued")
    commit_text(runtime, changed)
    assert all(runtime.task("writing", name)["status"] == "succeeded"
               for name in ["review", "summary", "title"])
    completed = runtime.finish("writing", completion="Content and selected metadata are ready")
    assert completed["completion"]["deliverables"][REF] == file_version(path)


def test_unscoped_metadata_review_remains_byte_sensitive(project):
    runtime, _ = project
    dispatch = add_consumer(runtime, scoped=False)
    runtime.submit("writing", "review", dispatch["token"], summary="Metadata also checked")
    commit_text(runtime, ARTICLE.replace("tags: [Python]", "tags: [IO]"))
    assert runtime.task("writing", "review")["status"] == "blocked"


@pytest.mark.parametrize("old,new", [
    ("title: 分批读取与内存", "title: 逐行读取保证恒定内存"),
    ("date: 2026-11-18", "date: 2026-11-19"),
    ("author: supplied-notes", "author: different-author"),
    ("prose_policy_revision: 2", "prose_policy_revision: 3"),
    ("source_ref: inputs/evidence.md", "source_ref: inputs/other.md"),
    ("source_ref: inputs/evidence.md", "source_ref: inputs/evidence.md\ncustom_boundary: changed"),
    ("列表占用仍会增长", "列表占用不会增长"),
])
def test_title_boundaries_unknown_fields_and_middle_body_changes_invalidate(project, old, new):
    runtime, _ = project
    dispatch = add_consumer(runtime)
    runtime.submit("writing", "review", dispatch["token"], summary="PASS on prior content")
    commit_text(runtime, ARTICLE.replace(old, new))
    assert runtime.task("writing", "review")["status"] == "blocked"
    with pytest.raises(StateError, match="Required tasks have not succeeded"):
        runtime.finish("writing", completion="Must not accept the stale review")


def test_finish_detects_external_body_change_after_review(project):
    runtime, path = project
    dispatch = add_consumer(runtime)
    runtime.submit("writing", "review", dispatch["token"], summary="PASS")
    path.write_text(ARTICLE.replace("列表占用仍会增长", "列表占用不会增长"), encoding="utf-8")
    with pytest.raises(ConflictError) as caught:
        runtime.finish("writing", completion="Must not rely on the prior review")
    assert caught.value.code == "review_version_conflict"


def test_inflight_reader_can_finish_after_noncontent_metadata_change(project):
    runtime, path = project
    dispatch = add_consumer(runtime)
    path.write_text(ARTICLE.replace("tags: [Python]", "tags: [IO]"), encoding="utf-8")
    assert runtime.submit("writing", "review", dispatch["token"], summary="PASS")["status"] == "succeeded"


def test_inflight_reader_rejects_changed_content(project):
    runtime, path = project
    dispatch = add_consumer(runtime)
    path.write_text(ARTICLE.replace("列表占用仍会增长", "列表占用不会增长"), encoding="utf-8")
    with pytest.raises(ConflictError) as caught:
        runtime.submit("writing", "review", dispatch["token"], summary="Old PASS")
    assert caught.value.code == "input_conflict"


def test_content_input_scope_does_not_weaken_full_file_write_cas(project):
    runtime, path = project
    runtime.add("writing", "edit", role="writer", goal="Edit one paragraph",
                input_refs=[{"path": REF, "version_scope": "article_content"}],
                allowed_write_roots=[REF])
    dispatch = runtime.dispatch("writing", "edit")
    (Path(dispatch["staging_dir"]) / "draft.md").write_text(ARTICLE + "补充一句。\n", encoding="utf-8")
    user_version = ARTICLE.replace("tags: [Python]", "tags: [用户修改]")
    path.write_text(user_version, encoding="utf-8")
    with pytest.raises(ConflictError) as caught:
        runtime.submit("writing", "edit", dispatch["token"], outputs=[
            {"staged_path": "draft.md", "target_path": REF}])
    assert caught.value.code == "write_conflict"
    assert path.read_text(encoding="utf-8") == user_version


@pytest.mark.parametrize("text", [
    "---\ntitle: [broken\ntags: [Python]\n---\n正文\n",
    "---\ntitle: A\ntitle: B\ntags: [Python]\n---\n正文\n",
    "---\ntitle: A\ntags: [Python]\n正文\n",
])
def test_ambiguous_frontmatter_falls_back_to_strict_file_version(project, text):
    _, path = project
    path.write_text(text, encoding="utf-8")
    original = file_version(path, version_scope="article_content")
    assert original["projection"] == "full_file"
    assert original["sha256"] == file_version(path)["sha256"]
    path.write_text(text.replace("Python", "IO"), encoding="utf-8")
    assert file_version(path, version_scope="article_content") != original


def test_scope_does_not_ignore_unknown_status_key(project):
    _, path = project
    path.write_text(ARTICLE.replace("workflow_status: draft", "status: experimental"), encoding="utf-8")
    original = file_version(path, version_scope="article_content")
    path.write_text(path.read_text().replace("status: experimental", "status: verified"), encoding="utf-8")
    assert file_version(path, version_scope="article_content") != original


def test_interrupted_self_edit_recovers_with_scoped_input_and_full_file_outputs(project, monkeypatch):
    import textpicos.runtime.core as core
    runtime, path = project
    runtime.add("writing", "edit", role="writer", goal="Edit supplied content",
                input_refs=[{"path": REF, "version_scope": "article_content"}],
                allowed_write_roots=[REF, "deliverables/summary.txt"])
    dispatch = runtime.dispatch("writing", "edit")
    stage = Path(dispatch["staging_dir"])
    new_body = ARTICLE + "补充适用条件。\n"
    (stage / "draft.md").write_text(new_body, encoding="utf-8")
    (stage / "summary.txt").write_text("摘要", encoding="utf-8")
    original_replace = core.replace_from_copy
    def interrupt_after_first(source, target):
        original_replace(source, target)
        raise OSError("Simulated interruption after one replacement")
    monkeypatch.setattr(core, "replace_from_copy", interrupt_after_first)
    with pytest.raises(OSError):
        runtime.submit("writing", "edit", dispatch["token"], outputs=[
            {"staged_path": "draft.md", "target_path": REF},
            {"staged_path": "summary.txt", "target_path": "deliverables/summary.txt"}])
    monkeypatch.setattr(core, "replace_from_copy", original_replace)
    runtime.resume("writing")
    assert path.read_text(encoding="utf-8") == new_body
    assert runtime.task("writing", "edit")["status"] == "succeeded"
    assert runtime.finish("writing", completion="Recovered both results")["status"] == "completed"


def test_input_scope_is_validated_and_default_skills_preserve_omission(project):
    runtime, _ = project
    with pytest.raises(StateError) as caught:
        runtime.add("writing", "bad", role="reviewer", goal="Read", input_refs=[
            {"path": REF, "version_scope": "ignore_everything"}])
    assert caught.value.code == "invalid_version_scope"
    default = runtime.add("writing", "default", role="writer", goal="Use configured defaults")
    explicit = runtime.add("writing", "explicit", role="writer", goal="Use required methods only", skill_ids=[])
    assert default["skill_ids"] is None
    assert explicit["skill_ids"] == []
    updated = runtime.update("writing", "explicit", reason="Restore configured defaults", skill_ids=None)
    assert updated["skill_ids"] is None


def test_duplicate_input_cannot_silently_weaken_the_requested_version_scope(project):
    runtime, path = project
    with pytest.raises(StateError) as caught:
        runtime.add("writing", "conflicting", role="reviewer", goal="Check metadata too",
                    input_refs=[REF, {"path": str(path), "version_scope": "article_content"}])
    assert caught.value.code == "conflicting_version_scope"
