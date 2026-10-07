"""Claude Code 会话适配器。

存储结构：
    ~/.claude/projects/<cwd-slug>/<sessionId>.jsonl

记录是一条"扁平 + 链式 parentUuid"的结构：
    {"type":"user"|"assistant"|"summary", "uuid":..., "parentUuid":...,
     "sessionId":..., "cwd":..., "timestamp":..., "message":{...}, ...}
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional

from .. import ir
from ..clean import strip_scaffolding
from ..paths import iso, read_jsonl, safe_ms, slug_for, atomic_write, uuid7, now_ms, validate_session_id
from .base import BaseAdapter, SessionInfo, ToolNameMap

MAX_SCAN_BYTES = 32 * 1024 * 1024


def _iter_content(msg: Dict[str, Any]) -> List[Dict[str, Any]]:
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    if isinstance(c, list):
        return [x for x in c if isinstance(x, dict)]
    return []


def _stringify_tool_result(x: Any) -> str:
    """tool_result 的 content 可能是字符串或块数组，统一成字符串。"""
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        parts = []
        for b in x:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text") or "")
                else:
                    parts.append(json.dumps(b, ensure_ascii=False))
        return "\n".join(p for p in parts if p)
    if x is None:
        return ""
    return json.dumps(x, ensure_ascii=False)


class ClaudeAdapter(BaseAdapter):
    name = "claude"
    label = "Claude Code"

    def __init__(self, home: str | None = None, clean: bool = True):
        root = (home
                or os.environ.get("RELAY_CLAUDE_HOME")
                or os.environ.get("CLAUDE_CONFIG_DIR")
                or os.path.expanduser(os.path.join("~", ".claude")))
        self.root = root
        self.home = os.path.join(root, "projects")
        self.clean = clean

    # ---------------- 发现 ----------------

    def discover(self) -> Iterable[SessionInfo]:
        for path in self._iter_files(self.home, "*.jsonl"):
            info = self._peek(path)
            if info:
                yield info

    def _peek(self, path: str) -> Optional[SessionInfo]:
        st = self._stat(path)
        sid = os.path.splitext(os.path.basename(path))[0]
        title = ""
        model = ""
        cwd = ""
        created_ms = None
        updated_ms = None
        turns = 0
        first_user = ""
        for rec, _trunc in read_jsonl(path, MAX_SCAN_BYTES):
            rt = rec.get("type")
            ts = safe_ms(rec.get("timestamp"))
            if rt == "summary" and not title:
                title = rec.get("summary") or ""
            elif rt in ("user", "assistant"):
                msg = rec.get("message") or {}
                if not cwd:
                    cwd = rec.get("cwd") or ""
                if not model:
                    model = msg.get("model") or ""
                if rt == "user" and msg.get("role") == ir.USER and not first_user:
                    for b in _iter_content(msg):
                        if b.get("type") == "text":
                            t = b.get("text") or ""
                            first_user = ir.summarize_line(strip_scaffolding(t) if self.clean else t, 60)
                            break
                turns += 1
            if ts is not None:
                created_ms = ts if created_ms is None else min(created_ms, ts)
                updated_ms = ts if updated_ms is None else max(updated_ms, ts)
        return SessionInfo(
            source=self.name, id=sid, title=title or first_user or "未命名会话",
            cwd=cwd.replace("\\", "/"), model=model,
            created_ms=created_ms, updated_ms=updated_ms or st["updated_ms"],
            size=st["size"], turns=turns, path=path,
        )

    # ---------------- 读取 ----------------

    def read(self, sid: str) -> ir.Conversation:
        path = self.find_path(sid)
        if not path:
            raise FileNotFoundError(f"找不到 Claude 会话: {sid}")
        return self._parse(path)

    def _parse(self, path: str) -> ir.Conversation:
        conv = ir.Conversation(
            source=self.name,
            id=os.path.splitext(os.path.basename(path))[0],
            path=path,
            truncated=os.path.getsize(path) > MAX_SCAN_BYTES,
        )
        for rec, truncated in read_jsonl(path, MAX_SCAN_BYTES):
            conv.truncated = conv.truncated or truncated
            rt = rec.get("type")
            ts = safe_ms(rec.get("timestamp"))
            if not conv.cwd and rec.get("cwd"):
                conv.cwd = rec["cwd"].replace("\\", "/")
            if not conv.created_at and ts:
                conv.created_at = iso(ts)
            if ts:
                conv.updated_at = iso(ts)
            if rt == "summary" and not conv.title:
                conv.title = rec.get("summary") or ""
                continue
            if rt not in ("user", "assistant"):
                continue

            msg = rec.get("message") or {}
            role = msg.get("role") or rt
            model = msg.get("model")
            if model and not conv.model:
                conv.model = model

            blocks: List[ir.Block] = []
            tool_ids: List[str] = []
            for b in _iter_content(msg):
                bt = b.get("type")
                if bt == "text":
                    text = b.get("text") or ""
                    if self.clean:
                        text = strip_scaffolding(text)
                    if text:
                        blocks.append(ir.Block.text_block(text))
                elif bt == "thinking":
                    text = b.get("thinking") or ""
                    if self.clean:
                        text = strip_scaffolding(text)
                    if text:
                        blocks.append(ir.Block.thinking_block(text))
                elif bt == "tool_use":
                    cid = b.get("id") or ""
                    tool_ids.append(cid)
                    args = b.get("input")
                    if not isinstance(args, str):
                        args = json.dumps(args or {}, ensure_ascii=False)
                    blocks.append(ir.Block.tool_call(cid, b.get("name") or "unknown", args))
                elif bt == "tool_result":
                    out = _stringify_tool_result(b.get("content"))
                    if self.clean:
                        out = strip_scaffolding(out)
                    blk = ir.Block.tool_result(b.get("tool_use_id") or "", out,
                                               is_error=bool(b.get("is_error")))
                    blocks.append(blk)
                elif bt == "image":
                    src = b.get("source") or {}
                    data = src.get("data") if isinstance(src, dict) else None
                    blocks.append(ir.Block(kind=ir.IMAGE,
                                           media_type=src.get("media_type", "image/png") if isinstance(src, dict) else "image/png",
                                           text=data or "", meta={"source": src}))

            if not blocks:
                continue
            # 工具结果在 Claude 中存为 user；在 IR 中属于助手动作。
            # 混合消息按连续角色分组，保留工具结果和真实用户文字的顺序。
            default_role = role if role in (ir.USER, ir.ASSISTANT, ir.SYSTEM) else ir.USER
            grouped = []
            for block in blocks:
                block_role = ir.ASSISTANT if block.kind == ir.TOOL_RESULT else default_role
                if grouped and grouped[-1].role == block_role:
                    grouped[-1].blocks.append(block)
                else:
                    grouped.append(ir.Turn(role=block_role, blocks=[block], ts=iso(ts),
                                           model=model, source_type=rt))
            conv.turns.extend(grouped)
        return conv

    # ---------------- 写入 ----------------

    def write(self, conv: ir.Conversation, cwd: str | None = None,
              session_id: str | None = None, remap_tools: bool = True,
              include_thinking: bool = True) -> str:
        target_cwd = (cwd or conv.cwd or os.getcwd()).replace("\\", "/")
        sid = validate_session_id(session_id if session_id is not None else uuid7())
        slug = self.project_dir_for(target_cwd)
        out_path = os.path.join(self.home, slug, f"{sid}.jsonl")

        base = now_ms()
        seq = 0

        def rid() -> str:
            nonlocal seq
            seq += 1
            return uuid7(base + seq)

        def base_record(uuid: str, parent: Optional[str], ts_ms: int) -> Dict[str, Any]:
            return {
                "parentUuid": parent,
                "isSidechain": False,
                "userType": "external",
                "cwd": target_cwd,
                "sessionId": sid,
                "version": "1.0.62",
                "type": "user",
                "uuid": uuid,
                "timestamp": iso(ts_ms),
            }

        lines: List[str] = []
        parent: Optional[str] = None

        if conv.title or conv.meta.get("summary"):
            lines.append(json.dumps({
                "type": "summary",
                "summary": conv.title or conv.meta.get("summary"),
                "leafUuid": "",
            }, ensure_ascii=False))

        for turn in conv.turns:
            ts = safe_ms(turn.ts) or base + seq
            uid = rid()
            if turn.role == ir.USER:
                content = [{"type": "text", "text": b.text} for b in turn.blocks
                           if b.kind in (ir.TEXT, ir.IMAGE) and b.text]
                if not content:
                    continue
                rec = base_record(uid, parent, ts)
                rec["message"] = {"role": ir.USER, "content": content}
                lines.append(json.dumps(rec, ensure_ascii=False))
                parent = uid
                continue

            if turn.role != ir.ASSISTANT:
                continue

            content: List[Dict[str, Any]] = []

            def flush_content():
                nonlocal parent, content
                if not content:
                    return
                assistant_id = rid()
                rec = base_record(assistant_id, parent, ts)
                rec["type"] = "assistant"
                rec["message"] = {
                    "role": ir.ASSISTANT,
                    "model": turn.model or conv.model or "unknown",
                    "id": f"msg_{assistant_id}", "type": "message", "content": content,
                    "stop_reason": "tool_use" if content[-1]["type"] == "tool_use" else "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                }
                lines.append(json.dumps(rec, ensure_ascii=False))
                parent = assistant_id
                content = []

            for b in turn.blocks:
                if b.kind == ir.THINKING and include_thinking:
                    content.append({"type": "thinking", "thinking": b.text, "signature": ""})
                elif b.kind == ir.TEXT:
                    if content and content[-1].get("type") == "text":
                        content[-1]["text"] += "\n\n" + b.text
                    else:
                        content.append({"type": "text", "text": b.text})
                elif b.kind == ir.TOOL_CALL:
                    name = ToolNameMap.convert(b.name, "claude", remap_tools)
                    try:
                        inp = json.loads(b.arguments) if b.arguments else {}
                    except Exception:
                        inp = {"_raw": b.arguments}
                    content.append({"type": "tool_use", "id": b.call_id or f"toolu_{uid}",
                                    "name": name, "input": inp})
                elif b.kind == ir.TOOL_RESULT:
                    # 先写前面的助手块，工具结果即使独占一轮也必须写入。
                    flush_content()
                    rid_res = rid()
                    rec2 = base_record(rid_res, parent, ts)
                    rec2["message"] = {"role": ir.USER, "content": [
                        {"type": "tool_result", "tool_use_id": b.call_id,
                         "content": b.output or "", "is_error": bool(b.is_error)}
                    ]}
                    rec2["toolUseResult"] = {"stdout": b.output or "", "stderr": "",
                                             "interrupted": False, "isImage": False}
                    lines.append(json.dumps(rec2, ensure_ascii=False))
                    parent = rid_res
            flush_content()

        atomic_write(out_path, lines, overwrite=False)
        return out_path
