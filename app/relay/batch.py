"""批量迁移：按条件选出多个会话，逐个转换，幂等、可预演、单条失败不拖垮整批。

幂等靠「确定性目标 ID」：目标会话 ID 由 来源 + 源会话 ID + 目标 派生（uuid5），
所以同一批命令重复执行时，已迁移过的会话会被识别并按冲突策略处理，而不是悄悄生成重复会话。
"""

from __future__ import annotations

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
        raise ValueError("limit 必须大于 0")
    limit = min(limit, MAX_ITEMS)
    rows = registry.list_sessions(source, keyword=keyword, limit=10 ** 9)
    if ids:
        wanted = list(dict.fromkeys(ids))
        by_id = {row["id"]: row for row in rows}
        missing = [sid for sid in wanted if sid not in by_id]
        if missing:
            raise ValueError("找不到会话：" + "、".join(missing[:5]))
        rows = [by_id[sid] for sid in wanted]
    return rows[:limit]


def run(source: str, target: str, ids: Optional[Sequence[str]] = None, keyword: str = "", limit: int = 100,
        cwd: Optional[str] = None, on_conflict: str = "skip", redact_secrets: bool = False,
        remap_tools: bool = True, include_thinking: bool = True, dry_run: bool = True,
        stop_on_error: bool = False, progress: Optional[Callable[[int, int, Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    if on_conflict not in POLICIES:
        raise ValueError("on_conflict 必须是 " + " / ".join(POLICIES))
    registry.get(source)
    dst = registry.get(target)
    if not dst.can_write:
        raise ValueError("%s 尚不支持作为迁移目标" % dst.label)
    if source.startswith(("windows_", "ubuntu_")) and not cwd:
        raise ValueError("从跨系统来源批量迁出需指定存在的本机项目目录")
    rows = select(source, ids, keyword, limit)
    existing = {row.id for row in dst.discover()}
    items: List[Dict[str, Any]] = []
    stopped = False
    for index, row in enumerate(rows, 1):
        item: Dict[str, Any] = {"id": row["id"], "title": row["title"], "turns": row["turns"]}
        tid = target_id(source, row["id"], target)
        item["target_id"] = tid
        try:
            if tid in existing and on_conflict != "new":
                if on_conflict == "fail":
                    raise FileExistsError("目标已存在同一来源会话的迁移结果：" + tid)
                item["status"] = "skipped"
                item["reason"] = "已迁移过（目标 ID %s 已存在）" % tid
            elif row.get("error"):
                item["status"] = "failed"
                item["error"] = "源会话不可读：" + str(row["error"])
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
            item["error"] = str(exc)
        items.append(item)
        if progress:
            progress(index, len(rows), item)
        if item["status"] == "failed" and (stop_on_error or on_conflict == "fail"):
            stopped = True
            break
    counts = {key: sum(1 for item in items if item["status"] == key) for key in ("migrated", "would-migrate", "skipped", "failed")}
    return {"ok": counts["failed"] == 0, "dry_run": dry_run, "source": source, "target": target, "selected": len(rows),
            "processed": len(items), "stopped_early": stopped, "on_conflict": on_conflict, **counts, "items": items}
