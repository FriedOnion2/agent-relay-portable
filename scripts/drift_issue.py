#!/usr/bin/env python3
"""Open (or update) a single tracking issue when a scheduled compatibility run fails.

Used by the scheduled workflows so that a client changing its on-disk format is noticed without
anyone having to watch the Actions tab. Needs the `gh` CLI with GH_TOKEN, and `issues: write`.
One open issue per workflow (found by label + title); repeat failures add a comment instead of new issues.
"""
import argparse
import json
import subprocess
import sys

LABEL = 'format-drift'


def gh(*args, check=True):
    return subprocess.run(['gh', *args], capture_output=True, text=True, check=check).stdout


def body(workflow, run_url, details):
    text = ['计划任务 **%s** 失败：%s' % (workflow, run_url), '']
    if details.strip():
        text += ['<details><summary>结果</summary>', '', details.strip(), '', '</details>', '']
    text += ['可能是某个客户端更新后改了本地存储格式，或 CI 环境变化。先看运行日志；确认是格式变化后更新对应适配器与 fixture。',
             '此 issue 由 `scripts/drift_issue.py` 自动维护：问题持续时在这里追加评论，修好后手动关闭即可。']
    return '\n'.join(text)


def find_open(title):
    rows = json.loads(gh('issue', 'list', '--label', LABEL, '--state', 'open', '--search', title + ' in:title',
                         '--json', 'number,title', '--limit', '20') or '[]')
    return next((row['number'] for row in rows if row['title'] == title), None)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--workflow', required=True)
    parser.add_argument('--run-url', required=True)
    parser.add_argument('--details-file')
    args = parser.parse_args(argv)
    details = ''
    if args.details_file:
        with open(args.details_file, encoding='utf-8') as handle:
            details = handle.read()
    title = '兼容性计划任务失败：' + args.workflow
    text = body(args.workflow, args.run_url, details)
    gh('label', 'create', LABEL, '--description', '客户端存储格式可能已变化', '--color', 'd93f0b', check=False)
    number = find_open(title)
    if number:
        gh('issue', 'comment', str(number), '--body', text)
        print('已在 issue #%s 追加评论' % number)
    else:
        print(gh('issue', 'create', '--title', title, '--label', LABEL, '--body', text).strip())
    return 0


if __name__ == '__main__':
    sys.exit(main())
