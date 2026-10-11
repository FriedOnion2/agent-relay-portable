"""Yuanbao exports only: synthetic data, isolated homes, no client credentials."""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import bootstrap
import cli
import server
from relay import archive, health, ir, locations, preview, registry, session_store, skill_store, yuanbao
from relay.adapters.yuanbao import YuanbaoAdapter, decode
from relay.corpus import Corpus


def document():
    return {'exportTime': '2026-10-12 09:30:00', 'cookie': 'never-import-credential', 'conversations': [
        {'id': 'session-one', 'title': '元宝测试一', 'messages': [
            {'role': 'user', 'content': '中文问题 <script>not executable</script>'},
            {'role': 'assistant', 'content': '中文答案', 'thinking': '独立思考'}]},
        {'id': 'session-two', 'title': 'other-private-title', 'messages': [
            {'role': 'user', 'content': 'other-private-body'}]}]}


class YuanbaoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / 'yuanbao'
        self.home.mkdir()
        self.project = self.root / 'project 中文'
        self.project.mkdir()
        self.source = self.root / 'source-export.json'
        self.source.write_text(json.dumps(document(), ensure_ascii=False), encoding='utf-8')
        self.adapter = YuanbaoAdapter(home=str(self.home))
        self.cache = patch.dict(registry._CACHE, {'yuanbao': self.adapter}, clear=True)
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.environment = patch.dict(os.environ, {
            'RELAY_STORAGE_HOME': str(self.root / 'storage'), 'RELAY_YUANBAO_HOME': str(self.home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.log = patch('relay.oplog.log_path', return_value=self.root / 'operations.jsonl')
        self.log.start()
        self.addCleanup(self.log.stop)

    def import_rows(self):
        yuanbao.import_file(str(self.source))
        return list(self.adapter.discover())

    def first_row(self):
        return next(row for row in self.import_rows() if row.native_id == 'session-one')

    def test_bulk_import_is_deduplicated_and_preserves_content_and_thinking(self):
        original = self.source.read_bytes()
        result = yuanbao.import_file(str(self.source))
        self.assertEqual((result['imported'], result['skipped']), (2, 0))
        self.assertEqual(yuanbao.import_file(str(self.source))['skipped'], 2)
        conv = self.adapter.read('session-one')
        self.assertEqual([turn.role for turn in conv.turns], [ir.USER, ir.ASSISTANT])
        self.assertEqual(conv.turns[1].blocks[0].kind, ir.THINKING)
        self.assertEqual(conv.turns[1].blocks[0].text, '独立思考')
        self.assertEqual(conv.turns[1].blocks[1].text, '中文答案')
        self.assertIsNone(conv.created_at)  # exportTime is not a message timestamp.
        self.assertIn('中文答案', registry.export_markdown('yuanbao', 'session-one', include_thinking=False))
        self.assertNotIn('独立思考', registry.export_markdown('yuanbao', 'session-one', include_thinking=False))
        self.assertEqual(self.source.read_bytes(), original)
        for path in self.home.glob('*.json'):
            self.assertNotIn(b'never-import-credential', path.read_bytes())

    def test_lookalikes_bad_roles_empty_content_and_invalid_unicode_fail_before_writes(self):
        values = [[], {'messages': []}, {'source': 'codex', 'id': 'x', 'messages': []},
                  dict(document(), conversations=[])]
        for value in (True, None, 123, {}):
            data = document()
            data['conversations'][0]['messages'][0]['content'] = value
            values.append(data)
        for mutation in ({'role': 'unknown'}, {'content': '', 'thinking': ''}, {'content': '\ud800'}):
            data = document()
            data['conversations'][0]['messages'][0].update(mutation)
            values.append(data)
        for data in values:
            with self.subTest(data=data):
                self.source.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaises(ValueError):
                    yuanbao.import_file(str(self.source))
                self.assertEqual(list(self.home.glob('*.json')), [])
        with self.assertRaises(ValueError):
            decode(b'{"source":"yuanbao","source":"codex"}')
        with patch.object(archive, 'MAX_FILE', 5), self.assertRaises(ValueError):
            decode(b'{"messages":[]}')

    def test_partial_publication_failure_rolls_back_all_created_exports(self):
        original = yuanbao.atomic_write
        calls = []
        def fail_second(*args, **kwargs):
            calls.append(args)
            if len(calls) == 2:
                raise OSError('simulated full disk')
            return original(*args, **kwargs)
        with patch.object(yuanbao, 'atomic_write', side_effect=fail_second), self.assertRaises(OSError):
            yuanbao.import_file(str(self.source))
        self.assertEqual(list(self.home.iterdir()), [])

    def test_bad_file_is_visible_as_unreadable_and_input_paths_are_bounded(self):
        (self.home / 'broken.json').write_text('{"source":"yuanbao"', encoding='utf-8')
        row = next(self.adapter.discover())
        self.assertFalse(row.readable)
        with self.assertRaises(ValueError):
            self.adapter.read(row.id)
        with self.assertRaises(ValueError):
            yuanbao.import_file('relative.json')
        database = self.root / 'chat_message_v2.db'
        database.write_bytes(b'not a plaintext export')
        with self.assertRaises(ValueError):
            yuanbao.import_file(str(database))

    def test_same_native_id_revisions_have_stable_selectors_and_ambiguous_id_refuses(self):
        self.import_rows()
        data = document()
        data['conversations'] = data['conversations'][:1]
        data['conversations'][0]['messages'][1]['content'] = 'another revision'
        self.source.write_text(json.dumps(data), encoding='utf-8')
        yuanbao.import_file(str(self.source))
        rows = [row for row in self.adapter.discover() if row.native_id == 'session-one']
        self.assertEqual(len(rows), 2)
        self.assertEqual({row.variant_count for row in rows}, {2})
        with self.assertRaises(ValueError):
            self.adapter.read('session-one')
        contents = {self.adapter.read(row.id).turns[1].blocks[1].text for row in rows}
        self.assertEqual(contents, {'中文答案', 'another revision'})
        moved = self.root / 'another device'
        shutil.move(str(self.home), str(moved))
        adapter = YuanbaoAdapter(home=str(moved))
        self.assertEqual({row.id for row in rows}, {row.id for row in adapter.discover() if row.native_id == 'session-one'})
        for row in rows:
            self.assertEqual(adapter.read(row.id).stats()['turns'], 2)

    def test_migrates_to_existing_writers_but_never_offers_native_yuanbao_or_skill_write(self):
        row = self.first_row()
        for target in registry.writable_keys():
            adapter = registry.get(target, home=str(self.root / target))
            registry._CACHE[target] = adapter
            result = registry.transfer('yuanbao', row.id, target, cwd=str(self.project),
                                       session_id='11111111-1111-4111-8111-111111111111')
            self.assertTrue(result['ok'])
            restored = adapter.read(next(adapter.discover()).id)
            self.assertIn('中文答案', '\n'.join(turn.text() for turn in restored.turns))
            self.assertEqual(restored.stats()['thinking'], 1)
        self.assertNotIn('yuanbao', registry.writable_keys())
        self.assertNotIn('yuanbao', registry.cross_system_keys())
        with self.assertRaises(ValueError):
            self.adapter.write(ir.Conversation())
        with self.assertRaises(ValueError):
            skill_store.skill_roots('yuanbao')
        self.assertNotIn('native_restore', self.adapter.info()['capabilities'])
        self.assertNotIn('skill_store', self.adapter.info()['capabilities'])

    def test_single_selected_export_package_moves_without_source_and_refuses_collisions(self):
        # Package directly from a batch: never archive the other conversations.
        shutil.copyfile(self.source, self.home / 'batch.json')
        selected = next(row for row in self.adapter.discover() if row.native_id == 'session-one')
        result = session_store.store_session('yuanbao', selected.id, self.root / 'storage')
        manifest, files = archive.read_package(result['path'], session_store.KIND)
        self.assertEqual(manifest['session']['format'], 'yuanbao-export-json')
        self.assertEqual(set(files), {'root0/session.json'})
        self.assertNotIn(b'other-private', files['root0/session.json'][0])
        self.assertNotIn(b'never-import-credential', files['root0/session.json'][0])
        moved = self.root / 'moved.zip'
        shutil.move(result['path'], str(moved))
        shutil.rmtree(self.home)
        self.source.unlink()
        target = YuanbaoAdapter(home=str(self.root / 'new-device'))
        registry._CACHE['yuanbao'] = target
        plan = preview.package(str(moved), str(self.project))
        self.assertEqual(plan['mode'], 'yuanbao-export-json')
        restored = session_store.restore_session(str(moved), str(self.project), preview_token=plan['token'])
        conv = target.read(restored['to']['id'])
        self.assertEqual(conv.cwd, str(self.project))
        self.assertEqual(conv.turns[1].blocks[0].text, '独立思考')
        before = Path(restored['to']['path']).read_bytes()
        with self.assertRaises(FileExistsError):
            session_store.restore_session(str(moved), str(self.project))
        self.assertEqual(Path(restored['to']['path']).read_bytes(), before)
        new = session_store.restore_session(str(moved), str(self.project), session_id='new-copy')
        self.assertEqual(target.read(new['to']['id']).id, 'new-copy')

    def test_restore_validates_content_ids_and_preview_destination_before_writes(self):
        selected = self.first_row()
        result = session_store.store_session('yuanbao', selected.id, self.root / 'storage')
        plan = preview.package(result['path'], str(self.project), session_id='new-copy')
        registry._CACHE['yuanbao'] = YuanbaoAdapter(home=str(self.root / 'changed-home'))
        with self.assertRaises(ValueError):
            session_store.restore_session(result['path'], str(self.project), 'new-copy', preview_token=plan['token'])
        self.assertFalse((self.root / 'changed-home').exists())
        manifest, files = archive.read_package(result['path'], session_store.KIND)
        manifest['session']['id'] = 'wrong-conversation'
        forged = archive.write_package(self.root / 'forged.zip', manifest, files)
        with self.assertRaises(ValueError):
            preview.package(forged['path'], str(self.project))
        with self.assertRaises(ValueError):
            session_store.restore_session(forged['path'], str(self.project))

    def test_cli_configuration_health_and_search_work_without_a_native_store(self):
        self.assertIn('yuanbao', cli.READ_AGENTS)
        self.assertNotIn('windows_yuanbao', cli.READ_AGENTS)
        self.assertEqual(cli.build_parser().parse_args(['import-yuanbao', str(self.source)]).func, cli.cmd_import_yuanbao)
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(locations.default_home('yuanbao').endswith(os.path.join('imports', 'yuanbao')))
            bootstrap.apply_config({'agent_homes': {'yuanbao': str(self.home)}})
            self.assertEqual(os.environ['RELAY_YUANBAO_HOME'], str(self.home))
        checked = health.check('yuanbao')
        self.assertEqual(checked['status'], 'passed')
        self.assertEqual(checked['evidence'], 'synthetic-export-read')
        self.assertEqual(checked['native_file_roundtrip'], 'unsupported')
        row = self.first_row()
        session_store.store_session('yuanbao', row.id, self.root / 'storage')
        corpus = Corpus(self.root)
        indexed = corpus.update(sources=['yuanbao'], include_thinking=False)
        self.assertFalse(indexed['errors'])
        self.assertTrue(corpus.search('中文答案')['results'])
        self.assertFalse(corpus.search('独立思考')['results'])
        shutil.rmtree(self.home)
        indexed = corpus.update(sources=[], packages=True)
        self.assertFalse(indexed['errors'])
        self.assertTrue(corpus.search('中文答案')['results'])

    def test_http_import_and_bad_format_return_structured_messages(self):
        srv = server.create_server('127.0.0.1', 0)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            def request(path):
                con = http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=5)
                try:
                    con.request('POST', '/api/import-yuanbao', json.dumps({'path': path}),
                                {'Content-Type': 'application/json'})
                    response = con.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    con.close()
            status, result = request(str(self.source))
            self.assertEqual(status, 200)
            self.assertEqual(result['imported'], 2)
            status, result = request('relative.json')
            self.assertEqual(status, 400)
            self.assertEqual(result['error_message']['code'], 'err.yuanbao_input_path')
        finally:
            srv.shutdown()
            thread.join(5)
            srv.server_close()
