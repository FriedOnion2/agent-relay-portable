"""敏感信息扫描与脱敏：在迁移、导出前发现会话里混入的密钥、令牌和口令。

只看文本，不联网、不调用模型。规则偏保守（高置信的厂商密钥格式 + 明确的「名称=值」赋值），
报告里只有类型、位置和长度，不包含密钥本身的任何片段；脱敏会把命中的内容替换成 [REDACTED:类型]。
扫描不能保证发现全部敏感信息，也不应被当作安全审计。
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Dict, List, Tuple

from . import ir
from .messages import text as message_text, join_text

_LABEL_CODES = {'private-key': 'msg.secret_private_key', 'anthropic-key': 'msg.secret_anthropic_key', 'openai-key': 'msg.secret_openai_key', 'github-token': 'msg.secret_github_token', 'aws-access-key': 'msg.secret_aws_access_key', 'google-api-key': 'msg.secret_google_api_key', 'slack-token': 'msg.secret_slack_token', 'stripe-key': 'msg.secret_stripe_key', 'tencent-key': 'msg.secret_tencent_key', 'aliyun-key': 'msg.secret_aliyun_key', 'jwt': 'msg.secret_jwt', 'bearer-token': 'msg.secret_bearer_token', 'url-credentials': 'msg.secret_url_credentials', 'secret-assignment': 'msg.secret_secret_assignment'}

# (类型, 说明, 正则, 取值的分组号；0 表示整个匹配)
RULES: List[Tuple[str, str, "re.Pattern[str]", int]] = [
    ("private-key", "私钥", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----[\s\S]{0,6000}?(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|\Z)"), 0),
    ("anthropic-key", "Anthropic API 密钥", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), 0),
    ("openai-key", "OpenAI / DeepSeek 风格 API 密钥", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}"), 0),
    ("github-token", "GitHub 令牌", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})"), 0),
    ("aws-access-key", "AWS 访问密钥 ID", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), 0),
    ("google-api-key", "Google API 密钥", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), 0),
    ("slack-token", "Slack 令牌", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), 0),
    ("stripe-key", "Stripe 密钥", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}"), 0),
    ("tencent-key", "腾讯云 SecretId", re.compile(r"\bAKID[A-Za-z0-9]{32}\b"), 0),
    ("aliyun-key", "阿里云 AccessKey ID", re.compile(r"\bLTAI[A-Za-z0-9]{12,20}\b"), 0),
    ("jwt", "JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), 0),
    ("bearer-token", "Authorization Bearer 令牌", re.compile(r"(?i)\bBearer\s+([A-Za-z0-9._~+/\-]{20,}=*)"), 1),
    ("url-credentials", "URL 中的账号口令", re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:([^\s/@]{3,})@"), 1),
    ("secret-assignment", "疑似口令 / 密钥赋值",
     re.compile(r"(?i)\b(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token|token|passwd|password|pwd)\b[\"']?\s*[:=]\s*[\"']?([^\s\"'`,;<>(){}\[\]]{8,})"), 1),
    ("secret-assignment", "疑似口令 / 密钥赋值",
     re.compile(r"(?:密码|口令|密钥)\s*[:：=]\s*[\"']?([^\s\"'`,，;；<>(){}\[\]]{6,})"), 1),
]

_PLACEHOLDER = re.compile(r"(?i)(?:x{3,}|\*{3,}|\.{3,}|your|example|sample|changeme|placeholder|dummy|redacted|"
                          r"<|\$\{|\$[A-Za-z_]|process\.env|os\.environ|getenv|env\.|null|none|true|false|undefined)")


def _looks_real(value: str) -> bool:
    if _PLACEHOLDER.search(value):
        return False
    return len(set(value)) >= 4          # 全是同一个或两三个字符的多半是示例


def scan_text(text: str) -> List[Dict[str, Any]]:
    """返回不重叠的命中：{kind, label, start, end（被取值的范围）, length}。不返回任何取值片段（连掩码也不给）。"""
    if not text or len(text) < 8:
        return []
    found: List[Dict[str, Any]] = []
    taken: List[Tuple[int, int]] = []
    for kind, _label, pattern, group in RULES:
        for match in pattern.finditer(text):
            start, end = match.span(group)
            if start < 0 or end <= start:
                continue
            value = text[start:end]
            if kind == "secret-assignment" and not _looks_real(value):
                continue
            if any(start < b and a < end for a, b in taken):
                continue
            taken.append((start, end))
            found.append({"kind": kind, "label": message_text(_LABEL_CODES[kind]), "start": start, "end": end, "length": end - start})
    found.sort(key=lambda row: row["start"])
    return found


def redact_text(text: str) -> str:
    if not text:
        return text
    pieces, last = [], 0
    for row in scan_text(text):
        pieces.append(text[last:row["start"]])
        pieces.append("[REDACTED:%s]" % row["kind"])
        last = row["end"]
    pieces.append(text[last:])
    return "".join(pieces)


_FIELDS = {ir.TEXT: ("text",), ir.THINKING: ("text",), ir.TOOL_CALL: ("arguments",), ir.TOOL_RESULT: ("output",)}


def scan_conversation(conv: ir.Conversation) -> Dict[str, Any]:
    kinds: Dict[str, Dict[str, Any]] = {}
    locations: List[Dict[str, Any]] = []
    for turn_index, turn in enumerate(conv.turns):
        for block_index, block in enumerate(turn.blocks):
            for field_name in _FIELDS.get(block.kind, ()):
                for row in scan_text(getattr(block, field_name)):
                    entry = kinds.setdefault(row["kind"], {"kind": row["kind"], "label": row["label"], "count": 0})
                    entry["count"] += 1
                    if len(locations) < 200:
                        locations.append({"turn": turn_index, "block": block_index, "field": field_name,
                                          "kind": row["kind"], "length": row["length"]})
    ordered = sorted(kinds.values(), key=lambda row: -row["count"])
    return {"total": sum(row["count"] for row in ordered), "kinds": ordered, "locations": locations}


def redact_conversation(conv: ir.Conversation) -> ir.Conversation:
    turns = []
    for turn in conv.turns:
        blocks = []
        for block in turn.blocks:
            changes = {name: redact_text(getattr(block, name)) for name in _FIELDS.get(block.kind, ())}
            blocks.append(replace(block, **changes) if changes else block)
        turns.append(replace(turn, blocks=blocks))
    return replace(conv, turns=turns)


def summary_line(result: Dict[str, Any]) -> str:
    return join_text((message_text('msg.secret_count', label=row['label'], count=row['count'])
                      for row in result['kinds']), '、')
