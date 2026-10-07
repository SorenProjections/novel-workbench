"""图E — 事件提交流程（Event Commit）。

步骤：
  E1. presnapshot  — 构建事件前状态快照
  E2. extract      — 从事件草稿提取 ObservedDelta
  E3. reconcile    — Reconcile 对账 → DiffReport
  E4. fix          — 分级修复（若 reconcile 未通过）
  E5. commit       — 原子提交到 events 存储
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from novelwb.core.constants import FixLevel
from novelwb.core.schemas.domain_models import (
    AuthObject,
    ContextPackage,
    DiffReport,
    EventDraft,
    EventRecord,
    ObservedDelta,
    StateSnapshot,
)
from novelwb.core.schemas.patch_models import CommitReceipt
from novelwb.engine.context_compiler import ContextCompiler
from novelwb.engine.hard_lint import LintContext
from novelwb.engine.policies import RepairPolicy
from novelwb.engine.step_runner import GraphDeps, StepResult, StepRunner
from novelwb.storage import AuthStore, ContextStore, EventsStore, SnapshotsStore, StagingStore
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.logger import get_logger
from novelwb.utils.timeutil import to_iso, utcnow
from novelwb.utils.transactions import atomic_method

_logger = get_logger(__name__)


class StructuredOutputError(RuntimeError):
    """A commit-critical LLM step violated its structured-output contract."""


def _strip_extra(data: dict[str, Any], model_class: type[BaseModel]) -> dict[str, Any]:
    """Remove unknown keys to avoid extra='forbid' validation errors."""
    known = set(model_class.model_fields.keys())
    return {k: v for k, v in data.items() if k in known}


@dataclass
class GraphEInput:
    """图E 的输入。"""

    run_id: str
    event_id: str
    draft: EventDraft  # 已生成的事件草稿
    bible_auth: AuthObject | None = None  # 用于 HardLint D/G 检查
    context_package: ContextPackage | None = None
    commit: bool = True
    auto_repair: bool = True


@dataclass
class GraphEOutput:
    """图E 的输出。"""

    event_record: EventRecord
    commit_receipt: CommitReceipt
    pre_snapshot: StateSnapshot
    observed_delta: ObservedDelta
    diff_report: DiffReport
    fix_attempts: int = 0
    aborted: bool = False
    abort_reason: str = ""
    failure_stage: str = ""


class GraphE:
    """事件提交图执行器。"""

    def __init__(
        self,
        deps: GraphDeps,
        layout: WorkspaceLayout,
        repair_policy: RepairPolicy | None = None,
    ) -> None:
        self._runner = StepRunner(deps)
        self._layout = layout
        self._auth_store = AuthStore(layout)
        self._events_store = EventsStore(layout)
        self._snapshots_store = SnapshotsStore(layout)
        self._staging_store = StagingStore(layout)
        self._context_store = ContextStore(layout)
        self._repair = repair_policy or RepairPolicy()

    def run(self, inp: GraphEInput) -> GraphEOutput:
        run_id = inp.run_id
        event_id = inp.event_id
        draft = inp.draft
        context_package = inp.context_package or self._context_store.load_package(event_id)

        # ── E1: PreSnapshot ────────────────────────────────────
        try:
            pre_snap = self._run_presnapshot(run_id, event_id, inp.bible_auth, context_package)
        except StructuredOutputError as exc:
            return self._abort_structured(
                run_id,
                event_id,
                draft,
                str(exc),
                context_package,
                failure_stage="presnapshot",
            )

        # ── E2: Extract ObservedDelta ───────────────────────────
        try:
            observed_delta = self._run_extract(run_id, event_id, draft, pre_snap, context_package)
        except StructuredOutputError as exc:
            return self._abort_structured(
                run_id,
                event_id,
                draft,
                str(exc),
                context_package,
                pre_snapshot=pre_snap,
                failure_stage="state_delta",
            )

        # ── E3+E4: Reconcile + Fix ──────────────────────────────
        diff_report, draft, fix_attempts, aborted, abort_reason = self._reconcile_loop(
            run_id,
            event_id,
            draft,
            pre_snap,
            observed_delta,
            inp.bible_auth,
            context_package,
            auto_repair=inp.auto_repair,
        )
        if not aborted and fix_attempts > 0:
            try:
                observed_delta = self._run_extract(
                    run_id, event_id, draft, pre_snap, context_package
                )
            except StructuredOutputError as exc:
                return self._abort_structured(
                    run_id,
                    event_id,
                    draft,
                    str(exc),
                    context_package,
                    pre_snapshot=pre_snap,
                    failure_stage="state_delta",
                )
            diff_report, draft, extra_fix_attempts, aborted, abort_reason = self._reconcile_loop(
                run_id,
                event_id,
                draft,
                pre_snap,
                observed_delta,
                inp.bible_auth,
                context_package,
                auto_repair=inp.auto_repair,
            )
            fix_attempts += extra_fix_attempts
            if not aborted and extra_fix_attempts > 0:
                try:
                    observed_delta = self._run_extract(
                        run_id, event_id, draft, pre_snap, context_package
                    )
                except StructuredOutputError as exc:
                    return self._abort_structured(
                        run_id,
                        event_id,
                        draft,
                        str(exc),
                        context_package,
                        pre_snapshot=pre_snap,
                        failure_stage="state_delta",
                    )

        if aborted:
            _logger.error(f"graphE_aborted event={event_id} reason={abort_reason}")
            # 仍然返回，让 Orchestrator 决定是否整体回滚
            return GraphEOutput(
                event_record=self._make_event_record(
                    run_id,
                    event_id,
                    draft,
                    pre_snap,
                    observed_delta,
                    diff_report,
                    context_package,
                ),
                commit_receipt=CommitReceipt.model_construct(
                    receipt_id="",
                    run_id=run_id,
                    staging_id="",
                    commit_type="event",
                    committed_at="",
                    committed_objects=[],
                ),
                pre_snapshot=pre_snap,
                observed_delta=observed_delta,
                diff_report=diff_report,
                fix_attempts=fix_attempts,
                aborted=True,
                abort_reason=abort_reason,
                failure_stage="reconcile",
            )

        if not inp.commit:
            return GraphEOutput(
                event_record=self._make_event_record(
                    run_id,
                    event_id,
                    draft,
                    pre_snap,
                    observed_delta,
                    diff_report,
                    context_package,
                ),
                commit_receipt=CommitReceipt.model_construct(
                    receipt_id="",
                    run_id=run_id,
                    staging_id="",
                    commit_type="event",
                    committed_at="",
                    committed_objects=[],
                ),
                pre_snapshot=pre_snap,
                observed_delta=observed_delta,
                diff_report=diff_report,
                fix_attempts=fix_attempts,
            )

        # ── E5: Commit ──────────────────────────────────────────
        event_record, receipt = self._run_commit(
            run_id,
            event_id,
            draft,
            pre_snap,
            observed_delta,
            diff_report,
            context_package,
        )

        self._snapshots_store.save_pre(pre_snap, event_id)
        self._snapshots_store.save_post(observed_delta.state_after, event_id)
        self._snapshots_store.save_latest(observed_delta.state_after)
        _logger.info(f"graphE_committed event={event_id} fix_attempts={fix_attempts}")

        return GraphEOutput(
            event_record=event_record,
            commit_receipt=receipt,
            pre_snapshot=pre_snap,
            observed_delta=observed_delta,
            diff_report=diff_report,
            fix_attempts=fix_attempts,
        )

    @atomic_method
    def commit_reviewed(
        self,
        *,
        run_id: str,
        event_id: str,
        draft: EventDraft,
        pre_snapshot: StateSnapshot,
        observed_delta: ObservedDelta,
        diff_report: DiffReport,
        context_package: ContextPackage | None = None,
    ) -> GraphEOutput:
        """Commit a human-reviewed delta without rerunning extraction."""
        event_record, receipt = self._run_commit(
            run_id,
            event_id,
            draft,
            pre_snapshot,
            observed_delta,
            diff_report,
            context_package,
        )
        self._snapshots_store.save_pre(pre_snapshot, event_id)
        self._snapshots_store.save_post(observed_delta.state_after, event_id)
        self._snapshots_store.save_latest(observed_delta.state_after)
        return GraphEOutput(
            event_record=event_record,
            commit_receipt=receipt,
            pre_snapshot=pre_snapshot,
            observed_delta=observed_delta,
            diff_report=diff_report,
        )

    # ── 内部步骤 ──────────────────────────────────────────────────────────

    def _run_presnapshot(
        self,
        run_id: str,
        event_id: str,
        bible_auth: AuthObject | None,
        context_package: ContextPackage | None,
    ) -> StateSnapshot:
        compiled_context = (
            ContextCompiler.render_input_context(context_package) if context_package else None
        )
        latest = self._snapshots_store.load_latest()
        if latest is not None:
            data = latest.model_dump(mode="json")
            data["snapshot_key"] = f"pre_{event_id}"
            data["event_id"] = event_id
            if compiled_context and context_package is not None:
                char_context = compiled_context["char_content"]
                data["reading_focus"] = char_context.get("reading_focus", [])
                data["status_cards"] = char_context.get("status_cards", {})
                data["context_fingerprint"] = context_package.fingerprint
            return StateSnapshot.model_validate(data)

        char_auth = self._auth_store.load_artifact("char_state") or self._auth_store.load_artifact(
            "cast"
        )
        ledger_auth = self._auth_store.load_latest("LEDGER")
        bible_content = (
            compiled_context["bible_content"]
            if compiled_context
            else bible_auth.content
            if bible_auth
            else {}
        )
        char_content = (
            compiled_context["char_content"]
            if compiled_context
            else char_auth.content
            if char_auth
            else {}
        )
        ledger_content = (
            compiled_context["ledger_content"]
            if compiled_context
            else ledger_auth.content
            if ledger_auth
            else {}
        )
        result = self._runner.run(
            step_key="graphE.event.presnapshot.build",
            input_pack={
                "event_id": event_id,
                "run_id": run_id,
                "bible_content": bible_content,
                "char_content": char_content,
                "ledger_content": ledger_content,
                "latest_state": {},
                "recent_events": self._events_store.list_index()[-5:],
                "context_meta": compiled_context["context_meta"] if compiled_context else {},
            },
            run_id=run_id,
        )
        if not result.ok or not isinstance(result.parsed, dict):
            raise StructuredOutputError("presnapshot did not return valid structured output")
        try:
            data = _strip_extra(result.parsed, StateSnapshot)
            data.setdefault("snapshot_key", f"pre_{event_id}")
            if context_package:
                data["context_fingerprint"] = context_package.fingerprint
            return StateSnapshot.model_validate(data)
        except Exception as exc:
            raise StructuredOutputError(f"presnapshot validation failed: {exc}") from exc

    def _run_extract(
        self,
        run_id: str,
        event_id: str,
        draft: EventDraft,
        snap: StateSnapshot,
        context_package: ContextPackage | None,
    ) -> ObservedDelta:
        validation_errors: list[str] = []

        def valid_observed_delta(value: Any) -> bool:
            try:
                self._parse_observed_delta(
                    value,
                    event_id=event_id,
                    snap=snap,
                    context_package=context_package,
                )
                return True
            except Exception as exc:
                validation_errors.append(str(exc))
                raise

        result = self._runner.run(
            step_key="graphE.event.extract",
            input_pack={
                "event_id": event_id,
                "run_id": run_id,
                "draft_text": draft.draft_text,
                "pre_snapshot": snap.model_dump(mode="json"),
                "context_meta": (
                    ContextCompiler.render_input_context(context_package)["context_meta"]
                    if context_package
                    else {}
                ),
            },
            run_id=run_id,
            parsed_validator=valid_observed_delta,
        )
        if result.ok:
            try:
                return self._parse_observed_delta(
                    result.parsed,
                    event_id=event_id,
                    snap=snap,
                    context_package=context_package,
                )
            except Exception as exc:  # pragma: no cover - validator and parse share one path
                validation_errors.append(str(exc))

        attempts = max(1, len(result.call_records))
        detail = validation_errors[-1] if validation_errors else "模型没有返回可解析的 JSON 对象"
        _logger.warning(f"graphE_extract_parse_fail event={event_id} attempts={attempts}: {detail}")
        raise StructuredOutputError(f"状态差异提取在 {attempts} 次尝试后仍未通过结构校验：{detail}")

    @staticmethod
    def _merge_mapping(before: Any, after: Any) -> dict[str, Any]:
        merged = dict(before) if isinstance(before, dict) else {}
        if isinstance(after, dict):
            merged.update(after)
        return merged

    @staticmethod
    def _append_unique(before: Any, after: Any) -> list[Any]:
        merged = list(before) if isinstance(before, list) else []
        if not isinstance(after, list):
            return merged
        for item in after:
            if item not in merged:
                merged.append(item)
        return merged

    @classmethod
    def _merge_status_cards(cls, before: Any, after: Any) -> dict[str, list[Any]]:
        merged: dict[str, list[Any]] = {
            str(group): list(cards)
            for group, cards in dict(before or {}).items()
            if isinstance(cards, list)
        }
        if not isinstance(after, dict):
            return merged
        for group, cards in after.items():
            if not isinstance(cards, list):
                continue
            existing = list(merged.get(str(group), []))
            positions = {
                str(card.get("card_id")): index
                for index, card in enumerate(existing)
                if isinstance(card, dict) and card.get("card_id")
            }
            for card in cards:
                if not isinstance(card, dict):
                    continue
                card_id = str(card.get("card_id") or "")
                if card_id and card_id in positions:
                    existing[positions[card_id]] = card
                else:
                    if card_id:
                        positions[card_id] = len(existing)
                    existing.append(card)
            merged[str(group)] = existing
        return merged

    @classmethod
    def _parse_observed_delta(
        cls,
        value: Any,
        *,
        event_id: str,
        snap: StateSnapshot,
        context_package: ContextPackage | None,
    ) -> ObservedDelta:
        if not isinstance(value, dict):
            raise ValueError("根节点必须是 JSON 对象")
        parsed = dict(value)
        raw_after = parsed.get("state_after")
        if not isinstance(raw_after, dict):
            raise ValueError("state_after 必须是 JSON 对象")

        pre_state = snap.model_dump(mode="json")
        state_after_raw = dict(raw_after)
        state_after_raw.setdefault("snapshot_key", f"post_{event_id}")
        state_after_raw.setdefault("event_id", event_id)

        for field_name in (
            "resources",
            "hp",
            "relationship_state",
            "entity_states",
            "narrative_line_states",
            "entity_agendas",
            "asset_states",
        ):
            state_after_raw[field_name] = cls._merge_mapping(
                pre_state.get(field_name),
                state_after_raw.get(field_name),
            )
        for field_name in ("ability_boundary", "open_threads", "timeline_events"):
            state_after_raw[field_name] = cls._append_unique(
                pre_state.get(field_name),
                state_after_raw.get(field_name),
            )
        if "reading_focus" not in state_after_raw:
            state_after_raw["reading_focus"] = pre_state.get("reading_focus", [])
        state_after_raw["status_cards"] = cls._merge_status_cards(
            pre_state.get("status_cards"),
            state_after_raw.get("status_cards"),
        )

        summary = str(
            parsed.get("result_state_summary") or state_after_raw.get("result_state_summary") or ""
        ).strip()
        if not summary:
            raise ValueError("result_state_summary 不能为空")
        state_after_raw["result_state_summary"] = summary
        if context_package:
            state_after_raw["context_fingerprint"] = context_package.fingerprint

        state_after = StateSnapshot.model_validate(_strip_extra(state_after_raw, StateSnapshot))
        delta_data = _strip_extra(parsed, ObservedDelta)
        delta_data["state_after"] = state_after
        delta_data["result_state_summary"] = summary
        return ObservedDelta.model_validate(delta_data)

    def _reconcile_loop(
        self,
        run_id: str,
        event_id: str,
        draft: EventDraft,
        pre_snap: StateSnapshot,
        delta: ObservedDelta,
        bible_auth: AuthObject | None,
        context_package: ContextPackage | None,
        *,
        auto_repair: bool = True,
    ) -> tuple[DiffReport, EventDraft, int, bool, str]:
        attempt = 0
        # HardLint 直接作用于 draft，不经过 StepRunner 的 Judge 机制
        # （Reconcile 的 LLM 输出是 DiffReport，不是 EventDraft）
        lint_engine = self._runner._deps.lint_engine
        while True:
            lint_ctx = LintContext(
                run_id=run_id,
                event_id=event_id,
                draft=draft,
                bible_auth=bible_auth,
                pre_snapshot=pre_snap,
                observed_delta=delta,
                context_package=context_package,
                enabled_rule_groups=["A", "B", "C", "D", "E", "G"],
            )
            # 先对 draft 直接跑 HardLint
            diff_report = lint_engine.run(lint_ctx)
            # 若 HardLint 已通过，再调用 LLM Reconcile 作深度检查
            if diff_report.passed:
                reconcile_result = self._runner.run(
                    step_key="graphE.event.reconcile",
                    input_pack={
                        "event_id": event_id,
                        "run_id": run_id,
                        "draft_text": draft.draft_text,
                        "pre_snapshot": pre_snap.model_dump(mode="json"),
                        "observed_delta": delta.model_dump(mode="json"),
                        "context_meta": (
                            ContextCompiler.render_input_context(context_package)["context_meta"]
                            if context_package
                            else {}
                        ),
                    },
                    lint_ctx=None,  # 不再对 reconcile 输出跑 HardLint
                    run_id=run_id,
                )
                diff_report = self._build_diff_report(reconcile_result, event_id, run_id)

            if not diff_report.passed and not auto_repair:
                problems = (
                    diff_report.violated_forbidden
                    or diff_report.patch_instructions
                    or diff_report.soft_defects
                )
                detail = "；".join(str(item) for item in problems[:3])
                reason = "事件事实对账未通过，人工审核正文不会被后台自动改写"
                if detail:
                    reason = f"{reason}；具体问题：{detail}"
                return diff_report, draft, attempt, True, reason

            decision = self._repair.decide(diff_report, attempt)
            if not decision.should_retry:
                if decision.should_abort:
                    problems = (
                        diff_report.violated_forbidden
                        or diff_report.patch_instructions
                        or diff_report.soft_defects
                    )
                    detail = "；".join(str(item) for item in problems[:3])
                    reason = decision.reason
                    if detail:
                        reason = f"{reason}；最后一次对账问题：{detail}"
                    return diff_report, draft, attempt, True, reason
                return diff_report, draft, attempt, False, ""

            # Fix
            draft = self._run_fix(run_id, event_id, draft, diff_report, decision.fix_level)
            attempt += 1

    def _run_fix(
        self, run_id: str, event_id: str, draft: EventDraft, report: DiffReport, level: FixLevel
    ) -> EventDraft:
        fix_result = self._runner.run(
            step_key="graphE.event.fix",
            input_pack={
                "event_id": event_id,
                "run_id": run_id,
                "draft_text": draft.draft_text,
                "violations": report.violated_forbidden,
                "fix_level": level.value,
                "patch_instructions": report.patch_instructions,
            },
            run_id=run_id,
        )
        if fix_result.parsed and isinstance(fix_result.parsed, dict):
            new_text = fix_result.parsed.get("draft_text", fix_result.text)
        else:
            new_text = fix_result.text or draft.draft_text
        return EventDraft.model_construct(
            event_id=draft.event_id,
            run_id=draft.run_id,
            draft_text=new_text,
            blocks=draft.blocks,
            word_count=len(new_text),
        )

    def _run_commit(
        self,
        run_id: str,
        event_id: str,
        draft: EventDraft,
        pre_snap: StateSnapshot,
        delta: ObservedDelta,
        report: DiffReport,
        context_package: ContextPackage | None,
    ) -> tuple[EventRecord, CommitReceipt]:
        self._runner.run(
            step_key="graphE.event.commit",
            input_pack={
                "event_id": event_id,
                "run_id": run_id,
                "draft_text": draft.draft_text,
                "diff_report": report.model_dump(mode="json"),
            },
            run_id=run_id,
        )
        event_record = self._make_event_record(
            run_id,
            event_id,
            draft,
            pre_snap,
            delta,
            report,
            context_package,
        )
        self._events_store.save(event_record)
        now_str = to_iso(utcnow())
        receipt = CommitReceipt.model_construct(
            receipt_id=f"rcpt_{event_id}",
            run_id=run_id,
            staging_id=f"stg_{event_id}",
            commit_type="event",
            committed_at=now_str,
            committed_objects=["event", "pre_snapshot", "post_snapshot"],
            committed_event_id=event_id,
            committed_state_after_key=delta.state_after.snapshot_key,
        )
        return event_record, receipt

    @staticmethod
    def _make_event_record(
        run_id: str,
        event_id: str,
        draft: EventDraft,
        pre_snap: StateSnapshot,
        delta: ObservedDelta,
        report: DiffReport,
        context_package: ContextPackage | None = None,
    ) -> EventRecord:
        now = utcnow()
        return EventRecord.model_construct(
            event_id=event_id,
            project_id="",
            draft_text=draft.draft_text,
            blocks=draft.blocks,
            state_before_key=pre_snap.snapshot_key,
            state_after_key=delta.state_after.snapshot_key,
            observed_delta=delta,
            diff_report=report,
            committed_at=now,
            committed_by_run_id=run_id,
            ledger_version_after=0,
            context_package_id=context_package.context_id if context_package else None,
            context_fingerprint=context_package.fingerprint if context_package else None,
        )

    @staticmethod
    def _build_diff_report(result: StepResult, event_id: str, run_id: str) -> DiffReport:
        if result.ok and result.parsed and isinstance(result.parsed, dict):
            try:
                data = _strip_extra(result.parsed, DiffReport)
                data["event_id"] = event_id
                data["run_id"] = run_id
                # Normalize fix_level_suggested: accept string or null
                fls = data.get("fix_level_suggested")
                if fls is not None:
                    try:
                        from novelwb.core.constants import FixLevel

                        data["fix_level_suggested"] = FixLevel(fls)
                    except (ValueError, KeyError):
                        data["fix_level_suggested"] = None
                return DiffReport.model_validate(data)
            except Exception as exc:
                _logger.warning(f"graphE_reconcile_parse_fail event={event_id}: {exc}")
        return DiffReport(
            event_id=event_id,
            run_id=run_id,
            passed=False,
            violated_forbidden=[*result.violations, "reconcile_structured_output_invalid"],
            soft_defects=[],
            fix_level_suggested=None,
            missing_due_debts=[],
            unbridged_state_jump=[],
            name_collision=[],
            rule_drift=[],
            momentum_overflow=False,
            patch_instructions=[],
        )

    @classmethod
    def _abort_structured(
        cls,
        run_id: str,
        event_id: str,
        draft: EventDraft,
        reason: str,
        context_package: ContextPackage | None,
        pre_snapshot: StateSnapshot | None = None,
        failure_stage: str = "state_delta",
    ) -> GraphEOutput:
        """Build a non-persisted result for a failed commit-critical step."""
        _logger.error(f"graphE_structured_abort event={event_id} reason={reason}")
        pre_snapshot = pre_snapshot or StateSnapshot(snapshot_key=f"pre_{event_id}")
        delta = ObservedDelta(
            state_after=StateSnapshot(snapshot_key=f"post_{event_id}_uncommitted"),
            result_state_summary=f"uncommitted: {reason}",
        )
        report = DiffReport(
            event_id=event_id,
            run_id=run_id,
            passed=False,
            violated_forbidden=["structured_output_invalid"],
            patch_instructions=[reason],
        )
        return GraphEOutput(
            event_record=cls._make_event_record(
                run_id,
                event_id,
                draft,
                pre_snapshot,
                delta,
                report,
                context_package,
            ),
            commit_receipt=CommitReceipt.model_construct(
                receipt_id="",
                run_id=run_id,
                staging_id="",
                commit_type="none",
                committed_at="",
                committed_objects=[],
            ),
            pre_snapshot=pre_snapshot,
            observed_delta=delta,
            diff_report=report,
            aborted=True,
            abort_reason=reason,
            failure_stage=failure_stage,
        )
