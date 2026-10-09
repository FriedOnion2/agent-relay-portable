"""Strict Windows -> Ubuntu -> Windows native-package gate, using synthetic data.

Codex is driven through its real app-server. A loopback Responses endpoint supplies
one deterministic text answer: no login, paid model, historical tool execution or
user session directory is involved. Missing clients fail this release gate.
"""
import argparse
import hashlib
import json
import os
import platform
import queue
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from relay import preview, registry, session_store  # noqa: E402
from relay.adapters.codex import CodexAdapter  # noqa: E402
from smoke_codex_resume import AppServer, SESSION_ID, synthetic  # noqa: E402


class Responses(BaseHTTPRequestHandler):
    calls = 0

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert self.path.endswith('/responses'), self.path
        assert payload['stream'] is True
        type(self).calls += 1
        answer = 'AgentRelay loopback continuation verified'
        part = {'type': 'output_text', 'text': answer, 'annotations': []}
        item = {'id': 'msg_relay', 'type': 'message', 'role': 'assistant',
                'status': 'completed', 'content': [part]}
        response = {'id': 'resp_relay', 'object': 'response', 'created_at': int(time.time()),
                    'model': 'relay-fixture', 'status': 'completed', 'output': [item],
                    'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}
        events = [
            {'type': 'response.created', 'response': dict(response, status='in_progress', output=[])},
            {'type': 'response.output_item.added', 'output_index': 0,
             'item': dict(item, status='in_progress', content=[])},
            {'type': 'response.content_part.added', 'output_index': 0, 'content_index': 0,
             'item_id': item['id'], 'part': dict(part, text='')},
            {'type': 'response.output_text.delta', 'output_index': 0, 'content_index': 0,
             'item_id': item['id'], 'delta': answer},
            {'type': 'response.output_text.done', 'output_index': 0, 'content_index': 0,
             'item_id': item['id'], 'text': answer},
            {'type': 'response.content_part.done', 'output_index': 0, 'content_index': 0,
             'item_id': item['id'], 'part': part},
            {'type': 'response.output_item.done', 'output_index': 0, 'item': item},
            {'type': 'response.completed', 'response': response},
        ]
        data = ''.join('event: %s\ndata: %s\n\n' % (event['type'], json.dumps(event))
                       for event in events).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def initialize(server):
    result = server.call('initialize', {'clientInfo': {'name': 'relay-cross-device', 'version': '1'}})
    assert not result.get('error'), result
    server.proc.stdin.write(json.dumps({'method': 'initialized'}) + '\n')
    server.proc.stdin.flush()


def resumed(server, cwd):
    result = server.call('thread/resume', {'threadId': SESSION_ID, 'cwd': str(cwd),
                                         'modelProvider': 'relay-smoke', 'model': 'relay-fixture'})
    assert not result.get('error'), result
    return result['result']['thread']


def check_history(thread, markers):
    items = [item for turn in thread['turns'] for item in turn.get('items', [])]
    serialized = json.dumps(items, ensure_ascii=False)
    for marker in ['你好', '先检查目录', '文件不存在', '完成', '再来一次', '好的'] + markers:
        assert marker in serialized, 'Missing client-visible history: ' + marker
    tools = [item for item in items if item['type'] == 'dynamicToolCall']
    assert len(tools) == 2, tools
    assert tools[0]['arguments'] == {'command': 'pwd'} and tools[0]['success'] is True
    assert tools[1]['arguments'] == {'path': 'missing.txt'} and tools[1]['success'] is False
    assert '/tmp' in serialized


def continue_codex(home, cwd, markers):
    endpoint = ThreadingHTTPServer(('127.0.0.1', 0), Responses)
    worker = threading.Thread(target=endpoint.serve_forever, daemon=True)
    worker.start()
    (home / 'config.toml').write_text(
        'model = "relay-fixture"\nmodel_provider = "relay-smoke"\n'
        '[model_providers.relay-smoke]\nname = "Loopback verification"\n'
        'base_url = "http://127.0.0.1:%d/v1"\nwire_api = "responses"\n'
        'requires_openai_auth = false\n' % endpoint.server_port, encoding='utf-8')
    before = Responses.calls
    server = AppServer(str(home), str(cwd))
    try:
        initialize(server)
        check_history(resumed(server, cwd), markers)
        marker = 'relay-continuation-' + platform.system() + '-' + str(len(markers))
        result = server.call('turn/start', {'threadId': SESSION_ID,
            'input': [{'type': 'text', 'text': marker}], 'approvalPolicy': 'never',
            'sandboxPolicy': {'type': 'readOnly'}, 'model': 'relay-fixture'})
        assert not result.get('error'), result
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                line = server.lines.get(timeout=1)
            except queue.Empty:
                continue
            assert line is not None, 'Codex exited during continuation'
            event = json.loads(line)
            if event.get('method') == 'turn/completed':
                turn = event['params']['turn']
                assert turn['status'] == 'completed' and not turn.get('error'), turn
                break
        else:
            raise AssertionError('Codex continuation timed out')
        assert Responses.calls > before, 'Continuation never reached loopback endpoint'
    finally:
        server.close()
        endpoint.shutdown()
        endpoint.server_close()
        worker.join(3)
    markers = markers + [marker, 'AgentRelay loopback continuation verified']
    server = AppServer(str(home), str(cwd))
    try:
        initialize(server)
        check_history(resumed(server, cwd), markers)
    finally:
        server.close()
    return markers


def snapshot(folder):
    return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob('*') if path.is_file()}


