"""Complexity routing derived from an explicit user brief."""

from __future__ import annotations

from typing import Any

_LOW_MARKERS = (
    "简单",
    "无脑爽",
    "无脑",
    "不复杂",
    "逻辑简单",
    "直白",
    "单线",
    "轻松爽",
    "不要阴谋",
    "不要反转",
    "低门槛",
)
_HIGH_MARKERS = (
    "复杂",
    "群像",
    "多线",
    "烧脑",
    "权谋",
    "多重反转",
    "硬核",
    "高阅读门槛",
    "史诗",
)


def detect_complexity_profile(user_brief: str) -> dict[str, Any]:
    text = (user_brief or "").strip().lower()
    low_hits = [marker for marker in _LOW_MARKERS if marker in text]
    high_hits = [marker for marker in _HIGH_MARKERS if marker in text]
    if low_hits and not high_hits:
        level = "low"
    elif high_hits and not low_hits:
        level = "high"
    else:
        level = "medium"
    return {
        "level": level,
        "evidence": low_hits or high_hits,
        "candidate_policy": "single"
        if level == "low"
        else "bounded"
        if level == "medium"
        else "spec",
        "plot_logic": "单线推进、直接因果"
        if level == "low"
        else "受控多线"
        if level == "medium"
        else "允许多线交织",
        "hidden_layers_max": 0 if level == "low" else 1 if level == "medium" else 3,
        "gray_forces_allowed": level == "high",
    }
