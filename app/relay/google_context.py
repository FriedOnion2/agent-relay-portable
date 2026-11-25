"""Portable, normalized snapshots of the Google sources, restored into Relay."""
import json
import uuid

from . import archive, oplog, registry
from .adapters.google import PORTABLE_FORMAT, decode_context, encode_context
from .messages import text
from .native_import import _exclusive_lock, _inside
from .paths import atomic_write, ensure_directory, iso, validate_session_id
from .session_store import KIND, project_directory

ENTRY = 'root0/context.json'


def collect(adapter, sid, root):
    conv = adapter.read(sid)
    raw = encode_context(conv)
    manifest = {'kind': KIND, 'agent': adapter.name, 'source': adapter.name, 'created_at': iso(),
                'root_count': 1, 'entry': ENTRY,
                'session': {'id': conv.id, 'native_id': conv.id, 'selection_id': sid, 'title': conv.title,
                            'cwd': conv.cwd, 'format': PORTABLE_FORMAT, 'stats': conv.stats()},
                'notes': [text('msg.google_context_restore_note')]}
    path = archive.storage_root(root) / 'conversations' / adapter.name / (uuid.uuid4().hex + '.zip')
    if any(_inside(path, base) for base in adapter.roots):
        raise ValueError(text('err.storage_directory_cannot_be_inside_the_source_agent_data_directory'))
    return path, manifest, {ENTRY: (raw, False)}


def load(data):
    if data.count != 1 or data.entry != ENTRY or set(data.files) != {ENTRY} or data.session.get('format') != PORTABLE_FORMAT:
        raise ValueError(text('err.google_context_format'))
    conv = decode_context(data.files[ENTRY][0], data.agent)
    if conv.id != data.session['id'] or conv.id != data.session.get('native_id'):
        raise ValueError(text('err.session_package_id_does_not_match_the_declared_entry'))
    return conv


def context_home(adapter):
    root = adapter.restored_home
    if (root.is_symlink() or root.parent.is_symlink() or
            any(_inside(root, home) for home in adapter.native_roots)):
        raise ValueError(text('err.google_context_format'))
    return root


def report(data, cwd, session_id):
    from .preview import fingerprint

    adapter = registry.get(data.agent)
    root = context_home(adapter)
    if session_id is not None:
        validate_session_id(session_id)
    if cwd:
        cwd = project_directory(cwd)
    return {'ok': True, 'mode': PORTABLE_FORMAT, 'target': data.agent, 'target_cwd': cwd or '',
            'token': fingerprint({'manifest': data.manifest, 'cwd': cwd or '', 'session_id': session_id,
                                  'destination': str(root)}),
            'blockers': [], 'preserved': [{'item': text('msg.google_context_preserved'),
                                           'count': len(data.google_conversation.turns)}],
            'degraded': [], 'dropped': [], 'unknown': [], 'warnings': [text('msg.google_context_restore_note')]}


def restore(data, package_path, cwd, session_id, token):
    from .preview import check_token

    plan = report(data, cwd, session_id)
    check_token(token, plan['token'])
    adapter = registry.get(data.agent)
    root = context_home(adapter)
    sid = session_id or data.session['id']
    name = validate_session_id(sid)
    destination = root / (name + '.json')
    doc = json.loads(data.files[ENTRY][0])
    doc.update(id=sid, cwd=plan['target_cwd'])
    content = json.dumps(doc, ensure_ascii=False, sort_keys=True).encode('utf-8')
    if len(content) > archive.MAX_FILE:
        raise ValueError(text('err.a_file_exceeds_32_mib'))
    with oplog.track('google-context-restore', [str(root)], source=data.agent, target=data.agent,
                     session=sid, title=data.session.get('title'), path=str(destination)):
        if root.is_symlink():
            raise ValueError(text('err.google_context_format'))
        ensure_directory(root)
        with _exclusive_lock(root / '.restore.publish-lock'):
            if any(row.id == sid for row in adapter.discover() if row.readable):
                raise FileExistsError(text('msg.backup_exists'))
            atomic_write(str(destination), [content], encoding=None, overwrite=False)
    return {'ok': True, 'mode': PORTABLE_FORMAT, 'target_os': 'AgentRelay',
            'from': {'source': data.agent, 'path': str(package_path)},
            'to': {'source': data.agent, 'id': sid, 'native_id': sid, 'path': str(destination), 'cwd': doc['cwd']},
            'stats': data.google_conversation.stats(), 'notes': [text('msg.google_context_restore_note')], 'preview': plan}
