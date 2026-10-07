"""Verify frozen CLI, bundled Zstd, shared data root, HTTP and graceful exit."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from relay import ir
from relay.adapters.workbuddy import WorkBuddyAdapter


def smoke(binary):
    binary = Path(binary).resolve()
    with tempfile.TemporaryDirectory(prefix='AgentRelay release 中文 ') as folder:
        root = Path(folder)
        homes = {name: str(root / name) for name in ('workbuddy', 'dsh', 'codebuddy', 'claude', 'claude_sdk', 'codex')}
        (root / 'config.json').write_text(json.dumps({'agent_homes': homes, 'open_browser': False}), encoding='utf-8')
        env = dict(os.environ, RELAY_PORTABLE_ROOT=str(root))
        # Runtime must not depend on Python/Node found on PATH.
        env['PATH'] = ''
        source = WorkBuddyAdapter(home=homes['workbuddy'])
        conversation = ir.Conversation(source='fixture', title='Release 打包测试', cwd=str(root), turns=[
            ir.Turn(ir.USER, [ir.Block.text_block('portable fixture')]),
            ir.Turn(ir.ASSISTANT, [ir.Block.text_block('ready')]),
        ])
        source.write(conversation, session_id='fixture')
        def run(*args):
            result = subprocess.run([str(binary), *args], env=env, cwd=folder,
                                    capture_output=True, text=True, encoding='utf-8', timeout=45)
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            return result.stdout
        run('--help')
        assert 'Release 内置 Python' in run('doctor')
        transferred = json.loads(run('transfer', 'workbuddy', 'fixture', '--to', 'dsh', '--cwd', str(root), '--json'))
        assert transferred['ok']
        run('store-sessions', 'workbuddy', 'fixture')
        assert list((root / 'storage/conversations/workbuddy').glob('*.zip'))
        # Run behind an occupied port to exercise the real packaged process.
        with socket.socket() as old:
            old.bind(('127.0.0.1', 0)); old.listen()
            port = old.getsockname()[1]
            if port > 65530:
                raise AssertionError('Ephemeral port too close to maximum; retry the build')
            process = subprocess.Popen([str(binary), 'serve', '--port', str(port), '--no-browser'], env=env,
                                       cwd=folder, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 60
                actual = None
                while time.monotonic() < deadline and actual is None:
                    if process.poll() is not None:
                        raise AssertionError(process.stderr.read().decode('utf-8', 'replace'))
                    for candidate in range(port + 1, port + 6):
                        try:
                            with urllib.request.urlopen('http://127.0.0.1:%d/' % candidate, timeout=.2) as response:
                                if response.headers.get('Server', '').startswith('AgentRelay/'):
                                    assert b'selectAllSessions' in response.read()
                                    actual = candidate
                                    break
                        except OSError:
                            pass
                    if actual is None:
                        time.sleep(.1)
                assert actual, 'Packaged HTTP server did not start'
                request = urllib.request.Request('http://127.0.0.1:%d/api/shutdown' % actual, data=b'{}',
                                                 headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(request, timeout=5) as response:
                    assert json.load(response)['ok']
                assert process.wait(timeout=20) == 0
            finally:
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=10)
                process.stderr.close()
        print('PASS: standalone CLI, Zstd DSH import, shared portable storage, occupied-port HTTP and exit (PATH empty)')


if __name__ == '__main__':
    smoke(sys.argv[1])
