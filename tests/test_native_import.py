"""Same-agent Windows imports preserve native artifacts, using synthetic stores."""
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import cli
from relay import registry, native_import
from relay.adapters.dsh import read_records
from test_relay import content
import test_sources
import test_windows_profiles

NEW_UUID = "11111111-1111-4111-8111-111111111111"


class NativeImportTests(unittest.TestCase):
    def setUp(self):
        test_windows_profiles.WindowsProfilesTests.setUp(self)
        self.cwd = self.root / "Ubuntu project 中文.space !"
        self.cwd.mkdir()
        self.cwd = self.cwd.resolve()
        self.targets = {key: registry.get(key, home=str(self.root / "ubuntu" / key))
                        for key in cli.AGENTS}
        registry._CACHE.update(self.targets)
        path = next(registry.get("windows_dsh").discover()).path
        rows = read_records(path)
        rows[0]["delegationDepth"] = 0
        Path(path).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def make_ide_workspace(self):
        target = self.targets["codebuddy"]
        data = self.root / "ubuntu" / "ide-data"
        target.roots.append(str(data))
        path = test_sources.CodeBuddyTests().fixture(str(data))
        for file in (path / "messages").glob("*.json"):
            file.write_text(file.read_text(encoding="utf-8").replace("/fixture", str(self.cwd).replace("\\", "/")),
                            encoding="utf-8")
        index = path.parent / "index.json"
        value = json.loads(index.read_text(encoding="utf-8"))
        value["conversations"][0]["id"] = "ubuntu-seed"
        value["local-only"] = "keep"
        index.write_text(json.dumps(value), encoding="utf-8")
        new = path.parent / "ubuntu-seed"
        path.rename(new)
        return new

    def snapshot(self, directory):
        return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}

    def test_all_six_same_agent_imports_preserve_content_and_windows_files(self):
        self.make_ide_workspace()
        before = self.snapshot(self.profile)
        for key in cli.AGENTS:
            source = "windows_" + key
            for row in registry.list_sessions(source):
                with self.subTest(agent=key, session=row["id"]):
                    original = registry.read_conversation(source, row["id"])
                    result = native_import.import_windows(source, row["id"], str(self.cwd))
                    self.assertEqual(result["to"]["source"], key)
                    local = registry.read_conversation(key, result["to"]["id"])
                    self.assertEqual(content(local), content(original))
                    self.assertEqual(local.cwd.replace("\\", "/"), str(self.cwd).replace("\\", "/"))
                    self.assertTrue(Path(result["to"]["path"]).is_file())
                    self.assertEqual(result["mode"], "native-windows-import")
                    if key == "dsh":
                        records = read_records(result["to"]["path"])
                        self.assertEqual(records[1:], read_records(original.path)[1:])
                        self.assertEqual(Path(result["to"]["path"]).parent.parent.name,
                                         native_import.dsh_project(str(self.cwd).replace("\\", "/")))
                        self.assertEqual(records[0]["id"], "native-id")
        self.assertEqual(before, self.snapshot(self.profile))
        self.assertEqual(registry.writable_keys(), ["workbuddy", "dsh", "claude", "codex"])

    def test_original_id_collision_refuses_overwrite_and_new_id_can_be_used(self):
        for key in ("workbuddy", "claude", "claude_sdk", "codex", "dsh"):
            source = "windows_" + key
            sid = registry.list_sessions(source)[0]["id"]
            result = native_import.import_windows(source, sid, str(self.cwd))
            before = Path(result["to"]["path"]).read_bytes()
            with self.assertRaises(FileExistsError):
                native_import.import_windows(source, sid, str(self.cwd))
            self.assertEqual(Path(result["to"]["path"]).read_bytes(), before)
            result = native_import.import_windows(source, sid, str(self.cwd), session_id=NEW_UUID)
            self.assertEqual(result["to"]["native_id"], NEW_UUID)
            if key in ("claude", "claude_sdk", "codex"):
                with self.assertRaisesRegex(ValueError, "UUID"):
                    native_import.import_windows(source, sid, str(self.cwd), session_id="not-a-uuid")

    def test_codex_native_metadata_title_index_and_arguments_are_preserved(self):
        src = registry.get("windows_codex")
        row = next(src.discover())
        records = native_import._jsonl(row.path)
        old = "C:\\Users\\Alice\\project"
        for record in records:
            if record["type"] in ("session_meta", "turn_context"):
                record["payload"]["cwd"] = old
                record["payload"]["vendor-native"] = {"opaque": "keep"}
            if record["type"] == "turn_context":
                record["payload"]["workspace_roots"] = [old]
                record["payload"]["sandbox_policy"]["writable_roots"] = [old + "\\sub"]
            if record.get("payload", {}).get("type") == "function_call":
                record["payload"]["arguments"] = json.dumps({"path": old + "\\file.txt"})
        Path(row.path).write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        Path(src.adapter.index_path).write_text(json.dumps({"id": row.id, "thread_name": "native title",
                         "updated_at": "2026-10-07T00:00:00Z", "vendor": "keep"}) + "\n", encoding="utf-8")
        result = native_import.import_windows("codex", row.id, str(self.cwd), session_id=NEW_UUID)
        imported = native_import._jsonl(result["to"]["path"])
        context = next(r["payload"] for r in imported if r["type"] == "turn_context")
        expected_cwd = str(self.cwd).replace("\\", "/")
        self.assertEqual(context["workspace_roots"], [expected_cwd])
        self.assertEqual(context["sandbox_policy"]["writable_roots"], [expected_cwd + "/sub"])
        self.assertEqual(context["vendor-native"], {"opaque": "keep"})
        self.assertEqual([r["payload"]["arguments"] for r in imported if r.get("payload", {}).get("type") == "function_call"],
                         [r["payload"]["arguments"] for r in records if r.get("payload", {}).get("type") == "function_call"])
        index = native_import._jsonl(self.targets["codex"].index_path)[0]
        self.assertEqual(index["thread_name"], "native title")
        self.assertEqual(index["vendor"], "keep")
        self.assertEqual(index["id"], NEW_UUID)
        self.assertEqual(self.targets["codex"].read(NEW_UUID).title, "native title")
        self.assertIn("codex resume " + NEW_UUID, result["resume_command"])
        self.assertFalse(list(Path(self.targets["codex"].root).glob("*.publish-lock")))

    def test_claude_keeps_native_branches_unknown_fields_and_sdk_independent_home(self):
        source = registry.get("windows_claude_sdk")
        row = next(source.discover())
        records = native_import._jsonl(row.path)
        records[1]["vendor-field"] = {"type": "unknown", "data": [1, 2]}
        Path(row.path).write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        result = native_import.import_windows("claude_sdk", row.id, str(self.cwd))
        self.assertTrue(native_import._inside(result["to"]["path"], self.targets["claude_sdk"].root))
        self.assertFalse(native_import._inside(result["to"]["path"], self.targets["claude"].root))
        imported = native_import._jsonl(result["to"]["path"])
        self.assertEqual(imported[1]["vendor-field"], records[1]["vendor-field"])
        self.assertEqual([r.get("uuid") for r in imported], [r.get("uuid") for r in records])
        self.assertEqual(Path(result["to"]["path"]).parent.name,
                         native_import._project_key(str(self.cwd).replace("\\", "/")))

    def test_codebuddy_ide_reuses_native_workspace_and_preserves_its_index(self):
        source = registry.get("windows_codebuddy")
        row = next(r for r in source.discover() if r.id.startswith("ide:"))
        with self.assertRaisesRegex(ValueError, "创建一条会话"):
            native_import.import_windows("codebuddy", row.id, str(self.cwd))
        seed = self.make_ide_workspace()
        seed_before = self.snapshot(seed)
        result = native_import.import_windows("codebuddy", row.id, str(self.cwd), session_id="imported-ide")
        index = json.loads((seed.parent / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["local-only"], "keep")
        self.assertEqual([item["id"] for item in index["conversations"]], ["ubuntu-seed", "imported-ide"])
        self.assertEqual(self.snapshot(seed), seed_before)
        self.assertEqual(Path(result["to"]["path"]).parent.parent, seed.parent)
        self.assertFalse(list(seed.parent.glob("*.publish-lock")))
        self.assertFalse(list(seed.parent.glob("*.partial")))
        with self.assertRaises(FileExistsError):
            native_import.import_windows("codebuddy", row.id, str(self.cwd), session_id="imported-ide")

    def test_ide_index_publish_failure_rolls_back_only_the_new_session(self):
        seed = self.make_ide_workspace()
        before = self.snapshot(seed.parent)
        sid = next(row.id for row in registry.get("windows_codebuddy").discover() if row.id.startswith("ide:"))
        real = native_import.atomic_write
        def fail_index(path, *args, **kwargs):
            if Path(path) == seed.parent / "index.json":
                raise OSError("synthetic index failure")
            return real(path, *args, **kwargs)
        with patch.object(native_import, "atomic_write", side_effect=fail_index), self.assertRaises(OSError):
            native_import.import_windows("codebuddy", sid, str(self.cwd), session_id="rolled-back")
        self.assertEqual(self.snapshot(seed.parent), before)
        self.assertFalse((seed.parent / "rolled-back").exists())

    def test_codex_index_failure_keeps_existing_index_and_removes_new_rollout(self):
        src = registry.get("windows_codex")
        row = next(src.discover())
        Path(src.adapter.index_path).write_text(json.dumps({"id":row.id, "thread_name":"native"}) + "\n", encoding="utf-8")
        target = self.targets["codex"]
        index = Path(target.index_path)
        index.parent.mkdir(parents=True)
        index.write_text('{"id":"existing","thread_name":"keep"}\n', encoding="utf-8")
        original = index.read_bytes()
        real = native_import.atomic_write
        def fail_index(path, *args, **kwargs):
            if Path(path) == index:
                raise OSError("synthetic index failure")
            return real(path, *args, **kwargs)
        with patch.object(native_import, "atomic_write", side_effect=fail_index), self.assertRaises(OSError):
            native_import.import_windows("codex", row.id, str(self.cwd))
        self.assertEqual(index.read_bytes(), original)
        self.assertEqual(list(Path(target.home).rglob("rollout-*.jsonl")), [])
        self.assertFalse(list(index.parent.glob("*.publish-lock")))

    def test_dsh_utf16_project_encoding_and_claude_native_sanitizer(self):
        self.assertEqual(native_import.dsh_segment("../会话😀"), "..~002F~4F1A~8BDD~D83D~DE00")
        self.assertEqual(native_import.dsh_segment(".."), "~002E~002E")
        self.assertEqual(native_import.dsh_project("/tmp/中文 space"), "--tmp-~4E2D~6587~0020space--")
        self.assertEqual(native_import._project_key("/home/alice/中文.a_b"), "-home-alice----a-b")
        self.assertLess(len(native_import._project_key("a" * 300)), 210)

    def test_corrupt_jsonl_and_windows_destination_are_rejected_before_publication(self):
        src = registry.get("windows_codex")
        row = next(src.discover())
        with open(row.path, "ab") as output:
            output.write(b"broken\n")
        with self.assertRaisesRegex(ValueError, "损坏"):
            native_import.import_windows("codex", row.id, str(self.cwd))
        self.assertFalse(Path(self.targets["codex"].home).exists())
        for key in ("claude", "claude_sdk", "workbuddy", "dsh", "codebuddy"):
            registry._CACHE[key] = registry.get(key, home=str(self.profile / "would-write"))
            sid = registry.list_sessions("windows_" + key)[0]["id"]
            with self.assertRaisesRegex(ValueError, "Windows 来源"):
                native_import.import_windows(key, sid, str(self.cwd))
        self.assertFalse((self.profile / "would-write").exists())

    def test_dsh_old_generation_and_missing_fork_parent_are_not_guessed(self):
        path = test_sources.write_log(self.profile / ".dsh", test_sources.log(3), 3)
        # Remove v4 so the canonical source selects the historical generation.
        path.with_name("session.v4.jsonl").unlink()
        sid = registry.list_sessions("windows_dsh")[0]["id"]
        with self.assertRaisesRegex(ValueError, "完整 v4"):
            native_import.import_windows("dsh", sid, str(self.cwd))
        records = test_sources.log()
        records[0].update(delegationDepth=0, parentSession="missing-parent", isSeeded=True)
        test_sources.write_log(self.profile / ".dsh", records)
        with self.assertRaisesRegex(ValueError, "父会话"):
            native_import.import_windows("dsh", sid, str(self.cwd))

    def test_cli_json_result_and_shell_quoted_resume_instruction(self):
        source = registry.get("windows_claude")
        sid = next(source.discover()).id
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli.main(["import-windows", "claude", sid, "--cwd", str(self.cwd), "--json"])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertIn("claude --resume", result["resume_command"])
        self.assertIn("'", result["resume_command"])


if __name__ == "__main__":
    unittest.main()
