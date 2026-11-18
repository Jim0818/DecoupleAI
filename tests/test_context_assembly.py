"""Context tests use temporary projects and never open the user's articles."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from textpicos.context import ContextError, assemble_context, context_prompt, load_capabilities


class ContextAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = SimpleNamespace(root=self.root, config=self.root / "config", articles=self.root / "articles")
        self.registry = {
            "orchestration_mode": "supervisor",
            "content_defaults": {"prose_policy_revision": 2},
            "roles": {
                "writer": {
                    "entrypoint": "agents/workers/writer/SKILL.md",
                    "default_mode": "edit",
                    "modes": {"edit": {}, "title": {"default_skills": []}},
                    "required_skills": ["writing"],
                    "default_skills": ["natural-prose"],
                    "account_files": ["L1_identity.md"],
                },
                "reviewer": {
                    "entrypoint": "agents/workers/reviewer/SKILL.md",
                    "default_mode": "review",
                    "modes": {"review": {}},
                    "required_skills": ["review"],
                    "independent_context": True,
                },
            },
            "skills": {
                "writing": {"kind": "production", "entrypoint": "skills/writing/SKILL.md", "mode_refs": {"edit": ["skills/writing/references/edit.md"]}},
                "natural-prose": {"kind": "production", "entrypoint": "skills/natural-prose/SKILL.md"},
                "review": {"kind": "production", "entrypoint": "skills/review/SKILL.md"},
                "maintenance": {"kind": "maintenance", "entrypoint": "skills/maintenance/SKILL.md"},
            },
            "accounts": {a: {"directory": f"config/accounts/{a}"} for a in ["studio", "decoupleai"]},
        }
        for rel in [
            "agents/workers/writer/SKILL.md", "agents/workers/reviewer/SKILL.md",
            "skills/writing/SKILL.md", "skills/writing/references/edit.md",
            "skills/natural-prose/SKILL.md", "skills/review/SKILL.md",
            "config/accounts/studio/L1_identity.md", "config/accounts/decoupleai/L1_identity.md",
        ]:
            self.write(rel, f"# Actual method: {rel}\n")
        self.save_registry()

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def save_registry(self):
        self.write("config/system/capabilities.json", json.dumps(self.registry))

    def assemble(self, task=None, **kwargs):
        return assemble_context(self.paths, task or {}, role="writer", **kwargs)

    def test_current_role_method_and_only_selected_account_are_present(self):
        result = self.assemble(account_id="studio")
        refs = [item["path"] for item in result["resources"]]
        self.assertIn(str((self.root / "skills/writing/references/edit.md").resolve()), refs)
        self.assertIn(str((self.root / "skills/natural-prose/SKILL.md").resolve()), refs)
        self.assertTrue(any("accounts/studio/" in ref for ref in refs))
        self.assertFalse(any("decoupleai" in ref or "maintenance" in ref for ref in refs))

    def test_missing_required_method_does_not_fall_back_to_legacy(self):
        (self.root / "skills/writing/references/edit.md").unlink()
        self.write("agents/legacy/writer/runtime.md", "# An unrelated old method")
        with self.assertRaisesRegex(ContextError, "Required method"):
            self.assemble()

    def test_empty_registered_method_is_not_accepted(self):
        self.write("skills/writing/references/edit.md", "")
        with self.assertRaisesRegex(ContextError, "is empty"):
            self.assemble()

    def test_aliases_to_same_resource_are_loaded_once(self):
        alias = self.root / "skills/writing/references/edit-alias.md"
        alias.symlink_to("edit.md")
        self.registry["skills"]["writing"]["mode_refs"]["edit"].append(str(alias))
        self.save_registry()
        result = self.assemble(skill_ids=["natural-prose", "natural-prose"])
        resolved = [item["resolved_path"] for item in result["resources"]]
        self.assertEqual(len(resolved), len(set(resolved)))
        method = next(item for item in result["resources"] if item["kind"] == "method")
        self.assertEqual(len(method["ids"]), 2)

    def test_absolute_input_is_a_reference_not_repeated_body(self):
        with TemporaryDirectory() as external:
            p = Path(external) / "selected-draft.md"
            p.write_text("UNIQUE_PRIVATE_BODY_SENTINEL", encoding="utf-8")
            result = self.assemble({"input_refs": [str(p)]})
            self.assertEqual(result["task"]["input_refs"][0]["path"], str(p))
            self.assertNotIn("UNIQUE_PRIVATE_BODY_SENTINEL", json.dumps(result))
            self.assertNotIn("UNIQUE_PRIVATE_BODY_SENTINEL", context_prompt(result))

    def test_missing_required_input_is_explicit_and_optional_is_reported(self):
        with self.assertRaisesRegex(ContextError, "Required input"):
            self.assemble({"input_refs": ["missing.md"]})
        result = self.assemble({"input_refs": [{"path": "missing.md", "required": False}]})
        self.assertEqual(result["warnings"][0]["kind"], "optional_reference_missing")

    def test_maintenance_exclusion_does_not_disable_future_selected_articles(self):
        fixture = self.write("articles/fixture.md", "A temporary test article, not user data")
        result = self.assemble({"input_refs": [str(fixture)]})
        self.assertEqual(result["task"]["input_refs"][0]["path"], str(fixture))
        with self.assertRaisesRegex(ContextError, "excluded"):
            self.assemble({"input_refs": [str(fixture)]}, exclusions=[self.paths.articles])

    def test_scope_rejects_alias_into_excluded_directory(self):
        fixture = self.write("articles/fixture.md", "temporary")
        alias = self.root / "selected.md"
        alias.symlink_to(fixture)
        with self.assertRaisesRegex(ContextError, "excluded"):
            self.assemble({"input_refs": [str(alias)]}, exclusions=[self.paths.articles])

    def test_lexical_exclusion_is_rejected_before_filesystem_resolution(self):
        original_resolve = Path.resolve
        def guarded_resolve(path, *args, **kwargs):
            if "articles" in path.parts:
                raise AssertionError("Excluded path must not be resolved")
            return original_resolve(path, *args, **kwargs)
        with patch.object(Path, "resolve", guarded_resolve):
            with self.assertRaisesRegex(ContextError, "excluded"):
                self.assemble({"input_refs": [str(self.paths.articles / "unread.md")]}, exclusions=[self.paths.articles])

    def test_optional_method_is_loaded_only_when_selected(self):
        self.write(".agents/skills/optional/SKILL.md", "# optional method")
        self.registry["optional_capabilities"] = {"optional": {"kind": "production_optional", "structure": "skill", "entrypoint": ".agents/skills/optional/SKILL.md"}}
        self.save_registry()
        self.assertFalse(any("optional/SKILL.md" in item["path"] for item in self.assemble()["resources"]))
        result = self.assemble(skill_ids=["optional"])
        self.assertIn("optional", result["skill_ids"])
        self.assertTrue(any("optional/SKILL.md" in item["path"] for item in result["resources"]))

    def test_optional_bundle_requires_explicit_entrypoint(self):
        self.write(".agents/skills/bundle/tool/SKILL.md", "# selected tool")
        self.registry["optional_capabilities"] = {"bundle": {"kind": "production_optional", "structure": "bundle", "entrypoints": {"tool": ".agents/skills/bundle/tool/SKILL.md"}}}
        self.save_registry()
        with self.assertRaisesRegex(ContextError, "bundle entrypoint"):
            self.assemble(skill_ids=["bundle"])
        result = self.assemble(skill_ids=["bundle:tool"])
        self.assertTrue(any("bundle/tool/SKILL.md" in item["path"] for item in result["resources"]))

    def test_default_method_cannot_point_to_legacy_or_archive(self):
        for rel in ["agents/legacy/writer.md", "config/legacy/writer.md", "archive/writer.md"]:
            self.write(rel, "# old")
            self.registry["skills"]["writing"]["entrypoint"] = rel
            self.save_registry()
            with self.assertRaisesRegex(ContextError, "current project resources"):
                self.assemble()

    def test_title_does_not_load_natural_prose(self):
        result = self.assemble(mode="title")
        self.assertEqual(result["skill_ids"], ["writing"])

    def test_unspecified_and_explicit_empty_skills_have_different_meanings(self):
        default = self.assemble({"skill_ids": None})
        explicit = self.assemble({"skill_ids": []})
        self.assertIn("natural-prose", default["skill_ids"])
        self.assertEqual(explicit["skill_ids"], ["writing"])

    def test_current_policy_is_visible_and_old_draft_policy_can_be_preserved(self):
        current = self.assemble()
        replay = self.assemble({"metadata": {
            "prose_policy_revision": 1, "prose_structure_class": "sectioned_editorial",
        }})
        self.assertEqual(current["task"]["prose_policy_revision"], 2)
        self.assertEqual(replay["task"]["prose_policy_revision"], 1)
        self.assertEqual(replay["task"]["prose_structure_class"], "sectioned_editorial")
        self.assertNotIn("prose_policy_revision", self.assemble(mode="title")["task"])

    def test_reference_purpose_and_approval_provenance_reach_the_worker(self):
        draft = self.write("selected/draft.md", "ORIGINAL_BODY_SENTINEL")
        example = self.write("selected/edit-pair.md", "EXAMPLE_BODY_SENTINEL")
        selected = [
            {"path": str(draft), "purpose": "draft", "version_scope": "article_content"},
            {"path": str(example), "purpose": "approved_edit", "approval_ref": "feedback-42",
             "selection_reason": "The user accepted this way of joining repeated conclusions"},
        ]
        result = self.assemble({"input_refs": selected})
        refs = result["task"]["input_refs"]
        for original, resolved in zip(selected, refs):
            for key, value in original.items():
                self.assertEqual(resolved[key], value)
        prompt = context_prompt(result)
        self.assertIn("feedback-42", prompt)
        self.assertNotIn("EXAMPLE_BODY_SENTINEL", prompt)
        self.assertNotIn("ORIGINAL_BODY_SENTINEL", prompt)

    def test_reference_labels_do_not_fetch_or_confirm_external_sources(self):
        result = self.assemble({"input_refs": [{
            "url": "https://example.org/author-post", "purpose": "style_reference",
            "label": "A useful explanation, not author context",
        }]})
        ref = result["task"]["input_refs"][0]
        self.assertEqual(ref["purpose"], "style_reference")
        self.assertEqual(ref["verification"], "not_fetched")

    def test_custom_reference_purpose_remains_available_without_a_fixed_taxonomy(self):
        self.write("selected/source.md", "source")
        result = self.assemble({"input_refs": [{"path": "selected/source.md", "purpose": "reader-question"}]})
        self.assertEqual(result["task"]["input_refs"][0]["purpose"], "reader-question")

    def test_invalid_policy_revision_is_not_silently_replaced(self):
        with self.assertRaisesRegex(ContextError, "prose_policy_revision"):
            self.assemble({"metadata": {"prose_policy_revision": "2"}})

    def test_maintenance_is_not_an_implicit_production_method(self):
        with self.assertRaisesRegex(ContextError, "non-production skill"):
            self.assemble(skill_ids=["maintenance"])

    def test_invalid_mode_and_account_do_not_silently_use_defaults(self):
        with self.assertRaisesRegex(ContextError, "Unknown mode"):
            self.assemble(mode="legacy_v3")
        with self.assertRaisesRegex(ContextError, "Unknown account"):
            self.assemble(account_id="wrong-account")

    def test_independent_review_is_requirement_not_claimed_execution(self):
        result = assemble_context(self.paths, {}, role="reviewer")
        self.assertTrue(result["requires_independent_context"])
        self.assertFalse(result["load_policy"]["execution_started"])

    def test_directory_reference_is_not_expanded(self):
        selected = self.root / "selected-materials"
        selected.mkdir()
        (selected / "unrelated.txt").write_text("do not read")
        with patch.object(Path, "rglob", side_effect=AssertionError("Must not scan")), patch.object(Path, "iterdir", side_effect=AssertionError("Must not scan")):
            result = self.assemble({"input_refs": [str(selected)]})
        self.assertEqual(result["resources"][-1]["type"], "directory")
        self.assertFalse(result["load_policy"]["expand_directories"])

    def test_urls_remain_unfetched_source_references(self):
        result = self.assemble({"input_refs": ["https://example.org/docs"]})
        self.assertEqual(result["task"]["input_refs"][0]["verification"], "not_fetched")


if __name__ == "__main__":
    unittest.main()
