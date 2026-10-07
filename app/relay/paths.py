"""时间 / ID / 路径 slug 的公共工具。"""

from __future__ import annotations

import os
import random
import re
import datetime as dt

# ---------------- ID ----------------

def uuid7(now_ms: int | None = None) -> str:
    """生成一个 UUIDv7（时间可排序，便于按字典序恢复原始顺序）。"""
    if now_ms is None:
        now_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    rnd = random.getrandbits(74)
    hi = (now_ms << 16) | ((rnd >> 58) & 0x0FFF) | (0x7 << 76)
    hi = hi & ((1 << 80) - 1)
    u = (hi << 48) | (rnd & ((1 << 48) - 1))
    h = f"{u:032x}"
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def short_id(prefix: str = "", n: int = 12) -> str:
    h = os.urandom(n // 2 + 1).hex()[:n]
    return f"{prefix}{h}" if prefix else h


# ---------------- 时间 ----------------

_UTC = dt.timezone.utc


def now_ms() -> int:
    return int(dt.datetime.now(_UTC).timestamp() * 1000)


def iso(ms: int | None = None) -> str:
    """毫秒时间戳 -> ISO-8601 (UTC, 毫秒精度, Z 结尾)。"""
    if ms is None:
        ms = now_ms()
    return dt.datetime.fromtimestamp(ms / 1000, _UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


def parse_iso(s: str | None) -> int | None:
    """ISO-8601 -> 毫秒时间戳。解析失败返回 None。"""
    if not s:
        return None
    try:
        t = str(s).strip().replace("Z", "+00:00")
        # Python 3.11+ 支持任意小数位；低版本需截断到 6 位
        m = re.search(r"\.(\d+)", t)
        if m and len(m.group(1)) > 6:
            t = t[: m.start(1) + 6] + (t[m.end(1):] if m.end(1) < len(t) else "")
        d = dt.datetime.fromisoformat(t)
        if d.tzinfo is None:
            d = d.replace(tzinfo=_UTC)
        return int(d.timestamp() * 1000)
    except Exception:
        return None


def safe_ms(v, default: int | None = None) -> int | None:
    """把可能是 int/float/str 的时间统一成毫秒 int。"""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        v = float(v)
        # 秒级时间戳（10 位量级）自动升到毫秒
        if v < 1e11:
            v *= 1000
        return int(v)
    return parse_iso(str(v)) or default


def local_str(ms: int | None) -> str:
    if not ms:
        return "-"
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


# ---------------- 路径 slug ----------------

def slug_for(cwd: str) -> str:
    """工作目录 -> 项目目录名（启发式，仅在反查表没命中时兜底）。

    Windows 上这条规则用本机 7 个真实目录名双向校验过：
        C:\\Users\\x\\WorkBuddy\\2026-10-07  ->  c-Users-x-WorkBuddy-2026-10-07
    做法是把连续的非字母数字折叠成单个 '-'，首字母小写（盘符小写的惯例）。

    POSIX 路径不能套同一套：那样 `/Users/foo/project` 会变成 `users-foo-project`，
    而各家的 macOS 项目目录是带前导短横线的 `-Users-foo-project`
    （那个横线就是根目录 `/`）。所以 POSIX 保留前导横线。
    """
    if not cwd:
        return "unknown"
    if not is_windows_path(cwd):
        s = re.sub(r"[^\w.\-]", "-", cwd.replace("\\", "/"))
        return s or "unknown"
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(cwd)).strip("-")
    if not s:
        return "unknown"
    return s[0].lower() + s[1:]


def normalize_cwd(cwd: str) -> str:
    """统一成正斜杠的绝对路径字符串。"""
    if not cwd:
        return ""
    return os.path.normpath(str(cwd)).replace("\\", "/")


def expand(p: str) -> str:
    return os.path.expanduser(p)


def is_windows_path(p: str) -> bool:
    """是否 Windows 风格路径（带盘符，如 C:\\Users 或 C:/Users）。"""
    return bool(p) and len(p) >= 2 and p[1] == ":"


def native_path(p: str) -> str:
    """按各自平台的书写习惯展示路径。

    Windows 路径转成反斜杠并把盘符小写（这是 DSH 会话记录里的实际惯例：
    session 元数据里是 `C:\\Users\\…`，记录里写的是 `c:\\Users\\…`）。
    POSIX 路径必须原样返回 —— 直接 lower + 换分隔符会把 `/Users/foo` 毁成 `\\users\\foo`。
    """
    if not p:
        return p
    if is_windows_path(p):
        return p[0].lower() + p[1:].replace("/", "\\")
    return p


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def atomic_write(path: str, lines, encoding: str = "utf-8") -> None:
    """逐行写入，先写临时文件再替换，避免写到一半产生坏文件。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".partial"
    with open(tmp, "w", encoding=encoding, newline="\n") as f:
        for line in lines:
            f.write(line if line.endswith("\n") else line + "\n")
    os.replace(tmp, path)


def read_jsonl(path: str, max_bytes: int | None = None):
    """惰性逐行读取 jsonl，跳过坏行。返回 (dict|None, 是否截断)。"""
    import json

    truncated = False
    read = 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            read += len(line.encode("utf-8", "replace"))
            if max_bytes and read > max_bytes:
                truncated = True
                break
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), truncated
            except Exception:
                continue
