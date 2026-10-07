"""敏感信息脱敏 — API Key、路径等不进日志/响应。"""

from __future__ import annotations

import re
from typing import Any

# 需要脱敏的字段名（大小写不敏感）
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "secret",
        "password",
        "token",
        "deepseek_api_key",
        "authorization",
    }
)

# API Key 模式（sk- 开头）
_KEY_PATTERN = re.compile(r"(sk-[A-Za-z0-9]{4})[A-Za-z0-9]+")


def redact_key(value: str) -> str:
    """脱敏单个 Key 字符串，保留前缀。"""
    return _KEY_PATTERN.sub(r"\1****", value)


def redact_dict(data: Any, depth: int = 0) -> Any:
    """递归脱敏 dict 中的敏感字段。"""
    if depth > 10:
        return data
    if isinstance(data, dict):
        return {
            k: ("****" if k.lower() in _SENSITIVE_KEYS else redact_dict(v, depth + 1))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_dict(item, depth + 1) for item in data]
    if isinstance(data, str):
        return redact_key(data)
    return data


def safe_repr(data: Any, max_len: int = 200) -> str:
    """返回脱敏后的简短表示，用于日志。"""
    import json

    redacted = redact_dict(data)
    text = json.dumps(redacted, ensure_ascii=False, separators=(",", ":"))
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
