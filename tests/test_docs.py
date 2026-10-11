import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ('guide', 'reference', 'dev', 'research')
LINK = re.compile(r'\]\(([^)#\s]+)(?:#[^)\s]*)?\)')


def markdown_files():
    out = subprocess.run(['git', '-c', 'core.quotepath=false', 'ls-files', '*.md'], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode != 0:      # 不在 git 检出里（例如源码包）：退回到直接扫描
        return sorted(p for p in ROOT.rglob('*.md') if 'build' not in p.parts and '.git' not in p.parts)
    return [ROOT / name for name in out.stdout.split('\n') if name]


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
