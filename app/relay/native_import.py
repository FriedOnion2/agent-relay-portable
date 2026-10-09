"""Migrate native artifacts between Windows and Ubuntu stores in both directions.

This is intentionally separate from an IR writer: native records, unknown
fields, branch history and tool arguments are retained instead of synthesized.
It never launches an agent or copies account configuration.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import ntpath
import platform
import re
import shlex
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

from .adapters.base import _norm_cwd
from .adapters.workbuddy import WorkBuddyAdapter
from .adapters.dsh import read_records
from .paths import atomic_write, validate_session_id
from .windows import WindowsSource

MAX_BYTES = 32 * 1024 * 1024


def _jsonl(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("原生会话为空或超过 32 MiB，无法完整迁移")
    if not raw.endswith(b"\n"):
        raise ValueError("原生会话末行未完整写入，请关闭源软件后重试")
    try:
        rows = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    except (ValueError, UnicodeError) as exc:
        raise ValueError("原生会话含损坏记录，已停止迁移") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("原生 JSONL 每行必须是对象")
    return rows


def _project_key(cwd):
    # Claude's official SDK sanitizer and signed 32-bit/base36 path hash.
    key = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    if len(key) > 200:
        value = 0
        for char in cwd:
            value = (value * 31 + ord(char)) & 0xFFFFFFFF
        value = abs(value if value < 0x80000000 else value - 0x100000000)
        hashed = ""
        while value:
            hashed = "0123456789abcdefghijklmnopqrstuvwxyz"[value % 36] + hashed
            value //= 36
        key = key[:200] + "-" + (hashed or "0")
    return key


@contextmanager
def _exclusive_lock(path):
    path.open("x").close()
    try:
        yield
    finally:
        path.unlink()


def _claude_project(adapter, cwd):
    indexed = adapter._project_index().get(_norm_cwd(cwd))
    return indexed or _project_key(cwd)


def _units(text):
    encoded = text.encode("utf-16-le", "surrogatepass")
    return [int.from_bytes(encoded[i:i + 2], "little") for i in range(0, len(encoded), 2)]


def dsh_segment(text):
    if text in (".", ".."):
        return "~002E" * len(text)
    return "".join(chr(code) if code < 128 and re.fullmatch(r"[A-Za-z0-9._-]", chr(code))
                   else f"~{code:04X}" for code in _units(text))


def dsh_project(cwd):
    readable, separator = "", False
    for code in _units(cwd):
        char = chr(code)
        if char in "/\\:":
            if not separator:
                readable += "-"
            separator = True
        else:
            readable += char if code < 128 and re.fullmatch(r"[A-Za-z0-9._-]", char) else f"~{code:04X}"
            separator = False
    return "--" + (readable.lstrip("-") or "root")[:251] + "--"


def _inside(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    return path == root or root in path.parents


def _check_destination(path, source):
    profile = getattr(source, "profile", None)
    if (profile and _inside(path, profile)) or any(
            _inside(path, root) or _inside(root, path) for root in source.roots):
        raise ValueError("目标目录与来源重叠，已停止写入；请修正用户目录 / agent_homes / 环境变量")


def _map_path(value, old_cwd, new_cwd):
    if not isinstance(value, str) or not old_cwd:
        return value
    normalized = value.replace("\\", "/")
    old = old_cwd.replace("\\", "/").rstrip("/")
    if _norm_cwd(normalized) == _norm_cwd(old):
        return new_cwd
    windows = len(old) > 1 and old[1] == ":"
    candidate, prefix = (normalized.lower(), old.lower()) if windows else (normalized, old)
    if candidate.startswith(prefix + "/"):
        suffix = normalized[len(old):]
        if "\\" in new_cwd and PureWindowsPath(new_cwd).is_absolute():
            return new_cwd.rstrip("/\\") + suffix.replace("/", "\\")
        return new_cwd.rstrip("/") + suffix
    return value


def _metadata(row, old_cwd, cwd, sid, old_id):
    for key in ("cwd", "workingDirectory", "projectPath", "workspaceRoot"):
        if key in row:
            row[key] = _map_path(row[key], old_cwd, cwd)
    for key in ("workspace_roots", "writable_roots"):
        if isinstance(row.get(key), list):
            row[key] = [_map_path(value, old_cwd, cwd) for value in row[key]]
    for key in ("sessionId", "session_id"):
        if key in row and row[key] == old_id:
            row[key] = sid


def _publish_jsonl(path, rows):
    atomic_write(str(path), [json.dumps(row, ensure_ascii=False) for row in rows], overwrite=False)


def _find_native_id(rows, fallback):
    return next((str(row["sessionId"]) for row in rows if row.get("sessionId")), fallback)


def _native_jsonl(source, target, conv, cwd, requested_id):
    rows = _jsonl(conv.path)
    native = source.source
    old_id = _find_native_id(rows, Path(conv.path).stem) if native in ("workbuddy", "codebuddy") else conv.id
    sid = validate_session_id(requested_id or old_id)
    if requested_id and native in ("claude", "claude_sdk", "codex"):
        try:
            canonical = str(uuid.UUID(requested_id))
        except ValueError:
            canonical = ""
        if canonical != requested_id.lower():
            raise ValueError("Claude / SDK / Codex 的新会话 ID 必须是 UUID，请使用网页的“生成新 ID”")
    if native == "codebuddy":
        writer = WorkBuddyAdapter(home=target.root)
        path = Path(writer.home) / writer.project_dir_for(cwd) / (sid + ".jsonl")
        # CodeBuddy exposes path-prefixed IDs, so check native file basenames.
        if any(Path(row.path).stem == sid for row in target.discover() if row.id.startswith("cli:")):
            raise FileExistsError("目标 CodeBuddy CLI 会话 ID 已存在，请指定新 --session-id")
    else:
        if target.find_path(sid):
            raise FileExistsError("目标会话 ID 已存在，请指定新 --session-id")
        if native in ("claude", "claude_sdk"):
            path = Path(target.home) / _claude_project(target, cwd) / (sid + ".jsonl")
        elif native == "codex":
            now = dt.datetime.now(dt.timezone.utc)
            path = Path(target.home) / now.strftime("%Y/%m/%d") / f"rollout-{now.strftime('%Y-%m-%dT%H-%M-%S')}-{sid}.jsonl"
        else:
            path = Path(target.home) / target.project_dir_for(cwd) / (sid + ".jsonl")
    for row in rows:
        _metadata(row, conv.cwd, cwd, sid, old_id)
        if isinstance(row.get("meta"), dict):
            _metadata(row["meta"], conv.cwd, cwd, sid, old_id)
        if native == "codex" and row.get("type") in ("session_meta", "turn_context"):
            payload = row.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("Codex 会话元信息无效")
            _metadata(payload, conv.cwd, cwd, sid, old_id)
            if row["type"] == "session_meta":
                payload["id"] = sid
                payload["cwd"] = cwd
            else:
                payload["cwd"] = cwd
                if isinstance(payload.get("sandbox_policy"), dict):
                    _metadata(payload["sandbox_policy"], conv.cwd, cwd, sid, old_id)
        elif native in ("claude", "claude_sdk", "workbuddy", "codebuddy") and "cwd" in row:
            # A record may describe an old working directory; only map matching
            # roots, retaining the history of directory changes.
            _metadata(row, conv.cwd, cwd, sid, old_id)
    _check_destination(path, source)
    if native == "codex":
        entry = None
        source_index = Path(source.adapter.index_path)
        if source_index.is_file() and source_index.stat().st_size:
            for row in _jsonl(source_index):
                if str(row.get("id") or row.get("thread_id")) == conv.id:
                    entry = copy.deepcopy(row)
                    for key in ("id", "thread_id"):
                        if key in entry:
                            entry[key] = sid
        if entry:
            root = Path(target.root)
            root.mkdir(parents=True, exist_ok=True)
            with _exclusive_lock(root / ".relay-import.publish-lock"):
                index = Path(target.index_path)
                original = index.read_bytes() if index.exists() else b""
                if len(original) > MAX_BYTES:
                    raise ValueError("目标 Codex 标题索引过大，已停止迁移")
                current = _jsonl(index) if original else []
                if any(str(row.get("id") or row.get("thread_id")) == sid for row in current):
                    raise FileExistsError("目标 Codex 标题索引中已存在此 ID，请指定新 --session-id")
                _publish_jsonl(path, rows)
                try:
                    if (index.read_bytes() if index.exists() else b"") != original:
                        raise ValueError("Codex 标题索引正在变化，请关闭软件后重试")
                    atomic_write(str(index), [json.dumps(row, ensure_ascii=False) for row in [*current, entry]])
                except BaseException:
                    path.unlink()
                    raise
        else:
            _publish_jsonl(path, rows)
    else:
        _publish_jsonl(path, rows)
    return path, sid


def _native_dsh(source, target, conv, cwd, requested_id, compression):
    rows = read_records(conv.path)
    header = rows[0]
    version = header.get("version")
    seeded_v0 = (version == 0 and type(header.get("seedLength")) is int and header["seedLength"] >= 0
                 and header["seedLength"] + 1 < len(rows)
                 and rows[header["seedLength"] + 1].get("type") == "session/end-seed")
    if version != 4 and not seeded_v0:
        raise ValueError("DSH 同软件迁移要求完整 v4 或已关闭的 v0 seed；其他旧世代先用源系统 DSH 升级")
    if (type(header.get("delegationDepth")) is not int or header["delegationDepth"] < 0
            or (version == 4 and type(header.get("isSeeded")) is not bool)):
        raise ValueError("DSH 原生 header 缺少有效 delegationDepth / isSeeded，不能构造可恢复会话")
    allowed = {"type", "version", "id", "createdAt", "cwd", "parentSession", "isSeeded",
               "origin", "delegationDepth", "agentPreset"}
    if seeded_v0:
        allowed.add("seedLength")
    if set(header) - allowed or type(header.get("createdAt")) is not int or header["createdAt"] < 0:
        raise ValueError("DSH header 不符合官方 v4 原生格式")
    sid = validate_session_id(requested_id) if requested_id else header["id"]
    encoded = dsh_segment(sid)
    if not encoded or len(encoded) > 255:
        raise ValueError("DSH 会话 ID 编码超出文件名限制")
    existing = [target.read(row.id).meta["header"]["id"] for row in target.discover() if row.readable]
    if sid in existing:
        raise FileExistsError("目标 DSH 会话 ID 已存在，请指定新 --session-id")
    if any(Path(path).parent.name == encoded for path, _ in target._candidates()):
        raise FileExistsError("目标 DSH 已有相同 ID 的会话目录，即使读取受限也不会覆盖")
    parent = header.get("parentSession")
    if parent and parent not in existing:
        raise ValueError("此 DSH 会话依赖父会话；请先迁移父会话并保留其原 ID")
    if header.get("origin") == "subagent":
        raise ValueError("DSH 子代理会话需要完整主会话关系，暂不单独导入；可以导出 Markdown")
    header.update(id=sid, cwd=cwd)
    directory = Path(target.home) / dsh_project(cwd) / encoded
    _check_destination(directory, source)
    if directory.exists():
        raise FileExistsError("目标 DSH 会话目录已存在")
    filename = ("session.jsonl" if version == 0 else "session.v4.jsonl") + (".zstd" if compression == "zstd" else "")
    path = directory / filename
    if compression == "zstd":
        try:
            import zstandard as zstd
        except ImportError:
            raise ValueError("DSH 原生导入需要 zstandard，请用启动器的 Python 安装 requirements-optional.txt") from None
        compressor = zstd.ZstdCompressor(write_checksum=True)
        # The first independent frame must contain exactly the header line.
        data = compressor.compress((json.dumps(header, ensure_ascii=False) + "\n").encode("utf-8"))
        if len(rows) > 1:
            data += compressor.compress(("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows[1:])).encode("utf-8"))
    else:
        data = ("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)).encode("utf-8")
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir()  # exclusive ownership; never merge into a native session
    temporary = directory / ".session.partial"
    try:
        with temporary.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(str(temporary), str(path))
            temporary.unlink()
        except FileExistsError:
            raise
        except OSError:
            # The exclusively created session directory is owned by this
            # import. FAT/exFAT can publish by rename when links are unavailable.
            if path.exists():
                raise FileExistsError(str(path)) from None
            os.rename(str(temporary), str(path))
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        if path.exists():
            path.unlink()
        directory.rmdir()
        raise
    return path, sid


def _ide_user_workspace(env, old_cwd, cwd):
    if env.get("role") != "user":
        return
    inner = env.get("message")
    encoded = isinstance(inner, str)
    inner = json.loads(inner) if encoded else inner
    if not isinstance(inner, dict):
        return
    for block in inner.get("content", []):
        if not isinstance(block, dict) or not isinstance(block.get("text"), str):
            continue
        text = block["text"]
        if "<user_query>" not in text:
            continue
        prefix, query = text.split("<user_query>", 1)
        def rewrite(match):
            value = match[1].strip()
            return "Workspace Folder: " + (cwd if _norm_cwd(value) == _norm_cwd(old_cwd) else value)
        block["text"] = re.sub(r"Workspace Folder:\s*([^\r\n<]+)", rewrite, prefix) + "<user_query>" + query
    env["message"] = json.dumps(inner, ensure_ascii=False) if encoded else inner


def _native_ide(source, target, conv, cwd, requested_id):
    workspaces = set()
    for row in target.discover():
        if row.readable and row.id.startswith("ide:") and _norm_cwd(row.cwd) == _norm_cwd(cwd):
            workspaces.add(Path(row.path).parent.parent)
    if len(workspaces) != 1:
        raise ValueError("请先在目标系统 CodeBuddy IDE 的目标项目创建一条会话并关闭软件；"
                         "需要唯一匹配的原生工作区，多个 profile 匹配时请显式配置 CodeBuddy Data 根目录")
    workspace = workspaces.pop()
    _check_destination(workspace, source)
    path = Path(conv.path)
    sid = validate_session_id(requested_id or path.parent.name)
    destination = workspace / sid
    manifest = source.adapter._json(str(path))
    source_index = source.adapter._json(str(path.parent.parent / "index.json"))
    entry = next((copy.deepcopy(item) for item in source_index.get("conversations", [])
                  if isinstance(item, dict) and item.get("id") == path.parent.name), None)
    if entry is None:
        raise ValueError("源 CodeBuddy 工作区索引缺少此会话，无法完整迁移")
    entry["id"] = sid
    _metadata(entry, conv.cwd, cwd, sid, path.parent.name)
    _metadata(manifest, conv.cwd, cwd, sid, path.parent.name)
    if manifest.get("id") == path.parent.name:
        manifest["id"] = sid
    documents = {"index.json": manifest}
    for ref in manifest["messages"]:
        mid = validate_session_id(ref["id"])
        env = source.adapter._json(str(path.parent / "messages" / (mid + ".json")))
        _metadata(env, conv.cwd, cwd, sid, path.parent.name)
        _ide_user_workspace(env, conv.cwd, cwd)
        documents["messages/" + mid + ".json"] = env
    index = workspace / "index.json"
    # Native apps must be closed; this lock serializes Relay imports and the
    # snapshot check refuses an observed external edit before publication.
    lock = workspace / ".relay-import.publish-lock"
    with _exclusive_lock(lock):
        stage = None
        published = False
        try:
            original = index.read_bytes()
            current = json.loads(original.decode("utf-8-sig"))
            conversations = current.get("conversations")
            if not isinstance(conversations, list):
                raise ValueError("目标 CodeBuddy 工作区索引格式不支持")
            if destination.exists() or any(isinstance(item, dict) and item.get("id") == sid for item in conversations):
                raise FileExistsError("目标 CodeBuddy IDE 会话已存在，请指定新 --session-id")
            stage = Path(tempfile.mkdtemp(prefix=".relay-", suffix=".partial", dir=str(workspace)))
            for relative, doc in documents.items():
                _publish_jsonl(stage / relative, [doc])
            if index.read_bytes() != original:
                raise ValueError("CodeBuddy 索引正在变化，请关闭软件后重试")
            destination.mkdir()  # refuses even an existing empty session
            published = True
            if (stage / "messages").exists():
                os.rename(str(stage / "messages"), str(destination / "messages"))
            os.rename(str(stage / "index.json"), str(destination / "index.json"))
            conversations.append(entry)
            atomic_write(str(index), [json.dumps(current, ensure_ascii=False)])
            return destination / "index.json", sid
        except BaseException:
            if published:
                shutil.rmtree(destination)
            raise
        finally:
            if stage is not None and stage.exists():
                shutil.rmtree(stage)


def import_windows(agent, sid, cwd, session_id=None, dsh_compression="zstd", preview_token=None):
    source, target, cwd, target_name, target_os = context('import-windows', agent, cwd)
    return _migrate(source, target, sid, cwd, session_id, dsh_compression,
                    'native-windows-import', target_name, target_os, preview_token)


def context(mode, agent, cwd, project_path=None):
    from . import registry
    if mode == 'import-ubuntu':
        from .ubuntu import UbuntuSource
        source = registry.get(agent if agent.startswith('ubuntu_') else 'ubuntu_' + agent)
        if not isinstance(source, UbuntuSource):
            raise ValueError('请选择 Ubuntu 来源')
        return source, registry.get(source.source), _windows_cwd(cwd), source.source, 'Windows'
    if mode == 'export-windows':
        from .windows import selected_profile
        if platform.system() != 'Linux':
            raise ValueError('export-windows 在 Ubuntu / Linux 中运行')
        if agent not in registry._ADAPTERS:
            raise ValueError('请选择本机 agent 来源')
        profile = selected_profile()
        if not profile or not Path(profile).is_dir():
            raise ValueError('请先用 windows-use 选择可访问的 Windows 用户目录')
        local = registry.get(agent)
        source = SimpleNamespace(source=agent, adapter=local, name=agent, read=local.read,
                                 roots=getattr(local, 'roots', [getattr(local, 'root', local.home)]))
        return source, registry.get('windows_' + agent).adapter, _windows_cwd(cwd, project_path), 'windows_' + agent, 'Windows'
    if mode != 'import-windows':
        raise ValueError('未知原生迁移方式')
    source = registry.get(agent if agent.startswith("windows_") else "windows_" + agent)
    if not isinstance(source, WindowsSource):
        raise ValueError("请选择 Windows 来源")
    if not cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
        raise ValueError("需要存在的 Ubuntu 项目目录（--cwd /home/…）")
    cwd = str(Path(cwd).resolve()).replace("\\", "/")
    target = registry.get(source.source)
    return source, target, cwd, source.source, 'Ubuntu'


def _windows_cwd(cwd, project_path=None):
    if not isinstance(cwd, str) or not PureWindowsPath(cwd).is_absolute() or any(ord(c) < 32 for c in cwd):
        raise ValueError("需要 Windows 绝对项目路径，例如 D:\\project，不能填写 Ubuntu 挂载路径")
    cwd = ntpath.normpath(cwd)
    for component in PureWindowsPath(cwd).parts[1:]:
        if re.search(r'[<>:"|?*]', component) or component.endswith((".", " ")):
            raise ValueError("Windows 项目路径含无效文件名字符或结尾")
    if platform.system() == "Windows":
        accessible = Path(cwd)
    else:
        if not project_path or not Path(project_path).is_absolute():
            raise ValueError("在 Ubuntu 写回 Windows 需另填 --project-path：项目在 Ubuntu 中的挂载路径")
        accessible = Path(project_path)
    if not accessible.is_dir():
        raise ValueError("目标项目目录不可访问；请核对 cwd / project_path 和分区挂载")
    return cwd


def export_windows(agent, sid, cwd, project_path=None, session_id=None, dsh_compression="zstd", preview_token=None):
    """On Ubuntu, publish a local session to an explicitly selected Windows home."""
    source, target, cwd, target_name, target_os = context('export-windows', agent, cwd, project_path)
    return _migrate(source, target, sid, cwd, session_id,
                    dsh_compression, 'native-windows-export', target_name, target_os, preview_token)


def import_ubuntu(agent, sid, cwd, session_id=None, dsh_compression="zstd", preview_token=None):
    """On Windows, import an accessible Ubuntu home backup into local native stores."""
    source, target, cwd, target_name, target_os = context('import-ubuntu', agent, cwd)
    return _migrate(source, target, sid, cwd, session_id,
                    dsh_compression, 'native-ubuntu-import', target_name, target_os, preview_token)


def _migrate(source, target, sid, cwd, session_id, dsh_compression, mode, target_name, target_os, preview_token=None):
    if dsh_compression not in ("zstd", "none"):
        raise ValueError("dsh_compression 必须是 zstd 或 none")
    for root in getattr(target, "roots", [getattr(target, "root", target.home)]):
        _check_destination(root, source)
    conv = source.read(sid)
    if conv.truncated:
        raise ValueError("源会话超过读取限制，无法完整迁移")
    from . import preview
    plan = preview.report(conv, target_name, dict(cwd=cwd, session_id=session_id, dsh_compression=dsh_compression), target.home, native=True)
    preview.check_token(preview_token, plan['token'])
    notes = ["已保留原生记录；项目元数据已映射，历史正文与工具参数中的路径不自动替换。",
             "未复制账号、凭据、应用设置、附件或子代理旁路文件；请在目标软件中核对续聊。"]
    from . import oplog, registry
    with oplog.track(mode, registry._write_roots(target), source=source.name, target=target_name,
                     session=sid, title=conv.title) as record:
        if source.source == "dsh":
            path, native_id = _native_dsh(source, target, conv, cwd, session_id, dsh_compression)
        elif source.source == "codebuddy" and conv.meta.get("source_format") == "codebuddy-ide-manifest":
            path, native_id = _native_ide(source, target, conv, cwd, session_id)
            notes.append("CodeBuddy IDE 使用已有原生工作区并更新 conversations 索引；重启软件查看。")
        else:
            path, native_id = _native_jsonl(source, target, conv, cwd, session_id)
        record["path"] = str(path)
    if source.source == "codex":
        notes.append("Codex CLI 可按 ID 恢复；Desktop 的数据库索引未自动更新。")
    if source.source == "claude_sdk":
        notes.append("目标是 SDK 的 Claude 原生共享存储；由你的 SDK 应用设置 resume，创建者仍不可区分。")
    resume = ""
    if source.source in ("claude", "codex"):
        command = "claude --resume" if source.source == "claude" else "codex resume"
        if target_os == "Windows":
            quote = lambda value: "'" + value.replace("'", "''") + "'"
            resume = "Set-Location -LiteralPath " + quote(cwd) + "; if ($?) { " + command + " " + quote(native_id) + " }"
        else:
            resume = "cd -- " + shlex.quote(cwd) + " && " + command + " " + shlex.quote(native_id)
    if source.source == "codebuddy":
        lookup_id = next(row.id for row in target.discover() if Path(row.path).resolve() == Path(path).resolve())
    elif source.source == "dsh":
        lookup_id = str(path.parent.relative_to(Path(target.home))).replace("\\", "/")
    else:
        lookup_id = native_id
    return {"ok": True, "mode": mode, "target_os": target_os,
            "from": {"source": source.name, "id": sid, "path": conv.path, "title": conv.title},
            "to": {"source": target_name, "id": lookup_id, "native_id": native_id,
                   "cwd": cwd, "path": str(path)}, "resume_command": resume,
            "notes": notes, "stats": conv.stats(), "truncated": False, "preview":plan}
