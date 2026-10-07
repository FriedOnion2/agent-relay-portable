#!/usr/bin/env python3
"""便携版引导层。

这是 AgentRelay 便携版和"装在某台特定机器上"的普通版的区别所在：
所有路径都相对本文件解析，因此整个目录拷到移动硬盘、换了盘符或挂载点照样能跑。

负责三件事：
  1. 在陌生机器上找到能用的 Python 解释器
  2. 找出当前主机上各个来源的会话目录（在主机上，不在 U 盘上）
  3. 读取 U 盘上的 config.json，用里面的显式配置覆盖自动探测结果

同时支持： python bootstrap.py   直接打印环境体检报告
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from relay.locations import SOURCES
from relay.windows import PROFILE_ENV, selected_profile

MIN_PY = (3, 8)


# ---------------------------------------------------------------- 路径

def app_root() -> Path:
    """程序目录（本文件所在目录，即 app/）。"""
    return Path(__file__).resolve().parent


def media_root() -> Path:
    """移动硬盘根目录（app/ 的上一级）。"""
    return app_root().parent


def log_dir() -> Path:
    """日志写在盘上，不在主机上留东西。"""
    p = media_root() / "logs"
    try:
        p.mkdir(exist_ok=True)
    except OSError:
        p = app_root() / "logs"
        p.mkdir(exist_ok=True)
    return p


def config_path() -> Path:
    return media_root() / "config.json"


def is_removable(path: Path) -> str:
    """判断所在盘是不是可移动介质。返回描述串，判断不了就返回空串。"""
    try:
        if platform.system() == "Windows":
            import ctypes
            drive = Path(path.anchor).drive.rstrip("\\")
            if not drive:
                return ""
            # GetDriveTypeW: 0未知 1不存在 2可移动 3固定 4网络 5光驱 6内存盘
            t = ctypes.windll.kernel32.GetDriveTypeW(drive + "\\")
            return {2: "可移动磁盘", 3: "本地磁盘", 4: "网络驱动器",
                    5: "光盘", 6: "内存盘"}.get(t, "")
        if platform.system() == "Darwin":
            # /Volumes/XXX 下的通常是外置盘
            parts = path.resolve().parts
            if len(parts) > 1 and parts[1] == "Volumes":
                return "外置宗卷"
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------- 找 Python

def _version_of(exe: Path | str) -> tuple | None:
    """跑一次解释器问版本号，跑不通返回 None。"""
    try:
        out = subprocess.run(
            (["py", "-3"] if str(exe) == "py -3" else [str(exe)])
            + ["-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, timeout=25,
        )
        if out.returncode != 0:
            return None
        maj, _, mino = out.stdout.strip().partition(".")
        return (int(maj), int(mino))
    except Exception:
        return None


def python_candidates() -> list[tuple[str, str]]:
    """候选解释器列表 [(路径/命令, 来源说明)]，按优先级排序。"""
    c: list[tuple[str, str]] = []

    env_py = os.environ.get("RELAY_PYTHON")
    if env_py:
        c.append((env_py, "环境变量 RELAY_PYTHON"))
    if sys.executable:
        c.append((sys.executable, "当前运行的 Python"))

    # 1. 盘上自带的 Python（真正免安装的关键）
    rt = media_root() / "runtime"
    winish = platform.system() == "Windows"
    if winish:
        for rel in ("python/python.exe", "python/Scripts/python.exe", "python.exe"):
            p = rt / rel
            if p.is_file():
                c.append((str(p), "移动硬盘自带 runtime"))
    else:
        for rel in ("python/bin/python3", "python/bin/python", "bin/python3", "python3"):
            p = rt / rel
            if p.is_file():
                c.append((str(p), "移动硬盘自带 runtime"))

    # 2. Windows 的 py 启动器
    if winish and shutil.which("py"):
        c.append(("py -3", "Windows Python 启动器"))

    # 3. PATH 里现成的
    for cmd in ("python3", "python"):
        found = shutil.which(cmd)
        if found:
            c.append((found, f"PATH 中的 {cmd}"))

    # 4. 各平台的常见安装位置
    if winish:
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            base = Path(local) / "Programs" / "Python"
            if base.is_dir():
                for d in sorted(base.glob("Python3*"), reverse=True):
                    exe = d / "python.exe"
                    if exe.is_file():
                        c.append((str(exe), "用户级安装"))
        for d in (r"C:\Python3", r"C:\Python39", r"C:\Python311", r"C:\Python312", r"C:\Python313"):
            exe = Path(d) / "python.exe"
            if exe.is_file():
                c.append((str(exe), "系统级安装"))
    elif platform.system() == "Darwin":
        for p in ("/opt/homebrew/bin/python3",      # Apple Silicon 的 Homebrew
                  "/usr/local/bin/python3",         # Intel 的 Homebrew
                  "/usr/bin/python3"):              # Xcode 命令行工具自带的
            if Path(p).is_file():
                c.append((p, "系统自带" if p == "/usr/bin/python3" else "Homebrew"))
        fr = Path("/Library/Frameworks/Python.framework/Versions")
        if fr.is_dir():
            for v in sorted(fr.glob("3.*"), reverse=True):
                exe = v / "bin" / "python3"
                if exe.is_file():
                    c.append((str(exe), "python.org 安装"))
    else:
        for p in ("/usr/bin/python3", "/usr/local/bin/python3", "/bin/python3"):
            if Path(p).is_file():
                c.append((p, "系统 Python"))

    return c


def find_python() -> dict:
    """挑第一个版本达标的解释器。"""
    tried = []
    for cmd, origin in python_candidates():
        ver = _version_of(cmd)
        tried.append({"cmd": cmd, "origin": origin,
                      "ver": f"{ver[0]}.{ver[1]}" if ver else None,
                      "ok": bool(ver and ver >= MIN_PY)})
        if ver and ver >= MIN_PY:
            return {"ok": True, "cmd": cmd, "origin": origin,
                    "version": f"{ver[0]}.{ver[1]}", "tried": tried}
    return {"ok": False, "cmd": None, "origin": None, "version": None, "tried": tried}


# ---------------------------------------------------------------- 配置

DEFAULT_CONFIG = {
    "_说明": "全部留空即可 —— 留空时程序会自动探测。只有在会话目录不在默认位置时填。",
    "agent_homes": {
        "claude": "",
        "claude_sdk": "",
        "codex": "",
        "dsh": "",
        "workbuddy": "",
        "codebuddy": "",
    },
    "port": 8745,
    "open_browser": True,
    "windows_user_home": "",
    "ubuntu_user_home": "",
}


def write_default_config(force: bool = False) -> Path:
    p = config_path()
    if p.exists() and not force:
        return p
    p.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    return p


def load_config() -> dict:
    p = config_path()
    if not p.is_file():
        return {}
    try:
        cfg = json.loads(p.read_text(encoding="utf-8-sig"))
        if not isinstance(cfg, dict):
            raise ValueError("配置必须是 JSON 对象")
        homes = cfg.get("agent_homes", {})
        if not isinstance(homes, dict):
            raise ValueError("agent_homes 必须是 JSON 对象")
        for key in SOURCES:
            if key in homes and not isinstance(homes[key], str):
                raise ValueError(f"agent_homes.{key} 必须是字符串")
        if "port" in cfg and (type(cfg["port"]) is not int or not 1 <= cfg["port"] <= 65535):
            raise ValueError("port 必须是 1 到 65535 的整数")
        if "open_browser" in cfg and type(cfg["open_browser"]) is not bool:
            raise ValueError("open_browser 必须为 true 或 false")
        if "windows_user_home" in cfg and not isinstance(cfg["windows_user_home"], str):
            raise ValueError("windows_user_home 必须是字符串")
        profile = (cfg.get("windows_user_home") or "").strip()
        if profile and platform.system() == "Linux" and not Path(profile).expanduser().is_absolute():
            raise ValueError("windows_user_home 必须是 Ubuntu 中的绝对挂载路径")
        if "ubuntu_user_home" in cfg and not isinstance(cfg["ubuntu_user_home"], str):
            raise ValueError("ubuntu_user_home 必须是字符串")
        ubuntu = (cfg.get("ubuntu_user_home") or "").strip()
        if ubuntu and platform.system() == "Windows" and not Path(ubuntu).expanduser().is_absolute():
            raise ValueError("ubuntu_user_home 必须是 Windows 可访问的绝对路径")
        return cfg
    except Exception as e:
        print(f"⚠ config.json 解析失败，忽略此文件：{e}", file=sys.stderr)
        return {}


def apply_config(cfg: dict | None = None) -> list[str]:
    """把配置里的 agent 目录覆盖写进环境变量，返回生效的说明列表。"""
    cfg = cfg if cfg is not None else load_config()
    applied = []
    profile = (cfg.get("windows_user_home") or "").strip()
    if profile and platform.system() == "Linux":
        os.environ[PROFILE_ENV] = os.path.expanduser(profile)
        applied.append(f"Windows 用户目录（只读） ← {profile}")
    ubuntu = (cfg.get("ubuntu_user_home") or "").strip()
    if ubuntu and platform.system() == "Windows":
        from relay.ubuntu import PROFILE_ENV as UBUNTU_ENV
        os.environ[UBUNTU_ENV] = os.path.expanduser(ubuntu)
        applied.append(f"Ubuntu 用户目录（只读） ← {ubuntu}")
    homes = cfg.get("agent_homes") or {}
    for key in SOURCES:
        envname = "RELAY_" + key.upper() + "_HOME"
        v = (homes.get(key) or "").strip()
        if v:
            os.environ[envname] = os.path.expanduser(v)
            applied.append(f"{key} 目录 ← {v}")
    return applied


def effective_port(cfg: dict | None = None) -> int:
    cfg = cfg if cfg is not None else load_config()
    try:
        port = int(cfg.get("port") or DEFAULT_CONFIG["port"])
        return port if 1 <= port <= 65535 else DEFAULT_CONFIG["port"]
    except Exception:
        return DEFAULT_CONFIG["port"]


def effective_open_browser(cfg: dict | None = None) -> bool:
    cfg = cfg if cfg is not None else load_config()
    return bool(cfg.get("open_browser", True))


# ---------------------------------------------------------------- 主机会话目录

def probe_agent_homes() -> list[dict]:
    """使用同一套 adapter 探测目录和会话，避免将日志世代计为多个会话。"""
    from relay import registry
    out = []
    for key in registry.all_keys():
        adapter = registry.get(key, clean=True)
        try:
            rows = list(adapter.discover()) if adapter.available() else []
            count = len(rows)
            errors = list(dict.fromkeys(row.error for row in rows if row.error))
        except Exception as exc:
            count, errors = -1, [str(exc)]
        out.append({"key":key, "label":adapter.label, "root":adapter.root if hasattr(adapter, "root") else adapter.home,
                    "data":"; ".join(getattr(adapter, "roots", [adapter.home])),
                    "found":adapter.available(), "files":count, "errors":errors[:3]})
    return out


# ---------------------------------------------------------------- 体检报告

def report(verbose: bool = True, cfg: dict | None = None) -> dict:
    py = find_python()
    cfg = cfg if cfg is not None else load_config()
    apply_config(cfg)
    return {
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "app_root": str(app_root()),
        "media_root": str(media_root()),
        "media_kind": is_removable(media_root()) or "（无法判断，不影响运行）",
        "python": py,
        "config": str(config_path()) if config_path().is_file() else "（无 config.json，走自动探测）",
        "overrides": cfg.get("agent_homes") or {},
        "agents": probe_agent_homes(),
        "port": effective_port(cfg),
        "windows_user_home": selected_profile(),
    }


def print_report(cfg: dict | None = None) -> int:
    r = report(cfg=cfg)
    line = "─" * 66
    print(line)
    print(" AgentRelay 便携版 · 运行环境体检")
    print(line)
    print(f"  当前系统     {r['platform']}")
    print(f"  程序位置     {r['app_root']}")
    print(f"  所在盘       {r['media_root']}  [{r['media_kind']}]")
    print(f"  配置文件     {r['config']}")
    if r["windows_user_home"]:
        print(f"  Windows 用户 {r['windows_user_home']}（跨系统只读）")
    print()
    py = r["python"]
    if py["ok"]:
        print(f"  ✓ Python     {py['version']}  via {py['origin']}")
        print(f"               {py['cmd']}")
    else:
        print("  ✗ 没找到可用的 Python（需要 3.8 以上）")
        for t in py["tried"]:
            mark = "✗" if not t["ok"] else "✓"
            why = f"版本 {t['ver']} 过低" if t["ver"] and not t["ok"] else "无法执行"
            print(f"      {mark} {t['cmd']}  ({t['origin']}) {why}")
    print()
    print("  当前主机上的会话目录：")
    for a in r["agents"]:
        if a["found"]:
            cnt = f"{a['files']} 个会话" if a["files"] >= 0 else "读取失败"
            print(f"    ✓ {a['label']:<16} {cnt}")
            print(f"      {a['data']}")
        else:
            print(f"    · {a['label']:<16} 未安装 / 目录不存在")
            print(f"      {a['data']}")
        for error in a.get("errors", []):
            print(f"      ↳ {error}")
        if a["key"] == "claude_sdk":
            print("      ↳ SDK 与 Claude Code 共用存储；此处统计包含共享会话，不代表 SDK 专属数量。")
    print()
    print(line)
    return 0 if py["ok"] else 2


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(print_report())
