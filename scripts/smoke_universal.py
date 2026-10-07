"""Verify the actual all-platform download and host launcher with isolated data."""
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from relay import ir
from relay.adapters.workbuddy import WorkBuddyAdapter


def smoke(asset):
    asset = Path(asset).resolve()
    with zipfile.ZipFile(asset) as archive:
        names = archive.namelist()
        assert len([name for name in names if '/runtimes/' in name]) == 4
        assert not any('/tests/' in name or '/docs/' in name or '/.git/' in name or name.endswith('.md') for name in names)
    with tempfile.TemporaryDirectory(prefix='AgentRelay universal 中文 ') as folder:
        destination = Path(folder)
        if sys.platform == 'darwin':
            subprocess.run(['/usr/bin/ditto', '-x', '-k', str(asset), folder], check=True)
        else:
            with zipfile.ZipFile(asset) as archive:
                archive.extractall(destination)
        root = next(path for path in destination.iterdir() if path.is_dir())
        homes = {name: str(destination / 'fixtures' / name) for name in ('workbuddy', 'dsh', 'codebuddy', 'claude', 'claude_sdk', 'codex')}
        config = {'agent_homes': homes, 'open_browser': False}
        (root / 'config.json').write_text(json.dumps(config), encoding='utf-8')
        conversation = ir.Conversation(source='fixture', title='Universal fixture', cwd=str(destination), turns=[
            ir.Turn(ir.USER, [ir.Block.text_block('portable test')]),
            ir.Turn(ir.ASSISTANT, [ir.Block.text_block('ready')]),
        ])
        WorkBuddyAdapter(home=homes['workbuddy']).write(conversation, session_id='fixture')
        def request(port, path='/', body=None):
            options = {} if body is None else {'data': json.dumps(body).encode(), 'headers': {'Content-Type':'application/json'}}
            req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), **options)
            with urllib.request.urlopen(req, timeout=3) as response:
                data = response.read()
                return json.loads(data) if path.startswith('/api/') else data
        def wait(port, process=None):
            deadline = time.monotonic() + 100
            while time.monotonic() < deadline:
                if process is not None and process.poll() is not None:
                    raise AssertionError('Launcher exited early: ' + process.stderr.read().decode('utf-8', 'replace'))
                try:
                    assert b'selectAllSkills' in request(port)
                    return
                except OSError:
                    time.sleep(.2)
            raise AssertionError('Universal launcher did not become ready')
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0)); occupied.listen()
            port = occupied.getsockname()[1]
            if port > 65530:
                raise AssertionError('Ephemeral port too high; retry')
            if sys.platform == 'win32':
                command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(root / 'Start-AgentRelay.ps1')]
            else:
                command = ['/bin/bash', str(root / ('启动_AgentRelay.command' if sys.platform == 'darwin' else '启动_AgentRelay.sh'))]
            process = subprocess.Popen(command + ['--no-browser', '--port', str(port)], cwd=destination,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            actual = port + 1
            try:
                wait(actual, process)
                stored = request(actual, '/api/store-session', {'source':'workbuddy', 'id':'fixture'})
                assert stored['ok']
                assert Path(stored['path']).is_relative_to(root / 'storage'), stored
                imported = request(actual, '/api/transfer', {'source':'workbuddy', 'id':'fixture', 'target':'dsh', 'cwd':str(destination)})
                assert imported['ok'], imported
                assert request(actual, '/api/shutdown', {})['ok']
                assert process.wait(timeout=20) == 0
            finally:
                if process.poll() is None:
                    try:
                        request(actual, '/api/shutdown', {})
                        process.wait(timeout=10)
                    except Exception:
                        process.terminate(); process.wait(timeout=10)
                process.stderr.close()
        if sys.platform == 'darwin':
            # The Finder entry must also retain the root config/storage instead of cache paths.
            with socket.socket() as free:
                free.bind(('127.0.0.1', 0)); native_port = free.getsockname()[1]
            config['port'] = native_port
            (root / 'config.json').write_text(json.dumps(config), encoding='utf-8')
            subprocess.run(['/usr/bin/open', '-n', str(root / 'AgentRelay.app')], check=True)
            try:
                wait(native_port)
                stored = request(native_port, '/api/store-session', {'source':'workbuddy', 'id':'fixture'})
                assert Path(stored['path']).is_relative_to(root / 'storage')
            finally:
                request(native_port, '/api/shutdown', {})
            # Confirm no service is left pointing at the temporary root.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    request(native_port)
                except OSError:
                    break
                time.sleep(.1)
            else:
                raise AssertionError('Finder-launched service did not exit')
        print('PASS: universal package on %s/%s; shared storage, bundled DSH and exit' % (platform.system(), platform.machine()))


if __name__ == '__main__':
    smoke(sys.argv[1])
