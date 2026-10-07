"""Read mounted Windows profiles without changing the host's native stores."""
from __future__ import annotations

import os
import platform
import re
from dataclasses import replace
from pathlib import Path

from .locations import SOURCES
from .adapters.base import ReadOnlyAdapter

PROFILE_ENV = "RELAY_WINDOWS_USER_HOME"
PROFILE_DIRS = {"workbuddy": ".workbuddy", "dsh": ".dsh", "codebuddy": ".codebuddy",
                "claude": ".claude", "claude_sdk": ".claude", "codex": ".codex"}


def selected_profile():
    # A portable config travels between systems; Linux mount paths must not
    # redirect the native Windows or macOS sources when the OS changes.
    if platform.system() != "Linux":
        return ""
    value = os.environ.get(PROFILE_ENV, "").strip()
    if not value:
        return ""
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Windows 用户目录需要 Ubuntu 中的绝对挂载路径，不能填写 C:\\Users 路径")
    return str(path)


def mounted_roots():
    """Mount table plus conventional desktop/manual mount locations, no recursion."""
    roots = {Path("/mnt")}
    try:
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) > 4:
                roots.add(Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4])))
    except OSError:
        pass
    for base, depth in ((Path("/media"), 2), (Path("/run/media"), 2), (Path("/mnt"), 1)):
        level = [base]
        for _ in range(depth):
            following = []
            for parent in level:
                try:
                    following.extend(p for p in parent.iterdir() if p.is_dir())
                except OSError:
                    continue
            roots.update(following)
            level = following
    return sorted(roots, key=str)


def discover_profiles(roots=None):
    if platform.system() != "Linux":
        return []
    rows, seen = [], set()
    for root in mounted_roots() if roots is None else roots:
        users = Path(root) / "Users"
        try:
            profiles = sorted(users.iterdir(), key=lambda p: p.name.casefold())
        except OSError:
            continue
        for profile in profiles:
            try:
                if not profile.is_dir():
                    continue
                canonical = str(profile.resolve())
                if canonical in seen:
                    continue
                seen.add(canonical)
                found = [key for key, folder in PROFILE_DIRS.items() if (profile / folder).is_dir()]
                ide = profile / "AppData" / "Local" / "CodeBuddyExtension" / "Data"
                if ide.is_dir() and "codebuddy" not in found:
                    found.append("codebuddy")
                if found:
                    rows.append({"user": profile.name, "home": str(profile), "sources": found,
                                 "readable": os.access(profile, os.R_OK | os.X_OK)})
            except OSError:
                continue
    return rows


class WindowsSource(ReadOnlyAdapter):
    """Delegate format parsing while enforcing read-only at the adapter boundary."""
    def __init__(self, source, factory, profile, clean=True):
        self.name = "windows_" + source
        self.label = "Windows · " + SOURCES[source][0]
        self.profile = profile
        self.source = source
        self.adapter = factory(home=str(Path(profile) / PROFILE_DIRS[source]), clean=clean)
        if source == "codebuddy":
            self.adapter.roots = [self.adapter.root, str(Path(profile) / "AppData" / "Local"
                                  / "CodeBuddyExtension" / "Data")]
        self.home = self.adapter.home
        self.root = getattr(self.adapter, "root", self.home)
        self.roots = getattr(self.adapter, "roots", [self.home])
        self.read_note = (f"Windows 只读来源：{profile}。仅读取与导出；迁出需指定 Ubuntu 项目目录。 "
                          + getattr(self.adapter, "read_note", ""))

    def available(self):
        return self.adapter.available()

    def info(self):
        result = super().info()
        result.update(homes=self.roots, windows_profile=self.profile,
                      write_note="Windows 跨系统来源只读，不写回 Windows 会话目录")
        if not Path(self.profile).is_dir():
            result["error"] = "Windows 用户目录不可访问，请先挂载分区并核对路径"
        elif not os.access(self.profile, os.R_OK | os.X_OK):
            result["error"] = "Windows 用户目录没有读取权限，请检查挂载权限"
        return result

    def discover(self):
        for row in self.adapter.discover():
            yield replace(row, source=self.name)

    def read(self, sid):
        conv = self.adapter.read(sid)
        # Do not alter the delegate's cached object or its provenance metadata.
        return replace(conv, source=self.name, meta={**conv.meta,
                       "windows_profile": self.profile,
                       "notes": [*conv.meta.get("notes", []), self.read_note]})
