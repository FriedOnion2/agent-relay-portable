"""Portable, bounded conversation corpus shared by search and Skill discovery.

DELETE journaling keeps completed transactions in one movable SQLite file.
Only an explicit update reads agent data; queries never create a database.
"""

from .messages import text as message_text, error_text
import hashlib
import json
import re
import sqlite3
import tempfile
import time
from pathlib import Path

from . import archive, device, ir, registry, session_store
from .paths import iso, parse_iso
from .runtime import project_root

VERSION = 1
MAX_TEXT = 200000
MAX_DOCUMENTS = 10000
MAX_SECONDS = 120
LEXEMES = re.compile(r'[\u3400-\u9fff]+|[^\W_\u3400-\u9fff]+', re.UNICODE)


def terms(value):
    """ASCII encodings give FTS5 reliable Chinese single/bigram matching."""
    result = []
    for word in LEXEMES.findall(value.casefold()):
        if '\u3400' <= word[0] <= '\u9fff':
            result.extend('c%x' % ord(c) for c in word)
            result.extend('b%x_%x' % (ord(a), ord(b)) for a, b in zip(word, word[1:]))
        else:
            result.append('w' + word.encode('utf-8').hex())
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _stamp(paths):
    result = []
    for path in paths:
        p = Path(path)
        try:
            st = p.stat()
            result.append((str(p.resolve()), st.st_size, st.st_mtime_ns, st.st_ctime_ns))
        except FileNotFoundError:
            result.append((str(p), None))
    return digest(result)


def _dependencies(adapter, row):
    native = getattr(adapter, 'adapter', adapter)
    paths = [row.path]
    if hasattr(native, 'index_path'):
        paths.append(native.index_path)
    if native.name == 'codebuddy' and Path(row.path).name == 'index.json':
        manifest = native._json(row.path)
        refs = manifest.get('messages', [])
        if len(refs) > archive.MAX_FILES:
            raise ValueError(message_text('err.too_many_codebuddy_referenced_files'))
        from .paths import validate_session_id
        paths.extend(Path(row.path).parent / 'messages' / (validate_session_id(r['id']) + '.json') for r in refs)
        paths.append(Path(row.path).parent.parent / 'index.json')
    return _stamp(paths)


def _snapshot(conv, include_thinking):
    # Retain only searchable fields and bounded IR; raw/image metadata never enters the index.
    texts, tools, thinking, turns = [], [], [], []
    used = 0
    partial = bool(conv.truncated)
    for turn in conv.turns[:4000]:
        blocks = []
        for b in turn.blocks[:256]:
            if b.kind not in (ir.TEXT, ir.THINKING, ir.TOOL_CALL, ir.TOOL_RESULT):
                continue
            if b.kind == ir.THINKING and not include_thinking:
                continue
            value = b.text if b.kind in (ir.TEXT, ir.THINKING) else b.arguments if b.kind == ir.TOOL_CALL else b.output
            remaining = max(0, MAX_TEXT - used)
            text = value[:remaining]
            partial |= len(value) > remaining
            used += len(text)
            name = b.name[:200]
            blocks.append(dict(kind=b.kind, text=text if b.kind in (ir.TEXT, ir.THINKING) else '',
                               name=name, arguments=text if b.kind == ir.TOOL_CALL else '',
                               output=text if b.kind == ir.TOOL_RESULT else '',
                               call_id=b.call_id[:200], is_error=b.is_error))
            if b.kind == ir.TEXT:
                texts.append(text)
            elif b.kind == ir.THINKING:
                thinking.append(text)
            else:
                tools.append(name + '\n' + text)
        partial |= len(turn.blocks) > 256
        turns.append(dict(role=turn.role, blocks=blocks))
        if used >= MAX_TEXT:
            partial = True
            break
    partial |= len(conv.turns) > 4000
    payload = dict(source=conv.source, id=conv.id, title=conv.title[:1000], cwd=conv.cwd[:4000],
                   turns=turns, truncated=partial)
    return payload, '\n'.join(texts), '\n'.join(tools), '\n'.join(thinking), partial


