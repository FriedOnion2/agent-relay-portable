#!/usr/bin/env python3
"""Real-client smoke test: a conversation written by AgentRelay must be resumable by the installed Codex.

Writes a synthetic conversation into a throw-away CODEX_HOME with the Codex adapter, then drives the real
``codex app-server`` over stdio JSON-RPC (``thread/resume``) and checks that Codex rebuilds every turn and
its items. Needs the ``codex`` CLI on PATH (no login, no network, no model call). Exit codes:
0 = passed, 1 = failed, 77 = codex not installed (skipped).
"""
import json
from contextlib import contextmanager
import os
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
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
        ir.Turn(ir.ASSISTANT, [ir.Block.thinking_block('先检查目录'),
                               ir.Block.tool_call('c1', 'Bash', '{"command":"pwd"}'),
                               ir.Block.tool_result('c1', '/tmp'),
                               ir.Block.tool_call('c2', 'Read', '{"path":"missing.txt"}'),
                               ir.Block.tool_result('c2', '文件不存在', True), ir.Block.text_block('完成')]),
        ir.Turn(ir.USER, [ir.Block.text_block('再来一次')]),
        ir.Turn(ir.ASSISTANT, [ir.Block.text_block('好的')]),
    ])


class AppServer:
    def __init__(self, home, cwd):
        self.proc = subprocess.Popen([shutil.which('codex'), 'app-server', '--listen', 'stdio://'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1,
                                     env=dict(os.environ, CODEX_HOME=home), cwd=cwd,
                                     start_new_session=os.name != 'nt')
        self.next_id = 0
        # select() does not work on pipes on Windows, so a reader thread feeds a queue instead.
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=self._pump, daemon=True)
        self.reader.start()

    def _pump(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def call(self, method, params, timeout=60):
        self.next_id += 1
        want = self.next_id
        self.proc.stdin.write(json.dumps({'id': want, 'method': method, 'params': params}) + '\n')
        self.proc.stdin.flush()
        end = time.time() + timeout
        while time.time() < end:
            try:
                line = self.lines.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                break
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get('id') == want:
                return message
        raise TimeoutError('no response to ' + method)

    def close(self):
        # EOF lets both npm wrappers and native app-server finish their children
        # and release databases. Terminating only the wrapper can strand them.
        self.proc.stdin.close()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(self.proc.pid), '/T', '/F'],
                               capture_output=True, timeout=10)
            else:
                os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait(10)
        self.reader.join(10)
        if self.reader.is_alive():
            raise RuntimeError('app-server output pipe did not close')
        self.proc.stdout.close()


@contextmanager
def temporary_directory():
    directory = tempfile.TemporaryDirectory()
    try:
        yield directory.name
    finally:
        # Windows may release file handles just after process exit. Retry only
        # permission errors, finitely; persistent failures remain visible.
        for attempt in range(5):
            try:
                directory.cleanup()
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.1 * (attempt + 1))


def history_problems(thread):
    turns = thread.get('turns', [])
    if len(turns) != 2:
        return ['expected 2 turns, got %d' % len(turns)]
    items = [item for turn in turns for item in turn.get('items', [])]
    problems = []
    kinds = [item['type'] for item in items]
    if kinds != ['userMessage', 'reasoning', 'dynamicToolCall', 'dynamicToolCall', 'agentMessage',
                 'userMessage', 'agentMessage']:
        problems.append('unexpected history item types: %s' % kinds)
    serialized = json.dumps(items, ensure_ascii=False)
    for value in ('你好', '先检查目录', 'pwd', '/tmp', 'missing.txt', '文件不存在', '完成', '再来一次', '好的'):
        if value not in serialized:
            problems.append('missing history content: ' + value)
    tools = [item for item in items if item['type'] == 'dynamicToolCall']
    if len(tools) == 2:
        if tools[0].get('arguments') != {'command': 'pwd'} or tools[0].get('success') is not True:
            problems.append('first tool arguments / result status changed')
        if tools[1].get('arguments') != {'path': 'missing.txt'} or tools[1].get('success') is not False:
            problems.append('failed tool arguments / result status changed')
    if '你好' not in (thread.get('preview') or ''):
        problems.append('preview missing first user message: %r' % thread.get('preview'))
    return problems


def main():
    if not shutil.which('codex'):
        print('skip: codex CLI not found on PATH')
        return 77
    version = subprocess.run([shutil.which('codex'), '--version'], capture_output=True,
                             text=True, encoding='utf-8', timeout=30).stdout.strip()
    with temporary_directory() as home, temporary_directory() as cwd:
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
    problems = history_problems(thread)
    if problems:
        print('FAIL (%s): %s' % (version, '; '.join(problems)))
        return 1
    print('ok (%s): resumed %d turns, items per turn %s' % (version, len(turns), items))
    return 0


if __name__ == '__main__':
    sys.exit(main())
