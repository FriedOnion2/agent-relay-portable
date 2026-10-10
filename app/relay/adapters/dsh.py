"""DeepSeek Harness historical log reader and native import adapter."""
from __future__ import annotations

from ..messages import text as message_text, error_text
import json
import os
import re
from .. import ir
from ..locations import resolve_home
from ..paths import iso, safe_ms
from .base import BaseAdapter, SessionInfo

MAX_SCAN_BYTES = 32 * 1024 * 1024
GENERATION = re.compile(r"session(?:\.v([1-9][0-9]*))?\.jsonl(\.zstd)?$")


def json_text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def content_text(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or []
                     if isinstance(b, dict) and b.get("type") == "text")


def blocks(content):
    if isinstance(content, str):
        return [ir.Block.text_block(content)]
    if content is not None and not isinstance(content, list):
        raise ValueError(message_text('err.message_content_must_be_text_or_a_block_list'))
    out = []
    for b in content or []:
        if not isinstance(b, dict):
            raise ValueError(message_text('err.message_blocks_must_be_json_objects'))
        kind = b.get("type")
        if kind == "text":
            out.append(ir.Block.text_block(b.get("text", "")))
        elif kind in ("reasoning", "thinking"):
            out.append(ir.Block.thinking_block(b.get("text") or b.get("thinking", "")))
        elif kind in ("text-chunks", "reasoning-chunks"):
            text = "".join(c if isinstance(c, str) else c.get("text", "") for c in b.get("chunks", []))
            out.append(ir.Block.text_block(text) if kind == "text-chunks" else ir.Block.thinking_block(text))
        elif kind == "tool-call":
            out.append(ir.Block.tool_call(b.get("id") or b.get("toolCallId", ""),
                       b.get("name") or b.get("toolName", ""),
                       json_text(b.get("arguments", b.get("args", {})))))
        elif kind == "tool-result":
            output = content_text(b.get("content")) if "content" in b else json_text(b.get("result"))
            out.append(ir.Block.tool_result(b.get("toolCallId", ""), output, bool(b.get("isError"))))
        elif kind in ("image", "file"):
            out.append(ir.Block(ir.IMAGE if kind == "image" else ir.RAW, meta=b))
        else:
            out.append(ir.Block(ir.RAW, meta=b))
    return out


def read_records(path):
    """Fail closed on corrupt/incomplete logs; bound encoded and decoded data."""
    with open(path, "rb") as f:
        raw = f.read(MAX_SCAN_BYTES + 1)
    if len(raw) > MAX_SCAN_BYTES:
        raise ValueError(message_text('err.dsh_log_exceeds_the_32_mib_read_limit'))
    if path.endswith(".zstd"):
        try:
            import zstandard as zstd
        except ImportError:
            raise ValueError(message_text('err.compressed_dsh_session_detected_install_zstandard_from_requirements_optional_txt')) from None
        decoded = bytearray()
        try:
            offset = 0
            while offset < len(raw):
                decoder = zstd.ZstdDecompressor(max_window_size=MAX_SCAN_BYTES).decompressobj()
                while offset < len(raw) and not decoder.eof:
                    chunk = raw[offset:offset + 256]
                    offset += len(chunk)
                    data = decoder.decompress(chunk)
                    if len(decoded) + len(data) > MAX_SCAN_BYTES:
                        raise ValueError(message_text('err.decompressed_dsh_content_exceeds_the_32_mib_read_limit'))
                    decoded.extend(data)
                if not decoder.eof:
                    raise ValueError(message_text('err.incomplete_dsh_compressed_frame_wait_until_the_session_finishes_writing_and_retry'))
                offset -= len(decoder.unused_data)
        except zstd.ZstdError as exc:
            raise ValueError(message_text('err.dsh_compressed_file_is_corrupt_or_its_window_is_too_large')) from exc
        raw = bytes(decoded)
    try:
        records = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    except (ValueError, UnicodeError) as exc:
        raise ValueError(message_text('err.dsh_log_is_corrupt_or_its_last_line_is_incomplete')) from exc
    if not records or any(not isinstance(r, dict) for r in records):
        raise ValueError(message_text('err.not_a_dsh_session_log'))
    # v0/v1 compact multiple streaming events into one physical row.
    expanded = [records[0]]
    for rec in records[1:]:
        kind = rec.get("type")
        if kind not in ("text-chunks", "reasoning-chunks", "tool-call-chunks"):
            expanded.append(rec)
            continue
        data = rec.get("data") or {}
        values = data.get("args" if kind == "tool-call-chunks" else "texts")
        deltas = data.get("dt")
        if (not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values)
                or not isinstance(deltas, list) or len(deltas) != len(values) - 1):
            raise ValueError(message_text('err.invalid_dsh_packed_chunks'))
        timestamp = rec["time0"]
        for index, value in enumerate(values):
            if index:
                timestamp += deltas[index - 1]
            chunk = {"index":data["index"], "type":"tool-call-delta" if kind == "tool-call-chunks"
                     else "reasoning-delta" if kind == "reasoning-chunks" else "text-delta"}
            if kind == "tool-call-chunks":
                chunk.update(id=data["id"], name=data.get("name", ""), argumentsDelta=value)
            else:
                chunk["text"] = value
            expanded.append({"type":"assistant/chunk", "seq":rec["seq0"] + index, "time":timestamp,
                             "data":{"turn":data["turn"], "step":data["step"], "chunk":chunk}})
    return expanded


