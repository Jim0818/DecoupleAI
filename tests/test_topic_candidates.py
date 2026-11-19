"""Candidate persistence and selected catalogs, using isolated data only."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from textpicos.content import topic_candidates as topics
from textpicos.paths import ProjectPaths


class TopicCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = ProjectPaths(Path(self.temp.name))
        self.index = self.paths.resources / "catalogs/topic-candidates.json"
        self.record = {"account_id": "intellifuture", "key": "check-sources", "title": "Check an Agent brief",
                       "reader_task": "Check original sources", "rationale": "A concrete first task",
                       "sources": [{"source_id": "official-feed", "item_id": "entry-1", "url": "https://example.org/post"}]}

    def create(self):
        return topics.upsert_candidate(self.paths, self.record, expected_revision=0, request_id="create")

    def write(self, name, body):
        p = self.paths.resources / "catalogs" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return str(p.relative_to(self.paths.root))

    def catalogs(self):
        one = self.write("column.md", "| 日期 | slug | 标题 | 状态 |\n|---|---|---|---|\n"
                         "| 2026-11-19 | source-check | Agent brief | published |\n")
        two = self.write("series.md", "| 日期 | 账号 | slug | 状态 |\n|---|---|---|---|\n"
                         "| 2026-11-19 | intellifuture | source-check | pending（HR2） |\n\n"
                         "| slug | 本表原始状态 | 另一表原始状态 | 当前处理 |\n|---|---|---|---|\n"
                         "| source-check | pending | published | status_conflict |\n")
        return [{"path": one, "account_id": "intellifuture"}, {"path": two}]

    def resolution(self, refs):
        view = topics.registry_view(self.paths, refs)
        return {"account_id": "intellifuture", "slug": "source-check", "status": "published",
                "observed_fingerprint": view["records"][0]["observed_fingerprint"],
                "actor": "fixture-supervisor", "reason": "Fixture explicit confirmation",
                "evidence_kind": "explicit_user_confirmation", "evidence_refs": ["fixture:confirmation"]}

    def test_empty_read_does_not_initialize_or_create_cache(self):
        result = topics.load_index(self.paths)
        self.assertEqual(result["status"], "empty")
        self.assertFalse(result["initialized"])
        self.assertEqual(result["revision"], 0)
        self.assertFalse(self.index.exists())
        self.assertFalse(self.paths.cache.exists())

    def test_stable_key_survives_title_and_angle_revision(self):
        first = self.create()
        updated = topics.upsert_candidate(self.paths, {**self.record, "title": "New clear title", "angle": "Check citations"},
                                           expected_revision=1, request_id="retitle")
        self.assertEqual(first["candidate"]["id"], updated["candidate"]["id"])
        self.assertEqual(updated["candidate"]["record_version"], 2)
        self.assertEqual(len(topics.load_index(self.paths)["candidates"]), 1)
        self.assertEqual(updated["candidate"]["history"][-1]["changes"]["title"]["before"], self.record["title"])
        other = topics.upsert_candidate(self.paths, {**self.record, "account_id": "studio"},
                                         expected_revision=2, request_id="other-account")
        self.assertNotEqual(other["candidate"]["id"], first["candidate"]["id"])

    def test_replay_is_idempotent_and_different_payload_is_rejected(self):
        first = self.create()
        before = self.index.read_bytes()
        replay = topics.upsert_candidate(self.paths, self.record, expected_revision=0, request_id="create")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["revision"], first["revision"])
        self.assertEqual(self.index.read_bytes(), before)
        with self.assertRaisesRegex(topics.CandidateError, "different operation"):
            topics.upsert_candidate(self.paths, {**self.record, "title": "Other"}, expected_revision=1, request_id="create")
        self.assertEqual(self.index.read_bytes(), before)

    def test_stale_revision_never_overwrites(self):
        self.create()
        before = self.index.read_bytes()
        with self.assertRaises(topics.CandidateError) as caught:
            topics.upsert_candidate(self.paths, {**self.record, "title": "Stale"}, expected_revision=0, request_id="stale")
        self.assertEqual(caught.exception.code, "version_conflict")
        self.assertEqual(self.index.read_bytes(), before)

    def test_two_writers_have_one_successful_cas(self):
        self.create()

        def writer(number):
            try:
                return topics.upsert_candidate(self.paths, {**self.record, "title": f"Writer {number}"},
                                                expected_revision=1, request_id=f"writer-{number}")["status"]
            except topics.CandidateError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(writer, (1, 2)))
        self.assertCountEqual(outcomes, ["ok", "version_conflict"])
        self.assertEqual(topics.load_index(self.paths)["revision"], 2)

    def test_noncooperating_edit_is_detected_before_commit(self):
        self.create()
        external = json.loads(self.index.read_text())
        external["revision"] = 100
        now = topics._now
        changed = False

        def competing_edit():
            nonlocal changed
            if not changed:
                self.index.write_text(json.dumps(external), encoding="utf-8")
                changed = True
            return now()

        with patch.object(topics, "_now", side_effect=competing_edit):
            with self.assertRaises(topics.CandidateError) as caught:
                topics.upsert_candidate(self.paths, {**self.record, "title": "Race"}, expected_revision=1, request_id="race")
        self.assertEqual(caught.exception.code, "version_conflict")
        self.assertEqual(json.loads(self.index.read_text())["revision"], 100)

    def test_failed_atomic_write_preserves_previous_state(self):
        self.create()
        before = self.index.read_bytes()
        with patch.object(topics, "atomic_json", side_effect=OSError("simulated storage failure")):
            with self.assertRaises(OSError):
                topics.upsert_candidate(self.paths, {**self.record, "title": "Unsaved"}, expected_revision=1, request_id="failure")
        self.assertEqual(self.index.read_bytes(), before)

    def test_feedback_is_replayable_and_selected_does_not_publish(self):
        created = self.create()
        event = {"kind": "selected", "reason": "Useful first tutorial", "actor": "fixture-supervisor"}
        first = topics.record_feedback(self.paths, created["candidate"]["id"], event, expected_revision=1, request_id="select")
        second = topics.record_feedback(self.paths, created["candidate"]["id"], event, expected_revision=1, request_id="select")
        self.assertTrue(second["replayed"])
        self.assertEqual(len(second["candidate"]["feedback"]), 1)
        self.assertEqual(first["candidate"]["decision"], "selected")
        self.assertNotIn("published", first["candidate"])
        self.assertFalse(self.paths.runs.exists())
        self.assertFalse(self.paths.articles.exists())

    def test_feedback_request_id_is_canonical_in_record_and_replay(self):
        identity = self.create()["candidate"]["id"]
        event = {"kind": "selected", "reason": "Fixture selection", "actor": "fixture-supervisor"}
        result = topics.record_feedback(self.paths, identity, event, expected_revision=1, request_id=" select ")
        stored = topics.load_index(self.paths)["candidates"][0]
        self.assertEqual(stored["feedback"][0]["id"], "select")
        before = self.index.read_bytes()
        for request_id in ("select", " select "):
            replay = topics.record_feedback(self.paths, identity, event, expected_revision=1, request_id=request_id)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["revision"], result["revision"])
            self.assertEqual(len(replay["candidate"]["feedback"]), 1)
        self.assertEqual(self.index.read_bytes(), before)

    def test_sources_only_report_actual_feedback_and_preserve_history(self):
        created = self.create()
        identity = created["candidate"]["id"]
        before = topics.source_summary(self.paths)
        self.assertEqual(before["sources"][0]["used_candidate_ids"], [])
        self.assertEqual(before["recorded_production_minutes"], 0)
        topics.record_feedback(self.paths, identity, {"kind": "used", "reason": "Fixture material was used",
            "actor": "fixture-supervisor", "source_ids": ["official-feed"], "evidence_refs": ["fixture:output"]},
            expected_revision=1, request_id="use")
        topics.record_feedback(self.paths, identity, {"kind": "production_result", "reason": "Fixture timer",
            "actor": "fixture-supervisor", "effort_minutes": 12, "evidence_refs": ["fixture:timer"]},
            expected_revision=2, request_id="effort")
        topics.upsert_candidate(self.paths, {**self.record, "sources": []}, expected_revision=3, request_id="source-change")
        after = topics.source_summary(self.paths)
        self.assertEqual(after["sources"][0]["used_candidate_ids"], [identity])
        self.assertEqual(after["sources"][0]["candidate_ids"], [])
        self.assertEqual(after["recorded_production_minutes"], 12)
        self.assertFalse(after["automatic_source_decisions"])

    def test_used_or_numeric_feedback_needs_evidence_and_known_source(self):
        identity = self.create()["candidate"]["id"]
        events = [
            {"kind": "used", "reason": "No evidence", "actor": "fixture", "source_ids": ["official-feed"]},
            {"kind": "production_result", "reason": "No timer", "actor": "fixture", "effort_minutes": 2},
            {"kind": "used", "reason": "Unknown source", "actor": "fixture", "source_ids": ["unknown"], "evidence_refs": ["fixture:one"]},
            {"kind": "production_result", "reason": "Bad number", "actor": "fixture", "effort_minutes": float("nan"), "evidence_refs": ["fixture:one"]},
        ]
        for index, event in enumerate(events):
            with self.subTest(event=index), self.assertRaises(topics.CandidateError):
                topics.record_feedback(self.paths, identity, event, expected_revision=1, request_id=f"invalid-{index}")
        self.assertEqual(topics.load_index(self.paths)["revision"], 1)

    def test_raw_article_refs_are_never_read_or_probed(self):
        record = {**self.record, "article_refs": ["articles/published/private.md"], "run_refs": ["unknown-run"]}
        topics.upsert_candidate(self.paths, record, expected_revision=0, request_id="opaque")
        self.assertEqual(topics.load_index(self.paths)["candidates"][0]["article_refs"], record["article_refs"])
        self.assertFalse(self.paths.articles.exists())

    def test_unsafe_paths_are_rejected_before_reading(self):
        paths = ["articles/private.md", "resources/catalogs/../../articles/private.md",
                 "archive/private.md", "config/system/runtime.json", "/tmp/external.json", ""]
        with patch.object(topics, "_read_bytes", side_effect=AssertionError("Must not read")):
            for value in paths:
                with self.subTest(path=value), self.assertRaises(topics.CandidateError):
                    topics.load_index(self.paths, index_path=value)

    def test_symlink_index_and_catalog_are_rejected_before_open(self):
        target = self.paths.root / "opaque-target"
        target.write_text("must not read")
        self.index.parent.mkdir(parents=True)
        self.index.symlink_to(target)
        catalog = self.index.parent / "linked.md"
        catalog.symlink_to(target)
        with patch.object(topics, "_read_bytes", side_effect=AssertionError("Must not open symlink")):
            with self.assertRaises(topics.CandidateError):
                topics.load_index(self.paths)
            with self.assertRaises(topics.CandidateError):
                topics.registry_view(self.paths, [{"path": str(catalog), "account_id": "studio"}])

    def test_catalog_conflict_keeps_original_rows_and_ignores_conflict_table(self):
        refs = self.catalogs()
        originals = {r["path"]: (self.paths.root / r["path"]).read_bytes() for r in refs}
        view = topics.registry_view(self.paths, refs)
        self.assertEqual(len(view["records"]), 1)
        record = view["records"][0]
        self.assertTrue(record["unresolved"])
        self.assertEqual(len(record["observations"]), 2)
        self.assertCountEqual([v["status"] for v in record["observations"]], ["pending", "published"])
        self.assertIn("pending（HR2）", [v["raw_status"] for v in record["observations"]])
        self.assertIsNone(record["effective_status"])
        self.assertFalse(view["article_accessed"])
        self.assertFalse(self.index.exists())
        for path, body in originals.items():
            self.assertEqual((self.paths.root / path).read_bytes(), body)

    def test_resolution_requires_evidence_and_matching_observations(self):
        refs = self.catalogs()
        resolution = self.resolution(refs)
        for value in ({**resolution, "evidence_refs": []}, {**resolution, "observed_fingerprint": "wrong"}):
            with self.assertRaises(topics.CandidateError):
                topics.resolve_registry_conflict(self.paths, refs, value, expected_revision=0, request_id="bad-resolution")
        self.assertFalse(self.index.exists())

    def test_resolution_is_traceable_and_goes_stale_after_source_change(self):
        refs = self.catalogs()
        resolution = self.resolution(refs)
        original = (self.paths.root / refs[1]["path"]).read_bytes()
        result = topics.resolve_registry_conflict(self.paths, refs, resolution, expected_revision=0, request_id="resolve")
        self.assertEqual(result["revision"], 1)
        resolved = topics.registry_view(self.paths, refs)["records"][0]
        self.assertEqual(resolved["effective_status"], "published")
        self.assertEqual(resolved["resolution_status"], "current")
        self.assertTrue(resolved["status_conflict"])
        self.assertFalse(resolved["unresolved"])
        self.assertEqual((self.paths.root / refs[1]["path"]).read_bytes(), original)
        path = self.paths.root / refs[1]["path"]
        path.write_bytes(original.replace("pending（HR2）".encode(), "pending（new evidence pending）".encode()))
        stale = topics.registry_view(self.paths, refs)["records"][0]
        self.assertEqual(stale["resolution_status"], "stale_resolution")
        self.assertTrue(stale["unresolved"])
        self.assertIsNone(stale["effective_status"])
        self.assertEqual(len(stale["resolution_history"]), 1)

    def test_resolution_request_id_is_canonical_and_index_remains_readable(self):
        refs = self.catalogs()
        resolution = self.resolution(refs)
        result = topics.resolve_registry_conflict(self.paths, refs, resolution,
                                                   expected_revision=0, request_id=" resolve ")
        index = topics.load_index(self.paths)
        self.assertEqual(index["resolutions"]["intellifuture/source-check"][0]["request_id"], "resolve")
        self.assertEqual(topics.registry_view(self.paths, refs)["records"][0]["resolution_status"], "current")
        before = self.index.read_bytes()
        for request_id in ("resolve", " resolve "):
            replay = topics.resolve_registry_conflict(self.paths, refs, resolution,
                                                       expected_revision=0, request_id=request_id)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["revision"], result["revision"])
            self.assertEqual(replay["resolution"]["request_id"], "resolve")
        self.assertEqual(self.index.read_bytes(), before)

    def test_empty_catalog_is_distinct_from_missing_or_unparseable(self):
        valid = self.write("empty.md", "| slug | 状态 |\n|---|---|\n")
        result = topics.registry_view(self.paths, [{"path": valid, "account_id": "studio"}])
        self.assertEqual(result["status"], "empty")
        invalid = self.write("unparsed.md", "# Some unrelated notes\n")
        for path in (invalid, "resources/catalogs/missing.md"):
            with self.subTest(path=path), self.assertRaises(topics.CandidateError):
                topics.registry_view(self.paths, [{"path": path, "account_id": "studio"}])

    def test_unknown_status_is_not_inferred_as_pending(self):
        path = self.write("unknown.md", "| slug | 状态 |\n|---|---|\n| one | maybe finished |\n")
        record = topics.registry_view(self.paths, [{"path": path, "account_id": "studio"}])["records"][0]
        self.assertTrue(record["unresolved"])
        self.assertEqual(record["observations"][0]["status"], "unknown")

    def test_corrupt_index_and_boolean_revision_do_not_look_empty(self):
        self.index.parent.mkdir(parents=True)
        for content in ("{", '{"schema_version":1,"revision":true,"candidates":{},"resolutions":{},"requests":{}}',
                        '{"revision":0,"revision":1}'):
            self.index.write_text(content)
            with self.subTest(content=content), self.assertRaises(topics.CandidateError):
                topics.load_index(self.paths)

    def test_stored_resolution_without_evidence_is_rejected(self):
        refs = self.catalogs()
        topics.resolve_registry_conflict(self.paths, refs, self.resolution(refs), expected_revision=0, request_id="resolve")
        data = json.loads(self.index.read_text())
        data["resolutions"]["intellifuture/source-check"][0]["evidence_refs"] = []
        self.index.write_text(json.dumps(data))
        with self.assertRaises(topics.CandidateError) as caught:
            topics.registry_view(self.paths, refs)
        self.assertEqual(caught.exception.code, "invalid_index")

    def test_stored_used_feedback_without_evidence_is_rejected(self):
        identity = self.create()["candidate"]["id"]
        topics.record_feedback(self.paths, identity, {"kind": "used", "reason": "Fixture result", "actor": "fixture",
            "source_ids": ["official-feed"], "evidence_refs": ["fixture:result"]}, expected_revision=1, request_id="used")
        data = json.loads(self.index.read_text())
        data["candidates"][identity]["feedback"][0]["evidence_refs"] = []
        self.index.write_text(json.dumps(data))
        with self.assertRaises(topics.CandidateError) as caught:
            topics.source_summary(self.paths)
        self.assertEqual(caught.exception.code, "invalid_index")

    def test_candidate_view_is_derived_and_escapes_table_cells(self):
        topics.upsert_candidate(self.paths, {**self.record, "title": "A | B\nC", "material_gaps": ["Run a real task"]},
                                expected_revision=0, request_id="render")
        view = topics.list_candidates(self.paths, account_id="intellifuture", decision="proposed")
        output = topics.render_candidates(view)
        self.assertIn("A \\| B C", output)
        self.assertIn("Run a real task", output)
        self.assertEqual(topics.list_candidates(self.paths, account_id="studio")["candidates"], [])
        self.assertEqual(list(self.index.parent.glob("*.md")), [])


if __name__ == "__main__":
    unittest.main()
