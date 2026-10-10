"""批量迁移：按条件选出多个会话，逐个转换，幂等、可预演、单条失败不拖垮整批。

幂等靠「确定性目标 ID」：目标会话 ID 由 来源 + 源会话 ID + 目标 派生（uuid5），
所以同一批命令重复执行时，已迁移过的会话会被识别并按冲突策略处理，而不是悄悄生成重复会话。
"""

from __future__ import annotations

from .messages import text as message_text, error_text

import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import registry

NAMESPACE = uuid.UUID("5d0f9d2c-7a63-4b57-9d5e-2f3e8c1a6b10")
POLICIES = ("skip", "new", "fail")
MAX_ITEMS = 500


def target_id(source: str, sid: str, target: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "%s\0%s\0%s" % (source, sid, target)))


def select(source: str, ids: Optional[Sequence[str]] = None, keyword: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    if limit < 1:
        raise ValueError(message_text('err.limit_must_be_greater_than_0'))
    limit = min(limit, MAX_ITEMS)
    rows = registry.list_sessions(source, keyword=keyword, limit=10 ** 9)
    if ids:
        wanted = list(dict.fromkeys(ids))
        by_id = {row["id"]: row for row in rows}
        missing = [sid for sid in wanted if sid not in by_id]
        if missing:
            raise ValueError(message_text('err.session_not_found_value', value="、".join(missing[:5])))
        rows = [by_id[sid] for sid in wanted]
    return rows[:limit]


def run(source: str, target: str, ids: Optional[Sequence[str]] = None, keyword: str = "", limit: int = 100,
        cwd: Optional[str] = None, on_conflict: str = "skip", redact_secrets: bool = False,
        remap_tools: bool = True, include_thinking: bool = True, dry_run: bool = True,
        stop_on_error: bool = False, progress: Optional[Callable[[int, int, Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    if on_conflict not in POLICIES:
        raise ValueError(message_text('err.on_conflict_must_be_value', value=" / ".join(POLICIES)))
    registry.get(source)
    dst = registry.get(target)
    if not dst.can_write:
        raise ValueError(message_text('err.label_does_not_support_migration_writes_yet', label=dst.label))
    if source.startswith(("windows_", "ubuntu_")) and not cwd:
        raise ValueError(message_text('err.batch_migration_from_a_cross_system_source_requires_an_existing_local_project_directory'))
    rows = select(source, ids, keyword, limit)
    existing = {row.native_id or row.id for row in dst.discover()}
    items: List[Dict[str, Any]] = []
    stopped = False
    for index, row in enumerate(rows, 1):
        item: Dict[str, Any] = {"id": row["id"], "title": row["title"], "turns": row["turns"]}
        tid = target_id(source, row["id"], target)
        item["target_id"] = tid
        try:
            if tid in existing and on_conflict != "new":
                if on_conflict == "fail":
                    raise FileExistsError(message_text('err.a_migration_result_for_this_source_session_already_exists_tid', tid=tid))
                item["status"] = "skipped"
                item["reason"] = message_text('msg.batch_already_migrated', tid=tid)
            elif row.get("error"):
                item["status"] = "failed"
                item["error"] = message_text('err.source_unreadable', detail=error_text(row['error']))
            elif dry_run:
                item["status"] = "would-migrate"
            else:
                use_id = None if (tid in existing) else tid
                result = registry.transfer(source, row["id"], target, cwd=cwd, session_id=use_id,
                                           remap_tools=remap_tools, include_thinking=include_thinking,
                                           redact_secrets=redact_secrets)
                item["status"] = "migrated"
                item["path"] = result["to"]["path"]
                if use_id is None:
                    item["target_id"] = None
                existing.add(tid)
        except Exception as exc:  # 单条失败只记录，除非要求遇错即停
            item["status"] = "failed"
            item["error"] = error_text(exc)
        items.append(item)
        if progress:
            progress(index, len(rows), item)
        if item["status"] == "failed" and (stop_on_error or on_conflict == "fail"):
            stopped = True
            break
    counts = {key: sum(1 for item in items if item["status"] == key) for key in ("migrated", "would-migrate", "skipped", "failed")}
    return {"ok": counts["failed"] == 0, "dry_run": dry_run, "source": source, "target": target, "selected": len(rows),
            "processed": len(items), "stopped_early": stopped, "on_conflict": on_conflict, **counts, "items": items}
