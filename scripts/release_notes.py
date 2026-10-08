#!/usr/bin/env python3
"""Render the GitHub Release notes for a tag from CHANGELOG.md and the notes template.

Fails (non-zero exit) when the tag does not match ``relay.__version__`` or when
CHANGELOG.md has no non-empty section for that version, so a release cannot be
published without written notes.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package_version():
    text = (ROOT / 'app' / 'relay' / '__init__.py').read_text(encoding='utf-8')
    return re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M).group(1)


def changelog_section(version, text):
    pattern = re.compile(r'^## \[%s\][^\n]*\n(.*?)(?=^## \[|\Z)' % re.escape(version), re.M | re.S)
    match = pattern.search(text)
    body = match.group(1).strip() if match else ''
    return re.sub(r'^###', '###', body)


def render(tag, repo, changelog=None, template=None):
    if not re.fullmatch(r'v[0-9A-Za-z.\-]+', tag):
        raise ValueError('Invalid version tag: %s' % tag)
    version = tag[1:]
    if version != package_version():
        raise ValueError('Tag %s does not match app/relay/__init__.py __version__ %s' % (tag, package_version()))
    changelog = changelog if changelog is not None else (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    body = changelog_section(version, changelog)
    if not body:
        raise ValueError('CHANGELOG.md has no entry for [%s]' % version)
    template = template if template is not None else (ROOT / '.github' / 'release-notes-template.md').read_text(encoding='utf-8')
    return template.replace('{tag}', tag).replace('{repo}', repo).replace('{changelog}', body) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--repo', default='FriedOnion2/agent-relay-portable')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        notes = render(args.tag, args.repo)
    except ValueError as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 1
    args.output.write_text(notes, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
