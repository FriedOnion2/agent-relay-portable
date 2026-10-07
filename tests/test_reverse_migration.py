"""Bidirectional native migrations with isolated Windows and Ubuntu stores."""
import io
import json
import os
import shutil
import uuid
import unittest
from contextlib import redirect_stdout, ExitStack
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import test_native_import
from test_relay import content
from relay import registry, native_import, windows, ubuntu
import cli
import bootstrap


class ReverseMigrationTests(unittest.TestCase):
    setUp = test_native_import.NativeImportTests.setUp
    snapshot = test_native_import.NativeImportTests.snapshot
    make_ide_workspace = test_native_import.NativeImportTests.make_ide_workspace

    def seed_local(self):
        self.make_ide_workspace()
        imported = []
        for key in cli.AGENTS:
            for row in registry.list_sessions("windows_" + key):
                result = native_import.import_windows(key, row["id"], str(self.cwd))
                imported.append((key, result["to"]["id"]))
        return imported

    def windows_ide_cwd(self, cwd):
        target = registry.get("windows_codebuddy").adapter
        row = next(row for row in target.discover() if row.id.startswith("ide:"))
        directory = Path(row.path).parent
        for path in (directory / "messages").glob("*.json"):
            env = json.loads(path.read_text(encoding="utf-8"))
            native_import._ide_user_workspace(env, "/fixture", cwd)
            path.write_text(json.dumps(env, ensure_ascii=False), encoding="utf-8")

    def test_six_agents_and_both_codebuddy_formats_roundtrip_without_source_edits(self):
        imported = self.seed_local()
        cwd = "D:\\Projects\\中文 space's repo"
        self.windows_ide_cwd(cwd)
        before = self.snapshot(self.root / "ubuntu")
        for key, sid in imported:
            with self.subTest(agent=key, sid=sid):
                original = registry.get(key).read(sid)
                new_id = str(uuid.uuid5(uuid.NAMESPACE_URL, key + sid))
                result = native_import.export_windows(key, sid, cwd, project_path=str(self.cwd), session_id=new_id)
                self.assertEqual(result["mode"], "native-windows-export")
                self.assertEqual(result["to"]["source"], "windows_" + key)
                dest = registry.get("windows_" + key).read(result["to"]["id"])
                self.assertEqual(content(original), content(dest))
                self.assertEqual(dest.cwd.replace("/", "\\"), cwd)
                if key in ("claude", "codex"):
                    self.assertIn("Set-Location -LiteralPath 'D:\\Projects\\中文 space''s repo'", result["resume_command"])
                with self.assertRaises(FileExistsError):
                    native_import.export_windows(key, sid, cwd, project_path=str(self.cwd), session_id=new_id)
        self.assertEqual(before, self.snapshot(self.root / "ubuntu"))
        self.assertEqual(registry.writable_keys(), ["workbuddy", "claude", "codex"])

    def test_windows_imports_accessible_ubuntu_home_and_linux_ide_layout(self):
        # Treat the synthetic source as a copied Ubuntu home, including its IDE layout.
        backup = self.root / "Ubuntu backup"
        shutil.copytree(self.profile, backup)
        shutil.move(str(backup / "AppData/Local/CodeBuddyExtension/Data"), str(backup / "ide-data"))
        (backup / ".config/CodeBuddyExtension").mkdir(parents=True)
        shutil.move(str(backup / "ide-data"), str(backup / ".config/CodeBuddyExtension/Data"))
        before = self.snapshot(backup)
        self.make_ide_workspace()
        # On actual Windows this exercises cwd existence; POSIX fixtures cannot
        # represent a Windows drive, so only that host-specific check is mocked.
        cwd = str(self.cwd) if os.name == "nt" else "D:\\Projects\\target"
        target = self.targets["codebuddy"]
        ide = next(row for row in target.discover() if row.id.startswith("ide:"))
        for path in (Path(ide.path).parent / "messages").glob("*.json"):
            env = json.loads(path.read_text(encoding="utf-8"))
            native_import._ide_user_workspace(env, str(self.cwd).replace("\\", "/"), cwd)
            path.write_text(json.dumps(env), encoding="utf-8")
        with ExitStack() as stack:
            stack.enter_context(patch.object(windows.platform, "system", return_value="Windows"))
            stack.enter_context(patch.dict(os.environ, {ubuntu.PROFILE_ENV: str(backup)}))
            if os.name != "nt":
                stack.enter_context(patch.object(native_import, "_windows_cwd", return_value=cwd))
            registry._CACHE.update(self.targets)
            self.assertEqual(len(registry.all_keys()), 12)
            self.assertFalse(any(k.startswith("windows_") for k in registry.all_keys()))
            for key in cli.AGENTS:
                for row in registry.list_sessions("ubuntu_" + key):
                    result = native_import.import_ubuntu(key, row["id"], cwd,
                                session_id=str(uuid.uuid5(uuid.NAMESPACE_URL, key + row["id"])))
                    self.assertEqual(content(registry.get("ubuntu_" + key).read(row["id"])),
                                     content(registry.get(key).read(result["to"]["id"])))
                    self.assertEqual(result["target_os"], "Windows")
                    self.assertEqual(registry.get(key).read(result["to"]["id"]).cwd.replace("/", "\\"), cwd)
            self.assertNotIn("windows_profile", registry.get("ubuntu_codex").info())
        self.assertEqual(before, self.snapshot(backup))

    def test_path_validation_and_metadata_subpaths_do_not_rewrite_tool_arguments(self):
        for cwd in ("/mnt/data/project", "D:relative", "\\relative", "D:\\bad\nname", "D:\\bad?name", "D:\\bad. "):
            with self.assertRaises(ValueError):
                native_import._windows_cwd(cwd, str(self.cwd))
        for path in (None, "relative", str(self.root / "missing")):
            with self.assertRaises(ValueError):
                native_import._windows_cwd("D:\\project", path)
        self.assertEqual(native_import._windows_cwd("D:/project/../target", str(self.cwd)), "D:\\target")
        row = {"cwd":"/home/a/p", "writable_roots":["/home/a/p/sub", "/home/a/other"],
               "arguments":{"path":"/home/a/p/sub"}}
        native_import._metadata(row, "/home/a/p", "D:\\p", "new", "old")
        self.assertEqual(row["writable_roots"], ["D:\\p\\sub", "/home/a/other"])
        self.assertEqual(row["arguments"]["path"], "/home/a/p/sub")

    def test_reverse_codex_index_failure_rolls_back_only_new_rollout(self):
        sid = native_import.import_windows("codex", registry.list_sessions("windows_codex")[0]["id"], str(self.cwd))["to"]["id"]
        target = registry.get("windows_codex").adapter
        Path(self.targets["codex"].index_path).write_text(json.dumps({"id":sid,"thread_name":"title"}) + "\n", encoding="utf-8")
        before = self.snapshot(self.profile)
        real = native_import.atomic_write
        def fail_index(path, *args, **kw):
            if Path(path) == Path(target.index_path):
                raise OSError("index failure")
            return real(path, *args, **kw)
        with patch.object(native_import, "atomic_write", side_effect=fail_index), self.assertRaises(OSError):
            native_import.export_windows("codex", sid, "D:\\p", str(self.cwd), session_id=str(uuid.uuid4()))
        self.assertEqual(before, self.snapshot(self.profile))

    def test_source_target_overlap_and_missing_profile_refuse_writes(self):
        sid = native_import.import_windows("codex", registry.list_sessions("windows_codex")[0]["id"], str(self.cwd))["to"]["id"]
        registry._CACHE["codex"] = registry.get("windows_codex").adapter
        with self.assertRaisesRegex(ValueError, "来源重叠"):
            native_import.export_windows("codex", sid, "D:\\p", str(self.cwd))
        with patch.dict(os.environ, {windows.PROFILE_ENV:str(self.root / "missing")}), self.assertRaises(ValueError):
            native_import.export_windows("codex", sid, "D:\\p", str(self.cwd))

    def test_ubuntu_selection_config_and_platform_scope(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"extra":"keep", "windows_user_home":"/mnt/w"}), encoding="utf-8")
        with patch.object(windows.platform, "system", return_value="Windows"), patch.object(bootstrap, "config_path", return_value=config), redirect_stdout(io.StringIO()):
            cli.cmd_windows_use(SimpleNamespace(cmd="ubuntu-use", path=str(self.root), clear=False))
            self.assertEqual(ubuntu.selected_profile(), str(self.root))
            saved = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(saved["extra"], "keep")
            self.assertEqual(saved["windows_user_home"], "/mnt/w")
            cli.cmd_windows_use(SimpleNamespace(cmd="ubuntu-use", path=None, clear=True))
            self.assertEqual(ubuntu.selected_profile(), "")
        with patch.dict(os.environ, {ubuntu.PROFILE_ENV:str(self.root)}):
            self.assertEqual(ubuntu.selected_profile(), "")

    def test_reverse_cli_routes_and_keeps_original_id_when_possible(self):
        sid = native_import.import_windows("codex", registry.list_sessions("windows_codex")[0]["id"], str(self.cwd))["to"]["id"]
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(["export-windows", "codex", sid, "--cwd", "D:\\p", "--project-path", str(self.cwd),
                             "--session-id", str(uuid.uuid4()), "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["mode"], "native-windows-export")
