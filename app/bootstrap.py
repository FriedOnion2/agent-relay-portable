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

from relay.messages import text as message_text, error_text, lang_text, render

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from relay.runtime import project_root
from relay.locations import SOURCES, CROSS_ACCOUNT_SOURCES
from relay.windows import PROFILE_ENV, selected_profile

MIN_PY = (3, 8)


# ---------------------------------------------------------------- 路径

def app_root() -> Path:
    """程序目录（本文件所在目录，即 app/）。"""
    return Path(__file__).resolve().parent


def media_root() -> Path:
    """移动硬盘根目录（app/ 的上一级）。"""
    return project_root()


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
    if getattr(sys, "frozen", False):
        return {"ok": True, "cmd": sys.executable, "origin": "Release 内置 Python",
                "version": "%d.%d" % sys.version_info[:2], "tried": []}
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
        "workbuddy_ai": "",
        "codebuddy": "",
        "yuanbao": "",
    },
    "port": 8745,
    "open_browser": True,
    "windows_user_home": "",
    "ubuntu_user_home": "",
}


def _merge_device(cfg):
    from relay import device
    try:
        return device.merge(cfg)
    except (OSError, ValueError) as exc:
        result = device.merge(cfg, local={})
        device.warnings.append(message_text('msg.local_config_read_failed', detail=error_text(exc)))
        return result


def load_config() -> dict:
    p = config_path()
    if not p.is_file():
        return _merge_device({})
    try:
        cfg = json.loads(p.read_text(encoding="utf-8-sig"))
        if not isinstance(cfg, dict):
            raise ValueError(message_text('err.configuration_must_be_a_json_object'))
        homes = cfg.get("agent_homes", {})
        if not isinstance(homes, dict):
            raise ValueError(message_text('err.agent_homes_must_be_a_json_object'))
        for key in (*SOURCES, *CROSS_ACCOUNT_SOURCES):
            if key in homes and not isinstance(homes[key], str):
                raise ValueError(message_text('err.agent_homes_key_must_be_a_string', key=key))
        if "port" in cfg and (type(cfg["port"]) is not int or not 1 <= cfg["port"] <= 65535):
            raise ValueError(message_text('err.port_must_be_an_integer_from_1_to_65535'))
        if "open_browser" in cfg and type(cfg["open_browser"]) is not bool:
            raise ValueError(message_text('err.open_browser_must_be_true_or_false'))
        if "windows_user_home" in cfg and not isinstance(cfg["windows_user_home"], str):
            raise ValueError(message_text('err.windows_user_home_must_be_a_string'))
        profile = (cfg.get("windows_user_home") or "").strip()
        if profile and platform.system() == "Linux" and not Path(profile).expanduser().is_absolute():
            raise ValueError(message_text('err.windows_user_home_must_be_an_absolute_mounted_path_in_ubuntu'))
        if "ubuntu_user_home" in cfg and not isinstance(cfg["ubuntu_user_home"], str):
            raise ValueError(message_text('err.ubuntu_user_home_must_be_a_string'))
        ubuntu = (cfg.get("ubuntu_user_home") or "").strip()
        if ubuntu and platform.system() == "Windows" and not Path(ubuntu).expanduser().is_absolute():
            raise ValueError(message_text('err.ubuntu_user_home_must_be_an_absolute_path_accessible_from_windows'))
        return _merge_device(cfg)
    except Exception as e:
        print(f"⚠ config.json 解析失败，忽略此文件：{e}", file=sys.stderr)
        from relay import device
        result = _merge_device({})
        device.warnings.append(message_text('msg.shared_config_read_failed', detail=error_text(e)))
        return result


_APPLIED_ENV: dict = {}


