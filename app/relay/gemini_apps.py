"""Import locally downloaded Gemini Apps activity records."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path

from . import archive, ir, oplog, registry
from .adapters.google import encode_context
from .google_context import context_home
from .messages import text
from .native_import import _exclusive_lock
from .paths import atomic_write, ensure_directory, parse_iso

AGENT = 'gemini_apps'
PRODUCTS = {'gemini', 'bard', 'gemini apps', 'gemini 应用', 'gemini 應用程式'}


class ActivityText(HTMLParser):
    """Extract text without retaining markup or opening embedded resources."""

    BLOCKS = {'p', 'br', 'div', 'li', 'pre', 'blockquote', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
    HIDDEN = {'script', 'style', 'template'}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden.append(tag)
        elif not self.hidden and tag in self.BLOCKS:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
        elif tag in self.BLOCKS:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _value(value):
    return value if isinstance(value, str) else ''


def _response(value):
    items = value if isinstance(value, list) else [value]
    parsed = []
    for item in items:
        fragment = _value(item.get('html') if isinstance(item, dict) else item)
        if fragment:
            parser = ActivityText()
            parser.feed(fragment)
            parser.close()
            parsed.append(''.join(parser.parts).strip())
    return '\n\n'.join(part for part in parsed if part)


def activity(record):
    if not isinstance(record, dict):
        return None
    products = record.get('products')
    labels = [_value(record.get('header'))]
    if isinstance(products, list):
        labels.extend(map(_value, products))
    if not any(label.strip().casefold() in PRODUCTS for label in labels):
        return None
    timestamp = _value(record.get('time'))
    if not timestamp or parse_iso(timestamp) is None:
        return None

    prompt = _value(record.get('title')).strip()
    subtitles = record.get('subtitles')
    if isinstance(subtitles, list):
        subtitle = next((_value(row.get('value')).strip() for row in subtitles
                         if isinstance(row, dict) and _value(row.get('value')).strip()), '')
        prompt = subtitle or prompt
    for prefix in ('Prompted ', 'Asked Gemini: '):
        if prompt.startswith(prefix):
            prompt = prompt[len(prefix):].strip()
            break
    else:
        if not record.get('safeHtmlItem') and not subtitles:
            return None
    response = _response(record.get('safeHtmlItem'))
    turns = [ir.Turn(role, [ir.Block.text_block(value)], ts=timestamp)
             for role, value in ((ir.USER, prompt), (ir.ASSISTANT, response)) if value]
    if not turns:
        return None
    fingerprint = json.dumps([timestamp, prompt, response], ensure_ascii=False).encode('utf-8')
    sid = 'activity-' + hashlib.sha256(fingerprint).hexdigest()
    return ir.Conversation(source=AGENT, id=sid, title=ir.summarize_line(prompt or response),
                           created_at=timestamp, updated_at=timestamp, turns=turns)


def import_file(path):
    if not isinstance(path, str) or not Path(path).expanduser().is_absolute():
        raise ValueError(text('err.gemini_apps_input_path'))
    source = Path(path).expanduser()
    if source.suffix.lower() != '.json':
        raise ValueError(text('err.gemini_apps_format'))
    return import_bytes(archive.read_file(source))


def receive(stream, size):
    if not 0 < size <= archive.MAX_FILE:
        raise ValueError(text('err.gemini_apps_limit'))
    raw = stream.read(size)
    if len(raw) != size:
        raise ValueError(text('err.gemini_apps_format'))
    return import_bytes(raw)


def import_bytes(raw):
    try:
        rows = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError(text('err.gemini_apps_format')) from None
    if not isinstance(rows, list):
        raise ValueError(text('err.gemini_apps_format'))
    files = {}
    recognized = 0
    for row in rows:
        conv = activity(row)
        if conv is not None:
            recognized += 1
            files[conv.id + '.json'] = encode_context(conv)
    if not files:
        raise ValueError(text('err.gemini_apps_format'))
    if (len(files) > archive.MAX_FILES or any(len(raw) > archive.MAX_FILE for raw in files.values()) or
            sum(map(len, files.values())) > archive.MAX_TOTAL):
        raise ValueError(text('err.gemini_apps_limit'))

    adapter = registry.get(AGENT)
    root = context_home(adapter)
    created = []
    with oplog.track('gemini-activity-import', [str(root)], source=AGENT, target=AGENT, path=str(root)):
        ensure_directory(root)
        with _exclusive_lock(root / '.restore.publish-lock'):
            pending = []
            for name, raw in files.items():
                destination = root / name
                if destination.exists() or destination.is_symlink():
                    if archive.read_file(destination) != raw:
                        # An earlier restore can attach a local project. Keep it.
                        if adapter.read(destination.stem).id != destination.stem:
                            raise ValueError(text('err.gemini_apps_format'))
                else:
                    pending.append((destination, raw))
            try:
                for destination, raw in pending:
                    atomic_write(str(destination), [raw], encoding=None, overwrite=False)
                    created.append(destination)
            except BaseException:
                for destination in reversed(created):
                    destination.unlink()
                raise
    return {'ok': True, 'imported': len(created), 'skipped': recognized - len(created),
            'ignored': len(rows) - recognized}
