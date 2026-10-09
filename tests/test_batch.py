import unittest
from pathlib import Path

import test_native_import
from relay import batch, ir, registry


class BatchTests(unittest.TestCase):
    setUp = test_native_import.NativeImportTests.setUp

    def seed(self, count=3):
        ids = []
        for i in range(count):
            conv = ir.Conversation(source='fixture', cwd=str(self.cwd), title='会话%d' % i, turns=[
                ir.Turn(ir.USER, [ir.Block.text_block('问题 %d' % i)]),
                ir.Turn(ir.ASSISTANT, [ir.Block.text_block('回答 %d' % i)])])
            self.targets['claude'].write(conv, session_id='src-%d' % i)
            ids.append('src-%d' % i)
        return ids

    def codex_ids(self):
        return {row.id for row in self.targets['codex'].discover()}

    def test_target_id_is_deterministic_and_distinct(self):
        self.assertEqual(batch.target_id('claude', 'a', 'codex'), batch.target_id('claude', 'a', 'codex'))
        self.assertNotEqual(batch.target_id('claude', 'a', 'codex'), batch.target_id('claude', 'b', 'codex'))
        self.assertNotEqual(batch.target_id('claude', 'a', 'codex'), batch.target_id('claude', 'a', 'workbuddy'))

    def test_dry_run_writes_nothing(self):
        ids = self.seed()
        res = batch.run('claude', 'codex', ids=ids, cwd=str(self.cwd), dry_run=True)
        self.assertEqual((res['would-migrate'], res['migrated'], res['failed']), (3, 0, 0))
        self.assertEqual(self.codex_ids(), set())

    def test_run_migrates_and_second_run_skips(self):
        ids = self.seed()
        first = batch.run('claude', 'codex', ids=ids, cwd=str(self.cwd), dry_run=False)
        self.assertEqual((first['migrated'], first['skipped'], first['failed']), (3, 0, 0))
        self.assertEqual(self.codex_ids(), {batch.target_id('claude', sid, 'codex') for sid in ids})
        again = batch.run('claude', 'codex', ids=ids, cwd=str(self.cwd), dry_run=False)
        self.assertEqual((again['migrated'], again['skipped']), (0, 3))
        self.assertEqual(len(self.codex_ids()), 3)

    def test_new_policy_creates_a_fresh_copy(self):
        ids = self.seed(1)
        batch.run('claude', 'codex', ids=ids, cwd=str(self.cwd), dry_run=False)
        res = batch.run('claude', 'codex', ids=ids, cwd=str(self.cwd), on_conflict='new', dry_run=False)
        self.assertEqual(res['migrated'], 1)
        self.assertEqual(len(self.codex_ids()), 2)

    def test_fail_policy_stops_at_first_conflict(self):
        ids = self.seed()
        batch.run('claude', 'codex', ids=ids[:1], cwd=str(self.cwd), dry_run=False)
        res = batch.run('claude', 'codex', ids=ids, cwd=str(self.cwd), on_conflict='fail', dry_run=False)
        self.assertTrue(res['stopped_early'])
        self.assertFalse(res['ok'])
        self.assertEqual((res['processed'], res['failed'], res['migrated']), (1, 1, 0))
        self.assertEqual(len(self.codex_ids()), 1)

    def test_one_bad_session_does_not_stop_the_batch(self):
        from unittest import mock
        ids = self.seed()
        real = registry.transfer

        def flaky(source, sid, *args, **kwargs):
            if sid == ids[1]:
                raise ValueError('源会话没有可迁移的内容')
            return real(source, sid, *args, **kwargs)

        with mock.patch.object(registry, 'transfer', flaky):
            res = batch.run('claude', 'codex', ids=ids, cwd=str(self.cwd), dry_run=False)
            self.assertEqual((res['migrated'], res['failed'], res['processed']), (2, 1, 3))
            self.assertFalse(res['ok'])
            self.assertIn('没有可迁移', res['items'][1]['error'])
            stop = batch.run('claude', 'codex', ids=ids, cwd=str(self.cwd), on_conflict='new', dry_run=False, stop_on_error=True)
            self.assertTrue(stop['stopped_early'])
            self.assertEqual(stop['processed'], 2)

    def test_selection_by_keyword_limit_and_unknown_id(self):
        ids = self.seed()
        res = batch.run('claude', 'codex', keyword='会话1', cwd=str(self.cwd), dry_run=True)
        self.assertEqual([item['id'] for item in res['items']], [ids[1]])
        self.assertEqual(batch.run('claude', 'codex', limit=2, cwd=str(self.cwd), dry_run=True)['selected'], 2)
        with self.assertRaisesRegex(ValueError, '找不到会话'):
            batch.run('claude', 'codex', ids=['nope'], dry_run=True)

    def test_invalid_arguments(self):
        with self.assertRaisesRegex(ValueError, 'on_conflict'):
            batch.run('claude', 'codex', on_conflict='overwrite')
        with self.assertRaisesRegex(ValueError, 'limit'):
            batch.run('claude', 'codex', limit=0)

    def test_redaction_is_applied_to_every_item(self):
        secret = 'sk-' + 'proj-' + 'AbCdEfGh1234567890XyZ'
        conv = ir.Conversation(source='fixture', cwd=str(self.cwd), turns=[
            ir.Turn(ir.USER, [ir.Block.text_block('key ' + secret)]), ir.Turn(ir.ASSISTANT, [ir.Block.text_block('ok')])])
        self.targets['claude'].write(conv, session_id='leaky')
        res = batch.run('claude', 'codex', ids=['leaky'], cwd=str(self.cwd), dry_run=False, redact_secrets=True)
        self.assertNotIn(secret, Path(res['items'][0]['path']).read_text(encoding='utf-8'))

    def test_progress_callback_reports_every_item(self):
        ids = self.seed()
        seen = []
        batch.run('claude', 'codex', ids=ids, cwd=str(self.cwd), dry_run=True, progress=lambda i, n, item: seen.append((i, n)))
        self.assertEqual(seen, [(1, 3), (2, 3), (3, 3)])


if __name__ == '__main__':
    unittest.main()
