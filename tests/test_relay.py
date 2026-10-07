"""Synthetic sessions only: tests never read or write real agent homes."""
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import bootstrap
import cli
from relay import ir, paths, registry
from relay.adapters.base import _norm_cwd, BaseAdapter, SessionInfo
from relay.adapters.claude import ClaudeAdapter
from relay.adapters.codex import CodexAdapter
from relay.adapters.workbuddy import WorkBuddyAdapter

ADAPTERS = {"claude": ClaudeAdapter, "codex": CodexAdapter, "workbuddy": WorkBuddyAdapter}


def sample():
    return ir.Conversation(source="synthetic", title="中文迁移回归", cwd="/tmp/relay project",
        model="test-model", turns=[
            ir.Turn(ir.USER, [ir.Block.text_block("需求：" + "很长的真实用户内容" * 600)]),
            ir.Turn(ir.ASSISTANT, [ir.Block.thinking_block("检查文件")]),
            ir.Turn(ir.ASSISTANT, [ir.Block.tool_call("call-1", "Bash", '{"command":"pwd"}')]),
            ir.Turn(ir.ASSISTANT, [ir.Block.tool_result("call-1", "/tmp/relay project")]),
            ir.Turn(ir.ASSISTANT, [ir.Block.text_block("继续"),
                ir.Block.tool_call("call-2", "Read", '{"path":"hello.txt"}'),
                ir.Block.tool_result("call-2", "你好\n第二行"),
                ir.Block.text_block("完成")]),
            ir.Turn(ir.USER, [ir.Block.text_block("下一步")]),
        ])


def content(conv):
    def arguments(block):
        if block.kind != ir.TOOL_CALL:
            return block.arguments
        try:
            return json.loads(block.arguments)
        except ValueError:
            return block.arguments
    return [(b.kind, b.text, b.call_id, arguments(b), b.output)
            for t in conv.turns for b in t.blocks]


