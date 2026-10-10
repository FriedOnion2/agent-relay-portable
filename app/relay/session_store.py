"""One native session per package, grouped by agent for device-to-device transfer."""

from .messages import text as message_text, error_text
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
        raise ValueError(message_text('err.community_plugins_only_support_reading_and_conversion_native_session_packaging_is_not_avai'))
    native = getattr(source, "source", source.name)
    adapter = getattr(source, "adapter", source)
    conv = source.read(sid)
    if conv.truncated:
        raise ValueError(message_text('err.source_session_is_incomplete_cannot_save_a_native_storage_package'))
    roots = [Path(value).resolve() for value in getattr(adapter, "roots", [adapter.root])]
    files = {}
    total = 0
    def add(path, data=None):
        nonlocal total
        path = Path(path)
        root_index = next((i for i, base in enumerate(roots) if native_import._inside(path, base)), None)
        if root_index is None:
            raise ValueError(message_text('err.source_session_file_is_outside_the_agent_storage_directory'))
        relative = path.resolve().relative_to(roots[root_index]).as_posix()
        name = "root%d/" % root_index + relative
        if name not in files and len(files) >= archive.MAX_FILES:
            raise ValueError(message_text('err.too_many_files_in_the_session_package'))
        data = archive.read_file(path) if data is None else data
        total += len(data) - (len(files[name][0]) if name in files else 0)
        if total > archive.MAX_TOTAL:
            raise ValueError(message_text('err.original_session_package_files_exceed_256_mib_in_total'))
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
            raise ValueError(message_text('err.codebuddy_workspace_index_lacks_a_unique_session_entry'))
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
                # A ZIP contains only the chosen rollout. Keep its native ID
                # as the lookup key so older v1 package readers can restore it.
                "session":{"id":conv.id if native == "codex" else sid, "selection_id":sid, "native_id":conv.id,
                           "title":conv.title, "cwd":conv.cwd, "format":conv.meta.get("source_format"),
                           "stats":conv.stats()},
                "notes":[message_text('msg.native_session_and_required_title_workspace_indexes_excludes_account_settings_credentials_')]}
    path = archive.storage_root(root) / "conversations" / native / (uuid.uuid4().hex + ".zip")
    if any(native_import._inside(path, base) for base in roots):
        raise ValueError(message_text('err.storage_directory_cannot_be_inside_the_source_agent_data_directory'))
    return archive.write_package(path, manifest, files)


def store_sessions(agent, ids=None, all_sessions=False, root=None):
    ids = list(ids or [])
    if all_sessions and ids:
        raise ValueError(message_text('err.all_cannot_be_used_together_with_specific_session_ids'))
    if all_sessions:
        ids = [row.id for row in registry.get(agent).discover()]
    if not ids:
        raise ValueError(message_text('err.select_session_ids_or_all_no_readable_sessions_found'))
    results, errors = [], []
    for sid in dict.fromkeys(ids):
        try:
            results.append(store_session(agent, sid, root))
        except (OSError, ValueError, KeyError) as exc:
            errors.append({"id":sid, "error":error_text(exc)})
    return {"ok":not errors, "stored":results, "errors":errors}


def restore_session(package, cwd, session_id=None, dsh_compression="zstd", preview_token=None):
    if preview_token:
        from . import preview
        preview.check_token(preview_token, preview.package(package, cwd, session_id, dsh_compression)['token'])
    manifest, files = archive.read_package(package, KIND)
    agent = manifest.get("agent")
    if agent not in registry._ADAPTERS:
        raise ValueError(message_text('err.agent_in_this_package_does_not_support_native_restore'))
    count = manifest.get("root_count")
    session = manifest.get("session")
    if type(count) is not int or count not in (1, 2) or not isinstance(session, dict) or not isinstance(session.get("id"), str):
        raise ValueError(message_text('msg.invalid_session_package_metadata'))
    entry = archive.safe_name(manifest.get("entry"))
    if entry not in files or any(not any(name.startswith("root%d/" % i) for i in range(count)) for name in files):
        raise ValueError(message_text('msg.invalid_session_package_entry_or_agent_root_declaration'))
    system = platform.system()
    if system == "Windows":
        cwd = native_import._windows_cwd(cwd)
    else:
        if not cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
            raise ValueError(message_text('msg.restoring_needs_an_absolute_project_directory_that_exists_on_this_device'))
        cwd = str(Path(cwd).resolve())
    with tempfile.TemporaryDirectory(prefix="agentrelay-session-") as temporary:
        archive.unpack(files, temporary)
        roots = [str(Path(temporary) / ("root%d" % i)) for i in range(count)]
        adapter = registry.get(agent, home=roots[0])
        if agent == "codebuddy":
            adapter.roots = roots
        conv = adapter.read(session["id"])
        if Path(conv.path).resolve() != (Path(temporary) / entry).resolve():
            raise ValueError(message_text('err.session_package_id_does_not_match_the_declared_entry'))
        if not conv.cwd and isinstance(session.get("cwd"), str):
            conv = replace(conv, cwd=session["cwd"])
        source = SimpleNamespace(source=agent, name=manifest.get("source") or agent, adapter=adapter,
                                 roots=roots, read=lambda sid:conv)
        result = native_import._migrate(source, registry.get(agent), session["id"], cwd, session_id,
                        dsh_compression, "native-package-import", agent, system)
    result["from"]["path"] = str(Path(package).resolve())
    result["notes"].append(message_text('msg.session_package_verified'))
    return result
