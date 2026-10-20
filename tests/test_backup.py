"""Synthetic multi-agent backups; no reads or writes to real client stores."""
import copy
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from relay import archive, backup, registry, session_store
from relay.adapters.workbuddy import WorkBuddyAdapter
from relay.adapters.workbuddy_ai import WorkBuddyAIAdapter
from relay.adapters.dsh import DshAdapter
from relay.adapters.dsh_write import history_events
from test_relay import sample


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay backup 中文 ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / 'old project'
        self.project.mkdir()
        self.local = self.root / 'new project'
        self.local.mkdir()
        self.agents = ['workbuddy', 'workbuddy_ai']
        self.sources = {key: cls(home=str(self.root / 'source' / key)) for key, cls in
                        [('workbuddy', WorkBuddyAdapter), ('workbuddy_ai', WorkBuddyAIAdapter)]}
        for source in self.sources.values():
            source.write(sample(), cwd=str(self.project), session_id='same-id')
        self.turns = {key: len(source.read('same-id').turns) for key, source in self.sources.items()}
        self.skill = Path(self.sources['workbuddy'].root) / 'skills' / 'fixture-skill'
        self.skill.mkdir(parents=True)
        (self.skill / 'SKILL.md').write_text('---\nname: fixture-skill\n---\nSynthetic only\n', encoding='utf-8')
        (self.skill / 'script.sh').write_bytes(b'#!/bin/sh\nexit 99\n')
        (self.skill / '.env').write_text('excluded fixture', encoding='utf-8')
        for context in [patch.dict(registry._CACHE, self.sources, clear=True),
                        patch.dict(os.environ, {'RELAY_STORAGE_HOME': str(self.root / 'storage')}),
                        patch('relay.oplog.log_path', return_value=self.root / 'operations.jsonl')]:
            context.start()
            self.addCleanup(context.stop)
        self.original = self.sources['workbuddy'].read('same-id').cwd
        self.options = {'projects': {source.read('same-id').cwd: str(self.local) for source in self.sources.values()}}

    def targets(self):
        targets = {key: type(source)(home=str(self.root / 'target' / key)) for key, source in self.sources.items()}
        registry._CACHE.update(targets)
        return targets

    def export(self, mode='all'):
        result = backup.export(mode, self.agents)
        self.assertTrue(result['ok'], result)
        return result['path']

    def rewrite(self, path, mutation):
        manifest, files = archive.read_package(path)
        mutation(manifest, files)
        destination = self.root / ('modified-' + str(len(list(self.root.glob('modified-*')))) + '.zip')
        archive.write_package(destination, manifest, files)
        return destination

    def dsh_package(self, headers):
        source = DshAdapter(home=str(self.root / 'source-dsh'))
        for sid, extra in headers:
            events = history_events(sample(), True, False, 1700000000000)
            header = dict(type='session', version=0, id=sid, createdAt=1700000000000,
                          cwd=str(self.project), delegationDepth=0, seedLength=len(events) - 1)
            header.update(extra)
            path = Path(source.home) / 'fixture-project' / sid / 'session.jsonl'
            path.parent.mkdir(parents=True)
            path.write_text(''.join(json.dumps(row) + '\n' for row in [header] + events), encoding='utf-8')
        registry._CACHE['dsh'] = source
        result = backup.export('sessions', ['dsh'])
        self.assertTrue(result['ok'], result)
        # Always put child before parent, regardless of adapter ordering.
        package = self.rewrite(result['path'], lambda m, f: m['items'].sort(
            key=lambda item: item['manifest']['session']['id'].endswith('/parent')))
        target = DshAdapter(home=str(self.root / 'target-dsh'))
        registry._CACHE['dsh'] = target
        return package, target, {'projects': {str(self.project): str(self.local)}}

    def test_dsh_parent_is_restored_first_and_retries_skip_native_ids_after_project_mapping(self):
        package, target, options = self.dsh_package([('child', {'parentSession': 'parent'}), ('parent', {})])
        report = backup.plan(package, options)
        self.assertEqual((report['ready'], report['blocked']), (2, 0), report)
        self.assertEqual([row['native_id'] for row in report['rows']], ['parent', 'child'])
        result = backup.restore(package, options, report['token'])
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(list(target.discover())), 2)
        self.assertEqual(backup.plan(package, options)['skip'], 2)

    def test_dsh_missing_parent_cycle_subagent_and_copy_dependency_block_before_writes(self):
        for headers, conflict in [([('child', {'parentSession': 'missing'})], 'skip'),
                                  ([('child', {'parentSession': 'parent'}), ('parent', {'parentSession': 'child'})], 'skip'),
                                  ([('child', {'origin': 'subagent'})], 'skip'),
                                  ([('child', {'parentSession': 'parent'}), ('parent', {})], 'copy')]:
            with self.subTest(headers=headers, conflict=conflict):
                # Each case uses a fresh source and target.
                with tempfile.TemporaryDirectory(dir=self.root) as root:
                    previous = self.root
                    self.root = Path(root)
                    try:
                        package, target, options = self.dsh_package(headers)
                        options['conflict'] = conflict
                        report = backup.plan(package, options)
                        self.assertGreater(report['blocked'], 0, report)
                        with self.assertRaises(ValueError):
                            backup.restore(package, options, report['token'])
                        self.assertFalse(Path(target.home).exists())
                    finally:
                        self.root = previous

    def test_full_backup_moves_both_editions_and_skill_without_executing_or_copying_credentials(self):
        package = self.export()
        summary = backup.inspect(package)
        self.assertEqual(summary['count'], 3)
        self.assertEqual(summary['skill_agents'], ['workbuddy'])
        manifest, files = archive.read_package(package)
        self.assertFalse(any(name.endswith('.env') for name in files))
        self.assertEqual({item['manifest']['agent'] for item in manifest['items']}, set(self.agents))
        targets = self.targets()
        plan = backup.plan(package, self.options)
        self.assertEqual((plan['ready'], plan['blocked']), (3, 0))
        result = backup.restore(package, self.options, plan['token'])
        self.assertTrue(result['ok'], result)
        for key, target in targets.items():
            self.assertEqual(Path(target.read('same-id').cwd).resolve(), self.local)
            self.assertEqual(len(target.read('same-id').turns), self.turns[key])
        restored = Path(targets['workbuddy'].root) / 'skills' / 'fixture-skill'
        self.assertEqual((restored / 'script.sh').read_bytes(), b'#!/bin/sh\nexit 99\n')
        self.assertFalse((restored / '.env').exists())
        self.assertEqual(len(result['restored']), 3)

    def test_sessions_and_reading_modes_are_distinct_and_reading_cannot_be_imported(self):
        package = self.export('sessions')
        self.assertEqual(backup.inspect(package)['count'], 2)
        self.assertFalse(backup.inspect(package)['skill_agents'])
        reading = self.export('markdown')
        manifest, files = archive.read_package(reading)
        self.assertEqual(manifest['kind'], backup.READING_KIND)
        self.assertEqual(len(files), 2)
        self.assertTrue(all(name.endswith('.md') for name in files))
        self.assertTrue(all('你好' in data.decode('utf-8') for data, executable in files.values()))
        with self.assertRaises(ValueError):
            backup.inspect(reading)

    def test_conflicts_skip_and_copy_are_repeatable_without_overwrite(self):
        package = self.export()
        # Existing source records and Skill are protected, even on the same device.
        before = {key: Path(source.read('same-id').path).read_bytes() for key, source in self.sources.items()}
        report = backup.plan(package, self.options)
        self.assertEqual(report['skip'], 3)
        self.assertFalse(backup.restore(package, self.options, report['token'])['restored'])
        options = dict(self.options, conflict='copy')
        report = backup.plan(package, options)
        self.assertEqual(report['ready'], 3)
        self.assertTrue(backup.restore(package, options, report['token'])['ok'])
        self.assertEqual(backup.plan(package, options)['skip'], 3)
        for key, source in self.sources.items():
            self.assertEqual(Path(source.read('same-id').path).read_bytes(), before[key])

    def test_preview_is_readonly_and_missing_mapping_or_stale_token_prevents_all_writes(self):
        package = self.export()
        targets = self.targets()
        bad = {'projects': {self.original: str(self.root / 'missing')}}
        report = backup.plan(package, bad)
        self.assertEqual(report['blocked'], 2)
        with self.assertRaises(ValueError):
            backup.restore(package, bad, report['token'])
        for target in targets.values():
            self.assertFalse(Path(target.root).exists())
        report = backup.plan(package, self.options)
        changed = {'projects': {self.original: str(self.project)}}
        with self.assertRaises(ValueError):
            backup.restore(package, changed, report['token'])
        with self.assertRaises(ValueError):
            backup.restore(package, self.options)
        # Changing the configured native home also invalidates confirmation.
        registry._CACHE['workbuddy'] = WorkBuddyAdapter(home=str(self.root / 'other-target'))
        with self.assertRaises(ValueError):
            backup.restore(package, self.options, report['token'])
        self.assertFalse((self.root / 'other-target').exists())

    def test_partial_restore_reports_errors_and_retries_skip_completed_items(self):
        package = self.export()
        self.targets()
        plan = backup.plan(package, self.options)
        original = session_store.restore_session
        calls = []
        def restore(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise OSError('isolated fixture failure')
            return original(*args, **kwargs)
        with patch.object(session_store, 'restore_session', side_effect=restore):
            result = backup.restore(package, self.options, plan['token'])
        self.assertFalse(result['ok'])
        self.assertEqual((len(result['restored']), len(result['errors'])), (2, 1))
        report = backup.plan(package, self.options)
        self.assertEqual((report['ready'], report['skip']), (1, 2))
        self.assertTrue(backup.restore(package, self.options, report['token'])['ok'])

    def test_export_errors_are_embedded_and_cancellation_publishes_nothing(self):
        with patch.object(self.sources['workbuddy'], 'read', side_effect=ValueError('fixture unreadable')):
            result = backup.export('sessions', self.agents)
        self.assertFalse(result['ok'])
        self.assertEqual(result['processed'], 1)
        self.assertTrue(backup.inspect(result['path'])['errors'])
        count = len(list((self.root / 'storage' / 'backups').glob('*.zip')))
        cancel = threading.Event()
        canceled = backup.export('all', self.agents, progress=lambda row: cancel.set(), cancel=cancel)
        self.assertTrue(canceled['canceled'])
        self.assertNotIn('path', canceled)
        self.assertEqual(len(list((self.root / 'storage' / 'backups').glob('*.zip'))), count)

    def test_limits_fail_before_publishing_a_truncated_backup(self):
        first_size = len(Path(self.sources['workbuddy'].read('same-id').path).read_bytes())
        with patch.object(archive, 'MAX_TOTAL', first_size + 5):
            with self.assertRaises(ValueError):
                backup.export('all', self.agents)
        self.assertFalse((self.root / 'storage' / 'backups').exists())

    def test_duplicate_shared_store_paths_are_exported_once(self):
        registry._CACHE['claude_sdk'] = self.sources['workbuddy']
        result = backup.export('sessions', ['workbuddy', 'claude_sdk'])
        self.assertEqual(result['processed'], 1)

    def test_untrusted_inner_manifests_and_undeclared_payloads_are_rejected(self):
        package = self.export()
        mutations = [
            lambda m, f: m['items'].append(copy.deepcopy(m['items'][0])),
            lambda m, f: m['items'][0]['manifest'].update(agent=[]),
            lambda m, f: m['items'][0]['manifest']['session'].update(cwd=[]),
            lambda m, f: m['items'][0]['manifest']['files'][0].update(path='../escape'),
            lambda m, f: m['items'][0]['manifest']['files'][0].update(sha256='0' * 64),
            lambda m, f: f.update({'orphan': (b'undeclared item', False)}),
        ]
        for mutation in mutations:
            altered = self.rewrite(package, mutation)
            with self.subTest(path=altered), self.assertRaises(ValueError):
                backup.inspect(altered)

    def test_upload_is_bounded_verified_and_truncated_uploads_are_removed(self):
        package = self.export()
        raw = Path(package).read_bytes()
        uploaded = backup.receive(io.BytesIO(raw), len(raw))
        self.assertEqual(uploaded['count'], 3)
        self.assertEqual(backup.download_path(uploaded['id']).read_bytes(), raw)
        before = set((self.root / 'storage' / 'backups').iterdir())
        for content, length in [(raw[:10], len(raw)), (b'not a zip', 9), (b'', backup.MAX_UPLOAD + 1)]:
            with self.assertRaises(ValueError):
                backup.receive(io.BytesIO(content), length)
        self.assertEqual(set((self.root / 'storage' / 'backups').iterdir()), before)
        with self.assertRaises(ValueError):
            backup.download_path('../../config')

    def test_invalid_options_and_empty_sources_cannot_be_reported_as_success(self):
        for agents in ([], ['plugin-fixture'], 'workbuddy', [None]):
            with self.assertRaises(ValueError):
                backup.export(agents=agents)
        empty = WorkBuddyAdapter(home=str(self.root / 'empty'))
        with patch.dict(registry._CACHE, {'workbuddy': empty}, clear=True):
            result = backup.export(agents=['workbuddy'])
            self.assertTrue(result['empty'])
            self.assertFalse(result['ok'])
        package = self.export()
        for options in ({'projects': []}, {'conflict': 'overwrite'}, {'unknown': True}):
            with self.assertRaises(ValueError):
                backup.plan(package, options)
