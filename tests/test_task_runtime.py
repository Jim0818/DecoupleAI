"""Task runtime acceptance tests: isolated temporary projects, no live content."""
from __future__ import annotations

import json
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from textpicos.runtime import ConflictError, Runtime, RuntimeError, StateError


def project_paths(root):
    root = Path(root).resolve()
    return SimpleNamespace(root=root, runs=root / "workspace" / "runs")


def concurrent_submit(root, run_id, task_id, token, barrier, queue):
    runtime = Runtime(project_paths(root))
    barrier.wait(timeout=15)
    try:
        runtime.submit(run_id, task_id, token,
                       outputs=[{"staged_path": "result.txt", "target_path": "deliverables/shared.txt"}])
        queue.put("accepted")
    except RuntimeError as exc:
        queue.put(exc.code)


def interrupt_commit(root, token):
    import textpicos.runtime.core as core
    original = core.replace_from_copy
    count = 0
    def replace_then_die(source, target):
        nonlocal count
        original(source, target)
        count += 1
        if count == 1:
            os._exit(73)
    core.replace_from_copy = replace_then_die
    Runtime(project_paths(root)).submit("run", "write", token, outputs=[
        {"staged_path": "one.txt", "target_path": "deliverables/one.txt"},
        {"staged_path": "two.txt", "target_path": "deliverables/two.txt"},
    ])


class TaskRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="textpicos-runtime-")
        self.root = Path(self.temporary.name).resolve()
        self.runtime = Runtime(project_paths(self.root))

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def task(self, task_id="write", run="run", **kwargs):
        return self.runtime.add(run, task_id, role="writer", goal="Produce the requested result", **kwargs)

    def stage(self, dispatch, name="result.txt", content="final"):
        path = Path(dispatch["staging_dir"]) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_source_annotations_require_a_valid_file_reference(self):
        self.runtime.create("run", "Use selected material")
        for value in [{"url": "https://example.org/source"}, "https://example.org/source",
                      {"path": ""}, {"path": "source.md", "url": "ftp://example.org/source"}]:
            with self.subTest(reference=value), self.assertRaises(StateError) as caught:
                self.task(input_refs=[value])
            self.assertEqual(caught.exception.code, "invalid_input_reference")
        self.assertEqual(self.runtime.status("run")["tasks"], {})

    def test_dynamic_task_payload_and_explicit_completion(self):
        state = self.runtime.create("run", {"reader_task": "Compare two supplied choices"},
                                    metadata={"account_id": "studio"})
        self.assertEqual("planning", state["status"])
        task = self.runtime.add("run", "custom", role="specialist", mode="compare",
                                goal="Answer the question", skill_ids=["chosen-method"],
                                acceptance_criteria=["Use supplied sources"], metadata={"local": True})
        self.assertEqual("studio", task["account_id"])
        self.assertEqual(["chosen-method"], task["skill_ids"])
        self.assertEqual("ready", self.runtime.status("run")["status"])
        dispatch = self.runtime.dispatch("run", "custom")
        self.runtime.submit("run", "custom", dispatch["token"], summary="The requested comparison")
        self.assertEqual("awaiting_completion", self.runtime.status("run")["status"])
        with self.assertRaises(StateError):
            self.runtime.finish("run", completion="")
        self.assertEqual("completed", self.runtime.finish("run", completion="User goal is met")["status"])

    def test_missing_dependency_is_blocked_and_cycle_rejected(self):
        self.runtime.create("run", "A dynamically planned task")
        self.task("second", depends_on=["first"])
        self.assertEqual("blocked", self.runtime.status("run")["status"])
        with self.assertRaises(StateError) as caught:
            self.task("first", depends_on=["second"])
        self.assertEqual("dependency_cycle", caught.exception.code)
        self.assertNotIn("first", self.runtime.status("run")["tasks"])
        self.task("first")
        self.assertEqual(["first"], self.runtime.status("run")["ready_tasks"])

    def test_missing_input_does_not_start_a_worker(self):
        self.runtime.create("run", "Read supplied material")
        self.task(input_refs=["inputs/missing.txt"])
        with self.assertRaises(StateError) as caught:
            self.runtime.dispatch("run", "write")
        self.assertEqual("missing_input", caught.exception.code)
        task = self.runtime.task("run", "write")
        self.assertEqual(0, task["attempt"])
        self.assertIsNone(task["dispatch"])
        self.assertEqual("blocked", self.runtime.status("run")["status"])

    def test_supervisor_adjusts_tasks_without_mutating_in_flight_inputs(self):
        self.runtime.create("run", "Prepare a concise answer")
        self.task("unnecessary-research")
        changed = self.runtime.update("run", "unnecessary-research", reason="Existing sources are sufficient",
                                      goal="Only verify supplied dates", mode="verify")
        self.assertEqual("verify", changed["mode"])
        dispatch = self.runtime.dispatch("run", "unnecessary-research")
        with self.assertRaises(StateError) as caught:
            self.runtime.update("run", "unnecessary-research", reason="Changed direction", goal="Different scope")
        self.assertEqual("task_in_flight", caught.exception.code)
        self.runtime.cancel("run", "unnecessary-research", reason="No longer needed")
        self.runtime.update("run", "unnecessary-research", reason="Remove obsolete requirement", required=False)
        result = self.runtime.finish("run", completion="The supplied answer already satisfies the goal")
        self.assertEqual("completed", result["status"])
        with self.assertRaises(ConflictError):
            self.runtime.submit("run", "unnecessary-research", dispatch["token"])

    def test_atomic_submit_idempotent_retry_and_single_state(self):
        self.runtime.create("run", "Create a document", deliverables=["deliverables/result.txt"])
        self.task(allowed_write_roots=["deliverables/result.txt"])
        dispatch = self.runtime.dispatch("run", "write")
        self.stage(dispatch, content="accepted bytes")
        outputs = [{"staged_path": "result.txt", "target_path": "deliverables/result.txt"}]
        first = self.runtime.submit("run", "write", dispatch["token"], outputs=outputs, summary="Done")
        self.assertEqual("accepted bytes", (self.root / "deliverables/result.txt").read_text())
        self.assertFalse(Path(dispatch["staging_dir"]).exists())
        repeated = self.runtime.submit("run", "write", dispatch["token"], outputs=outputs, summary="Done")
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(first["outputs"], repeated["outputs"])
        self.assertEqual(1, self.runtime.status("run")["artifacts"]["deliverables/result.txt"]["version"])
        with self.assertRaises(ConflictError):
            self.runtime.submit("run", "write", dispatch["token"], outputs=outputs, summary="different request")
        finished = self.runtime.finish("run", completion="Required file is ready")
        self.assertEqual("completed", finished["status"])
        self.assertEqual(["engine-state.json"], [p.name for p in (self.root / "workspace/runs/run").glob("*.json")])

    def test_wrong_token_and_cancelled_attempt_cannot_write(self):
        self.runtime.create("run", "Document")
        self.task(allowed_write_roots=["deliverables/result.txt"])
        dispatch = self.runtime.dispatch("run", "write", host_id="host-123")
        self.stage(dispatch)
        outputs = [{"staged_path": "result.txt", "target_path": "deliverables/result.txt"}]
        with self.assertRaises(ConflictError):
            self.runtime.submit("run", "write", "wrong", outputs=outputs)
        cancelled = self.runtime.cancel("run", reason="user stopped")
        self.assertEqual("host-123", cancelled["cancel_requests"][0]["host_id"])
        with self.assertRaises(ConflictError):
            self.runtime.submit("run", "write", dispatch["token"], outputs=outputs)
        self.assertFalse((self.root / "deliverables/result.txt").exists())
        self.assertTrue(Path(dispatch["staging_dir"]).exists())
        self.runtime.resume("run", host_states={"host-123": "cancelled"})
        self.assertFalse(Path(dispatch["staging_dir"]).exists())

    def test_explicit_output_scope_and_symlinks(self):
        self.runtime.create("run", "Document")
        self.task(allowed_write_roots=["deliverables/allowed.txt"])
        dispatch = self.runtime.dispatch("run", "write")
        self.stage(dispatch)
        with self.assertRaises(StateError) as caught:
            self.runtime.submit("run", "write", dispatch["token"], outputs=[
                {"staged_path": "result.txt", "target_path": "deliverables/other.txt"}])
        self.assertEqual("outside_write_scope", caught.exception.code)
        with self.assertRaises(StateError):
            self.runtime.submit("run", "write", dispatch["token"], outputs=[
                {"staged_path": "../escape.txt", "target_path": "deliverables/allowed.txt"}])
        directory = self.root / "deliverables"
        directory.mkdir(exist_ok=True)
        external = self.write("other/actual.txt", "protected")
        (directory / "allowed.txt").symlink_to(external)
        with self.assertRaises(StateError):
            self.runtime.submit("run", "write", dispatch["token"], outputs=[
                {"staged_path": "result.txt", "target_path": "deliverables/allowed.txt"}])
        self.assertEqual("protected", external.read_text())

    def test_directory_scope_creates_new_files_but_does_not_replace_existing(self):
        self.runtime.create("run", "Figure")
        self.write("deliverables/existing.svg", "user version")
        self.task(allowed_write_roots=[{"path": "deliverables", "kind": "directory"}])
        dispatch = self.runtime.dispatch("run", "write")
        self.stage(dispatch, content="new graphic")
        with self.assertRaises(ConflictError):
            self.runtime.submit("run", "write", dispatch["token"], outputs=[
                {"staged_path": "result.txt", "target_path": "deliverables/existing.svg"}])
        self.runtime.submit("run", "write", dispatch["token"], outputs=[
            {"staged_path": "result.txt", "target_path": "deliverables/new.svg"}])
        self.assertEqual("user version", (self.root / "deliverables/existing.svg").read_text())

    def test_input_and_write_baselines_preserve_new_user_edits(self):
        self.runtime.create("run", "Edit locally")
        self.write("inputs/source.txt", "source one")
        self.write("deliverables/result.txt", "original")
        self.task(input_refs=["inputs/source.txt"], allowed_write_roots=["deliverables/result.txt"])
        dispatch = self.runtime.dispatch("run", "write")
        self.stage(dispatch)
        self.write("inputs/source.txt", "source two")
        outputs = [{"staged_path": "result.txt", "target_path": "deliverables/result.txt"}]
        with self.assertRaises(ConflictError) as caught:
            self.runtime.submit("run", "write", dispatch["token"], outputs=outputs)
        self.assertEqual("input_conflict", caught.exception.code)
        self.write("inputs/source.txt", "source one")
        self.write("deliverables/result.txt", "new user edit")
        with self.assertRaises(ConflictError) as caught:
            self.runtime.submit("run", "write", dispatch["token"], outputs=outputs)
        self.assertEqual("write_conflict", caught.exception.code)
        self.assertEqual("new user edit", (self.root / "deliverables/result.txt").read_text())

    def test_cross_run_concurrent_commits_have_one_winner(self):
        context = multiprocessing.get_context("spawn")
        barrier, queue = context.Barrier(2), context.Queue()
        self.write("deliverables/shared.txt", "baseline")
        processes = []
        for number in range(2):
            run = f"run-{number}"
            self.runtime.create(run, "Edit shared file")
            self.task(run=run, allowed_write_roots=["deliverables/shared.txt"])
            dispatch = self.runtime.dispatch(run, "write")
            self.stage(dispatch, content=f"worker-{number}")
            process = context.Process(target=concurrent_submit, args=(
                str(self.root), run, "write", dispatch["token"], barrier, queue))
            processes.append(process)
        for process in processes:
            process.start()
        results = [queue.get(timeout=20), queue.get(timeout=20)]
        for process in processes:
            process.join(timeout=20)
            self.assertEqual(0, process.exitcode)
        self.assertEqual(["accepted", "write_conflict"], sorted(results))
        self.assertIn((self.root / "deliverables/shared.txt").read_text(), {"worker-0", "worker-1"})

    def prepare_crash(self):
        self.runtime.create("run", "Two output files", deliverables=["deliverables/one.txt", "deliverables/two.txt"])
        self.write("deliverables/one.txt", "old-one")
        self.write("deliverables/two.txt", "old-two")
        self.task(allowed_write_roots=["deliverables/one.txt", "deliverables/two.txt"])
        dispatch = self.runtime.dispatch("run", "write")
        self.stage(dispatch, "one.txt", "new-one")
        self.stage(dispatch, "two.txt", "new-two")
        process = multiprocessing.get_context("spawn").Process(target=interrupt_commit,
                                                               args=(str(self.root), dispatch["token"]))
        process.start()
        process.join(timeout=20)
        self.assertEqual(73, process.exitcode)
        return dispatch

    def test_crashed_multi_output_commit_rolls_forward_exactly_once(self):
        dispatch = self.prepare_crash()
        self.assertEqual("blocked", self.runtime.status("run")["status"])
        self.assertEqual("new-one", (self.root / "deliverables/one.txt").read_text())
        self.assertEqual("old-two", (self.root / "deliverables/two.txt").read_text())
        resumed = Runtime(project_paths(self.root)).resume("run")
        self.assertEqual("succeeded", resumed["recovery"]["status"])
        self.assertEqual("new-two", (self.root / "deliverables/two.txt").read_text())
        self.assertIsNone(resumed["pending_commit"])
        self.assertEqual(1, resumed["artifacts"]["deliverables/one.txt"]["version"])
        repeated = self.runtime.submit("run", "write", dispatch["token"], outputs=[
            {"staged_path": "one.txt", "target_path": "deliverables/one.txt"},
            {"staged_path": "two.txt", "target_path": "deliverables/two.txt"}])
        self.assertTrue(repeated["idempotent"])

    def test_recovery_conflict_preserves_user_edit_and_abort_restores_other_target(self):
        self.prepare_crash()
        self.write("deliverables/two.txt", "user wrote after crash")
        with self.assertRaises(ConflictError):
            self.runtime.resume("run")
        aborted = self.runtime.resume("run", abort_conflict=True)
        self.assertEqual("old-one", (self.root / "deliverables/one.txt").read_text())
        self.assertEqual("user wrote after crash", (self.root / "deliverables/two.txt").read_text())
        self.assertEqual(["deliverables/two.txt"], aborted["recovery"]["preserved_external_changes"])
        self.assertEqual("failed", aborted["tasks"]["write"]["status"])

    def test_finish_fences_optional_worker_then_revision_rejects_late_result(self):
        self.runtime.create("run", "Return comparison")
        self.task("answer")
        answer = self.runtime.dispatch("run", "answer")
        self.runtime.submit("run", "answer", answer["token"], summary="comparison")
        self.task("optional", required=False, allowed_write_roots=["deliverables/figure.svg"])
        optional = self.runtime.dispatch("run", "optional", host_id="visual-host")
        self.stage(optional)
        completed = self.runtime.finish("run", completion="The comparison is sufficient")
        self.assertEqual("completed", completed["status"])
        self.assertEqual("visual-host", completed["cancel_requests"][0]["host_id"])
        self.assertTrue(Path(optional["staging_dir"]).exists())
        revised = self.runtime.revise("run", feedback="Shorten the conclusion")
        self.assertEqual(2, revised["epoch"])
        self.assertEqual("planning", revised["status"])
        with self.assertRaises(ConflictError):
            self.runtime.submit("run", "optional", optional["token"], outputs=[
                {"staged_path": "result.txt", "target_path": "deliverables/figure.svg"}])
        self.runtime.resume("run", host_states={"visual-host": "cancelled"})
        self.assertFalse(Path(optional["staging_dir"]).exists())

    def test_required_deliverables_and_current_versions_are_checked(self):
        self.runtime.create("run", "File", deliverables=["deliverables/result.txt"])
        self.task(allowed_write_roots=["deliverables/result.txt"])
        dispatch = self.runtime.dispatch("run", "write")
        self.runtime.submit("run", "write", dispatch["token"], summary="Forgot the file")
        with self.assertRaises(StateError) as caught:
            self.runtime.finish("run", completion="Claimed complete")
        self.assertEqual("missing_deliverable", caught.exception.code)

    def test_stale_review_does_not_pass_after_body_edit(self):
        self.runtime.create("run", "Review file")
        self.write("deliverables/result.txt", "old")
        self.runtime.add("run", "review", role="reviewer", goal="Check facts", input_refs=["deliverables/result.txt"])
        review = self.runtime.dispatch("run", "review")
        self.runtime.submit("run", "review", review["token"], summary="PASS on this version")
        self.task("repair", allowed_write_roots=["deliverables/result.txt"])
        repair = self.runtime.dispatch("run", "repair")
        self.stage(repair, content="new")
        self.runtime.submit("run", "repair", repair["token"], outputs=[
            {"staged_path": "result.txt", "target_path": "deliverables/result.txt"}])
        self.assertEqual("blocked", self.runtime.task("run", "review")["status"])
        with self.assertRaises(StateError):
            self.runtime.finish("run", completion="Ready")
        self.runtime.unblock("run", "review", resolution="Recheck changed version")
        recheck = self.runtime.dispatch("run", "review")
        with self.assertRaises(ConflictError):
            self.runtime.submit("run", "review", review["token"], summary="different delayed reply")
        self.runtime.submit("run", "review", recheck["token"], summary="PASS on the new version")
        self.assertEqual("completed", self.runtime.finish("run", completion="Recheck complete")["status"])

    def test_host_reconciliation_does_not_guess_or_fake_success(self):
        self.runtime.create("run", "Review")
        self.task(max_attempts=2)
        first = self.runtime.dispatch("run", "write")
        self.runtime.bind_host("run", "write", first["token"], "host-a")
        self.assertEqual("running", self.runtime.resume("run")["status"])
        complete_host = self.runtime.resume("run", host_states={"host-a": "completed"})
        self.assertEqual("running", complete_host["status"])
        self.assertEqual("collect_result", complete_host["awaiting_hosts"][0]["action"])
        self.runtime.resume("run", host_states={"host-a": "lost"})
        second = self.runtime.dispatch("run", "write")
        self.assertEqual(2, second["attempt"])
        with self.assertRaises(ConflictError):
            self.runtime.submit("run", "write", first["token"])
        self.runtime.fail("run", "write", second["token"], reason="unavailable input")
        with self.assertRaises(StateError) as caught:
            self.runtime.dispatch("run", "write")
        self.assertEqual("attempts_exhausted", caught.exception.code)

    def test_runtime_control_is_not_an_output_target(self):
        self.runtime.create("run", "File")
        self.task(allowed_write_roots=["workspace/runs/run/engine-state.json"])
        with self.assertRaises(StateError) as caught:
            self.runtime.dispatch("run", "write")
        self.assertEqual("protected_target", caught.exception.code)

    def test_legacy_state_is_not_silently_adopted(self):
        self.write("workspace/runs/old/engine-state.json", json.dumps({"schema_version": 4, "run_id": "old"}))
        with self.assertRaises(StateError) as caught:
            self.runtime.status("old")
        self.assertEqual("wrong_runtime", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
