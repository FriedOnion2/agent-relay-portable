"""适配器基类。

新增一个 agent 只需实现 name / discover / read / write 四件事，
其余（枚举、统计、摘要）都由基类提供。
"""

from __future__ import annotations

import fnmatch
import os
import ntpath
import posixpath
from dataclasses import dataclass, asdict, replace
from collections import OrderedDict
from typing import Any, Dict, Iterable, Optional

from .. import ir
from ..paths import human_size, local_str, read_jsonl, slug_for, is_windows_path


def _norm_cwd(cwd: str) -> str:
    """反查表的 key：统一分隔符、去尾斜杠、小写。

    大小写不敏感是因为 Windows 上路径可能来自不同来源，大小写不一致很常见，
    而 PowerShell 里 `cd C:\\Users` 和 `c:\\users` 是同一个目录。
    """
    if not cwd:
        return ""
    windows = is_windows_path(cwd) or cwd.startswith(("\\\\", "//"))
    normalized = (ntpath if windows else posixpath).normpath(str(cwd)).replace("\\", "/")
    return normalized.lower() if windows else normalized


@dataclass
class SessionInfo:
    """列表用的轻量会话信息（不读取全文）。"""

    source: str
    id: str
    title: str
    cwd: str
    model: str
    created_ms: Optional[int]
    updated_ms: Optional[int]
    size: int
    turns: int
    path: str
    readable: bool = True
    error: str = ""
    shared_store: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["created"] = local_str(self.created_ms)
        d["updated"] = local_str(self.updated_ms)
        d["size_str"] = human_size(self.size)
        return d


class ToolNameMap:
    """工具名互译。各家的内置工具叫法不一样，迁移时统一到 canonical 名。"""

    # 其它 agent -> canonical（Claude / DSH 风格）
    TO_CANONICAL: Dict[str, str] = {
        "exec": "Bash",
        "exec_command": "Bash",
        "shell": "Bash",
        "apply_patch": "Edit",
        "update_plan": "TodoWrite",
        "view_image": "Read",
        "list_dir": "Glob",
        "search": "Grep",
        "plan": "ExitPlanMode",
    }
    # canonical -> Codex 风格
    TO_CODEX: Dict[str, str] = {
        "Bash": "exec",
        "Read": "view_image",
        "Edit": "apply_patch",
        "TodoWrite": "update_plan",
        "Glob": "list_dir",
        "Grep": "search",
    }
    TO_DSH: Dict[str, str] = {
        "Bash":"bash", "Read":"read", "Write":"write", "Edit":"edit",
        "Glob":"glob", "Grep":"grep", "TodoWrite":"todo_write",
    }

    @classmethod
    def convert(cls, name: str, target: str, enabled: bool = True) -> str:
        if not name or not enabled:
            return name
        if target == "codex":
            return cls.TO_CODEX.get(name, name)
        if name.startswith(("mcp__", "builtin__")):
            return name
        if target == "dsh":
            canonical = cls.TO_CANONICAL.get(name, name)
            return cls.TO_DSH.get(canonical, canonical)
        return cls.TO_CANONICAL.get(name, name)


