"""Explicit SDK view of the shared Claude native session store.

SDK APIs enumerate Claude sessions, not a distinct SDK-owned format. Never infer
the creator from userType, agentName, isSidechain or process entrypoint variables.
"""
from ..locations import resolve_home
from .base import ReadOnlyAdapter
from .claude import ClaudeAdapter


class ClaudeSdkAdapter(ReadOnlyAdapter, ClaudeAdapter):
    name = "claude_sdk"
    label = "Claude Agent SDK"
    read_note = "SDK 与 Claude Code 共用会话存储；此入口显示共享记录，无法仅凭日志确认创建者。"

    def __init__(self, home=None, clean=True):
        # Resolve this source's override independently, then reuse the native reader.
        super().__init__(home=resolve_home(self.name, home), clean=clean)

    def discover(self):
        for row in super().discover():
            row.shared_store = True
            yield row

    def _parse(self, path):
        conv = super()._parse(path)
        conv.meta.update(source_format="claude-native-jsonl", shared_store=True, creator="unknown")
        conv.meta.setdefault("notes", []).insert(0, self.read_note)
        return conv
