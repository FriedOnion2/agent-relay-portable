"""DeepSeek Harness event logs: historical export, not active surface replay."""
from __future__ import annotations
import json
import os
import re
from .. import ir
from ..locations import resolve_home
from ..paths import iso, safe_ms
from .base import ReadOnlyAdapter, SessionInfo

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
        raise ValueError("消息 content 必须是文本或块列表")
    out = []
    for b in content or []:
        if not isinstance(b, dict):
            raise ValueError("消息块必须是 JSON 对象")
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
        raise ValueError("DSH 日志超过 32 MiB 读取限制")
    if path.endswith(".zstd"):
        try:
            import zstandard as zstd
        except ImportError:
            raise ValueError("已识别 DSH 压缩会话；请安装 requirements-optional.txt 的 zstandard") from None
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
                        raise ValueError("DSH 解压内容超过 32 MiB 读取限制")
                    decoded.extend(data)
                if not decoder.eof:
                    raise ValueError("DSH 压缩帧不完整，请等会话写入完成后重试")
                offset -= len(decoder.unused_data)
        except zstd.ZstdError as exc:
            raise ValueError("DSH 压缩文件损坏或窗口过大") from exc
        raw = bytes(decoded)
    try:
        records = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    except (ValueError, UnicodeError) as exc:
        raise ValueError("DSH 日志损坏或末行未写完") from exc
    if not records or any(not isinstance(r, dict) for r in records):
        raise ValueError("不是 DSH 会话日志")
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
            raise ValueError("DSH packed chunks 无效")
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


class DshAdapter(ReadOnlyAdapter):
    name = "dsh"
    label = "DeepSeek Harness"

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
                error = "DSH 同一世代有普通和压缩日志，无法确定来源" if len(candidates) != 1 else ""
                if version > 4:
                    error = f"不支持 DSH v{version}；支持 v0–v4"
                yield candidates[0], error

    def discover(self):
        for path, error in self._candidates():
            yield self._peek(path, error) if error else self._cached_summary(path, lambda:self._peek(path))

    def _peek(self, path, error=""):
        st = self._stat(path)
        sid = os.path.relpath(os.path.dirname(path), self.home).replace("\\", "/")
        conv = None
        if not error:
            try:
                conv = self._parse(path)
            except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
                error = str(exc)
        return SessionInfo(self.name, sid, (conv.title if conv else "DSH 会话") or "未命名会话",
                           conv.cwd if conv else "", (conv.model or "") if conv else "",
                           safe_ms(conv.created_at) if conv else None,
                           safe_ms(conv.updated_at) if conv else st["updated_ms"], st["size"],
                           len(conv.turns) if conv else 0, path, not bool(error), error)

    def read(self, sid):
        for path, error in self._candidates():
            identity = os.path.relpath(os.path.dirname(path), self.home).replace("\\", "/")
            if identity == sid:
                if error:
                    raise ValueError(error)
                conv = self._parse(path)
                conv.id = identity
                return conv
        raise FileNotFoundError(f"找不到 DSH 会话: {sid}")

    def _parse(self, path):
        records = read_records(path)
        header = records[0]
        actual = header.get("version")
        if header.get("type") != "session" or not isinstance(header.get("id"), str) or not header["id"] or type(actual) is not int:
            raise ValueError("不是 DSH session header；WorkBuddy 请选独立来源")
        filename = GENERATION.fullmatch(os.path.basename(path))
        expected = int(filename.group(1) or 0) if filename else None
        if actual not in range(5) or (expected is not None and actual != expected):
            raise ValueError("DSH header 版本与文件世代不匹配或尚不支持")
        conv = ir.Conversation(source=self.name, id=str(header["id"]), path=path,
                               cwd=header.get("cwd") or "", created_at=iso(safe_ms(header.get("createdAt"))),
                               meta={"format_version":actual, "header":header,
                                     "notes":["DSH 导出保留事件历史；不等同于压缩、替换后的当前运行上下文。"],
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
                raise ValueError("DSH event seq 不连续或 data 无效")
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
                    raise ValueError("DSH message 必须是 JSON 对象")
                parsed = blocks(message.get("content"))
                if kind == "tool/result" and actual == 4:
                    if message.get("role") != "tool" or not message.get("toolCallId"):
                        raise ValueError("DSH v4 工具结果必须有 tool role 和 toolCallId")
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
