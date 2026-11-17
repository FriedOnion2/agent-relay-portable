"""Record owned file publications and undo them when their contents still match.

Receipts use the existing JSONL log and preserve undo support for old entries.
"""

from __future__ import annotations

from .messages import text as message_text, join_text, error_text, annotate, restore_text

import contextlib
from contextvars import ContextVar
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
MAX_RECORDED = 500              # 单次操作最多记录的新建文件数；超过则标记为不可撤销
HASH_LIMIT = 64 * 1024 * 1024   # 超过这个大小的新建文件只比对大小与修改时间
READ_LINES = 5000

_lock = threading.Lock()


def log_path() -> Path:
    base = os.environ.get("RELAY_LOG_HOME")
    return (Path(base).expanduser() if base else project_root() / "logs") / LOG_NAME


_active: ContextVar = ContextVar("relay_operation", default=None)


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
            handle.write(json.dumps(annotate(entry), ensure_ascii=False) + "\n")


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


def file_evidence(path):
    """Capture the staged file's identity and data before publication."""
    if _active.get() is None:
        return None
    info = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Expected a staged regular file")
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "sha256": _sha256(path),
            "device": info.st_dev, "inode": info.st_ino}


def published(path, evidence, *, previous_size=None, replacement=False):
    record = _active.get()
    if record is None:
        return
    path = os.path.abspath(path)
    if not _inside(path, record["roots"]):
        return
    if replacement or evidence is None:
        record["modified_other"].append(path)
    elif previous_size is None:
        record["created"].append(dict(evidence, path=path))
    else:
        record["appended"].append(dict(evidence, path=path, size_before=previous_size, size_after=evidence["size"]))


def created_directory(path):
    record = _active.get()
    path = os.path.abspath(path)
    if record is not None and (path in record["roots"] or _inside(path, record["roots"])):
        try:
            info = os.stat(path, follow_symlinks=False)
        except OSError:
            return  # A missing directory never needs cleanup.
        if stat.S_ISDIR(info.st_mode):
            record["created_dirs"].append(path)
            record["directory_ids"][path] = [info.st_dev, info.st_ino]


@contextlib.contextmanager
def track(kind: str, roots: Iterable[str | None], **meta: Any):
    roots = [os.path.abspath(str(root)) for root in roots if root]
    record: Dict[str, Any] = {"id": paths.short_id("op-", 12), "time": paths.iso(), "kind": kind,
                              "roots": roots, "created": [], "appended": [], "created_dirs": [],
                              "modified_other": [], "directory_ids": {}, "receipt_version": 1, **meta}
    token = _active.set(record)
    try:
        yield record
    except BaseException as error:
        _finish(record, "failed", error_text(error))
        raise
    else:
        _finish(record, "ok", "")
    finally:
        _active.reset(token)


def _finish(record, status, error):
    try:
        # Rollback can remove a published file before the operation finishes.
        record["created"] = [row for row in record["created"] if os.path.lexists(row["path"])]
        reasons = []
        if record["modified_other"]:
            reasons.append(message_text('msg.undo_existing_files_rewritten'))
        if any(len(record[key]) > MAX_RECORDED for key in ("created", "appended", "created_dirs")):
            reasons.append(message_text('msg.undo_too_many_changes'))
        if status == "failed" and not any(record[key] for key in ("created", "appended", "modified_other")):
            return
        for key in ("created", "appended", "created_dirs", "modified_other"):
            record[key] = record[key][:MAX_RECORDED]
        record["directory_ids"] = {path: record["directory_ids"][path] for path in record["created_dirs"]}
        record.update(status=status, error=error, undoable=not reasons,
                      undo_blocked=join_text(reasons, "；"))
        _append(record)
    except Exception:  # Logging must not turn a completed migration into a failure.
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
            **{key:entry[key] for key in ("error_message", "undo_blocked_message") if key in entry},
            "undone": {"time": undo.get("time"), "removed": undo.get("removed"), "kept": undo.get("kept")} if undo else None,
        })
    rows.reverse()
    return rows[:max(1, min(int(limit), 1000))]


