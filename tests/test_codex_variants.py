"""A native thread ID can have several independently selectable rollouts."""
import json
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from relay import archive, batch, corpus, preview, registry, session_store
from relay.adapters.codex import CodexAdapter
from relay.adapters.claude import ClaudeAdapter
import cli

SID = '11111111-1111-4111-8111-111111111111'


class CodexVariantsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = CodexAdapter(home=str(self.root / 'source'))
        self.paths = []
        for number in (1, 2):
            path = Path(self.source.home) / ('rollout-%d-%s.jsonl' % (number, SID))
            path.parent.mkdir(parents=True, exist_ok=True)
            records = [
                {'type': 'session_meta', 'payload': {'id': SID, 'cwd': '/original', 'model_provider': 'openai'}},
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                  'content': [{'type': 'input_text', 'text': 'variant %d' % number}]}},
            ]
            path.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
            self.paths.append(path)

    def test_list_has_unique_selectors_and_preserves_native_id(self):
        rows = list(self.source.discover())
        self.assertEqual(len({row.id for row in rows}), 2)
        for row in rows:
            self.assertEqual(row.native_id, SID)
            self.assertEqual(row.variant_count, 2)
            self.assertEqual(self.source.read(row.id).path, row.path)
            self.assertEqual(self.source.read(row.id).id, SID)

    def test_native_id_and_short_id_refuse_ambiguous_reads(self):
        for sid in (SID, SID[:8]):
            with self.subTest(sid=sid), self.assertRaisesRegex(ValueError, '多个|多条'):
                self.source.read(sid)

    def test_five_rollouts_with_one_title_do_not_collapse(self):
        for number in (3, 4, 5):
            (Path(self.source.home) / ('rollout-%d-%s.jsonl' % (number, SID))).write_bytes(self.paths[0].read_bytes())
        Path(self.source.index_path).write_text(json.dumps({'id': SID, 'thread_name': 'same title'}) + '\n', encoding='utf-8')
        rows = list(self.source.discover())
        self.assertEqual(len({row.id for row in rows}), 5)
        self.assertEqual({row.title for row in rows}, {'same title'})
        self.assertEqual({row.variant_count for row in rows}, {5})

    def test_cli_lists_paths_and_show_reads_selected_rollout(self):
        with patch.dict(registry._CACHE, {'codex': self.source}, clear=True):
            row = next(row for row in self.source.discover() if Path(row.path) == self.paths[1])
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(cli.main(['list', 'codex']), 0)
            self.assertIn(row.id, output.getvalue())
            self.assertIn(row.path, output.getvalue())
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(['show', 'codex', SID]), 1)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(cli.main(['show', 'codex', row.id, '--json']), 0)
            self.assertIn('variant 2', output.getvalue())
            self.assertNotIn('variant 1', output.getvalue())

    def test_missing_selected_rollout_does_not_fall_back_to_a_sibling(self):
        row = next(row for row in self.source.discover() if Path(row.path) == self.paths[1])
        self.paths[1].unlink()
        with self.assertRaises(FileNotFoundError):
            self.source.read(row.id)

    def test_batch_migration_preserves_each_variant_and_is_idempotent(self):
        target = ClaudeAdapter(home=str(self.root / 'target'))
        with patch.dict(registry._CACHE, {'codex': self.source, 'claude': target}, clear=True):
            result = batch.run('codex', 'claude', cwd=str(self.root), dry_run=False)
            self.assertEqual(result['migrated'], 2)
            self.assertEqual({target.read(item['target_id']).first_user_text() for item in result['items']},
                             {'variant 1', 'variant 2'})
            repeated = batch.run('codex', 'claude', cwd=str(self.root), dry_run=False)
            self.assertEqual(repeated['skipped'], 2)

    def test_offline_index_keeps_both_variant_contents(self):
        with patch.object(corpus.device, 'identity', return_value='fixture-device'), \
             patch.object(registry, 'get', return_value=self.source):
            store = corpus.Corpus(self.root / 'portable')
            result = store.update(sources=['codex'], packages=False)
            self.assertEqual(result['errors'], [])
            self.assertEqual(result['indexed'], 2)
            hits = store.search('variant')['results']
            self.assertEqual(len(hits), 2)
            self.assertEqual(len({hit['sid'] for hit in hits}), 2)
            bodies = {store.document(hit['key'])['conversation']['turns'][0]['blocks'][0]['text'] for hit in hits}
            self.assertEqual(bodies, {'variant 1', 'variant 2'})

    def test_selector_remains_valid_after_sibling_disappears_or_home_moves(self):
        row = next(row for row in self.source.discover() if Path(row.path) == self.paths[1])
        self.paths[0].unlink()
        self.assertEqual(self.source.read(row.id).first_user_text(), 'variant 2')
        moved = self.root / 'moved'
        Path(self.source.root).rename(moved)
        other = CodexAdapter(home=str(moved))
        self.assertEqual(other.read(row.id).first_user_text(), 'variant 2')

    def test_storing_selected_rollout_restores_that_variant_only(self):
        target = CodexAdapter(home=str(self.root / 'target'))
        project = self.root / 'project'
        project.mkdir()
        with patch.dict(registry._CACHE, {'codex': self.source}, clear=True):
            row = next(row for row in self.source.discover() if Path(row.path) == self.paths[1])
            result = session_store.store_session('codex', row.id, self.root / 'storage')
        manifest, files = archive.read_package(result['path'], session_store.KIND)
        self.assertEqual(manifest['session']['id'], SID)
        self.assertEqual(manifest['session']['selection_id'], row.id)
        self.assertEqual(files[manifest['entry']][0], self.paths[1].read_bytes())
        with patch.dict(registry._CACHE, {'codex': target}, clear=True):
            restored = session_store.restore_session(result['path'], str(project.resolve()))
        self.assertEqual(target.read(restored['to']['id']).first_user_text(), 'variant 2')
        self.assertEqual(target.read(restored['to']['id']).id, SID)

    def test_preview_binds_the_selected_file_and_rejects_changes(self):
        target = ClaudeAdapter(home=str(self.root / 'target'))
        with patch.dict(registry._CACHE, {'codex': self.source, 'claude': target}, clear=True):
            rows = list(self.source.discover())
            plans = [preview.conversion('codex', row.id, 'claude') for row in rows]
            self.assertNotEqual(plans[0]['token'], plans[1]['token'])
            selected = Path(rows[1].path)
            selected.write_text(selected.read_text(encoding='utf-8').replace('variant 2', 'changed'), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '变化|改变'):
                registry.transfer('codex', rows[1].id, 'claude', preview_token=plans[1]['token'])
            self.assertFalse(Path(target.home).exists())
