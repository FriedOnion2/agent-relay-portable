"""Bounded, verified local ZIP packages; no account configuration or execution."""
import hashlib
import json
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .runtime import project_root

MAX_FILE = 32 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_FILES = 4096
MAX_MANIFEST = 2 * 1024 * 1024


def storage_root(root=None):
    value = root or os.environ.get("RELAY_STORAGE_HOME")
    return Path(value).expanduser().resolve() if value else project_root() / "storage"


def safe_name(name):
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or any(ord(c) < 32 for c in name)):
        raise ValueError("包内路径无效")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in (".", "..", "") for part in name.split("/")):
        raise ValueError("包内路径越界")
    for part in path.parts:
        if (re.search(r'[<>"|?*]', part) or part.endswith((".", " "))
                or part.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *["COM%d" % n for n in range(1, 10)], *["LPT%d" % n for n in range(1, 10)]}):
            raise ValueError("包内路径不能跨平台使用")
    return name


def is_link(path):
    path = Path(path)
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def read_file(path):
    path = Path(path)
    if is_link(path) or not path.is_file():
        raise ValueError("仅打包普通文件，不包含符号链接")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise ValueError("单个文件超过 32 MiB")
    return data


def write_package(path, manifest, files):
    """Publish an exclusive package after a complete ZIP has been flushed."""
    path = Path(path)
    if path.exists():
        raise FileExistsError("存储包已存在，不覆盖：" + str(path))
    if not files or len(files) > MAX_FILES or sum(len(data) for data, mode in files.values()) > MAX_TOTAL:
        raise ValueError("存储包为空或超过文件数量/256 MiB 限制")
    manifest = dict(manifest, version=1, files=[])
    folded = set()
    for name, (data, mode) in files.items():
        safe_name(name)
        if name.casefold() == "manifest.json" or name.casefold() in folded or len(data) > MAX_FILE:
            raise ValueError("包内名称冲突或文件过大")
        folded.add(name.casefold())
        manifest["files"].append({"path":name, "size":len(data), "sha256":hashlib.sha256(data).hexdigest(), "executable":bool(mode)})
    raw_manifest = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    if len(raw_manifest) > MAX_MANIFEST:
        raise ValueError("包清单过大")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".relay-", suffix=".partial", dir=str(path.parent))
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("manifest.json", raw_manifest)
            for name, (data, mode) in files.items():
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | (0o755 if mode else 0o644)) << 16
                package.writestr(info, data)
        with open(temporary, "r+b") as stream:
            os.fsync(stream.fileno())
        try:
            os.link(temporary, str(path))
        except FileExistsError:
            raise
        except OSError:
            # Exclusive file creation also works on FAT/exFAT. Remove only a
            # destination owned by this attempt if copying fails.
            with path.open("xb") as output:
                try:
                    with open(temporary, "rb") as source:
                        import shutil
                        shutil.copyfileobj(source, output)
                    output.flush()
                    os.fsync(output.fileno())
                except BaseException:
                    output.close()
                    path.unlink()
                    raise
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"ok":True, "path":str(path), "manifest":manifest}


def read_package(path, kind=None, full=True):
    try:
        return _read_package(path, kind, full)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, RecursionError) as exc:
        raise ValueError("存储包损坏或压缩格式不支持") from exc


def _read_package(path, kind=None, full=True):
    """Verify all names, sizes, CRC and SHA before a caller writes native stores."""
    path = Path(path)
    if path.stat().st_size > MAX_TOTAL + MAX_MANIFEST + 4 * 1024 * 1024:
        raise ValueError("包文件过大")
    with zipfile.ZipFile(path) as package:
        infos = package.infolist()
        if len(infos) > MAX_FILES + 1:
            raise ValueError("包内文件过多")
        index, folded, total = {}, set(), 0
        for info in infos:
            safe_name(info.filename)
            if info.filename.casefold() in folded or info.is_dir() or info.flag_bits & 1:
                raise ValueError("包含重复目录项、目录或加密条目")
            folded.add(info.filename.casefold())
            mode = info.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError("包含符号链接或非普通文件")
            if info.file_size > (MAX_MANIFEST if info.filename == "manifest.json" else MAX_FILE):
                raise ValueError("包内文件超过读取限制")
            total += info.file_size
            index[info.filename] = info
        if total > MAX_TOTAL + MAX_MANIFEST or "manifest.json" not in index:
            raise ValueError("包缺少清单或解压后过大")
        manifest = json.loads(package.read("manifest.json").decode("utf-8"))
        if (not isinstance(manifest, dict) or type(manifest.get("version")) is not int
                or manifest["version"] != 1 or (kind and manifest.get("kind") != kind)):
            raise ValueError("不支持的存储包类型或版本")
        rows = manifest.get("files")
        if not isinstance(rows, list) or not rows:
            raise ValueError("存储包清单为空或无效")
        expected, files = set(), {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("存储包文件清单无效")
            name = safe_name(row.get("path"))
            if (name == "manifest.json" or name in expected or name not in index
                    or type(row.get("size")) is not int or row["size"] != index[name].file_size
                    or not isinstance(row.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
                    or type(row.get("executable")) is not bool):
                raise ValueError("存储包文件清单与 ZIP 不一致")
            expected.add(name)
            if full:
                data = package.read(name)
                if hashlib.sha256(data).hexdigest() != row["sha256"]:
                    raise ValueError("存储包校验失败：" + name)
                files[name] = (data, row["executable"])
        if expected != set(index) - {"manifest.json"}:
            raise ValueError("存储包含未声明文件")
        return manifest, files


def unpack(files, directory):
    # Only caller-owned empty temporary directories; never extractall into a home.
    directory = Path(directory)
    for name, (data, executable) in files.items():
        path = directory / safe_name(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        path.chmod(0o755 if executable else 0o644)


def list_packages(kind, agent=None, root=None):
    directory = storage_root(root) / ("conversations" if kind == "agentrelay-session" else "skills")
    rows = []
    for path in sorted(directory.glob("*/*.zip")):
        if agent and path.parent.name != agent:
            continue
        try:
            manifest, _ = read_package(path, kind, full=False)
            rows.append({"path":str(path), "agent":manifest.get("agent"), "created_at":manifest.get("created_at"),
                         "session":manifest.get("session"), "skill":manifest.get("skill"), "verified":False})
        except (OSError, ValueError, zipfile.BadZipFile, KeyError) as exc:
            rows.append({"path":str(path), "error":str(exc)})
    return rows
