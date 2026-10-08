import subprocess
import sys
import unittest
from pathlib import Path

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
        with self.assertRaises(ValueError):
            release_notes.render('v' + __version__, 'o/r', changelog='## [Unreleased]\n', template='{changelog}')

    def test_tag_must_match_package_version(self):
        with self.assertRaises(ValueError):
            release_notes.render('v0.0.0-not-this', 'o/r', changelog=CHANGELOG, template='{changelog}')
        with self.assertRaises(ValueError):
            release_notes.render('../evil', 'o/r', changelog=CHANGELOG, template='{changelog}')

    def test_render_fills_placeholders(self):
        changelog = '## [%s] - 2026-01-01\n\n- hello\n' % __version__
        text = release_notes.render('v' + __version__, 'o/r', changelog=changelog,
                                    template='{tag} {repo}\n{changelog}')
        self.assertEqual(text, 'v%s o/r\n- hello\n' % __version__)

    def test_repository_changelog_covers_current_version(self):
        # Fails when __version__ is bumped without writing release notes.
        text = release_notes.render('v' + __version__, 'o/r')
        self.assertIn('o/r', text)

    def test_cli_reports_version(self):
        out = subprocess.run([sys.executable, str(ROOT / 'app' / 'cli.py'), '--version'],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn(__version__, out)


if __name__ == '__main__':
    unittest.main()
