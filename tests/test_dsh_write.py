"""DSH imports through the public transfer/read interfaces; synthetic homes only."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from relay import ir, registry
from relay.adapters.dsh import DshAdapter, read_records
from relay.adapters.codex import CodexAdapter
from relay.adapters.claude import ClaudeAdapter
from relay.adapters.workbuddy import WorkBuddyAdapter
from relay.adapters.claude_sdk import ClaudeSdkAdapter
try:
    import zstandard
except ImportError:
    zstandard = None


def conversation():
    return ir.Conversation(source="fixture", title="导入 DSH", cwd=os.path.join(os.path.abspath(os.sep), "tmp", "中文 project😀"),
        model="fixture-model", turns=[
            ir.Turn(ir.USER, [ir.Block.text_block("请读取文件")]),
            ir.Turn(ir.ASSISTANT, [ir.Block.thinking_block("检查文件"),
                ir.Block.tool_call("read-1", "Read", '{"path":"hello.txt"}')]),
            ir.Turn(ir.ASSISTANT, [ir.Block.tool_result("read-1", "你好\n第二行", True),
                ir.Block.text_block("已经完成")]),
            ir.Turn(ir.USER, [ir.Block.text_block("下一步")]),
        ])


class DshWriteTests(unittest.TestCase):
    @unittest.skipUnless(zstandard, "install requirements-optional.txt for DSH write tests")
    def test_existing_writers_can_import_into_native_dsh(self):
        for source_cls in (CodexAdapter, ClaudeAdapter, WorkBuddyAdapter):
            with self.subTest(source=source_cls.name), tempfile.TemporaryDirectory() as root:
                source = source_cls(home=os.path.join(root, "source"))
                target = DshAdapter(home=os.path.join(root, "target"))
                source.write(conversation(), session_id="original", remap_tools=False)
                original = source.read("original")
                with patch.dict(registry._CACHE, {source.name: source, "dsh": target}, clear=True):
                    result = registry.transfer(source.name, "original", "dsh",
                                               session_id="imported", remap_tools=False, new_title="导入 DSH")
                path = Path(result["to"]["path"])
                self.assertEqual(path.name, "session.jsonl.zstd")
                row = next(target.discover())
                imported = target.read(row.id)
                self.assertEqual(imported.title, "导入 DSH")
                self.assertEqual(imported.cwd.replace("\\", "/"), original.cwd.replace("\\", "/"))
                self.assertEqual(imported.first_user_text(), "请读取文件")
                self.assertEqual(imported.stats()["tool_call"], 1)
                self.assertEqual(imported.stats()["tool_result"], 1)
                result_block = next(b for t in imported.turns for b in t.blocks if b.kind == ir.TOOL_RESULT)
                self.assertEqual(result_block.output, "你好\n第二行")
                original_result = next(b for t in original.turns for b in t.blocks if b.kind == ir.TOOL_RESULT)
                self.assertEqual(result_block.is_error, original_result.is_error)
                events = read_records(str(path))
                self.assertEqual(events[0]["version"], 0)
                self.assertEqual(events[-1]["type"], "session/end-seed")
                before = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    target.write(conversation(), session_id="imported")
                self.assertEqual(path.read_bytes(), before)

    @unittest.skipUnless(zstandard, "install requirements-optional.txt for DSH write tests")
    def test_incomplete_tools_are_history_and_thinking_can_be_excluded(self):
        with tempfile.TemporaryDirectory() as root:
            original = conversation()
            original.turns.append(ir.Turn(ir.ASSISTANT, [
                ir.Block.tool_call("unfinished", "Bash", '{"command":"do not execute"}')]))
            target = DshAdapter(home=root)
            target.write(original, session_id="closed-history", include_thinking=False)
            imported = target.read("closed-history")
            self.assertEqual(imported.stats()["thinking"], 0)
            self.assertEqual(imported.stats()["tool_call"], 1)
            self.assertIn("do not execute", imported.turns[-1].text())
            call = next(b for t in imported.turns for b in t.blocks if b.kind == ir.TOOL_CALL)
            self.assertEqual(call.name, "read")
            result = next(b for t in imported.turns for b in t.blocks if b.kind == ir.TOOL_RESULT)
            self.assertTrue(result.is_error)

    @unittest.skipUnless(zstandard, "install requirements-optional.txt for DSH write tests")
    def test_source_timestamps_survive_when_conversation_has_no_created_at(self):
        """Sources without created_at must not flatten every event to the import time."""
        base = 1_700_000_000_000
        original = conversation()
        original.created_at = None
        for index, turn in enumerate(original.turns):
            turn.ts = base + index * 60_000
        with tempfile.TemporaryDirectory() as root:
            target = DshAdapter(home=root)
            path = target.write(original, session_id="keep-time")
            rows = read_records(path)
            self.assertEqual(rows[0]["createdAt"], base)
            times = {row["time"] for row in rows[1:]}
            self.assertGreater(len(times), 1)
            self.assertEqual(min(times), base)
            self.assertEqual(max(times), base + 3 * 60_000)
            users = [row["time"] for row in rows[1:] if row["type"] == "user/message"]
            self.assertEqual(users, [base, base + 3 * 60_000])
            self.assertEqual([row["time"] for row in rows[1:]], sorted(row["time"] for row in rows[1:]))

    def test_invalid_ids_and_missing_decoder_do_not_create_sessions(self):
        with tempfile.TemporaryDirectory() as root:
            target = DshAdapter(home=root)
            for sid in ("../outside", "", "a/b", "a\\b"):
                with self.assertRaises(ValueError):
                    target.write(conversation(), session_id=sid)
            with patch.dict(sys.modules, {"zstandard":None}):
                with self.assertRaisesRegex(ValueError, "安装|安装依赖"):
                    target.write(conversation(), session_id="missing-decoder")
            self.assertEqual(list(Path(root).iterdir()), [])

    @unittest.skipUnless(zstandard, "install requirements-optional.txt for DSH write tests")
    def test_duplicate_id_in_another_project_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            target = DshAdapter(home=root)
            target.write(conversation(), session_id="same-id")
            with self.assertRaises(FileExistsError):
                target.write(conversation(), session_id="same-id", cwd=os.path.join(root, "different-project"))

    @unittest.skipUnless(zstandard, "install requirements-optional.txt for DSH write tests")
    def test_sdk_shared_history_can_import_into_dsh(self):
        with tempfile.TemporaryDirectory() as root:
            source_home = os.path.join(root, "source")
            ClaudeAdapter(home=source_home).write(conversation(), session_id="sdk-shared")
            source = ClaudeSdkAdapter(home=source_home)
            target = DshAdapter(home=os.path.join(root, "target"))
            with patch.dict(registry._CACHE, {"claude_sdk":source, "dsh":target}, clear=True):
                registry.transfer("claude_sdk", "sdk-shared", "dsh", session_id="sdk-import")
            imported = target.read("sdk-import")
            self.assertEqual(imported.first_user_text(), "请读取文件")
            self.assertEqual(imported.stats()["tool_result"], 1)

    @unittest.skipUnless(zstandard, "install requirements-optional.txt for DSH write tests")
    def test_failed_oversized_import_leaves_no_session_and_can_be_retried(self):
        with tempfile.TemporaryDirectory() as root:
            target = DshAdapter(home=root)
            with patch("relay.adapters.dsh_write.MAX_LOG_BYTES", 128):
                with self.assertRaisesRegex(ValueError, "超过"):
                    target.write(conversation(), session_id="retry")
            self.assertEqual(list(target.discover()), [])
            self.assertEqual(list(Path(root).rglob("*.partial")), [])
            self.assertEqual(list(Path(root).rglob("*.publish-lock")), [])
            target.write(conversation(), session_id="retry")
            self.assertTrue(next(target.discover()).readable)


if __name__ == "__main__":
    unittest.main()