# ---------------- 撤销 ----------------

def _inside(path: str, roots: List[str]) -> bool:
    real = os.path.normcase(os.path.realpath(path))
    for root in roots:
        base = os.path.normcase(os.path.realpath(root))
        if real != base and real.startswith(base + os.sep):
            return True
    return False


def undo(op_id: str, force: bool = False) -> Dict[str, Any]:
    entries = _read_entries()
    entry = next((e for e in entries if e.get("id") == op_id and not e.get("undo_of")), None)
    if not entry:
        raise KeyError(message_text('err.operation_record_not_found'))
    if any(e.get("undo_of") == op_id for e in entries):
        raise ValueError(message_text('err.this_operation_has_already_been_undone'))
    if not entry.get("undoable"):
        reason = restore_text(entry.get('undo_blocked'), entry.get('undo_blocked_message'))
        raise ValueError(message_text('err.this_operation_cannot_be_undone_automatically_value', value=reason or message_text('msg.no_file_changes_recorded')))
    roots = entry.get("roots") or []
    removed, kept, truncated = [], [], []

    for row in entry.get("created", []):
        path = row["path"]
        if not _inside(path, roots):
            kept.append({"path": path, "reason": message_text('msg.outside_the_recorded_target_directory_skipped')})
            continue
        if not os.path.lexists(path):
            continue
        if os.path.islink(path) or not os.path.isfile(path):
            kept.append({"path": path, "reason": message_text('msg.no_longer_a_regular_file_skipped')})
            continue
        info = os.stat(path)
        same = info.st_size == row["size"] and (row.get("sha256") is None and info.st_mtime_ns == row["mtime_ns"]
                                                or row.get("sha256") is not None and _sha256(path) == row["sha256"])
        identity = ("inode" not in row or
                    (info.st_dev, info.st_ino) == (row["device"], row["inode"]))
        if not identity or (not same and not force):
            kept.append({"path": path, "reason": message_text('msg.modified_after_writing_possibly_resumed_in_the_target_app_kept_to_avoid_losing_new_content')})
            continue
        os.remove(path)
        removed.append(path)

    for row in entry.get("appended", []):
        path = row["path"]
        if not _inside(path, roots) or not os.path.isfile(path) or os.path.islink(path):
            kept.append({"path": path, "reason": message_text('msg.file_is_missing_or_outside_the_target_directory_skipped')})
            continue
        with open(path, "r+b") as handle:
            info = os.fstat(handle.fileno())
            same_file = os.path.samestat(info, os.stat(path, follow_symlinks=False))
            if row.get("sha256") is not None:
                digest = hashlib.sha256()
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                unchanged = digest.hexdigest() == row["sha256"]
            else:
                unchanged = info.st_mtime_ns == row["mtime_ns"]
            current = os.fstat(handle.fileno())
            after = os.stat(path, follow_symlinks=False)
            if (not same_file or not os.path.samestat(current, after) or info.st_size != row["size_after"] or
                    current.st_size != info.st_size or current.st_mtime_ns != info.st_mtime_ns or not unchanged):
                kept.append({"path": path, "reason": message_text('msg.modified_after_writing_not_truncated_to_the_original_length')})
                continue
            handle.truncate(row["size_before"])
        truncated.append(path)

    for directory in sorted(set(entry.get("created_dirs", [])), key=len, reverse=True):
        if _inside(directory, roots) or directory in roots:
            with contextlib.suppress(OSError):
                info = os.stat(directory, follow_symlinks=False)
                expected = entry.get("directory_ids", {}).get(directory)
                if (stat.S_ISDIR(info.st_mode) and
                        (expected is None or expected == [info.st_dev, info.st_ino]) and
                        not os.listdir(directory)):
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