class Corpus:
    def __init__(self, root=None):
        self.root = (Path(root) if root else project_root()).resolve()
        self.path = self.root / 'index' / 'corpus.sqlite3'
        self.owner = device.identity()

    def _connect(self, write=False):
        if not write and not self.path.exists():
            return None
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.path) if write else self.path.resolve().as_uri() + '?mode=ro',
                             uri=not write, timeout=5)
        db.row_factory = sqlite3.Row
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version != VERSION and (version or db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]):
            if write:
                backup = self.path.with_name('corpus-schema-%d-%d.sqlite3' % (version, time.time_ns()))
                target = sqlite3.connect(str(backup))
                try:
                    db.backup(target)
                finally:
                    target.close()
            db.close()
            raise ValueError(message_text('err.incompatible_index_version_original_database_preserved_backed_up_before_updating_use_a_mat'))
        if write and version == 0:
            try:
                db.executescript('''
                    PRAGMA journal_mode=DELETE;
                    CREATE TABLE docs (key TEXT PRIMARY KEY, scope TEXT, source TEXT, sid TEXT,
                        origin TEXT, device TEXT, locator TEXT, stamp TEXT, title TEXT, cwd TEXT,
                        updated_ms INTEGER, body TEXT, tools TEXT, thinking TEXT, payload TEXT,
                        canonical TEXT, partial INTEGER, offline INTEGER DEFAULT 0, thinking_enabled INTEGER);
                    CREATE INDEX scope_docs ON docs(scope);
                    CREATE VIRTUAL TABLE search_fts USING fts5(key UNINDEXED, body, tools, thinking, tokenize='unicode61');
                    PRAGMA user_version=1;
                ''')
            except Exception:
                db.close()
                raise
        return db

    def status(self):
        db = self._connect()
        if db is None:
            return dict(ok=True, exists=False, documents=0, schema=VERSION)
        try:
            count = db.execute('SELECT count(*) FROM docs').fetchone()[0]
            try:
                file_updated_at = iso(int(self.path.stat().st_mtime * 1000))
            except OSError:
                file_updated_at = None
            return dict(ok=True, exists=True, documents=count, schema=VERSION, path=str(self.path),
                        thinking_documents=db.execute('SELECT count(*) FROM docs WHERE thinking_enabled=1').fetchone()[0],
                        file_updated_at=file_updated_at)
        finally:
            db.close()

    def _put(self, db, key, scope, source, sid, origin, owner, locator, stamp, conv, include_thinking):
        payload, body, tools, thinking, partial = _snapshot(conv, include_thinking)
        native = source.removeprefix('windows_').removeprefix('ubuntu_') if hasattr(str, 'removeprefix') else re.sub(r'^(windows_|ubuntu_)', '', source)
        if native == 'claude_sdk':
            native = 'claude'
        # Same native session in Claude/SDK or copied packages is one independent evidence.
        evidence = digest([native, conv.id or sid, [dict(t, blocks=[b for b in t['blocks'] if b['kind'] != ir.THINKING]) for t in payload['turns']]])
        values = (key, scope, source, sid, origin, owner, locator, stamp, payload['title'], payload['cwd'],
                  parse_iso(conv.updated_at or conv.created_at), body, tools, thinking,
                  json.dumps(payload, ensure_ascii=False), evidence, int(partial), 0, int(include_thinking))
        with db:
            db.execute('DELETE FROM search_fts WHERE key=?', (key,))
            db.execute('INSERT OR REPLACE INTO docs VALUES (' + ','.join('?' * 19) + ')', values)
            db.execute('INSERT INTO search_fts VALUES (?,?,?,?)',
                       (key, ' '.join(terms(payload['title'] + '\n' + payload['cwd'] + '\n' + body)),
                        ' '.join(terms(tools)), ' '.join(terms(thinking))))

    def update(self, sources=None, include_thinking=False, packages=True, progress=None, cancel=None,
               max_documents=MAX_DOCUMENTS, max_seconds=MAX_SECONDS):
        if type(include_thinking) is not bool or type(packages) is not bool:
            raise ValueError(message_text('err.index_options_must_be_booleans'))
        sources = registry.all_keys() if sources is None else sources
        if not isinstance(sources, list) or any(not isinstance(s, str) or s not in registry.all_keys() for s in sources):
            raise ValueError(message_text('err.invalid_index_source_list'))
        if not 1 <= max_documents <= MAX_DOCUMENTS or not 0 < max_seconds <= MAX_SECONDS:
            raise ValueError(message_text('err.invalid_index_scan_limit'))
        state = dict(ok=True, processed=0, indexed=0, unchanged=0, errors=[], warnings=[], canceled=False, limited=False, source='')
        start, owner = time.monotonic(), self.owner
        def stopped():
            state['canceled'] = bool(cancel and cancel.is_set())
            state['limited'] = state['processed'] >= max_documents or time.monotonic() - start >= max_seconds
            return state['canceled'] or state['limited']
        def report():
            if progress:
                progress(dict(state, errors=list(state['errors']), warnings=list(state['warnings'])))
        def clean(scope, seen, roots=None):
            with db:
                for row in db.execute('SELECT key,locator FROM docs WHERE scope=?', (scope,)).fetchall():
                    if row['key'] not in seen:
                        if roots is not None:
                            accessible = False
                            for root in roots:
                                if not root or not Path(root).is_dir():
                                    continue
                                try:
                                    Path(row['locator']).resolve().relative_to(Path(root).resolve())
                                    accessible = True
                                except ValueError:
                                    continue
                            if not accessible:
                                continue
                        db.execute('DELETE FROM search_fts WHERE key=?', (row['key'],))
                        db.execute('DELETE FROM docs WHERE key=?', (row['key'],))
        db = self._connect(write=True)
        try:
            # Explicitly switching the option off removes previously retained thought content,
            # including offline records; no later search can reveal it.
            with db:
                if not include_thinking:
                    for row in db.execute('SELECT key,payload FROM docs WHERE thinking_enabled=1').fetchall():
                        payload = json.loads(row['payload'])
                        for turn in payload['turns']:
                            turn['blocks'] = [b for b in turn['blocks'] if b['kind'] != ir.THINKING]
                        db.execute("UPDATE docs SET thinking='',payload=?,thinking_enabled=0,stamp='' WHERE key=?", (json.dumps(payload, ensure_ascii=False), row['key']))
                        db.execute("UPDATE search_fts SET thinking='' WHERE key=?", (row['key'],))
            for source in dict.fromkeys(sources):
                if stopped():
                    break
                state['source'] = source
                seen, complete = set(), True
                try:
                    with db:
                        db.execute("UPDATE docs SET offline=1 WHERE origin='local' AND device=? AND source=?", (owner,source))
                    from . import plugins
                    adapter = registry.get(source) if source in plugins.entries else registry.get(source, clean=True)
                    if not adapter.available():
                        state['warnings'].append(message_text('msg.source_offline_cache_kept', source=source))
                        continue
                    native = getattr(adapter, 'adapter', adapter)
                    roots = getattr(native, 'roots', [getattr(native, 'root', native.home)])
                    scope = digest([owner, source, [str(Path(p).resolve()) for p in roots if p]])
                    for row in adapter.discover():
                        if stopped():
                            complete = False
                            break
                        state['processed'] += 1
                        key = digest([scope, row.id])
                        seen.add(key)
                        try:
                            if not row.readable:
                                raise ValueError(message_text('err.unreadable_session', detail=error_text(row.error) if row.error else message_text('msg.session_unreadable')))
                            dependency_stamp = _dependencies(adapter, row)
                            stamp = digest([dependency_stamp, row.title, row.cwd, include_thinking])
                            old = db.execute('SELECT stamp FROM docs WHERE key=?', (key,)).fetchone()
                            if old and old['stamp'] == stamp and source not in plugins.entries:
                                with db:
                                    db.execute('UPDATE docs SET offline=0 WHERE key=?', (key,))
                                state['unchanged'] += 1
                            else:
                                conv = adapter.read(row.id)
                                if dependency_stamp != _dependencies(adapter, row):
                                    raise ValueError(message_text('err.source_file_is_changing_update_the_index_again'))
                                self._put(db, key, scope, source, row.id, 'local', owner, row.path, stamp, conv, include_thinking)
                                state['indexed'] += 1
                        except Exception as exc:
                            state['errors'].append(dict(source=source, id=row.id, error=error_text(exc)))
                        report()
                    if complete:
                        clean(scope, seen, roots)
                except Exception as exc:
                    state['errors'].append(dict(source=source, error=error_text(exc)))
                report()
            if packages and not stopped():
                state['source'] = 'packages'
                storage = archive.storage_root()
                try:
                    locator = storage.relative_to(self.root).as_posix()
                except ValueError:
                    locator = str(storage)
                scope = digest(['packages', locator])
                seen, complete = set(), True
                with db:
                    db.execute("UPDATE docs SET offline=1 WHERE origin='package'")
                if not storage.is_dir():
                    state['warnings'].append(message_text('msg.packages_offline_cache_kept'))
                    complete = False
                else:
                    for path in (storage / 'conversations').glob('*/*.zip'):
                        if stopped():
                            complete = False
                            break
                        state['processed'] += 1
                        relative = path.relative_to(storage).as_posix()
                        key = digest([scope, relative])
                        seen.add(key)
                        try:
                            stamp = digest([_stamp([path]), include_thinking])
                            old = db.execute('SELECT stamp FROM docs WHERE key=?', (key,)).fetchone()
                            if old and old['stamp'] == stamp:
                                with db:
                                    db.execute('UPDATE docs SET offline=0 WHERE key=?', (key,))
                                state['unchanged'] += 1
                                continue
                            manifest, files = archive.read_package(path, session_store.KIND)
                            agent, count, session = manifest.get('agent'), manifest.get('root_count'), manifest.get('session')
                            if agent not in registry._ADAPTERS or type(count) is not int or count not in (1, 2) or not isinstance(session, dict):
                                raise ValueError(message_text('err.invalid_storage_package_metadata'))
                            entry = archive.safe_name(manifest.get('entry'))
                            if entry not in files:
                                raise ValueError(message_text('err.storage_package_entry_is_missing'))
                            with tempfile.TemporaryDirectory(prefix='relay-corpus-') as temporary:
                                archive.unpack(files, temporary)
                                roots = [str(Path(temporary) / ('root%d' % i)) for i in range(count)]
                                adapter = registry.get(agent, home=roots[0])
                                if agent == 'codebuddy':
                                    adapter.roots = roots
                                conv = adapter.read(session['id'])
                                if Path(conv.path).resolve() != (Path(temporary) / entry).resolve():
                                    raise ValueError(message_text('err.session_id_does_not_match_the_package_entry'))
                                conv.cwd = conv.cwd or session.get('cwd') or ''
                                self._put(db, key, scope, agent, session['id'], 'package', '', locator + '/' + relative,
                                          stamp, conv, include_thinking)
                            state['indexed'] += 1
                        except Exception as exc:
                            state['errors'].append(dict(source='package', id=relative, error=error_text(exc)))
                        report()
                    if complete:
                        clean(scope, seen)
            state['ok'] = not state['errors']
            report()
            return state
        finally:
            db.close()

    def _public(self, row):
        value = {k:row[k] for k in ('key','source','sid','origin','title','cwd','updated_ms','partial')}
        value['offline'] = bool(row['offline'] or (row['origin'] == 'local' and row['device'] != self.owner))
        return value

    def search(self, query='', source='', project='', tool='', after='', before='', include_thinking=False, limit=50, offset=0):
        if any(not isinstance(v, str) for v in (query, source, project, tool, after, before)) or type(include_thinking) is not bool:
            raise ValueError(message_text('err.invalid_search_field_type'))
        if len(query) > 256 or len(project) > 1000 or len(tool) > 200 or type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 10000:
            raise ValueError(message_text('err.search_scope_is_too_large'))
        words = LEXEMES.findall(query.casefold())
        if len(words) > 32:
            raise ValueError(message_text('err.too_many_search_terms'))
        expressions = []
        for word in words:
            tokens = terms(word)
            tokens = tokens[len(word):] if '\u3400' <= word[0] <= '\u9fff' and len(word) > 1 else tokens
            expressions.extend('"' + t + '"' for t in tokens)
        where, args = [], []
        if expressions:
            fields = '{body tools thinking}' if include_thinking else '{body tools}'
            where.append('key IN (SELECT key FROM search_fts WHERE search_fts MATCH ?)')
            args.append(fields + ' : (' + ' AND '.join(expressions) + ')')
        for column, value in (('source', source),):
            if value:
                where.append(column + '=?'); args.append(value)
        for column, value in (('cwd', project), ('tools', tool)):
            if value:
                where.append('instr(lower(' + column + '),lower(?))>0'); args.append(value)
        for value, operator in ((after, '>='), (before, '<=')):
            if value:
                ms = parse_iso(value)
                if ms is None:
                    raise ValueError(message_text('err.time_filters_require_an_iso_date'))
                if operator == '<=' and len(value) == 10:
                    ms += 86400000 - 1
                where.append('updated_ms' + operator + '?'); args.append(ms)
        db = self._connect()
        if db is None:
            return dict(ok=True, results=[], indexed=False, more=False)
        try:
            sql = 'SELECT * FROM docs' + (' WHERE ' + ' AND '.join(where) if where else '') + " ORDER BY offline, CASE origin WHEN 'package' THEN 0 ELSE 1 END,updated_ms DESC,key"
            results, seen, matched = [], set(), 0
            for row in db.execute(sql, args):
                hay = '\n'.join([row['title'], row['cwd'], row['body'], row['tools']] + ([row['thinking']] if include_thinking else [])).casefold()
                if any(w not in hay for w in words) or row['canonical'] in seen:
                    continue
                seen.add(row['canonical'])
                if matched < offset:
                    matched += 1; continue
                if len(results) == limit:
                    return dict(ok=True, results=results, indexed=True, more=True)
                hit = min((hay.find(w) for w in words), default=0)
                value = self._public(row)
                value['snippet'] = hay[max(0, hit-80):max(0, hit-80)+300]
                results.append(value)
            return dict(ok=True, results=results, indexed=True, more=False)
        finally:
            db.close()

    def document(self, key, include_thinking=False):
        db = self._connect()
        try:
            row = db.execute('SELECT * FROM docs WHERE key=?', (key,)).fetchone() if db else None
            if row is None:
                raise FileNotFoundError(message_text('err.session_not_found_in_the_index'))
            value = self._public(row)
            value['can_open'] = False
            if row['origin'] == 'local' and row['device'] == self.owner and not row['offline']:
                try:
                    from . import plugins
                    adapter = registry.get(row['source']) if row['source'] in plugins.entries else registry.get(row['source'], clean=True)
                    available = adapter.available()
                    native = getattr(adapter, 'adapter', adapter)
                    roots = getattr(native, 'roots', [getattr(native, 'root', native.home)])
                    scope = digest([self.owner,row['source'],[str(Path(p).resolve()) for p in roots if p]])
                    value['can_open'] = available and scope == row['scope'] and Path(row['locator']).is_file()
                except (OSError,ValueError,KeyError):
                    pass
            payload = json.loads(row['payload'])
            if not include_thinking:
                for t in payload['turns']:
                    t['blocks'] = [b for b in t['blocks'] if b['kind'] != ir.THINKING]
            value.update(conversation=payload, locator=row['locator'], canonical=row['canonical'])
            return value
        finally:
            if db:
                db.close()

    def evidence(self, limit=500):
        """Bounded, complete, independent cached records; no original source reads."""
        db = self._connect()
        if db is None:
            return []
        try:
            rows = db.execute("SELECT * FROM docs WHERE partial=0 ORDER BY offline, CASE origin WHEN 'package' THEN 0 ELSE 1 END,updated_ms DESC,key")
            documents, seen = [], set()
            for row in rows:
                if row['canonical'] not in seen:
                    seen.add(row['canonical'])
                    payload = json.loads(row['payload'])
                    for t in payload['turns']:
                        t['blocks'] = [b for b in t['blocks'] if b['kind'] != ir.THINKING]
                    documents.append(dict(self._public(row), conversation=payload, canonical=row['canonical'], can_open=False))
                if len(documents) >= limit:
                    break
            return documents
        finally:
            db.close()
