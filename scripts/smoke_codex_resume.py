#!/usr/bin/env python3
"""Real-client smoke test: a conversation written by AgentRelay must be resumable by the installed Codex.

Writes a synthetic conversation into a throw-away CODEX_HOME with the Codex adapter, then drives the real
``codex app-server`` over stdio JSON-RPC (``thread/resume``) and checks that Codex rebuilds every turn and
its items. Needs the ``codex`` CLI on PATH (no login, no network, no model call). Exit codes:
0 = passed, 1 = failed, 77 = codex not installed (skipped).
"""
import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from relay import ir  # noqa: E402
from relay.adapters.codex import CodexAdapter  # noqa: E402

SESSION_ID = '0199aaaa-0000-7000-8000-0000000000a1'


def synthetic():
    return ir.Conversation(source='smoke', title='smoke', cwd='/tmp', model='demo-model', turns=[
        ir.Turn(ir.USER, [ir.Block.text_block('你好')]),
        ir.Turn(ir.ASSISTANT, [ir.Block.tool_call('c1', 'Bash', '{"command":"pwd"}'),
                               ir.Block.tool_result('c1', '/tmp'), ir.Block.text_block('完成')]),
        ir.Turn(ir.USER, [ir.Block.text_block('再来一次')]),
        ir.Turn(ir.ASSISTANT, [ir.Block.text_block('好的')]),
    ])


class AppServer:
    def __init__(self, home, cwd):
        self.proc = subprocess.Popen(['codex', 'app-server', '--listen', 'stdio://'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                     env=dict(os.environ, CODEX_HOME=home), cwd=cwd)
        self.next_id = 0

    def call(self, method, params, timeout=60):
        self.next_id += 1
        want = self.next_id
        self.proc.stdin.write(json.dumps({'id': want, 'method': method, 'params': params}) + '\n')
        self.proc.stdin.flush()
        end = time.time() + timeout
        while time.time() < end:
            ready, _, _ = select.select([self.proc.stdout], [], [], 1)
            if not ready:
                continue
            line = self.proc.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get('id') == want:
                return message
        raise TimeoutError('no response to ' + method)

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def main():
    if not shutil.which('codex'):
        print('skip: codex CLI not found on PATH')
        return 77
    version = subprocess.run(['codex', '--version'], capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cwd:
        CodexAdapter(home=home).write(synthetic(), session_id=SESSION_ID, cwd=cwd)
        server = AppServer(home, cwd)
        try:
            server.call('initialize', {'clientInfo': {'name': 'agentrelay-smoke', 'title': 'smoke', 'version': '0'}})
            server.proc.stdin.write(json.dumps({'method': 'initialized'}) + '\n')
            server.proc.stdin.flush()
            reply = server.call('thread/resume', {'threadId': SESSION_ID})
        finally:
            server.close()
    if reply.get('error'):
        print('FAIL (%s): thread/resume error: %s' % (version, json.dumps(reply['error'], ensure_ascii=False)[:300]))
        return 1
    thread = reply['result']['thread']
    turns = thread.get('turns', [])
    items = [len(turn.get('items', [])) for turn in turns]
    problems = []
    if len(turns) != 2:
        problems.append('expected 2 turns, got %d' % len(turns))
    if not items or min(items) < 2:
        problems.append('every turn should have at least a user and an assistant item, got %s' % items)
    if '你好' not in (thread.get('preview') or ''):
        problems.append('preview missing first user message: %r' % thread.get('preview'))
    if problems:
        print('FAIL (%s): %s' % (version, '; '.join(problems)))
        return 1
    print('ok (%s): resumed %d turns, items per turn %s' % (version, len(turns), items))
    return 0


if __name__ == '__main__':
    sys.exit(main())
