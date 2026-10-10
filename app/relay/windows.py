"""Read mounted Windows profiles without changing the host's native stores."""
from __future__ import annotations

from .messages import text as message_text

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
        raise ValueError(message_text('err.windows_user_directory_must_be_an_absolute_mounted_path_in_ubuntu_not_c_users'))
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
        self.read_note = (message_text('msg.windows_read_only_source_profile_reading_and_export_only_migration_requires_an_ubuntu_proj', profile=profile, value=getattr(self.adapter, "read_note", "")))

    def available(self):
        return self.adapter.available()

    def info(self):
        result = super().info()
        result.update(homes=self.roots, windows_profile=self.profile,
                      native_import=True, native_target=self.source,
                      write_note=message_text('msg.browsing_adapters_are_read_only_to_write_back_use_the_migration_entry_for_the_correspondin'))
        if not Path(self.profile).is_dir():
            result["error"] = message_text('msg.windows_user_directory_is_inaccessible_mount_the_partition_and_check_the_path_first')
        elif not os.access(self.profile, os.R_OK | os.X_OK):
            result["error"] = message_text('msg.windows_user_directory_is_not_readable_check_mount_permissions')
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
