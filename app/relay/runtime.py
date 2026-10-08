"""Locate writable portable data beside the source tree or packaged app."""
import os
import sys
from pathlib import Path


def project_root():
    if getattr(sys, "frozen", False):
        portable = os.environ.get("RELAY_PORTABLE_ROOT")
        if portable:
            path = Path(portable).expanduser()
            if not path.is_absolute():
                raise ValueError("RELAY_PORTABLE_ROOT 必须是绝对路径")
            return path.resolve()
        executable = Path(sys.executable).resolve()
        # macOS executable lives in AgentRelay.app/Contents/MacOS/.
        if executable.parent.name == "MacOS" and executable.parent.parent.name == "Contents":
            return executable.parents[3]
        return executable.parent
    here = Path(__file__).resolve()
    if here.parents[1].name == "app":
        return here.parents[2]            # 源码目录 / U 盘便携版：数据放在 app/ 旁边
    return installed_data_dir()


def installed_data_dir():
    """pip / pipx 安装后包在 site-packages 里，不能往那里写数据；改用每用户数据目录。"""
    override = os.environ.get("RELAY_PORTABLE_ROOT")
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise ValueError("RELAY_PORTABLE_ROOT 必须是绝对路径")
        return path.resolve()
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming") / "AgentRelay"
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support" / "AgentRelay"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "agent-relay"
    return base
