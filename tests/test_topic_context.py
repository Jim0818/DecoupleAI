"""Discovery context regressions use isolated files, never live content trees."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from textpicos.context import ContextError, account_file_names, assemble_context


def make_project(tmp_path):
    production = json.loads(
        (Path(__file__).resolve().parents[1] / "config/system/capabilities.json")
        .read_text(encoding="utf-8")
    )
    registry = {
        "orchestration_mode": "supervisor",
        "roles": {"research": deepcopy(production["roles"]["research"])},
        "skills": {"research": deepcopy(production["skills"]["research"])},
        "accounts": {
            name: {"directory": f"config/accounts/{name}"}
            for name in ("studio", "intellifuture")
        },
    }

    def write(relative, content="fixture content"):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination

    role = registry["roles"]["research"]
    skill = registry["skills"]["research"]
    write(role["entrypoint"])
    write(skill["entrypoint"])
    for ref in role.get("policy_refs", []):
        write(ref if isinstance(ref, str) else ref["path"])
    for refs in skill.get("mode_refs", {}).values():
        for ref in refs:
            write(ref if isinstance(ref, str) else ref["path"])
    write("config/accounts/studio/L1_identity.md")
    write("config/accounts/studio/L2_values.md")

    def save():
        write("config/system/capabilities.json", json.dumps(registry))

    def assemble(mode="discover", **kwargs):
        save()
        paths = SimpleNamespace(root=tmp_path, config=tmp_path / "config")
        return assemble_context(
            paths, {"role": "research", "mode": mode, "account_id": "studio", **kwargs}
        )

    return SimpleNamespace(
        root=tmp_path, registry=registry, role=role, write=write,
        assemble=assemble, save=save,
    )


def account_names(context):
    return [Path(item["path"]).name for item in context["resources"] if item["kind"] == "account"]


class TopicContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = make_project(Path(self.temp.name))

    def test_current_discover_loads_l1_and_l2_without_other_accounts(self):
        result = self.project.assemble()
        self.assertEqual(account_names(result), ["L1_identity.md", "L2_values.md"])
        self.assertFalse(any("intellifuture" in item["path"] for item in result["resources"]))

    def test_other_research_modes_keep_their_existing_account_context(self):
        for mode in ("research", "verify"):
            with self.subTest(mode=mode):
                self.assertEqual(account_names(self.project.assemble(mode)), ["L1_identity.md"])

    def test_missing_or_empty_mode_list_keeps_role_resources(self):
        for definition in ({}, {"account_files": []}):
            with self.subTest(definition=definition):
                self.project.role["modes"]["discover"] = definition
                self.assertEqual(account_names(self.project.assemble()), ["L1_identity.md"])

    def test_mode_merge_deduplicates_names_and_resolved_aliases(self):
        (self.project.root / "config/accounts/studio/identity-alias.md").symlink_to("L1_identity.md")
        self.project.role["modes"]["discover"]["account_files"] = [
            "L1_identity.md", "identity-alias.md", "L2_values.md", "L2_values.md",
        ]
        result = self.project.assemble()
        self.assertEqual(account_names(result), ["L1_identity.md", "L2_values.md"])
        identity = next(item for item in result["resources"] if item["id"] == "account:studio:L1_identity.md")
        self.assertIn("account:studio:identity-alias.md", identity["ids"])

    def test_missing_discover_resource_fails_without_affecting_other_modes(self):
        (self.project.root / "config/accounts/studio/L2_values.md").unlink()
        with self.assertRaisesRegex(ContextError, "Required account does not exist"):
            self.project.assemble()
        self.assertEqual(account_names(self.project.assemble("verify")), ["L1_identity.md"])

    def test_bad_mode_account_resources_fail_explicitly(self):
        for invalid in (None, "L2_values.md", {}, [None], [""], ["../other/L2.md"],
                        ["/tmp/outside.md"], ["https://example.org/file"], ["bad\x00name"]):
            with self.subTest(invalid=invalid):
                self.project.role["modes"]["discover"]["account_files"] = invalid
                with self.assertRaisesRegex(ContextError, r"roles\.research\.modes\.discover\.account_files"):
                    self.project.assemble()

    def test_bad_role_account_resources_fail_explicitly(self):
        for invalid in (None, "L1_identity.md", [42]):
            with self.subTest(invalid=invalid):
                self.project.role["account_files"] = invalid
                with self.assertRaisesRegex(ContextError, r"roles\.research\.account_files"):
                    self.project.assemble()

    def test_bad_role_or_mode_definitions_are_context_errors(self):
        original = deepcopy(self.project.role)
        for field in ("role", "modes", "discover"):
            with self.subTest(field=field):
                role = deepcopy(original)
                self.project.registry["roles"]["research"] = role
                if field == "role":
                    self.project.registry["roles"]["research"] = None
                elif field == "modes":
                    role["modes"] = None
                else:
                    role["modes"]["discover"] = None
                with self.assertRaisesRegex(ContextError, "must be a mapping"):
                    self.project.assemble()

    def test_mode_resource_cannot_escape_project_through_a_symlink(self):
        with TemporaryDirectory() as external:
            target = Path(external) / "external.md"
            target.write_text("external fixture", encoding="utf-8")
            l2 = self.project.root / "config/accounts/studio/L2_values.md"
            l2.unlink()
            l2.symlink_to(target)
            with self.assertRaisesRegex(ContextError, "current project resources"):
                self.project.assemble()

    def test_mode_account_resource_preserves_maintenance_exclusions(self):
        paths = SimpleNamespace(root=self.project.root, config=self.project.root / "config")
        l2 = self.project.root / "config/accounts/studio/L2_values.md"
        self.project.save()
        original_resolve = Path.resolve

        def guarded_resolve(path, *args, **kwargs):
            if path == l2:
                raise AssertionError("Excluded resource was probed")
            return original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", guarded_resolve):
            with self.assertRaisesRegex(ContextError, "excluded from this operation"):
                assemble_context(paths, {"role": "research", "mode": "discover", "account_id": "studio"}, exclusions=[l2])

    def test_selected_scope_is_a_reference_not_an_expanded_library(self):
        chosen = self.project.write("resources/selected-topic-scope.md", "PRIVATE_SCOPE_SENTINEL")
        self.project.write("resources/unselected-topic-scope.md", "unselected")
        result = self.project.assemble(input_refs=[{"path": str(chosen), "purpose": "topic_scope"}])
        self.assertEqual(result["task"]["input_refs"][0]["purpose"], "topic_scope")
        self.assertNotIn("PRIVATE_SCOPE_SENTINEL", json.dumps(result))
        self.assertFalse(any("unselected-topic-scope" in item["path"] for item in result["resources"]))
        self.assertFalse(result["load_policy"]["expand_directories"])

    def test_account_file_validation_is_side_effect_free(self):
        with patch.object(Path, "stat", side_effect=AssertionError("Unexpected filesystem probe")):
            self.assertEqual(account_file_names({}, "role"), [])
            self.assertEqual(
                account_file_names({"account_files": ["L1.md", "L1.md", "detail/scope.md"]}, "role"),
                ["L1.md", "detail/scope.md"],
            )
