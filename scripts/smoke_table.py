#!/usr/bin/env python3
"""Merge the per-OS JSON files written by smoke_all.py into one Markdown support table (stdout)."""
import json
import sys
from pathlib import Path

ICON = {'pass': '✅ 通过', 'fail': '❌ 失败', 'skip': '⏭ 跳过'}
ORDER = ['Linux', 'macOS', 'Windows']


def main(folder):
    rows = [row for path in sorted(Path(folder).rglob('*.json')) for row in json.loads(path.read_text(encoding='utf-8'))]
    systems = [o for o in ORDER if any(r['os'] == o for r in rows)]
    clients = list(dict.fromkeys(r['client'] for r in rows))
    cell = {(r['os'], r['client']): r for r in rows}
    out = ['| 软件 | ' + ' | '.join(systems) + ' |', '|---|' + '---|' * len(systems)]
    for client in clients:
        out.append('| %s | %s |' % (client, ' | '.join(ICON[cell[(o, client)]['status']] if (o, client) in cell else '—' for o in systems)))
    out += ['', '跳过 / 失败原因：']
    for r in rows:
        if r['status'] != 'pass':
            out.append('- %s · %s：%s' % (r['os'], r['client'], r['detail'].replace('\n', ' ')))
    print('\n'.join(out))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
