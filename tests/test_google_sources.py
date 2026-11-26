"""Synthetic Google session and portable archive checks."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from relay import archive, preview, registry, session_store
from relay.adapters.google import AntigravityAdapter, GeminiAdapter
from relay.adapters.workbuddy import WorkBuddyAdapter
from relay.corpus import Corpus


class GoogleTests(unittest.TestCase):
    def test_antigravity_transcript_to_gemini_import_file_and_back(self):
        folder = 'antigravity/brain/conversation/.system_generated/logs/'
        steps = [{'type': 'USER_INPUT', 'content': '<USER_REQUEST>中文问题</USER_REQUEST>'},
                 {'type': 'CHECKPOINT', 'content': 'internal'},
                 {'type': 'PLANNER_RESPONSE', 'content': 'answer', 'thinking': 'internal'}]
        compact = self.file(folder + 'transcript.jsonl', '\n'.join(map(json.dumps, steps)))
        source = AntigravityAdapter(str(self.root / 'antigravity'), restored_home=self.root / 'imports')
        registry._CACHE['antigravity'] = source
        sid = next(source.discover()).id
        full = self.file(folder + 'transcript_full.jsonl', compact.read_text(encoding='utf8'))
        compact.write_text('{bad', encoding='utf8')
        self.assertEqual([(r.id, Path(r.path)) for r in source.discover()], [(sid, full)])
        doc = registry.export_gemini_session('antigravity', sid)
        self.assertNotIn('internal', json.dumps(doc))
        self.file('gemini/demo/chats/session-fixture.json', json.dumps(doc))
        target = GeminiAdapter(str(self.root / 'gemini'), restored_home=self.root / 'imports')
        reread = target.read(next(target.discover()).id)
        self.assertEqual([(t.role, t.text()) for t in reread.turns], [('user', '中文问题'), ('assistant', 'answer')])
        full.unlink()
        self.assertFalse(next(source.discover()).readable)
        steps[0]['truncated_fields'] = ['content']
        compact.write_text('\n'.join(map(json.dumps, steps)), encoding='utf8')
        with self.assertRaises(ValueError):
            registry.export_gemini_session('antigravity', sid)
        with self.assertRaises(ValueError):
            session_store.store_session('antigravity', sid, str(self.root / 'storage'))

    def test_antigravity_default_discovers_each_client_and_honors_explicit_home(self):
        desktop = self.root / '.gemini/antigravity'
        for name in ('antigravity', 'antigravity-cli', 'antigravity-ide'):
            self.file('.gemini/' + name + '/brain/shared/.system_generated/logs/transcript.jsonl',
                      json.dumps({'type': 'USER_INPUT', 'content': name}))
        with patch.dict('os.environ', {'RELAY_ANTIGRAVITY_HOME': '', 'ANTIGRAVITY_HISTORY_HOME': ''}), \
                patch('pathlib.Path.home', return_value=self.root):
            all_clients = AntigravityAdapter(restored_home=self.root / 'restored')
            rows = list(all_clients.discover())
            self.assertEqual(len({row.id for row in rows}), 3)
            self.assertEqual({row.title for row in rows}, {'antigravity', 'antigravity-cli', 'antigravity-ide'})
            only_desktop = AntigravityAdapter(str(desktop), restored_home=self.root / 'restored')
            self.assertEqual([row.title for row in only_desktop.discover()], ['antigravity'])

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='relay-google-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        for guard in (patch.dict(registry._CACHE, clear=True),
                      patch.dict('os.environ', {'RELAY_LOG_HOME': str(self.root / 'log')})):
            guard.start()
            self.addCleanup(guard.stop)

    def file(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def test_gemini_replays_jsonl_and_legacy_json_with_project_and_tools(self):
        meta = {'sessionId': 'fixture', 'projectHash': 'demo'}
        original = {'id': 'original', 'type': 'user', 'content': 'Original question'}
        obsolete = {'id': 'old', 'type': 'gemini', 'content': 'obsolete'}
        newer = {'id': 'new', 'type': 'gemini', 'content': [{'text': 'before patch'}], 'model': 'gemini-fixture',
                 'thoughts': [{'subject': 'Short summary', 'description': 'Sample thought'}],
                 'toolCalls': [{'id': 'call', 'name': 'read_file', 'args': {'path': 'sample.txt'}}]}
        records = [meta, original, obsolete, {'$rewindTo': 'old'}, newer,
                   {'id': 'suffix', 'type': 'info', 'content': 'notice'},
                   {'id': 'removed', 'type': 'error', 'content': 'removed error'},
                   {'$patch': {'updates': [{'id': 'new', 'content': [{'text': '修改后的答复'}],
                                            'toolCalls': [{'id': 'call', 'result': [{'text': 'sample result'}]}]}],
                               'removeIds': ['removed'], 'orderIds': ['suffix', 'new']}},
                   {'$set': {'summary': 'Fixture title'}}]
        self.file('gemini/demo/chats/session-new.jsonl', '\n'.join(map(json.dumps, records)))
        self.file('gemini/demo/.project_root', str(self.root))
        self.file('gemini/second/chats/session-old.json', json.dumps(dict(meta, messages=[original])))
        self.file('gemini/not-history/session-ignored.json', json.dumps(dict(meta, messages=[original])))
        self.file('gemini/demo/chats/session-invalid.jsonl', '{broken')
        adapter = GeminiAdapter(str(self.root / 'gemini'), restored_home=self.root / 'imports/gemini')
        rows = list(adapter.discover())
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(row.readable for row in rows), 2)
        self.assertEqual(len({row.id for row in rows}), 3)
        current = next(row for row in rows if row.title == 'Fixture title')
        self.assertEqual(current.cwd, str(self.root))
        conv = adapter.read(current.id)
        self.assertEqual([turn.role for turn in conv.turns], ['user', 'system', 'assistant'])
        self.assertEqual(conv.cwd, str(self.root))
        self.assertEqual(conv.stats()['tool_call'], 1)
        self.assertEqual(conv.stats()['tool_result'], 1)
        self.assertIn('sample result', conv.turns[-1].text())
        self.assertIn('修改后的答复', conv.turns[-1].text())
        self.assertIn('Sample thought', conv.turns[-1].text())
        self.assertNotIn('obsolete', '\n'.join(turn.text() for turn in conv.turns))
        registry._CACHE.update(gemini=adapter, workbuddy=WorkBuddyAdapter(home=str(self.root / 'target')))
        plan = preview.conversion('gemini', current.id, 'workbuddy', cwd=str(self.root), session_id='gemini-transfer')
        result = registry.transfer('gemini', current.id, 'workbuddy', cwd=str(self.root),
                                   preview_token=plan['token'], session_id='gemini-transfer')
        self.assertTrue(result['ok'])
        self.assertIn('修改后的答复', registry.export_markdown('workbuddy', 'gemini-transfer'))

    def test_antigravity_artifacts_export_store_restore_index_and_undo(self):
        artifact = self.file('antigravity/brain/run-test/walkthrough.md', '# Demo artifact\n\n反重力验收文本')
        self.file('antigravity/exports/pinned.txt', 'hand-saved conversation')
        self.file('antigravity/brain/run-test/internal.md', 'should be excluded')
        self.file('antigravity/conversations/id.pb', 'unsupported')
        source = AntigravityAdapter(str(self.root / 'antigravity'), restored_home=self.root / 'first/imports/antigravity')
        registry._CACHE['antigravity'] = source
        rows = {Path(row.path).name: row for row in source.discover()}
        self.assertEqual(set(rows), {'walkthrough.md', 'pinned.txt'})
        row = rows[artifact.name]
        before = artifact.read_bytes()
        self.assertFalse(source.can_write)
        package = session_store.store_session(source.name, row.id, root=str(self.root / 'storage'))['path']
        data = session_store.SessionPackage.read(package)
        with data.open_source() as opened:
            self.assertIn('反重力验收文本', opened.read(row.id).turns[0].text())
        with self.assertRaises(ValueError):
            session_store.store_session(source.name, row.id, root=source.home)

        target = AntigravityAdapter(str(self.root / 'other-client'), restored_home=self.root / 'second/imports/antigravity')
        registry._CACHE['antigravity'] = target
        plan = preview.package(package, '')
        result = session_store.restore_session(package, '', preview_token=plan['token'])
        output = Path(result['to']['path'])
        self.assertEqual(output.parent, target.restored_home)
        self.assertEqual(target.read(row.id).turns[0].blocks[0].text, before.decode('utf-8'))
        self.assertEqual(artifact.read_bytes(), before)
        self.assertFalse(Path(target.home).exists())
        with self.assertRaises(FileExistsError):
            session_store.restore_session(package, '')
        corpus = Corpus(self.root / 'index')
        with patch.dict('os.environ', {'RELAY_ANTIGRAVITY_HOME': target.home}), \
                patch('relay.adapters.google.portable_home', return_value=target.restored_home):
            scanned = corpus.update(sources=['antigravity'], packages=False)
        self.assertEqual(scanned['indexed'], 1, scanned)
        self.assertEqual(len(corpus.search('反重力验收文本')['results']), 1)
        from relay import oplog
        receipt = next(row for row in oplog.list_operations() if row['kind'] == 'google-context-restore')
        self.assertTrue(oplog.undo(receipt['id'])['complete'])
        self.assertFalse(output.exists())
        manifest, files = archive.read_package(package, session_store.KIND)
        doc = json.loads(files[data.entry][0])
        doc['id'] = '../outside'
        with self.assertRaises(ValueError):
            session_store.SessionPackage(manifest, {data.entry: (json.dumps(doc).encode(), False)})

    def test_desktop_open_chat_is_validated_and_imports_once(self):
        from relay import gemini_desktop
        from relay.adapters.google import GeminiAppsAdapter

        adapter = GeminiAppsAdapter(str(self.root / 'chats'))
        registry._CACHE['gemini_apps'] = adapter
        key = 'u/0/app/example'
        snapshot = {'status': 'ready', 'chats': [{'key': key, 'active': True, 'title': 'Example'}],
                    'turns': [{'role': 'user', 'text': 'Question'}, {'role': 'assistant', 'text': 'Answer'}]}
        with patch.object(gemini_desktop, '_read', return_value=snapshot):
            self.assertEqual(gemini_desktop.import_open(key)['imported'], 1)
            self.assertEqual(gemini_desktop.import_open(key)['skipped'], 1)
            with self.assertRaises(ValueError):
                gemini_desktop.import_open('app/other')
            snapshot['turns'].pop()
            with self.assertRaises(ValueError):
                gemini_desktop.import_open(key)
        row, = adapter.discover()
        session = registry.export_gemini_session('gemini_apps', row.id)
        self.assertEqual([m['content'][0]['text'] for m in session['messages']], ['Question', 'Answer'])

    def test_gemini_apps_takeout_is_idempotent_and_handoff_is_text(self):
        from relay import gemini_apps
        from relay.adapters.google import GeminiAppsAdapter
        store = self.root / 'imports/gemini_apps'
        adapter = GeminiAppsAdapter(str(store))
        registry._CACHE['gemini_apps'] = adapter
        first = {'products': ['Gemini'], 'header': 'Gemini Apps', 'title': 'Prompted Exported question',
                 'time': '2026-03-04T10:00:00Z',
                 'safeHtmlItem': [{'html': '<p>Reply &amp; content</p><script>ignore me</script>'
                                           '<p>Second line</p>'}]}
        unrelated = {'header': 'Maps', 'time': '2026-03-04T10:00:00Z', 'title': 'Prompted Wrong product'}
        second = dict(first, title='Prompted Another question', time='2026-03-04T10:01:00Z')
        path = self.file('takeout/MyActivity.json', json.dumps([first, first, unrelated, second]))
        result = gemini_apps.import_file(str(path))
        self.assertEqual(result, {'ok': True, 'imported': 2, 'skipped': 1, 'ignored': 1})
        self.assertEqual(gemini_apps.import_file(str(path))['skipped'], 3)
        rows = list(adapter.discover())
        self.assertEqual(len(rows), 2)
        first_id = next(row.id for row in rows if row.title == 'Exported question')
        conv = adapter.read(first_id)
        self.assertEqual(conv.turns[0].text(), 'Exported question')
        self.assertIn('Reply & content', conv.turns[1].text())
        self.assertNotIn('ignore me', conv.turns[1].text())
        handoff = registry.export_chat_handoff('gemini_apps', first_id, 'en', 'msg.gemini_handoff_prompt')
        self.assertIn('next Gemini request', handoff)
        self.assertIn('Reply & content', handoff)
        self.assertNotIn('Wrong product', handoff)
        with self.assertRaises(ValueError):
            gemini_apps.import_file(str(self.file('takeout/wrong.json', json.dumps([unrelated]))))
