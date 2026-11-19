"""Topic entry-point integration: durable cache/evidence and mutation routing."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from textpicos.content import topic_tools as tools
from textpicos.paths import ProjectPaths
from textpicos.runtime import Runtime


class TopicToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = ProjectPaths(Path(self.temp.name))
        config = self.paths.config / "system"
        config.mkdir(parents=True)
        self.spec = {"id": "official", "kind": "feed", "url": "https://example.org/feed", "enabled": True}
        (config / "topic-sources.json").write_text(json.dumps({"schema_version": 1, "sources": [self.spec]}))
        (config / "topic-planning.json").write_text(json.dumps({"schema_version": 1,
            "vault_root": "/fixture-explicit-vault", "accounts": {"studio": {
                "topic_sources": [{"scope": "vault", "path": "topics.md"}], "catalog_refs": []}}}))
        self.item = {"id": "entry-1", "title": "A real bounded task", "url": "https://example.org/1",
                     "published_at": "2024-01-01T00:00:00Z", "observed_at": "2026-11-19T00:00:00Z",
                     "verification": "source_not_checked"}
        self.result = {"status": "ok", "items": [self.item], "sources": [{"source_id": "official",
            "status": "ok", "fetched_at": "2026-11-19T00:00:00Z", "items": [self.item]}],
            "states": {"official": {"fingerprint": "fixture", "items": [self.item]}}}

    def fetch(self, result=None):
        with patch("textpicos.content.topic_sources.collect_sources", return_value=deepcopy(result or self.result)):
            return tools.execute({"op": "fetch"}, paths=self.paths)

    def selection(self):
        return {"source_id": "official", "item_id": "entry-1",
                "expected_item_sha256": tools._digest(self.item)}

    def test_fetch_persists_success_without_exposing_private_state(self):
        result, code = self.fetch()
        self.assertEqual(code, 0)
        self.assertNotIn("states", result)
        self.assertNotIn("state", result["sources"][0])
        cached, _ = tools.execute({"op": "cache"}, paths=self.paths)
        entry = cached["sources"][0]
        self.assertEqual(entry["status"], "cached")
        self.assertEqual(entry["result"]["items"][0]["published_at"], self.item["published_at"])
        self.assertEqual(result["items"][0]["evidence_selections"], [self.selection()])

    def test_failure_preserves_previous_successful_cache(self):
        self.fetch()
        cache = tools._cache_path(self.paths, "official")
        before = cache.read_bytes()
        failure = {"status": "unavailable", "items": [], "sources": [{"source_id": "official",
                    "status": "unavailable", "items": []}], "states": {}}
        result, code = self.fetch(failure)
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(cache.read_bytes(), before)

    def test_partial_result_keeps_each_source_health(self):
        result = deepcopy(self.result)
        result["status"] = "partial"
        returned, code = self.fetch(result)
        self.assertEqual(code, 0)
        self.assertEqual(returned["sources"][0]["status"], "ok")

    def test_first_partial_result_can_be_saved_without_advancing_state(self):
        partial = deepcopy(self.result)
        partial["status"] = partial["sources"][0]["status"] = "partial"
        partial["sources"][0]["failure_status"] = "unavailable"
        partial["states"]["official"] = {}
        result, code = self.fetch(partial)
        self.assertEqual(code, 0)
        self.assertEqual(result["sources"][0]["failure_status"], "unavailable")
        cache = json.loads(tools._cache_path(self.paths, "official").read_text())
        self.assertEqual(cache["state"], {})
        Runtime(self.paths).create("partial-run", "Save an actually returned item")
        evidence, code = tools.execute({"op": "save-evidence", "run_id": "partial-run",
            "items": result["items"][0]["evidence_selections"]}, paths=self.paths)
        self.assertEqual(code, 0)
        self.assertEqual(evidence["count"], 1)

    def test_partial_result_preserves_prior_incremental_state(self):
        self.fetch()
        partial = deepcopy(self.result)
        partial["status"] = partial["sources"][0]["status"] = "partial"
        partial["states"]["official"] = {"unexpected": "must not advance"}
        self.fetch(partial)
        cache = json.loads(tools._cache_path(self.paths, "official").read_text())
        self.assertEqual(cache["state"], self.result["states"]["official"])

    def test_changed_config_does_not_reuse_incompatible_cache(self):
        self.fetch()
        self.spec["url"] = "https://example.org/other-feed"
        (self.paths.config / "system/topic-sources.json").write_text(json.dumps({"schema_version": 1, "sources": [self.spec]}))
        with patch("textpicos.content.topic_sources.collect_sources", return_value=deepcopy(self.result)) as collect:
            tools.execute({"op": "fetch"}, paths=self.paths)
        self.assertEqual(collect.call_args.kwargs["states"], {})

    def test_missing_cache_does_not_create_empty_success(self):
        result, code = tools.execute({"op": "cache"}, paths=self.paths)
        self.assertEqual(code, 0)
        self.assertEqual(result["sources"][0]["status"], "not_available")
        self.assertFalse(self.paths.cache.exists())

    def test_evidence_survives_cache_removal_and_remains_unverified(self):
        self.fetch()
        Runtime(self.paths).create("evidence-run", "Record selected material")
        request = {"op": "save-evidence", "run_id": "evidence-run",
                   "items": [self.selection()]}
        result, code = tools.execute(request, paths=self.paths)
        self.assertEqual(code, 0)
        evidence = self.paths.root / result["path"]
        original = evidence.read_bytes()
        with self.assertRaisesRegex(ValueError, "version changed"):
            tools.execute(request, paths=self.paths)
        tools._cache_path(self.paths, "official").unlink()
        self.assertEqual(evidence.read_bytes(), original)
        self.assertEqual(json.loads(original)["verification"], "source_not_checked")
        self.assertEqual(json.loads(original)["items"][0]["item"]["published_at"], self.item["published_at"])

    def test_selected_evidence_version_cannot_drift_after_refresh(self):
        original, _ = self.fetch()
        Runtime(self.paths).create("version-run", "Save the selected version")
        changed = deepcopy(self.result)
        changed["sources"][0]["items"][0]["title"] = "A later source edit"
        self.fetch(changed)
        with self.assertRaisesRegex(ValueError, "source item version changed"):
            tools.execute({"op": "save-evidence", "run_id": "version-run",
                "items": original["items"][0]["evidence_selections"]}, paths=self.paths)
        self.assertFalse((self.paths.runs / "version-run/evidence/topic-source-items.json").exists())

    def test_deduplicated_items_preserve_each_source_selection(self):
        result = deepcopy(self.result)
        second = deepcopy(result["sources"][0])
        second["source_id"] = "second"
        second["items"][0]["id"] = "another-id"
        for source in [result["sources"][0], second]:
            source["items"][0]["canonical_url"] = "https://example.org/1"
        result["items"][0]["canonical_url"] = "https://example.org/1"
        result["sources"].append(second)
        tools._bind_item_versions(result)
        selected = result["items"][0]["evidence_selections"]
        self.assertEqual([item["source_id"] for item in selected], ["official", "second"])
        for source, selection in zip(result["sources"], selected):
            self.assertEqual(selection["expected_item_sha256"], tools._item_digest(source["items"][0]))

    def test_evidence_requires_real_selected_item_and_active_run(self):
        self.fetch()
        Runtime(self.paths).create("closed-run", "Done")
        Runtime(self.paths).finish("closed-run", completion="Fixture completed")
        request = {"op": "save-evidence", "run_id": "closed-run",
                   "items": [self.selection()]}
        with self.assertRaisesRegex(ValueError, "completed run"):
            tools.execute(request, paths=self.paths)
        request["items"][0]["item_id"] = "made-up"
        with self.assertRaisesRegex(ValueError, "absent"):
            tools.execute(request, paths=self.paths)

    def test_candidate_cli_preserves_identity_and_reports_revision_conflict(self):
        record = {"account_id": "studio", "key": "one-task", "title": "One task", "reader_task": "Check one result"}
        request = {"op": "candidate-upsert", "record": record, "expected_revision": 0, "request_id": "create"}
        created, _ = tools.execute(request, paths=self.paths)
        request.update(request_id="other", record={**record, "title": "Changed title"})
        with self.assertRaises(ValueError):
            tools.execute(request, paths=self.paths)
        view, _ = tools.execute({"op": "candidates", "format": "markdown"}, paths=self.paths)
        self.assertIn("One task", view["markdown"])
        feedback, _ = tools.execute({"op": "feedback", "topic_id": created["candidate"]["id"],
            "event": {"kind": "selected", "actor": "fixture-supervisor", "reason": "Ready to research"},
            "expected_revision": 1, "request_id": "select"}, paths=self.paths)
        self.assertEqual(feedback["candidate"]["decision"], "selected")
        self.assertFalse(self.paths.runs.exists())

    def test_planning_uses_registered_bridge_and_preserves_maintenance_scope(self):
        completed = type("Result", (), {"returncode": 2, "stdout": "", "stderr": '{"error":"OUT_OF_SCOPE"}'})()
        with patch.dict("os.environ", {"TEXTPICOS_MAINTENANCE_SCOPE": "system"}, clear=True):
            with patch.object(tools.subprocess, "run", return_value=completed) as run:
                result, code = tools.execute({"op": "planning", "account_id": "studio"}, paths=self.paths)
        self.assertEqual(code, 2)
        self.assertEqual(result["error"], "OUT_OF_SCOPE")
        self.assertTrue(run.call_args.args[0][-1].endswith("skills/kb-bridge/dispatch.py"))
        self.assertEqual(run.call_args.kwargs["env"]["TEXTPICOS_MAINTENANCE_SCOPE"], "system")
        self.assertEqual(run.call_args.kwargs["env"]["TEXTPICOS_AI_WIKI_ROOT"], "/fixture-explicit-vault")

    def test_cache_symlink_and_unknown_source_are_rejected(self):
        with self.assertRaises(ValueError):
            tools.execute({"op": "fetch", "source_ids": ["unconfigured"]}, paths=self.paths)
        parent = self.paths.cache / "topic-sources"
        parent.mkdir(parents=True)
        outside = self.paths.root / "outside.json"
        outside.write_text("{}")
        (parent / "official.json").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            tools.execute({"op": "cache"}, paths=self.paths)


if __name__ == "__main__":
    unittest.main()