class BaseAdapter:
    api_version: int = 1
    name: str = ""
    label: str = ""
    home: Optional[str] = None          # 会话根目录
    can_write: bool = True

    # ---------------- 子类实现 ----------------

    def available(self) -> bool:
        """本机的这个 agent 是否有数据目录。"""
        return bool(self.home and os.path.isdir(self.home))

    def _cached_summary(self, path, load):
        """Cache small list rows only; changed files and failed reads are retried."""
        st = os.stat(path)
        stamp = (st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        cache = getattr(self, "_summary_cache", None)
        if cache is None:
            cache = self._summary_cache = OrderedDict()
        cached = cache.get(path)
        if cached and cached[0] == stamp:
            cache.move_to_end(path)
            return replace(cached[1])
        row = load()
        cache.pop(path, None)
        if row is not None and row.readable:
            cache[path] = (stamp, replace(row))
            while len(cache) > 512:
                cache.popitem(last=False)
        return row

    def discover(self) -> Iterable[SessionInfo]:
        raise NotImplementedError

    def read(self, sid: str) -> ir.Conversation:
        raise NotImplementedError

    def write(self, conv: ir.Conversation, cwd: str | None = None,
              session_id: str | None = None, remap_tools: bool = True,
              include_thinking: bool = True) -> str:
        raise NotImplementedError

    def self_check(self):
        from ..health import check
        return check(self.name)

    # ---------------- 通用辅助 ----------------

    def find_path(self, sid: str) -> Optional[str]:
        """通过 会话id（或文件名的模糊匹配）定位会话文件。"""
        if not isinstance(sid, str) or not sid.strip():
            raise ValueError("缺少会话 ID")
        matches = []
        for s in self.discover():
            if s.id == sid:
                return s.path
            if sid in os.path.basename(s.path):
                matches.append(s.path)
        if len(matches) > 1:
            raise ValueError("会话 ID 匹配多条记录，请使用完整 ID")
        return matches[0] if matches else None

    def project_dir_for(self, cwd: str) -> str:
        """算出 cwd 对应的项目目录名。

        优先查反查表：扫描该 agent 已有的项目目录，从会话记录里读出它们各自的 cwd，
        建立 cwd → 目录名的映射。命中就用现成的目录名 —— 这是唯一 100% 可靠的办法。

        反查表查不到时才退回启发式 slug（换机器、首次写入新目录时会遇到）。
        """
        key = _norm_cwd(cwd)
        idx = self._project_index()
        if key and key in idx:
            return idx[key]
        return slug_for(cwd)

    def _project_index(self) -> Dict[str, str]:
        """扫描 projects 目录，从已有会话记录里提取 cwd。每次进程缓存一次。"""
        if getattr(self, "_proj_idx", None) is not None:
            return self._proj_idx
        idx: Dict[str, str] = {}
        home = getattr(self, "home", None)
        if home and os.path.isdir(home):
            try:
                for entry in os.scandir(home):
                    if not entry.is_dir():
                        continue
                    cwd = self._cwd_of_project_dir(entry.path)
                    if cwd:
                        idx.setdefault(_norm_cwd(cwd), entry.name)
            except OSError:
                pass
        self._proj_idx = idx
        return idx

    def _cwd_of_project_dir(self, dirpath: str) -> Optional[str]:
        """读一个项目目录里第一条带 cwd 的记录。只看前若干条，够快。"""
        for dirpath2, _dirs, files in os.walk(dirpath):
            for fn in sorted(files):
                if not fn.endswith(".jsonl"):
                    continue
                path = os.path.join(dirpath2, fn)
                for rec, _trunc in read_jsonl(path, 512 * 1024):
                    c = rec.get("cwd")
                    if c:
                        return str(c)
            break  # 只看一层
        return None

    def info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "home": self.home,
            "available": self.available(),
            "can_read": True,
            "can_write": self.can_write,
            "api_version": self.api_version,
            "community": False,
            "capabilities": ["read", "export", "native_store", "native_restore", "skill_store"] + (["write"] if self.can_write else []),
            "write_note": "" if self.can_write else "支持读取、导出及迁出；尚不支持写入此来源",
            "read_note": getattr(self, "read_note", ""),
        }

    @staticmethod
    def _title_from_conv(conv: ir.Conversation, fallback="未命名会话") -> str:
        if conv.title:
            return conv.title
        t = conv.first_user_text(50)
        return t or fallback

    @staticmethod
    def _iter_files(root: str, pattern: str):
        if not os.path.isdir(root):
            return
        def failed(exc):
            raise exc
        # An unreadable subtree is not an empty/deleted store. Indexing callers
        # must retain cached records when enumeration cannot complete.
        for dirpath, _dirnames, filenames in os.walk(root, onerror=failed):
            _dirnames[:] = [name for name in _dirnames if not (name.startswith(".relay-") and name.endswith(".partial"))]
            for fn in filenames:
                if fnmatch.fnmatch(fn, pattern):
                    p = os.path.join(dirpath, fn)
                    yield p

    @staticmethod
    def _stat(path: str) -> Dict[str, Any]:
        try:
            st = os.stat(path)
            return {"size": st.st_size, "created_ms": int(st.st_ctime * 1000),
                    "updated_ms": int(st.st_mtime * 1000)}
        except OSError:
            return {"size": 0, "created_ms": None, "updated_ms": None}


def summarize_for_list(conv: ir.Conversation) -> Dict[str, int]:
    """从完整会话里算会话列表需要的统计（用于无法廉价取标题的场景）。"""
    return conv.stats()


class ReadOnlyAdapter(BaseAdapter):
    can_write = False

    def write(self, conv, **kwargs):
        raise ValueError(f"{self.label} 暂不支持作为迁移目标；可读取、导出或迁移到其他工具")
