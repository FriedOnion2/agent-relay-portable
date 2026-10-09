"""操作记录与撤销。

每次写入目标软件的迁移 / 恢复都在写入前后对目标目录做文件快照（只看路径、大小、修改时间），记下新建的文件、
新建的目录和被追加内容的文件（例如 Codex 的 session_index.jsonl）。撤销只删除「仍和写入时一模一样」的新建文件，
并把追加过的文件截回原长度；写入之后被用户续聊、改动过的文件不会被删除，而是原样保留并说明原因。

记录保存在 logs/operations.jsonl（可用 RELAY_LOG_HOME 改目录），每行一个 JSON。撤销也追加一行，不改写旧记录。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List

from . import paths
from .runtime import project_root

LOG_NAME = "operations.jsonl"
MAX_FILES_SCANNED = 300_000     # 目标目录文件数超过这个值就不跟踪（避免每次写入都扫描巨大目录）
MAX_RECORDED = 500              # 单次操作最多记录的新建文件数；超过则标记为不可撤销
HASH_LIMIT = 64 * 1024 * 1024   # 超过这个大小的新建文件只比对大小与修改时间
READ_LINES = 5000

_lock = threading.Lock()


def log_path() -> Path:
    base = os.environ.get("RELAY_LOG_HOME")
    return (Path(base).expanduser() if base else project_root() / "logs") / LOG_NAME


# ---------------- 快照 ----------------

def _scan(roots: Iterable[str]):
    """返回 (files, dirs, complete)。files: 路径 -> (大小, mtime_ns)；不跟随符号链接。"""
    files: Dict[str, tuple] = {}
    dirs = set()
    complete = True
    for root in roots:
        if not root:
            continue
        try:
            if not stat.S_ISDIR(os.stat(root).st_mode):
                continue
        except FileNotFoundError:
            continue  # A missing destination can legitimately be created by the write.
        except OSError:
            complete = False
            continue
        stack = [os.path.abspath(root)]
        while stack:
            current = stack.pop()
            dirs.add(current)
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(entry.path)
                            elif entry.is_file(follow_symlinks=False):
                                info = entry.stat(follow_symlinks=False)
                                files[entry.path] = (info.st_size, info.st_mtime_ns)
                        except OSError:
                            complete = False
                            continue
            except OSError:
                complete = False
                continue
            if len(files) > MAX_FILES_SCANNED:
                return files, dirs, False
    return files, dirs, complete


def _sha256(path: str) -> str | None:
    try:
        if os.path.getsize(path) > HASH_LIMIT:
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


# ---------------- 记录 ----------------

def _append(entry: Dict[str, Any]) -> None:
    path = log_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_entries() -> List[Dict[str, Any]]:
    path = log_path()
    if not path.exists():
        return []
    with _lock:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-READ_LINES:]
    entries = []
    for line in lines:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            entries.append(value)
    return entries


@contextlib.contextmanager
def track(kind: str, roots: Iterable[str | None], **meta: Any):
    """包住一次写入：结束时把新建 / 追加的文件记入日志。yield 的字典可补充 path 等信息。"""
    roots = [os.path.abspath(str(root)) for root in roots if root]
    record: Dict[str, Any] = {"id": paths.short_id("op-", 12), "time": paths.iso(), "kind": kind,
                              "roots": roots, **meta}
    before_files, before_dirs, complete = _scan(roots)
    try:
        yield record
    except BaseException as error:
        _finish(record, before_files, before_dirs, complete, roots, "failed", str(error))
        raise
    _finish(record, before_files, before_dirs, complete, roots, "ok", "")


def _finish(record, before_files, before_dirs, complete, roots, status, error):
    try:
        after_files, after_dirs, after_complete = _scan(roots)
        created, appended, other = [], [], []
        for path, (size, mtime) in after_files.items():
            old = before_files.get(path)
            if old is None:
                created.append({"path": path, "size": size, "mtime_ns": mtime, "sha256": _sha256(path)})
            elif old != (size, mtime):
                if size > old[0]:
                    appended.append({"path": path, "size_before": old[0], "size_after": size, "mtime_ns": mtime})
                else:
                    other.append(path)
        record.update(status=status, error=error,
                      created=created[:MAX_RECORDED], appended=appended[:MAX_RECORDED],
                      created_dirs=sorted(after_dirs - before_dirs, key=len, reverse=True)[:MAX_RECORDED],
                      modified_other=other[:50])
        record["undoable"] = bool(complete and after_complete and len(created) <= MAX_RECORDED
                                  and len(appended) <= MAX_RECORDED and not other)
        if not record["undoable"]:
            reasons = []
            if not (complete and after_complete):
                reasons.append("目标目录扫描不完整（读取失败或文件过多），无法安全撤销")
            if len(created) > MAX_RECORDED or len(appended) > MAX_RECORDED:
                reasons.append("变化的文件过多")
            if other:
                reasons.append("有已有文件被改写（不是追加）")
            record["undo_blocked"] = "；".join(reasons)
        if status == "failed" and not (created or appended or other):
            return                      # 校验失败、什么都没写：不留记录
        _append(record)
    except Exception:                    # 记录失败不能影响迁移本身
        return


# ---------------- 查询 ----------------

def list_operations(limit: int = 100) -> List[Dict[str, Any]]:
    entries = _read_entries()
    undone = {e.get("undo_of"): e for e in entries if e.get("undo_of")}
    rows = []
    for entry in entries:
        if entry.get("undo_of") or not entry.get("id"):
            continue
        undo = undone.get(entry["id"])
        rows.append({
            "id": entry["id"], "time": entry.get("time"), "kind": entry.get("kind"),
            "source": entry.get("source"), "target": entry.get("target"), "session": entry.get("session"),
            "title": entry.get("title"), "path": entry.get("path"), "status": entry.get("status"),
            "error": entry.get("error") or "",
            "created": [row["path"] for row in entry.get("created", [])],
            "appended": [row["path"] for row in entry.get("appended", [])],
            "undoable": bool(entry.get("undoable")) and not undo and bool(entry.get("created") or entry.get("appended")),
            "undo_blocked": entry.get("undo_blocked", ""),
            "undone": {"time": undo.get("time"), "removed": undo.get("removed"), "kept": undo.get("kept")} if undo else None,
        })
    rows.reverse()
    return rows[:max(1, min(int(limit), 1000))]


# ---------------- 撤销 ----------------

def _inside(path: str, roots: List[str]) -> bool:
    real = os.path.realpath(path)
    for root in roots:
        base = os.path.realpath(root)
        if real != base and real.startswith(base + os.sep):
            return True
    return False


def undo(op_id: str, force: bool = False) -> Dict[str, Any]:
    entries = _read_entries()
    entry = next((e for e in entries if e.get("id") == op_id and not e.get("undo_of")), None)
    if not entry:
        raise KeyError("找不到这条操作记录")
    if any(e.get("undo_of") == op_id for e in entries):
        raise ValueError("这条操作已经撤销过")
    if not entry.get("undoable"):
        raise ValueError("这条操作不能自动撤销：" + (entry.get("undo_blocked") or "没有记录到文件变化"))
    roots = entry.get("roots") or []
    removed, kept, truncated = [], [], []

    for row in entry.get("created", []):
        path = row["path"]
        if not _inside(path, roots):
            kept.append({"path": path, "reason": "不在记录的目标目录内，已跳过"})
            continue
        if not os.path.lexists(path):
            continue
        if os.path.islink(path) or not os.path.isfile(path):
            kept.append({"path": path, "reason": "不再是普通文件，已跳过"})
            continue
        info = os.stat(path)
        same = info.st_size == row["size"] and (row.get("sha256") is None and info.st_mtime_ns == row["mtime_ns"]
                                                or row.get("sha256") is not None and _sha256(path) == row["sha256"])
        if not same and not force:
            kept.append({"path": path, "reason": "写入后又被修改（可能已在目标软件里续聊），为避免丢失新内容未删除"})
            continue
        os.remove(path)
        removed.append(path)

    for row in entry.get("appended", []):
        path = row["path"]
        if not _inside(path, roots) or not os.path.isfile(path) or os.path.islink(path):
            kept.append({"path": path, "reason": "文件不存在或不在目标目录内，已跳过"})
            continue
        info = os.stat(path)
        if info.st_size != row["size_after"] or info.st_mtime_ns != row["mtime_ns"]:
            kept.append({"path": path, "reason": "写入后又被修改，未截回原长度"})
            continue
        with open(path, "r+b") as handle:
            handle.truncate(row["size_before"])
        truncated.append(path)

    for directory in entry.get("created_dirs", []):       # 已按路径长度从深到浅排序
        if _inside(directory, roots) or directory in roots:
            with contextlib.suppress(OSError):
                if not os.listdir(directory):
                    os.rmdir(directory)

    outcome = {"undo_of": op_id, "time": paths.iso(), "removed": removed, "truncated": truncated, "kept": kept}
    if not kept:
        _append(outcome)
    else:
        outcome["partial"] = True
        # 部分撤销也记一行，但保留可再次尝试：不写 undo_of
        _append({"note_of": op_id, **{k: v for k, v in outcome.items() if k != "undo_of"}})
    return {"ok": True, "id": op_id, "removed": removed, "truncated": truncated, "kept": kept,
            "complete": not kept}
