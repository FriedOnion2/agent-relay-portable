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
# Codex 只认识配置里存在的 provider；写入未知值会让 thread/resume 直接报错。
DEFAULT_MODEL_PROVIDER = "openai"


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


_ASSISTANT_ITEMS = ("agent_message", "function_call", "function_call_output", "custom_tool_call",
                    "custom_tool_call_output", "web_search_call")


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
        last_role = None
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
            elif rt == "response_item":
                ptype = pl.get("type")
                if ptype == "message":
                    role = pl.get("role")
                    if role == ir.USER:
                        t = _content_to_text(pl.get("content"))
                        if self.clean:
                            t = strip_scaffolding(t)
                        if t and not looks_like_system_prompt(t):
                            turns += 1
                            last_role = ir.USER
                            if not first_user:
                                first_user = ir.summarize_line(t, 60)
                    elif role == ir.ASSISTANT and _content_to_text(pl.get("content")):
                        if last_role != ir.ASSISTANT:
                            turns += 1
                        last_role = ir.ASSISTANT
                elif ptype in _ASSISTANT_ITEMS:
                    # 与 _parse 一致：连续的助手内容（含工具往返）合并为一轮
                    if last_role != ir.ASSISTANT:
                        turns += 1
                    last_role = ir.ASSISTANT
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
                    elif pl.get("encrypted_content"):
                        conv.meta["encrypted_reasoning"] = conv.meta.get("encrypted_reasoning", 0) + 1

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
        if not conv.title:
            conv.title = conv.first_user_text(60)
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
                # 与 Codex 自己写出的会话一致；缺少它时 thread/resume 重建出的 turn 没有 items
                "history_mode": "paginated",
                "model_provider": conv.meta.get("model_provider") or DEFAULT_MODEL_PROVIDER,
            },
        }, ensure_ascii=False))
        ordinal += 1

        def emit(ts_ms: int, kind: str, payload: Dict[str, Any]) -> None:
            nonlocal ordinal
            lines.append(json.dumps({"timestamp": iso(ts_ms), "ordinal": ordinal,
                                     "type": kind, "payload": payload}, ensure_ascii=False))
            ordinal += 1

        # Codex 按 task_started / item_completed / task_complete 重建对话轮次；
        # 只有 response_item 时 thread/read 读不到任何 turn。
        current_turn: Optional[str] = None
        last_ts = base

        def open_turn(ts_ms: int) -> str:
            tid = uuid7(ts_ms)
            emit(ts_ms, "event_msg", {"type": "task_started", "turn_id": tid, "root_turn_id": tid,
                                      "started_at": ts_ms // 1000, "collaboration_mode_kind": "default"})
            emit(ts_ms, "turn_context", {
                "turn_id": tid,
                "root_turn_id": tid,
                "cwd": target_cwd,
                "workspace_roots": [target_cwd],
                "current_date": now.strftime("%Y-%m-%d"),
                "timezone": conv.meta.get("turn_timezone") or "UTC",
                "approval_policy": {"granular": {"sandbox_approval": False, "rules": False}},
                "approvals_reviewer": "user",
                "sandbox_policy": {"type": "workspace-write"},
                "model": conv.model or "unknown",
            })
            return tid

        def close_turn(ts_ms: int, last_message: Optional[str]) -> None:
            nonlocal current_turn
            if current_turn:
                emit(ts_ms, "event_msg", {"type": "task_complete", "turn_id": current_turn,
                                          "last_agent_message": last_message,
                                          "started_at": ts_ms // 1000, "completed_at": ts_ms // 1000})
                current_turn = None

        def item_completed(ts_ms: int, item: Dict[str, Any]) -> None:
            emit(ts_ms, "event_msg", {"type": "item_completed", "thread_id": sid,
                                      "turn_id": current_turn, "item": item,
                                      "started_at_ms": ts_ms, "completed_at_ms": ts_ms})

        last_assistant_text: Optional[str] = None

        for turn in conv.turns:
            ts = safe_ms(turn.ts) or (base + ordinal)

            if turn.role == ir.USER:
                texts = [b.text for b in turn.blocks if b.kind in (ir.TEXT, ir.IMAGE) and b.text]
                if not texts:
                    continue
                close_turn(last_ts, last_assistant_text)
                last_assistant_text = None
                last_ts = ts
                current_turn = open_turn(ts)
                user_text = "\n".join(texts)
                emit(ts, "response_item", {
                    "type": "message", "id": f"msg_{uuid7(ts)}", "role": ir.USER,
                    "content": [{"type": "input_text", "text": user_text}],
                })
                item_completed(ts, {"type": "UserMessage", "id": uuid7(ts),
                                    "content": [{"type": "text", "text": user_text, "text_elements": []}]})
                continue

            if turn.role != ir.ASSISTANT:
                continue
            if current_turn is None:
                last_ts = ts
                current_turn = open_turn(ts)

            for b in turn.blocks:
                ts_b = ts + (ordinal % 1000)
                last_ts = max(last_ts, ts_b)
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
                    item_completed(ts_b, {"type": "AgentMessage", "id": uuid7(ts_b),
                                          "content": [{"type": "Text", "text": b.text}],
                                          "phase": "final_answer"})
                    last_assistant_text = b.text
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

        close_turn(last_ts, last_assistant_text)
        atomic_write(out_path, lines, overwrite=False)
        if conv.title:
            # Codex 的会话名放在 session_index.jsonl（thread_name）；追加一行，不改动已有记录
            with open(self.index_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": sid, "thread_name": conv.title, "updated_at": iso(base)},
                                    ensure_ascii=False) + "\n")
        return out_path
