"""Explicitly trusted read adapters, isolated from the server by a worker process."""

from .messages import text as message_text, error_text
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
entries: dict = {}
errors: list = []


def configure(rows):
    entries.clear()
    errors.clear()
    from .locations import SOURCES
    for row in rows:
        try:
            if not isinstance(row, dict):
                raise ValueError(message_text('err.plugin_configuration_must_be_an_object'))
            name = row.get('name')
            if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', name):
                raise ValueError(message_text('err.invalid_plugin_name'))
            if name in SOURCES or name.startswith(('windows_', 'ubuntu_')) or name in entries:
                raise ValueError(message_text('err.plugins_cannot_override_built_in_sources_or_register_twice'))
            if row.get('api_version') != API_VERSION:
                raise ValueError(message_text('err.plugin_interface_version_does_not_match'))
            path = Path(row['path'])
            if not path.is_absolute():
                path = project_root() / path
            digest = row.get('sha256', '')
            if not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError(message_text('err.plugin_lacks_a_confirmed_sha_256'))
            entries[name] = dict(row, path=str(path.resolve()))
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(error_text(exc))


def enable(name, path):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix != '.py' or path.stat().st_size > 1024 * 1024:
        raise ValueError(message_text('err.select_a_trusted_python_plugin_file_of_at_most_1_mib'))
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


