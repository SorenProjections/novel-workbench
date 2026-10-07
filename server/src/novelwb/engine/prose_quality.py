"""Deterministic prose quality checks used to bound Graph 4 regeneration."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

_BLOCK_MARKER_RE = re.compile(r"【块(?:－|-)[^】]+】|【块结束】")
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;]+")
_COMPACT_RE = re.compile(r"[\s，。！？；：、,.!?;:'\"“”‘’（）()《》【】—…]+")
_FILLER_PATTERNS = (
    "不知为何",
    "心中一颤",
    "心头一震",
    "就在这时",
    "说时迟那时快",
    "空气仿佛凝固",
    "时间仿佛静止",
)


@dataclass(frozen=True)
class ProseQualityReport:
    score: float
    passed: bool
    issues: list[str] = field(default_factory=list)
    metrics: dict[str, float | int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProseQualityEvaluator:
    """Score mechanical prose signals without pretending to judge literary taste."""

    def __init__(self, threshold: float = 72.0) -> None:
        self.threshold = float(threshold)

    @staticmethod
    def effective_char_count(text: str) -> int:
        body = _BLOCK_MARKER_RE.sub("", text or "").strip()
        return len(_COMPACT_RE.sub("", body))

    def evaluate(self, text: str, target_chars: int = 0) -> ProseQualityReport:
        body = _BLOCK_MARKER_RE.sub("", text or "").strip()
        compact = _COMPACT_RE.sub("", body)
        char_count = self.effective_char_count(body)
        score = 100.0 if char_count else 0.0
        issues: list[str] = [] if char_count else ["正文为空或仅含标点/块标记"]

        length_ratio = char_count / target_chars if target_chars > 0 else 1.0
        length_passed = target_chars <= 0 or 0.75 <= length_ratio <= 1.35
        if target_chars > 0 and length_ratio < 0.75:
            penalty = min(45.0, (0.75 - length_ratio) * 90.0)
            score -= penalty
            issues.append(f"正文长度仅达到目标的 {length_ratio:.0%}")
        elif target_chars > 0 and length_ratio > 1.35:
            penalty = min(20.0, (length_ratio - 1.35) * 30.0)
            score -= penalty
            issues.append(f"正文长度超过目标至 {length_ratio:.0%}")

        repeat_ratio = self._repeated_shingle_ratio(compact)
        if repeat_ratio > 0.08:
            score -= min(28.0, (repeat_ratio - 0.08) * 120.0)
            issues.append(f"连续短语重复率偏高（{repeat_ratio:.1%}）")

        sentence_lengths = [
            len(_COMPACT_RE.sub("", sentence))
            for sentence in _SENTENCE_SPLIT_RE.split(body)
            if _COMPACT_RE.sub("", sentence)
        ]
        sentence_cv = self._coefficient_of_variation(sentence_lengths)
        if len(sentence_lengths) >= 6 and sentence_cv < 0.22:
            score -= min(10.0, (0.22 - sentence_cv) * 45.0)
            issues.append("句长变化不足，节奏趋于机械")

        filler_hits = sum(body.count(pattern) for pattern in _FILLER_PATTERNS)
        filler_per_k = filler_hits * 1000 / max(char_count, 1)
        if filler_per_k > 2.5:
            score -= min(18.0, (filler_per_k - 2.5) * 2.5)
            issues.append(f"模板化过渡语偏多（每千字 {filler_per_k:.1f} 次）")

        longest_paragraph = max((len(p.strip()) for p in body.splitlines()), default=0)
        if longest_paragraph > 1200:
            score -= min(10.0, (longest_paragraph - 1200) / 160.0)
            issues.append("存在过长段落，阅读呼吸不足")

        score = round(max(0.0, min(100.0, score)), 2)
        return ProseQualityReport(
            score=score,
            passed=score >= self.threshold and length_passed,
            issues=issues,
            metrics={
                "char_count": char_count,
                "target_chars": max(0, int(target_chars)),
                "length_ratio": round(length_ratio, 4),
                "repeated_shingle_ratio": round(repeat_ratio, 4),
                "sentence_count": len(sentence_lengths),
                "sentence_length_cv": round(sentence_cv, 4),
                "filler_hits": filler_hits,
                "filler_hits_per_1000_chars": round(filler_per_k, 4),
                "longest_paragraph": longest_paragraph,
            },
        )

    @staticmethod
    def _repeated_shingle_ratio(text: str, width: int = 6) -> float:
        if len(text) < width * 3:
            return 0.0
        shingles = [text[i : i + width] for i in range(len(text) - width + 1)]
        counts = Counter(shingles)
        repeated = sum(count - 1 for count in counts.values() if count > 1)
        return repeated / max(1, len(shingles))

    @staticmethod
    def _coefficient_of_variation(values: list[int]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        if mean <= 0:
            return 0.0
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return math.sqrt(variance) / mean
