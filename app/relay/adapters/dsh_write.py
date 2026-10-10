"""Native v0 import, readable by released DSH and its newer format migrations.

History is a closed seed: historical tools have results, never pending work.
Physical headers and each event occupy independent Zstandard frames.
"""

from ..messages import text as message_text
import json
import os
import re
from pathlib import Path

from .. import ir
from ..paths import atomic_write, now_ms, safe_ms, uuid7, validate_session_id
from .base import ToolNameMap

MAX_LOG_BYTES = 32 * 1024 * 1024


def project_key(cwd):
    # Official DSH path encoding operates on UTF-16 code units, including emoji.
    units = cwd.encode("utf-16-le", "surrogatepass")
    result = ""
    separator = False
    for offset in range(0, len(units), 2):
        code = int.from_bytes(units[offset:offset + 2], "little")
        ch = chr(code)
        if ch in "/\\:":
            if not separator:
                result += "-"
            separator = True
        else:
            result += ch if re.fullmatch(r"[A-Za-z0-9._-]", ch) else "~%04X" % code
            separator = False
    return "--" + (result.lstrip("-") or "root")[:251] + "--"


def history_events(conv, include_thinking, remap_tools, created):
    events = []
    timestamp = created
    def event(kind, data, **extra):
        seq = len(events)
        events.append({"type":kind, "seq":seq, "time":timestamp, "data":data, **extra})
        return seq

    event("turn/start", {"turn":1})
    event("step/start", {"turn":1, "step":1})
    # Calls without a subsequent result are kept as text, so resume cannot run
    # unfinished work from the source tool. Duplicate IDs are also downgraded.
    pending = {}
    paired = {}
    used_ids = set()
    for turn in conv.turns:
        for block in turn.blocks:
            if turn.role == ir.ASSISTANT and block.kind == ir.TOOL_CALL and block.call_id and block.name and block.call_id not in used_ids:
                pending[block.call_id] = block
                used_ids.add(block.call_id)
            elif block.kind == ir.TOOL_RESULT and block.call_id in pending:
                call = pending.pop(block.call_id)
                paired[id(call)] = block
                paired[id(block)] = call

    def block_content(block):
        if block.kind == ir.TEXT:
            return {"type":"text", "text":block.text}
        if block.kind == ir.THINKING:
            return {"type":"reasoning", "text":block.text} if include_thinking else None
        if block.kind == ir.TOOL_CALL and id(block) in paired:
            # Arguments remain source history; no target tool is executed.
            return {"type":"tool-call", "id":block.call_id,
                    "name":ToolNameMap.convert(block.name, "dsh", remap_tools), "arguments":block.arguments or "{}"}
        if block.kind == ir.TOOL_CALL:
            text = "[未完成的历史工具调用 %s]\n%s" % (block.name, block.arguments)
        elif block.kind == ir.TOOL_RESULT:
            text = "[历史工具结果 %s%s]\n%s" % (block.call_id, "，错误" if block.is_error else "", block.output)
        else:
            text = "[来源内容块]\n" + json.dumps(block.__dict__, ensure_ascii=False)
        return {"type":"text", "text":text}

    def message(role, content, source):
        return {"id":uuid7(), "role":role, "content":content, "source":source}

    def assistant(content, model):
        chunks = []
        for index, block in enumerate(content):
            chunks.append({"type":"block-start", "index":index, "blockType":block["type"]})
            if block["type"] == "tool-call":
                chunks.append({"type":"tool-call-delta", "index":index, "id":block["id"],
                               "name":block["name"], "argumentsDelta":block["arguments"]})
            else:
                chunks.append({"type":"reasoning-delta" if block["type"] == "reasoning" else "text-delta",
                               "index":index, "text":block["text"]})
            chunks.append({"type":"block-end", "index":index, "block":block})
        chunks.append({"type":"finish", "reason":{"kind":"tool-calls" if any(b["type"] == "tool-call" for b in content) else "stop"}})
        seqs = [event("assistant/chunk", {"turn":1, "step":1, "chunk":chunk}) for chunk in chunks]
        event("assistant/message", {"turn":1, "step":1,
              "message":message("assistant", content, {"kind":"model", "provider":conv.source or "agentrelay-import", "model":model or "imported"})},
              surfaceOp="append", sourceEventSeqs=seqs)
        for block in content:
            if block["type"] == "tool-call":
                event("tool/call", {"turn":1, "step":1, "callId":block["id"], "name":block["name"], "arguments":block["arguments"]})

    for turn in conv.turns:
        timestamp = max(timestamp, safe_ms(turn.ts, timestamp))
        content = []
        for block in turn.blocks:
            if block.kind == ir.TOOL_RESULT and id(block) in paired:
                if content:
                    assistant(content, turn.model or conv.model)
                    content = []
                result = {"type":"tool-result", "toolCallId":block.call_id,
                          "content":[{"type":"text", "text":block.output}], "isError":block.is_error}
                event("tool/result", {"turn":1, "step":1,
                      "message":message("user", [result], {"kind":"tool", "callId":block.call_id})}, surfaceOp="append")
            else:
                converted = block_content(block)
                if converted is not None:
                    content.append(converted)
        if not content:
            continue
        if turn.role == ir.ASSISTANT:
            assistant(content, turn.model or conv.model)
        else:
            source = {"kind":"user"} if turn.role == ir.USER else {"kind":"plugin", "plugin":"agentrelay-import"}
            if turn.role != ir.USER:
                content.insert(0, {"type":"text", "text":"[导入的来源系统上下文]"})
            event("user/message", message("user", content, source), surfaceOp="append")
    event("step/end", {"turn":1, "step":1})
    event("turn/end", {"turn":1, "reason":{"kind":"completed"}})
    event("session/title", {"title":conv.title or conv.first_user_text() or "导入的会话",
                            "messageSeqs":[], "source":{"kind":"user"}})
    event("session/end-seed", {})
    return events


