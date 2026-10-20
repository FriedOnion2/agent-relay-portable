"""Portable multi-agent backups built from the existing verified native packages."""
import hashlib
import re
import tempfile
import uuid
from pathlib import Path

from . import archive, preview, registry, session_store, skill_store
from .messages import text as message_text, error_text
from .paths import iso

KIND = 'agentrelay-backup'
READING_KIND = 'agentrelay-reading'
MODES = ('all', 'sessions', 'markdown')
MAX_UPLOAD = archive.MAX_TOTAL + archive.MAX_MANIFEST + 4 * 1024 * 1024


def _fail(code):
    raise ValueError(message_text('msg.backup_' + code))


def _notify(progress, processed, errors):
    if progress:
        progress({'processed': processed, 'errors': list(errors)})


def export(mode='all', agents=None, include_thinking=True, progress=None, cancel=None, lang='zh'):
    if mode not in MODES or type(include_thinking) is not bool:
        _fail('invalid_options')
    agents = list(registry._ADAPTERS) if agents is None else agents
    if (not isinstance(agents, list) or not agents or
            any(not isinstance(a, str) or a not in registry._ADAPTERS for a in agents)):
        _fail('invalid_agents')
    files, items, errors, seen = {}, [], [], set()
    total = 0
    with tempfile.TemporaryDirectory(prefix='relay-backup-') as temporary:
        def add(agent, kind, source):
            nonlocal total
            identity = (kind, str(Path(source.path if kind == 'session' else source).resolve()))
            if identity in seen:
                return
            key = uuid.uuid4().hex
            if mode == 'markdown':
                if registry.get(agent).read(source.id).truncated:
                    _fail('incomplete')
                text = registry.export_markdown(agent, source.id, include_thinking=include_thinking, lang=lang)
                content = {'conversations/%s/%s.md' % (agent, key): (text.encode('utf-8'), False)}
                item = {'key': key, 'agent': agent, 'title': source.title, 'id': source.id}
            else:
                result = (session_store.store_session(agent, source.id, temporary) if kind == 'session'
                          else skill_store.store_skill(agent, source, temporary))
                package = Path(result['path'])
                metadata, native = archive.read_package(package)
                package.unlink()
                content = {'items/%s/%s' % (key, name): data for name, data in native.items()}
                item = {'key': key, 'manifest': metadata}
            size = sum(len(data) for data, executable in content.values())
            if (any(len(data) > archive.MAX_FILE for data, executable in content.values()) or
                    total + size > archive.MAX_TOTAL or len(files) + len(content) > archive.MAX_FILES):
                _fail('limit')
            files.update(content)
            total += size
            items.append(item)
            seen.add(identity)
            _notify(progress, len(items), errors)

        for agent in dict.fromkeys(agents):
            if cancel and cancel.is_set():
                return {'ok': False, 'canceled': True, 'processed': len(items), 'errors': errors}
            try:
                source = registry.get(agent)
                for row in source.discover():
                    if cancel and cancel.is_set():
                        return {'ok': False, 'canceled': True, 'processed': len(items), 'errors': errors}
                    try:
                        add(agent, 'session', row)
                    except (OSError, ValueError, KeyError) as exc:
                        # Capacity errors abort instead of labelling a truncated
                        # archive as a complete backup.
                        if exc.args and getattr(exc.args[0], 'code', '') == 'msg.backup_limit':
                            raise
                        errors.append({'agent': agent, 'id': row.id, 'error': error_text(exc)})
                if mode == 'all' and agent != 'yuanbao':
                    discovered = skill_store.discover_skills(agent)
                    errors.extend(dict(row, agent=agent) for row in discovered['errors'])
                    for row in discovered['skills']:
                        if cancel and cancel.is_set():
                            return {'ok': False, 'canceled': True, 'processed': len(items), 'errors': errors}
                        try:
                            add(agent, 'skill', row['path'])
                        except (OSError, ValueError, KeyError) as exc:
                            if exc.args and getattr(exc.args[0], 'code', '') == 'msg.backup_limit':
                                raise
                            errors.append({'agent': agent, 'path': row['path'], 'error': error_text(exc)})
            except (OSError, ValueError, KeyError) as exc:
                if exc.args and getattr(exc.args[0], 'code', '') == 'msg.backup_limit':
                    raise
                errors.append({'agent': agent, 'error': error_text(exc)})
        if not items:
            return {'ok': False, 'processed': 0, 'errors': errors, 'empty': True}
        if cancel and cancel.is_set():
            return {'ok': False, 'canceled': True, 'processed': len(items), 'errors': errors}
        key = uuid.uuid4().hex
        result = archive.write_package(archive.storage_root() / 'backups' / (key + '.zip'),
                                       {'kind': READING_KIND if mode == 'markdown' else KIND,
                                        'mode': mode, 'created_at': iso(), 'items': items, 'errors': errors}, files)
        return {'ok': not errors, 'id': key, 'path': result['path'], 'processed': len(items), 'errors': errors,
                'download': '/api/backup-download?id=' + key}


