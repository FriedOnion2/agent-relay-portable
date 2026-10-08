#!/usr/bin/env python3
"""Run every real-client smoke test on this machine and print / save a per-client result.

Each client ends up as ``pass``, ``fail`` or ``skip`` (with a reason). Clients that cannot be driven headlessly
or that AgentRelay cannot write to are declared skips, so the support table below stays complete on every OS.
Usage: smoke_all.py [--json out.json]. Exit code is 1 only when a smoke test that ran has failed.
"""
import json
import platform
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

# name -> script, or a fixed skip reason when there is nothing automatable.
CLIENTS = [
    ('Codex', 'smoke_codex_resume.py'),
    ('DSH', 'smoke_dsh_native.py'),
    ('Claude Code', '需要登录才能续聊，且无法无头驱动'),
    ('CodeBuddy', 'AgentRelay 只读取 CodeBuddy，没有写入路径可测'),
    ('WorkBuddy', '桌面应用，无法在无界面环境启动'),
]


def os_name():
    return {'Linux': 'Linux', 'Darwin': 'macOS', 'Windows': 'Windows'}.get(platform.system(), platform.system())


def run_one(script):
    try:
        result = subprocess.run([sys.executable, str(SCRIPTS / script)], capture_output=True, text=True,
                                encoding='utf-8', timeout=300)
    except subprocess.TimeoutExpired:
        return 'fail', '超时（300 秒）'
    detail = (result.stdout.strip().splitlines() or [''])[-1] or result.stderr.strip()[-200:]
    if result.returncode == 0:
        return 'pass', detail
    if result.returncode == 77:
        return 'skip', detail.replace('skip: ', '')
    return 'fail', (result.stdout + result.stderr).strip()[-400:]


def main():
    rows = []
    for name, target in CLIENTS:
        if target.endswith('.py'):
            status, detail = run_one(target)
        else:
            status, detail = 'skip', target
        rows.append({'os': os_name(), 'client': name, 'status': status, 'detail': detail})
        print('%-12s %-5s %s' % (name, status, detail))
    if '--json' in sys.argv:
        Path(sys.argv[sys.argv.index('--json') + 1]).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    return 1 if any(row['status'] == 'fail' for row in rows) else 0


if __name__ == '__main__':
    sys.exit(main())
