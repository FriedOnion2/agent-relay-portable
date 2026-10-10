"""Read an accessible Ubuntu home backup from Windows, never via ext4 drivers."""

from .messages import text as message_text
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
        raise ValueError(message_text('err.ubuntu_user_directory_must_be_an_absolute_path_accessible_from_windows'))
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
        self.read_note = message_text('msg.ubuntu_read_only_source_profile_an_accessible_user_directory_backup_or_shared_directory_is', profile=profile)

    def info(self):
        result = super().info()
        result.pop("windows_profile", None)
        result.update(ubuntu_profile=self.profile, write_note=message_text('msg.ubuntu_cross_system_sources_are_read_only_migration_writes_to_the_corresponding_local_app'))
        if "error" in result:
            result["error"] = message_text('msg.ubuntu_user_directory_is_unreadable_check_backup_shared_directory_path_and_permissions')
        return result

    def read(self, sid):
        conv = super().read(sid)
        conv.meta.pop("windows_profile", None)
        conv.meta["ubuntu_profile"] = self.profile
        return conv
