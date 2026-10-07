"""Explicitly trusted read adapters, isolated from the server by a worker process."""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import device, ir
from .adapters.base import BaseAdapter, SessionInfo
from .runtime import project_root

API_VERSION = 1
MAX_OUTPUT = 32 * 1024 * 1024
TIMEOUT = 15
entries = {}
errors = []


def configure(rows):
    entries.clear()
    errors.clear()
    from .locations import SOURCES
    for row in rows:
        try:
            if not isinstance(row, dict):
                raise ValueError('插件配置必须是对象')
            name = row.get('name')
            if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', name):
                raise ValueError('插件名称无效')
            if name in SOURCES or name.startswith(('windows_', 'ubuntu_')) or name in entries:
                raise ValueError('插件不能覆盖内置来源或重复注册')
            if row.get('api_version') != API_VERSION:
                raise ValueError('插件接口版本不匹配')
            path = Path(row['path'])
            if not path.is_absolute():
                path = project_root() / path
            digest = row.get('sha256', '')
            if not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('插件缺少已确认的 SHA-256')
            entries[name] = dict(row, path=str(path.resolve()))
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))


def enable(name, path):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix != '.py' or path.stat().st_size > 1024 * 1024:
        raise ValueError('请选择不超过 1 MiB 的可信 Python 插件文件')
    row = {'name':name, 'path':str(path), 'api_version':API_VERSION,
           'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    try:
        row['path'] = path.relative_to(project_root().resolve()).as_posix()
    except ValueError:
        pass
    saved = device.read()
    rows = [entry for entry in saved.get('plugins', []) if entry.get('name') != name] + [row]
    configure(rows)
    if errors:
        message = '; '.join(errors)
        configure(saved.get('plugins', []))
        raise ValueError(message)
    # Loading happens only after explicit enable, in an isolated worker.
    adapter = PluginAdapter(name)
    try:
        info = adapter.info()
    except Exception:
        configure(saved.get('plugins', []))
        raise
    saved['plugins'] = rows
    device.write(saved)
    return info


def disable(name):
    saved = device.read()
    saved['plugins'] = [row for row in saved.get('plugins', []) if row.get('name') != name]
    device.write(saved)
    configure(saved['plugins'])
    return {'ok':True, 'disabled':name}


def _invoke(name, action, sid=None):
    spec = entries[name]
    if getattr(sys, 'frozen', False):
        command = [sys.executable, '--plugin-worker']
    else:
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'portable.py'), '--plugin-worker']
    # Stdout is a bounded file instead of unbounded capture_output in memory.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as diagnostic:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=output, stderr=diagnostic)
        try:
            process.stdin.write(json.dumps({'spec':spec, 'action':action, 'id':sid}).encode('utf-8'))
            process.stdin.close()
            deadline = time.monotonic() + TIMEOUT
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise ValueError('社区插件调用超时，已停止工作进程')
                if os.fstat(output.fileno()).st_size > MAX_OUTPUT or os.fstat(diagnostic.fileno()).st_size > MAX_OUTPUT:
                    raise ValueError('社区插件输出超过 32 MiB，已停止工作进程')
                time.sleep(.05)
        finally:
            if not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                process.kill()
                process.wait()
        if process.returncode:
            diagnostic.seek(0)
            raise ValueError('社区插件调用失败：' + diagnostic.read(2000).decode('utf-8', 'replace')) from None
        output.seek(0, 2)
        if output.tell() > MAX_OUTPUT:
            raise ValueError('社区插件返回内容超过 32 MiB')
        output.seek(0)
        value = json.load(output)
    if not isinstance(value, dict) or not value.get('ok'):
        raise ValueError(value.get('error', '插件返回无效') if isinstance(value, dict) else '插件返回无效')
    return value['data']


def _conversation(value):
    if not isinstance(value, dict) or not isinstance(value.get('turns'), list):
        raise ValueError('插件必须返回统一 Conversation')
    fields = {key: value[key] for key in ('source','id','title','cwd','model','created_at','updated_at','path','meta','truncated') if key in value}
    turns = []
    if len(value['turns']) > 100000:
        raise ValueError('插件轮次数量超出限制')
    for row in value['turns']:
        if row.get('role') not in (ir.USER, ir.ASSISTANT, ir.SYSTEM):
            raise ValueError('插件角色无效')
        blocks = [ir.Block(**item) for item in row.get('blocks', [])]
        turns.append(ir.Turn(row['role'], blocks, row.get('ts'), row.get('model')))
    return ir.Conversation(turns=turns, **fields)


class PluginAdapter(BaseAdapter):
    can_write = False
    api_version = API_VERSION

    def __init__(self, name):
        self.name = name
        self.label = '社区：' + name
        self.home = None

    def info(self):
        data = _invoke(self.name, 'info')
        if data.get('name') != self.name or data.get('api_version') != API_VERSION:
            raise ValueError('插件名称或接口版本不匹配')
        self.home = data.get('home')
        self.label = '社区：' + str(data.get('label') or self.name)
        return dict(data, label=self.label, can_read=True, can_write=False, community=True,
                    capabilities=['read', 'export', 'convert_source'], api_version=API_VERSION,
                    read_note='可信社区 Python 插件；独立进程与超时隔离，不是安全沙箱。',
                    write_note='首版社区插件仅作为读取与转换来源，不进行原生存储或写入')

    def available(self):
        return bool(self.info().get('available'))

    def discover(self):
        rows = _invoke(self.name, 'discover')
        if not isinstance(rows, list) or len(rows) > 100000:
            raise ValueError('插件会话列表无效或过大')
        for row in rows:
            row = dict(row, source=self.name)
            yield SessionInfo(**{key:row[key] for key in SessionInfo.__dataclass_fields__ if key in row})

    def read(self, sid):
        conv = _conversation(_invoke(self.name, 'read', sid))
        conv.source = self.name
        return conv

    def write(self, conv, **kwargs):
        raise ValueError('社区插件尚未开放写入；请选择内置可写目标')


def worker():
    """Internal entry, available in both source and frozen packages."""
    try:
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, 'reconfigure'):
                stream.reconfigure(encoding='utf-8')
        request = json.loads(sys.stdin.buffer.read(2 * 1024 * 1024))
        spec = request['spec']
        path = Path(spec['path'])
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('插件文件过大')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != spec['sha256']:
            raise ValueError('插件文件已改变，请检查内容并重新启用')
        # Execute the exact bytes verified above; never reopen changed code.
        module_spec = importlib.util.spec_from_file_location('agentrelay_community', path)
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_spec.name] = module
        import contextlib
        with contextlib.redirect_stdout(sys.stderr):
            exec(compile(raw, str(path), 'exec'), module.__dict__)
            adapter = module.Adapter()
            if adapter.name != spec['name'] or adapter.api_version != API_VERSION:
                raise ValueError('插件名称或接口版本不匹配')
            action = request['action']
            if action == 'info':
                data = adapter.info()
                data['api_version'] = adapter.api_version
            elif action == 'discover':
                data = []
                for row in adapter.discover():
                    if len(data) >= 100000:
                        raise ValueError('插件列表过大')
                    data.append(row.to_dict())
            elif action == 'read':
                data = adapter.read(request['id']).to_dict()
            else:
                raise ValueError('不支持的插件操作')
        encoded = json.dumps({'ok':True, 'data':data}, ensure_ascii=False).encode('utf-8')
        if len(encoded) > MAX_OUTPUT:
            raise ValueError('插件返回内容过大')
        sys.stdout.buffer.write(encoded)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
