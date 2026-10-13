"""Read documented Yuanbao exporter JSON; never open account databases."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from collections import Counter, OrderedDict
from copy import deepcopy

from .. import archive, ir
from ..locations import resolve_home
from ..messages import error_text, text
from ..paths import safe_ms
from .base import ReadOnlyAdapter, SessionInfo

FORMAT = "yuanbao-export-json"
MAX_CONVERSATIONS = 4096
MAX_MESSAGES = 100000
MAX_CACHE_FILES = 128
MAX_CACHE_ROWS = 4096
MAX_CACHE_TEXT = 256 * 1024  # Characters across retained summary fields; never retain message bodies.


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(text('err.yuanbao_invalid_export'))
        result[key] = value
    return result


def decode(raw):
    if len(raw) > archive.MAX_FILE:
        raise ValueError(text('err.a_file_exceeds_32_mib'))
    try:
        document = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_object)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(text('err.yuanbao_invalid_export')) from exc
    if not isinstance(document, dict):
        raise ValueError(text('err.yuanbao_invalid_export'))
    if document.get('source') == 'yuanbao':
        if type(document.get('version', 1)) is not int or document.get('version', 1) != 1:
            raise ValueError(text('err.yuanbao_invalid_export'))
        rows = [document.get('conversation')] if 'conversation' in document else [document]
    elif isinstance(document.get('exportTime'), str) and isinstance(document.get('conversations'), list):
        rows = document['conversations']
    else:
        raise ValueError(text('err.yuanbao_invalid_export'))
    if not rows or len(rows) > MAX_CONVERSATIONS:
        raise ValueError(text('err.yuanbao_invalid_export'))
    # Validate the entire document before publishing or listing any of it.
    return [normalize(row) for row in rows]


def normalize(row):
    if not isinstance(row, dict):
        raise ValueError(text('err.yuanbao_invalid_export'))
    sid = row.get('id')
    if not isinstance(sid, str) or not sid.strip() or len(sid) > 512 or any(ord(c) < 32 for c in sid):
        raise ValueError(text('err.yuanbao_invalid_export'))
    result = {'id': sid, 'title': row.get('title', ''), 'messages': []}
    for key in ('title', 'cwd', 'model', 'created_at', 'updated_at'):
        if key in row:
            if not isinstance(row[key], str):
                raise ValueError(text('err.yuanbao_invalid_export'))
            try:
                row[key].encode('utf-8')
            except UnicodeError:
                raise ValueError(text('err.yuanbao_invalid_export')) from None
            result[key] = row[key]
    messages = row.get('messages')
    if not isinstance(messages, list) or not messages or len(messages) > MAX_MESSAGES:
        raise ValueError(text('err.yuanbao_invalid_export'))
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in (ir.USER, ir.ASSISTANT, ir.SYSTEM):
            raise ValueError(text('err.yuanbao_invalid_export'))
        content, thinking = message.get('content', ''), message.get('thinking', '')
        if not isinstance(content, str) or not isinstance(thinking, str) or not (content or thinking):
            raise ValueError(text('err.yuanbao_invalid_export'))
        try:
            content.encode('utf-8')
            thinking.encode('utf-8')
            sid.encode('utf-8')
        except UnicodeError:
            raise ValueError(text('err.yuanbao_invalid_export')) from None
        result['messages'].append({'role': message['role'], 'content': content, 'thinking': thinking})
    return result


def encode(row):
    return (json.dumps({'source': 'yuanbao', 'version': 1, 'conversation': normalize(row)},
                       ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')


def _title(row):
    if row['title']:
        return row['title']
    for message in row['messages']:
        if message['role'] == ir.USER:
            value = '\n'.join(part for part in (message['thinking'], message['content']) if part).strip()
            if value:
                return ir.summarize_line(value, 60)
    return text('ui.session')


def conversation(row, path=''):
    conv = ir.Conversation(source='yuanbao', id=row['id'], title=row['title'], path=path,
                           cwd=row.get('cwd', ''), model=row.get('model') or None,
                           created_at=row.get('created_at') or None, updated_at=row.get('updated_at') or None,
                           meta={'source_format': FORMAT, 'export': row,
                                 'notes': [text('msg.yuanbao_export_limits')]})
    for message in row['messages']:
        blocks = ([ir.Block.thinking_block(message['thinking'])] if message['thinking'] else [])
        if message['content']:
            blocks.append(ir.Block.text_block(message['content']))
        conv.turns.append(ir.Turn(message['role'], blocks, source_type=FORMAT))
    conv.title = _title(row)
    return conv


class YuanbaoAdapter(ReadOnlyAdapter):
    name = 'yuanbao'
    label = 'Tencent Yuanbao'
    cross_system = False
    read_note = text('msg.yuanbao_read_note')

    def __init__(self, home=None, clean=True):
        self.root = self.home = resolve_home(self.name, home)
        self._list_cache = OrderedDict()
        self._list_lock = threading.Lock()

    def info(self):
        result = super().info()
        result.update(label=text('ui.yuanbao'), capabilities=['read', 'export', 'export_store', 'export_restore'],
                      native_export=False, storage_format=FORMAT, write_note=text('msg.yuanbao_no_native_write'))
        return result

    def _files(self):
        for path in self._iter_files(self.root, '*.json'):
            resolved = Path(path).resolve()
            try:
                resolved.relative_to(Path(self.root).resolve())
            except ValueError:
                raise ValueError(text('err.source_session_file_is_outside_the_agent_storage_directory')) from None
            yield path

    def _prefix(self, path):
        relative = os.path.relpath(path, self.root).replace('\\', '/')
        return 'yuanbao:' + hashlib.sha256(relative.encode('utf-8')).hexdigest()[:16] + ':'

    def discover(self):
        rows = list(self._discover())
        counts = Counter(row.native_id for row in rows if row.native_id)
        for row in rows:
            row.variant_count = counts.get(row.native_id, 1)
            yield row

    def _discover(self):
        for path in self._files():
            stamp = self._stat(path)
            try:
                yield from self._list_file(path)
            except (ValueError, OSError) as exc:
                yield SessionInfo(self.name, self._prefix(path) + 'error', Path(path).name, '', '', None,
                                  stamp['updated_ms'], stamp['size'], 0, path, False, error_text(exc))

    @staticmethod
    def _list_stamp(path):
        if archive.is_link(path):
            raise ValueError(text('err.only_regular_files_can_be_packaged_symbolic_links_are_excluded'))
        st = os.stat(path)
        return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_mode)

    def _list_file(self, path):
        """Bounded LRU of detached summaries; details always read the original file."""
        stamp = self._list_stamp(path)
        with self._list_lock:
            cached = self._list_cache.get(path)
            if cached and cached[0] == stamp:
                self._list_cache.move_to_end(path)
                return deepcopy(list(cached[1]))
            self._list_cache.pop(path, None)
        prefix = self._prefix(path)
        rows = [SessionInfo(self.name, prefix + str(index), _title(row), row.get('cwd', ''),
                            row.get('model', ''), safe_ms(row.get('created_at')),
                            safe_ms(row.get('updated_at')) or stamp[3] // 1000000, stamp[2],
                            len(row['messages']), path, native_id=row['id'])
                for index, row in enumerate(decode(archive.read_file(path)))]
        characters = sum(len(value) for row in rows for value in vars(row).values() if isinstance(value, str))
        if len(rows) <= MAX_CACHE_ROWS and characters <= MAX_CACHE_TEXT and self._list_stamp(path) == stamp:
            with self._list_lock:
                self._list_cache[path] = (stamp, tuple(deepcopy(rows)), characters)
                self._list_cache.move_to_end(path)
                while (len(self._list_cache) > MAX_CACHE_FILES
                       or sum(len(entry[1]) for entry in self._list_cache.values()) > MAX_CACHE_ROWS
                       or sum(entry[2] for entry in self._list_cache.values()) > MAX_CACHE_TEXT):
                    self._list_cache.popitem(last=False)
        return rows

    def read(self, sid):
        if not isinstance(sid, str) or not sid.strip():
            raise ValueError(text('err.missing_session_id'))
        matches = []
        for path in self._files():
            prefix = self._prefix(path)
            if sid.startswith('yuanbao:') and not sid.startswith(prefix):
                continue
            rows = decode(archive.read_file(path))
            for index, row in enumerate(rows):
                if sid in (prefix + str(index), row['id']):
                    matches.append(conversation(row, path))
        if len(matches) > 1:
            raise ValueError(text('msg.several_records_share_this_session_id_use_a_distinct_selection_id_from_the_list'))
        if not matches:
            raise FileNotFoundError(text('err.yuanbao_session_not_found', sid=sid))
        return matches[0]
