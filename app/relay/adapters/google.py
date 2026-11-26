"""Gemini CLI recordings and readable Antigravity artifacts."""
import hashlib
import json
import os
from pathlib import Path

from .. import archive, ir
from ..locations import resolve_home
from ..messages import error_text, text
from ..paths import is_windows_path, safe_ms, validate_session_id
from ..runtime import project_root
from .base import ReadOnlyAdapter, SessionInfo

PORTABLE_FORMAT = 'relay-google-context-v1'
BLOCK_FIELDS = {'kind', 'text', 'call_id', 'name', 'arguments', 'output', 'is_error', 'media_type'}
BLOCK_KINDS = {ir.TEXT, ir.THINKING, ir.TOOL_CALL, ir.TOOL_RESULT, ir.IMAGE}


def _invalid():
    return ValueError(text('err.google_context_format'))


def _string(value):
    return value if isinstance(value, str) else ''


def portable_home(agent):
    return project_root() / 'imports' / agent


def encode_context(conv):
    if conv.truncated:
        raise ValueError(text('err.source_session_is_incomplete_cannot_save_a_native_storage_package'))
    doc = {key: value for key, value in conv.to_dict().items() if key not in ('meta', 'truncated')}
    doc['format'] = PORTABLE_FORMAT
    turns = []
    for turn in doc['turns']:
        turn['blocks'] = [{key: value for key, value in block.items() if key in BLOCK_FIELDS}
                          for block in turn['blocks'] if block['kind'] in BLOCK_KINDS]
        if turn['blocks']:
            turns.append(turn)
    doc['turns'] = turns
    return json.dumps(doc, ensure_ascii=False, sort_keys=True).encode('utf-8')


def decode_context(raw, agent, path=''):
    doc = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(doc, dict) or doc.get('format') != PORTABLE_FORMAT or doc.get('source') != agent:
        raise _invalid()
    keys = ('id', 'title', 'cwd', 'model', 'created_at', 'updated_at')
    validate_session_id(doc.get('id'))
    if (any(not isinstance(doc.get(key), (str, type(None))) for key in keys) or
            not isinstance(doc.get('turns'), list) or not doc['turns']):
        raise _invalid()
    conv = ir.Conversation(source=agent, path=path, **{key: _string(doc.get(key)) for key in keys})
    for turn in doc['turns']:
        if (not isinstance(turn, dict) or turn.get('role') not in (ir.USER, ir.ASSISTANT, ir.SYSTEM) or
                not isinstance(turn.get('blocks'), list) or not turn['blocks']):
            raise _invalid()
        blocks = []
        for block in turn['blocks']:
            if (not isinstance(block, dict) or set(block) - BLOCK_FIELDS or _string(block.get('kind')) not in BLOCK_KINDS or
                    any(type(value) is not (bool if key == 'is_error' else str) for key, value in block.items())):
                raise _invalid()
            blocks.append(ir.Block(**block))
        conv.turns.append(ir.Turn(turn['role'], blocks, ts=_string(turn.get('ts')), model=_string(turn.get('model'))))
    return conv


