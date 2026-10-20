"""Exercise generated launchers with local fixture archives, never downloads."""
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.assemble_release import PLATFORMS, assemble


class UniversalLauncherTests(unittest.TestCase):
    def test_same_version_rebuild_does_not_reuse_old_runtime(self):
        with tempfile.TemporaryDirectory(prefix='relay launcher 中文 ') as temporary:
            root = Path(temporary)
            assets = root / 'assets'
            assets.mkdir()
            cache = root / 'cache'
            tag = 'v1.1.0-dev.fixture'
            for marker in ('first-build', 'rebuilt-same-version'):
                for target in PLATFORMS:
                    folder = 'AgentRelay-' + tag + '-' + target
                    if target.startswith('linux'):
                        with tarfile.open(assets / (folder + '.tar.gz'), 'w:gz') as archive:
                            raw = ('#!/bin/sh\nprintf "%s\\n"\n' % marker).encode()
                            entry = tarfile.TarInfo(folder + '/AgentRelay')
                            entry.size, entry.mode = len(raw), 0o755
                            archive.addfile(entry, io.BytesIO(raw))
                    else:
                        with zipfile.ZipFile(assets / (folder + '.zip'), 'w') as archive:
                            if target.startswith('windows'):
                                # A preinstalled native executable exits immediately
                                # on the launcher's `serve` argument. Its exit code
                                # is immaterial; inspect the selected runtime below.
                                executable = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/whoami.exe'
                                archive.writestr(folder + '/AgentRelay.exe', executable.read_bytes() if sys.platform == 'win32' else b'fixture')
                            else:
                                entry = zipfile.ZipInfo(folder + '/AgentRelay.app/Contents/MacOS/AgentRelay')
                                entry.external_attr = 0o100755 << 16
                                archive.writestr(entry, '#!/bin/sh\nprintf "%s\\n"\n' % marker)
                            archive.writestr(folder + '/payload-marker.txt', marker)
                assemble(tag, assets, root / 'output')
                portable = root / 'output' / ('AgentRelay-' + tag + '-universal')
                env = dict(os.environ)
                if sys.platform == 'win32':
                    env['LOCALAPPDATA'] = str(cache)
                    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
                    command = [str(powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                               str(portable / 'Start-AgentRelay.ps1')]
                elif sys.platform == 'darwin':
                    env['HOME'] = str(cache)
                    command = ['/bin/bash', str(portable / '启动_AgentRelay.command')]
                else:
                    env['XDG_CACHE_HOME'] = str(cache)
                    command = ['/bin/bash', str(portable / '启动_AgentRelay.sh')]
                result = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=30)
                if sys.platform == 'win32':
                    self.assertEqual(result.returncode, 1, result.stderr.decode(errors='replace'))
                    markers = [path.read_text() for path in cache.rglob('payload-marker.txt')]
                    self.assertIn(marker, markers)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                    self.assertEqual(result.stdout.decode().strip(), marker)
                # Move only the media directory: cached binaries must remain
                # usable and the generated launcher must locate its new root.
                moved = root / ('moved ' + marker)
                shutil.move(str(portable), moved)
                command[-1] = str(moved / Path(command[-1]).name)
                moved_result = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=30)
                self.assertEqual(moved_result.returncode, result.returncode)
                if sys.platform != 'win32':
                    self.assertEqual(moved_result.stdout, result.stdout)