def download_path(key):
    if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{32}', key):
        _fail('invalid_package')
    # Resolve an existing server-owned entry, never construct a path from HTTP input.
    for path in (archive.storage_root() / 'backups').iterdir():
        if path.name == key + '.zip':
            if archive.is_link(path) or not path.is_file():
                _fail('invalid_package')
            return path
    raise FileNotFoundError(message_text('msg.backup_invalid_package'))


def receive(stream, length):
    if type(length) is not int or not 0 < length <= MAX_UPLOAD:
        _fail('limit')
    key = uuid.uuid4().hex
    root = archive.storage_root() / 'backups'
    root.mkdir(parents=True, exist_ok=True)
    path = root / (key + '.zip')
    try:
        with path.open('xb') as output:
            remaining = length
            while remaining:
                data = stream.read(min(1024 * 1024, remaining))
                if not data:
                    _fail('invalid_package')
                output.write(data)
                remaining -= len(data)
        summary = inspect(path)
        return dict(summary, path=str(path), id=key)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _read(package):
    manifest, files = archive.read_package(package)
    if manifest.get('kind') == READING_KIND:
        _fail('reading_only')
    items = manifest.get('items')
    if manifest.get('kind') != KIND or manifest.get('mode') not in ('all', 'sessions') or not isinstance(items, list) or not items:
        _fail('invalid_package')
    used, keys = set(), set()
    for item in items:
        if not isinstance(item, dict):
            _fail('invalid_package')
        key, inner = item.get('key'), item.get('manifest')
        if (not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{32}', key) or key in keys or
                not isinstance(inner, dict) or type(inner.get('version')) is not int or inner['version'] != 1 or
                inner.get('kind') not in (session_store.KIND, skill_store.KIND) or
                not isinstance(inner.get('agent'), str) or inner['agent'] not in registry._ADAPTERS):
            _fail('invalid_package')
        keys.add(key)
        rows = inner.get('files')
        if not isinstance(rows, list) or not rows:
            _fail('invalid_package')
        for row in rows:
            if not isinstance(row, dict):
                _fail('invalid_package')
            name = 'items/%s/%s' % (key, archive.safe_name(row.get('path')))
            if name not in files or name in used:
                _fail('invalid_package')
            data, executable = files[name]
            if (type(row.get('size')) is not int or row['size'] != len(data) or
                    row.get('sha256') != hashlib.sha256(data).hexdigest() or
                    type(row.get('executable')) is not bool or row['executable'] != executable):
                _fail('invalid_package')
            used.add(name)
        field = 'session' if inner['kind'] == session_store.KIND else 'skill'
        if not isinstance(inner.get(field), dict) or not isinstance(inner[field].get('id' if field == 'session' else 'name'), str):
            _fail('invalid_package')
        if field == 'session' and any(inner[field].get(name) is not None and not isinstance(inner[field][name], str)
                                      for name in ('cwd', 'title', 'native_id')):
            _fail('invalid_package')
        if field == 'skill' and ('skill/SKILL.md' not in {row['path'] for row in rows} or
                                any(not row['path'].startswith('skill/') for row in rows)):
            _fail('invalid_package')
        if manifest['mode'] == 'sessions' and field != 'session':
            _fail('invalid_package')
    if used != set(files):
        _fail('invalid_package')
    if not isinstance(manifest.get('errors', []), list) or any(not isinstance(row, dict) for row in manifest.get('errors', [])):
        _fail('invalid_package')
    return manifest, files


