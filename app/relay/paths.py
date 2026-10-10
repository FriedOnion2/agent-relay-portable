"""时间 / ID / 路径 slug 的公共工具。"""

from __future__ import annotations

from .messages import text as message_text

import os
import secrets
import tempfile
import re
import datetime as dt

# ---------------- ID ----------------

def uuid7(now_ms: int | None = None) -> str:
    """生成一个 UUIDv7（时间可排序，便于按字典序恢复原始顺序）。"""
    if now_ms is None:
        now_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    if not 0 <= now_ms < (1 << 48):
        raise ValueError(message_text('err.uuidv7_timestamp_exceeds_the_48_bit_range'))
    u = ((now_ms << 80) | (7 << 76) | (secrets.randbits(12) << 64)
         | (2 << 62) | secrets.randbits(62))
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
        return s if s not in ("", ".", "..") else "unknown"
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(cwd)).strip("-")
    if not s:
        return "unknown"
    return s[0].lower() + s[1:]


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


def atomic_write(path: str, lines, encoding: str | None = "utf-8", overwrite: bool = True) -> None:
    """原子发布文本行；encoding=None 时原样发布字节块（用于压缩日志）。"""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".relay-", suffix=".partial", dir=directory)
    try:
        options = {"encoding":encoding, "newline":"\n"} if encoding is not None else {}
        with os.fdopen(fd, "w" if encoding is not None else "wb", **options) as f:
            for line in lines:
                f.write(line if encoding is None or line.endswith("\n") else line + "\n")
            f.flush()
            os.fsync(f.fileno())
        if overwrite:
            os.replace(tmp, path)
        elif os.name == "nt":
            # Windows rename never replaces an existing target (including exFAT).
            os.rename(tmp, path)
        else:
            # Hard-link publication is atomic and fails if the target exists.
            try:
                os.link(tmp, path)
            except FileExistsError:
                raise
            except OSError:
                # FAT/exFAT do not support hard links. Serialize Relay writers
                # and publish the complete temporary file by renaming it.
                lock = path + ".publish-lock"
                with open(lock, "x"):
                    try:
                        if os.path.exists(path):
                            raise FileExistsError(path)
                        os.rename(tmp, path)
                    finally:
                        os.unlink(lock)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def validate_session_id(sid: str) -> str:
    """只允许安全的单个文件名，避免指定 ID 写到会话目录之外。"""
    if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", sid):
        raise ValueError(message_text('err.session_ids_may_only_contain_letters_digits_underscores_and_hyphens_at_most_128_characters'))
    return sid


def read_jsonl(path: str, max_bytes: int | None = None, strict: bool = False):
    """Read bounded objects; strict native readers reject corrupt/incomplete rows."""
    import json

    read = 0
    with open(path, "rb") as f:
        truncated = bool(max_bytes and os.fstat(f.fileno()).st_size > max_bytes)
        while True:
            line = f.readline(max_bytes - read + 1) if max_bytes else f.readline()
            if not line:
                break
            read += len(line)
            if max_bytes and read > max_bytes:
                break
            try:
                line = line.decode("utf-8-sig" if read == len(line) else "utf-8", "strict" if strict else "replace").strip()
            except UnicodeError as exc:
                raise ValueError(message_text('err.jsonl_encoding_is_corrupt_complete_reading_is_not_possible')) from exc
            if not line:
                continue
            try:
                record = json.loads(line)
                if isinstance(record, dict):
                    yield record, truncated
                elif strict:
                    raise ValueError(message_text('err.every_jsonl_line_must_be_a_json_object'))
            except (ValueError, TypeError):
                if strict:
                    raise ValueError(message_text('err.jsonl_is_corrupt_or_its_last_line_is_incomplete_wait_for_writing_to_finish_or_use_a_comple')) from None
                continue
