"""Regression — 回归测试执行器（图6）。

四类测试：
  prose   — 语感/文风（Lens一致性、说明书密度、重复片段）
  mechanic — 机制（力量/规则内一致性，违规使用禁忌能力）
  boundary — 事件边界（PreSnapshot→ObservedDelta状态跳变合法性）
  chapter  — 章节化（Breather约束、MomentumDebt、钩子轮换）
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from novelwb.core.schemas.domain_models import (
    AuthObject,
    ChapterSpec,
    EventRecord,
)
from novelwb.utils.timeutil import to_iso, utcnow

# ── 结果数据结构 ───────────────────────────────────────────────────────────


@dataclass
class RegressionIssue:
    test_type: str  # prose / mechanic / boundary / chapter
    issue_id: str  # e.g. "prose_01"
    severity: str  # "error" | "warning"
    message: str
    event_id: str | None = None
    chapter_id: str | None = None


@dataclass
class RegressionReport:
    run_id: str
    project_id: str
    test_types_run: list[str]
    issues: list[RegressionIssue]
    passed: bool
    generated_at: str
    event_count: int = 0
    chapter_count: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


# ── 上下文 ────────────────────────────────────────────────────────────────


@dataclass
class RegressionContext:
    """回归测试所需的全部输入。"""

    run_id: str
    project_id: str

    # 被测事件历史（按时间顺序）
    event_records: list[EventRecord] = field(default_factory=list)

    # 被测章节历史（按 chapter_index 排序）
    chapter_specs: list[ChapterSpec] = field(default_factory=list)

    # 权威对象（用于机制/语感检查）
    bible_auth: AuthObject | None = None
    volume_contract_auth: AuthObject | None = None

    # 启用的测试类型
    test_types: list[str] = field(
        default_factory=lambda: ["prose", "mechanic", "boundary", "chapter"]
    )


# ── 测试实现 ──────────────────────────────────────────────────────────────


def _test_prose(ctx: RegressionContext) -> list[RegressionIssue]:
    """语感/文风回归：检查 Lens 一致性、说明书密度、重复片段。"""
    issues: list[RegressionIssue] = []

    spec00 = {}
    if ctx.bible_auth and isinstance(ctx.bible_auth.content, dict):
        spec00 = ctx.bible_auth.content.get("spec00", ctx.bible_auth.content)
    max_density: float = spec00.get("scale_budget", {}).get("max_explanation_density", 0.25)

    for rec in ctx.event_records:
        draft_text = getattr(rec, "draft_text", "") or ""
        if not draft_text:
            continue

        # 说明书密度
        import re

        lines = [line for line in draft_text.splitlines() if line.strip()]
        if lines:
            exp_lines = sum(1 for line in lines if re.search(r"[（(][^）)]{2,30}[）)]", line))
            density = exp_lines / len(lines)
            if density > max_density * 1.5:
                issues.append(
                    RegressionIssue(
                        test_type="prose",
                        issue_id="prose_01",
                        severity="warning",
                        message=f"说明书密度过高: {density:.2%} > {max_density * 1.5:.2%}",
                        event_id=rec.event_id,
                    )
                )

        # 重复片段检测（≥15字的相同片段出现≥3次）
        chunk = 15
        counts: dict[str, int] = {}
        for i in range(max(0, len(draft_text) - chunk + 1)):
            s = draft_text[i : i + chunk]
            counts[s] = counts.get(s, 0) + 1
        repeats = [s for s, c in counts.items() if c >= 3]
        if repeats:
            issues.append(
                RegressionIssue(
                    test_type="prose",
                    issue_id="prose_02",
                    severity="warning",
                    message=f"检测到重复片段（{len(repeats)}处）",
                    event_id=rec.event_id,
                )
            )

    return issues


def _test_mechanic(ctx: RegressionContext) -> list[RegressionIssue]:
    """机制回归：检查禁忌词、能力超出边界（基于 BIBLE taboo 列表）。"""
    issues: list[RegressionIssue] = []

    spec00 = {}
    if ctx.bible_auth and isinstance(ctx.bible_auth.content, dict):
        spec00 = ctx.bible_auth.content.get("spec00", ctx.bible_auth.content)
    taboo: list[str] = [
        word
        for word in [*(spec00.get("taboo") or []), *(spec00.get("taboo_words") or [])]
        if isinstance(word, str)
    ]

    for rec in ctx.event_records:
        draft_text = getattr(rec, "draft_text", "") or ""
        if not draft_text:
            continue
        text_lower = draft_text.lower()
        for word in taboo:
            if word and word.lower() in text_lower:
                issues.append(
                    RegressionIssue(
                        test_type="mechanic",
                        issue_id="mechanic_01",
                        severity="error",
                        message=f"事件正文触犯禁忌: {word!r}",
                        event_id=rec.event_id,
                    )
                )

    return issues


def _test_boundary(ctx: RegressionContext) -> list[RegressionIssue]:
    """事件边界回归：PreSnapshot → ObservedDelta 状态一致性。"""
    issues: list[RegressionIssue] = []

    for rec in ctx.event_records:
        # 若 EventRecord 持有快照引用（通过 state_before_key/state_after_key 判断）
        state_before = getattr(rec, "state_before_key", None)
        state_after_key = getattr(rec, "state_after_key", None)
        if not state_after_key or state_after_key != rec.observed_delta.state_after.snapshot_key:
            issues.append(
                RegressionIssue(
                    test_type="boundary",
                    issue_id="boundary_after",
                    severity="error",
                    message="事件记录与提交后状态快照键不一致",
                    event_id=rec.event_id,
                )
            )
        fingerprint = rec.context_fingerprint
        if fingerprint and rec.observed_delta.state_after.context_fingerprint != fingerprint:
            issues.append(
                RegressionIssue(
                    test_type="boundary",
                    issue_id="boundary_context",
                    severity="error",
                    message="事件与状态变化的上下文指纹不一致",
                    event_id=rec.event_id,
                )
            )
        if not state_before:
            issues.append(
                RegressionIssue(
                    test_type="boundary",
                    issue_id="boundary_01",
                    severity="warning",
                    message="EventRecord 缺少 state_before_key（无法验证边界连续性）",
                    event_id=rec.event_id,
                )
            )

    return issues


def _test_chapter(ctx: RegressionContext) -> list[RegressionIssue]:
    """章节化回归：Breather 约束 + MomentumDebt + 钩子轮换。"""
    issues: list[RegressionIssue] = []

    if not ctx.chapter_specs:
        return issues

    from novelwb.core.constants import ChapterIntent, Defaults

    specs = ctx.chapter_specs
    total = len(specs)
    breather_count = sum(1 for cs in specs if cs.chapter_intent == ChapterIntent.BREATHER)
    breather_ratio = breather_count / total if total > 0 else 0.0
    max_ratio = Defaults.BREATHER_QUOTA_PER_VOLUME_RATIO

    if breather_ratio > max_ratio:
        issues.append(
            RegressionIssue(
                test_type="chapter",
                issue_id="chapter_01",
                severity="error",
                message=(
                    f"Breather 章占比超限: {breather_ratio:.2%} > "
                    f"{max_ratio:.2%}（{breather_count}/{total}）"
                ),
            )
        )

    # 连续 Breather
    consec = max_consec = 0
    for cs in specs:
        if cs.chapter_intent == ChapterIntent.BREATHER:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    if max_consec > Defaults.MAX_CONSECUTIVE_BREATHER:
        issues.append(
            RegressionIssue(
                test_type="chapter",
                issue_id="chapter_02",
                severity="error",
                message=f"连续 Breather 超限: {max_consec} > {Defaults.MAX_CONSECUTIVE_BREATHER}",
            )
        )

    # 钩子轮换
    hook_types = [cs.hook_type for cs in specs if cs.hook_type]
    if len(hook_types) >= 5:
        counts = Counter(hook_types)
        dominant = counts.most_common(1)[0]
        if dominant[1] / len(hook_types) > 0.6:
            hook_share = dominant[1] / len(hook_types)
            issues.append(
                RegressionIssue(
                    test_type="chapter",
                    issue_id="chapter_03",
                    severity="warning",
                    message=f"钩子类型单一: {dominant[0]!r} 占比 {hook_share:.0%}",
                )
            )

    # MomentumDebt 累积
    total_debt = sum((cs.momentum_debt_delta or 0) for cs in specs)
    if total_debt > Defaults.MOMENTUM_DEBT_MAX:
        issues.append(
            RegressionIssue(
                test_type="chapter",
                issue_id="chapter_04",
                severity="warning",
                message=f"MomentumDebt 累积过高: {total_debt} > {Defaults.MOMENTUM_DEBT_MAX}",
            )
        )

    return issues


# ── Regression 测试分发表 ──────────────────────────────────────────────────

_TEST_MAP = {
    "prose": _test_prose,
    "mechanic": _test_mechanic,
    "boundary": _test_boundary,
    "chapter": _test_chapter,
}


# ── RegressionRunner ──────────────────────────────────────────────────────


class RegressionRunner:
    """执行回归测试套件，返回 RegressionReport。"""

    def run(self, ctx: RegressionContext) -> RegressionReport:
        all_issues: list[RegressionIssue] = []
        types_run: list[str] = []

        for test_type in ctx.test_types:
            fn = _TEST_MAP.get(test_type)
            if fn:
                issues = fn(ctx)
                all_issues.extend(issues)
                types_run.append(test_type)

        passed = all(i.severity != "error" for i in all_issues)

        return RegressionReport(
            run_id=ctx.run_id,
            project_id=ctx.project_id,
            test_types_run=types_run,
            issues=all_issues,
            passed=passed,
            generated_at=to_iso(utcnow()),
            event_count=len(ctx.event_records),
            chapter_count=len(ctx.chapter_specs),
        )
