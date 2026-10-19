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
from relay import archive, health, locations, preview, registry, session_store
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

    def test_transfer_to_and_from_domestic_and_other_writers_preserves_content(self):
        path = self.seed()
        before = path.read_bytes()
        for target in registry.writable_keys():
            if target == 'workbuddy_ai':
                continue
            with self.subTest(target=target):
                dst = registry.get(target, home=str(self.root / target))
                registry._CACHE[target] = dst
                result = registry.transfer('workbuddy_ai', 'fixture', target, cwd=str(self.project),
                                           session_id='11111111-1111-4111-8111-111111111111')
                restored = dst.read(next(row.id for row in dst.discover()
                                         if Path(row.path).resolve() == Path(result['to']['path']).resolve()))
                self.assertEqual(content(restored), content(self.source.read('fixture')))
        result = registry.transfer('workbuddy', '11111111-1111-4111-8111-111111111111', 'workbuddy_ai',
                                   cwd=str(self.project), session_id='return-copy')
        self.assertTrue(result['ok'])
        self.assertEqual(content(self.source.read('return-copy')), content(sample()))
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
