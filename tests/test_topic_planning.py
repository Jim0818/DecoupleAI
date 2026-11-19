"""Selected planning sources, truthful parsing, and bridge access boundaries."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from textpicos.content import topic_planning as planning
from textpicos.paths import ProjectPaths
from textpicos.runtime import Runtime

SOURCE = Path(__file__).resolve().parents[1]
BRIDGE = SOURCE / "skills/kb-bridge/dispatch.py"


class TopicPlanningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.write("config/system/paths.json", "{}")

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def request(self, name="topics.md", **extra):
        return {"account_id": "studio", "sources": [{"scope": "project", "path": name}], **extra}

    def table(self, title_header="候选题"):
        return ("## A1 — This is a group, not a topic\n\n"
                f"| ID | {title_header} | 状态 | 证据 |\n|---|---|---|---|\n"
                "| PY-001 | First task | planned | E1 |\n"
                "| PY-002 | Second task | captured | E2 |\n")

    def test_three_current_table_headers_preserve_metadata_not_group_headings(self):
        for title_header in ("候选题", "工作标题", "标题"):
            with self.subTest(title_header=title_header):
                self.write("topics.md", self.table(title_header))
                result, code = planning.list_topics(self.request(), project_root=self.root)
                self.assertEqual((code, result["status"], result["count"]), (0, "ok", 2))
                self.assertEqual([x["source_topic_id"] for x in result["items"]], ["PY-001", "PY-002"])
                self.assertEqual(result["items"][0]["metadata"]["证据"], "E1")
                self.assertEqual(result["items"][0]["planning_status"], "planned")
                self.assertNotIn("trial_verified", result["items"][0])

    def test_explicit_id_survives_title_edit_and_row_insertion(self):
        self.write("topics.md", self.table())
        first, _ = planning.list_topics(self.request(), project_root=self.root)
        self.write("topics.md", "Intro\n" + self.table().replace("First task", "New angle"))
        second, _ = planning.list_topics(self.request(), project_root=self.root)
        self.assertEqual(first["items"][0]["topic_id"], second["items"][0]["topic_id"])
        self.assertNotEqual(first["items"][0]["source_locations"], second["items"][0]["source_locations"])
        self.assertNotEqual(first["sources"][0]["sha256"], second["sources"][0]["sha256"])

    def test_two_selected_files_with_same_local_id_keep_distinct_identity(self):
        self.write("one.md", "### A1 — First\n")
        self.write("two.md", "### A1 — Second\n")
        req = self.request(sources=[{"scope": "project", "path": p} for p in ("one.md", "two.md", "one.md")])
        result, _ = planning.list_topics(req, project_root=self.root)
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["sources"]), 2)
        self.assertEqual(len({x["topic_id"] for x in result["items"]}), 2)

    def test_matching_table_and_heading_merge_locations(self):
        self.write("topics.md", self.table() + "\n### PY-001 — First task\nChosen details.\n")
        result, code = planning.list_topics(self.request(), project_root=self.root)
        self.assertEqual(code, 0)
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["items"][0]["source_locations"]), 2)
        self.assertEqual(result["items"][0]["excerpt"], "Chosen details.")

    def test_conflicting_explicit_id_is_parse_failure_not_empty_success(self):
        self.write("topics.md", "### A1 — First\n### A1 — Different\n")
        result, code = planning.list_topics(self.request(), project_root=self.root)
        self.assertEqual(code, 2)
        self.assertEqual(result["sources"][0]["error"], "CONFLICTING_TOPIC_ID")
        self.assertEqual(result["source_status"], "read")
        self.assertEqual(result["index_status"], "unavailable")
        self.assertEqual(result["items"], [])

    def test_extra_table_cell_is_rejected_without_shifting_status(self):
        self.write("topics.md", "| ID | 标题 | 状态 |\n|---|---|---|\n"
                   "| A1 | An A | B comparison | planned |\n")
        result, code = planning.list_topics(self.request(), project_root=self.root)
        self.assertEqual((code, result["status"]), (2, "not_available"))
        self.assertEqual(result["sources"][0]["error"], "INVALID_TABLE")
        self.assertEqual(result["sources"][0]["parse_status"], "error")
        self.assertEqual(result["source_status"], "read")
        self.assertEqual(result["items"], [])

    def test_missing_auxiliary_table_cell_is_rejected(self):
        self.write("topics.md", "| ID | 标题 | 状态 | 证据 |\n|---|---|---|---|\n"
                   "| A1 | A task | planned |\n")
        result, code = planning.list_topics(self.request(), project_root=self.root)
        self.assertEqual((code, result["status"]), (2, "not_available"))
        self.assertEqual(result["sources"][0]["error"], "INVALID_TABLE")
        self.assertEqual(result["sources"][0]["parse_status"], "error")
        self.assertEqual(result["source_status"], "read")
        self.assertEqual(result["items"], [])

    def test_ordinary_headings_require_explicit_parser_choice(self):
        self.write("topics.md", "# Strategy\n## Boundaries\n### A task\nSome detail.\n")
        result, code = planning.list_topics(self.request(), project_root=self.root)
        self.assertEqual((code, result["sources"][0]["error"]), (2, "UNSUPPORTED_FORMAT"))
        req = self.request(sources=[{"scope": "project", "path": "topics.md", "format": "markdown_headings", "heading_level": 3}])
        result, code = planning.list_topics(req, project_root=self.root)
        self.assertEqual((code, result["count"]), (0, 1))
        self.assertEqual(result["items"][0]["identity_basis"], "content_fingerprint")

    def test_empty_json_is_success_but_malformed_json_is_not(self):
        self.write("topics.json", '{"topics":[]}')
        result, code = planning.list_topics(self.request("topics.json"), project_root=self.root)
        self.assertEqual((code, result["status"]), (0, "empty"))
        self.write("topics.json", '{"topics":')
        result, code = planning.list_topics(self.request("topics.json"), project_root=self.root)
        self.assertEqual((code, result["status"], result["source_status"]), (2, "not_available", "read"))

    def test_json_topics_keep_id_and_json_pointer(self):
        self.write("topics.json", json.dumps({"topics": [{"id": "A1", "title": "Task", "status": "needs_material", "reader_task": "Check output"}]}))
        result, code = planning.list_topics(self.request("topics.json"), project_root=self.root)
        self.assertEqual(code, 0)
        item = result["items"][0]
        self.assertEqual(item["source_topic_id"], "A1")
        self.assertEqual(item["planning_status"], "needs_material")
        self.assertEqual(item["source_locations"], [{"json_pointer": "/topics/0"}])

    def test_partial_source_failure_preserves_usable_items_and_failure_code(self):
        self.write("topics.md", self.table())
        req = self.request(sources=[{"scope": "project", "path": f} for f in ("topics.md", "missing.md")])
        result, code = planning.list_topics(req, project_root=self.root)
        self.assertEqual((code, result["status"], result["count"]), (2, "partial", 2))
        self.assertEqual(result["source_status"], "partial")
        result, code = planning.list_topics({**req, "optional": True}, project_root=self.root)
        self.assertEqual((code, result["status"]), (0, "partial"))

    def test_stale_expected_hash_returns_actual_read_version(self):
        path = self.write("topics.md", self.table())
        req = self.request(sources=[{"scope": "project", "path": "topics.md", "expected_sha256": "0" * 64}])
        result, code = planning.list_topics(req, project_root=self.root)
        self.assertEqual(code, 2)
        self.assertEqual(result["sources"][0]["error"], "STALE_SOURCE")
        self.assertEqual(result["sources"][0]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(result["source_status"], "read")

    def test_selected_byte_budget_and_limit_are_explicit(self):
        self.write("topics.md", self.table())
        result, _ = planning.list_topics(self.request(limit=1), project_root=self.root)
        self.assertTrue(result["has_more"])
        self.assertEqual(result["sources"][0]["topic_count"], 2)
        with patch.object(planning, "MAX_BYTES", 10):
            result, code = planning.list_topics(self.request(), project_root=self.root)
        self.assertEqual((code, result["sources"][0]["error"]), (2, "SOURCE_TOO_LARGE"))

    def test_fenced_examples_are_not_topics(self):
        self.write("topics.md", "```markdown\n### A1 — Example\n```\n### B1 — Actual topic\n")
        result, code = planning.list_topics(self.request(), project_root=self.root)
        self.assertEqual((code, result["count"]), (0, 1))
        self.assertEqual(result["items"][0]["source_topic_id"], "B1")

    def test_rejected_paths_never_reach_file_open(self):
        for name in ("../outside.md", "/tmp/outside.md", "articles/private.md", "archive/keep.md", "a\\b.md"):
            with self.subTest(name=name), patch.object(planning.os, "open", side_effect=AssertionError("unexpected read")):
                with self.assertRaises(ValueError):
                    planning.list_topics(self.request(name), project_root=self.root)

    def test_symlink_file_and_parent_cannot_escape_selected_boundary(self):
        target = self.write("outside/secret.md", "### A1 — Private\n")
        (self.root / "link.md").symlink_to(target)
        (self.root / "linked").symlink_to(target.parent, target_is_directory=True)
        for name in ("link.md", "linked/secret.md"):
            with self.subTest(name=name):
                result, code = planning.list_topics(self.request(name), project_root=self.root)
                self.assertEqual(code, 2)
                self.assertEqual(result["items"], [])
                self.assertEqual(result["sources"][0]["read_status"], "not_read")
        result, code = planning.list_topics(self.request("secret.md"), project_root=self.root / "linked")
        self.assertEqual(code, 2)
        self.assertEqual(result["items"], [])

    def test_system_refuses_vault_before_run_or_file_probe(self):
        req = {"sources": [{"scope": "vault", "path": "selected.md"}], "run_id": "missing"}
        with patch.dict(os.environ, {"TEXTPICOS_MAINTENANCE_SCOPE": "system"}), patch.object(planning.os, "open", side_effect=AssertionError("probe")):
            with self.assertRaises(planning.PlanningError) as caught:
                planning.list_topics(req, project_root=self.root, vault_root=self.root / "vault")
        self.assertEqual(caught.exception.code, "OUT_OF_SCOPE")

    def test_unconfigured_vault_does_not_probe_default_locations(self):
        req = {"sources": [{"scope": "vault", "path": "selected.md"}]}
        with patch.object(planning.os, "open", side_effect=AssertionError("probe")):
            with self.assertRaises(planning.PlanningError) as caught:
                planning.list_topics(req, project_root=self.root)
        self.assertEqual(caught.exception.code, "VAULT_NOT_CONFIGURED")

    def test_direct_api_validates_selected_native_run_before_read(self):
        req = {"sources": [{"scope": "vault", "path": "selected.md"}], "run_id": "missing"}
        with patch.object(planning, "_read_source", side_effect=AssertionError("probe")):
            with self.assertRaises(planning.PlanningError) as caught:
                planning.list_topics(req, project_root=self.root, vault_root=self.root / "vault")
        self.assertEqual(caught.exception.code, "INVALID_RUN")
        self.assertFalse((self.root / "workspace/runs").exists())
        Runtime(ProjectPaths.from_root(self.root)).create("current", "Read selected planning")
        self.write("vault/selected.md", "### A1 — Real selected topic\n")
        req["run_id"] = "current"
        state = self.root / "workspace/runs/current/engine-state.json"
        before = state.read_bytes()
        result, code = planning.list_topics(req, project_root=self.root, vault_root=self.root / "vault")
        self.assertEqual((code, result["count"]), (0, 1))
        self.assertEqual(state.read_bytes(), before)

    def test_strategy_returns_actual_content_and_truncation_not_policy_verdict(self):
        text = "# Current strategy\n\nUse tasks, not an imposed topic quota.\n"
        self.write("strategy.md", text)
        result, code = planning.read_strategy(self.request("strategy.md"), project_root=self.root)
        self.assertEqual((code, result["source_status"]), (0, "read"))
        self.assertEqual(result["items"][0]["text"], text)
        self.assertFalse(result["items"][0]["truncated"])
        self.assertEqual(result["items"][0]["verification"], "source_read_not_policy_adjudicated")
        limited, _ = planning.read_strategy(self.request("strategy.md", max_chars=12), project_root=self.root)
        self.assertTrue(limited["items"][0]["truncated"])

    def test_unselected_strategy_preserves_honest_local_result(self):
        with patch.object(planning.os, "open", side_effect=AssertionError("probe")):
            result, code = planning.read_strategy({"account_id": "studio", "optional": True})
        self.assertEqual((code, result["status"], result["source_status"]), (0, "not_available", "not_read"))
        self.assertFalse(result["legacy_fallback"])

    def test_project_bridge_works_in_system_scope_without_vault_configuration(self):
        self.write("topics.md", self.table())
        env = dict(os.environ, TEXTPICOS_ROOT=str(self.root), PYTHONPATH=str(SOURCE / "src"), TEXTPICOS_MAINTENANCE_SCOPE="system")
        run = subprocess.run([sys.executable, "-S", str(BRIDGE)], cwd=self.root, env=env, input=json.dumps({"op": "list-topics", **self.request()}), text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["count"], 2)
        self.assertFalse((self.root / "workspace/runs").exists())


if __name__ == "__main__":
    unittest.main()
