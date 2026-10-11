"""Import and carry Yuanbao JSON exports without touching the Yuanbao client."""
import hashlib
import uuid
from pathlib import Path

from . import archive, oplog, registry
from .adapters.yuanbao import FORMAT, conversation, decode, encode, normalize
from .messages import text
from .native_import import _exclusive_lock, _inside
from .paths import iso, atomic_write


def _publish(adapter, rows, reject_ids=False):
    home = Path(adapter.home)
    if home.exists() and archive.is_link(home):
        raise ValueError(text('err.yuanbao_export_directory'))
    raw_files = {hashlib.sha256(raw).hexdigest() + '.json': raw for raw in map(encode, rows)}
    if any(len(raw) > archive.MAX_FILE for raw in raw_files.values()):
        raise ValueError(text('err.a_file_exceeds_32_mib'))
    home.mkdir(parents=True, exist_ok=True)
    created = []
    with _exclusive_lock(home / '.yuanbao.publish-lock'):
        if reject_ids:
            existing = {row.native_id for row in adapter.discover()}
            if existing.intersection(row['id'] for row in rows):
                raise FileExistsError(text('err.yuanbao_id_exists'))
        pending = []
        for name, raw in raw_files.items():
            path = home / name
            if path.exists() or path.is_symlink():
                if archive.read_file(path) != raw:
                    raise FileExistsError(text('err.yuanbao_id_exists'))
            else:
                pending.append((name, raw))
        try:
            for name, raw in pending:
                destination = home / name
                atomic_write(str(destination), [raw], encoding=None, overwrite=False)
                created.append(destination)
        except BaseException:
            for path in reversed(created):
                path.unlink()
            raise
    return {'imported': len(created), 'skipped': len(raw_files) - len(created),
            'paths': [str(home / name) for name in raw_files]}


def import_file(path):
    if not isinstance(path, str) or not Path(path).expanduser().is_absolute():
        raise ValueError(text('err.yuanbao_input_path'))
    source = Path(path).expanduser()
    if source.suffix.lower() != '.json':
        raise ValueError(text('err.yuanbao_invalid_export'))
    rows = decode(archive.read_file(source))
    adapter = registry.get('yuanbao')
    with oplog.track('yuanbao-export-import', [adapter.home], source='yuanbao', target='yuanbao') as record:
        result = _publish(adapter, rows)
        record['path'] = adapter.home
    return dict(result, ok=True, home=adapter.home, notes=[text('msg.yuanbao_export_limits')])


def store(adapter, sid, root):
    conv = adapter.read(sid)
    raw = encode(conv.meta['export'])
    path = archive.storage_root(root) / 'conversations' / 'yuanbao' / (uuid.uuid4().hex + '.zip')
    if _inside(path, Path(adapter.root).resolve()):
        raise ValueError(text('err.storage_directory_cannot_be_inside_the_source_agent_data_directory'))
    manifest = {'kind': 'agentrelay-session', 'agent': 'yuanbao', 'source': 'yuanbao',
                'created_at': iso(), 'root_count': 1, 'entry': 'root0/session.json',
                'session': {'id': conv.id, 'native_id': conv.id, 'selection_id': sid,
                            'title': conv.title, 'cwd': conv.cwd, 'format': FORMAT, 'stats': conv.stats()},
                'notes': [text('msg.yuanbao_export_package')]}
    return archive.write_package(path, manifest, {'root0/session.json': (raw, False)})


def package_data(path):
    manifest, files = archive.read_package(path, 'agentrelay-session')
    session = manifest.get('session')
    if (manifest.get('agent') != 'yuanbao' or type(manifest.get('root_count')) is not int
            or manifest['root_count'] != 1 or manifest.get('entry') != 'root0/session.json'
            or set(files) != {'root0/session.json'} or not isinstance(session, dict)
            or session.get('format') != FORMAT):
        raise ValueError(text('msg.invalid_session_package_metadata'))
    rows = decode(files['root0/session.json'][0])
    if len(rows) != 1 or session.get('id') != rows[0]['id'] or session.get('native_id') != rows[0]['id']:
        raise ValueError(text('err.session_package_id_does_not_match_the_declared_entry'))
    return manifest, rows[0]


def package_preview(path, cwd, session_id=None, dsh_compression='zstd'):
    manifest, row = package_data(path)
    return _package_preview(manifest, row, cwd, session_id, dsh_compression)


def _package_preview(manifest, row, cwd, session_id, dsh_compression):
    from .preview import fingerprint
    if not isinstance(cwd, str) or not cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
        raise ValueError(text('msg.restoring_needs_an_absolute_project_directory_that_exists_on_this_device'))
    if session_id is not None:
        normalize(dict(row, id=session_id))
    options = dict(cwd=cwd, session_id=session_id, dsh_compression=dsh_compression)
    return {'ok': True, 'mode': FORMAT, 'target': 'yuanbao', 'target_cwd': cwd,
            'token': fingerprint({'manifest': manifest, 'options': options, 'destination': registry.get('yuanbao').home}),
            'blockers': [], 'preserved': [{'item': text('msg.yuanbao_export_content'), 'count': len(row['messages'])}],
            'degraded': [], 'dropped': [], 'unknown': [], 'warnings': [text('msg.yuanbao_export_package')]}


def restore(path, cwd, session_id=None, dsh_compression='zstd', preview_token=None):
    from .preview import check_token
    manifest, row = package_data(path)
    plan = _package_preview(manifest, row, cwd, session_id, dsh_compression)
    check_token(preview_token, plan['token'])
    row['cwd'] = str(Path(cwd).resolve())
    if session_id is not None:
        row['id'] = session_id
    adapter = registry.get('yuanbao')
    conv = conversation(row)
    with oplog.track('yuanbao-export-restore', [adapter.home], source='yuanbao', target='yuanbao',
                     session=conv.id, title=conv.title) as record:
        result = _publish(adapter, [row], reject_ids=True)
        record['path'] = result['paths'][0]
    sid = adapter._prefix(result['paths'][0]) + '0'
    return {'ok': True, 'mode': FORMAT, 'target_os': 'AgentRelay',
            'from': {'source': 'yuanbao', 'path': str(Path(path).resolve())},
            'to': {'source': 'yuanbao', 'id': sid, 'native_id': conv.id, 'path': result['paths'][0], 'cwd': row['cwd']},
            'stats': conv.stats(), 'notes': [text('msg.yuanbao_export_package')], 'preview': plan}
