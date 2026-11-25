"""Portable, normalized snapshots of the Google sources, restored into Relay."""
import json
import uuid
from pathlib import Path

from . import archive, oplog, registry
from .adapters.google import BLOCK_FIELDS, BLOCK_KINDS, PORTABLE_FORMAT, decode_context
from .messages import text
from .native_import import _exclusive_lock, _inside
from .paths import atomic_write, ensure_directory, iso, validate_session_id
from .session_store import KIND, project_directory

ENTRY = 'root0/context.json'


def collect(adapter, sid, root):
    conv = adapter.read(sid)
    doc = {key: value for key, value in conv.to_dict().items() if key not in ('meta', 'truncated')}
    doc['format'] = PORTABLE_FORMAT
    turns = []
    for turn in doc['turns']:
        turn['blocks'] = [{key: value for key, value in block.items() if key in BLOCK_FIELDS}
                          for block in turn['blocks'] if block['kind'] in BLOCK_KINDS]
        if turn['blocks']:
            turns.append(turn)
    doc['turns'] = turns
    raw = json.dumps(doc, ensure_ascii=False, sort_keys=True).encode('utf-8')
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


def report(data, cwd, session_id):
    from .preview import fingerprint

    adapter = registry.get(data.agent)
    root = adapter.restored_home
    if root.is_symlink() or root.parent.is_symlink() or _inside(root, adapter.home):
        raise ValueError(text('err.google_context_format'))
    if session_id is not None:
        validate_session_id(session_id)
    if cwd:
        cwd = project_directory(cwd)
    return {'ok': True, 'mode': PORTABLE_FORMAT, 'target': data.agent, 'target_cwd': cwd or '',
            'token': fingerprint({'manifest': data.manifest, 'cwd': cwd or '', 'session_id': session_id,
                                  'destination': str(adapter.restored_home)}),
            'blockers': [], 'preserved': [{'item': text('msg.google_context_preserved'),
                                           'count': len(data.google_conversation.turns)}],
            'degraded': [], 'dropped': [], 'unknown': [], 'warnings': [text('msg.google_context_restore_note')]}


def restore(data, package_path, cwd, session_id, token):
    from .preview import check_token

    plan = report(data, cwd, session_id)
    check_token(token, plan['token'])
    adapter = registry.get(data.agent)
    root = adapter.restored_home
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
            'from': {'source': data.agent, 'path': str(Path(package_path).resolve())},
            'to': {'source': data.agent, 'id': sid, 'native_id': sid, 'path': str(destination), 'cwd': doc['cwd']},
            'stats': data.google_conversation.stats(), 'notes': [text('msg.google_context_restore_note')], 'preview': plan}
