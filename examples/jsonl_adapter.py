"""Trusted read-only example: JSON Lines chats in <portable root>/example-jsonl/*.jsonl.

Each line is one message: {"role": "user" | "assistant", "content": "..."}; "title" on the first line is optional.
Copy this file as the starting point for a real adapter and replace the parsing in ``read``.
Check it with:  python app/cli.py plugins check jsonl examples/jsonl_adapter.py
"""
import json
from pathlib import Path
from relay import ir
from relay.adapters.base import BaseAdapter, SessionInfo
from relay.runtime import project_root

LIMIT = 1024 * 1024          # read at most 1 MiB per file and report anything cut short
ROLES = {'user': ir.USER, 'assistant': ir.ASSISTANT, 'system': ir.SYSTEM}


class Adapter(BaseAdapter):
    name = 'jsonl'
    label = 'JSONL 会话示例'
    api_version = 1                       # must match relay.plugins.API_VERSION
    can_write = False                     # community plugins are read-only

    def __init__(self):
        self.home = str(project_root() / 'example-jsonl')

    def available(self):
        return Path(self.home).is_dir()

    def _files(self):
        for path in sorted(Path(self.home).glob('*.jsonl')):
            if path.is_file() and not path.is_symlink():      # never follow links out of the data folder
                yield path

    def discover(self):
        for path in self._files():
            size = path.stat().st_size
            yield SessionInfo(self.name, path.name, path.stem, '', '', None, int(path.stat().st_mtime * 1000),
                              size, 0, str(path), readable=size <= LIMIT,
                              error='' if size <= LIMIT else '示例限制为 1 MiB')

    def read(self, sid):
        if Path(sid).name != sid or not sid.endswith('.jsonl'):      # reject paths: only names from discover()
            raise ValueError('请选择列表中的 .jsonl 文件')
        path = Path(self.home) / sid
        if path.is_symlink() or not path.is_file():
            raise ValueError('找不到会话文件')
        with path.open('rb') as stream:
            raw = stream.read(LIMIT + 1)
        truncated = len(raw) > LIMIT
        turns, title = [], path.stem
        for number, line in enumerate(raw[:LIMIT].decode('utf-8-sig', 'replace').splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                role = ROLES[row['role']]
                text = str(row['content'])
            except (ValueError, KeyError, TypeError):
                raise ValueError('第 %d 行不是 {"role", "content"} 格式' % number) from None   # say which line, don't guess
            title = row.get('title', title) if number == 1 else title
            turns.append(ir.Turn(role, [ir.Block.text_block(text)]))
        return ir.Conversation(source=self.name, id=sid, title=title, path=str(path), turns=turns, truncated=truncated)
