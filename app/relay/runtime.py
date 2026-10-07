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
    return Path(__file__).resolve().parents[2]