def _records(raw, suffix):
    data = raw.decode('utf-8-sig')
    if suffix == '.json':
        document = json.loads(data)
        if not isinstance(document, dict) or not isinstance(document.get('messages'), list):
            raise _invalid()
        return document, document['messages']
    metadata, messages = {}, {}

    def add(record):
        if not isinstance(record, dict) or not _string(record.get('id')) or 'type' not in record:
            raise _invalid()
        messages[record['id']] = record

    def patch(update):
        if not isinstance(update, dict):
            raise _invalid()
        current = messages.get(_string(update.get('id')))
        if current is None:
            return
        if 'content' in update:
            current['content'] = update['content']
        tool_map = {t['id']: t for t in current.get('toolCalls', []) if isinstance(t, dict) and _string(t.get('id'))}
        for tool in update.get('toolCalls', []):
            if isinstance(tool, dict) and _string(tool.get('id')) in tool_map and 'result' in tool:
                tool_map[tool['id']]['result'] = tool['result']

    for line in data.split('\n'):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise _invalid()
        if '$rewindTo' in record:
            target = record['$rewindTo']
            found = False
            for key in list(messages):
                found |= key == target
                if found:
                    del messages[key]
            if not found:
                messages.clear()
        elif '$patch' in record:
            changes = record['$patch']
            if not isinstance(changes, dict):
                raise _invalid()
            patch(changes)
            for update in changes.get('updates', []):
                patch(update)
            for key in changes.get('removeIds', []):
                messages.pop(key, None)
            for key in changes.get('orderIds', []):
                if key in messages:
                    messages[key] = messages.pop(key)
        elif '$set' in record or ('sessionId' in record and 'projectHash' in record):
            fields = record.get('$set', record)
            if not isinstance(fields, dict):
                raise _invalid()
            if 'messages' in fields:
                if '$set' in record:
                    messages.clear()
                for msg in fields['messages']:
                    add(msg)
            metadata.update((key, value) for key, value in fields.items() if key != 'messages')
        else:
            add(record)
    return metadata, list(messages.values())


def _parts(content):
    if isinstance(content, str):
        yield ir.Block.text_block(content)
    elif isinstance(content, list):
        for part in content:
            yield from _parts(part)
    elif isinstance(content, dict):
        value = _string(content.get('text'))
        if value:
            yield ir.Block.thinking_block(value) if content.get('thought') else ir.Block.text_block(value)
        elif isinstance(content.get('inlineData'), dict):
            mime = _string(content['inlineData'].get('mimeType'))
            if mime.startswith('image/'):
                yield ir.Block(ir.IMAGE, media_type=mime)


def gemini_conversation(raw, path, identity):
    doc, messages = _records(raw, Path(path).suffix)
    if not _string(doc.get('sessionId')) or not _string(doc.get('projectHash')):
        raise _invalid()
    conv = ir.Conversation(source='gemini', id=identity, path=str(path),
                           title=_string(doc.get('summary')), cwd=_string(doc.get('cwd')),
                           created_at=_string(doc.get('startTime')), updated_at=_string(doc.get('lastUpdated')))
    for message in messages:
        if not isinstance(message, dict):
            raise _invalid()
        role = {'user': ir.USER, 'gemini': ir.ASSISTANT, 'info': ir.SYSTEM,
                'warning': ir.SYSTEM, 'error': ir.SYSTEM}.get(_string(message.get('type')))
        if role is None:
            raise _invalid()
        content = message.get('displayContent') or message.get('content')
        blocks = list(_parts(content))
        for thought in message.get('thoughts') or []:
            if isinstance(thought, dict):
                summary = '\n'.join(filter(None, map(_string, (thought.get('subject'), thought.get('description')))))
                if summary:
                    blocks.append(ir.Block.thinking_block(summary))
        for tool in message.get('toolCalls') or []:
            if not isinstance(tool, dict) or not _string(tool.get('id')) or not _string(tool.get('name')):
                raise _invalid()
            blocks.append(ir.Block.tool_call(tool['id'], tool['name'], json.dumps(tool.get('args', {}), ensure_ascii=False)))
            if tool.get('result') is not None:
                output = json.dumps(tool['result'], ensure_ascii=False)
                blocks.append(ir.Block.tool_result(tool['id'], output, tool.get('status') in ('error', 'cancelled')))
        if blocks:
            model = _string(message.get('model'))
            conv.turns.append(ir.Turn(role, blocks, ts=_string(message.get('timestamp')), model=model))
            conv.model = model or conv.model
    conv.title = conv.title or conv.first_user_text() or str(doc['sessionId'])
    if not conv.turns:
        raise _invalid()
    return conv


