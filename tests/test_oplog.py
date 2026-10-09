import json
import os
import tempfile
import unittest
from pathlib import Path

from relay import ir, oplog, registry
from relay.adapters.codex import CodexAdapter


def conversation():
    return ir.Conversation(source='fixture', title='undo me', cwd='/tmp', model='m', turns=[
        ir.Turn(ir.USER, [ir.Block.text_block('hello')]),
        ir.Turn(ir.ASSISTANT, [ir.Block.text_block('hi')]),
    ])


class OperationLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'codex'
        self.home.mkdir()
        os.environ['RELAY_LOG_HOME'] = str(Path(self.tmp.name) / 'logs')
        self.addCleanup(os.environ.pop, 'RELAY_LOG_HOME', None)

    def write(self, session_id='0199aaaa-0000-7000-8000-0000000000d1'):
        adapter = CodexAdapter(home=str(self.home))
        with oplog.track('transfer', [str(self.home)], source='fixture', target='codex', session='s1', title='undo me') as record:
            record['path'] = adapter.write(conversation(), session_id=session_id, cwd=self.tmp.name)
        return adapter, record

    def test_records_created_and_appended_files(self):
        (self.home / 'session_index.jsonl').write_text('{"id":"old"}\n', encoding='utf-8')
        _, record = self.write()
        rows = oplog.list_operations()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], record['id'])
        self.assertEqual(rows[0]['status'], 'ok')
        self.assertTrue(rows[0]['undoable'])
        self.assertTrue(any(path.endswith('.jsonl') and 'rollout' in path for path in rows[0]['created']))
        self.assertEqual([Path(path).name for path in rows[0]['appended']], ['session_index.jsonl'])

    def test_undo_removes_new_files_and_restores_appended_index(self):
        index = self.home / 'session_index.jsonl'
        index.write_text('{"id":"old"}\n', encoding='utf-8')
        adapter, record = self.write()
        created = [Path(p) for p in oplog.list_operations()[0]['created']]
        self.assertTrue(all(path.exists() for path in created))
        result = oplog.undo(record['id'])
        self.assertTrue(result['complete'])
        self.assertTrue(all(not path.exists() for path in created))
        self.assertEqual(index.read_text(encoding='utf-8'), '{"id":"old"}\n')
        self.assertFalse((self.home / 'sessions' / '2026').exists() and any((self.home / 'sessions').rglob('*')))
        self.assertIsNotNone(oplog.list_operations()[0]['undone'])
        with self.assertRaises(ValueError):
            oplog.undo(record['id'])

    def test_undo_keeps_a_session_that_was_continued_after_the_write(self):
        _, record = self.write()
        rollout = next(Path(p) for p in oplog.list_operations()[0]['created'] if 'rollout' in p)
        with open(rollout, 'a', encoding='utf-8') as handle:
            handle.write('{"type":"event_msg","payload":{}}\n')
        result = oplog.undo(record['id'])
        self.assertFalse(result['complete'])
        self.assertTrue(rollout.exists())
        self.assertIn('续聊', result['kept'][0]['reason'])
        self.assertIsNone(oplog.list_operations()[0]['undone'])       # 仍可在手动处理后再试
        forced = oplog.undo(record['id'], force=True)
        self.assertFalse(rollout.exists())
        self.assertTrue(forced['complete'])

    def test_failed_write_without_changes_leaves_no_record(self):
        with self.assertRaises(ValueError):
            with oplog.track('transfer', [str(self.home)]):
                raise ValueError('nothing written')
        self.assertEqual(oplog.list_operations(), [])

    def test_failed_write_with_partial_files_is_recorded_and_undoable(self):
        with self.assertRaises(RuntimeError):
            with oplog.track('transfer', [str(self.home)]):
                (self.home / 'half.jsonl').write_text('partial', encoding='utf-8')
                raise RuntimeError('boom')
        row = oplog.list_operations()[0]
        self.assertEqual(row['status'], 'failed')
        self.assertTrue(row['undoable'])
        oplog.undo(row['id'])
        self.assertFalse((self.home / 'half.jsonl').exists())

    def test_rewritten_existing_file_blocks_undo(self):
        target = self.home / 'index.json'
        target.write_text('long original content', encoding='utf-8')
        with oplog.track('transfer', [str(self.home)]):
            target.write_text('short', encoding='utf-8')
        row = oplog.list_operations()[0]
        self.assertFalse(row['undoable'])
        self.assertIn('改写', row['undo_blocked'])
        with self.assertRaises(ValueError):
            oplog.undo(row['id'])

    def test_undo_never_touches_paths_outside_the_recorded_roots(self):
        outside = Path(self.tmp.name) / 'outside.txt'
        outside.write_text('keep', encoding='utf-8')
        _, record = self.write()
        log = oplog.log_path()
        entries = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
        entries[0]['created'].append({'path': str(outside), 'size': 4, 'mtime_ns': outside.stat().st_mtime_ns, 'sha256': None})
        log.write_text('\n'.join(json.dumps(e) for e in entries) + '\n', encoding='utf-8')
        result = oplog.undo(record['id'])
        self.assertTrue(outside.exists())
        self.assertIn(str(outside), [row['path'] for row in result['kept']])

    def test_transfer_through_the_registry_is_logged(self):
        source = Path(self.tmp.name) / 'src'
        source.mkdir()
        CodexAdapter(home=str(source)).write(conversation(), session_id='0199aaaa-0000-7000-8000-0000000000d2', cwd=self.tmp.name)
        env = {'RELAY_CODEX_HOME': str(source)}
        os.environ.update(env)
        self.addCleanup(lambda: [os.environ.pop(key, None) for key in env])
        registry._CACHE.clear()
        self.addCleanup(registry._CACHE.clear)
        destination = Path(self.tmp.name) / 'claude'
        os.environ['RELAY_CLAUDE_HOME'] = str(destination)
        self.addCleanup(os.environ.pop, 'RELAY_CLAUDE_HOME', None)
        registry._CACHE.clear()
        rows = registry.list_sessions('codex')
        self.assertTrue(rows)
        result = registry.transfer('codex', rows[0]['id'], 'claude', cwd=self.tmp.name)
        logged = oplog.list_operations()
        self.assertEqual(logged[0]['kind'], 'transfer')
        self.assertEqual(logged[0]['target'], 'claude')
        self.assertEqual(logged[0]['path'], result['to']['path'])
        oplog.undo(logged[0]['id'])
        self.assertFalse(Path(result['to']['path']).exists())


if __name__ == '__main__':
    unittest.main()
