"""International WorkBuddy AI: separate identity, shared JSONL protocol."""
import os
import re
from pathlib import Path

from .. import archive
from ..locations import resolve_home
from ..messages import text as message_text
from ..paths import is_windows_path
from .workbuddy import WorkBuddyAdapter


class WorkBuddyAIAdapter(WorkBuddyAdapter):
    name = 'workbuddy_ai'
    label = 'WorkBuddy AI (International)'
    read_note = message_text('msg.workbuddy_ai_file_support')

    def __init__(self, home=None, clean=True):
        root = Path(resolve_home(self.name, home))
        # The desktop can keep transcripts at the device root while user-*
        # contains only identity/memory files. Never let that hide its store.
        desktop_store = (root / 'projects').is_dir() or (root / 'workbuddy.db').is_file()
        scopes = sorted(path for path in root.glob('user-*') if path.is_dir())
        if any(archive.is_link(path) for path in scopes):
            raise ValueError(message_text('err.only_regular_files_can_be_packaged_symbolic_links_are_excluded'))
        if not desktop_store and len(scopes) > 1:
            raise ValueError(message_text('err.workbuddy_ai_select_account_directory'))
        super().__init__(home=str(root if desktop_store or not scopes else scopes[0]), clean=clean)

    def project_dir_for(self, cwd):
        # WorkBuddy AI 5.8.4 compressWorkspacePathName: preserve case, Unicode
        # and spaces; long components use a UTF-8 byte hash, not the legacy slug.
        native_absolute = os.path.isabs(cwd) and (os.name != 'nt' or is_windows_path(cwd))
        canonical = cwd
        if native_absolute:
            try:
                # Match the client's realpathSync try/catch: a missing full
                # path stays unchanged, even when a parent is a macOS link.
                canonical = str(Path(cwd).resolve(strict=True))
            except (OSError, RuntimeError):
                pass
        value = re.sub(r'-+', '-', re.sub(r'[/\\:]', '-', canonical)).strip('-')
        raw = value.encode('utf-8')
        if len(raw) <= 255:
            return value
        hashed = 5381
        for byte in raw:
            hashed = ((hashed * 33) ^ byte) & 0xffffffff
        suffix = ''
        while hashed:
            hashed, digit = divmod(hashed, 36)
            suffix = '0123456789abcdefghijklmnopqrstuvwxyz'[digit] + suffix
        return raw[:180].decode('utf-8', errors='ignore') + '-' + (suffix or '0')