class GoogleSource(ReadOnlyAdapter):
    cross_system = False
    portable_context = True
    managed_context = False

    def __init__(self, home=None, clean=True, restored_home=None):
        self.home = self.root = resolve_home(self.name, home)
        self.native_roots = [] if self.managed_context else [self.home]
        if self.name == 'antigravity' and not any(str(value or '').strip() for value in
                (home, os.environ.get('RELAY_ANTIGRAVITY_HOME'), os.environ.get('ANTIGRAVITY_HISTORY_HOME'))):
            parent = Path(self.home).parent
            self.native_roots.extend(str(parent / name) for name in ('antigravity-ide', 'antigravity-cli'))
        if restored_home is not None:
            self.restored_home = restored_home
        else:
            self.restored_home = Path(self.home) if self.managed_context else portable_home(self.name)
        self.roots = [*self.native_roots, str(self.restored_home)]
        self._paths = {}

    def available(self):
        return any(Path(root).is_dir() for root in self.roots)

    def info(self):
        return dict(super().info(), capabilities=['read', 'export', 'native_store', 'export_restore'],
                    read_note=text('msg.' + self.name + '_read_note'))

    def _candidates(self):
        if self.restored_home.is_dir():
            for path in self.restored_home.glob('*.json'):
                yield path, self.restored_home, True
        for root in self.native_roots:
            for path in self.native_files(Path(root)):
                yield Path(path), Path(root), False

    def project_for(self, path):
        return ''

    def _read_file(self, path, root, restored):
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError:
            raise _invalid() from None
        raw = archive.read_file(path)
        if restored:
            conv = decode_context(raw, self.name, str(path))
            if path.stem != conv.id:
                raise _invalid()
            return conv
        relative = path.relative_to(root).as_posix()
        if self.name == 'antigravity':
            if path.suffix == '.jsonl':
                relative = path.with_name('transcript.jsonl').relative_to(root).as_posix()
            if root.name in ('antigravity-cli', 'antigravity-ide'):
                relative = root.name + '/' + relative
        identity = 'file-' + hashlib.sha256(relative.encode('utf-8')).hexdigest()
        return self.parse_native(raw, path, identity)

    def _read(self, path, root, restored):
        try:
            return self._read_file(path, root, restored)
        except (ValueError, UnicodeError, TypeError, KeyError, RecursionError):
            raise _invalid() from None

    def discover(self):
        seen = set()
        for path, root, restored in self._candidates():
            stamp = self._stat(str(path))
            def summary(path=path, root=root, restored=restored, stamp=stamp):
                conv = self._read(path, root, restored)
                return SessionInfo(self.name, conv.id, conv.title, conv.cwd, conv.model or '',
                                   safe_ms(conv.created_at), safe_ms(conv.updated_at) or stamp['updated_ms'],
                                   stamp['size'], len(conv.turns), str(path), native_id=conv.id)
            try:
                row = self._cached_summary(str(path), summary)
                if not restored and not row.cwd:
                    row.cwd = self.project_for(path)
                if row.id in seen:
                    continue
                seen.add(row.id)
                self._paths[row.id] = (path, root, restored)
                yield row
            except (OSError, ValueError) as exc:
                yield SessionInfo(self.name, 'unreadable:' + path.name, path.name, '', '', None, stamp['updated_ms'],
                                  stamp['size'], 0, str(path), False, error=error_text(exc))

    def read(self, sid):
        validate_session_id(sid)
        candidate = self._paths.get(sid)
        if candidate is None or not candidate[0].is_file():
            if next((row for row in self.discover() if row.id == sid and row.readable), None) is None:
                raise _invalid()
            candidate = self._paths[sid]
        path, root, restored = candidate
        conv = self._read(path, root, restored)
        if not restored:
            conv.cwd = conv.cwd or self.project_for(path)
        if conv.id != sid:
            raise _invalid()
        return conv


