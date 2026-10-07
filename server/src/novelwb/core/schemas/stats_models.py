"""统计模型 — fatigue/intent分布/钩子重复率等结构。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IntentDistribution(BaseModel):
    """ChapterIntent 分布统计。"""

    advance: int = 0
    settle: int = 0
    foreshadow: int = 0
    breather: int = 0
    total: int = 0

    @property
    def breather_ratio(self) -> float:
        return self.breather / self.total if self.total > 0 else 0.0

    @property
    def consecutive_breather_max(self) -> int:
        """需要外部传入序列来计算，此处仅占位。"""
        return 0

    model_config = {"extra": "forbid"}


class HookRotationStats(BaseModel):
    """钩子类型轮换统计。"""

    hook_counts: dict[str, int] = Field(default_factory=dict)
    repeat_rate: float = 0.0  # 连续重复同类型钩子的比例
    dominant_hook: str | None = None

    model_config = {"extra": "forbid"}


class MomentumDebtStats(BaseModel):
    """动量债趋势统计。"""

    current_debt: int = 0
    peak_debt: int = 0
    trend: list[int] = Field(default_factory=list)  # 近N章的债值序列
    overdue_count: int = 0

    model_config = {"extra": "forbid"}


class VolumeStats(BaseModel):
    """卷级统计快照。"""

    volume_id: str
    project_id: str
    event_count: int = 0
    chapter_count: int = 0
    total_chars: int = 0
    intent_distribution: IntentDistribution = Field(default_factory=IntentDistribution)
    hook_rotation: HookRotationStats = Field(default_factory=HookRotationStats)
    momentum_debt: MomentumDebtStats = Field(default_factory=MomentumDebtStats)
    new_entities_count: int = 0
    new_terms_count: int = 0
    advance_delta_frequency: float = 0.0  # Advance章中三变量变动频率
    computed_at: datetime

    model_config = {"extra": "forbid"}


class FatigueWarning(BaseModel):
    """疲劳预警单条警告。"""

    warning_type: str  # breather_overuse | hook_repeat | momentum_overflow | training_gap
    severity: str  # info | warn | critical
    detail: str
    recommendation: str

    model_config = {"extra": "forbid"}


class FatigueSummary(BaseModel):
    """疲劳报告汇总（图3/图5生成，触发卷规划调整）。"""

    report_id: str
    project_id: str
    volume_id: str | None = None
    chapter_range_start: int = 0
    chapter_range_end: int = 0
    stats: VolumeStats
    warnings: list[FatigueWarning] = Field(default_factory=list)
    next_volume_recommendations: list[str] = Field(default_factory=list)
    intent_rotation_advice: str | None = None
    generated_at: datetime

    model_config = {"extra": "forbid"}
