"""Independent source roots and observed persistence formats; synthetic data only."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import bootstrap
from relay import ir, registry, locations
from relay.adapters.dsh import DshAdapter, read_records
from relay.adapters.workbuddy import WorkBuddyAdapter
from relay.adapters.codebuddy import CodeBuddyAdapter
from relay.adapters.markdown import render

try:
    import zstandard as zstd
except ImportError:
    zstd = None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def log(version=4):
    records = [{"type":"session", "version":version, "id":"native-id", "cwd":"/fixture",
                "createdAt":1780000000000, "isSeeded":False}]
    def event(kind, data):
        records.append({"type":kind, "seq":len(records)-1, "time":1780000000000+len(records), "data":data})
    event("user/message", {"role":"user", "source":{"kind":"user"},
                           "content":[{"type":"text", "text":"hello"}]})
    event("assistant/chunk", {"turn":1, "step":1, "chunk":{"type":"text-delta", "index":0, "text":"duplicate"}})
    event("assistant/message", {"turn":1, "step":1, "message":{"role":"assistant", "source":{"model":"test"},
           "content":[{"type":"text", "text":"answer"}, {"type":"tool-call", "id":"c", "name":"read_file", "arguments":"{}"}]}})
    event("tool/call", {"callId":"c", "name":"read_file", "arguments":"{}"})
    result = {"role":"tool", "toolCallId":"c", "isError":True, "content":[{"type":"text", "text":"output"}]}
    if version < 4:
        result = {"role":"user", "content":[{"type":"tool-result", "toolCallId":"c", "isError":True,
                  "content":[{"type":"text", "text":"output"}]}]}
    event("tool/result", {"message":result})
    event("session/title", {"title":"fixture title"})
    return records


def write_log(root, records, version=4):
    filename = "session.jsonl" if version == 0 else f"session.v{version}.jsonl"
    path = Path(root) / "sessions" / "project" / "session-id" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r)+"\n" for r in records), encoding="utf-8")
    return path


class IndependentSourcesTests(unittest.TestCase):
    def test_default_roots_and_separate_overrides(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(locations.Path, "home", return_value=Path("/fixture")):
            self.assertTrue(locations.resolve_home("workbuddy").endswith(".workbuddy"))
            self.assertTrue(locations.resolve_home("dsh").endswith(".dsh"))
            self.assertTrue(locations.resolve_home("codebuddy").endswith(".codebuddy"))
            with patch.dict(os.environ, {"DSH_HOME":"/native", "RELAY_DSH_HOME":"/relay"}):
                self.assertEqual(locations.resolve_home("dsh"), os.path.abspath("/relay"))
                self.assertEqual(locations.resolve_home("dsh", "/explicit"), os.path.abspath("/explicit"))
                self.assertTrue(locations.resolve_home("workbuddy").endswith(".workbuddy"))
        with patch.dict(os.environ, {}, clear=True):
            bootstrap.apply_config({"agent_homes":{"dsh":"/d", "workbuddy":"/w", "codebuddy":"/c"}})
            self.assertEqual(os.environ["RELAY_DSH_HOME"], "/d")
            self.assertEqual(os.environ["RELAY_WORKBUDDY_HOME"], "/w")
            self.assertEqual(os.environ["RELAY_CODEBUDDY_HOME"], "/c")

    def test_lookalike_logs_are_not_misidentified(self):
        with tempfile.TemporaryDirectory() as root:
            write_log(root, log())
            write_json(Path(root)/"projects/p/foreign.jsonl", log()[0])
            self.assertEqual(len(list(DshAdapter(home=root).discover())), 1)
            self.assertEqual(list(WorkBuddyAdapter(home=root).discover()), [])
            self.assertEqual(list(CodeBuddyAdapter(home=root).discover()), [])
        with tempfile.TemporaryDirectory() as root:
            write_json(Path(root)/"sessions/p/s/session.v4.jsonl", {"type":"message", "role":"user", "content":[]})
            row = next(DshAdapter(home=root).discover())
            self.assertFalse(row.readable)
            self.assertIn("WorkBuddy", row.error)

    def test_read_only_targets_rejected_before_source_read(self):
        for target in ("dsh", "codebuddy"):
            with self.subTest(target=target), patch.dict(registry._CACHE, {}, clear=True):
                with patch.object(WorkBuddyAdapter, "read", side_effect=AssertionError("must not read")):
                    with self.assertRaisesRegex(ValueError, "迁移目标"):
                        registry.transfer("workbuddy", "none", target)
        self.assertEqual(registry.writable_keys(), ["workbuddy", "claude", "codex"])


class DshTests(unittest.TestCase):
    def test_cached_summaries_refresh_when_log_or_generation_changes(self):
        with tempfile.TemporaryDirectory() as root:
            path=write_log(root, log())
            a=DshAdapter(home=root)
            with patch.object(a, "_parse", wraps=a._parse) as parse:
                self.assertEqual(next(a.discover()).title, "fixture title")
                self.assertEqual(next(a.discover()).title, "fixture title")
                self.assertEqual(parse.call_count, 1)
                records=log(); records[-1]["data"]["title"]="updated fixture title"
                write_log(root, records)
                self.assertEqual(next(a.discover()).title, "updated fixture title")
                self.assertEqual(parse.call_count, 2)
                Path(str(path)+".zstd").write_bytes(b"invalid")
                self.assertFalse(next(a.discover()).readable)
                write_log(root, log(5), 5)
                self.assertIn("v5", next(a.discover()).error)

    def test_v0_to_v4_tool_results_no_duplicate_calls_or_streams(self):
        for version in range(5):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as root:
                write_log(root, log(version), version)
                a = DshAdapter(home=root)
                row = next(a.discover())
                self.assertTrue(row.readable, row.error)
                conv = a.read(row.id)
                self.assertEqual(conv.title, "fixture title")
                self.assertEqual(conv.cwd, "/fixture")
                self.assertEqual(conv.stats()["tool_call"], 1)
                self.assertEqual(conv.stats()["tool_result"], 1)
                self.assertTrue(conv.turns[-1].blocks[0].is_error)
                self.assertEqual(conv.turns[-1].blocks[0].output, "output")
                self.assertNotIn("duplicate", render(conv))
                self.assertIn("answer", render(conv))

    def test_highest_generation_and_unknown_newest_are_not_silently_downgraded(self):
        with tempfile.TemporaryDirectory() as root:
            write_log(root, log(0), 0)
            write_log(root, log(4), 4)
            a = DshAdapter(home=root)
            rows = list(a.discover())
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0].path.endswith("v4.jsonl"))
            write_log(root, log(5), 5)
            row = next(a.discover())
            self.assertFalse(row.readable)
            self.assertIn("v5", row.error)
            with self.assertRaises(ValueError):
                a.read(row.id)

    def test_header_sequence_and_partial_json_errors_are_visible(self):
        for mutation in (lambda r:r[0].update(version=3), lambda r:r[2].update(seq=99)):
            with tempfile.TemporaryDirectory() as root:
                records = log(); mutation(records); write_log(root, records)
                self.assertFalse(next(DshAdapter(home=root).discover()).readable)
        with tempfile.TemporaryDirectory() as root:
            path = write_log(root, log())
            with path.open("ab") as f:
                f.write(b'{"type":')
            self.assertFalse(next(DshAdapter(home=root).discover()).readable)

    def test_packed_legacy_streams_and_final_message_precedence(self):
        records = [log(0)[0], {"type":"text-chunks", "seq0":0, "time0":1780000000000,
                   "data":{"turn":1, "step":1, "index":0, "texts":["hello", " world"], "dt":[1]}}]
        with tempfile.TemporaryDirectory() as root:
            path = write_log(root, records, 0)
            self.assertEqual(DshAdapter(home=root)._parse(str(path)).turns[0].text(), "hello world")
            records.append({"type":"assistant/message", "seq":2, "time":1780000000002,
                            "data":{"turn":1, "step":1, "message":{"content":[{"type":"text", "text":"final"}]}}})
            write_log(root, records, 0)
            self.assertEqual([t.text() for t in DshAdapter(home=root)._parse(str(path)).turns], ["final"])

    @unittest.skipUnless(zstd, "install requirements-optional.txt for compressed tests")
    def test_multiframe_checksums_incomplete_frames_and_decode_budget(self):
        with tempfile.TemporaryDirectory() as root:
            plain = write_log(root, log())
            compressed = Path(str(plain)+".zstd")
            encoder = zstd.ZstdCompressor(write_checksum=True)
            raw = b"".join(encoder.compress(line) for line in plain.read_bytes().splitlines(keepends=True))
            compressed.write_bytes(raw)
            self.assertFalse(next(DshAdapter(home=root).discover()).readable) # ambiguous encoding
            plain.unlink()
            row = next(DshAdapter(home=root).discover())
            self.assertTrue(row.readable, row.error)
            self.assertEqual(DshAdapter(home=root).read(row.id).stats()["tool_result"], 1)
            for bad in (raw[:-1], raw[:-1]+bytes([raw[-1]^1])):
                compressed.write_bytes(bad)
                self.assertFalse(next(DshAdapter(home=root).discover()).readable)
            compressed.write_bytes(encoder.compress(b"x" * 2000))
            with patch("relay.adapters.dsh.MAX_SCAN_BYTES", 1024), self.assertRaisesRegex(ValueError, "解压内容"):
                read_records(str(compressed))
            compressed.write_bytes(raw)
            with patch.dict(sys.modules, {"zstandard":None}):
                row = next(DshAdapter(home=root).discover())
                self.assertFalse(row.readable)
                self.assertIn("zstandard", row.error)


class CodeBuddyTests(unittest.TestCase):
    def fixture(self, root):
        session = Path(root)/"profile/CodeBuddyIDE/history/ws/s"
        write_json(session.parent/"index.json", {"conversations":[{"id":"s", "name":"IDE title", "selectedModelId":"test"}]})
        write_json(session/"index.json", {"messages":[{"id":"z"}, {"id":"a"}, {"id":"t"}]})
        write_json(session/"messages/z.json", {"role":"user", "createdAt":"2026-10-07T00:00:00Z",
                   "message":json.dumps({"content":[{"type":"text", "text":"Workspace Folder: /fixture\n<user_query>hello</user_query>"}]}),
                   "extra":json.dumps({"sourceContentBlocks":[{"text":"real query"}]})})
        write_json(session/"messages/a.json", {"role":"assistant", "message":{"content":[
                   {"type":"thinking", "thinking":"plan"}, {"type":"tool-call", "toolCallId":"c", "toolName":"Read", "args":{"path":"a"}}]}})
        write_json(session/"messages/t.json", {"role":"tool", "message":{"content":[
                   {"type":"tool-result", "toolCallId":"c", "result":{"result":{"stdout":"output"}}}]}})
        return session

    def test_cli_and_ide_are_ordered_independent_and_exportable(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            write_json(Path(root)/"projects/p/s.jsonl", {"type":"message", "role":"user", "cwd":"/cli",
                       "message":{"content":[{"type":"text", "text":"CLI query"}]}})
            a = CodeBuddyAdapter(home=root)
            rows = list(a.discover())
            self.assertEqual(len(rows), 2)
            self.assertEqual(len({r.id for r in rows}), 2)
            for row in rows:
                self.assertTrue(row.readable, row.error)
                conv = a.read(row.id)
                self.assertEqual(conv.source, "codebuddy")
                if row.id.startswith("ide:"):
                    self.assertEqual(conv.title, "IDE title")
                    self.assertEqual(conv.cwd, "/fixture")
                    self.assertEqual(conv.turns[0].text(), "real query")
                    self.assertEqual(conv.stats()["tool_result"], 1)
                    self.assertIn("output", render(conv))
                else:
                    self.assertEqual(conv.turns[0].text(), "CLI query")
            with self.assertRaises(ValueError):
                a.write(ir.Conversation())

    def test_missing_messages_and_traversal_are_not_partial_migrations(self):
        for reference in ("missing", "../../outside", "../outside", "a/b", "a\\b"):
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as root:
                session = self.fixture(root)
                write_json(session/"index.json", {"messages":[{"id":reference}]})
                a = CodeBuddyAdapter(home=root)
                row = next(a.discover())
                self.assertFalse(row.readable)
                with self.assertRaises((ValueError, FileNotFoundError)):
                    a.read(row.id)

    def test_doctor_counts_sessions_instead_of_message_files(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            write_log(root, log(0), 0); write_log(root, log(4), 4)
            env = {"RELAY_" + k.upper() + "_HOME":root for k in registry.all_keys()}
            with patch.dict(os.environ, env), patch.dict(registry._CACHE, {}, clear=True):
                rows = {r["key"]:r for r in bootstrap.probe_agent_homes()}
                self.assertEqual(rows["codebuddy"]["files"], 1)
                self.assertEqual(rows["dsh"]["files"], 1)

    def test_both_new_sources_migrate_out_to_existing_writers(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            write_log(root, log())
            for source, source_cls in (("dsh", DshAdapter), ("codebuddy", CodeBuddyAdapter)):
                src = source_cls(home=root)
                sid = next(src.discover()).id
                original = src.read(sid)
                for target in registry.writable_keys():
                    with self.subTest(source=source, target=target):
                        dst = registry.get(target, home=os.path.join(root, "target-"+source+target))
                        with patch.dict(registry._CACHE, {source:src, target:dst}, clear=True):
                            result = registry.transfer(source, sid, target, session_id="migrated")
                        migrated = dst.read("migrated")
                        self.assertEqual(migrated.stats()["tool_result"], original.stats()["tool_result"])
                        self.assertEqual(migrated.first_user_text(), original.first_user_text())
                        self.assertTrue(Path(result["to"]["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
