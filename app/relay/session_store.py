"""One native session per package, grouped by agent for device-to-device transfer."""
import copy
import json
import platform
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from . import archive, registry, native_import
from .paths import iso, validate_session_id

KIND = "agentrelay-session"


def store_session(agent, sid, root=None):
    source = registry.get(agent)
    if source.info().get('community'):
        raise ValueError('社区插件仅支持读取与转换；尚不支持原生会话打包')
    native = getattr(source, "source", source.name)
    adapter = getattr(source, "adapter", source)
    conv = source.read(sid)
    if conv.truncated:
        raise ValueError("源会话读取不完整，不能保存原生存储包")
    roots = [Path(value).resolve() for value in getattr(adapter, "roots", [adapter.root])]
    files = {}
    total = 0
    def add(path, data=None):
        nonlocal total
        path = Path(path)
        root_index = next((i for i, base in enumerate(roots) if native_import._inside(path, base)), None)
        if root_index is None:
            raise ValueError("源会话文件不在 Agent 存储目录内")
        relative = path.resolve().relative_to(roots[root_index]).as_posix()
        name = "root%d/" % root_index + relative
        if name not in files and len(files) >= archive.MAX_FILES:
            raise ValueError("会话包文件过多")
        data = archive.read_file(path) if data is None else data
        total += len(data) - (len(files[name][0]) if name in files else 0)
        if total > archive.MAX_TOTAL:
            raise ValueError("会话包原始文件总大小超过 256 MiB")
        files[name] = (data, False)
        return name
    entry = add(conv.path)
    if native == "codebuddy" and conv.meta.get("source_format") == "codebuddy-ide-manifest":
        path = Path(conv.path)
        manifest = adapter._json(str(path))
        for ref in manifest["messages"]:
            mid = validate_session_id(ref["id"])
            add(path.parent / "messages" / (mid + ".json"))
        workspace_index = path.parent.parent / "index.json"
        index = copy.deepcopy(adapter._json(str(workspace_index)))
        entries = [row for row in index.get("conversations", []) if isinstance(row, dict) and row.get("id") == path.parent.name]
        if len(entries) != 1:
            raise ValueError("CodeBuddy 工作区索引缺少唯一会话条目")
        index["conversations"] = entries
        add(workspace_index, (json.dumps(index, ensure_ascii=False) + "\n").encode("utf-8"))
    if native == "codex":
        path = Path(adapter.index_path)
        if path.is_file() and path.stat().st_size:
            rows = [row for row in native_import._jsonl(path) if str(row.get("id") or row.get("thread_id")) == conv.id]
            if rows:
                add(path, ("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)).encode("utf-8"))
    manifest = {"kind":KIND, "agent":native, "created_at":iso(), "platform":platform.system(),
                "source":agent, "root_count":len(roots), "entry":entry,
                "session":{"id":sid, "title":conv.title, "cwd":conv.cwd, "format":conv.meta.get("source_format"),
                           "stats":conv.stats()},
                "notes":["原生会话及所需标题/工作区索引；不含账号设置、凭据、附件或子代理旁路文件。"]}
    path = archive.storage_root(root) / "conversations" / native / (uuid.uuid4().hex + ".zip")
    if any(native_import._inside(path, base) for base in roots):
        raise ValueError("存储目录不能放在源 Agent 数据目录内")
    return archive.write_package(path, manifest, files)


def store_sessions(agent, ids=None, all_sessions=False, root=None):
    ids = list(ids or [])
    if all_sessions and ids:
        raise ValueError("--all 与指定会话 ID 不能同时使用")
    if all_sessions:
        ids = [row.id for row in registry.get(agent).discover()]
    if not ids:
        raise ValueError("请选择会话 ID 或 --all；没有可读取会话")
    results, errors = [], []
    for sid in dict.fromkeys(ids):
        try:
            results.append(store_session(agent, sid, root))
        except (OSError, ValueError, KeyError) as exc:
            errors.append({"id":sid, "error":str(exc)})
    return {"ok":not errors, "stored":results, "errors":errors}


def restore_session(package, cwd, session_id=None, dsh_compression="zstd", preview_token=None):
    if preview_token:
        from . import preview
        preview.check_token(preview_token, preview.package(package, cwd, session_id, dsh_compression)['token'])
    manifest, files = archive.read_package(package, KIND)
    agent = manifest.get("agent")
    if agent not in registry._ADAPTERS:
        raise ValueError("包中的 Agent 不支持原生恢复")
    count = manifest.get("root_count")
    session = manifest.get("session")
    if type(count) is not int or count not in (1, 2) or not isinstance(session, dict) or not isinstance(session.get("id"), str):
        raise ValueError("会话包元数据无效")
    entry = archive.safe_name(manifest.get("entry"))
    if entry not in files or any(not any(name.startswith("root%d/" % i) for i in range(count)) for name in files):
        raise ValueError("会话包入口或 Agent 根目录声明无效")
    system = platform.system()
    if system == "Windows":
        cwd = native_import._windows_cwd(cwd)
    else:
        if not cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
            raise ValueError("恢复需要当前设备上存在的绝对项目目录")
        cwd = str(Path(cwd).resolve())
    with tempfile.TemporaryDirectory(prefix="agentrelay-session-") as temporary:
        archive.unpack(files, temporary)
        roots = [str(Path(temporary) / ("root%d" % i)) for i in range(count)]
        adapter = registry.get(agent, home=roots[0])
        if agent == "codebuddy":
            adapter.roots = roots
        conv = adapter.read(session["id"])
        if Path(conv.path).resolve() != (Path(temporary) / entry).resolve():
            raise ValueError("会话包 ID 与声明入口不匹配")
        if not conv.cwd and isinstance(session.get("cwd"), str):
            conv = replace(conv, cwd=session["cwd"])
        source = SimpleNamespace(source=agent, name=manifest.get("source") or agent, adapter=adapter,
                                 roots=roots, read=lambda sid:conv)
        result = native_import._migrate(source, registry.get(agent), session["id"], cwd, session_id,
                        dsh_compression, "native-package-import", agent, system)
    result["from"]["path"] = str(Path(package).resolve())
    result["notes"].append("已校验存储包所有文件；同 ID 不覆盖，不自动合并两端新增历史。")
    return result
