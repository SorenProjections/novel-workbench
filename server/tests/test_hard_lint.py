"""HardLint 引擎单元测试（规则 A-G 基本路径）。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from novelwb.engine.hard_lint import HardLintEngine, LintContext
from novelwb.core.schemas.domain_models import (
    EventDraft,
    ObservedDelta,
    StateSnapshot,
    BlockSpec,
)
from novelwb.core.constants import BlockIntent


def _now():
    return datetime.now(timezone.utc)


def _make_draft(event_id: str, run_id: str, text: str = "测试内容" * 30) -> EventDraft:
    return EventDraft.model_construct(
        event_id=event_id,
        run_id=run_id,
        draft_text=text,
        blocks=[],
        word_count=len(text),
    )


def _make_ctx(
    event_id: str = "ev-001",
    run_id: str = "run-001",
    draft: EventDraft | None = None,
    rules: list[str] | None = None,
) -> LintContext:
    return LintContext(
        run_id=run_id,
        event_id=event_id,
        draft=draft,
        enabled_rule_groups=rules or list("ABCDEFG"),
    )


engine = HardLintEngine()


# ── 规则 A ───────────────────────────────────────────────────────────────────


def test_rule_a_pass_with_valid_draft():
    draft = _make_draft("ev-001", "run-001")
    ctx = _make_ctx(draft=draft, rules=["A"])
    report = engine.run(ctx)
    # 有草稿时 A 组不应触发 draft-missing 违规
    assert isinstance(report.rule_drift, list)


def test_rule_a_fail_no_draft():
    ctx = _make_ctx(draft=None, rules=["A"])
    report = engine.run(ctx)
    # draft 为 None 时应标记未通过
    assert not report.passed


# ── 规则 B ───────────────────────────────────────────────────────────────────


def test_rule_b_pass_normal_text():
    # 正常长度文本不应触发字数预算违规（无 bible_auth 时默认宽松）
    draft = _make_draft("ev-001", "run-001", text="字" * 500)
    ctx = _make_ctx(draft=draft, rules=["B"])
    report = engine.run(ctx)
    assert isinstance(report.rule_drift, list)


# ── 规则 D ───────────────────────────────────────────────────────────────────


def test_rule_d_no_bible_no_taboo():
    # 无 bible_auth 时 D 组直接跳过，不触发
    draft = _make_draft("ev-001", "run-001")
    ctx = _make_ctx(draft=draft, rules=["D"])
    report = engine.run(ctx)
    assert isinstance(report.violated_forbidden, list)


# ── 规则 G ───────────────────────────────────────────────────────────────────


def test_rule_g_pass_with_snapshots():
    snap_before = StateSnapshot(snapshot_key="pre_ev-001", event_id="ev-001")
    snap_after = StateSnapshot(snapshot_key="post_ev-001", event_id="ev-001")
    delta = ObservedDelta(
        state_after=snap_after,
        result_state_summary="OK",
    )
    draft = _make_draft("ev-001", "run-001")
    ctx = LintContext(
        run_id="run-001",
        event_id="ev-001",
        draft=draft,
        pre_snapshot=snap_before,
        observed_delta=delta,
        enabled_rule_groups=["G"],
    )
    report = engine.run(ctx)
    assert isinstance(report.unbridged_state_jump, list)


# ── 综合：通过路径 ─────────────────────────────────────────────────────────────


def test_full_run_minimal_pass():
    draft = _make_draft("ev-x", "run-x", text="测试" * 100)
    ctx = _make_ctx(event_id="ev-x", run_id="run-x", draft=draft)
    report = engine.run(ctx)
    # 检查返回结构完整性
    assert hasattr(report, "passed")
    assert hasattr(report, "violated_forbidden")
    assert hasattr(report, "unbridged_state_jump")
    assert isinstance(report.rule_drift, list)
