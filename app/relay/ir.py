"""统一中间表示 (Intermediate Representation)。

各家 agent 的会话格式各不相同，transfer 时先统一转成 IR，再由目标适配器序列化，
避免 N×N 的直接转换器。
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---- 块类型 ----
TEXT = "text"
THINKING = "thinking"
IMAGE = "image"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
RAW = "raw"

# ---- 角色 ----
USER = "user"
ASSISTANT = "assistant"
SYSTEM = "system"


@dataclass
class Block:
    """内容的最小单位。字段按需使用，未使用的留空。"""

    kind: str
    text: str = ""
    call_id: str = ""
    name: str = ""
    arguments: str = ""
    output: str = ""
    is_error: bool = False
    media_type: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    # ---- 构造糖 ----
    @staticmethod
    def text_block(text: str) -> "Block":
        return Block(kind=TEXT, text=text)

    @staticmethod
    def thinking_block(text: str) -> "Block":
        return Block(kind=THINKING, text=text)

    @staticmethod
    def tool_call(call_id: str, name: str, arguments: str = "") -> "Block":
        return Block(kind=TOOL_CALL, call_id=call_id, name=name, arguments=arguments)

    @staticmethod
    def tool_result(call_id: str, output: str, is_error: bool = False) -> "Block":
        return Block(kind=TOOL_RESULT, call_id=call_id, output=output, is_error=is_error)

    def plain(self) -> str:
        """块的纯文本投影，用于预览与降级。"""
        if self.kind in (TEXT, THINKING):
            return self.text
        if self.kind == TOOL_CALL:
            args = _trim(self.arguments, 300)
            return f"[调用工具 {self.name}] {args}"
        if self.kind == TOOL_RESULT:
            prefix = "[工具出错] " if self.is_error else "[工具结果] "
            return prefix + _trim(self.output, 300)
        if self.kind == IMAGE:
            return f"[图片 {self.media_type or 'image'}]"
        if self.kind == RAW:
            return "[原始内容块] " + _trim(json.dumps(self.meta, ensure_ascii=False), 600)
        return ""


@dataclass
class Turn:
    role: str
    blocks: List[Block] = field(default_factory=list)
    ts: Optional[str] = None          # ISO-8601, UTC
    model: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    source_type: str = ""             # 原始记录类型，便于溯源调试

    def text(self) -> str:
        """整轮的纯文本投影。"""
        parts = [b.plain() for b in self.blocks if b.plain()]
        return "\n".join(parts).strip()

    def all_text(self) -> str:
        return "\n".join(b.text for b in self.blocks if b.text)


@dataclass
class Conversation:
    source: str = ""            # workbuddy | dsh | codebuddy | claude | claude_sdk | codex
    id: str = ""
    title: str = ""
    cwd: str = ""
    model: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    turns: List[Turn] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    path: str = ""
    truncated: bool = False     # 源文件过大、只读取了部分时为真

    # ---- 统计 ----
    def stats(self) -> Dict[str, int]:
        counts = {"user": 0, "assistant": 0, "system": 0, "tool_call": 0, "tool_result": 0, "thinking": 0}
        for t in self.turns:
            if t.role in counts:
                counts[t.role] += 1
            for b in t.blocks:
                if b.kind == TOOL_CALL:
                    counts["tool_call"] += 1
                elif b.kind == TOOL_RESULT:
                    counts["tool_result"] += 1
                elif b.kind == THINKING:
                    counts["thinking"] += 1
        counts["turns"] = len(self.turns)
        return counts

    def first_user_text(self, limit: int = 80) -> str:
        for t in self.turns:
            if t.role == USER:
                s = t.text()
                if s:
                    return summarize_line(s, limit)
        return ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "id": self.id,
            "title": self.title,
            "cwd": self.cwd,
            "model": self.model,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "meta": self.meta,
            "truncated": self.truncated,
            "turns": [
                {
                    "role": t.role,
                    "ts": t.ts,
                    "model": t.model,
                    "source_type": t.source_type,
                    "blocks": [
                        {k: v for k, v in b.__dict__.items() if v not in ("", None, False, {})}
                        for b in t.blocks
                    ],
                }
                for t in self.turns
            ],
        }


# ---------- 通用工具 ----------

def _trim(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + f" …(共 {len(s)} 字符)"


def summarize_line(s: str, limit: int = 80) -> str:
    """把一段可能多行的文本压成单行摘要。"""
    s = (s or "").strip().replace("\r", " ")
    s = re.sub(r"\s+", " ", s)
    return s if len(s) <= limit else s[:limit] + "…"


def preview_text(s: str, limit: int = 4000) -> str:
    s = s or ""
    return s if len(s) <= limit else s[:limit] + f"\n\n… 已截断（原文 {len(s)} 字符）"
