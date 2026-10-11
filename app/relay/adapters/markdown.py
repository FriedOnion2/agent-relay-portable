"""导出成可读 markdown —— 通用"交接文档"。

不管目标 agent 是哪家，这份 md 都能直接贴进去当上下文。
"""

from __future__ import annotations

import json
from typing import List

from .. import ir
from ..messages import lang_text

ROLE_CODES = {
    ir.USER: "msg.md_role_user",
    ir.ASSISTANT: "msg.md_role_assistant",
    ir.SYSTEM: "msg.md_role_system",
}


def render(conv: ir.Conversation, include_thinking: bool = True,
           include_tools: bool = True, max_text: int = 0, lang: str = "zh") -> str:
    def t(code, **params):
        return lang_text(lang, code, **params)

    lines: List[str] = []
    lines.append(f"# {conv.title or t('msg.md_untitled_session')}")
    lines.append("")
    if conv.cwd:
        lines.append(t("msg.md_working_directory", value=conv.cwd))
    if conv.model:
        lines.append(t("msg.md_model", value=conv.model))
    lines.append(t("msg.md_source", value=conv.source))
    for note in conv.meta.get("notes", []):
        lines.append(t("msg.md_read_note", value=note))
    if conv.truncated:
        lines.append(t("msg.md_truncated_note"))
    if conv.created_at:
        lines.append(t("msg.md_created_at", value=conv.created_at))
    if conv.updated_at:
        lines.append(t("msg.md_updated_at", value=conv.updated_at))
    st = conv.stats()
    lines.append(t("msg.md_turn_stats", turns=st.get('turns', 0), user=st.get('user', 0),
                   assistant=st.get('assistant', 0), tools=st.get('tool_call', 0)))
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, turn in enumerate(conv.turns, 1):
        label = t(ROLE_CODES[turn.role]) if turn.role in ROLE_CODES else turn.role
        lines.append(f"## {i}. {label}")
        if turn.ts:
            lines.append(t("msg.md_time", value=turn.ts) + (t("msg.md_time_model", value=turn.model) if turn.model else ""))
            lines.append("")
        for b in turn.blocks:
            if b.kind == ir.THINKING:
                if not include_thinking:
                    continue
                txt = b.text
                lines.append(t("msg.md_thinking"))
                lines.append("")
                lines.append(txt)
                lines.append("")
                lines.append("</details>")
                lines.append("")
            elif b.kind == ir.TEXT:
                lines.append(b.text)
                lines.append("")
            elif b.kind == ir.TOOL_CALL:
                if not include_tools:
                    continue
                lines.append(t("msg.md_tool_call", name=b.name))
                lines.append("")
                lines.append("```json")
                lines.append(_clip(b.arguments, max_text, lang))
                lines.append("```")
                lines.append("")
            elif b.kind == ir.TOOL_RESULT:
                if not include_tools:
                    continue
                tag = t("msg.md_tool_error") if b.is_error else t("msg.md_tool_result")
                lines.append(f"**{tag}** `{b.call_id}`")
                lines.append("")
                lines.append("```")
                lines.append(_clip(b.output, max_text, lang))
                lines.append("```")
                lines.append("")
            elif b.kind == ir.IMAGE:
                lines.append(t("msg.md_image_omitted"))
                lines.append("")
            elif b.kind == ir.RAW:
                lines.extend([t("msg.md_raw_block"), "", "```json",
                              _clip(json.dumps(b.meta, ensure_ascii=False, indent=2), max_text, lang), "```", ""])
        lines.append("")
    return "\n".join(lines)


def _clip(s: str, max_text: int, lang: str = "zh") -> str:
    s = s or ""
    if max_text and len(s) > max_text:
        return s[:max_text] + lang_text(lang, "msg.md_clipped", count=len(s))
    return s
