#!/usr/bin/env python3
"""Render the GitHub Release notes for a tag from CHANGELOG.md and the notes template.

Two kinds of builds (see docs/maintainers.md):

* stable ``vX.Y.Z`` tag: must equal ``relay.__version__`` and CHANGELOG.md needs a non-empty section for it;
* rolling ``dev`` build of a ``main`` commit (``--sha``): ``__version__`` must end with ``-dev``; notes come from [Unreleased].

Fails (non-zero exit) otherwise, so nothing is published without written notes.
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


STABLE_TAG = re.compile(r'v\d+\.\d+\.\d+')
DEV_SUFFIX = '-dev'


def dev_label(sha, version=None):
    """滚动开发版的构建标签，例如 v0.5.0-dev.1a2b3c4；GitHub 上对应的 tag 始终是固定的 ``dev``。"""
    if not re.fullmatch(r'[0-9a-f]{7,40}', sha):
        raise ValueError('Invalid commit sha: %s' % sha)
    version = version or package_version()
    if not version.endswith(DEV_SUFFIX):
        raise ValueError('Rolling dev builds need __version__ ending with "%s" (found %s)' % (DEV_SUFFIX, version))
    return 'v%s.%s' % (version, sha[:7])


def check_stable(tag):
    if not STABLE_TAG.fullmatch(tag):
        raise ValueError('Release tags must look like v1.2.3 (got %s); prereleases use the rolling "dev" build' % tag)
    if tag[1:] != package_version():
        raise ValueError('Tag %s does not match app/relay/__init__.py __version__ %s' % (tag, package_version()))


def render(tag, repo, changelog=None, template=None, dev_sha=None):
    """tag 为正式版标签；传 dev_sha 时改为渲染滚动开发版说明（tag 参数被忽略）。"""
    changelog = changelog if changelog is not None else (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    if dev_sha:
        label = dev_label(dev_sha)
        body = changelog_section('Unreleased', changelog) or '（暂无未发布条目）'
        template = template if template is not None else (ROOT / '.github' / 'release-notes-dev-template.md').read_text(encoding='utf-8')
        ref = dev_sha
    else:
        check_stable(tag)
        label, ref = tag, tag
        body = changelog_section(tag[1:], changelog)
        if not body:
            raise ValueError('CHANGELOG.md has no entry for [%s]' % tag[1:])
        template = template if template is not None else (ROOT / '.github' / 'release-notes-template.md').read_text(encoding='utf-8')
    return (template.replace('{tag}', label).replace('{ref}', ref).replace('{sha}', dev_sha or '')
            .replace('{repo}', repo).replace('{changelog}', body) + '\n')


def meta(tag, dev_sha):
    """给工作流用：mode / label（文件名里的版本标签）。"""
    if dev_sha:
        return {'mode': 'dev', 'label': dev_label(dev_sha)}
    check_stable(tag)
    return {'mode': 'stable', 'label': tag}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default='', help='正式版标签，如 v0.5.0')
    parser.add_argument('--sha', default='', help='滚动开发版对应的提交（与 --tag 二选一）')
    parser.add_argument('--repo', default='FriedOnion2/agent-relay-portable')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--meta', action='store_true', help='只输出 mode= / label= 两行（写入 GITHUB_OUTPUT）')
    args = parser.parse_args(argv)
    if bool(args.tag) == bool(args.sha):
        parser.error('exactly one of --tag / --sha is required')
    try:
        if args.meta:
            for key, value in meta(args.tag, args.sha).items():
                print('%s=%s' % (key, value))
            return 0
        if not args.output:
            parser.error('--output is required')
        notes = render(args.tag, args.repo, dev_sha=args.sha or None)
    except ValueError as exc:
        print('error: %s' % exc, file=sys.stderr)
        return 1
    args.output.write_text(notes, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