def write_native(home, conv, cwd, session_id, remap_tools, include_thinking):
    if conv.truncated:
        raise ValueError(message_text('err.incomplete_source_session_cannot_be_imported_into_dsh'))
    sid = validate_session_id(session_id if session_id is not None else uuid7())
    target_cwd = cwd if cwd is not None else conv.cwd or os.getcwd()
    if not Path(target_cwd).is_absolute():
        raise ValueError(message_text('err.dsh_target_working_directory_must_be_an_absolute_path_on_this_system_enter_the_target_dire'))
    try:
        import zstandard as zstd
    except ImportError:
        raise ValueError(message_text('err.dsh_import_requires_zstandard_on_mac_run_mac_command_otherwise_install_requirements_option')) from None
    # Start from the source's own clock. Falling back to "now" first would make
    # the max() in history_events() flatten every event to the import time.
    stamps = [safe_ms(t.ts) for t in conv.turns if safe_ms(t.ts)]
    created = safe_ms(conv.created_at) or (min(stamps) if stamps else now_ms())
    events = history_events(conv, include_thinking, remap_tools, created)
    header = {"type":"session", "version":0, "id":sid, "createdAt":created,
              "cwd":target_cwd, "delegationDepth":0, "seedLength":len(events) - 1}
    encoder = zstd.ZstdCompressor(write_checksum=True)
    def frames():
        total = encoded = 0
        for record in [header] + events:
            line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
            total += len(line)
            frame = encoder.compress(line)
            encoded += len(frame)
            if total > MAX_LOG_BYTES or encoded > MAX_LOG_BYTES:
                raise ValueError(message_text('err.generated_dsh_log_exceeds_32_mib_reduce_the_session_before_importing'))
            yield frame
    os.makedirs(home, exist_ok=True)
    lock = os.path.join(home, ".relay-" + sid + ".publish-lock")
    path = os.path.join(home, project_key(target_cwd), sid, "session.jsonl.zstd")
    open(lock, "x").close()
    try:
        for _, dirs, _ in os.walk(home):
            if sid in dirs:
                raise FileExistsError(message_text('err.dsh_session_id_already_exists_sid', sid=sid))
        try:
            atomic_write(path, frames(), encoding=None, overwrite=False)
        except Exception:
            # A failed import must be retryable; remove only its empty dir.
            try:
                os.rmdir(os.path.dirname(path))
            except OSError:
                pass
            raise
    finally:
        os.unlink(lock)
    return path
