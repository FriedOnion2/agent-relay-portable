"""Read an accessible Ubuntu home backup from Windows, never via ext4 drivers."""
import os
import platform
from pathlib import Path

from .windows import WindowsSource

PROFILE_ENV = "RELAY_UBUNTU_USER_HOME"


def selected_profile():
    if platform.system() != "Windows":
        return ""
    value = os.environ.get(PROFILE_ENV, "").strip()
    if value and not Path(value).expanduser().is_absolute():
        raise ValueError("Ubuntu 用户目录需要 Windows 可访问的绝对路径")
    return str(Path(value).expanduser()) if value else ""


class UbuntuSource(WindowsSource):
    def __init__(self, source, factory, profile, clean=True):
        super().__init__(source, factory, profile, clean=clean)
        self.name = "ubuntu_" + source
        self.label = self.label.replace("Windows ·", "Ubuntu ·")
        if source == "codebuddy":
            self.adapter.roots = [self.adapter.root, str(Path(profile) / ".config"
                                  / "CodeBuddyExtension" / "Data")]
            self.roots = self.adapter.roots
        self.read_note = "Ubuntu 只读来源：" + profile + "。需要已可访问的用户目录备份或共享目录。"

    def info(self):
        result = super().info()
        result.pop("windows_profile", None)
        result.update(ubuntu_profile=self.profile, write_note="Ubuntu 跨系统来源只读；迁移写入本机对应软件")
        if "error" in result:
            result["error"] = "Ubuntu 用户目录不可读，请核对备份/共享目录路径和权限"
        return result

    def read(self, sid):
        conv = super().read(sid)
        conv.meta.pop("windows_profile", None)
        conv.meta["ubuntu_profile"] = self.profile
        return conv
