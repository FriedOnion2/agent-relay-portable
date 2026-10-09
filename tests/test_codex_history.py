"""Synthetic regressions for client-visible history and failed publication."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from relay import ir, paths  # noqa: E402
from relay.adapters.codex import CodexAdapter  # noqa: E402


def conversation():
    return ir.Conversation(source='fixture', title='synthetic', turns=[
        ir.Turn(ir.USER, [ir.Block.text_block('request')]),
        ir.Turn(ir.ASSISTANT, [ir.Block.thinking_block('check first'),
            ir.Block.tool_call('c1', 'Bash', '{"command":"pwd"}'),
            ir.Block.text_block('commentary'), ir.Block.tool_result('c1', '/fixture'),
            ir.Block.tool_call('c2', 'Read', 'non-json arguments'), ir.Block.tool_result('c2', '', True),
            ir.Block.tool_call('missing', 'Read', '{}'), ir.Block.tool_result('orphan', 'standalone'),
            ir.Block.text_block('done')]),
    ])


class CodexHistoryTests(unittest.TestCase):
    def test_completed_history_includes_reasoning_arguments_results_and_order(self):
        with tempfile.TemporaryDirectory() as root:
            output = CodexAdapter(home=root).write(conversation(), session_id='history', remap_tools=False)
            rows = [row for row, _ in paths.read_jsonl(output)]
            items = [row['payload']['item'] for row in rows
                     if row['type'] == 'event_msg' and row['payload']['type'] == 'item_completed']
            self.assertEqual([item['type'] for item in items], [
                'UserMessage', 'Reasoning', 'DynamicToolCall', 'AgentMessage',
                'DynamicToolCall', 'DynamicToolCall', 'DynamicToolCall', 'AgentMessage'])
            self.assertEqual(items[1]['summary_text'], ['check first'])
            self.assertEqual(items[2]['arguments'], {'command': 'pwd'})
            self.assertEqual(items[2]['content_items'][0]['text'], '/fixture')
            self.assertEqual(items[4]['arguments'], 'non-json arguments')
            self.assertEqual(items[4]['status'], 'failed')
            self.assertFalse(items[4]['success'])
            self.assertEqual(items[4]['content_items'][0]['text'], '')
            self.assertIsNone(items[5]['success'])
            self.assertIsNone(items[5]['content_items'])
            self.assertEqual(items[6]['tool'], 'unpaired_result')
            self.assertEqual(items[6]['content_items'][0]['text'], 'standalone')
            self.assertEqual(len({item['id'] for item in items}), len(items))
            # Original response records remain usable by the relay reader.
            restored = CodexAdapter(home=root).read('history')
            self.assertEqual(restored.stats()['tool_call'], 3)
            self.assertEqual(restored.stats()['tool_result'], 3)

    def test_thinking_exclusion_removes_client_visible_reasoning_too(self):
        with tempfile.TemporaryDirectory() as root:
            output = CodexAdapter(home=root).write(conversation(), include_thinking=False)
            rows = [row for row, _ in paths.read_jsonl(output)]
            self.assertFalse(any(row['payload'].get('item', {}).get('type') == 'Reasoning' for row in rows))
            self.assertEqual(CodexAdapter(home=root)._parse(output).stats()['thinking'], 0)

    def test_list_counts_match_retained_content_for_clean_and_raw_views(self):
        payloads = [
            {'type': 'message', 'role': 'user', 'content': 'request'},
            {'type': 'reasoning', 'summary': [{'type': 'summary_text', 'text': 'working'}]},
            {'type': 'message', 'role': 'user', 'content': 'follow up'},
            {'type': 'message', 'role': 'assistant', 'content': '<environment_context>injected</environment_context>'},
            {'type': 'agent_message', 'content': ''},
            {'type': 'message', 'role': 'user', 'content': 'last request'},
            {'type': 'reasoning', 'summary': [], 'encrypted_content': 'opaque'},
        ]
        with tempfile.TemporaryDirectory() as root:
            day = Path(root) / 'sessions' / '2026' / '10' / '09'
            day.mkdir(parents=True)
            rows = [{'type': 'session_meta', 'payload': {'id': 'counts'}}]
            rows += [{'type': 'response_item', 'payload': payload} for payload in payloads]
            (day / 'rollout-counts.jsonl').write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
            for clean, expected in [(True, 4), (False, 5)]:
                with self.subTest(clean=clean):
                    adapter = CodexAdapter(home=root, clean=clean)
                    self.assertEqual(list(adapter.discover())[0].turns, expected)
                    self.assertEqual(adapter.read('counts').stats()['turns'], expected)

    def test_invalid_title_index_leaves_no_session_and_allows_retry(self):
        with tempfile.TemporaryDirectory() as root:
            adapter = CodexAdapter(home=root)
            index = Path(adapter.index_path)
            index.mkdir()
            with self.assertRaises(OSError):
                adapter.write(conversation(), session_id='retry')
            self.assertEqual(list(Path(root).rglob('rollout-*.jsonl')), [])
            self.assertFalse((Path(root) / '.relay-import.publish-lock').exists())
            index.rmdir()
            self.assertTrue(Path(adapter.write(conversation(), session_id='retry')).is_file())

    def test_title_publication_failure_preserves_existing_index_and_rolls_back(self):
        for existing in (False, True):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as root:
                adapter = CodexAdapter(home=root)
                index = Path(adapter.index_path)
                original = b'{"id":"old","thread_name":"old"}'
                if existing:
                    index.write_bytes(original)

                def fail_index(path, lines, index_path=adapter.index_path, **options):
                    if path == index_path:
                        raise OSError('simulated full disk')
                    return paths.atomic_write(path, lines, **options)

                with patch('relay.adapters.codex.atomic_write', side_effect=fail_index), self.assertRaises(OSError):
                    adapter.write(conversation(), session_id='retry')
                self.assertEqual(list(Path(root).rglob('rollout-*.jsonl')), [])
                self.assertEqual(index.read_bytes() if index.exists() else b'', original if existing else b'')
                adapter.write(conversation(), session_id='retry')
                self.assertEqual(len(list(paths.read_jsonl(adapter.index_path))), 2 if existing else 1)

    def test_external_index_change_is_kept_and_owned_rollout_is_removed(self):
        with tempfile.TemporaryDirectory() as root:
            adapter = CodexAdapter(home=root)
            index = Path(adapter.index_path)
            external = b'{"id":"other","thread_name":"external"}\n'

            def changing_index(path, lines, **options):
                result = paths.atomic_write(path, lines, **options)
                if path != adapter.index_path:
                    index.write_bytes(external)
                return result

            with patch('relay.adapters.codex.atomic_write', side_effect=changing_index), self.assertRaisesRegex(
                    ValueError, '正在变化'):
                adapter.write(conversation(), session_id='retry')
            self.assertEqual(index.read_bytes(), external)
            self.assertEqual(list(Path(root).rglob('rollout-*.jsonl')), [])


if __name__ == '__main__':
    unittest.main()
