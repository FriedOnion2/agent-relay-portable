import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import build_release


@unittest.skipUnless(sys.platform == 'darwin', 'requires macOS codesign and extended attributes')
class MacBundleSigningTests(unittest.TestCase):
    def test_generated_bundle_with_finder_metadata_is_cleaned_and_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / 'Fixture.app'
            executable = app / 'Contents/MacOS/Fixture'
            executable.parent.mkdir(parents=True)
            shutil.copyfile('/usr/bin/true', executable)
            executable.chmod(0o755)
            (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
                'CFBundleExecutable': 'Fixture', 'CFBundleIdentifier': 'test.agentrelay.fixture',
                'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1',
            }))
            resource = app / 'Contents/Resources/data.txt'
            resource.parent.mkdir()
            resource.write_text('fixture', encoding='utf-8')
            subprocess.run(['xattr', '-wx', 'com.apple.FinderInfo', '00' * 32, str(resource)], check=True)
            subprocess.run(['xattr', '-w', 'com.apple.ResourceFork', 'fixture metadata', str(resource)], check=True)
            rejected = subprocess.run(['codesign', '--force', '--sign', '-', str(app)], capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn(b'resource fork', rejected.stderr)
            build_release.sign_macos_app(app)
            subprocess.run(['codesign', '--verify', '--strict', str(app)], check=True, capture_output=True)
            attributes = subprocess.check_output(['xattr', str(resource)], text=True)
            self.assertNotIn('com.apple.FinderInfo', attributes)
            self.assertNotIn('com.apple.ResourceFork', attributes)
            self.assertEqual(resource.read_text(encoding='utf-8'), 'fixture')


if __name__ == '__main__':
    unittest.main()
