"""Stable message codes with string-compatible Chinese output and JSON metadata."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def catalog():
    root = Path(__file__).resolve().parent.parent / 'web'
    if not (root / 'locales.zh.json').is_file():
        import relay_web
        root = Path(list(relay_web.__path__)[0])
    return json.loads((root / 'locales.zh.json').read_text(encoding='utf-8'))


class Message(str):
    def __new__(cls, code, params, fallback=None):
        value = catalog()[code].format(**params) if fallback is None else fallback
        obj = super().__new__(cls, value)
        obj.code = code
        obj.params = params
        return obj

    def descriptor(self):
        return {'code': self.code, 'params': {key: _parameter(value) for key, value in self.params.items()},
                'fallback': str(self)}

    def __reduce__(self):
        return (type(self), (self.code, self.params, str(self)))


def _parameter(value):
    if isinstance(value, Message):
        return value.descriptor()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def text(code, **params):
    return Message(code, params)


def error_text(error):
    if isinstance(error, Message):
        return error
    if isinstance(error, BaseException):
        for arg in error.args:
            if isinstance(arg, Message):
                return Message(arg.code, arg.params, str(error))
    return text('err.external', detail=str(error))


def restore_text(value, descriptor=None):
    """Read optional metadata from persisted records, retaining their original text."""
    if not isinstance(descriptor, dict) or descriptor.get('code') not in catalog():
        return value
    params = descriptor.get('params')
    if not isinstance(params, dict):
        return value
    params = {key: restore_text(item.get('fallback', ''), item) if isinstance(item, dict) else item
              for key, item in params.items()}
    return Message(descriptor['code'], params, str(value))


def join_text(items, separator):
    items = list(items)
    if not items:
        return ''
    result = items[-1]
    for item in reversed(items[:-1]):
        result = text('msg.message_pair', first=item, separator=separator, rest=result)
    return result


def annotate(value):
    """Add descriptors alongside legacy fields; never rewrite ordinary strings."""
    if isinstance(value, dict):
        result = {key: annotate(item) for key, item in value.items()}
        for key, item in value.items():
            if isinstance(item, Message):
                result[key + '_message'] = item.descriptor()
            elif isinstance(item, (list, tuple)) and any(isinstance(entry, Message) for entry in item):
                result[key + '_messages'] = [entry.descriptor() if isinstance(entry, Message) else entry for entry in item]
        return result
    if isinstance(value, (list, tuple)):
        return [annotate(item) for item in value]
    return value
