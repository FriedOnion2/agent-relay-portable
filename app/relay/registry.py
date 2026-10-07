"""适配器注册表与迁移编排。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from . import ir
from .adapters.claude import ClaudeAdapter
from .adapters.codex import CodexAdapter
from .adapters.dsh import DshAdapter
from .adapters.markdown import render as render_markdown
from .adapters.base import BaseAdapter

_ADAPTERS = {"dsh": DshAdapter, "claude": ClaudeAdapter, "codex": CodexAdapter}

_CACHE: Dict[str, BaseAdapter] = {}


def get(source: str, **kw) -> BaseAdapter:
    if not isinstance(source, str) or not source.strip():
        raise ValueError("缺少 agent 名称")
    key = source.lower()
    if key not in _ADAPTERS:
        raise KeyError(f"未知 agent: {source}（可选: {', '.join(_ADAPTERS)}）")
    if not kw and key in _CACHE:
        return _CACHE[key]
    a = _ADAPTERS[key](**kw)
    if not kw:
        _CACHE[key] = a
    return a


def all_keys() -> List[str]:
    return list(_ADAPTERS)


def sources_info() -> List[Dict[str, Any]]:
    out = []
    for k in all_keys():
        try:
            a = get(k)
            info = a.info()
            if info["available"]:
                s = list(a.discover())
                info["session_count"] = len(s)
            else:
                info["session_count"] = 0
            out.append(info)
        except Exception as e:  # 单个 agent 出问题不能拖垮全局
            out.append({"name": k, "available": False, "error": str(e), "session_count": 0})
    return out


def list_sessions(source: str, keyword: str = "", limit: int = 500) -> List[Dict[str, Any]]:
    a = get(source)
    rows = []
    for s in a.discover():
        if keyword:
            hay = f"{s.title} {s.cwd} {s.id}".lower()
            if keyword.lower() not in hay:
                continue
        rows.append(s.to_dict())
    rows.sort(key=lambda r: r["updated_ms"] or 0, reverse=True)
    return rows[:limit]


def read_conversation(source: str, sid: str) -> ir.Conversation:
    return get(source).read(sid)


def transfer(source: str, sid: str, target: str, cwd: str | None = None,
             session_id: str | None = None, remap_tools: bool = True,
             include_thinking: bool = True, new_title: str | None = None) -> Dict[str, Any]:
    """把 source 的一个会话迁移到 target，返回会话信息与新文件路径。"""
    src = get(source)
    dst = get(target)
    conv = src.read(sid)
    if new_title:
        conv.title = new_title
    path = dst.write(conv, cwd=cwd, session_id=session_id,
                     remap_tools=remap_tools, include_thinking=include_thinking)
    return {
        "ok": True,
        "from": {"source": source, "id": sid, "path": conv.path, "title": conv.title},
        "to": {"source": target, "path": path, "cwd": cwd or conv.cwd},
        "stats": conv.stats(),
        "truncated": conv.truncated,
    }


def export_markdown(source: str, sid: str, include_thinking: bool = True,
                    include_tools: bool = True, max_text: int = 0) -> str:
    conv = get(source).read(sid)
    return render_markdown(conv, include_thinking=include_thinking,
                           include_tools=include_tools, max_text=max_text)
