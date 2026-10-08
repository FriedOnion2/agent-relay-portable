"""WorkBuddy 会话适配器，与 DeepSeek Harness / CodeBuddy 独立。

存储结构：
    ~/.workbuddy/projects/<cwd-slug>/<sessionId>.jsonl
    ~/.workbuddy/sessions/<pid>.json          （进程元数据，可选）

记录类型：session-meta / ai-title / message / reasoning /
          function_call / function_call_result / file-history-snapshot
"""

from __future__ import annotations

import json
import os
from typing import Dict, Iterable, List, Optional

from .. import ir
from ..clean import strip_scaffolding
from ..locations import resolve_home
from ..paths import iso, read_jsonl, safe_ms, atomic_write, uuid7, now_ms, native_path, validate_session_id
from .base import BaseAdapter, SessionInfo, ToolNameMap

MAX_SCAN_BYTES = 32 * 1024 * 1024


class WorkBuddyAdapter(BaseAdapter):
    name = "workbuddy"
    label = "WorkBuddy"

    def __init__(self, home: str | None = None, clean: bool = True):
        root = resolve_home(self.name, home)
        self.root = root
        self.home = os.path.join(root, "projects")
        self.sessions_meta_dir = os.path.join(root, "sessions")
        self.clean = clean

    # ---------------- 发现 ----------------

    def discover(self) -> Iterable[SessionInfo]:
        cwd_map = self._cwd_from_sessions_meta()
        for path in self._iter_files(self.home, "*.jsonl"):
            info = self._peek(path, cwd_map)
            if info:
                yield info

    def _cwd_from_sessions_meta(self) -> Dict[str, str]:
        """<pid>.json 里记录了 sessionId -> cwd，用来补全 projects 目录缺失的信息。"""
        out: Dict[str, str] = {}
        for p in self._iter_files(self.sessions_meta_dir, "*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("sessionId") and d.get("cwd"):
                    out[d["sessionId"]] = d["cwd"]
            except Exception:
                continue
        return out

    def _peek(self, path: str, cwd_map: Dict[str, str]) -> Optional[SessionInfo]:
        st = self._stat(path)
        sid = os.path.splitext(os.path.basename(path))[0]
        cwd = ""
        title = ""
        model = ""
        created_ms = None
        updated_ms = None
        turns = 0
        first_user = ""
        recognized = False
        for rec, _trunc in read_jsonl(path, MAX_SCAN_BYTES):
            rt = rec.get("type")
            if rt in ("message", "reasoning", "function_call", "function_call_result", "session-meta", "ai-title"):
                recognized = True
            ts = safe_ms(rec.get("timestamp"))
            if rt == "ai-title":
                title = rec.get("aiTitle") or title
            elif rt == "message":
                if not cwd:
                    cwd = rec.get("cwd") or ""
                if not model:
                    model = (rec.get("providerData") or {}).get("model", "")
                if rec.get("role") == ir.USER and not first_user:
                    for b in rec.get("content") or []:
                        t = b.get("text") if isinstance(b, dict) else None
                        if t:
                            first_user = ir.summarize_line(strip_scaffolding(t) if self.clean else t, 60)
                            break
                turns += 1
            elif rt in ("reasoning", "function_call", "function_call_result"):
                if not cwd:
                    cwd = rec.get("cwd") or ""
                if not model:
                    model = (rec.get("providerData") or {}).get("model", "")
                turns += 1
            if ts is not None:
                created_ms = ts if created_ms is None else min(created_ms, ts)
                updated_ms = ts if updated_ms is None else max(updated_ms, ts)
        if not recognized:
            return None
        if not cwd:
            cwd = cwd_map.get(sid, "")
        if not title:
            title = first_user
        return SessionInfo(
            source=self.name, id=sid, title=title or "未命名会话",
            cwd=cwd.replace("\\", "/"), model=model,
            created_ms=created_ms, updated_ms=updated_ms or st["updated_ms"],
            size=st["size"], turns=turns, path=path,
        )

    # ---------------- 读取 ----------------

    def read(self, sid: str) -> ir.Conversation:
        path = self.find_path(sid)
        if not path:
            raise FileNotFoundError(f"找不到 WorkBuddy 会话: {sid}")
        return self._parse(path)

    def _parse(self, path: str) -> ir.Conversation:
        conv = ir.Conversation(
            source=self.name,
            id=os.path.splitext(os.path.basename(path))[0],
            path=path,
            truncated=os.path.getsize(path) > MAX_SCAN_BYTES,
        )
        pending_assistant: Optional[ir.Turn] = None   # 累积同一个 assistant 回合
        call_names: Dict[str, str] = {}              # callId -> tool name

        def flush():
            nonlocal pending_assistant
            if pending_assistant and pending_assistant.blocks:
                conv.turns.append(pending_assistant)
            pending_assistant = None

        def ensure_assistant(ts_ms):
            nonlocal pending_assistant
            if pending_assistant is None:
                pending_assistant = ir.Turn(role=ir.ASSISTANT, ts=iso(ts_ms), source_type=f"{self.name}-turn")

        for rec, truncated in read_jsonl(path, MAX_SCAN_BYTES):
            conv.truncated = conv.truncated or truncated
            rt = rec.get("type")
            ts = safe_ms(rec.get("timestamp"))

            if rt == "session-meta":
                conv.meta.update(rec.get("meta") or {})
                if not conv.created_at:
                    conv.created_at = iso(ts)

            elif rt == "ai-title":
                conv.title = rec.get("aiTitle") or conv.title

            elif rt == "message":
                role = rec.get("role") or ir.USER
                cwd = rec.get("cwd")
                if cwd and not conv.cwd:
                    conv.cwd = cwd.replace("\\", "/")
                model = (rec.get("providerData") or {}).get("model")
                if model and not conv.model:
                    conv.model = model

                blocks: List[ir.Block] = []
                for b in rec.get("content") or (rec.get("message") or {}).get("content") or []:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if bt in ("input_text", "output_text", "text"):
                        text = b.get("text") or ""
                        if self.clean:
                            text = strip_scaffolding(text)
                        if text:
                            blocks.append(ir.Block.text_block(text))

                if not blocks:
                    continue

                if role == ir.USER:
                    flush()
                    # 只有 tool_result 的用户消息也可能是工具回填，这里按纯文本处理即可
                    conv.turns.append(ir.Turn(role=ir.USER, blocks=blocks, ts=iso(ts),
                                              source_type="message"))
                else:
                    ensure_assistant(ts)
                    for blk in blocks:
                        pending_assistant.blocks.append(blk)
                    if model:
                        pending_assistant.model = model

            elif rt == "reasoning":
                raw = rec.get("rawContent") or []
                text = ""
                if isinstance(raw, list):
                    text = "\n\n".join(
                        (x.get("text") or "") for x in raw
                        if isinstance(x, dict) and x.get("type") == "reasoning_text"
                    )
                if not text:
                    text = "\n".join(x.get("text", "") for x in (rec.get("content") or []) if isinstance(x, dict))
                if not text:
                    text = rec.get("text") or ""
                if self.clean:
                    text = strip_scaffolding(text)
                if text:
                    ensure_assistant(ts)
                    pending_assistant.blocks.append(ir.Block.thinking_block(text))

            elif rt == "function_call":
                flush()
                cid = rec.get("callId") or rec.get("id") or ""
                name = rec.get("name") or "unknown"
                args = rec.get("arguments")
                if not isinstance(args, str):
                    args = json.dumps(args or {}, ensure_ascii=False)
                call_names[cid] = name
                ensure_assistant(ts)
                pending_assistant.blocks.append(ir.Block.tool_call(cid, name, args))

            elif rt == "function_call_result":
                cid = rec.get("callId") or ""
                out = rec.get("output")
                if isinstance(out, dict):
                    out = out["text"] if isinstance(out.get("text"), str) else json.dumps(out, ensure_ascii=False)
                elif out is None:
                    out = ""
                elif not isinstance(out, str):
                    out = json.dumps(out, ensure_ascii=False)
                ensure_assistant(ts)
                pending_assistant.blocks.append(
                    ir.Block.tool_result(cid, out or "", is_error=str(rec.get("status")) == "error")
                )
                call_names.pop(cid, None)

            # file-history-snapshot 等直接忽略

            if ts and not conv.updated_at:
                conv.updated_at = iso(ts)
            if ts:
                conv.updated_at = iso(ts)

        flush()

        # Storage directory is not the project's working directory.
        return conv

    # ---------------- 写入 ----------------

    def write(self, conv: ir.Conversation, cwd: str | None = None,
              session_id: str | None = None, remap_tools: bool = True,
              include_thinking: bool = True) -> str:
        target_cwd = (cwd or conv.cwd or os.getcwd()).replace("\\", "/")
        sid = validate_session_id(session_id if session_id is not None else uuid7())
        slug = self.project_dir_for(target_cwd)
        out_path = os.path.join(self.home, slug, f"{sid}.jsonl")
        win_cwd = native_path(target_cwd)

        lines: List[str] = []
        base = now_ms()

        def rid(i: int) -> str:
            return uuid7(base + i)

        # 会话元信息
        lines.append(json.dumps({
            "type": "session-meta", "id": rid(0), "sessionId": sid,
            "timestamp": base, "meta": {"relay.imported-from": conv.source or "unknown"},
        }, ensure_ascii=False))

        if conv.title:
            lines.append(json.dumps({
                "type": "ai-title", "id": rid(1), "timestamp": base + 1,
                "aiTitle": conv.title, "sessionId": sid, "cwd": win_cwd,
            }, ensure_ascii=False))

        seq = 2 if conv.title else 1
        for turn in conv.turns:
            ts = safe_ms(turn.ts) or (base + seq)
            if turn.role == ir.USER:
                texts = [b.text for b in turn.blocks if b.kind in (ir.TEXT, ir.IMAGE) and (b.text or b.media_type)]
                if not texts:
                    continue
                content = [{"type": "input_text" if b.kind != ir.IMAGE else "input_image",
                            "text": b.text} for b in turn.blocks
                           if b.kind in (ir.TEXT, ir.IMAGE) and b.text]
                if not content:
                    continue
                lines.append(json.dumps({
                    "id": rid(seq), "timestamp": ts, "type": "message", "role": ir.USER,
                    "content": content, "sessionId": sid, "cwd": win_cwd,
                }, ensure_ascii=False))
                seq += 1
                continue

            if turn.role != ir.ASSISTANT:
                continue

            for b in turn.blocks:
                ts_b = ts + (seq % 1000)
                if b.kind == ir.THINKING and include_thinking:
                    lines.append(json.dumps({
                        "id": rid(seq), "timestamp": ts_b, "type": "reasoning",
                        "providerData": {"relay.source": conv.source},
                        "content": [], "rawContent": [{"type": "reasoning_text", "text": b.text}],
                        "sessionId": sid, "cwd": win_cwd,
                    }, ensure_ascii=False))
                    seq += 1
                elif b.kind == ir.TEXT:
                    lines.append(json.dumps({
                        "id": rid(seq), "timestamp": ts_b, "type": "message", "role": ir.ASSISTANT,
                        "content": [{"type": "output_text", "text": b.text}],
                        "sessionId": sid, "cwd": win_cwd,
                    }, ensure_ascii=False))
                    seq += 1
                elif b.kind == ir.TOOL_CALL:
                    name = ToolNameMap.convert(b.name, self.name, remap_tools)
                    cid = b.call_id or f"call-{rid(seq)}"
                    lines.append(json.dumps({
                        "id": rid(seq), "timestamp": ts_b, "type": "function_call",
                        "callId": cid, "name": name, "arguments": b.arguments or "{}",
                        "sessionId": sid, "cwd": win_cwd,
                    }, ensure_ascii=False))
                    seq += 1
                elif b.kind == ir.TOOL_RESULT:
                    lines.append(json.dumps({
                        "id": rid(seq), "timestamp": ts_b, "type": "function_call_result",
                        "name": b.meta.get("name", ""), "callId": b.call_id,
                        "status": "error" if b.is_error else "completed",
                        "output": {"type": "text", "text": b.output or ""},
                        "sessionId": sid, "cwd": win_cwd,
                    }, ensure_ascii=False))
                    seq += 1

        atomic_write(out_path, lines, overwrite=False)
        return out_path
