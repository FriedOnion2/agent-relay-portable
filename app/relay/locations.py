"""Independent source identities and host directory resolution."""
from __future__ import annotations

import os
import platform
from pathlib import Path

SOURCES = {
    "workbuddy": ("WorkBuddy", "projects"),
    "dsh": ("DeepSeek Harness", "sessions"),
    "codebuddy": ("CodeBuddy", ""),
    "claude": ("Claude Code", "projects"),
    "codex": ("OpenAI Codex", "sessions"),
}


def default_home(source: str) -> str:
    home = Path.home()
    if source == "codebuddy-ide":
        system = platform.system()
        if system == "Windows":
            return str(Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
                       / "CodeBuddyExtension" / "Data")
        if system == "Darwin":
            return str(home / "Library" / "Application Support" / "CodeBuddyExtension" / "Data")
        return str(home / ".config" / "CodeBuddyExtension" / "Data")
    return str(home / {"dsh":".dsh", "workbuddy":".workbuddy",
                       "codebuddy":".codebuddy", "claude":".claude", "codex":".codex"}[source])


def resolve_home(source: str, explicit: str | None = None) -> str:
    agent_env = {"dsh":"DSH_HOME", "workbuddy":"WORKBUDDY_HOME",
                 "codebuddy":"CODEBUDDY_HOME", "claude":"CLAUDE_CONFIG_DIR",
                 "codex":"CODEX_HOME"}[source]
    value = next((v.strip() for v in (explicit, os.environ.get("RELAY_" + source.upper() + "_HOME"),
                  os.environ.get(agent_env)) if v and v.strip()), default_home(source))
    return os.path.abspath(os.path.expanduser(value))
