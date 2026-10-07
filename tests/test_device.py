import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

import bootstrap
from relay import device, registry


class DeviceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.patch=patch.object(device,'project_root',return_value=self.root)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.addCleanup(device.blocked_homes.clear)
        self.addCleanup(device.warnings.clear)

    def test_overrides_belong_to_device_and_shared_config_stays_unchanged(self):
        path=self.root/'codex';path.mkdir()
        shared={'agent_homes':{'codex':str(self.root/'old-device')},'port':8745}
        with patch.object(device,'identity',return_value='device-a'):
            device.set_home('codex',str(path))
            self.assertEqual(device.merge(shared)['agent_homes']['codex'],str(path.resolve()))
            self.assertFalse(device.blocked_homes)
        with patch.object(device,'identity',return_value='device-b'):
            self.assertIn('codex',device.blocked_homes if device.merge(shared) else {})
            self.assertNotIn('plugins',device.read())
        self.assertEqual(shared['agent_homes']['codex'],str(self.root/'old-device'))

    def test_relative_portable_path_and_explicit_auto_after_move(self):
        (self.root/'data').mkdir()
        result=device.merge({'agent_homes':{'claude':'data'}})
        self.assertEqual(result['agent_homes']['claude'],str(self.root/'data'))
        with patch.dict(os.environ,{},clear=False):
            bootstrap.apply_config(result)
            self.assertEqual(os.environ['RELAY_CLAUDE_HOME'],str(self.root/'data'))
            device.set_home('claude','')
            bootstrap.apply_config(device.merge({'agent_homes':{'claude':'data'}}))
            self.assertNotIn('RELAY_CLAUDE_HOME',os.environ)

    def test_blocked_old_path_is_not_silently_replaced_by_default(self):
        device.merge({'agent_homes':{'codex':str(self.root/'gone')}})
        with self.assertRaisesRegex(ValueError,'重新选择'):
            registry.get('codex')
        self.assertTrue(device.environment()['warnings'])

    def test_invalid_device_config_never_overwrites_and_environment_probe_leaves_no_file(self):
        path=device.config_path();path.parent.mkdir()
        path.write_text('{"agent_homes":{"codex":42}}',encoding='utf-8')
        before=path.read_bytes()
        with self.assertRaises(ValueError): device.set_home('codex','')
        self.assertEqual(path.read_bytes(),before)
        self.assertTrue(device.environment()['writable'])
        self.assertEqual(list(self.root.glob('.relay-probe-*')),[])

    def test_bad_local_config_preserves_valid_shared_config_and_reports_the_right_file(self):
        local=device.config_path();local.parent.mkdir()
        local.write_text('{"agent_homes":{"codex":42}}',encoding='utf-8')
        shared=self.root/'config.json'
        (self.root/'claude').mkdir()
        shared.write_text(json.dumps({'port':9123,'agent_homes':{'claude':str(self.root/'claude')}}),encoding='utf-8')
        with patch.object(bootstrap,'config_path',return_value=shared):
            cfg=bootstrap.load_config()
        self.assertEqual(cfg['port'],9123)
        self.assertEqual(cfg['agent_homes']['claude'],str(self.root/'claude'))
        self.assertTrue(any('本机配置读取失败' in warning for warning in device.warnings))
        self.assertFalse(any('共享配置读取失败' in warning for warning in device.warnings))
