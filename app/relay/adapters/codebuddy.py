"""CodeBuddy CLI Tencent JSONL and CN IDE ordered message manifests."""
from __future__ import annotations

from ..messages import text as message_text, error_text
import json
import os
import re
from .. import ir
from ..clean import strip_scaffolding
from ..locations import resolve_home, default_home
from ..paths import iso, safe_ms, validate_session_id
from .base import ReadOnlyAdapter, SessionInfo
from .workbuddy import WorkBuddyAdapter
from .dsh import blocks, json_text

MAX_SCAN_BYTES = 32 * 1024 * 1024


def object_value(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError(message_text('err.codebuddy_message_extra_must_be_a_json_object'))
    return value


class CodeBuddyAdapter(ReadOnlyAdapter, WorkBuddyAdapter):
    name = "codebuddy"
    label = "CodeBuddy"

    def __init__(self, home=None, clean=True):
        self.root = resolve_home(self.name, home)
        explicit = home or os.environ.get("RELAY_CODEBUDDY_HOME") or os.environ.get("CODEBUDDY_HOME")
        self.roots = [self.root] if explicit and explicit.strip() else [self.root, default_home("codebuddy-ide")]
        self.home = self.root
        self.clean = clean

    def available(self):
        return any(os.path.isdir(root) for root in self.roots)

    def info(self):
        result = super().info()
        result["homes"] = self.roots
        return result

    def _candidates(self):
        for root_index, root in enumerate(self.roots):
            projects = os.path.join(root, "projects")
            for path in self._iter_files(projects, "*.jsonl"):
                rel = os.path.relpath(path, root).replace("\\", "/")
                yield f"cli:{root_index}:{rel}", path, "cli"
            for path in self._iter_files(root, "index.json"):
                relative = os.path.relpath(path, root).replace("\\", "/")
                parts = relative.split("/")
                # Only history/<workspace>/<session>/index.json, including nested IDE profiles.
                if len(parts) >= 4 and parts[-4] == "history":
                    yield f"ide:{root_index}:{relative}", path, "ide"

    def _json(self, path, budget=None):
        with open(path, "rb") as f:
            raw = f.read(MAX_SCAN_BYTES + 1)
        if budget is not None:
            budget[0] += len(raw)
        if len(raw) > MAX_SCAN_BYTES or (budget and budget[0] > MAX_SCAN_BYTES):
            raise ValueError(message_text('err.codebuddy_session_exceeds_the_32_mib_read_limit'))
        return object_value(json.loads(raw.decode("utf-8-sig")))

    def discover(self):
        for sid, path, format_name in self._candidates():
            error, conv = "", None
            st = self._stat(path)
            try:
                if format_name == "cli" and not self._peek(path, {}):
                    continue
                conv = self._parse_source(path, format_name)
            except (ValueError, OSError, TypeError, AttributeError, KeyError) as exc:
                error = error_text(exc)
            yield SessionInfo(self.name, sid, (conv.title if conv else "CodeBuddy 会话") or "未命名会话",
                              conv.cwd if conv else "", (conv.model or "") if conv else "",
                              safe_ms(conv.created_at) if conv else None,
                              safe_ms(conv.updated_at) if conv else st["updated_ms"], st["size"],
                              len(conv.turns) if conv else 0, path, not bool(error), error)

    def read(self, sid):
        for identity, path, format_name in self._candidates():
            if identity == sid:
                conv = self._parse_source(path, format_name)
                conv.id = identity
                return conv
        raise FileNotFoundError(message_text('err.codebuddy_session_not_found_sid', sid=sid))

    def _parse_source(self, path, format_name):
        if format_name == "cli":
            conv = WorkBuddyAdapter._parse(self, path)
            conv.meta["source_format"] = "codebuddy-cli-jsonl"
            return conv
        budget = [0]
        manifest = self._json(path, budget)
        refs = manifest.get("messages")
        if not isinstance(refs, list):
            raise ValueError(message_text('err.not_a_codebuddy_ide_session_manifest'))
        directory = os.path.dirname(path)
        conv = ir.Conversation(source=self.name, path=path, id=os.path.basename(directory),
                               meta={"source_format":"codebuddy-ide-manifest"})
        workspace_index = os.path.join(os.path.dirname(directory), "index.json")
        if os.path.isfile(workspace_index):
            workspace = self._json(workspace_index, budget)
            for item in workspace.get("conversations", []):
                if item.get("id") == conv.id:
                    conv.title = item.get("name") or ""
                    conv.model = item.get("selectedModelId")
                    conv.created_at = iso(safe_ms(item.get("createdAt")))
                    break
        seen_results = set()
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("id"), str):
                raise ValueError(message_text('err.invalid_codebuddy_message_reference'))
            msg_id = validate_session_id(ref["id"])
            message_path = os.path.join(directory, "messages", msg_id + ".json")
            if not os.path.isfile(message_path):
                raise ValueError(message_text('err.incomplete_codebuddy_session_a_referenced_message_file_is_missing'))
            env = self._json(message_path, budget)
            inner = object_value(env.get("message") or {})
            extra = object_value(env.get("extra") or {})
            role = env.get("role") or inner.get("role")
            parsed = blocks(inner.get("content"))
            ts = iso(safe_ms(env.get("createdAt")))
            model = extra.get("modelId") or extra.get("modelName")
            if model:
                conv.model = model
            if ts:
                conv.created_at = conv.created_at or ts
                conv.updated_at = ts
            if role == "user":
                text = "\n".join(b.text for b in parsed if b.kind == ir.TEXT)
                cwd = re.search(r"Workspace Folder:\s*([^\r\n<]+)", text)
                if cwd and not conv.cwd:
                    conv.cwd = cwd.group(1).strip().replace("\\", "/")
                source_blocks = extra.get("sourceContentBlocks")
                if source_blocks:
                    parsed = [ir.Block.text_block(b["text"]) for b in source_blocks
                              if isinstance(b, dict) and isinstance(b.get("text"), str)]
                elif self.clean:
                    query = re.search(r"<user_query>([\s\S]*?)</user_query>", text)
                    parsed = [ir.Block.text_block(query.group(1).strip() if query else strip_scaffolding(text))]
            for block in parsed:
                if block.kind == ir.TOOL_RESULT:
                    seen_results.add(block.call_id)
            if parsed:
                conv.turns.append(ir.Turn(ir.ASSISTANT if role == "tool" else role or ir.SYSTEM,
                                  parsed, ts=ts, model=model, source_type="codebuddy-ide-message"))
            for call_id, status in ((extra.get("toolStatus") or {}) if role == "tool" else {}).items():
                if call_id not in seen_results and "result" in status:
                    seen_results.add(call_id)
                    conv.turns.append(ir.Turn(ir.ASSISTANT, [ir.Block.tool_result(call_id,
                                      json_text(status["result"]))], ts=ts, source_type="codebuddy-ide-tool-status"))
        conv.title = conv.title or conv.first_user_text(60)
        return conv
