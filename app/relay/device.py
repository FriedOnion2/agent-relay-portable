"""Device-local overrides beside portable data, never implicit plugin trust."""

from .messages import text as message_text, error_text
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import sys
import importlib.util
from pathlib import Path

from .runtime import project_root

warnings: list = []
blocked_homes: dict = {}


def identity():
    machine = platform.node()
    try:
        if platform.system() == 'Windows':
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography',
                                access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                machine = str(winreg.QueryValueEx(key, 'MachineGuid')[0])
        elif platform.system() == 'Linux':
            machine = Path('/etc/machine-id').read_text(encoding='ascii').strip() or machine
        elif platform.system() == 'Darwin':
            import re
            result = subprocess.run(['/usr/sbin/ioreg','-rd1','-c','IOPlatformExpertDevice'],
                                    capture_output=True, text=True, timeout=3, check=True)
            match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.stdout)
            if match:
                machine = match.group(1)
    except (ImportError, OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        user = str(Path.home())
    except RuntimeError:
        user = os.environ.get('USERNAME') or os.environ.get('USER') or str(getattr(os, 'getuid', lambda: '')())
    value = '\0'.join((platform.system(), machine, user))
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]


def config_path():
    return project_root() / 'devices' / (identity() + '.json')


def read():
    path = config_path()
    if not path.exists():
        return {}
    if path.stat().st_size > 1024 * 1024:
        raise ValueError(message_text('msg.the_device_config_is_too_large'))
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict) or not isinstance(value.get('agent_homes', {}), dict):
        raise ValueError(message_text('msg.the_device_config_and_agent_homes_must_be_objects'))
    for home in value.get('agent_homes', {}).values():
        if not isinstance(home, str):
            raise ValueError(message_text('msg.agent_directories_must_be_strings'))
    for key in ('windows_user_home', 'ubuntu_user_home'):
        if key in value and not isinstance(value[key], str):
            raise ValueError(message_text('msg.user_directories_must_be_strings'))
    if not isinstance(value.get('plugins', []), list):
        raise ValueError(message_text('msg.plugins_must_be_a_list'))
    return value


def write(value):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.device-', suffix='.partial', dir=str(path.parent))
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def merge(shared, local=None):
    warnings.clear()
    blocked_homes.clear()
    result = dict(shared)
    result['agent_homes'] = dict(shared.get('agent_homes') or {})
    local = read() if local is None else local
    result['agent_homes'].update(local.get('agent_homes', {}))
    for key in ('windows_user_home', 'ubuntu_user_home'):
        if key in local:
            result[key] = local[key]
    for key, value in result['agent_homes'].items():
        if key.startswith('_'):
            continue
        value = value.strip()
        result['agent_homes'][key] = value
        if not value:
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = project_root() / path
        result['agent_homes'][key] = str(path)
        if not path.is_dir():
            message = message_text('msg.configured_key_directory_is_inaccessible_path_select_it_again_in_environment_compatibility', key=key, path=path)
            warnings.append(message)
            blocked_homes[key] = message
    profile_key = 'windows_user_home' if platform.system() == 'Linux' else 'ubuntu_user_home' if platform.system() == 'Windows' else None
    profile = (result.get(profile_key) or '').strip() if profile_key else ''
    if profile:
        path = Path(profile).expanduser()
        if not path.is_absolute():
            warnings.append(message_text('msg.profile_key_is_not_a_local_absolute_path_select_it_again_with_windows_use_ubuntu_use', profile_key=profile_key))
            result[profile_key] = ''
        elif not path.is_dir():
            warnings.append(message_text('msg.cross_system_user_directory_is_inaccessible_check_the_mount_or_select_it_again_value', value=str(path)))
    # Plugin approvals are valid only on the device that enabled them.
    result['plugins'] = local.get('plugins', [])
    return result


def set_home(agent, home):
    from .locations import SOURCES
    if agent not in SOURCES:
        raise ValueError(message_text('msg.choose_a_built_in_agent'))
    if home:
        path = Path(home).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise ValueError(message_text('msg.choose_an_absolute_directory_that_exists_on_this_device_leave_blank_to_auto_dete'))
        home = str(path.resolve())
    value = read()
    value.setdefault('agent_homes', {})[agent] = home or ''
    return str(write(value))


def environment():
    root = project_root()
    writable = False
    error = ''
    try:
        handle, path = tempfile.mkstemp(prefix='.relay-probe-', dir=str(root))
        os.close(handle)
        os.unlink(path)
        writable = True
    except OSError as exc:
        error = error_text(exc)
    try:
        free = shutil.disk_usage(root).free
    except OSError:
        free = None
    fts5 = False
    sqlite_version = None
    try:
        import sqlite3
        database = sqlite3.connect(':memory:')
        try:
            database.execute('CREATE VIRTUAL TABLE probe USING fts5(text)')
            fts5 = True
            sqlite_version = sqlite3.sqlite_version
        finally:
            database.close()
    except (ImportError, RuntimeError) as exc:
        error = error or error_text(exc)
    except Exception as exc:
        error = error or message_text('err.sqlite_fts5_failed', detail=error_text(exc))
    return {'device_id': identity(), 'system': platform.system(), 'architecture': platform.machine(),
            'data_root': str(root), 'config_path': str(config_path()), 'writable': writable,
            'runtime': {'bundled':bool(getattr(sys, 'frozen', False)),
                        'python':platform.python_version(), 'executable':sys.executable,
                        'directory':str(Path(sys.executable).resolve().parent),
                        'zstandard':importlib.util.find_spec('zstandard') is not None,
                        'sqlite':sqlite_version, 'fts5':fts5,
                        'checksum':message_text('msg.the_bundle_launcher_checks_the_runtime_archive_sha_256_on_every_start_this_panel')},
            'free_bytes': free, 'write_error': error, 'warnings': list(warnings),
            'note': message_text('msg.a_new_device_uses_its_own_host_directories_by_default_local_overrides_are_stored')}
