"""Trusted read-only example: *.txt in <portable root>/example-conversations/."""
from pathlib import Path
from relay import ir
from relay.adapters.base import BaseAdapter, SessionInfo
from relay.runtime import project_root


class Adapter(BaseAdapter):
    name = 'plaintext'
    label = '文本会话示例'
    api_version = 1
    can_write = False

    def __init__(self):
        self.home = str(project_root() / 'example-conversations')

    def discover(self):
        for path in sorted(Path(self.home).glob('*.txt')):
            if not path.is_file() or path.is_symlink():
                continue
            stat = path.stat()
            yield SessionInfo(self.name, path.name, path.stem, '', '', None,
                              int(stat.st_mtime * 1000), stat.st_size, 1, str(path),
                              readable=stat.st_size <= 1024 * 1024,
                              error='' if stat.st_size <= 1024 * 1024 else '示例限制为 1 MiB')

    def read(self, sid):
        if Path(sid).name != sid or not sid.endswith('.txt'):
            raise ValueError('请选择列表中的文本文件')
        path = Path(self.home) / sid
        if path.is_symlink():
            raise ValueError('示例不读取符号链接')
        with path.open('rb') as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('示例限制为 1 MiB')
        return ir.Conversation(source=self.name, id=sid, title=path.stem,
                               path=str(path), turns=[ir.Turn(ir.USER, [ir.Block.text_block(raw.decode('utf-8-sig'))])])
