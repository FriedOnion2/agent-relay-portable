"""Independent source identities and host directory resolution."""
from __future__ import annotations

import os
import platform
from pathlib import Path

SOURCES = {
    "workbuddy": ("WorkBuddy", "projects"),
    "workbuddy_ai": ("WorkBuddy AI (International)", "projects"),
    "dsh": ("DeepSeek Harness", "sessions"),
    "codebuddy": ("CodeBuddy", ""),
    "claude": ("Claude Code", "projects"),
    "claude_sdk": ("Claude Agent SDK", "projects"),
    "codex": ("OpenAI Codex", "sessions"),
    "yuanbao": ("Tencent Yuanbao", ""),
}

CROSS_ACCOUNT_SOURCES = ('windows_workbuddy_ai', 'ubuntu_workbuddy_ai')


def default_home(source: str) -> str:
    if source == "yuanbao":
        from .runtime import project_root
        return str(project_root() / "imports" / "yuanbao")
    home = Path.home()
    if source == "codebuddy-ide":
        system = platform.system()
        if system == "Windows":
            return str(Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
                       / "CodeBuddyExtension" / "Data")
        if system == "Darwin":
            return str(home / "Library" / "Application Support" / "CodeBuddyExtension" / "Data")
        return str(home / ".config" / "CodeBuddyExtension" / "Data")
    return str(home / {"dsh":".dsh", "workbuddy":".workbuddy", "workbuddy_ai":".workbuddy-ai",
                       "codebuddy":".codebuddy", "claude":".claude", "claude_sdk":".claude", "codex":".codex"}[source])


def resolve_home(source: str, explicit: str | None = None) -> str:
    agent_env = {"dsh":"DSH_HOME", "workbuddy":"WORKBUDDY_HOME", "workbuddy_ai":"WORKBUDDY_AI_HOME",
                 "codebuddy":"CODEBUDDY_HOME", "claude":"CLAUDE_CONFIG_DIR", "claude_sdk":"CLAUDE_CONFIG_DIR",
                 "codex":"CODEX_HOME", "yuanbao":"YUANBAO_EXPORT_HOME"}[source]
    value = next((v.strip() for v in (explicit, os.environ.get("RELAY_" + source.upper() + "_HOME"),
                  os.environ.get(agent_env)) if v and v.strip()), None)
    value = value or default_home(source)
    return os.path.abspath(os.path.expanduser(value))
