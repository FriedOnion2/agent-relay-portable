"""SDK shared-storage view: no inferred creator and no writes to SDK target."""
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
from relay.adapters.claude import ClaudeAdapter
from relay.adapters.claude_sdk import ClaudeSdkAdapter
from relay.adapters.markdown import render


def fixture(root):
    conv = ir.Conversation(title="shared fixture", cwd="/fixture", turns=[
        ir.Turn(ir.USER, [ir.Block.text_block("question")]),
        ir.Turn(ir.ASSISTANT, [ir.Block.thinking_block("plan"),
                             ir.Block.tool_call("call", "Read", '{"path":"x"}')]),
        ir.Turn(ir.ASSISTANT, [ir.Block.tool_result("call", "result", True),
                             ir.Block.text_block("answer")]),
    ])
    return Path(ClaudeAdapter(home=root).write(conv, session_id="shared"))


class ClaudeSdkTests(unittest.TestCase):
    def test_default_store_shared_but_overrides_are_independent(self):
        self.assertEqual(locations.default_home("claude_sdk"), locations.default_home("claude"))
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR":"/native", "RELAY_CLAUDE_HOME":"/cli",
                                     "RELAY_CLAUDE_SDK_HOME":"/sdk"}, clear=True):
            self.assertEqual(ClaudeSdkAdapter().root, os.path.abspath("/sdk"))
            self.assertEqual(ClaudeAdapter().root, "/cli")
            self.assertEqual(ClaudeSdkAdapter(home="/explicit").root, os.path.abspath("/explicit"))
            del os.environ["RELAY_CLAUDE_SDK_HOME"]
            self.assertEqual(ClaudeSdkAdapter().root, os.path.abspath("/native"))
        with patch.dict(os.environ, {}, clear=True):
            bootstrap.apply_config({"agent_homes":{"claude":"/cli", "claude_sdk":"/sdk"}})
            self.assertEqual(os.environ["RELAY_CLAUDE_HOME"], "/cli")
            self.assertEqual(os.environ["RELAY_CLAUDE_SDK_HOME"], "/sdk")

    def test_shared_records_preserve_tools_and_do_not_claim_sdk_creator(self):
        with tempfile.TemporaryDirectory() as root:
            path = fixture(root)
            # These fields cannot establish SDK ownership.
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            for record in records:
                record.update(agentName="helper", userType="external", isSidechain=False)
            path.write_text("".join(json.dumps(r)+"\n" for r in records), encoding="utf-8")
            sdk = ClaudeSdkAdapter(home=root)
            cli_row = next(ClaudeAdapter(home=root).discover())
            sdk_row = next(sdk.discover())
            self.assertEqual(cli_row.path, sdk_row.path)
            self.assertTrue(sdk_row.shared_store)
            self.assertFalse(cli_row.shared_store)
            conv = sdk.read(sdk_row.id)
            self.assertEqual(conv.source, "claude_sdk")
            self.assertEqual(conv.meta["creator"], "unknown")
            self.assertEqual(conv.stats()["tool_call"], 1)
            self.assertEqual(conv.stats()["tool_result"], 1)
            self.assertEqual(conv.stats()["thinking"], 1)
            self.assertIn("无法仅凭日志确认创建者", render(conv))
            self.assertIn("result", render(conv))

    def test_sdk_is_not_a_writer_but_can_migrate_out(self):
        with tempfile.TemporaryDirectory() as root:
            path = fixture(root)
            original = path.read_bytes()
            sdk = ClaudeSdkAdapter(home=root)
            with self.assertRaises(ValueError):
                sdk.write(ir.Conversation())
            with patch.dict(registry._CACHE, {"claude_sdk":sdk}, clear=True):
                with patch.object(sdk, "read", side_effect=AssertionError("should not read")):
                    with self.assertRaisesRegex(ValueError, "迁移目标"):
                        registry.transfer("claude_sdk", "shared", "claude_sdk")
            for target in registry.writable_keys():
                with self.subTest(target=target):
                    dst = registry.get(target, home=os.path.join(root, "target-"+target))
                    with patch.dict(registry._CACHE, {"claude_sdk":sdk, target:dst}, clear=True):
                        registry.transfer("claude_sdk", "shared", target, cwd=root, session_id="output")
                    result = dst.read("output")
                    self.assertEqual(result.stats()["tool_result"], 1)
                    self.assertEqual(result.first_user_text(), "question")
            self.assertEqual(path.read_bytes(), original)

    def test_custom_title_and_metadata_only_logs(self):
        with tempfile.TemporaryDirectory() as root:
            path = fixture(root)
            created_at = ClaudeSdkAdapter(home=root).read("shared").created_at
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"type":"custom-title", "customTitle":"renamed", "sessionId":"shared",
                                    "timestamp":"2030-01-01T00:00:00Z"})+"\n")
            (path.parent/"empty.jsonl").write_text('{"type":"queue-operation"}\n', encoding="utf-8")
            sdk = ClaudeSdkAdapter(home=root)
            rows = list(sdk.discover())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].title, "renamed")
            self.assertEqual(sdk.read("shared").title, "renamed")
            self.assertEqual(sdk.read("shared").created_at, created_at)
            self.assertTrue(sdk.read("shared").updated_at.startswith("2030-01-01"))

    def test_config_validation_and_source_capabilities(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = Path(root)/"config.json"
            cfg.write_text('{"agent_homes":{"claude_sdk":42}}', encoding="utf-8")
            with patch.object(bootstrap, "config_path", return_value=cfg), patch.object(sys, "stderr"):
                self.assertEqual(bootstrap.load_config().get('agent_homes', {}), {})
                from relay import device
                self.assertTrue(any('共享配置读取失败' in warning for warning in device.warnings))
            fixture(root)
            adapters = {key:registry.get(key, home=os.path.join(root, key)) for key in registry.all_keys()}
            adapters["claude_sdk"] = ClaudeSdkAdapter(home=root)
            with patch.dict(registry._CACHE, adapters, clear=True):
                row = next(r for r in registry.sources_info() if r["name"] == "claude_sdk")
                self.assertEqual(row["session_count"], 1)
                self.assertFalse(row["can_write"])
                self.assertIn("共用", row["read_note"])
                self.assertTrue(registry.list_sessions("claude_sdk")[0]["shared_store"])

    def test_active_branch_excludes_sidechains_metadata_and_previous_branches(self):
        records = [
            {"type":"user", "uuid":"u", "parentUuid":None, "message":{"content":"question"}},
            {"type":"assistant", "uuid":"old", "parentUuid":"u", "message":{"content":"old branch"}},
            {"type":"assistant", "uuid":"new", "parentUuid":"u", "message":{"content":"current branch"}},
            {"type":"progress", "uuid":"p", "parentUuid":"new"},
            {"type":"assistant", "uuid":"side", "parentUuid":"u", "isSidechain":True,
             "message":{"content":"subagent"}},
        ]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"projects/p/session.jsonl"; path.parent.mkdir(parents=True)
            path.write_text("".join(json.dumps(r)+"\n" for r in records), encoding="utf-8")
            sdk = ClaudeSdkAdapter(home=root)
            conv = sdk.read("session")
            self.assertEqual([t.text() for t in conv.turns], ["question", "current branch"])
            self.assertTrue(any("主链" in n for n in conv.meta["notes"]))
            # Compaction begins a new physical chain; logicalParentUuid is provenance only.
            records += [
                {"type":"system", "uuid":"boundary", "parentUuid":None, "logicalParentUuid":"new"},
                {"type":"user", "uuid":"compact", "parentUuid":"boundary", "isCompactSummary":True,
                 "message":{"content":"compact summary"}},
                {"type":"user", "uuid":"meta", "parentUuid":"compact", "isMeta":True,
                 "message":{"content":"hidden metadata"}},
                {"type":"assistant", "uuid":"last", "parentUuid":"meta", "message":{"content":"continued"}},
            ]
            path.write_text("".join(json.dumps(r)+"\n" for r in records), encoding="utf-8")
            conv = sdk.read("session")
            self.assertEqual([t.text() for t in conv.turns], ["compact summary", "continued"])
            self.assertEqual(next(sdk.discover()).turns, 2)

    def test_broken_chain_and_wire_output_are_visible_errors(self):
        for records in (
            [{"type":"user", "uuid":"a", "parentUuid":"missing", "message":{"content":"x"}}],
            [{"type":"user", "uuid":"a", "parentUuid":"b", "message":{"content":"x"}},
             {"type":"assistant", "uuid":"b", "parentUuid":"a", "message":{"content":"x"}}],
            [{"type":"system", "subtype":"init", "session_id":"wire"},
             {"type":"assistant", "session_id":"wire", "message":{"content":"answer"}}],
        ):
            with self.subTest(records=records), tempfile.TemporaryDirectory() as root:
                path=Path(root)/"projects/p/session.jsonl"; path.parent.mkdir(parents=True)
                path.write_text("".join(json.dumps(r)+"\n" for r in records), encoding="utf-8")
                sdk=ClaudeSdkAdapter(home=root)
                self.assertFalse(next(sdk.discover()).readable)
                with self.assertRaises(ValueError):
                    sdk.read("session")

    def test_corrupt_or_torn_native_log_cannot_be_silently_migrated(self):
        for bad in (b'{"type":', b'[]\n', b'\xff\n'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as root:
                path=fixture(root)
                with path.open("ab") as f:
                    f.write(bad)
                sdk=ClaudeSdkAdapter(home=root)
                row=next(sdk.discover())
                self.assertFalse(row.readable)
                with self.assertRaises(ValueError):
                    sdk.read(row.id)

    def test_unknown_blocks_are_preserved_in_export_and_native_target_text(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"projects/p/session.jsonl"; path.parent.mkdir(parents=True)
            raw = {"type":"future-block", "payload":{"text":"important unknown content"}}
            path.write_text(json.dumps({"type":"assistant", "message":{"content":[raw]}}), encoding="utf-8")
            sdk=ClaudeSdkAdapter(home=root)
            conv=sdk.read("session")
            self.assertEqual(conv.turns[0].blocks[0].kind, ir.RAW)
            self.assertIn("important unknown content", render(conv))
            dst=registry.get("codex", home=os.path.join(root,"target"))
            with patch.dict(registry._CACHE, {"claude_sdk":sdk,"codex":dst}, clear=True):
                registry.transfer("claude_sdk", "session", "codex", session_id="out")
            self.assertIn("important unknown content", dst.read("out").turns[0].text())

    def test_truncated_source_cannot_migrate_silently(self):
        partial=ir.Conversation(source="claude_sdk", truncated=True,
                                turns=[ir.Turn(ir.USER,[ir.Block.text_block("partial")])])
        with patch.object(ClaudeSdkAdapter, "read", return_value=partial), patch.dict(registry._CACHE, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "迁移已停止"):
                registry.transfer("claude_sdk", "large", "claude")
        self.assertIn("只包含已读取", render(partial))


if __name__ == "__main__":
    unittest.main()