def check(name, path, sample=3):
    """开发插件时的自检：不保存任何配置，只在隔离进程里跑一遍接口并报告每一项。"""
    from .adapters.markdown import render as render_markdown
    checks = []

    def record(label, ok, detail=''):
        checks.append({'check': label, 'ok': bool(ok), 'detail': str(detail)})
        return ok

    path = Path(path).expanduser().resolve()
    if not record(message_text('msg.name_format'), isinstance(name, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', name),
                  message_text('msg.starts_with_a_lowercase_letter_only_lowercase_letters_digits_underscores_and_hyphens_at_mo')):
        return {'ok': False, 'checks': checks}
    from .locations import SOURCES
    if not record(message_text('msg.does_not_override_built_in_sources'), name not in SOURCES and not name.startswith(('windows_', 'ubuntu_')), name):
        return {'ok': False, 'checks': checks}
    if not record(message_text('msg.file'), path.is_file() and path.suffix == '.py' and path.stat().st_size <= 1024 * 1024,
                  message_text('msg.a_py_file_of_at_most_1_mib_is_required')):
        return {'ok': False, 'checks': checks}
    saved = dict(entries)
    entries[name] = {'name': name, 'path': str(path), 'api_version': API_VERSION,
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    try:
        adapter = PluginAdapter(name)
        try:
            info = adapter.info()
        except Exception as exc:
            record(message_text('msg.load_and_call_info'), False, exc)
            return {'ok': False, 'checks': checks}
        record(message_text('msg.load_and_call_info'), True, message_text('msg.name_and_api_version_match'))
        record(message_text('msg.info_describes_directory_availability'), 'available' in info, 'available=%s' % info.get('available'))
        try:
            rows = list(adapter.discover())
        except Exception as exc:
            record(message_text('msg.discover_returns_a_session_list'), False, exc)
            return {'ok': False, 'checks': checks}
        record(message_text('msg.discover_returns_a_session_list'), True, message_text('msg.value_sessions', value=len(rows)))
        record(message_text('msg.session_ids_are_unique'), len({row.id for row in rows}) == len(rows), message_text('msg.duplicate_ids_make_read_id_ambiguous'))
        readable = [row for row in rows if row.readable][:max(1, sample)]
        if not readable:
            record(message_text('msg.read_reads_the_sample'), True, message_text('msg.no_readable_sessions_skipped_prepare_a_synthetic_sample_before_self_check'))
        for row in readable:
            try:
                conv = adapter.read(row.id)
                text = render_markdown(conv)
                ok = bool(conv.turns) and isinstance(text, str)
                record(message_text('msg.read_id_returns_a_nonempty_session_that_can_be_exported_to_markdown', id=row.id), ok, message_text('msg.value_turns', value=len(conv.turns)))
            except Exception as exc:
                record('read(%s)' % row.id, False, exc)
    finally:
        entries.clear()
        entries.update(saved)
    return {'ok': all(row['ok'] for row in checks), 'checks': checks}


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
                    raise ValueError(message_text('err.community_plugin_call_timed_out_worker_stopped'))
                if os.fstat(output.fileno()).st_size > MAX_OUTPUT or os.fstat(diagnostic.fileno()).st_size > MAX_OUTPUT:
                    raise ValueError(message_text('err.community_plugin_output_exceeds_32_mib_worker_stopped'))
                time.sleep(.05)
        finally:
            if not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                process.kill()
                process.wait()
        if process.returncode:
            diagnostic.seek(0)
            raise ValueError(message_text('err.community_plugin_call_failed_value', value=diagnostic.read(2000).decode('utf-8', 'replace'))) from None
        output.seek(0, 2)
        if output.tell() > MAX_OUTPUT:
            raise ValueError(message_text('err.community_plugin_response_exceeds_32_mib'))
        output.seek(0)
        value = json.load(output)
    if not isinstance(value, dict) or not value.get('ok'):
        raise ValueError(message_text('err.invalid_plugin_response', detail=value.get('error') or message_text('msg.invalid_plugin_return') if isinstance(value, dict) else message_text('msg.invalid_plugin_return')))
    return value['data']


def _conversation(value):
    if not isinstance(value, dict) or not isinstance(value.get('turns'), list):
        raise ValueError(message_text('err.plugin_must_return_a_unified_conversation'))
    fields = {key: value[key] for key in ('source','id','title','cwd','model','created_at','updated_at','path','meta','truncated') if key in value}
    turns = []
    if len(value['turns']) > 100000:
        raise ValueError(message_text('err.plugin_turn_count_exceeds_the_limit'))
    for row in value['turns']:
        if row.get('role') not in (ir.USER, ir.ASSISTANT, ir.SYSTEM):
            raise ValueError(message_text('err.invalid_plugin_role'))
        blocks = [ir.Block(**item) for item in row.get('blocks', [])]
        turns.append(ir.Turn(row['role'], blocks, row.get('ts'), row.get('model')))
    return ir.Conversation(turns=turns, **fields)


class PluginAdapter(BaseAdapter):
    can_write = False
    api_version = API_VERSION

    def __init__(self, name):
        self.name = name
        self.label = message_text('msg.community_name', name=name)
        self.home = None

    def info(self):
        data = _invoke(self.name, 'info')
        if data.get('name') != self.name or data.get('api_version') != API_VERSION:
            raise ValueError(message_text('err.plugin_name_or_interface_version_does_not_match'))
        self.home = data.get('home')
        self.label = message_text('msg.community_value', value=str(data.get('label') or self.name))
        return dict(data, label=self.label, can_read=True, can_write=False, community=True,
                    capabilities=['read', 'export', 'convert_source'], api_version=API_VERSION,
                    read_note=message_text('msg.trusted_community_python_plugin_isolated_process_and_timeout_not_a_security_sandbox'),
                    write_note=message_text('msg.initial_community_plugins_are_read_and_conversion_sources_only_no_native_storage_or_writes'))

    def available(self):
        return bool(self.info().get('available'))

    def discover(self):
        rows = _invoke(self.name, 'discover')
        if not isinstance(rows, list) or len(rows) > 100000:
            raise ValueError(message_text('err.plugin_session_list_is_invalid_or_too_large'))
        for row in rows:
            row = dict(row, source=self.name)
            yield SessionInfo(**{key:row[key] for key in SessionInfo.__dataclass_fields__ if key in row})

    def read(self, sid):
        conv = _conversation(_invoke(self.name, 'read', sid))
        conv.source = self.name
        return conv

    def write(self, conv, **kwargs):
        raise ValueError(message_text('err.community_plugins_do_not_support_writes_yet_select_a_writable_built_in_target'))


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
            raise ValueError(message_text('err.plugin_file_is_too_large'))
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != spec['sha256']:
            raise ValueError(message_text('err.plugin_file_has_changed_review_it_and_enable_it_again'))
        # Execute the exact bytes verified above; never reopen changed code.
        module_spec = importlib.util.spec_from_file_location('agentrelay_community', path)
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_spec.name] = module
        import contextlib
        with contextlib.redirect_stdout(sys.stderr):
            exec(compile(raw, str(path), 'exec'), module.__dict__)
            adapter = module.Adapter()
            if adapter.name != spec['name'] or adapter.api_version != API_VERSION:
                raise ValueError(message_text('err.plugin_name_or_interface_version_does_not_match'))
            action = request['action']
            if action == 'info':
                data = adapter.info()
                data['api_version'] = adapter.api_version
            elif action == 'discover':
                data = []
                for row in adapter.discover():
                    if len(data) >= 100000:
                        raise ValueError(message_text('err.plugin_list_is_too_large'))
                    data.append(row.to_dict())
            elif action == 'read':
                data = adapter.read(request['id']).to_dict()
            else:
                raise ValueError(message_text('err.unsupported_plugin_operation'))
        encoded = json.dumps({'ok':True, 'data':data}, ensure_ascii=False).encode('utf-8')
        if len(encoded) > MAX_OUTPUT:
            raise ValueError(message_text('err.plugin_response_is_too_large'))
        sys.stdout.buffer.write(encoded)
        return 0
    except Exception as exc:
        print(error_text(exc), file=sys.stderr)
        return 1
