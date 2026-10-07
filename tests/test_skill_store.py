"""Skill transfers preserve data and executable scripts without running them."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_native_import
from relay import archive, skill_store, registry
import cli


class SkillStoreTests(unittest.TestCase):
    setUp = test_native_import.NativeImportTests.setUp
    snapshot = test_native_import.NativeImportTests.snapshot

    def fixture(self, base=None, name="sample-skill"):
        directory = (base or self.root / "source-skills") / name
        (directory / "scripts").mkdir(parents=True)
        (directory / "references").mkdir()
        (directory / "SKILL.md").write_text("---\nname: sample-skill\n---\nInstructions are data.\n", encoding="utf-8")
        (directory / "scripts/run.sh").write_bytes(b"#!/bin/sh\nprintf 'fixture only'\n")
        (directory / "references/data.bin").write_bytes(bytes(range(256)))
        return directory

    def test_complete_skill_transfer_preserves_files_excludes_credentials_and_sets_script_mode(self):
        source = self.fixture()
        (source / ".env").write_text("fixture secret", encoding="utf-8")
        (source / "auth.json").write_text("fixture token", encoding="utf-8")
        (source / ".git").mkdir()
        (source / ".git/config").write_text("fixture", encoding="utf-8")
        before = self.snapshot(source)
        result = skill_store.store_skill("codex", str(source), self.root / "storage")
        self.assertEqual(Path(result["path"]).parent.name, "codex")
        manifest, files = archive.read_package(result["path"], skill_store.KIND)
        self.assertEqual(set(files), {"skill/SKILL.md", "skill/scripts/run.sh", "skill/references/data.bin"})
        self.assertEqual(set(manifest["excluded"]), {".env", "auth.json", ".git/"})
        restored = skill_store.restore_skill(result["path"], skills_dir=str(self.root / "new-device"))
        target = Path(restored["path"])
        for relative in ("SKILL.md", "scripts/run.sh", "references/data.bin"):
            self.assertEqual((target / relative).read_bytes(), (source / relative).read_bytes())
        if os.name != "nt":
            self.assertTrue((target / "scripts/run.sh").stat().st_mode & 0o111)
        self.assertEqual(before, self.snapshot(source))

    def test_collision_refuses_even_empty_directory_and_can_restore_to_other_agent_with_new_name(self):
        source = self.fixture()
        package = skill_store.store_skill("claude", str(source), self.root / "storage")["path"]
        target = self.root / "skills"
        (target / source.name).mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            skill_store.restore_skill(package, skills_dir=str(target))
        result = skill_store.restore_skill(package, agent="codex", skills_dir=str(target), name="copy")
        self.assertEqual(result["agent"], "codex")
        self.assertEqual((target / "copy/SKILL.md").read_bytes(), (source / "SKILL.md").read_bytes())
        before = self.snapshot(target)
        with self.assertRaises(FileExistsError):
            skill_store.restore_skill(package, agent="codex", skills_dir=str(target), name="copy")
        self.assertEqual(before, self.snapshot(target))

    def test_batch_discovery_cli_listing_and_moved_store(self):
        source = self.fixture()
        self.fixture(name="another")
        (source.parent / "not-a-skill").mkdir()
        output = io.StringIO()
        storage = self.root / "storage"
        with redirect_stdout(output):
            code = cli.main(["store-skills", "claude", "--all", "--skills-dir", str(source.parent), "--storage", str(storage)])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(output.getvalue())["stored"]), 2)
        moved = self.root / "copied-device-store"
        storage.rename(moved)
        self.assertEqual(len(archive.list_packages(skill_store.KIND, "claude", moved)), 2)
        self.assertEqual(len(skill_store.discover_skills("claude", str(source.parent))["skills"]), 2)

    def test_default_roots_respect_agent_homes_and_foreign_profiles(self):
        self.assertEqual(skill_store.skill_roots("claude"), [Path(self.targets["claude"].root).resolve() / "skills"])
        with patch.object(skill_store.Path, "home", return_value=self.root / "user"):
            roots = skill_store.skill_roots("codex")
        self.assertEqual(roots[0], (self.root / "user/.agents/skills").resolve())
        self.assertEqual(roots[1], Path(self.targets["codex"].root).resolve() / "skills")
        self.assertEqual(skill_store.skill_roots("windows_codex")[0], self.profile.resolve() / ".agents/skills")
        self.assertEqual(skill_store.skill_roots("windows_claude")[0], self.profile.resolve() / ".claude/skills")

    def test_invalid_names_missing_descriptor_and_wrong_package_type_never_create_target(self):
        source = self.fixture()
        package = skill_store.store_skill("codex", str(source), self.root / "storage")["path"]
        target = self.root / "destination"
        for name in ("../escape", "nested/name", "CON", ".hidden", "name."):
            with self.assertRaises(ValueError):
                skill_store.restore_skill(package, skills_dir=str(target), name=name)
        self.assertFalse(target.exists())
        wrong = self.root / "wrong.zip"
        archive.write_package(wrong, {"kind":"agentrelay-session"}, {"skill/SKILL.md":(b"x",False)})
        with self.assertRaises(ValueError):
            skill_store.restore_skill(wrong, skills_dir=str(target))
        (source / "SKILL.md").unlink()
        with self.assertRaises(ValueError):
            skill_store.store_skill("codex", str(source), self.root / "storage")

    def test_install_failure_rolls_back_new_directory_without_removing_existing_skills(self):
        source = self.fixture()
        package = skill_store.store_skill("codex", str(source), self.root / "storage")["path"]
        target = self.root / "destination"
        (target / "existing").mkdir(parents=True)
        (target / "existing/SKILL.md").write_text("keep", encoding="utf-8")
        before = self.snapshot(target)
        with patch.object(skill_store.os, "rename", side_effect=OSError("publication failure")), self.assertRaises(OSError):
            skill_store.restore_skill(package, skills_dir=str(target))
        self.assertEqual(before, self.snapshot(target))
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["existing"])
        skill_store.restore_skill(package, skills_dir=str(target))

    def test_symbolic_links_are_rejected_without_collecting_external_files(self):
        source = self.fixture()
        outside = self.root / "outside.txt"
        outside.write_text("never packed", encoding="utf-8")
        try:
            (source / "link").symlink_to(outside)
        except OSError:
            self.skipTest("symlink creation unavailable")
        storage = self.root / "storage"
        with self.assertRaisesRegex(ValueError, "符号链接"):
            skill_store.store_skill("codex", str(source), storage)
        self.assertFalse(storage.exists())

    def test_windows_reparse_points_are_rejected_before_file_content_is_read(self):
        source = self.fixture()
        with patch.object(archive.Path, "lstat", return_value=SimpleNamespace(st_mode=0o100644, st_file_attributes=0x400)), self.assertRaises(ValueError):
            archive.read_file(source / "SKILL.md")
