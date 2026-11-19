"""Behavior checks for the native structural auditor."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_skill.py"
SPEC = importlib.util.spec_from_file_location("native_audit_skill", SCRIPT)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class AuditSkillTests(unittest.TestCase):
    def test_missing_or_empty_target_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for target in (root / "missing", root):
                run = subprocess.run(
                    [sys.executable, str(SCRIPT), str(target), "--gate"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(run.returncode, 2)
                self.assertIn("ERROR:", run.stderr)

    def test_repository_budget_applies_to_agents_and_tool_skills(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for relative, count, expected_limit in (
                ("agents/workers/example", 351, 350),
                ("skills/example", 301, 300),
            ):
                directory = root / relative
                directory.mkdir(parents=True)
                skill = directory / "SKILL.md"
                skill.write_text(
                    "---\nname: example\ndescription: Example skill\n---\n"
                    + "body\n" * (count - 4),
                    encoding="utf-8",
                )
                with patch.object(AUDIT, "REPO_ROOT", root):
                    report = AUDIT.audit_one(skill)
                self.assertTrue(
                    any(
                        finding["severity"] == "ERROR"
                        and f"> {expected_limit}" in finding["msg"]
                        for finding in report["findings"]
                    )
                )

    def test_secret_finding_never_echoes_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            skill = directory / "SKILL.md"
            skill.write_text(
                "---\nname: example\ndescription: Example skill\n---\nbody\n",
                encoding="utf-8",
            )
            credential = "SENSITIVEVALUE123456"
            script_dir = directory / "scripts"
            script_dir.mkdir()
            (script_dir / "demo.py").write_text(
                "api" + "_key = '" + credential + "'  # example from provider\n",
                encoding="utf-8",
            )
            report = AUDIT.audit_one(skill)
            self.assertGreater(report["counts"]["ERROR"], 0)
            self.assertNotIn(credential, json.dumps(report))

    def test_invalid_required_frontmatter_types_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "SKILL.md"
            skill.write_text(
                "---\nname: []\ndescription: []\n---\nbody\n",
                encoding="utf-8",
            )
            report = AUDIT.audit_one(skill)
            self.assertGreaterEqual(report["counts"]["ERROR"], 2)

    def test_yaml_syntax_types_lengths_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "SKILL.md"
            invalid_frontmatters = (
                "name: example\ndescription: [one, two",
                "name: example\ndescription:\n  - one",
                "name: example\ndescription:\n  nested: value",
                "name: " + "a" * 65 + "\ndescription: valid",
                "name: example\ndescription: " + "x" * 1025,
                "name: example\nname: other\ndescription: valid",
                "name: example\ndescription: '[TODO: fill]'",
            )
            for frontmatter in invalid_frontmatters:
                with self.subTest(frontmatter=frontmatter[:30]):
                    skill.write_text(f"---\n{frontmatter}\n---\nbody\n", encoding="utf-8")
                    self.assertGreater(AUDIT.audit_one(skill)["counts"]["ERROR"], 0)
            skill.write_text(
                "---\nname: example # comment\ndescription: valid\n---\nbody\n",
                encoding="utf-8",
            )
            self.assertEqual(AUDIT.audit_one(skill)["counts"]["ERROR"], 0)
            skill.write_text(
                "---\nname: example\ndescription: valid\nmetadata:\n"
                "  base: &base {foo: bar}\n  merged:\n    <<: *base\n"
                "---\nbody\n",
                encoding="utf-8",
            )
            self.assertEqual(AUDIT.audit_one(skill)["counts"]["ERROR"], 0)

    def test_negative_tool_mention_and_risky_operation(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            skill = directory / "SKILL.md"
            skill.write_text(
                "---\nname: example\ndescription: Example skill\n---\n"
                "Never call TaskCreate.\n",
                encoding="utf-8",
            )
            script_dir = directory / "scripts"
            script_dir.mkdir()
            (script_dir / "demo.sh").write_text(
                "# no backup available\n" + "rm " + "-rf \"$target\"\n",
                encoding="utf-8",
            )
            report = AUDIT.audit_one(skill)
            self.assertEqual(report["counts"]["ERROR"], 0)
            self.assertTrue(
                any("危险操作" in item["msg"] for item in report["findings"])
            )

    def test_bare_secret_and_escaping_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "example"
            directory.mkdir()
            skill = directory / "SKILL.md"
            skill.write_text(
                "---\nname: example\ndescription: Example skill\n---\nbody\n",
                encoding="utf-8",
            )
            script_dir = directory / "scripts"
            script_dir.mkdir()
            credential = "SENSITIVEVALUE123456"
            (script_dir / "demo.sh").write_text(
                "API" + "_KEY=" + credential + "\n", encoding="utf-8"
            )
            (script_dir / "demo.mjs").write_text(
                "const api" + "Key = '" + credential + "';\n", encoding="utf-8"
            )
            (script_dir / "reference.py").write_text(
                "api_key = loaded_secret_token\n", encoding="utf-8"
            )
            outside = root / "outside.py"
            outside.write_text("outside\n", encoding="utf-8")
            (script_dir / "link.py").symlink_to(outside)
            report = AUDIT.audit_one(skill)
            messages = [item["msg"] for item in report["findings"]]
            self.assertTrue(any("疑似硬编码密钥 scripts/demo.sh" in msg for msg in messages))
            self.assertTrue(any("疑似硬编码密钥 scripts/demo.mjs" in msg for msg in messages))
            self.assertTrue(any("脚本符号链接越界 scripts/link.py" in msg for msg in messages))
            self.assertFalse(any("reference.py" in msg for msg in messages))
            self.assertNotIn(credential, json.dumps(report))

    def test_broken_and_directory_script_symlinks_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "example"
            directory.mkdir()
            (directory / "SKILL.md").write_text(
                "---\nname: example\ndescription: Example skill\n---\nbody\n",
                encoding="utf-8",
            )
            scripts = directory / "scripts"
            scripts.mkdir()
            (scripts / "broken.py").symlink_to(root / "missing.py")
            self.assertTrue(
                any("符号链接失效" in msg for _, msg in AUDIT.scan_scripts(directory))
            )
            (scripts / "broken.py").unlink()
            scripts.rmdir()
            outside = root / "outside"
            outside.mkdir()
            (directory / "scripts").symlink_to(outside, target_is_directory=True)
            self.assertTrue(
                any("符号链接越界" in msg for _, msg in AUDIT.scan_scripts(directory))
            )

    def test_entry_symlink_and_invalid_budget_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            directory = root / "repo/skills/example"
            directory.mkdir(parents=True)
            outside = root / "outside.md"
            outside.write_text(
                "---\nname: example\ndescription: Example skill\n---\nbody\n",
                encoding="utf-8",
            )
            skill = directory / "SKILL.md"
            skill.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "符号链接越界"):
                AUDIT.audit_one(skill)
            skill.unlink()
            skill.write_text(outside.read_text(encoding="utf-8"), encoding="utf-8")
            budget_path = root / "budget.yaml"
            budget_path.write_text("budgets: []\n", encoding="utf-8")
            with patch.object(AUDIT, "REPO_ROOT", root / "repo"), patch.object(
                AUDIT, "BUDGET_PATH", budget_path
            ):
                with self.assertRaisesRegex(ValueError, "预算缺少"):
                    AUDIT.audit_one(skill)

    def test_invalid_utf8_skill_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "SKILL.md"
            skill.write_bytes(
                b"---\nname: example\ndescription: Example skill\n---\nbody \xff\n"
            )
            run = subprocess.run(
                [sys.executable, str(SCRIPT), str(skill), "--gate"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 2)
            self.assertIn("ERROR:", run.stderr)


if __name__ == "__main__":
    unittest.main()
