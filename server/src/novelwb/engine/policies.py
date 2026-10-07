"""Policies — 修复策略与重试决策层。

决策逻辑完全与图执行分离，便于单独测试和调整。
"""

from __future__ import annotations

from dataclasses import dataclass

from novelwb.core.constants import Defaults, FixLevel
from novelwb.core.schemas.domain_models import DiffReport

# ── 修复策略 ──────────────────────────────────────────────────────────────


@dataclass
class RepairDecision:
    """修复决策结果。"""

    fix_level: FixLevel
    should_retry: bool  # True = 重新生成；False = 提交（或中止）
    should_abort: bool  # True = 已超过重试上限，须人工介入
    reason: str


class RepairPolicy:
    """根据 DiffReport 决定修复行动。

    fix_level 推断：
      L0 — B/D/E 违规：边界补丁（重写开头 200-800 字）
      L1 — A/C 违规：局部回滚（重写前 1-2 块）
      L2 — F/G 违规：整事件回滚（重新生成）
    """

    def __init__(self, max_retries: int = Defaults.MAX_RETRY_COUNT) -> None:
        self._max_retries = max_retries

    def decide(self, report: DiffReport, attempt: int) -> RepairDecision:
        """根据 DiffReport 和当前尝试次数给出修复决策。

        Args:
            report:  HardLint 返回的 DiffReport。
            attempt: 当前是第几次尝试（0-indexed）。

        Returns:
            RepairDecision
        """
        if report.passed:
            return RepairDecision(
                fix_level=FixLevel.L0,
                should_retry=False,
                should_abort=False,
                reason="HardLint passed",
            )

        if attempt >= self._max_retries:
            return RepairDecision(
                fix_level=FixLevel.L2,
                should_retry=False,
                should_abort=True,
                reason=f"超过最大重试次数 ({self._max_retries})，须人工介入",
            )

        fix_level_str = report.fix_level_suggested or FixLevel.L0.value
        try:
            fix_level = FixLevel(fix_level_str)
        except ValueError:
            fix_level = FixLevel.L0

        return RepairDecision(
            fix_level=fix_level,
            should_retry=True,
            should_abort=False,
            reason=(
                f"违规 {len(report.violated_forbidden)} 条，"
                f"fix_level={fix_level.value}，重试 attempt={attempt + 1}"
            ),
        )


# ── 重试策略 ──────────────────────────────────────────────────────────────


class RetryPolicy:
    """通用重试决策（不依赖 DiffReport）。

    用于 LLM 调用失败的网络重试（DeepSeekAdapter 内部已有，
    此处用于图级别的"步骤失败整体重试"。）
    """

    def __init__(
        self,
        max_retries: int = Defaults.MAX_RETRY_COUNT,
        human_threshold: int = Defaults.HUMAN_OVERRIDE_THRESHOLD,
    ) -> None:
        self._max_retries = max_retries
        self._human_threshold = human_threshold

    def should_retry(self, attempt: int) -> bool:
        return attempt < self._max_retries

    def need_human(self, consecutive_failures: int) -> bool:
        return consecutive_failures >= self._human_threshold