def inspect(package):
    manifest, _ = _read(package)
    projects, skills = set(), set()
    for item in manifest['items']:
        inner = item['manifest']
        if inner['kind'] == session_store.KIND:
            projects.add(inner['session'].get('cwd') or '')
        else:
            skills.add(inner['agent'])
    return {'ok': True, 'count': len(manifest['items']), 'mode': manifest['mode'],
            'projects': sorted(projects), 'skill_agents': sorted(skills), 'errors': manifest.get('errors', [])}


def _options(options):
    options = {} if options is None else options
    if not isinstance(options, dict) or set(options) - {'projects', 'skills', 'conflict'}:
        _fail('invalid_options')
    for key in ('projects', 'skills'):
        value = options.get(key, {})
        if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
            _fail('invalid_options')
    if options.get('conflict', 'skip') not in ('skip', 'copy'):
        _fail('invalid_options')
    return options


def _materialize(item, files, root):
    prefix = 'items/' + item['key'] + '/'
    native = {name[len(prefix):]: value for name, value in files.items() if name.startswith(prefix)}
    package = Path(root) / (item['key'] + '.zip')
    archive.write_package(package, item['manifest'], native)
    return package


def _plan(manifest, files, options):
    options = _options(options)
    rows, targets, existing = [], {}, {}
    with tempfile.TemporaryDirectory(prefix='relay-backup-preview-') as temporary:
        for item in manifest['items']:
            inner, key = item['manifest'], item['key']
            agent = inner['agent']
            is_session = inner['kind'] == session_store.KIND
            row = {'key': key, 'agent': agent, 'kind': 'session' if is_session else 'skill', 'status': 'ready'}
            try:
                target = registry.get(agent)
                targets[agent] = target.home
                if is_session:
                    session = inner['session']
                    row.update(title=session.get('title') or session['id'], original_cwd=session.get('cwd') or '')
                    row['cwd'] = options.get('projects', {}).get(row['original_cwd'], row['original_cwd'])
                    if options.get('conflict') == 'copy':
                        row['session_id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, preview.fingerprint(manifest) + key + target.home))
                    else:
                        row['session_id'] = None
                    if agent == 'dsh':
                        from .adapters.dsh import read_records
                        entry = archive.safe_name(inner.get('entry'))
                        data, _ = files['items/%s/%s' % (key, entry)]
                        path = Path(temporary) / (uuid.uuid4().hex + ('.zstd' if entry.endswith('.zstd') else '.jsonl'))
                        path.write_bytes(data)
                        header = read_records(str(path))[0]
                        row.update(native_id=header['id'], parent=header.get('parentSession'), origin=header.get('origin'))
                    if agent not in existing:
                        existing[agent] = ({target.read(r.id).meta['header']['id'] for r in target.discover() if r.readable}
                                           if agent == 'dsh' else {r.id.split('@', 1)[0] for r in target.discover()})
                    sid = row['session_id'] or row.get('native_id') or session.get('native_id') or session['id']
                    if sid in existing[agent] or (session['id'] in existing[agent] and not row['session_id']):
                        row['status'] = 'skip'
                        row['reason'] = message_text('msg.backup_exists')
                    else:
                        if not Path(row['cwd']).is_absolute() or not Path(row['cwd']).is_dir():
                            _fail('project_required')
                        package = _materialize(item, files, temporary)
                        preview.package(package, row['cwd'], row['session_id'], 'none')
                        existing[agent].add(sid)
                else:
                    row['title'] = inner['skill']['name']
                    row['skills_dir'] = options.get('skills', {}).get(agent) or None
                    root = skill_store.skill_roots(agent, row['skills_dir'])[0]
                    row['name'] = skill_store.skill_name(row['title'] + ('-' + key[:8] if options.get('conflict') == 'copy' else ''))
                    row['destination'] = str(root / row['name'])
                    if Path(row['destination']).exists() or Path(row['destination']).is_symlink():
                        row['status'] = 'skip'
                        row['reason'] = message_text('msg.backup_exists')
            except (OSError, ValueError, KeyError) as exc:
                row.update(status='blocked', reason=error_text(exc))
            rows.append(row)
        rows = _order_dsh(rows, options)
    return {'ok': True, 'rows': rows, 'errors': manifest.get('errors', []),
            'token': preview.fingerprint({'manifest': manifest, 'options': options, 'targets': targets, 'rows': rows}),
            **{name: sum(row['status'] == name for row in rows) for name in ('ready', 'skip', 'blocked')}}


def _order_dsh(rows, options):
    """Read dependencies from verified payloads; restore parents before children."""
    pending, ordered = [], []
    for row in rows:
        if row['agent'] != 'dsh' or row['kind'] != 'session' or row['status'] != 'ready':
            ordered.append(row)
            continue
        try:
            if (row['origin'] == 'subagent' or
                    (row['parent'] and options.get('conflict') == 'copy')):
                _fail('dsh_dependency')
            pending.append(row)
        except (OSError, ValueError, KeyError) as exc:
            row.update(status='blocked', reason=error_text(exc))
            ordered.append(row)
    if not pending:
        return ordered
    target = registry.get('dsh')
    available = {target.read(r.id).meta['header']['id'] for r in target.discover() if r.readable}
    while pending:
        ready = [row for row in pending if not row['parent'] or row['parent'] in available]
        if not ready:
            for row in pending:
                row.update(status='blocked', reason=message_text('msg.backup_dsh_dependency'))
            ordered.extend(pending)
            break
        for row in ready:
            ordered.append(row)
            pending.remove(row)
            if not row['session_id']:
                available.add(row['native_id'])
    return ordered


def plan(package, options=None):
    manifest, files = _read(package)
    return _plan(manifest, files, options)


def restore(package, options=None, preview_token=None, progress=None, cancel=None):
    manifest, files = _read(package)
    report = _plan(manifest, files, options)
    if not preview_token:
        _fail('confirm')
    preview.check_token(preview_token, report['token'])
    if report['blocked']:
        _fail('blocked')
    results, skipped, errors = [], [], []
    with tempfile.TemporaryDirectory(prefix='relay-backup-import-') as temporary:
        items = {item['key']: item for item in manifest['items']}
        for row in report['rows']:
            if cancel and cancel.is_set():
                return {'ok': False, 'canceled': True, 'restored': results, 'skipped': skipped, 'errors': errors}
            if row['status'] == 'skip':
                skipped.append(row)
                continue
            try:
                path = _materialize(items[row['key']], files, temporary)
                result = (session_store.restore_session(path, row['cwd'], row['session_id'], 'none')
                          if row['kind'] == 'session' else
                          skill_store.restore_skill(path, row['agent'], row['skills_dir'], row['name']))
                results.append({'key': row['key'], 'agent': row['agent'], 'title': row['title'], 'result': result})
            except (OSError, ValueError, KeyError) as exc:
                errors.append({'key': row['key'], 'agent': row['agent'], 'title': row['title'], 'error': error_text(exc)})
            _notify(progress, len(results) + len(skipped) + len(errors), errors)
    return {'ok': not errors, 'restored': results, 'skipped': skipped, 'errors': errors}