class GeminiAdapter(GoogleSource):
    name = 'gemini'
    label = 'Gemini CLI'

    def native_files(self, root):
        for path in self._iter_files(str(root), 'session-*'):
            candidate = Path(path)
            if 'chats' in candidate.relative_to(root).parts[:-1] and candidate.suffix in ('.json', '.jsonl'):
                yield path

    def project_for(self, path):
        parents = path.relative_to(self.home).parts[:-1]
        marker = Path(self.home).joinpath(*parents[:parents.index('chats')], '.project_root')
        try:
            marker.resolve().relative_to(Path(self.home).resolve())
            if marker.stat().st_size > 8192:
                return ''
            cwd = archive.read_file(marker).decode('utf-8-sig').strip()
            if '\x00' not in cwd and (Path(cwd).is_absolute() or is_windows_path(cwd)):
                return cwd
        except (OSError, ValueError):
            pass
        return ''

    parse_native = staticmethod(gemini_conversation)


class AntigravityAdapter(GoogleSource):
    name = 'antigravity'
    label = 'Google Antigravity'
    ARTIFACTS = {'task.md', 'implementation_plan.md', 'walkthrough.md'}

    def native_files(self, root):
        for logs in sorted((root / 'brain').glob('*/.system_generated/logs')):
            for name in ('transcript_full.jsonl', 'transcript.jsonl'):
                path = logs / name
                if path.is_file():
                    yield str(path)
                    break
        # Files users explicitly put at the configured root or in exports.
        if root.is_dir():
            for path in sorted(root.iterdir()):
                if path.is_file() and path.suffix.lower() in ('.md', '.txt'):
                    yield str(path)
        for path in self._iter_files(str(root / 'exports'), '*'):
            if Path(path).suffix.lower() in ('.md', '.txt'):
                yield path
        for path in self._iter_files(str(root / 'brain'), '*.md'):
            if Path(path).name in self.ARTIFACTS:
                yield path

    @staticmethod
    def parse_native(raw, path, identity):
        if path.suffix == '.jsonl':
            # The full and compact journals describe the same session.
            conv = ir.Conversation(source='antigravity', id=identity, path=str(path),
                meta={'notes': [text('msg.antigravity_transcript_note')]})
            roles = {'USER_INPUT': ir.USER, 'PLANNER_RESPONSE': ir.ASSISTANT}
            for line in raw.decode('utf-8-sig').split('\n'):
                if not line.strip():
                    continue
                step = json.loads(line)
                if not isinstance(step, dict) or not isinstance(step.get('type'), str):
                    raise _invalid()
                role = roles.get(step['type'])
                body = _string(step.get('content'))
                if not role:
                    continue
                if step.get('truncated_fields') and 'content' in step['truncated_fields']:
                    conv.truncated = True
                if role == ir.USER and body.startswith('<USER_REQUEST>'):
                    request, closing, metadata = body[len('<USER_REQUEST>'):].rpartition('</USER_REQUEST>')
                    if closing and (not metadata.strip() or metadata.lstrip().startswith('<ADDITIONAL_METADATA>')):
                        body = request.strip()
                if body:
                    stamp = _string(step.get('created_at'))
                    conv.turns.append(ir.Turn(role, [ir.Block.text_block(body)], ts=stamp))
                    conv.created_at = conv.created_at or stamp
                    conv.updated_at = stamp or conv.updated_at
            if not conv.turns:
                raise _invalid()
            conv.title = conv.first_user_text() or path.parents[2].name
            return conv
        content = raw.decode('utf-8-sig')
        if not content.strip() or '\x00' in content:
            raise _invalid()
        first = next(line.strip() for line in content.splitlines() if line.strip())
        title = first.lstrip('# ').strip() if first.startswith('#') else path.stem
        if path.name in AntigravityAdapter.ARTIFACTS and path.parent.parent.name == 'brain':
            title = f'{title} ({path.parent.name[:12]})'
        return ir.Conversation(source='antigravity', id=identity, path=str(path), title=ir.summarize_line(title),
                               turns=[ir.Turn(ir.ASSISTANT, [ir.Block.text_block(content)])])



class GeminiAppsAdapter(GoogleSource):
    name = 'gemini_apps'
    label = 'Gemini Apps (Desktop / Web)'
    managed_context = True

    def native_files(self, root):
        return ()
