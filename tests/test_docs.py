import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ('guide', 'reference', 'dev', 'research')
LINK = re.compile(r'\]\(([^)#\s]+)(?:#[^)\s]*)?\)')


SKIP_DIRS = {'.git', 'build', 'dist', 'node_modules', '.venv', 'venv'}


def markdown_files():
    return sorted(p for p in ROOT.rglob('*.md')
                  if not SKIP_DIRS.intersection(p.relative_to(ROOT).parts) and not any(x.endswith('.egg-info') for x in p.parts))


class DocsLayoutTests(unittest.TestCase):
    def test_relative_markdown_links_resolve(self):
        broken = []
        for path in markdown_files():
            for target in LINK.findall(path.read_text(encoding='utf-8')):
                if re.match(r'[a-z][a-z0-9+.\-]*:', target) or target.startswith('/'):
                    continue
                if not (path.parent / target).resolve().exists():
                    broken.append('%s -> %s' % (path.relative_to(ROOT), target))
        self.assertEqual(broken, [])

    def test_docs_are_grouped_and_every_page_is_in_the_index(self):
        docs = ROOT / 'docs'
        loose = sorted(p.name for p in docs.glob('*.md') if p.name != 'README.md')
        self.assertEqual(loose, [], 'docs/ 下的页面要放进 guide/ reference/ dev/ research/ 之一')
        index = (docs / 'README.md').read_text(encoding='utf-8')
        missing = []
        for section in SECTIONS:
            for page in sorted((docs / section).glob('*.md')):
                if '%s/%s' % (section, page.name) not in index:
                    missing.append('%s/%s' % (section, page.name))
        self.assertEqual(missing, [], '这些页面没有列进 docs/README.md')
        self.assertIn('reference/formats/', index)

    def test_research_pages_are_marked_as_dated_records(self):
        for page in (ROOT / 'docs' / 'research').glob('*.md'):
            self.assertIn('不是现行规范', page.read_text(encoding='utf-8'), page.name)


if __name__ == '__main__':
    unittest.main()


class SiteConfigTests(unittest.TestCase):
    def test_every_page_outside_research_is_in_the_site_nav(self):
        config = (ROOT / 'mkdocs.yml').read_text(encoding='utf-8')
        missing = []
        for section in ('guide', 'reference', 'dev'):
            for page in sorted((ROOT / 'docs' / section).glob('*.md')):
                if '%s/%s' % (section, page.name) not in config:
                    missing.append('%s/%s' % (section, page.name))
        self.assertEqual(missing, [])


class CliReferenceTests(unittest.TestCase):
    def test_every_cli_command_is_documented(self):
        import argparse
        import sys
        sys.path.insert(0, str(ROOT / 'app'))
        import cli
        parser = cli.build_parser()
        names = [name for action in parser._actions if isinstance(action, argparse._SubParsersAction) for name in action.choices]
        page = (ROOT / 'docs' / 'reference' / 'cli.md').read_text(encoding='utf-8')
        self.assertEqual([name for name in names if '`%s' % name not in page], [])


class EnglishDocsTests(unittest.TestCase):
    def test_english_pages_are_in_nav_and_point_to_the_chinese_original(self):
        config = (ROOT / 'mkdocs.yml').read_text(encoding='utf-8')
        pages = sorted((ROOT / 'docs' / 'en').glob('*.md'))
        self.assertTrue(pages)
        for page in pages:
            self.assertIn('en/%s' % page.name, config, page.name)
            self.assertIn('Chinese', page.read_text(encoding='utf-8'), page.name)

    def test_english_cli_reference_covers_every_command(self):
        import argparse
        import sys
        sys.path.insert(0, str(ROOT / 'app'))
        import cli
        parser = cli.build_parser()
        names = [name for action in parser._actions if isinstance(action, argparse._SubParsersAction) for name in action.choices]
        page = (ROOT / 'docs' / 'en' / 'cli.md').read_text(encoding='utf-8')
        self.assertEqual([name for name in names if '`%s' % name not in page], [])