class TransferTests(unittest.TestCase):
    def test_all_six_directions_preserve_content_and_tool_order(self):
        for source, source_cls in ADAPTERS.items():
            for target, target_cls in ADAPTERS.items():
                if source == target:
                    continue
                with self.subTest(source=source, target=target), tempfile.TemporaryDirectory() as root:
                    src = source_cls(home=os.path.join(root, "source"))
                    dst = target_cls(home=os.path.join(root, "target"))
                    original = sample()
                    source_path = src.write(original, session_id="source-session", remap_tools=False)
                    parsed = src.read("source-session")
                    self.assertEqual(content(original), content(parsed))
                    output = dst.write(parsed, session_id="target-session", remap_tools=False)
                    result = dst.read("target-session")
                    self.assertEqual(content(original), content(result))
                    self.assertEqual(result.stats()["tool_result"], 2)
                    self.assertEqual(result.cwd, original.cwd)
                    if target == "claude":
                        self.assert_parent_chain(output)
                    self.assertTrue(Path(source_path).exists())

    def assert_parent_chain(self, output):
        seen = set()
        roots = 0
        for rec, _ in paths.read_jsonl(output):
            if "uuid" not in rec:
                continue
            self.assertNotIn(rec["uuid"], seen)
            if rec["parentUuid"] is None:
                roots += 1
            else:
                self.assertIn(rec["parentUuid"], seen)
            seen.add(rec["uuid"])
        self.assertEqual(roots, 1)

    def test_existing_session_is_never_overwritten(self):
        for cls in ADAPTERS.values():
            with self.subTest(adapter=cls.name), tempfile.TemporaryDirectory() as root:
                adapter = cls(home=root)
                path = Path(adapter.write(sample(), session_id="existing"))
                before = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    adapter.write(sample(), session_id="existing")
                self.assertEqual(path.read_bytes(), before)

    def test_invalid_id_cannot_escape_target_home(self):
        for cls in ADAPTERS.values():
            with tempfile.TemporaryDirectory() as root:
                for sid in ("../outside", "a/b", "a\\b", "", "C:outside"):
                    with self.subTest(adapter=cls.name, sid=sid), self.assertRaises(ValueError):
                        cls(home=root).write(sample(), session_id=sid)
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_thinking_can_be_excluded(self):
        for cls in ADAPTERS.values():
            with self.subTest(adapter=cls.name), tempfile.TemporaryDirectory() as root:
                adapter = cls(home=root)
                adapter.write(sample(), session_id="no-thinking", include_thinking=False)
                result = adapter.read("no-thinking")
                self.assertEqual(result.stats()["thinking"], 0)
                self.assertEqual(result.stats()["tool_result"], 2)

    def test_claude_mixed_user_message_keeps_result_and_text(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "mixed.jsonl"
            path.write_text(json.dumps({"type":"user", "message":{"role":"user", "content":[
                {"type":"tool_result", "tool_use_id":"call-1", "content":"result", "is_error":True},
                {"type":"text", "text":"follow-up"}]}}), encoding="utf-8")
            conv = ClaudeAdapter(home=root)._parse(str(path))
            self.assertEqual([t.role for t in conv.turns], [ir.ASSISTANT, ir.USER])
            self.assertTrue(conv.turns[0].blocks[0].is_error)
            self.assertEqual(conv.turns[1].blocks[0].text, "follow-up")

    def test_workbuddy_record_ids_are_unique(self):
        with tempfile.TemporaryDirectory() as root:
            output = WorkBuddyAdapter(home=root).write(sample())
            ids = [rec["id"] for rec, _ in paths.read_jsonl(output)]
            self.assertEqual(len(ids), len(set(ids)))

    def test_oversized_first_record_marks_conversation_truncated(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "large.jsonl"
            path.write_text(json.dumps({"text":"x" * 256}), encoding="utf-8")
            for key, cls in ADAPTERS.items():
                with self.subTest(adapter=key), patch("relay.adapters." + key + ".MAX_SCAN_BYTES", 32):
                    self.assertTrue(cls(home=root)._parse(str(path)).truncated)


class PathsTests(unittest.TestCase):
    def test_uuid7_version_variant_timestamp_and_uniqueness(self):
        timestamp = 1791332024450
        ids = [uuid.UUID(paths.uuid7(timestamp)) for _ in range(500)]
        self.assertEqual(len(set(ids)), len(ids))
        for value in ids:
            self.assertEqual(value.version, 7)
            self.assertEqual(value.variant, uuid.RFC_4122)
            self.assertEqual(value.int >> 80, timestamp)

    def test_path_lookup_respects_posix_case_and_windows_variants(self):
        self.assertEqual(_norm_cwd("C:\\Users\\Alice\\Project\\"), _norm_cwd("c:/users/alice/project"))
        self.assertNotEqual(_norm_cwd("/Users/alice/Project"), _norm_cwd("/Users/alice/project"))
        self.assertEqual(_norm_cwd("/"), "/")
        self.assertNotIn(paths.slug_for(".."), (".", ".."))
        self.assertNotIn(paths.slug_for("."), (".", ".."))
        for value in (None, "", 42):
            with self.assertRaises(ValueError):
                registry.get(value)

    def test_failed_atomic_write_keeps_original_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "session.jsonl"
            path.write_text("original", encoding="utf-8")
            def broken():
                yield "new"
                raise RuntimeError("interrupted")
            with self.assertRaises(RuntimeError):
                paths.atomic_write(str(path), broken())
            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(Path(root).iterdir()), [path])

    def test_jsonl_budget_bom_and_non_objects(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "test.jsonl"
            first = b'\xef\xbb\xbf{"text":"hello"}\r\n'
            path.write_bytes(first + b'[]\nnull\ninvalid\n{"text":"later"}\n')
            self.assertEqual(list(paths.read_jsonl(str(path), len(first))), [({"text":"hello"}, True)])
            self.assertEqual([rec for rec, _ in paths.read_jsonl(str(path))],
                             [{"text":"hello"}, {"text":"later"}])

    def test_empty_or_ambiguous_lookup_is_rejected(self):
        adapter = BaseAdapter()
        rows = [SessionInfo("test", sid, "", "", "", None, None, 0, 0, sid + ".jsonl")
                for sid in ("abc-1", "abc-2")]
        with patch.object(adapter, "discover", return_value=iter(rows)):
            with self.assertRaises(ValueError):
                adapter.find_path("abc")
        with self.assertRaises(ValueError):
            adapter.find_path("")


class BootstrapTests(unittest.TestCase):
    def test_config_bom_validation(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "config.json"
            with patch.object(bootstrap, "config_path", return_value=path):
                path.write_text('{"port":9123,"open_browser":false}', encoding="utf-8-sig")
                cfg = bootstrap.load_config()
                self.assertEqual(bootstrap.effective_port(cfg), 9123)
                self.assertFalse(bootstrap.effective_open_browser(cfg))
                for invalid in ('[]', '{"port":65536}', '{"agent_homes":[]}',
                                '{"agent_homes":{"codex":42}}', '{"open_browser":"false"}'):
                    path.write_text(invalid, encoding="utf-8")
                    with patch.object(sys, "stderr"):
                        self.assertEqual(bootstrap.load_config(), {})

    def test_py_launcher_is_executed_as_separate_arguments(self):
        with patch.object(bootstrap.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "3.12\n"
            self.assertEqual(bootstrap._version_of("py -3"), (3, 12))
            self.assertEqual(run.call_args[0][0][:2], ["py", "-3"])

    def test_doctor_exit_code_and_browser_setting(self):
        with patch.object(cli.bootstrap, "print_report", return_value=2):
            self.assertEqual(cli.main(["doctor"]), 2)
        with patch.object(cli, "_CFG", {"open_browser":False}), patch("server.run") as run:
            self.assertEqual(cli.main(["serve", "--port", "9123"]), 0)
            self.assertFalse(run.call_args.kwargs["open_browser"])


if __name__ == "__main__":
    unittest.main()
