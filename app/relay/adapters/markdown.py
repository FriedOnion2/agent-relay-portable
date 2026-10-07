"""导出成可读 markdown —— 通用"交接文档"。

不管目标 agent 是哪家，这份 md 都能直接贴进去当上下文。
"""

from __future__ import annotations

from typing import List

from .. import ir

ROLE_LABEL = {
    ir.USER: "👤 用户",
    ir.ASSISTANT: "🤖 助手",
    ir.SYSTEM: "⚙️ 系统",
}


def render(conv: ir.Conversation, include_thinking: bool = True,
           include_tools: bool = True, max_text: int = 0) -> str:
    lines: List[str] = []
    lines.append(f"# {conv.title or '未命名会话'}")
    lines.append("")
    if conv.cwd:
        lines.append(f"- **工作目录**：`{conv.cwd}`")
    if conv.model:
        lines.append(f"- **模型**：{conv.model}")
    lines.append(f"- **来源**：{conv.source}")
    for note in conv.meta.get("notes", []):
        lines.append(f"- **读取说明**：{note}")
    if conv.created_at:
        lines.append(f"- **创建时间**：{conv.created_at}")
    if conv.updated_at:
        lines.append(f"- **最后更新**：{conv.updated_at}")
    st = conv.stats()
    lines.append(f"- **轮次**：{st.get('turns', 0)}（用户 {st.get('user', 0)} / 助手 {st.get('assistant', 0)}，"
                 f"工具调用 {st.get('tool_call', 0)}）")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, turn in enumerate(conv.turns, 1):
        label = ROLE_LABEL.get(turn.role, turn.role)
        lines.append(f"## {i}. {label}")
        if turn.ts:
            lines.append(f"*时间：{turn.ts}*" + (f" · *模型：{turn.model}*" if turn.model else ""))
            lines.append("")
        for b in turn.blocks:
            if b.kind == ir.THINKING:
                if not include_thinking:
                    continue
                txt = b.text
                lines.append("<details><summary>💭 思考过程</summary>")
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
                lines.append(f"**🔧 工具调用：`{b.name}`**")
                lines.append("")
                lines.append("```json")
                lines.append(_clip(b.arguments, max_text))
                lines.append("```")
                lines.append("")
            elif b.kind == ir.TOOL_RESULT:
                if not include_tools:
                    continue
                tag = "❌ 工具出错" if b.is_error else "📤 工具结果"
                lines.append(f"**{tag}** `{b.call_id}`")
                lines.append("")
                lines.append("```")
                lines.append(_clip(b.output, max_text))
                lines.append("```")
                lines.append("")
            elif b.kind == ir.IMAGE:
                lines.append("_（图片，已省略）_")
                lines.append("")
        lines.append("")
    return "\n".join(lines)


def _clip(s: str, max_text: int) -> str:
    s = s or ""
    if max_text and len(s) > max_text:
        return s[:max_text] + f"\n… 截断（共 {len(s)} 字符）"
    return s