def apply_config(cfg: dict | None = None) -> list[str]:
    """把配置里的 agent 目录覆盖写进环境变量，返回生效的说明列表。"""
    cfg = cfg if cfg is not None else load_config()
    for name, value in _APPLIED_ENV.items():
        if os.environ.get(name) == value:
            os.environ.pop(name, None)
    _APPLIED_ENV.clear()
    applied = []
    profile = (cfg.get("windows_user_home") or "").strip()
    if profile and platform.system() == "Linux":
        os.environ[PROFILE_ENV] = os.path.expanduser(profile)
        _APPLIED_ENV[PROFILE_ENV] = os.environ[PROFILE_ENV]
        applied.append(f"Windows 用户目录（只读） ← {profile}")
    ubuntu = (cfg.get("ubuntu_user_home") or "").strip()
    if ubuntu and platform.system() == "Windows":
        from relay.ubuntu import PROFILE_ENV as UBUNTU_ENV
        os.environ[UBUNTU_ENV] = os.path.expanduser(ubuntu)
        _APPLIED_ENV[UBUNTU_ENV] = os.environ[UBUNTU_ENV]
        applied.append(f"Ubuntu 用户目录（只读） ← {ubuntu}")
    homes = cfg.get("agent_homes") or {}
    for key in (*SOURCES, *CROSS_ACCOUNT_SOURCES):
        envname = "RELAY_" + key.upper() + "_HOME"
        v = (homes.get(key) or "").strip()
        if v:
            os.environ[envname] = os.path.expanduser(v)
            _APPLIED_ENV[envname] = os.environ[envname]
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
        try:
            adapter = registry.get(key, clean=True)
            rows = list(adapter.discover()) if adapter.available() else []
            count = len(rows)
            errors = list(dict.fromkeys(row.error for row in rows if row.error))
        except Exception as exc:
            out.append({'key':key, 'label':key, 'root':'', 'data':'', 'found':False,
                        'files':-1, 'errors':[error_text(exc)]})
            continue
        out.append({"key":key, "label":adapter.label, "root":adapter.root if hasattr(adapter, "root") else adapter.home,
                    "data":"; ".join(getattr(adapter, "roots", [adapter.home])),
                    "found":adapter.available(), "files":count, "errors":errors[:3]})
    return out


# ---------------------------------------------------------------- 体检报告

def report(cfg: dict | None = None) -> dict:
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


_REPORT_KEYS = {
    "可移动磁盘": "drive_removable", "本地磁盘": "drive_local", "网络驱动器": "drive_network", "光盘": "drive_optical",
    "内存盘": "drive_ram", "外置宗卷": "drive_external", "（无法判断，不影响运行）": "media_unknown",
    "（无 config.json，走自动探测）": "no_config", "环境变量 RELAY_PYTHON": "origin_env", "当前运行的 Python": "origin_current",
    "移动硬盘自带 runtime": "origin_bundled", "Windows Python 启动器": "origin_py_launcher", "用户级安装": "origin_user",
    "系统级安装": "origin_system", "系统自带": "origin_os", "python.org 安装": "origin_pyorg", "系统 Python": "origin_system_python",
    "Release 内置 Python": "origin_release",
}


def print_report(cfg: dict | None = None, lang: str = "zh") -> int:
    def t(code, **params):
        return lang_text(lang, "msg.cli_b_" + code, **params)

    def loc(value):
        """The report data carries Chinese labels; show them in the requested language."""
        if value in _REPORT_KEYS:
            return t(_REPORT_KEYS[value])
        if isinstance(value, str) and value.startswith("PATH 中的 "):
            return t("origin_path", cmd=value[len("PATH 中的 "):])
        return value

    r = report(cfg=cfg)
    line = "─" * 66
    print(line)
    print(t("rule_title"))
    print(line)
    print(t("platform", value=r["platform"]))
    print(t("app_root", value=r["app_root"]))
    print(t("media_root", value=r["media_root"], kind=loc(r["media_kind"])))
    print(t("config", value=loc(r["config"])))
    if r["windows_user_home"]:
        print(t("windows_user", value=r["windows_user_home"]))
    print()
    py = r["python"]
    if py["ok"]:
        print(t("py_ok", version=py["version"], origin=loc(py["origin"])))
        print(f"               {py['cmd']}")
    else:
        print(t("py_none"))
        for item in py["tried"]:
            mark = "✗" if not item["ok"] else "✓"
            why = t("py_too_old", ver=item["ver"]) if item["ver"] and not item["ok"] else t("py_cannot_run")
            print(f"      {mark} {item['cmd']}  ({loc(item['origin'])}) {why}")
    print()
    print(t("sessions_dirs"))
    for a in r["agents"]:
        if a["found"]:
            cnt = t("count", files=a["files"]) if a["files"] >= 0 else t("read_failed")
            print(f"    ✓ {a['label']:<16} {cnt}")
            print(f"      {a['data']}")
        else:
            print(f"    · {a['label']:<16} {t('not_installed')}")
            print(f"      {a['data']}")
        for error in a.get("errors", []):
            print(f"      ↳ {render(error, lang)}")
        if a["key"] == "claude_sdk":
            print(f"      ↳ {t('sdk_shared')}")
    print()
    print(line)
    return 0 if py["ok"] else 2


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(print_report())
