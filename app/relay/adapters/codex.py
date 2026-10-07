"""OpenAI Codex (CLI / Desktop) 会话适配器。

存储结构：
    ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl
    ~/.codex/session_index.jsonl          （thread_name 索引）

每条记录是统一的信封：
    {"timestamp":..., "ordinal":N, "type":..., "payload":{...}}
type ∈ { session_meta, turn_context, response_item, event_msg, token_usage_record, ... }
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional

from .. import ir
from ..clean import strip_scaffolding, looks_like_system_prompt
from ..paths import iso, read_jsonl, safe_ms, atomic_write, uuid7, now_ms, validate_session_id
from .base import BaseAdapter, SessionInfo, ToolNameMap

MAX_SCAN_BYTES = 32 * 1024 * 1024


def _content_to_text(items: Any) -> str:
    """codex 的 content 可能是 str、块列表、或 [{'type':'input_text',...}]。"""
    if isinstance(items, str):
        return items
    if isinstance(items, list):
        parts = []
        for b in items:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                bt = b.get("type")
                if bt in ("input_text", "output_text", "text", "summary_text"):
                    parts.append(b.get("text") or b.get("summary") or "")
                elif bt == "encrypted_content":
                    parts.append("[加密内容]")
        return "\n".join(p for p in parts if p)
    if isinstance(items, dict):
        return items.get("text") or json.dumps(items, ensure_ascii=False)
    return ""


class CodexAdapter(BaseAdapter):
    name = "codex"
    label = "OpenAI Codex"

    def __init__(self, home: str | None = None, clean: bool = True):
        root = (home
                or os.environ.get("RELAY_CODEX_HOME")
                or os.environ.get("CODEX_HOME")
                or os.path.expanduser(os.path.join("~", ".codex")))
        self.root = root
        self.home = os.path.join(root, "sessions")
        self.index_path = os.path.join(root, "session_index.jsonl")
        self.clean = clean

    # ---------------- 发现 ----------------

    def _name_index(self) -> Dict[str, Dict[str, str]]:
        """thread_id -> {name, updated_at}"""
        out: Dict[str, Dict[str, str]] = {}
        if not os.path.isfile(self.index_path):
            return out
        for rec, _ in read_jsonl(self.index_path):
            tid = rec.get("id") or rec.get("thread_id")
            if tid:
                out[str(tid)] = {
                    "name": rec.get("thread_name") or "",
                    "updated_at": rec.get("updated_at") or "",
                }
        return out

    def discover(self) -> Iterable[SessionInfo]:
        names = self._name_index()
        for path in self._iter_files(self.home, "rollout-*.jsonl"):
            info = self._peek(path, names)
            if info:
                yield info

    def _peek(self, path: str, names: Dict[str, Dict[str, str]]) -> Optional[SessionInfo]:
        st = self._stat(path)
        sid = None
        title = ""
        cwd = ""
        model = ""
        created_ms = None
        updated_ms = None
        turns = 0
        first_user = ""
        for rec, _trunc in read_jsonl(path, MAX_SCAN_BYTES):
            rt = rec.get("type")
            pl = rec.get("payload") or {}
            ts = safe_ms(rec.get("timestamp"))
            if rt == "session_meta":
                sid = pl.get("id") or pl.get("session_id")
                cwd = pl.get("cwd") or ""
                model = pl.get("model") or pl.get("model_provider") or ""
                title = names.get(str(sid), {}).get("name", "")
            elif rt == "turn_context":
                cwd = cwd or pl.get("cwd") or ""
            elif rt == "response_item" and pl.get("type") == "message":
                role = pl.get("role")
                if role == ir.USER and not first_user:
                    t = _content_to_text(pl.get("content"))
                    if self.clean:
                        t = strip_scaffolding(t)
                    if t and not looks_like_system_prompt(t):
                        first_user = ir.summarize_line(t, 60)
                if role == ir.ASSISTANT:
                    turns += 1
            elif rt == "event_msg" and pl.get("type") == "task_started":
                turns += 1
            if ts is not None:
                created_ms = ts if created_ms is None else min(created_ms, ts)
                updated_ms = ts if updated_ms is None else max(updated_ms, ts)

        if not sid:
            sid = os.path.splitext(os.path.basename(path))[0]
        return SessionInfo(
            source=self.name, id=str(sid), title=title or first_user or "未命名会话",
            cwd=cwd.replace("\\", "/"), model=model,
            created_ms=created_ms, updated_ms=updated_ms or st["updated_ms"],
            size=st["size"], turns=turns, path=path,
        )

    # ---------------- 读取 ----------------

    def read(self, sid: str) -> ir.Conversation:
        path = self.find_path(sid)
        if not path:
            raise FileNotFoundError(f"找不到 Codex 会话: {sid}")
        return self._parse(path)

    def _parse(self, path: str) -> ir.Conversation:
        names = self._name_index()
        conv = ir.Conversation(source=self.name, path=path,
                               truncated=os.path.getsize(path) > MAX_SCAN_BYTES)
        pending_assistant: Optional[ir.Turn] = None

        def flush():
            nonlocal pending_assistant
            if pending_assistant and pending_assistant.blocks:
                conv.turns.append(pending_assistant)
            pending_assistant = None

        def ensure_assistant(ts_ms):
            nonlocal pending_assistant
            if pending_assistant is None:
                pending_assistant = ir.Turn(role=ir.ASSISTANT, ts=iso(ts_ms), source_type="codex-turn")

        for rec, truncated in read_jsonl(path, MAX_SCAN_BYTES):
            conv.truncated = conv.truncated or truncated
            rt = rec.get("type")
            pl = rec.get("payload") or {}
            ts = safe_ms(rec.get("timestamp"))

            if rt == "session_meta":
                conv.id = str(pl.get("id") or pl.get("session_id") or conv.id)
                conv.cwd = (pl.get("cwd") or "").replace("\\", "/")
                conv.created_at = conv.created_at or iso(ts)
                conv.meta.update({
                    "originator": pl.get("originator"),
                    "cli_version": pl.get("cli_version"),
                    "source": pl.get("source"),
                    "model_provider": pl.get("model_provider"),
                })
                nm = names.get(conv.id, {}).get("name")
                if nm:
                    conv.title = nm

            elif rt == "turn_context":
                conv.cwd = conv.cwd or (pl.get("cwd") or "").replace("\\", "/")
                conv.meta.setdefault("turn_timezone", pl.get("timezone"))
                if not conv.model and pl.get("model"):
                    conv.model = pl["model"]

            elif rt == "response_item":
                ptype = pl.get("type")
                if ptype == "message":
                    role = pl.get("role")
                    text = _content_to_text(pl.get("content"))
                    if role == ir.SYSTEM or role == "developer":
                        # 目标 agent 会自己注入系统提示，源侧的丢弃
                        continue
                    if not text:
                        continue
                    if self.clean:
                        text = strip_scaffolding(text)
                    if not text:
                        continue
                    if role == ir.USER:
                        if looks_like_system_prompt(text):
                            continue
                        flush()
                        conv.turns.append(ir.Turn(role=ir.USER, blocks=[ir.Block.text_block(text)],
                                                  ts=iso(ts), source_type="response_item/message"))
                    else:
                        ensure_assistant(ts)
                        pending_assistant.blocks.append(ir.Block.text_block(text))

                elif ptype == "agent_message":
                    # 子 agent 之间的消息，降级为带标注的文本
                    text = _content_to_text(pl.get("content"))
                    if self.clean:
                        text = strip_scaffolding(text)
                    if text:
                        ensure_assistant(ts)
                        author = pl.get("author") or ""
                        to = pl.get("recipient") or ""
                        pending_assistant.blocks.append(ir.Block.text_block(
                            f"[{author} → {to}] {text}"))

                elif ptype == "reasoning":
                    # encrypted_content 解不开，只保留 summary
                    text = _content_to_text(pl.get("summary") or pl.get("content") or [])
                    if self.clean:
                        text = strip_scaffolding(text)
                    if text:
                        ensure_assistant(ts)
                        pending_assistant.blocks.append(ir.Block.thinking_block(text))

                elif ptype == "function_call":
                    cid = pl.get("call_id") or pl.get("id") or ""
                    ensure_assistant(ts)
                    pending_assistant.blocks.append(
                        ir.Block.tool_call(cid, pl.get("name") or "unknown",
                                           pl.get("arguments") or "{}"))

                elif ptype == "function_call_output":
                    ensure_assistant(ts)
                    out = _content_to_text(pl.get("output"))
                    if self.clean:
                        out = strip_scaffolding(out)
                    pending_assistant.blocks.append(
                        ir.Block.tool_result(pl.get("call_id") or "", out or "", False))

                elif ptype == "custom_tool_call":
                    cid = pl.get("call_id") or pl.get("id") or ""
                    ensure_assistant(ts)
                    pending_assistant.blocks.append(
                        ir.Block.tool_call(cid, pl.get("name") or "unknown",
                                           pl.get("input") or ""))

                elif ptype == "custom_tool_call_output":
                    ensure_assistant(ts)
                    out = _content_to_text(pl.get("output"))
                    if self.clean:
                        out = strip_scaffolding(out)
                    pending_assistant.blocks.append(
                        ir.Block.tool_result(pl.get("call_id") or "", out or "", False))

                elif ptype == "web_search_call":
                    ensure_assistant(ts)
                    pending_assistant.blocks.append(
                        ir.Block.tool_call(pl.get("call_id") or pl.get("id") or "",
                                           "WebSearch", json.dumps(pl.get("action") or {}, ensure_ascii=False)))

            # event_msg / token_usage_record 与迁移无关，忽略

            if ts:
                conv.updated_at = iso(ts)

        flush()
        if not conv.id:
            conv.id = os.path.splitext(os.path.basename(path))[0]
        return conv

    # ---------------- 写入 ----------------

    def write(self, conv: ir.Conversation, cwd: str | None = None,
              session_id: str | None = None, remap_tools: bool = True,
              include_thinking: bool = True) -> str:
        import datetime as dt

        target_cwd = (cwd or conv.cwd or os.getcwd()).replace("\\", "/")
        sid = validate_session_id(session_id if session_id is not None else uuid7())
        if session_id is not None and self.find_path(sid):
            raise FileExistsError(f"目标会话已存在: {sid}")
        now = dt.datetime.now(dt.timezone.utc)
        out_path = os.path.join(
            self.home,
            f"{now.year:04d}", f"{now.month:02d}", f"{now.day:02d}",
            f"rollout-{now.strftime('%Y-%m-%dT%H-%M-%S')}-{sid}.jsonl",
        )

        base = now_ms()
        ordinal = 0
        lines: List[str] = []

        # session_meta（普通 dict，先手写，避免被 emit 的 type 推断污染）
        lines.append(json.dumps({
            "timestamp": iso(base),
            "ordinal": ordinal,
            "type": "session_meta",
            "payload": {
                "session_id": sid,
                "id": sid,
                "timestamp": iso(base),
                "cwd": target_cwd,
                "originator": "agent_relay",
                "cli_version": "imported",
                "source": "external-import",
                "thread_source": "user",
                "model_provider": conv.meta.get("model_provider") or "unknown",
            },
        }, ensure_ascii=False))
        ordinal += 1

        lines.append(json.dumps({
            "timestamp": iso(base),
            "ordinal": ordinal,
            "type": "turn_context",
            "payload": {
                "turn_id": uuid7(base),
                "cwd": target_cwd,
                "workspace_roots": [target_cwd],
                "current_date": now.strftime("%Y-%m-%d"),
                "timezone": conv.meta.get("turn_timezone") or "UTC",
                "approval_policy": {"granular": {"sandbox_approval": False, "rules": False}},
                "approvals_reviewer": "user",
                "sandbox_policy": {"type": "workspace-write"},
                "model": conv.model or "unknown",
            },
        }, ensure_ascii=False))
        ordinal += 1

        for turn in conv.turns:
            ts = safe_ms(turn.ts) or (base + ordinal)

            if turn.role == ir.USER:
                texts = [b.text for b in turn.blocks if b.kind in (ir.TEXT, ir.IMAGE) and b.text]
                if not texts:
                    continue
                lines.append(json.dumps({
                    "timestamp": iso(ts), "ordinal": ordinal, "type": "response_item",
                    "payload": {
                        "type": "message", "id": f"msg_{uuid7(ts)}", "role": ir.USER,
                        "content": [{"type": "input_text", "text": "\n".join(texts)}],
                    },
                }, ensure_ascii=False))
                ordinal += 1
                continue

            if turn.role != ir.ASSISTANT:
                continue

            for b in turn.blocks:
                ts_b = ts + (ordinal % 1000)
                if b.kind == ir.THINKING and include_thinking:
                    lines.append(json.dumps({
                        "timestamp": iso(ts_b), "ordinal": ordinal, "type": "response_item",
                        "payload": {"type": "reasoning",
                                    "summary": [{"type": "summary_text", "text": b.text}],
                                    "encrypted_content": None},
                    }, ensure_ascii=False))
                    ordinal += 1
                elif b.kind == ir.TEXT:
                    lines.append(json.dumps({
                        "timestamp": iso(ts_b), "ordinal": ordinal, "type": "response_item",
                        "payload": {"type": "message", "id": f"msg_{uuid7(ts_b)}",
                                    "role": ir.ASSISTANT,
                                    "content": [{"type": "output_text", "text": b.text}]},
                    }, ensure_ascii=False))
                    ordinal += 1
                elif b.kind == ir.TOOL_CALL:
                    name = ToolNameMap.convert(b.name, "codex", remap_tools)
                    lines.append(json.dumps({
                        "timestamp": iso(ts_b), "ordinal": ordinal, "type": "response_item",
                        "payload": {"type": "function_call",
                                    "id": f"fc_{uuid7(ts_b)}",
                                    "name": name,
                                    "arguments": b.arguments or "{}",
                                    "call_id": b.call_id or f"call_{uuid7(ts_b)}"},
                    }, ensure_ascii=False))
                    ordinal += 1
                elif b.kind == ir.TOOL_RESULT:
                    lines.append(json.dumps({
                        "timestamp": iso(ts_b), "ordinal": ordinal, "type": "response_item",
                        "payload": {"type": "function_call_output",
                                    "id": f"fco_{uuid7(ts_b)}",
                                    "call_id": b.call_id, "output": b.output or ""},
                    }, ensure_ascii=False))
                    ordinal += 1

        atomic_write(out_path, lines, overwrite=False)
        return out_path
