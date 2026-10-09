import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'app'))

import release_notes  # noqa: E402
from relay import __version__  # noqa: E402

CHANGELOG = """# Changelog

## [Unreleased]

### Fixed
- later

## [1.2.3] - 2026-01-01

### Added
- feature A

## [1.2.2] - 2025-12-01

- older
"""


class ReleaseNotesTests(unittest.TestCase):
    def test_section_is_extracted_without_neighbours(self):
        body = release_notes.changelog_section('1.2.3', CHANGELOG)
        self.assertIn('feature A', body)
        self.assertNotIn('later', body)
        self.assertNotIn('older', body)

    def test_missing_or_empty_section_is_rejected(self):
        self.assertEqual(release_notes.changelog_section('9.9.9', CHANGELOG), '')
        with patch.object(release_notes, 'package_version', return_value='9.9.9'):
            with self.assertRaises(ValueError):
                release_notes.render('v9.9.9', 'o/r', changelog=CHANGELOG, template='{changelog}')

    def test_stable_tag_must_be_plain_semver_and_match_package_version(self):
        with patch.object(release_notes, 'package_version', return_value='1.2.3'):
            self.assertEqual(release_notes.meta('v1.2.3', ''), {'mode': 'stable', 'label': 'v1.2.3'})
            for bad in ('v1.2.4', 'v1.2.3-dev.1', 'v1.2', '1.2.3', '../evil', 'dev'):
                with self.assertRaises(ValueError, msg=bad):
                    release_notes.meta(bad, '')

    def test_render_stable_fills_placeholders(self):
        with patch.object(release_notes, 'package_version', return_value='1.2.3'):
            text = release_notes.render('v1.2.3', 'o/r', changelog=CHANGELOG, template='{tag} {ref} {repo}\n{changelog}')
        self.assertTrue(text.startswith('v1.2.3 v1.2.3 o/r\n'))
        self.assertIn('feature A', text)
        self.assertNotIn('later', text)

    def test_rolling_dev_uses_unreleased_notes_and_commit_label(self):
        sha = 'a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0'
        with patch.object(release_notes, 'package_version', return_value='1.3.0-dev'):
            self.assertEqual(release_notes.meta('', sha), {'mode': 'dev', 'label': 'v1.3.0-dev.a1b2c3d'})
            text = release_notes.render('', 'o/r', changelog=CHANGELOG, template='{tag} {sha}\n{changelog}', dev_sha=sha)
            self.assertEqual(text, 'v1.3.0-dev.a1b2c3d %s\n### Fixed\n- later\n' % sha)
            empty = release_notes.render('', 'o/r', changelog='## [Unreleased]\n', template='{changelog}', dev_sha=sha)
            self.assertIn('暂无', empty)
            with self.assertRaises(ValueError):
                release_notes.meta('', 'not-a-sha')

    def test_dev_build_requires_a_dev_version_and_stable_forbids_it(self):
        sha = 'a' * 40
        with patch.object(release_notes, 'package_version', return_value='1.2.3'):
            with self.assertRaises(ValueError):
                release_notes.dev_label(sha)
        with patch.object(release_notes, 'package_version', return_value='1.3.0-dev'):
            with self.assertRaises(ValueError):
                release_notes.meta('v1.3.0-dev', '')

    def test_repository_main_is_in_dev_state_and_templates_render(self):
        # main 上的 __version__ 总是 X.Y.Z-dev；正式发布的 PR 才改成 X.Y.Z 并写入 CHANGELOG。
        self.assertRegex(__version__, r'^\d+\.\d+\.\d+-dev$')
        text = release_notes.render('', 'o/r', dev_sha='b' * 40)
        self.assertIn('滚动开发版', text)
        self.assertIn('v%s.bbbbbbb' % __version__, text)

    def test_cli_reports_version(self):
        out = subprocess.run([sys.executable, str(ROOT / 'app' / 'cli.py'), '--version'],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn(__version__, out)


if __name__ == '__main__':
    unittest.main()