class DshAdapter(BaseAdapter):
    name = "dsh"
    label = "DeepSeek Harness"

    def write(self, conv, cwd=None, session_id=None, remap_tools=True, include_thinking=True):
        from .dsh_write import write_native
        return write_native(self.home, conv, cwd, session_id, remap_tools, include_thinking)

    def __init__(self, home=None, clean=True):
        self.root = resolve_home(self.name, home)
        self.home = os.path.join(self.root, "sessions")
        self.clean = clean

    def _candidates(self):
        if not os.path.isdir(self.home):
            return
        for directory, _, filenames in os.walk(self.home):
            generations = {}
            for filename in filenames:
                match = GENERATION.fullmatch(filename)
                if match:
                    generations.setdefault(int(match.group(1) or 0), []).append(os.path.join(directory, filename))
            if generations:
                version = max(generations)
                candidates = sorted(generations[version])
                error = message_text('err.dsh_generation_ambiguous') if len(candidates) != 1 else ""
                if version > 4:
                    error = message_text('err.dsh_version_unsupported', version=version)
                yield candidates[0], error

    def discover(self):
        for path, error in self._candidates():
            yield self._peek(path, error) if error else self._cached_summary(path, lambda path=path: self._peek(path))

    def _peek(self, path, error=""):
        st = self._stat(path)
        sid = os.path.relpath(os.path.dirname(path), self.home).replace("\\", "/")
        conv = None
        if not error:
            try:
                conv = self._parse(path)
            except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
                error = error_text(exc)
        return SessionInfo(self.name, sid, (conv.title if conv else "DSH 会话") or "未命名会话",
                           conv.cwd if conv else "", (conv.model or "") if conv else "",
                           safe_ms(conv.created_at) if conv else None,
                           safe_ms(conv.updated_at) if conv else st["updated_ms"], st["size"],
                           len(conv.turns) if conv else 0, path, not bool(error), error)

    def read(self, sid):
        matches = []
        for path, error in self._candidates():
            identity = os.path.relpath(os.path.dirname(path), self.home).replace("\\", "/")
            if identity == sid or os.path.basename(os.path.dirname(path)) == sid:
                matches.append((path, identity, error))
        if len(matches) > 1:
            raise ValueError(message_text('err.dsh_session_id_matches_multiple_records_use_the_full_id'))
        if matches:
            path, identity, error = matches[0]
            if error:
                raise ValueError(error)
            conv = self._parse(path)
            conv.id = identity
            return conv
        raise FileNotFoundError(message_text('err.dsh_session_not_found_sid', sid=sid))

    def _parse(self, path):
        records = read_records(path)
        header = records[0]
        actual = header.get("version")
        if header.get("type") != "session" or not isinstance(header.get("id"), str) or not header["id"] or type(actual) is not int:
            raise ValueError(message_text('err.not_a_dsh_session_header_select_workbuddy_as_a_separate_source'))
        filename = GENERATION.fullmatch(os.path.basename(path))
        expected = int(filename.group(1) or 0) if filename else None
        if actual not in range(5) or (expected is not None and actual != expected):
            raise ValueError(message_text('err.dsh_header_version_does_not_match_the_file_generation_or_is_unsupported'))
        conv = ir.Conversation(source=self.name, id=str(header["id"]), path=path,
                               cwd=header.get("cwd") or "", created_at=iso(safe_ms(header.get("createdAt"))),
                               meta={"format_version":actual, "header":header,
                                     "notes":[message_text('msg.dsh_export_preserves_event_history_it_does_not_represent_the_current_context_after_compact')],
                                     "export_mode":"historical-events; not active surface replay"})
        seen_calls = set()
        final_steps = {(r["data"].get("turn"), r["data"].get("step")) for r in records[1:]
                       if r.get("type") == "assistant/message" and isinstance(r.get("data"), dict)}
        chunk_turns = {}
        final_calls = {b.get("id") for r in records[1:] if r.get("type") == "assistant/message"
                       for b in ((r.get("data") or {}).get("message") or {}).get("content", [])
                       if isinstance(b, dict) and b.get("type") == "tool-call"}
        for seq, rec in enumerate(records[1:]):
            if type(rec.get("seq")) is not int or rec["seq"] != seq or not isinstance(rec.get("data"), dict):
                raise ValueError(message_text('err.dsh_event_sequence_is_discontinuous_or_data_is_invalid'))
            kind, data = rec.get("type"), rec["data"]
            ts = iso(safe_ms(rec.get("time")))
            if ts:
                conv.updated_at = ts
            if kind == "session/title":
                conv.title = data.get("title") or conv.title
            elif kind == "assistant/chunk":
                key = (data.get("turn"), data.get("step"))
                if key in final_steps:
                    continue
                if key not in chunk_turns:
                    turn = ir.Turn(ir.ASSISTANT, ts=ts, source_type="assistant/chunk")
                    conv.turns.append(turn)
                    chunk_turns[key] = (turn, {})
                turn, indices = chunk_turns[key]
                chunk = data.get("chunk") or {}
                index = chunk.get("index", 0)
                if index not in indices:
                    kind_map = {"text-delta":ir.TEXT, "reasoning-delta":ir.THINKING, "tool-call-delta":ir.TOOL_CALL}
                    block = ir.Block(kind_map.get(chunk.get("type"), ir.RAW), call_id=chunk.get("id", ""),
                                     name=chunk.get("name", ""))
                    indices[index] = block
                    turn.blocks = [indices[i] for i in sorted(indices)]
                block = indices[index]
                block.text += chunk.get("text", "")
                block.arguments += chunk.get("argumentsDelta", "")
                block.name = chunk.get("name") or block.name
                if block.call_id:
                    seen_calls.add(block.call_id)
            elif kind in ("user/message", "assistant/message", "tool/result", "system/message", "developer/message"):
                message = data if kind == "user/message" else data.get("message", {})
                if not isinstance(message, dict):
                    raise ValueError(message_text('err.dsh_message_must_be_a_json_object'))
                parsed = blocks(message.get("content"))
                if kind == "tool/result" and actual == 4:
                    if message.get("role") != "tool" or not message.get("toolCallId"):
                        raise ValueError(message_text('err.dsh_v4_tool_results_require_tool_role_and_toolcallid'))
                    parsed = [ir.Block.tool_result(message.get("toolCallId", ""),
                              content_text(message.get("content")), bool(message.get("isError")))]
                    parsed[0].meta["content"] = message.get("content", [])
                role = ir.ASSISTANT if kind in ("assistant/message", "tool/result") else (
                       ir.USER if kind == "user/message" and (message.get("source") or {}).get("kind", "user") == "user"
                       else ir.SYSTEM)
                model = (message.get("source") or {}).get("model")
                if model:
                    conv.model = model
                filtered = []
                for block in parsed:
                    if block.kind == ir.TOOL_CALL:
                        if block.call_id in seen_calls:
                            continue
                        seen_calls.add(block.call_id)
                    filtered.append(block)
                if filtered:
                    conv.turns.append(ir.Turn(role, filtered, ts=ts, model=model, source_type=kind,
                                             meta={"surfaceOp":rec.get("surfaceOp"), "source":message.get("source")}))
            elif kind == "tool/call" and data.get("callId") not in seen_calls | final_calls:
                seen_calls.add(data.get("callId"))
                conv.turns.append(ir.Turn(ir.ASSISTANT, [ir.Block.tool_call(data.get("callId", ""),
                                  data.get("name", ""), json_text(data.get("arguments", {})))], ts=ts,
                                  source_type=kind))
            else:
                conv.meta.setdefault("events", []).append(rec)
        conv.title = conv.title or conv.first_user_text(60)
        return conv
