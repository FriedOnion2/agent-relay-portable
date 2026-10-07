"""Packages travel without source homes; corrupt packages never touch target stores."""
import io
import json
import os
import shutil
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

import test_native_import
from test_relay import content
from test_dsh_write import conversation
from relay import archive, registry, session_store, native_import
import cli


class SessionStoreTests(unittest.TestCase):
    setUp = test_native_import.NativeImportTests.setUp
    snapshot = test_native_import.NativeImportTests.snapshot
    make_ide_workspace = test_native_import.NativeImportTests.make_ide_workspace

    def test_every_agent_and_codebuddy_format_restore_from_only_a_moved_package(self):
        self.make_ide_workspace()
        before = self.snapshot(self.profile)
        storage = self.root / "portable storage"
        for agent in cli.AGENTS:
            for row in registry.list_sessions("windows_" + agent):
                with self.subTest(agent=agent, id=row["id"]):
                    conv = registry.get("windows_" + agent).read(row["id"])
                    result = session_store.store_session("windows_" + agent, row["id"], storage)
                    self.assertEqual(Path(result["path"]).parent.name, agent)
                    manifest, files = archive.read_package(result["path"], session_store.KIND)
                    self.assertEqual(manifest["agent"], agent)
                    self.assertFalse(any("auth.json" in name or "config" in name for name in files))
                    # The importer sees only its verified temporary source, not
                    # the original mounted home or an environment fallback.
                    with patch.dict(registry._CACHE, self.targets, clear=True):
                        restored = session_store.restore_session(result["path"], str(self.cwd), session_id=str(uuid.uuid4()))
                    dest = registry.get(agent).read(restored["to"]["id"])
                    self.assertEqual(content(conv), content(dest))
                    self.assertEqual(restored["from"]["path"], str(Path(result["path"]).resolve()))
                    self.assertEqual(dest.cwd.replace("\\", "/"), str(self.cwd).replace("\\", "/"))
        self.assertEqual(before, self.snapshot(self.profile))
        moved = self.root / "other-device-storage"
        shutil.move(str(storage), str(moved))
        rows = archive.list_packages(session_store.KIND, root=moved)
        self.assertEqual(len(rows), 7)

    def test_dsh_seed_writer_can_be_stored_and_restored_without_ir_conversion(self):
        source = self.targets["dsh"]
        source.write(conversation(), cwd=str(self.cwd), session_id="seed")
        result = session_store.store_session("dsh", "seed", self.root / "storage")
        imported = session_store.restore_session(result["path"], str(self.cwd), session_id="new-seed")
        from relay.adapters.dsh import read_records
        original = read_records(next(source.discover()).path)
        target = read_records(imported["to"]["path"])
        self.assertEqual(target[0]["version"], 0)
        self.assertEqual(original[1:], target[1:])

    def test_single_session_package_does_not_include_other_titles_credentials_or_configuration(self):
        source = registry.get("windows_codex").adapter
        sid = next(source.discover()).id
        Path(source.index_path).write_text(json.dumps({"id":sid,"thread_name":"selected"}) + "\n" +
            json.dumps({"id":"other","thread_name":"private other"}) + "\n", encoding="utf-8")
        (Path(source.root) / "auth.json").write_text('"credential"', encoding="utf-8")
        result = session_store.store_session("windows_codex", sid, self.root / "storage")
        manifest, files = archive.read_package(result["path"], session_store.KIND)
        self.assertNotIn("root0/auth.json", files)
        self.assertNotIn(b"private other", files["root0/session_index.jsonl"][0])
        imported = session_store.restore_session(result["path"], str(self.cwd))
        self.assertIn("selected", Path(self.targets["codex"].index_path).read_text())
        with self.assertRaises(FileExistsError):
            session_store.restore_session(result["path"], str(self.cwd))
        self.assertTrue(Path(imported["to"]["path"]).exists())

    def test_corruption_and_unsafe_archive_entries_are_rejected_before_restore(self):
        source = registry.get("windows_codex")
        package = session_store.store_session("windows_codex", next(source.discover()).id, self.root / "storage")["path"]
        with zipfile.ZipFile(package) as z:
            data = {name:z.read(name) for name in z.namelist()}
        selected = next(name for name in data if name != "manifest.json")
        data[selected] = data[selected][:1] + b"!" + data[selected][2:]
        bad = self.root / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            for name, raw in data.items():
                z.writestr(name, raw)
        with self.assertRaisesRegex(ValueError, "校验失败"):
            session_store.restore_session(bad, str(self.cwd))
        self.assertFalse(Path(self.targets["codex"].home).exists())
        for name in ("../outside", "root0/../../outside", "C:/outside", "root0\\escape", "root0/CON"):
            with zipfile.ZipFile(bad, "w") as z:
                z.writestr(name, b"x")
            with self.assertRaises(ValueError):
                archive.read_package(bad)
        with zipfile.ZipFile(bad, "w") as z:
            link = zipfile.ZipInfo("root0/link")
            link.external_attr = 0o120777 << 16
            z.writestr(link, "../outside")
        with self.assertRaises(ValueError):
            archive.read_package(bad)

    def test_size_limits_failed_publish_and_batch_cli_report_errors(self):
        root = self.root / "storage"
        sid = next(registry.get("windows_codex").discover()).id
        with patch.object(archive, "MAX_TOTAL", 8), self.assertRaises(ValueError):
            session_store.store_session("windows_codex", sid, root)
        self.assertFalse(root.exists())
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(["store-sessions", "windows_codex", sid, "missing", "--storage", str(root)])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(len(result["stored"]), 1)
        self.assertEqual(result["errors"][0]["id"], "missing")
        with self.assertRaises(ValueError):
            session_store.store_sessions("codex", [sid], True, root)
        path = root / "existing.zip"
        archive.write_package(path, {"kind":"fixture"}, {"data":(b"original",False)})
        original = path.read_bytes()
        with self.assertRaises(FileExistsError):
            archive.write_package(path, {"kind":"fixture"}, {"data":(b"new",False)})
        self.assertEqual(path.read_bytes(), original)

    @unittest.skipUnless(os.name == "nt", "requires a real Windows filesystem for cwd validation")
    def test_windows_restore_validates_native_drive_path_and_generates_powershell_resume(self):
        source = registry.get("windows_codex")
        package = session_store.store_session("windows_codex", next(source.discover()).id, self.root / "storage")["path"]
        with patch.object(native_import.platform, "system", return_value="Windows"):
            result = session_store.restore_session(package, str(self.cwd))
        self.assertIn("Set-Location -LiteralPath", result["resume_command"])
        self.assertEqual(result["to"]["cwd"], str(self.cwd))
