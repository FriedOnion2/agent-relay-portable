"""清洗/pretty-print 辅助。

各家 agent 写入会话时会带上自己的运行时脚手架（系统提示、identity 文件、
skills 清单、reminder 等）。迁移时这些是噪音：目标 agent 会重新注入自己的版本，
原样搬过去既占上下文又可能串味。
"""

from __future__ import annotations

import re

# 需要整块剥离的 XML 标签名（不区分大小写）
_STRIP_TAGS = (
    "system-reminder",
    "system_reminder",
    "user_info",
    "identity_context",
    "available_skills",
    "memory_and_skills_reminder",
    "project_layout",
    "current_time",
    "product_identity",
    "connector-status",
    "agent_skills",
    "library_routing",
    "office_skill_routing",
    "plugin_recommendation",
    "tool_use_policy",
    "tool_usage_policy",
    "task_management",
    "asking_questions",
    "agent_loop",
    "result_presentation",
    "sharing_files",
    "final_answer_instructions",
    "automations",
    "agent_mail",
    "mcp_configuration",
    "response_language",
    "binary_context",
    "working_modes",
    "personal_files_safety",
    "content_policy",
    "regional_conventions",
    "instructions_for_visualizer",
    "visualizer_examples",
    "web_development_policy",
    "app_development_routing",
    "expert_management",
    "system-reminder-data",
)

_TAG_RE = re.compile(
    r"<(" + "|".join(_STRIP_TAGS) + r")\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)

# 兜底：没配对的开标签也一并吃掉
_OPEN_RE = re.compile(
    r"<(" + "|".join(_STRIP_TAGS) + r")\b[^>]*>",
    re.IGNORECASE,
)

# `<system-reminder data-role="...">` 这种带属性的
_ATTR_RE = re.compile(r"<system-reminder[^>]*>")

_CODE_FENCE_RE = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)


# -------- 只需脱标签、保留内层内容的标签 --------
_UNWRAP_TAGS = ("user_query", "command-name", "command-message", "local-command-stdout")

_UNWRAP_RE = re.compile(
    r"</?(" + "|".join(_UNWRAP_TAGS) + r")\b[^>]*>",
    re.IGNORECASE,
)


def strip_scaffolding(text: str) -> str:
    """剥掉 agent 专属的运行时注入块，只留下用户/模型的真实内容。

    两件事：
      1. system-reminder / user_info 这类整块删除（内容跟目标 agent 无关）
      2. <user_query> 这类只脱标签、保留正文（正文正是用户真正说的话）
    """
    if not text:
        return ""
    cur = _UNWRAP_RE.sub("", text)
    prev = None
    # 多轮剥离，处理嵌套
    for _ in range(3):
        prev = cur
        cur = _TAG_RE.sub("", cur)
        cur = _ATTR_RE.sub("", cur)
        cur = _OPEN_RE.sub("", cur)
        if cur == prev:
            break
    cur = re.sub(r"\n{3,}", "\n\n", cur)
    return cur.strip()


# 明显的系统/开发者 prompt 特征（长度或固定开头）
_DEV_HINTS = (
    "you are codex",
    "you are claude",
    "you are a helpful",
    "these are the tools",
    "here are the tools",
    "<app-context>",
    "<environment_context>",
    "instructions:\n",
)


def looks_like_system_prompt(text: str) -> bool:
    """判断一段文本是不是 agent 自己注入的 system/developer prompt。"""
    if not text:
        return False
    low = text.lower().lstrip()
    # 超长且含工具清单等特征
    if len(text) > 4000:
        return True
    return any(low.startswith(h) for h in _DEV_HINTS)


def markdown_escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace("`", "\\`")


def to_markdown_blocks(text: str) -> str:
    """把裸文本包装一下，避免markdown渲染时格式塌掉。"""
    return text or ""
