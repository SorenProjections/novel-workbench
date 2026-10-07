"""HardLint 引擎 — 规则组 A-G 结构性校验。

规则分组（与 StepSpec hardlint.enabled_rule_groups 对应）：
  A — 结构与字段（必填/JSON可解析/类型范围/run_id存在）
  B — 预算与上限（字数/实体/术语/章长/事件长）
  C — ID与引用（块ID唯一性/引用存在/章节引用完整）
  D — 禁忌/撞名/合规（禁忌词/NAMECHECK 命中）
  E — 重复与注水（重复片段/说明书密度/钩子重复）
  F — 章节意图合法性（Breather占比/连续/MomentumDebt）
  G — 事件连续性（PreSnapshot/ObservedDelta 键存在）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from novelwb.core.constants import BlockIntent, ChapterIntent, Defaults, FixLevel
from novelwb.core.schemas.domain_models import (
    AuthObject,
    ChapterSpec,
    ContextPackage,
    DiffReport,
    EventDraft,
    ObservedDelta,
    StateSnapshot,
    VolumeContract,
)

# ── 上下文 ────────────────────────────────────────────────────────────────


@dataclass
class LintContext:
    """HardLint 所需的全部输入。"""

    run_id: str
    event_id: str

    # 被检对象
    draft: EventDraft | None = None
    chapter_specs: list[ChapterSpec] | None = None  # 当前事件的章节方案

    # 参考数据
    bible_auth: AuthObject | None = None  # BIBLE 权威对象（含 spec00 预算/禁忌）
    volume_contract: VolumeContract | None = None

    # 快照 & 增量
    pre_snapshot: StateSnapshot | None = None
    observed_delta: ObservedDelta | None = None
    context_package: ContextPackage | None = None

    # 历史章节列表（用于 F 组统计 Breather 占比）
    history_chapter_specs: list[ChapterSpec] = field(default_factory=list)

    # 启用的规则组（默认全启）
    enabled_rule_groups: list[str] = field(default_factory=lambda: list("ABCDEFG"))


# ── Violation 描述 ─────────────────────────────────────────────────────────


@dataclass
class Violation:
    rule_group: str  # "A" .. "G"
    rule_id: str  # e.g. "A01"
    message: str
    is_hard: bool = True  # True = 阻断提交；False = 软缺陷（警告）


# ── 工具函数 ──────────────────────────────────────────────────────────────


def _get_spec00(ctx: LintContext) -> dict[str, Any]:
    """从 BIBLE 权威对象中取出 spec00 节点，若不存在返回空 dict。"""
    if ctx.bible_auth and isinstance(ctx.bible_auth.content, dict):
        content = ctx.bible_auth.content
        spec00 = content.get("spec00", content)
        return spec00 if isinstance(spec00, dict) else {}
    return {}


def _chinese_char_count(text: str) -> int:
    """粗略计算字符数（汉字 + ASCII 字母按权重折算）。"""
    return len(text)


# ── 规则组实现 ─────────────────────────────────────────────────────────────


def _rule_A(ctx: LintContext) -> list[Violation]:
    """A — 结构与字段。"""
    v: list[Violation] = []
    draft = ctx.draft
    if draft is None:
        v.append(Violation("A", "A00", "draft 为 None，无法执行任何校验"))
        return v

    # A01 必填字段
    if not draft.event_id:
        v.append(Violation("A", "A01", "EventDraft.event_id 为空"))
    if not draft.run_id:
        v.append(Violation("A", "A01", "EventDraft.run_id 为空"))
    if not draft.draft_text or not draft.draft_text.strip():
        v.append(Violation("A", "A02", "EventDraft.draft_text 为空"))

    # A03 run_id 一致性
    if draft.run_id and draft.run_id != ctx.run_id:
        v.append(Violation("A", "A03", f"run_id 不匹配: draft={draft.run_id} ctx={ctx.run_id}"))

    # A04 blocks 中每个 block_intent 合法
    valid_block_intents = {bi.value for bi in BlockIntent}
    for i, blk in enumerate(draft.blocks or []):
        if blk.block_intent not in valid_block_intents:
            v.append(
                Violation("A", "A04", f"blocks[{i}].block_intent 非法值: {blk.block_intent!r}")
            )

    return v


def _rule_B(ctx: LintContext) -> list[Violation]:
    """B — 预算与上限。"""
    v: list[Violation] = []
    draft = ctx.draft
    if draft is None:
        return v

    spec00 = _get_spec00(ctx)
    budget = spec00.get("scale_budget", {})
    avg_event_chars: int = budget.get("avg_event_chars", Defaults.DEFAULT_EVENT_MAX_TOKENS * 2)
    hard_max = int(avg_event_chars * 1.5)
    hard_min = int(avg_event_chars * 0.3)

    text_len = _chinese_char_count(draft.draft_text or "")

    # B01 字数上限
    if text_len > hard_max:
        budget_message = (
            f"draft_text 超出预算上限: {text_len} > {hard_max}（avg_event_chars={avg_event_chars}）"
        )
        v.append(
            Violation(
                "B",
                "B01",
                budget_message,
            )
        )

    # B02 字数下限
    if text_len < hard_min and draft.draft_text:
        v.append(
            Violation(
                "B", "B02", f"draft_text 严重低于预算下限: {text_len} < {hard_min}", is_hard=False
            )
        )

    # B03 实体/术语密度（粗略：段落中含括号说明比率）
    max_density: float = budget.get("max_explanation_density", 0.25)
    if draft.draft_text:
        lines = [line for line in draft.draft_text.splitlines() if line.strip()]
        if lines:
            explanation_lines = sum(
                1 for line in lines if re.search(r"[（(（][^）)]{2,30}[）)]", line)
            )
            density = explanation_lines / len(lines)
            if density > max_density:
                v.append(
                    Violation(
                        "B",
                        "B03",
                        f"说明书密度过高: {density:.2%} > {max_density:.2%}",
                        is_hard=False,
                    )
                )

    # B04 blocks 数量过多（max_entities_per_event）
    max_ents: int = budget.get("max_entities_per_event", 10)
    if draft.blocks and len(draft.blocks) > max_ents * 2:
        v.append(
            Violation(
                "B",
                "B04",
                (
                    f"blocks 数量过多: {len(draft.blocks)} > "
                    f"{max_ents * 2}（max_entities_per_event={max_ents}）"
                ),
                is_hard=False,
            )
        )

    return v


def _rule_C(ctx: LintContext) -> list[Violation]:
    """C — ID与引用唯一性。"""
    v: list[Violation] = []
    draft = ctx.draft
    if draft is None:
        return v

    # C01 block_id 唯一
    seen_ids: set[str] = set()
    for blk in draft.blocks or []:
        if blk.block_id in seen_ids:
            v.append(Violation("C", "C01", f"重复 block_id: {blk.block_id!r}"))
        seen_ids.add(blk.block_id)

    # C02 chapter_specs 中 chapter_id 唯一
    if ctx.chapter_specs:
        seen_chap: set[str] = set()
        for cs in ctx.chapter_specs:
            if cs.chapter_id in seen_chap:
                v.append(Violation("C", "C02", f"重复 chapter_id: {cs.chapter_id!r}"))
            seen_chap.add(cs.chapter_id)

    return v


def _rule_D(ctx: LintContext) -> list[Violation]:
    """D — 禁忌词/撞名/合规。"""
    v: list[Violation] = []
    draft = ctx.draft
    if draft is None or not draft.draft_text:
        return v

    spec00 = _get_spec00(ctx)
    taboo_list: list[str] = [
        word
        for word in [*(spec00.get("taboo") or []), *(spec00.get("taboo_words") or [])]
        if isinstance(word, str)
    ]

    text_lower = draft.draft_text.lower()
    for taboo in taboo_list:
        if taboo and taboo.lower() in text_lower:
            v.append(Violation("D", "D01", f"触犯禁忌词: {taboo!r}"))

    # D02 naming_risk 检查（若 spec00 有设置）
    naming_risk = spec00.get("naming_risk")
    if naming_risk and isinstance(naming_risk, list):
        for risk_word in naming_risk:
            if risk_word and risk_word.lower() in text_lower:
                v.append(Violation("D", "D02", f"命名风险词命中: {risk_word!r}", is_hard=False))

    return v


def _rule_E(ctx: LintContext) -> list[Violation]:
    """E — 重复与注水。"""
    v: list[Violation] = []
    draft = ctx.draft
    if draft is None or not draft.draft_text:
        return v

    text = draft.draft_text

    # E01 口头禅（10字以上片段重复3次+）
    phrases_seen: dict[str, int] = {}
    chunk_size = 10
    for i in range(max(0, len(text) - chunk_size + 1)):
        chunk = text[i : i + chunk_size]
        phrases_seen[chunk] = phrases_seen.get(chunk, 0) + 1
    heavy_repeats = [p for p, c in phrases_seen.items() if c >= 3]
    if heavy_repeats:
        v.append(
            Violation(
                "E",
                "E01",
                f"检测到重复片段（{len(heavy_repeats)}处）: {heavy_repeats[:2]}",
                is_hard=False,
            )
        )

    # E02 钩子重复（chapter_specs 中 hook_type 分布）
    if ctx.chapter_specs and len(ctx.chapter_specs) >= 3:
        hook_types = [cs.hook_type for cs in ctx.chapter_specs if cs.hook_type]
        if hook_types:
            from collections import Counter

            counts = Counter(hook_types)
            dominant = counts.most_common(1)[0]
            if dominant[1] / len(hook_types) > 0.7:
                hook_share = dominant[1] / len(hook_types)
                v.append(
                    Violation(
                        "E",
                        "E02",
                        f"章节钩子类型单一: {dominant[0]!r} 占比 {hook_share:.0%}",
                        is_hard=False,
                    )
                )

    return v


def _rule_F(ctx: LintContext) -> list[Violation]:
    """F — 章节意图合法性（Breather 约束）。"""
    v: list[Violation] = []
    chapter_specs = ctx.chapter_specs
    if not chapter_specs:
        return v

    vc = ctx.volume_contract
    max_ratio: float = (
        float(vc.breather_quota) if vc is not None else Defaults.BREATHER_QUOTA_PER_VOLUME_RATIO
    )
    max_consec: int = (
        vc.max_consecutive_breather if vc is not None else Defaults.MAX_CONSECUTIVE_BREATHER
    )
    momentum_max: int = vc.momentum_debt_max if vc is not None else Defaults.MOMENTUM_DEBT_MAX

    # 合并历史 + 当前以计算卷内统计
    all_specs = list(ctx.history_chapter_specs) + list(chapter_specs)
    total = len(all_specs)
    breather_count = sum(1 for cs in all_specs if cs.chapter_intent == ChapterIntent.BREATHER)
    breather_ratio = breather_count / total if total > 0 else 0.0

    # F01 Breather 占比超限
    if breather_ratio > max_ratio:
        v.append(
            Violation(
                "F",
                "F01",
                (
                    f"Breather 占比超限: {breather_ratio:.2%} > {max_ratio:.2%}"
                    f"（{breather_count}/{total}）"
                ),
            )
        )

    # F02 连续 Breather 超限
    consec = 0
    max_seen = 0
    for cs in all_specs:
        if cs.chapter_intent == ChapterIntent.BREATHER:
            consec += 1
            max_seen = max(max_seen, consec)
        else:
            consec = 0
    if max_seen > max_consec:
        v.append(Violation("F", "F02", f"连续 Breather 超限: {max_seen} > {max_consec}"))

    # F03 MomentumDebt 超限（从 chapter_specs 的 delta 累积估算）
    total_debt = sum((cs.momentum_debt_delta or 0) for cs in all_specs)
    if total_debt > momentum_max:
        v.append(
            Violation(
                "F", "F03", f"MomentumDebt 超限: {total_debt} > {momentum_max}", is_hard=False
            )
        )

    return v


def _rule_G(ctx: LintContext) -> list[Violation]:
    """G — 事件连续性（快照/增量键存在）。"""
    v: list[Violation] = []

    # G01 PreSnapshot 存在
    if ctx.pre_snapshot is None:
        v.append(Violation("G", "G01", f"缺少 PreSnapshot（event_id={ctx.event_id}）"))

    # G02 ObservedDelta 存在
    if ctx.observed_delta is None:
        v.append(Violation("G", "G02", f"缺少 ObservedDelta（event_id={ctx.event_id}）"))

    # G03 ObservedDelta.state_after 非空
    if ctx.observed_delta and not ctx.observed_delta.state_after:
        v.append(Violation("G", "G03", "ObservedDelta.state_after 为空"))

    # G04 snapshot_key 与 event_id 对应
    if ctx.pre_snapshot and ctx.event_id:
        expected_key = f"pre_{ctx.event_id}"
        actual_key = ctx.pre_snapshot.snapshot_key or ""
        if actual_key and actual_key != expected_key:
            v.append(
                Violation(
                    "G",
                    "G04",
                    f"snapshot_key 不匹配: {actual_key!r} != {expected_key!r}",
                    is_hard=False,
                )
            )

    # G05 上下文指纹必须从编译阶段贯穿到事件前快照。
    if ctx.context_package and ctx.pre_snapshot:
        actual_fingerprint = ctx.pre_snapshot.context_fingerprint
        if actual_fingerprint != ctx.context_package.fingerprint:
            v.append(
                Violation(
                    "G",
                    "G05",
                    "PreSnapshot 的 context_fingerprint 与本次 ContextPackage 不一致",
                )
            )

    # G06 状态卡变更必须提供正文证据，避免模型无依据重写全量卡片。
    if ctx.observed_delta:
        for group, patches in ctx.observed_delta.card_updates.items():
            for patch in patches:
                if not patch.evidence:
                    v.append(
                        Violation(
                            "G",
                            "G06",
                            f"状态卡补丁缺少正文证据: {group}/{patch.card_id}",
                        )
                    )

                card = patch.card
                if card is None or not patch.revealed_to or card.revelation_gate is None:
                    continue
                gate = card.revelation_gate
                disallowed = [
                    name
                    for name in patch.revealed_to
                    if gate.allowed_knowers and name not in gate.allowed_knowers
                ]
                if disallowed:
                    v.append(
                        Violation(
                            "G",
                            "G07",
                            f"知识边界越权: {patch.card_id} 不允许向 {', '.join(disallowed)} 揭秘",
                        )
                    )
                missing_hints = set(gate.required_hint_ids) - set(gate.satisfied_hint_ids)
                if missing_hints:
                    missing_hint_names = ", ".join(sorted(missing_hints))
                    v.append(
                        Violation(
                            "G",
                            "G08",
                            f"揭秘前置伏笔不足: {patch.card_id} 缺少 {missing_hint_names}",
                        )
                    )

                available_refs: set[str] = set(
                    ctx.pre_snapshot.open_threads if ctx.pre_snapshot else []
                )
                if ctx.context_package:
                    available_refs.update(
                        source.source_id
                        for source in [
                            *ctx.context_package.protected_sources,
                            *ctx.context_package.selected_sources,
                        ]
                    )
                    available_refs.update(
                        selection.card.card_id for selection in ctx.context_package.selected_cards
                    )
                missing_facts = set(gate.required_fact_ids) - available_refs
                if missing_facts:
                    missing_fact_names = ", ".join(sorted(missing_facts))
                    v.append(
                        Violation(
                            "G",
                            "G09",
                            f"揭秘前置事实不足: {patch.card_id} 缺少 {missing_fact_names}",
                        )
                    )

    return v


# ── 规则分发表 ─────────────────────────────────────────────────────────────

_RULE_MAP = {
    "A": _rule_A,
    "B": _rule_B,
    "C": _rule_C,
    "D": _rule_D,
    "E": _rule_E,
    "F": _rule_F,
    "G": _rule_G,
}


# ── HardLintEngine ─────────────────────────────────────────────────────────


class HardLintEngine:
    """运行 HardLint 规则组，返回 DiffReport。"""

    def run(self, ctx: LintContext) -> DiffReport:
        """执行所有启用的规则组，返回 DiffReport。"""
        all_violations: list[Violation] = []

        for group in ctx.enabled_rule_groups:
            fn = _RULE_MAP.get(group.upper())
            if fn:
                all_violations.extend(fn(ctx))

        hard_violations = [vl for vl in all_violations if vl.is_hard]
        soft_violations = [vl for vl in all_violations if not vl.is_hard]
        passed = len(hard_violations) == 0

        # 推断建议修复级别
        fix_level = self._infer_fix_level(hard_violations)

        violated_forbidden = [f"[{vl.rule_id}] {vl.message}" for vl in hard_violations]
        soft_defects = [f"[{vl.rule_id}] {vl.message}" for vl in soft_violations]

        g_violations = [
            f"[{vl.rule_id}] {vl.message}" for vl in hard_violations if vl.rule_group == "G"
        ]
        d_violations = [
            f"[{vl.rule_id}] {vl.message}" for vl in hard_violations if vl.rule_id == "D01"
        ]
        f_soft = [vl for vl in all_violations if vl.rule_id == "F03"]

        return DiffReport(
            event_id=ctx.event_id,
            run_id=ctx.run_id,
            passed=passed,
            violated_forbidden=violated_forbidden,
            soft_defects=soft_defects,
            fix_level_suggested=fix_level if not passed else None,
            missing_due_debts=[],
            unbridged_state_jump=g_violations,
            name_collision=d_violations,
            rule_drift=[],
            momentum_overflow=len(f_soft) > 0,
            patch_instructions=self._build_instructions(hard_violations),
        )

    @staticmethod
    def _infer_fix_level(hard: list[Violation]) -> FixLevel:
        """根据违规严重程度推断修复级别。"""
        if not hard:
            return FixLevel.L0
        groups = {vl.rule_group for vl in hard}
        # G/F 问题影响事件逻辑 → L2
        if groups & {"G", "F"}:
            return FixLevel.L2
        # A/C 结构性问题 → L1
        if groups & {"A", "C"}:
            return FixLevel.L1
        # B/D/E 内容问题 → L0
        return FixLevel.L0

    @staticmethod
    def _build_instructions(hard: list[Violation]) -> list[str]:
        instructions = []
        for vl in hard:
            instructions.append(f"修复 [{vl.rule_id}]: {vl.message}")
        return instructions
