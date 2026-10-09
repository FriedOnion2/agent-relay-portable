"""比较两个会话：迁移后核对「内容有没有丢、有没有多」。

按顺序对齐用户 / 助手的文本和工具调用（工具名不参与比较，因为迁移时会按目标软件改名），
思考和系统上下文只统计数量。只读，不联网。
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Tuple

from . import ir

MAX_ITEMS = 20000
MAX_SAMPLES = 50

_SPACE = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _SPACE.sub(" ", text or "").strip()


def items(conv: ir.Conversation) -> List[Tuple[str, str, str]]:
    """(类型, 角色, 规范化文本) 序列；工具调用只比较参数，工具结果比较输出。"""
    rows: List[Tuple[str, str, str]] = []
    for turn in conv.turns:
        if turn.role not in (ir.USER, ir.ASSISTANT):
            continue
        for block in turn.blocks:
            if block.kind == ir.TEXT and _norm(block.text):
                rows.append(("text", turn.role, _norm(block.text)))
            elif block.kind == ir.TOOL_CALL:
                rows.append(("tool_call", turn.role, _norm(block.arguments)))
            elif block.kind == ir.TOOL_RESULT:
                rows.append(("tool_result", turn.role, _norm(block.output)))
    return rows


def _sample(row: Tuple[str, str, str], limit: int = 120) -> Dict[str, str]:
    text = row[2] if len(row[2]) <= limit else row[2][:limit] + "…"
    return {"kind": row[0], "role": row[1], "text": text}


def compare(a: ir.Conversation, b: ir.Conversation) -> Dict[str, Any]:
    left, right = items(a)[:MAX_ITEMS], items(b)[:MAX_ITEMS]
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    matched = 0
    only_a: List[Dict[str, str]] = []
    only_b: List[Dict[str, str]] = []
    changed: List[Dict[str, Any]] = []
    only_a_total = only_b_total = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            matched += i2 - i1
        elif tag == "replace" and (i2 - i1) == (j2 - j1) and all(left[i][:2] == right[j][:2] for i, j in zip(range(i1, i2), range(j1, j2))):
            for i, j in zip(range(i1, i2), range(j1, j2)):
                if len(changed) < MAX_SAMPLES:
                    changed.append({"before": _sample(left[i]), "after": _sample(right[j])})
            only_a_total += i2 - i1
            only_b_total += j2 - j1
        else:
            only_a_total += i2 - i1
            only_b_total += j2 - j1
            only_a.extend(_sample(row) for row in left[i1:i2] if len(only_a) < MAX_SAMPLES)
            only_b.extend(_sample(row) for row in right[j1:j2] if len(only_b) < MAX_SAMPLES)
    sa, sb = a.stats(), b.stats()
    return {
        "ok": True,
        "identical": only_a_total == 0 and only_b_total == 0,
        "a": {"source": a.source, "id": a.id, "title": a.title, "items": len(left), "stats": sa},
        "b": {"source": b.source, "id": b.id, "title": b.title, "items": len(right), "stats": sb},
        "matched": matched,
        "ratio": round(matcher.ratio(), 4),
        "only_in_a": only_a_total,
        "only_in_b": only_b_total,
        "changed": changed,
        "only_in_a_samples": only_a[:MAX_SAMPLES],
        "only_in_b_samples": only_b[:MAX_SAMPLES],
        "stats_delta": {key: sb[key] - sa[key] for key in sa},
        "truncated": a.truncated or b.truncated or len(items(a)) > MAX_ITEMS or len(items(b)) > MAX_ITEMS,
    }
