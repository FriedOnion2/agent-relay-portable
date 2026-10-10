"""适配器注册表与迁移编排。"""

from __future__ import annotations

from .messages import text as message_text, join_text, error_text

import os
from typing import Any, Dict, List

from . import ir
from .adapters.claude import ClaudeAdapter
from .adapters.claude_sdk import ClaudeSdkAdapter
from .adapters.codex import CodexAdapter
from .adapters.dsh import DshAdapter
from .adapters.workbuddy import WorkBuddyAdapter
from .adapters.codebuddy import CodeBuddyAdapter
from .adapters.markdown import render as render_markdown
from .adapters.base import BaseAdapter
from .windows import WindowsSource, selected_profile
from .ubuntu import UbuntuSource, selected_profile as selected_ubuntu

_ADAPTERS = {"workbuddy": WorkBuddyAdapter, "dsh": DshAdapter,
             "codebuddy": CodeBuddyAdapter, "claude": ClaudeAdapter,
             "claude_sdk": ClaudeSdkAdapter, "codex": CodexAdapter}

_CACHE: Dict[str, BaseAdapter] = {}


def get(source: str, **kw) -> BaseAdapter:
    if not isinstance(source, str) or not source.strip():
        raise ValueError(message_text('err.missing_agent_name'))
    key = source.lower()
    from . import device, plugins
    if key in plugins.entries:
        if kw:
            raise ValueError(message_text('err.community_plugin_directories_are_managed_by_the_plugins_themselves'))
        return plugins.PluginAdapter(key)
    if 'home' not in kw and key in device.blocked_homes:
        raise ValueError(device.blocked_homes[key])
    if key.startswith(("windows_", "ubuntu_")):
        ubuntu = key.startswith("ubuntu_")
        native = key.split("_", 1)[1]
        profile = selected_ubuntu() if ubuntu else selected_profile()
        if native not in _ADAPTERS or not profile:
            raise KeyError(message_text('err.cross_system_source_is_not_configured_run_windows_use_ubuntu_use_first'))
        if kw.keys() - {"clean"}:
            raise ValueError(message_text('err.cross_system_source_roots_are_set_by_windows_user_home_ubuntu_user_home'))
        cached = _CACHE.get(key)
        if not kw and cached and cached.profile == profile:
            return cached
        a = (UbuntuSource if ubuntu else WindowsSource)(native, _ADAPTERS[native], profile, **kw)
        if not kw:
            _CACHE[key] = a
        return a
    if key not in _ADAPTERS:
        raise KeyError(message_text('err.unknown_agent_source_available_value', source=source, value=', '.join(_ADAPTERS)))
    if not kw and key in _CACHE:
        return _CACHE[key]
    a = _ADAPTERS[key](**kw)
    if not kw:
        _CACHE[key] = a
    return a


def all_keys() -> List[str]:
    from . import plugins
    keys = list(_ADAPTERS)
    return (keys + list(plugins.entries) + (["windows_" + key for key in keys] if selected_profile() else [])
            + (["ubuntu_" + key for key in keys] if selected_ubuntu() else []))


def writable_keys() -> List[str]:
    return [key for key, cls in _ADAPTERS.items() if cls.can_write]


def sources_info() -> List[Dict[str, Any]]:
    out = []
    for k in all_keys():
        try:
            a = get(k)
            info = a.info()
            if k in _ADAPTERS and selected_profile():
                info.update(native_export=True, native_export_target="windows_" + k)
            if info["available"]:
                s = list(a.discover())
                info["session_count"] = len(s)
                info["unreadable_count"] = sum(not row.readable for row in s)
                errors = list(dict.fromkeys(row.error for row in s if row.error))
                if errors:
                    info["error"] = join_text(errors[:3], "; ")
            else:
                info["session_count"] = 0
            out.append(info)
        except Exception as e:  # 单个 agent 出问题不能拖垮全局
            from . import plugins
            out.append({"name": k, "available": False, "error": error_text(e), "session_count": 0,
                        "community":k in plugins.entries, "can_write":k in writable_keys()})
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


def _write_roots(adapter) -> List[str]:
    """写入会落在哪些目录里（用于操作记录）。"""
    roots = getattr(adapter, "roots", None) or [getattr(adapter, "root", None) or getattr(adapter, "home", None)]
    return [str(root) for root in roots if root]


def transfer(source: str, sid: str, target: str, cwd: str | None = None,
             session_id: str | None = None, remap_tools: bool = True,
             include_thinking: bool = True, new_title: str | None = None,
             preview_token: str | None = None, redact_secrets: bool = False) -> Dict[str, Any]:
    """把 source 的一个会话迁移到 target，返回会话信息与新文件路径。"""
    src = get(source)
    dst = get(target)
    if not dst.can_write:
        raise ValueError(message_text('err.label_does_not_support_migration_writes_yet', label=dst.label))
    if isinstance(src, WindowsSource):
        if not cwd or not os.path.isabs(cwd) or not os.path.isdir(cwd):
            raise ValueError(message_text('err.migration_from_a_cross_system_source_requires_an_existing_local_project_directory_cwd'))
    conv = src.read(sid)
    if conv.truncated:
        raise ValueError(message_text('err.source_session_exceeds_the_read_limit_migration_stopped_you_can_export_the_portion_already'))
    if not conv.turns:
        raise ValueError(message_text('err.source_session_has_no_migratable_content_empty_or_unparseable_file_migration_stopped'))
    from . import preview
    options = dict(cwd=cwd, session_id=session_id, remap_tools=remap_tools, include_thinking=include_thinking, new_title=new_title)
    if redact_secrets:
        options['redact_secrets'] = True
    plan = preview.report(conv, target, options, dst.home)
    preview.check_token(preview_token, plan['token'])
    conv = preview.prepare(conv, new_title)
    if redact_secrets:
        from . import sensitive
        conv = sensitive.redact_conversation(conv)
    from . import oplog
    with oplog.track("transfer", _write_roots(dst), source=source, target=target, session=sid,
                     title=conv.title) as record:
        path = dst.write(conv, cwd=cwd, session_id=session_id,
                         remap_tools=remap_tools, include_thinking=include_thinking)
        record["path"] = str(path)
    return {
        "ok": True,
        "from": {"source": source, "id": sid, "path": conv.path, "title": conv.title},
        "to": {"source": target, "path": path, "cwd": cwd or conv.cwd},
        "stats": conv.stats(),
        "truncated": conv.truncated,
        "preview": plan,
    }


def export_markdown(source: str, sid: str, include_thinking: bool = True,
                    include_tools: bool = True, max_text: int = 0, redact_secrets: bool = False) -> str:
    conv = get(source).read(sid)
    if redact_secrets:
        from . import sensitive
        conv = sensitive.redact_conversation(conv)
    return render_markdown(conv, include_thinking=include_thinking,
                           include_tools=include_tools, max_text=max_text)
