"""Hash 稳定性工具 — normalization + SHA256。

规则：
- 所有 hash 使用 SHA256，hex digest
- dict 先按 key 排序再序列化（保证顺序无关）
- list 保持顺序（顺序是语义的一部分）
- str 先 strip()，再 NFC 规范化
- 空值（None/空dict/空list）统一归一化为 null/{}/(空)
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any


def _normalize_value(v: Any) -> Any:
    """递归规范化值，消除无意义差异。"""
    if v is None:
        return None
    if isinstance(v, str):
        return unicodedata.normalize("NFC", v.strip())
    if isinstance(v, dict):
        return {_normalize_value(k): _normalize_value(val) for k, val in sorted(v.items())}
    if isinstance(v, (list, tuple)):
        return [_normalize_value(item) for item in v]
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    # 其他类型转 str
    return str(v)


def stable_hash(data: Any) -> str:
    """对任意数据计算稳定 SHA256 hash（顺序无关的dict）。"""
    normalized = _normalize_value(data)
    serialized = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def file_hash(path: str) -> str:
    """对文件内容计算 SHA256 hash（NFC规范化文本）。"""
    import pathlib

    content = pathlib.Path(path).read_text(encoding="utf-8")
    normalized = unicodedata.normalize("NFC", content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    """对字符串计算稳定 hash（NFC + strip）。"""
    normalized = unicodedata.normalize("NFC", text.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def dict_hash(d: dict[str, Any]) -> str:
    """对 dict 计算稳定 hash（key 排序）。"""
    return stable_hash(d)
