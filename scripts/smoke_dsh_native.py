#!/usr/bin/env python3
"""Real-client smoke test: a conversation written by AgentRelay must load in the installed DSH.

Builds the synthetic fixture used by tests/test_dsh_write.py, writes it with the DSH adapter into a throw-away
DSH_HOME and runs tests/dsh_native_smoke.mjs, which opens it with DSH's own session persistence packages
(list, restore, message projection, continuation write, reload). Needs ``dsh`` (and node) on PATH and
``zstandard``. Exit codes: 0 = passed, 1 = failed, 77 = prerequisite missing (skipped).
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
sys.path.insert(0, str(ROOT / 'tests'))

SESSION_ID = '0199aaaa-0000-7000-8000-0000000000b1'


def dsh_modules():
    dsh = shutil.which('dsh')
    if not dsh:
        return None
    package = Path(os.path.realpath(dsh)).parent.parent
    for candidate in (package / 'node_modules', package.parent.parent / 'node_modules'):
        if (candidate / '@deepseek-ai' / 'dsh-session').is_dir():
            return candidate
    return None


def main():
    try:
        import zstandard  # noqa: F401
    except ImportError:
        print('skip: zstandard not installed')
        return 77
    modules = dsh_modules()
    if not modules or not shutil.which('node'):
        print('skip: dsh / node not found (looked for @deepseek-ai/dsh-session next to the dsh binary)')
        return 77
    from relay.adapters.dsh import DshAdapter
    from test_dsh_write import conversation
    version = subprocess.run(['dsh', '--version'], capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as home:
        adapter = DshAdapter(home=home)
        adapter.write(conversation(), session_id=SESSION_ID, remap_tools=False)
        result = subprocess.run(['node', str(ROOT / 'tests' / 'dsh_native_smoke.mjs'), str(modules), home, SESSION_ID],
                                capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print('FAIL (dsh %s):\n%s%s' % (version, result.stdout[-1500:], result.stderr[-1500:]))
        return 1
    print('ok (dsh %s): %s' % (version, result.stdout.strip().splitlines()[-1]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
