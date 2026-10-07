"""Verify frozen CLI, bundled Zstd, shared data root, HTTP and graceful exit."""
import json
import http.client
import os
import shutil
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
        for home in homes.values():
            Path(home).mkdir()
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
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def run(*args, device_root=None, failure=False):
            command_env = dict(env, RELAY_PORTABLE_ROOT=str(device_root or root))
            result = subprocess.run([str(binary), *args], env=command_env, cwd=folder,
                                    capture_output=True, text=True, encoding='utf-8', timeout=45)
            if failure:
                assert result.returncode != 0, result.stdout
                return result.stdout + result.stderr
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            return result.stdout
        run('--help')
        assert 'Release 内置 Python' in run('doctor')
        environment = json.loads(run('device-config'))
        assert environment['runtime']['bundled'] and environment['runtime']['zstandard']
        assert environment['runtime']['fts5'] and environment['runtime']['sqlite']
        health = json.loads(run('health', '--output', str(root / 'health-output')))
        assert health['ok'] and len(health['adapters']) == 6
        assert all(row['native_resume'] == 'not-tested' for row in health['adapters'])
        arguments = ('transfer', 'workbuddy', 'fixture', '--to', 'dsh', '--cwd', str(root), '--json')
        plan = json.loads(run(*arguments, '--dry-run'))
        assert not list(Path(homes['dsh']).rglob('session*'))
        assert '重新预览' in run(*arguments, '--preview-token', 'outdated', failure=True)
        transferred = json.loads(run(*arguments, '--preview-token', plan['token']))
        assert transferred['ok']
        run('store-sessions', 'workbuddy', 'fixture')
        # Execute FTS5 and the analysis module inside the frozen interpreter.
        for n in range(3):
            source.write(ir.Conversation(title='发布流程知识库', cwd=str(root), turns=[
                ir.Turn(ir.USER,[ir.Block.text_block('核对项目发布流程 portable release')]),
                ir.Turn(ir.ASSISTANT,[ir.Block.thinking_block('思考暗号 hiddenreason'),
                    ir.Block.tool_call('a','Read','{"file_path":"/private/fixture"}'),
                    ir.Block.tool_result('a','read complete'),
                    ir.Block.tool_call('b','Bash','{"command":"echo sensitive-example"}'),
                    ir.Block.tool_result('b','command complete'),ir.Block.text_block('release发布 ready')]),
            ]),session_id='workflow-%d' % n)
        indexed=json.loads(run('index','--source','workbuddy'))
        assert indexed['ok'] and indexed['indexed']==5, indexed
        for query in ('发','发布','release发布','portable 发布'):
            assert len(json.loads(run('search',query))['results'])==3, query
        assert not json.loads(run('search','hiddenreason','--include-thinking'))['results']
        run('index','--source','workbuddy','--include-thinking')
        assert not json.loads(run('search','hiddenreason'))['results']
        assert len(json.loads(run('search','hiddenreason','--include-thinking'))['results'])==3
        run('index','--source','workbuddy')
        assert not json.loads(run('search','hiddenreason','--include-thinking'))['results']
        candidates=json.loads(run('extract-skills'))['candidates']
        assert len(candidates)==1 and candidates[0]['evidence_count']==3
        draft=root/'reviewed.md';draft.write_text(candidates[0]['markdown'],encoding='utf-8')
        assert 'sensitive-example' not in candidates[0]['markdown'] and not candidates[0]['selected']
        run('export-draft',str(draft),'--directory',str(root),failure=True)
        exported=json.loads(run('export-draft',str(draft),'--directory',str(root),'--confirm'))
        assert Path(exported['path']).is_file()
        run('export-draft',str(draft),'--directory',str(root),'--confirm',failure=True)
        assert list((root / 'storage/conversations/workbuddy').glob('*.zip'))
        # Full Skill files are transported; no script is ever executed.
        skill = root / 'fixture-skill'; (skill / 'resources').mkdir(parents=True)
        (skill / 'SKILL.md').write_text('---\nname: fixture-skill\ndescription: portable fixture\n---\nFixture', encoding='utf-8')
        (skill / 'resources/data.bin').write_bytes(bytes(range(256)))
        run('store-skills', 'workbuddy', str(skill))
        other = root / '设备 B new root'; other.mkdir()
        other_homes = {name:str(other / name) for name in homes}
        for home in other_homes.values(): Path(home).mkdir()
        (other / 'config.json').write_text(json.dumps({'agent_homes':other_homes}), encoding='utf-8')
        shutil.copytree(root / 'storage', other / 'storage')
        shutil.copytree(root / 'index', other / 'index')
        moved=json.loads(run('search','发布',device_root=other))['results']
        assert len(moved)==3
        assert not json.loads(run('indexed-session',moved[0]['key'],device_root=other))['can_open']
        assert len(json.loads(run('extract-skills',device_root=other))['candidates'])==1
        moved_index=json.loads(run('index','--source','workbuddy',device_root=other))
        assert moved_index['ok'],moved_index
        package = next((other / 'storage/conversations/workbuddy').glob('*.zip'))
        restore_args = ('restore-session', str(package), '--cwd', str(other))
        plan = json.loads(run(*restore_args, '--dry-run', device_root=other))
        run(*restore_args, '--preview-token', plan['token'], device_root=other)
        assert 'portable fixture' in run('export', 'workbuddy', 'fixture', device_root=other)
        assert run(*restore_args, device_root=other, failure=True)
        skill_package = next((other / 'storage/skills/workbuddy').glob('*.zip'))
        target_skills = other / 'skills'
        skill_args = ('restore-skill', str(skill_package), '--skills-dir', str(target_skills))
        run(*skill_args, device_root=other)
        assert (target_skills / 'fixture-skill/resources/data.bin').read_bytes() == bytes(range(256))
        assert run(*skill_args, device_root=other, failure=True)
        # Exercise the exact frozen worker, dynamic CLI choices and hash gate.
        plugin = root / 'plaintext_adapter.py'
        shutil.copyfile(ROOT / 'examples/plaintext_adapter.py', plugin)
        (root / 'example-conversations').mkdir()
        (root / 'example-conversations/example.txt').write_text('plugin fixture 中文', encoding='utf-8')
        assert json.loads(run('plugins', 'enable', 'plaintext', str(plugin)))['community']
        assert 'plugin fixture 中文' in run('export', 'plaintext', 'example.txt')
        assert json.loads(run('index','--source','plaintext','--no-packages'))['ok']
        assert len(json.loads(run('search','plugin fixture 中文','--source','plaintext'))['results'])==1
        run('transfer', 'plaintext', 'example.txt', '--to', 'claude', '--cwd', str(root), '--json')
        plugin.write_text(plugin.read_text(encoding='utf-8') + '\n# changed\n', encoding='utf-8')
        assert '已改变' in run('export', 'plaintext', 'example.txt', failure=True)
        run('plugins', 'disable', 'plaintext')
        local = root / 'codex-local'; local.mkdir()
        run('device-config', '--agent', 'codex', '--home', str(local))
        assert json.loads(run('sources', '--json'))
        assert 'codex-local' not in (root / 'config.json').read_text(encoding='utf-8')
        print('PASS: frozen FTS5 Chinese/mixed search, thought purge, workflow drafts and relocated corpus; preview/token, formats, plugin, device and storage restore')
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
                            with opener.open('http://127.0.0.1:%d/' % candidate, timeout=.2) as response:
                                if response.headers.get('Server', '').startswith('AgentRelay/'):
                                    assert b'selectAllSessions' in response.read()
                                    actual = candidate
                                    break
                        except (OSError, http.client.HTTPException):
                            pass
                    if actual is None:
                        time.sleep(.1)
                assert actual, 'Packaged HTTP server did not start'
                request = urllib.request.Request('http://127.0.0.1:%d/api/shutdown' % actual, data=b'{}',
                                                 headers={'Content-Type': 'application/json'})
                with opener.open(request, timeout=5) as response:
                    assert json.load(response)['ok']
                assert process.wait(timeout=20) == 0
            finally:
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=10)
                process.stderr.close()
        print('PASS: standalone CLI, Zstd DSH import, shared portable storage, occupied-port HTTP and exit (PATH empty)')


if __name__ == '__main__':
    smoke(sys.argv[1])
