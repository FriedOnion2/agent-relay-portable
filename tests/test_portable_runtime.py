import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import bootstrap
from relay import archive
from relay.runtime import project_root


class PortableRuntimeTests(unittest.TestCase):
    def test_packaged_runtime_keeps_shared_data_outside_binary_cache(self):
        shared = str(Path.cwd() / 'shared data')
        with patch.object(sys, 'frozen', True, create=True), patch.dict(os.environ, {'RELAY_PORTABLE_ROOT': shared}):
            self.assertEqual(bootstrap.config_path(), Path(shared) / 'config.json')
            with patch.dict(os.environ, {'RELAY_STORAGE_HOME': ''}):
                self.assertEqual(archive.storage_root(), Path(shared) / 'storage')
            with patch.object(bootstrap, '_version_of', side_effect=AssertionError('must not spawn itself')):
                self.assertTrue(bootstrap.find_python()['ok'])

    def test_direct_native_bundle_uses_directory_beside_app(self):
        executable = str(Path.cwd() / 'portable/AgentRelay.app/Contents/MacOS/AgentRelay')
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', executable), patch.dict(os.environ, {'RELAY_PORTABLE_ROOT': ''}):
            self.assertEqual(project_root(), Path.cwd() / 'portable')

    def test_source_default_remains_project_directory(self):
        with patch.object(sys, 'frozen', False, create=True), patch.dict(os.environ, {'RELAY_PORTABLE_ROOT': str(Path.cwd() / 'ignored')}):
            self.assertEqual(project_root(), Path(__file__).resolve().parents[1])