def run(phase, incoming, output):
    if not shutil.which('codex'):
        raise RuntimeError('Codex is required; missing clients cannot pass the release gate')
    expected_os = 'Linux' if phase == 'ubuntu' else 'Windows'
    assert platform.system() == expected_os, (phase, platform.system())
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='relay cross-device 中文 ') as temporary:
        root = Path(temporary)
        os.environ['RELAY_PORTABLE_ROOT'] = str(root)
        home = root / 'codex'; home.mkdir()
        cwd = root / '项目'; cwd.mkdir()
        registry._CACHE.clear()
        registry._CACHE['codex'] = CodexAdapter(home=str(home))
        markers = []
        if phase == 'windows-source':
            registry.get('codex').write(synthetic(), session_id=SESSION_ID, cwd=str(cwd))
        else:
            receipt = json.loads((incoming / 'receipt.json').read_text(encoding='utf-8'))
            assert receipt['platform'] == ('Windows' if phase == 'ubuntu' else 'Linux'), receipt
            package = incoming / receipt['package']
            source_hash = hashlib.sha256(package.read_bytes()).hexdigest()
            assert source_hash == receipt['sha256']
            markers = receipt['markers']
            plan = preview.package(str(package), str(cwd))
            assert not plan['blockers'], plan
            result = session_store.restore_session(str(package), str(cwd), preview_token=plan['token'])
            assert result['to']['native_id'] == SESSION_ID, result
            restored = registry.get('codex').read(SESSION_ID)
            assert Path(restored.cwd).resolve() == cwd.resolve()
            before = snapshot(home)
            try:
                session_store.restore_session(str(package), str(cwd))
            except (ValueError, FileExistsError):
                pass
            else:
                raise AssertionError('Conflicting native ID was overwritten')
            assert snapshot(home) == before, 'Conflict changed target files'
            assert hashlib.sha256(package.read_bytes()).hexdigest() == source_hash
        markers = continue_codex(home, cwd, markers)
        stored = session_store.store_session('codex', SESSION_ID, root=str(root / 'storage'))
        package = Path(stored['path'])
        shutil.copyfile(package, output / 'codex.zip')
        receipt = {'platform': platform.system(), 'package': 'codex.zip', 'markers': markers,
                   'sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
                   'client': subprocess_version(), 'phase': phase}
        (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        print('PASS: %s; native package, mapped project, preserved tools/reasoning, '
              'real Codex continuation + restart persistence, conflict no-overwrite; %s' % (phase, receipt['client']))


def subprocess_version():
    import subprocess
    return subprocess.check_output([shutil.which('codex'), '--version'], encoding='utf-8').strip()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['windows-source', 'ubuntu', 'windows-return'], required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.phase, args.input, args.output)
