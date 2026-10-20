"""International WorkBuddy: synthetic files only, no real user stores or credentials."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import bootstrap
import cli
from relay import archive, health, ir, locations, preview, registry, session_store
from relay.adapters.workbuddy import WorkBuddyAdapter
from relay.adapters.workbuddy_ai import WorkBuddyAIAdapter
from test_relay import sample, content


class WorkBuddyAITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / 'project 中文'
        self.project.mkdir()
        self.device_root = self.root / '.workbuddy-ai'
        self.account = self.device_root / 'user-fixture-personal'
        self.account.mkdir(parents=True)
        self.source = WorkBuddyAIAdapter(home=str(self.device_root))
        self.cache = patch.dict(registry._CACHE, {'workbuddy_ai': self.source}, clear=True)
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.environment = patch.dict(os.environ, {'RELAY_STORAGE_HOME': str(self.root / 'storage')})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.log = patch('relay.oplog.log_path', return_value=self.root / 'operations.jsonl')
        self.log.start()
        self.addCleanup(self.log.stop)

    def seed(self):
        path = Path(self.source.write(sample(), cwd=str(self.project), session_id='fixture'))
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        rows[0]['meta']['future-field'] = {'keep': [1, 2]}
        path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
        return path

    def test_identity_default_and_configuration_are_independent(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(locations.Path, 'home', return_value=self.root):
            self.assertEqual(locations.default_home('workbuddy_ai'), str(self.device_root))
            self.assertEqual(locations.default_home('workbuddy'), str(self.root / '.workbuddy'))
            with patch.dict(os.environ, {'WORKBUDDY_HOME': str(self.root / 'cn'),
                                        'CODEBUDDY_CONFIG_DIR': str(self.root / 'codebuddy')}):
                self.assertEqual(locations.resolve_home('workbuddy_ai'), str(self.device_root))
            bootstrap.apply_config({'agent_homes': {'workbuddy_ai': str(self.account), 'workbuddy': str(self.root / 'cn')}})
            self.assertEqual(locations.resolve_home('workbuddy_ai'), str(self.account))
            self.assertEqual(locations.resolve_home('workbuddy'), str(self.root / 'cn'))
            self.assertEqual(locations.resolve_home('workbuddy_ai', str(self.root / 'explicit')), str(self.root / 'explicit'))
        self.assertIn('workbuddy_ai', cli.READ_AGENTS)
        self.assertIn('workbuddy_ai', registry.writable_keys())
        self.assertIn('workbuddy_ai', registry.cross_system_keys())

    def test_account_scope_and_legacy_layout_roundtrip_keep_thinking_and_tools(self):
        path = self.seed()
        self.assertEqual(Path(self.source.root), self.account)
        self.assertIn(self.account, path.parents)
        summary = next(self.source.discover())
        self.assertEqual(summary.source, 'workbuddy_ai')
        self.assertEqual(content(self.source.read(summary.id)), content(sample()))
        self.assertEqual(self.source.read(summary.id).source, 'workbuddy_ai')
        legacy = WorkBuddyAIAdapter(home=str(self.root / 'legacy'))
        legacy.write(sample(), session_id='legacy')
        self.assertEqual(content(legacy.read('legacy')), content(sample()))
        self.assertNotEqual(self.source.root, WorkBuddyAdapter(home=str(self.root / '.workbuddy')).root)
        self.assertEqual(list(WorkBuddyAdapter(home=str(self.root / '.workbuddy')).discover()), [])

    def test_multiple_accounts_require_explicit_selection_before_writes(self):
        other = self.device_root / 'user-another-personal'
        other.mkdir()
        with self.assertRaises(ValueError) as error:
            WorkBuddyAIAdapter(home=str(self.device_root))
        self.assertEqual(error.exception.args[0].code, 'err.workbuddy_ai_select_account_directory')
        explicit = WorkBuddyAIAdapter(home=str(other))
        self.assertEqual(Path(explicit.root), other)
        self.assertFalse((self.device_root / 'projects').exists())
        with patch.object(archive, 'is_link', return_value=True), self.assertRaises(ValueError):
            WorkBuddyAIAdapter(home=str(self.device_root))

    def test_desktop_device_store_is_not_hidden_by_account_support_directories(self):
        # The 5.8.4 desktop keeps transcripts and its session database at the
        # device root; user-* can contain identity files without transcripts.
        desktop = WorkBuddyAdapter(home=str(self.device_root))
        desktop.write(sample(), cwd=str(self.project), session_id='desktop-fixture')
        # Unused identity-directory links cannot block a valid device store.
        with patch.object(archive, 'is_link', return_value=True):
            detected = WorkBuddyAIAdapter(home=str(self.device_root))
        self.assertEqual(Path(detected.root), self.device_root)
        self.assertEqual(content(detected.read('desktop-fixture')), content(sample()))
        detected.write(sample(), cwd=str(self.project), session_id='desktop-copy')
        self.assertTrue(any(row.id == 'desktop-copy' for row in desktop.discover()))
        self.assertFalse((self.account / 'projects').exists())

    def test_empty_desktop_database_selects_device_root_before_first_transcript(self):
        (self.device_root / 'workbuddy.db').touch()
        detected = WorkBuddyAIAdapter(home=str(self.device_root))
        self.assertEqual(Path(detected.root), self.device_root)

    def read_output(self, adapter, path):
        row = next(row for row in adapter.discover()
                   if Path(row.path).resolve() == Path(path).resolve())
        self.assertEqual(row.source, adapter.name)
        return row.id, adapter.read(row.id)

    def assert_transfer_content(self, actual, expected):
        self.assertEqual(content(actual), content(expected))
        self.assertEqual([block.is_error for turn in actual.turns for block in turn.blocks
                          if block.kind == ir.TOOL_RESULT],
                         [block.is_error for turn in expected.turns for block in turn.blocks
                          if block.kind == ir.TOOL_RESULT])
        self.assertEqual(actual.title, expected.title)
        self.assertEqual(Path(actual.cwd).resolve(), self.project)

    def test_both_editions_transfer_both_ways_with_every_writable_peer(self):
        # Exercise both inbound and outbound paths. The earlier test only
        # returned from domestic WorkBuddy, leaving other inbound paths untested.
        for edition in ('workbuddy', 'workbuddy_ai'):
            for peer in registry.writable_keys():
                if peer == edition:
                    continue
                with self.subTest(edition=edition, peer=peer):
                    case = self.root / (edition + '-' + peer)
                    src = registry.get(edition, home=str(case / 'source'))
                    dst = registry.get(peer, home=str(case / 'target'))
                    original = sample()
                    original.turns[3].blocks[0].is_error = True
                    path = Path(src.write(original, cwd=str(self.project), session_id='fixture'))
                    before = path.read_bytes()
                    expected = src.read('fixture')
                    with patch.dict(registry._CACHE, {edition: src, peer: dst}, clear=True):
                        outward = registry.transfer(edition, 'fixture', peer, cwd=str(self.project),
                                                   session_id='11111111-1111-4111-8111-111111111111')
                        sid, converted = self.read_output(dst, outward['to']['path'])
                        self.assert_transfer_content(converted, expected)
                        self.assertEqual(outward['from']['source'], edition)
                        self.assertEqual(outward['to']['source'], peer)
                        converted_bytes = Path(converted.path).read_bytes()
                        inward = registry.transfer(peer, sid, edition, cwd=str(self.project),
                                                  session_id='22222222-2222-4222-8222-222222222222')
                        _, returned = self.read_output(src, inward['to']['path'])
                        self.assert_transfer_content(returned, expected)
                        self.assertEqual(returned.source, edition)
                        self.assertEqual(Path(converted.path).read_bytes(), converted_bytes)
                    self.assertEqual(path.read_bytes(), before)

    def test_read_only_sources_migrate_into_both_editions_but_reject_reverse(self):
        from relay.adapters.claude import ClaudeAdapter
        from relay.adapters.yuanbao import encode

        for source in ('codebuddy', 'claude_sdk', 'yuanbao'):
            home = self.root / source
            home.mkdir()
            if source == 'codebuddy':
                WorkBuddyAdapter(home=str(home)).write(sample(), cwd=str(self.project), session_id='fixture')
            elif source == 'claude_sdk':
                ClaudeAdapter(home=str(home)).write(sample(), cwd=str(self.project), session_id='fixture')
            else:
                (home / 'fixture.json').write_bytes(encode({
                    'id': 'fixture', 'title': '元宝迁出测试', 'cwd': str(self.project),
                    'messages': [{'role': 'user', 'content': '问题'},
                                 {'role': 'assistant', 'content': '回答', 'thinking': '思考'}]}))
            src = registry.get(source, home=str(home))
            sid = next(src.discover()).id
            expected = src.read(sid)
            before = {path: path.read_bytes() for path in home.rglob('*') if path.is_file()}
            for edition in ('workbuddy', 'workbuddy_ai'):
                with self.subTest(source=source, edition=edition):
                    dst = registry.get(edition, home=str(self.root / (source + '-' + edition)))
                    with patch.dict(registry._CACHE, {source: src, edition: dst}, clear=True):
                        result = registry.transfer(source, sid, edition, cwd=str(self.project), session_id='imported')
                        imported_id, imported = self.read_output(dst, result['to']['path'])
                        self.assert_transfer_content(imported, expected)
                        self.assertEqual(imported.source, edition)
                        with self.assertRaises(ValueError) as error:
                            registry.transfer(edition, imported_id, source, cwd=str(self.project))
                        self.assertEqual(error.exception.args[0].code,
                                         'err.label_does_not_support_migration_writes_yet')
            self.assertEqual({path: path.read_bytes() for path in home.rglob('*') if path.is_file()}, before)

    def test_same_id_in_both_editions_stays_separate_through_archive_restore(self):
        adapters = {edition: registry.get(edition, home=str(self.root / edition))
                    for edition in ('workbuddy', 'workbuddy_ai')}
        originals = {}
        for edition, adapter in adapters.items():
            conv = sample()
            conv.title = edition + ' 独立来源'
            conv.turns[0].blocks[0].text = edition + ' ONLY'
            path = Path(adapter.write(conv, cwd=str(self.project), session_id='same-id'))
            originals[edition] = (path, path.read_bytes())
        with patch.dict(registry._CACHE, adapters, clear=True):
            for edition, adapter in adapters.items():
                with self.subTest(edition=edition):
                    listed = registry.list_sessions(edition)
                    self.assertEqual(len(listed), 1)
                    self.assertEqual(listed[0]['source'], edition)
                    self.assertEqual(listed[0]['title'], edition + ' 独立来源')
                    stored = session_store.store_session(edition, 'same-id', self.root / 'storage')
                    manifest, _ = archive.read_package(stored['path'], session_store.KIND)
                    self.assertEqual(manifest['agent'], edition)
                    self.assertEqual(manifest['source'], edition)
                    result = session_store.restore_session(stored['path'], str(self.project), session_id='restored')
                    self.assertEqual(result['to']['source'], edition)
                    self.assertIn(Path(adapter.root), Path(result['to']['path']).parents)
                    self.assertEqual(adapter.read('restored').first_user_text(), edition + ' ONLY')
                    other = adapters['workbuddy' if edition == 'workbuddy_ai' else 'workbuddy_ai']
                    self.assertEqual(other.read('same-id').first_user_text(), other.name + ' ONLY')
        for path, before in originals.values():
            self.assertEqual(path.read_bytes(), before)

    def test_native_package_travels_without_accounts_and_refuses_id_collisions(self):
        path = self.seed()
        for name in ('keyblob', 'settings.json', 'workbuddy.db'):
            (self.device_root / name).write_text('do-not-transfer-account-data', encoding='utf-8')
        self.source.write(sample(), session_id='unselected')
        original = path.read_bytes()
        stored = session_store.store_session('workbuddy_ai', 'fixture', self.root / 'storage')
        manifest, files = archive.read_package(stored['path'], session_store.KIND)
        self.assertEqual(manifest['agent'], 'workbuddy_ai')
        self.assertEqual(len(files), 1)
        self.assertEqual(next(iter(files.values()))[0], original)
        self.assertFalse(any('user-fixture' in name or 'unselected' in name for name in files))
        moved = self.root / 'moved.zip'
        shutil.move(stored['path'], moved)
        shutil.rmtree(self.device_root)
        target_root = self.root / 'new-device' / '.workbuddy-ai'
        target_account = target_root / 'user-new-device-personal'
        target_account.mkdir(parents=True)
        target = WorkBuddyAIAdapter(home=str(target_root))
        registry._CACHE['workbuddy_ai'] = target
        new_project = self.root / 'new project'
        new_project.mkdir()
        plan = preview.package(str(moved), str(new_project), session_id='new-id')
        result = session_store.restore_session(str(moved), str(new_project), session_id='new-id', preview_token=plan['token'])
        self.assertIn(target_account, Path(result['to']['path']).parents)
        restored = target.read('new-id')
        self.assertEqual(content(restored), content(sample()))
        self.assertEqual(restored.cwd.replace('\\', '/'), new_project.as_posix())
        self.assertEqual(restored.meta['future-field'], {'keep': [1, 2]})
        records = [json.loads(line) for line in Path(restored.path).read_text(encoding='utf-8').splitlines()]
        self.assertTrue(all(row.get('sessionId') == 'new-id' for row in records))
        with self.assertRaises(FileExistsError):
            session_store.restore_session(str(moved), str(new_project), session_id='new-id')
        self.assertFalse((target_root / 'workbuddy.db').exists())
        self.assertEqual(list(new_project.iterdir()), [])

    def test_offline_health_is_honest_about_client_resume(self):
        result = health.check('workbuddy_ai')
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['native_resume'], 'not-tested')

    def test_cross_system_multi_account_selection_and_native_roundtrip(self):
        from relay import device, native_import
        remote_profile = self.root / 'remote-profile'
        remote_root = remote_profile / '.workbuddy-ai'
        first = remote_root / 'user-first-personal'
        second = remote_root / 'user-second-personal'
        first.mkdir(parents=True)
        second.mkdir()
        WorkBuddyAIAdapter(home=str(first)).write(sample(), session_id='remote-first')
        WorkBuddyAIAdapter(home=str(second)).write(sample(), session_id='remote-second')
        for prefix, system in (('windows', 'Linux'), ('ubuntu', 'Windows')):
            key = prefix + '_workbuddy_ai'
            envkey = 'RELAY_' + key.upper() + '_HOME'
            with self.subTest(prefix=prefix), patch('platform.system', return_value=system), patch.dict(os.environ, {
                    'RELAY_' + prefix.upper() + '_USER_HOME': str(remote_profile), envkey: ''}):
                registry._CACHE.pop(key, None)
                with self.assertRaises(ValueError):
                    registry.get(key)
                with patch.object(device, 'config_path', return_value=self.root / (prefix + '.json')):
                    device.set_home(key, str(first))
                    bootstrap.apply_config(device.read())
                    self.assertEqual(Path(registry.get(key).adapter.root), first)
                    device.set_home(key, str(second))
                    bootstrap.apply_config(device.read())
                remote = registry.get(key)
                self.assertEqual(Path(remote.adapter.root), second)
                self.assertIn('remote-second', [row.id for row in remote.discover()])
                self.assertNotIn('remote-first', [row.id for row in remote.discover()])
                mode = 'import-windows' if prefix == 'windows' else 'import-ubuntu'
                # Synthetic Windows target paths are validated independently of
                # the host's real filesystem in this OS-selection test.
                with patch.object(native_import, '_windows_cwd', return_value=str(self.project)):
                    src, dst, cwd, target_name, target_os = native_import.context(mode, key, str(self.project))
                    result = native_import._migrate(src, dst, 'remote-second', cwd, prefix + '-copy',
                                                   'none', mode, target_name, target_os)
                self.assertEqual(content(self.source.read(result['to']['id'])), content(sample()))
                if prefix == 'windows':
                    result = native_import.export_windows('workbuddy_ai', result['to']['id'], 'D:/project',
                                                          project_path=str(self.project), session_id='back-copy')
                    self.assertIn(second, Path(result['to']['path']).parents)
                    self.assertEqual(content(remote.adapter.read('back-copy')), content(sample()))
                self.assertEqual([row.id for row in WorkBuddyAIAdapter(home=str(first)).discover()], ['remote-first'])

    def test_cross_account_override_cannot_escape_selected_profile(self):
        from relay.windows import WindowsSource
        root = self.root / 'profile' / '.workbuddy-ai'
        account = root / 'user-valid-personal'
        account.mkdir(parents=True)
        for invalid in (self.account, root, account / 'missing'):
            with self.subTest(path=invalid), patch.dict(os.environ, {'RELAY_WINDOWS_WORKBUDDY_AI_HOME': str(invalid)}):
                with self.assertRaises(ValueError) as error:
                    WindowsSource('workbuddy_ai', WorkBuddyAIAdapter, root.parent)
                self.assertEqual(error.exception.args[0].code, 'err.workbuddy_ai_cross_account_directory')
        with patch.dict(os.environ, {'RELAY_WINDOWS_WORKBUDDY_AI_HOME': str(account)}), \
                patch.object(archive, 'is_link', return_value=True), self.assertRaises(ValueError):
            WindowsSource('workbuddy_ai', WorkBuddyAIAdapter, root.parent)

    def test_project_directory_matches_584_client_path_fixtures(self):
        # Expected outputs acquired by replaying only the shipped pure path
        # helpers in Node; the client itself and its network are never started.
        cases = [
            ('C:/Users/Alice/WorkBuddy AI/中文 项目', 'C-Users-Alice-WorkBuddy AI-中文 项目'),
            ('/home/alice/WorkBuddy AI/中文 项目', 'home-alice-WorkBuddy AI-中文 项目'),
            ('C:/' + 'very-long-name-' * 25,
             'C-' + ('very-long-name-' * 25)[:178] + '-1or438e'),
            ('/home/' + '中文😀-' * 80, 'home-' + '中文😀-' * 15 + '中文😀' + '-15s3koa'),
        ]
        for cwd, expected in cases:
            with self.subTest(cwd=cwd):
                self.assertEqual(self.source.project_dir_for(cwd), expected)
                self.assertLessEqual(len(expected.encode('utf-8')), 255)


if __name__ == '__main__':
    unittest.main()
