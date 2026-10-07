"""Synthetic mounted profiles; never inspect the computer's Windows user data."""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import bootstrap
import cli
from relay import registry, windows
from relay.adapters.codex import CodexAdapter
from relay.adapters.claude import ClaudeAdapter
from relay.adapters.workbuddy import WorkBuddyAdapter
from test_relay import sample, content
import test_sources


class WindowsProfilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profile = self.root / "Win volume" / "Users" / "中文 user"
        self.profile.mkdir(parents=True)
        for cls, folder in ((CodexAdapter, ".codex"), (ClaudeAdapter, ".claude"),
                            (WorkBuddyAdapter, ".workbuddy")):
            cls(home=str(self.profile / folder)).write(sample(), session_id="fixture")
        WorkBuddyAdapter(home=str(self.profile / ".codebuddy")).write(sample(), session_id="cli")
        test_sources.CodeBuddyTests().fixture(str(self.profile / "AppData/Local/CodeBuddyExtension/Data"))
        test_sources.write_log(self.profile / ".dsh", test_sources.log())
        self.env = patch.dict(os.environ, {windows.PROFILE_ENV: str(self.profile)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.system = patch.object(windows.platform, "system", return_value="Linux")
        self.system.start()
        self.addCleanup(self.system.stop)
        self.cache = patch.dict(registry._CACHE, {}, clear=True)
        self.cache.start()
        self.addCleanup(self.cache.stop)

    def test_discovery_deduplicates_mounts_and_lists_profiles_with_agent_data(self):
        (self.profile.parent / "Default").mkdir()
        rows = windows.discover_profiles([self.root / "Win volume", self.root / "Win volume"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user"], "中文 user")
        self.assertEqual(set(rows[0]["sources"]), set(bootstrap.SOURCES))

    def test_six_windows_sources_read_export_without_touching_source_files(self):
        before = {p: p.read_bytes() for p in self.profile.rglob("*") if p.is_file()}
        self.assertEqual(len(registry.all_keys()), 12)
        for native in bootstrap.SOURCES:
            key = "windows_" + native
            adapter = registry.get(key)
            rows = registry.list_sessions(key)
            self.assertTrue(rows, key)
            self.assertEqual(len(rows), 2 if native == "codebuddy" else 1)
            self.assertTrue(all(row["source"] == key for row in rows))
            for row in rows:
                conv = registry.read_conversation(key, row["id"])
                self.assertEqual(conv.source, key)
                self.assertTrue(conv.turns)
                self.assertIn("Windows", registry.export_markdown(key, row["id"]))
            self.assertFalse(adapter.info()["can_write"])
            with self.assertRaises(ValueError):
                adapter.write(sample())
            with self.assertRaisesRegex(ValueError, "迁移目标"):
                registry.transfer("codex", "missing", key)
        self.assertEqual(registry.writable_keys(), ["workbuddy", "claude", "codex"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.profile.rglob("*") if p.is_file()})
        self.assertTrue(registry.get("codex").root.endswith(".codex"))
        self.assertNotEqual(registry.get("codex").root, str(self.profile / ".codex"))

    def test_windows_migration_requires_native_cwd_and_preserves_content(self):
        key = "windows_codex"
        src = registry.get(key)
        sid = next(src.discover()).id
        dst = registry.get("claude", home=str(self.root / "linux-claude"))
        with patch.dict(registry._CACHE, {"claude": dst}):
            for cwd in (None, "C:\\project", "relative", str(self.root / "missing")):
                with self.assertRaisesRegex(ValueError, "Ubuntu 项目目录"):
                    registry.transfer(key, sid, "claude", cwd=cwd)
            registry.transfer(key, sid, "claude", cwd=str(self.root), session_id="migrated")
        conv = dst.read("migrated")
        self.assertEqual(conv.cwd.replace("\\", "/"), str(self.root).replace("\\", "/"))
        self.assertEqual(content(conv), content(src.read(sid)))

    def test_missing_mount_stays_visible_and_profile_changes_invalidate_cache(self):
        first = registry.get("windows_codex")
        with patch.dict(os.environ, {windows.PROFILE_ENV: str(self.root / "missing")}):
            current = registry.get("windows_codex")
            self.assertIsNot(first, current)
            self.assertFalse(current.available())
            self.assertIn("挂载", current.info()["error"])
            self.assertEqual(registry.list_sessions("windows_codex"), [])

    def test_selection_is_ignored_when_booting_windows_or_macos(self):
        for system in ("Windows", "Darwin"):
            with patch.object(windows.platform, "system", return_value=system):
                self.assertEqual(windows.selected_profile(), "")
                self.assertEqual(registry.all_keys(), list(bootstrap.SOURCES))
                self.assertEqual(windows.discover_profiles([self.root / "Win volume"]), [])

    def test_config_update_preserves_fields_clear_and_temporary_override(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"port": 9876, "open_browser": False,
                                     "agent_homes": {"claude": "custom"}}), encoding="utf-8")
        with patch.object(bootstrap, "config_path", return_value=config), redirect_stdout(io.StringIO()):
            cli.cmd_windows_use(SimpleNamespace(path=str(self.profile), clear=False))
            saved = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(saved["port"], 9876)
            self.assertEqual(saved["agent_homes"], {"claude": "custom"})
            self.assertEqual(saved["windows_user_home"], str(self.profile))
            cli.cmd_windows_use(SimpleNamespace(path=None, clear=True))
            self.assertEqual(json.loads(config.read_text())["windows_user_home"], "")
            config.write_text("broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                cli.cmd_windows_use(SimpleNamespace(path=str(self.profile), clear=False))
            self.assertEqual(config.read_text(), "broken")
        with patch.object(cli, "_CFG", {}), patch.object(cli, "cmd_doctor", return_value=0) as doctor:
            self.assertEqual(cli.main(["doctor", "--windows-user", str(self.profile)]), 0)
            self.assertEqual(cli._CFG["windows_user_home"], str(self.profile))
            doctor.assert_called_once()

    def test_mountinfo_escapes_are_decoded_without_scanning_entire_disks(self):
        with patch.object(windows.Path, "read_text", return_value=
                          "12 1 8:3 / /media/user/Win\\040Volume rw - ntfs3 /dev/sda3 rw\n"), \
             patch.object(windows.Path, "iterdir", side_effect=PermissionError):
            self.assertIn(Path("/media/user/Win Volume"), windows.mounted_roots())

    def test_relative_or_windows_drive_selection_is_rejected(self):
        values = ["relative/profile"]
        if os.name != "nt":
            values.append("C:\\Users\\Alice")
        for value in values:
            with patch.dict(os.environ, {windows.PROFILE_ENV: value}), \
                 self.assertRaisesRegex(ValueError, "绝对挂载路径"):
                windows.selected_profile()


if __name__ == "__main__":
    unittest.main()
