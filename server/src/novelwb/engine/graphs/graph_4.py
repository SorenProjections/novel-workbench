"""图4 — 事件执行（Event Execution）。

步骤：
  4.1 event_budget    — 事件体量与展开深度（不是章节字数）
  4.2 event_route     — 按当前状态选择本次真正需要展开的叙事维度
  4.3 world_pulse     — 推演人物、势力、物件与环境的自主行动
  4.4 event_expand    — 多线展开并生成候选碰撞
  4.5 event_plan      — 将展开结果编织成连续场景
  4.6 prewrite_check  — 正文前一致性与覆盖检查
  4.7 namecheck/jit   — 命名检查与临时素材实例化
  4.8 prose_write     — 一次生成完整事件正文，章节后置切分
"""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from novelwb.core.constants import BlockIntent, Defaults
from novelwb.core.schemas.domain_models import (
    AuthObject,
    BlockSpec,
    ContextPackage,
    EventDraft,
    StateSnapshot,
)
from novelwb.engine.context_compiler import ContextCompiler
from novelwb.engine.prose_quality import ProseQualityEvaluator
from novelwb.engine.step_runner import GraphDeps, StepRunner
from novelwb.storage import ContextStore
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.ids import new_event_id
from novelwb.utils.logger import get_logger

_logger = get_logger(__name__)


@dataclass
class Graph4Input:
    """图4 的输入。"""

    run_id: str
    project_id: str
    event_slot: dict[str, Any]  # 来自卷契约的事件槽位规格
    bible_auth: AuthObject | None = None  # BIBLE 权威对象
    char_bible: AuthObject | None = None
    ledger: AuthObject | None = None
    volume_contract: AuthObject | None = None
    registry: AuthObject | None = None
    motif: AuthObject | None = None
    latest_snapshot: StateSnapshot | None = None
    authority_bundle: list[AuthObject] = field(default_factory=list)
    plan_only: bool = False
    execution_override: dict[str, Any] = field(default_factory=dict)


@dataclass
class Graph4Output:
    """图4 的输出。"""

    draft: EventDraft  # 生成的事件草稿，可直接传给图E
    context_package: ContextPackage
    budget_report: dict[str, Any] = field(default_factory=dict)
    quality_report: dict[str, Any] = field(default_factory=dict)
    execution_report: dict[str, Any] = field(default_factory=dict)
    quality_attempts: int = 0
    namecheck_passed: bool = True
    aborted: bool = False
    abort_reason: str = ""


@dataclass(frozen=True)
class EventPlanStep:
    """A logical event-planning file with its own review/commit boundary."""

    step_id: str
    label: str
    asset_id: str
    max_tokens: int
    required_fields: tuple[str, ...]


EVENT_PLAN_STEPS: tuple[EventPlanStep, ...] = (
    EventPlanStep(
        "constraints_route",
        "事件约束与展开路线",
        "event.plan.constraints_route",
        3500,
        ("budget_report", "event_route"),
    ),
    EventPlanStep(
        "world_pulse",
        "世界脉冲",
        "event.plan.world_pulse",
        4500,
        ("world_pulse",),
    ),
    EventPlanStep(
        "event_expansion",
        "多线事件展开",
        "event.plan.event_expansion",
        14000,
        ("event_expansion",),
    ),
    EventPlanStep(
        "scene_plan",
        "连续场景方案",
        "event.plan.scene_plan",
        21000,
        ("event_plan", "scene_plan"),
    ),
    EventPlanStep(
        "prewrite_assets",
        "正文前检查与临时资产",
        "event.plan.prewrite_assets",
        6300,
        ("prewrite_check", "namecheck", "jit_cards"),
    ),
)

PREWRITE_CHECK_DIMENSIONS: tuple[str, ...] = (
    "causality",
    "timeline",
    "map",
    "knowledge_boundary",
    "entity_agency",
    "line_lifecycle",
    "asset_coverage",
    "non_checklist_rhythm",
)


def event_plan_steps() -> list[EventPlanStep]:
    return list(EVENT_PLAN_STEPS)


def _event_plan_record(volume_content: dict[str, Any], event_id: str) -> dict[str, Any]:
    plans = volume_content.get("event_plans", {}) if isinstance(volume_content, dict) else {}
    record = plans.get(event_id, {}) if isinstance(plans, dict) else {}
    return record if isinstance(record, dict) else {}


def event_plan_step_complete(
    volume_content: dict[str, Any],
    event_id: str,
    step: EventPlanStep,
) -> bool:
    record = _event_plan_record(volume_content, event_id)
    receipts = record.get("approved_steps", [])
    files = record.get("files", {})
    return (
        isinstance(receipts, list)
        and step.step_id in set(map(str, receipts))
        and isinstance(files, dict)
        and isinstance(files.get(step.step_id), dict)
    )


def next_event_plan_step(volume_content: dict[str, Any], event_id: str) -> EventPlanStep | None:
    return next(
        (
            step
            for step in EVENT_PLAN_STEPS
            if not event_plan_step_complete(volume_content, event_id, step)
        ),
        None,
    )


def merge_event_plan_step(
    volume_content: dict[str, Any],
    *,
    event_id: str,
    event_index: int,
    step: EventPlanStep,
    generated: dict[str, Any],
) -> dict[str, Any]:
    """Persist one approved planning file without touching other event files."""

    content = deepcopy(volume_content)
    plans = content.setdefault("event_plans", {})
    if not isinstance(plans, dict):
        plans = {}
        content["event_plans"] = plans
    record = plans.setdefault(event_id, {})
    if not isinstance(record, dict):
        record = {}
        plans[event_id] = record
    record["event_id"] = event_id
    record["event_index"] = max(1, int(event_index))
    record["workflow_version"] = 2
    files = record.setdefault("files", {})
    if not isinstance(files, dict):
        files = {}
        record["files"] = files
    files[step.step_id] = deepcopy(generated)
    receipts = record.setdefault("approved_steps", [])
    if not isinstance(receipts, list):
        receipts = []
        record["approved_steps"] = receipts
    if step.step_id not in receipts:
        receipts.append(step.step_id)
    if step.step_id == "scene_plan":
        record.pop("revision_feedback", None)
    return content


def execution_report_from_event_plan(
    volume_content: dict[str, Any], event_id: str
) -> dict[str, Any]:
    """Assemble the exact approved files into Graph4's immutable write input."""

    record = _event_plan_record(volume_content, event_id)
    files = record.get("files", {}) if isinstance(record, dict) else {}
    report: dict[str, Any] = {}
    if isinstance(files, dict):
        for step in EVENT_PLAN_STEPS:
            payload = files.get(step.step_id, {})
            if isinstance(payload, dict):
                report.update(deepcopy(payload))
    feedback = record.get("revision_feedback") if isinstance(record, dict) else None
    if isinstance(feedback, dict) and feedback:
        report["_revision_feedback"] = deepcopy(feedback)
    return report


def invalidate_event_plan_downstream(
    volume_content: dict[str, Any],
    *,
    event_id: str,
    step_id: str,
) -> dict[str, Any]:
    """Keep an edited approved file and reopen every dependent later file."""

    content = deepcopy(volume_content)
    record = _event_plan_record(content, event_id)
    if not record:
        return content
    order = [item.step_id for item in EVENT_PLAN_STEPS]
    if step_id not in order:
        return content
    cutoff = order.index(step_id)
    receipts = record.get("approved_steps", [])
    record["approved_steps"] = (
        [item for item in receipts if str(item) in order and order.index(str(item)) <= cutoff]
        if isinstance(receipts, list)
        else [step_id]
    )
    files = record.get("files", {})
    if isinstance(files, dict):
        for downstream_step in order[cutoff + 1 :]:
            files.pop(downstream_step, None)
    return content


def reopen_event_plan_from_step(
    volume_content: dict[str, Any],
    *,
    event_id: str,
    step_id: str,
    revision_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reopen one approved planning file and every dependent file after it."""

    content = deepcopy(volume_content)
    record = _event_plan_record(content, event_id)
    if not record:
        return content
    order = [item.step_id for item in EVENT_PLAN_STEPS]
    if step_id not in order:
        return content
    cutoff = order.index(step_id)
    receipts = record.get("approved_steps", [])
    record["approved_steps"] = (
        [item for item in receipts if str(item) in order and order.index(str(item)) < cutoff]
        if isinstance(receipts, list)
        else []
    )
    files = record.get("files", {})
    if isinstance(files, dict):
        for reopened_step in order[cutoff:]:
            files.pop(reopened_step, None)
    if isinstance(revision_feedback, dict) and revision_feedback:
        record["revision_feedback"] = deepcopy(revision_feedback)
    else:
        record.pop("revision_feedback", None)
    return content


def merge_legacy_event_plan(
    volume_content: dict[str, Any],
    *,
    event_id: str,
    event_index: int,
    execution_report: dict[str, Any],
) -> dict[str, Any]:
    """Migrate an already generated v1 all-at-once plan without another LLM call."""

    field_map = {
        "constraints_route": ("budget_report", "event_route"),
        "world_pulse": ("world_pulse",),
        "event_expansion": ("event_expansion",),
        "scene_plan": ("event_plan", "scene_plan"),
        "prewrite_assets": ("prewrite_check", "namecheck", "jit_cards"),
    }
    content = deepcopy(volume_content)
    for step in EVENT_PLAN_STEPS:
        generated = {
            field: deepcopy(execution_report.get(field))
            for field in field_map[step.step_id]
            if field in execution_report
        }
        if step.step_id == "prewrite_assets":
            generated.setdefault("namecheck", {"passed": True, "legacy": True})
            generated.setdefault("jit_cards", [])
        content = merge_event_plan_step(
            content,
            event_id=event_id,
            event_index=event_index,
            step=step,
            generated=generated,
        )
    return content


class Graph4:
    """事件执行图执行器。"""

    def __init__(self, deps: GraphDeps, layout: WorkspaceLayout) -> None:
        self._runner = StepRunner(deps)
        self._layout = layout
        self._context_store = ContextStore(layout)
        configured_budget = os.environ.get("NOVELWB_EVENT_CONTEXT_TOKENS", "").strip()
        token_budget = (
            int(configured_budget)
            if configured_budget
            else max(120000, Defaults.DEFAULT_CONTEXT_INPUT_TOKENS)
        )
        self._context_compiler = ContextCompiler(token_budget=token_budget)
        self._quality = ProseQualityEvaluator(Defaults.MIN_EVENT_PROSE_SCORE)

    @staticmethod
    def normalize_prewrite_check(raw: object) -> dict[str, Any]:
        """Normalize documented envelopes and legacy flat check maps."""

        check = dict(raw) if isinstance(raw, dict) else {}
        nested = check.get("checks")
        checks = (
            dict(nested)
            if isinstance(nested, dict)
            else {
                key: check[key]
                for key in PREWRITE_CHECK_DIMENSIONS
                if isinstance(check.get(key), bool)
            }
        )
        failed = [key for key in PREWRITE_CHECK_DIMENSIONS if checks.get(key) is False]
        explicit_passed = check.get("passed")
        has_dimensions = any(key in checks for key in PREWRITE_CHECK_DIMENSIONS)
        passed = (
            bool(explicit_passed)
            if isinstance(explicit_passed, bool)
            else has_dimensions and not failed
        )
        passed = bool(passed and not failed)
        check["passed"] = passed
        check["checks"] = checks

        if not passed and not isinstance(check.get("issues"), list):
            labels = "、".join(failed) if failed else "输出结构"
            check["issues"] = [f"未通过检查项：{labels}"]
        if not passed and not isinstance(check.get("repair_instructions"), list):
            repairs: list[str] = []
            if "asset_coverage" in failed:
                repairs.append(
                    "把已选择的关键资产、人物反应和环境约束分别落实到具体场景、节拍与结果证据中"
                )
            if "non_checklist_rhythm" in failed:
                repairs.append(
                    "删除各场景对完整事件目标的重复复述，让每场只承担独立冲突、转折和余波，并以因果衔接"
                )
            if not repairs:
                repairs.append("根据未通过维度重织连续场景方案，并保留已确认的有效设计")
            check["repair_instructions"] = repairs
        check.setdefault("protected_strengths", [])
        return check

    @staticmethod
    def _valid_scene_plan_response(parsed: object) -> bool:
        if not isinstance(parsed, dict):
            return False
        scenes = parsed.get("scenes", parsed.get("blocks"))
        if not isinstance(scenes, list) or not scenes:
            return False
        return all(
            isinstance(scene, dict)
            and bool(scene.get("scene_id") or scene.get("block_id"))
            and bool(str(scene.get("scene_summary") or "").strip())
            for scene in scenes
        )

    @staticmethod
    def _valid_prewrite_response(parsed: object) -> bool:
        if not isinstance(parsed, dict):
            return False
        nested = parsed.get("checks")
        if isinstance(nested, dict):
            return any(key in nested for key in PREWRITE_CHECK_DIMENSIONS)
        return any(key in parsed for key in PREWRITE_CHECK_DIMENSIONS)

    def generate_review_step(
        self,
        inp: Graph4Input,
        step: EventPlanStep,
        approved_execution: dict[str, Any],
    ) -> tuple[dict[str, Any], ContextPackage]:
        """Generate exactly one reviewable planning file.

        Approved files are treated as immutable inputs.  In particular, the
        prewrite check never silently reweaves an already approved scene plan.
        """

        run_id = inp.run_id
        event_slot = inp.event_slot
        event_id = event_slot.get("slot_id") or new_event_id()
        auth_objects = inp.authority_bundle or [
            obj
            for obj in (
                inp.bible_auth,
                inp.registry,
                inp.char_bible,
                inp.ledger,
                inp.volume_contract,
                inp.motif,
            )
            if obj is not None
        ]
        context_package = self._context_compiler.compile_event(
            event_id=event_id,
            event_slot=event_slot,
            auth_objects=auth_objects,
            card_index=self._context_store.load_card_index(),
            latest_snapshot=inp.latest_snapshot,
        )
        self._context_store.save_package(context_package)
        context = self._context_compiler.render_input_context(context_package)
        bible_content = context["bible_content"]
        reg_content = context["reg_content"]
        char_content = context["char_content"]
        ledger_content = context["ledger_content"]
        volume_content = context["volume_content"]
        context_meta = context["context_meta"]
        snapshot = inp.latest_snapshot.model_dump(mode="json") if inp.latest_snapshot else {}
        execution = deepcopy(approved_execution or {})

        if step.step_id == "constraints_route":
            budget_result = self._runner.run(
                step_key="graph4.event.budget",
                input_pack={
                    "event_slot": event_slot,
                    "bible_content": bible_content,
                    "volume_content": volume_content,
                    "is_key_event": event_slot.get("is_key_event", False),
                    "context_meta": context_meta,
                },
                run_id=run_id,
            )
            budget = budget_result.parsed if isinstance(budget_result.parsed, dict) else {}
            budget = self._normalize_budget(budget, event_slot)
            route_result = self._runner.run(
                step_key="graph4.event.route",
                input_pack={
                    "event_slot": event_slot,
                    "budget": budget,
                    "latest_snapshot": snapshot,
                    "volume_content": volume_content,
                    "context_meta": context_meta,
                },
                run_id=run_id,
            )
            route = route_result.parsed if isinstance(route_result.parsed, dict) else {}
            return {"budget_report": budget, "event_route": route}, context_package

        budget = dict(execution.get("budget_report") or {})
        route = dict(execution.get("event_route") or {})
        if step.step_id == "world_pulse":
            result = self._runner.run(
                step_key="graph4.event.world_pulse",
                input_pack={
                    "event_slot": event_slot,
                    "event_route": route,
                    "latest_snapshot": snapshot,
                    "char_content": char_content,
                    "ledger_content": ledger_content,
                    "volume_content": volume_content,
                    "context_meta": context_meta,
                },
                run_id=run_id,
            )
            pulse = result.parsed if isinstance(result.parsed, dict) else {}
            return {"world_pulse": pulse}, context_package

        world_pulse = dict(execution.get("world_pulse") or {})
        if step.step_id == "event_expansion":
            result = self._runner.run(
                step_key="graph4.event.expand",
                input_pack={
                    "event_slot": event_slot,
                    "event_route": route,
                    "world_pulse": world_pulse,
                    "budget": budget,
                    "bible_content": bible_content,
                    "char_content": char_content,
                    "ledger_content": ledger_content,
                    "volume_content": volume_content,
                    "reg_content": reg_content,
                    "context_meta": context_meta,
                },
                run_id=run_id,
            )
            expansion = result.parsed if isinstance(result.parsed, dict) else {}
            return {"event_expansion": expansion}, context_package

        expansion = dict(execution.get("event_expansion") or {})
        if step.step_id == "scene_plan":
            plan_input = {
                "event_slot": event_slot,
                "budget": budget,
                "event_route": route,
                "world_pulse": world_pulse,
                "event_expansion": expansion,
                "bible_content": bible_content,
                "char_content": char_content,
                "ledger_content": ledger_content,
                "volume_content": volume_content,
                "reg_content": reg_content,
                "context_meta": context_meta,
            }
            revision_feedback = execution.get("_revision_feedback")
            if isinstance(revision_feedback, dict) and revision_feedback:
                plan_input["prewrite_feedback"] = revision_feedback
            result = self._runner.run(
                step_key="graph4.event.plan",
                input_pack=plan_input,
                run_id=run_id,
                parsed_validator=self._valid_scene_plan_response,
            )
            if not result.ok or not self._valid_scene_plan_response(result.parsed):
                raise ValueError(
                    "连续场景方案未返回可用 scenes，已自动重试仍失败；"
                    "本次不会用通用模板冒充场景方案"
                )
            event_plan = dict(result.parsed) if isinstance(result.parsed, dict) else {}
            raw_scenes = (
                event_plan.get("scenes", event_plan.get("blocks", []))
                if event_plan
                else result.parsed
            )
            scenes = self._normalize_block_plan(raw_scenes, budget, event_slot)
            event_plan["scenes"] = scenes
            return {"event_plan": event_plan, "scene_plan": scenes}, context_package

        if step.step_id == "prewrite_assets":
            event_plan = dict(execution.get("event_plan") or {})
            scenes = list(execution.get("scene_plan") or event_plan.get("scenes") or [])
            check_result = self._runner.run(
                step_key="graph4.event.prewrite_check",
                input_pack={
                    "event_slot": event_slot,
                    "event_route": route,
                    "world_pulse": world_pulse,
                    "event_expansion": expansion,
                    "event_plan": event_plan,
                    "latest_snapshot": snapshot,
                    "context_meta": context_meta,
                },
                run_id=run_id,
                parsed_validator=self._valid_prewrite_response,
            )
            if not check_result.ok:
                raise ValueError("正文前检查未返回完整检查项，已自动重试仍失败")
            prewrite = self.normalize_prewrite_check(check_result.parsed)
            namecheck_result = self._runner.run(
                step_key="graph4.event.namecheck",
                input_pack={
                    "event_slot": event_slot,
                    "block_plan": scenes,
                    "scene_plan": scenes,
                    "bible_content": bible_content,
                    "char_content": char_content,
                    "reg_content": reg_content,
                    "context_meta": context_meta,
                },
                run_id=run_id,
            )
            namecheck = namecheck_result.parsed if isinstance(namecheck_result.parsed, dict) else {}
            jit_result = self._runner.run(
                step_key="graph4.event.jit_cards",
                input_pack={
                    "event_slot": event_slot,
                    "block_plan": scenes,
                    "scene_plan": scenes,
                    "bible_content": bible_content,
                    "char_content": char_content,
                    "reg_content": reg_content,
                    "context_meta": context_meta,
                },
                run_id=run_id,
            )
            jit_cards = (
                jit_result.parsed.get("cards", []) if isinstance(jit_result.parsed, dict) else []
            )
            return {
                "prewrite_check": prewrite,
                "namecheck": namecheck,
                "jit_cards": jit_cards,
            }, context_package

        raise ValueError(f"未知事件规划审核步骤：{step.step_id}")

    @staticmethod
    def validate_review_step(step: EventPlanStep, generated: object) -> list[str]:
        if not isinstance(generated, dict):
            return ["当前事件规划文件必须是JSON对象"]
        missing = [field for field in step.required_fields if field not in generated]
        if missing:
            return [f"缺少字段：{', '.join(missing)}"]
        if step.step_id == "scene_plan":
            if not isinstance(generated.get("event_plan"), dict):
                return ["连续场景方案缺少 event_plan 对象"]
            if not isinstance(generated.get("scene_plan"), list) or not generated["scene_plan"]:
                return ["连续场景方案必须包含至少一个场景"]
        if step.step_id == "prewrite_assets":
            check = Graph4.normalize_prewrite_check(generated.get("prewrite_check"))
            if not isinstance(check, dict):
                return ["正文前检查必须是JSON对象"]
            if not bool(check.get("passed")):
                issues = check.get("issues") or check.get("errors") or []
                detail = "；".join(map(str, issues)) if isinstance(issues, list) else str(issues)
                return [f"正文前检查未通过{f'：{detail}' if detail else ''}"]
            if not isinstance(generated.get("namecheck"), dict):
                return ["命名检查必须是JSON对象"]
            if not isinstance(generated.get("jit_cards"), list):
                return ["临时资产卡必须是数组"]
        return []

    def run(self, inp: Graph4Input) -> Graph4Output:
        run_id = inp.run_id
        event_slot = inp.event_slot
        event_id = event_slot.get("slot_id") or new_event_id()

        auth_objects = inp.authority_bundle or [
            obj
            for obj in (
                inp.bible_auth,
                inp.registry,
                inp.char_bible,
                inp.ledger,
                inp.volume_contract,
                inp.motif,
            )
            if obj is not None
        ]
        context_package = self._context_compiler.compile_event(
            event_id=event_id,
            event_slot=event_slot,
            auth_objects=auth_objects,
            card_index=self._context_store.load_card_index(),
            latest_snapshot=inp.latest_snapshot,
        )
        self._context_store.save_package(context_package)
        context = self._context_compiler.render_input_context(context_package)
        bible_content = context["bible_content"]
        reg_content = context["reg_content"]
        char_content = context["char_content"]
        ledger_content = context["ledger_content"]
        volume_content = context["volume_content"]
        context_meta = context["context_meta"]
        _logger.info(
            f"graph4_context_compiled event={event_id} "
            f"fingerprint={context_package.fingerprint[:12]} "
            f"tokens={context_package.estimated_tokens}/{context_package.token_budget} "
            f"cards={len(context_package.selected_cards)}"
        )

        # Approved planning files are an immutable write contract.  This fast
        # path must stay before every planning call so prose retries never
        # regenerate or silently replace a human-approved file.
        if inp.execution_override:
            return self._run_approved_execution(
                inp=inp,
                event_id=event_id,
                context_package=context_package,
                context=context,
            )

        # ── 4.1: event_budget ──────────────────────────────────
        _logger.info(f"graph4_step event_budget run={run_id} event={event_id}")
        budget_result = self._runner.run(
            step_key="graph4.event.budget",
            input_pack={
                "event_slot": event_slot,
                "bible_content": bible_content,
                "volume_content": volume_content,
                "is_key_event": event_slot.get("is_key_event", False),
                "context_meta": context_meta,
            },
            run_id=run_id,
        )
        budget_report: dict[str, Any] = (
            budget_result.parsed if isinstance(budget_result.parsed, dict) else {}
        )
        budget_report = self._normalize_budget(budget_report, event_slot)

        # ── 4.2-4.4: 动态路由、世界脉冲、多线展开 ─────────────
        route_result = self._runner.run(
            step_key="graph4.event.route",
            input_pack={
                "event_slot": event_slot,
                "budget": budget_report,
                "latest_snapshot": inp.latest_snapshot.model_dump(mode="json")
                if inp.latest_snapshot
                else {},
                "volume_content": volume_content,
                "context_meta": context_meta,
            },
            run_id=run_id,
        )
        event_route = (
            route_result.parsed
            if isinstance(route_result.parsed, dict)
            else {
                "expansion_routes": ["character", "plot"],
                "narrative_weight": budget_report.get("narrative_weight", "standard"),
            }
        )

        pulse_result = self._runner.run(
            step_key="graph4.event.world_pulse",
            input_pack={
                "event_slot": event_slot,
                "event_route": event_route,
                "latest_snapshot": inp.latest_snapshot.model_dump(mode="json")
                if inp.latest_snapshot
                else {},
                "char_content": char_content,
                "ledger_content": ledger_content,
                "volume_content": volume_content,
                "context_meta": context_meta,
            },
            run_id=run_id,
        )
        world_pulse = pulse_result.parsed if isinstance(pulse_result.parsed, dict) else {}

        expand_result = self._runner.run(
            step_key="graph4.event.expand",
            input_pack={
                "event_slot": event_slot,
                "event_route": event_route,
                "world_pulse": world_pulse,
                "budget": budget_report,
                "bible_content": bible_content,
                "char_content": char_content,
                "ledger_content": ledger_content,
                "volume_content": volume_content,
                "reg_content": reg_content,
                "context_meta": context_meta,
            },
            run_id=run_id,
        )
        event_expansion = expand_result.parsed if isinstance(expand_result.parsed, dict) else {}

        # ── 4.5: 将展开结果编织为完整事件场景 ─────────────────
        _logger.info(f"graph4_step event_plan run={run_id} event={event_id}")
        plan_input = {
            "event_slot": event_slot,
            "budget": budget_report,
            "event_route": event_route,
            "world_pulse": world_pulse,
            "event_expansion": event_expansion,
            "bible_content": bible_content,
            "char_content": char_content,
            "ledger_content": ledger_content,
            "volume_content": volume_content,
            "reg_content": reg_content,
            "context_meta": context_meta,
        }
        plan_result = self._runner.run(
            step_key="graph4.event.plan",
            input_pack=plan_input,
            run_id=run_id,
        )
        block_plan: list[Any] = []
        event_plan: dict[str, Any] = {}
        if isinstance(plan_result.parsed, dict):
            block_plan = plan_result.parsed.get("scenes", plan_result.parsed.get("blocks", []))
            # 保留完整规划（含 allowed_changes / forbidden_changes / debt_handling）
            event_plan = plan_result.parsed
        elif isinstance(plan_result.parsed, list):
            block_plan = plan_result.parsed

        block_plan = self._normalize_block_plan(block_plan, budget_report, event_slot)
        budget_report["scene_count"] = len(block_plan)
        if not event_plan:
            event_plan = {"scenes": block_plan}
        else:
            event_plan["scenes"] = block_plan

        # ── 4.6: 正文前一致性检查；失败时携带问题重织一次 ─────
        check_result = self._runner.run(
            step_key="graph4.event.prewrite_check",
            input_pack={
                "event_slot": event_slot,
                "event_route": event_route,
                "world_pulse": world_pulse,
                "event_expansion": event_expansion,
                "event_plan": event_plan,
                "latest_snapshot": inp.latest_snapshot.model_dump(mode="json")
                if inp.latest_snapshot
                else {},
                "context_meta": context_meta,
            },
            run_id=run_id,
        )
        prewrite_check = self.normalize_prewrite_check(check_result.parsed)
        if not bool(prewrite_check.get("passed")):
            plan_input["prewrite_feedback"] = prewrite_check
            plan_result = self._runner.run(
                step_key="graph4.event.plan",
                input_pack=plan_input,
                run_id=run_id,
            )
            if isinstance(plan_result.parsed, dict):
                event_plan = plan_result.parsed
                block_plan = self._normalize_block_plan(
                    event_plan.get("scenes", event_plan.get("blocks", [])),
                    budget_report,
                    event_slot,
                )
                event_plan["scenes"] = block_plan

        # ── 4.3: namecheck ─────────────────────────────────────
        _logger.info(f"graph4_step namecheck run={run_id} event={event_id}")
        namecheck_result = self._runner.run(
            step_key="graph4.event.namecheck",
            input_pack={
                "event_slot": event_slot,
                "block_plan": block_plan,
                "scene_plan": block_plan,
                "bible_content": bible_content,
                "char_content": char_content,
                "reg_content": reg_content,
                "context_meta": context_meta,
            },
            run_id=run_id,
        )
        namecheck_passed = True
        if isinstance(namecheck_result.parsed, dict):
            namecheck_passed = bool(namecheck_result.parsed.get("passed", True))
        if not namecheck_passed:
            collisions = (
                namecheck_result.parsed.get("collisions", [])
                if isinstance(namecheck_result.parsed, dict)
                else []
            )
            _logger.warning(f"graph4_namecheck_failed event={event_id} collisions={collisions}")
            # 软失败：继续执行，但在 output 中标注

        # ── 4.4: jit_cards ─────────────────────────────────────
        _logger.info(f"graph4_step jit_cards run={run_id} event={event_id}")
        jit_result = self._runner.run(
            step_key="graph4.event.jit_cards",
            input_pack={
                "event_slot": event_slot,
                "block_plan": block_plan,
                "scene_plan": block_plan,
                "bible_content": bible_content,
                "char_content": char_content,
                "reg_content": reg_content,
                "context_meta": context_meta,
            },
            run_id=run_id,
        )
        jit_cards: list[Any] = []
        if isinstance(jit_result.parsed, dict):
            jit_cards = jit_result.parsed.get("cards", [])

        if inp.execution_override:
            override = inp.execution_override
            budget_report = dict(override.get("budget_report") or budget_report)
            event_route = dict(override.get("event_route") or event_route)
            world_pulse = dict(override.get("world_pulse") or world_pulse)
            event_expansion = dict(override.get("event_expansion") or event_expansion)
            prewrite_check = dict(override.get("prewrite_check") or prewrite_check)
            event_plan = dict(override.get("event_plan") or event_plan)
            block_plan = list(override.get("scene_plan") or event_plan.get("scenes") or block_plan)
            event_plan["scenes"] = block_plan
            jit_cards = list(override.get("jit_cards") or jit_cards)

        execution_report = self._build_execution_report(
            budget_report=budget_report,
            event_route=event_route,
            world_pulse=world_pulse,
            event_expansion=event_expansion,
            prewrite_check=prewrite_check,
            event_plan=event_plan,
            scene_plan=block_plan,
            jit_cards=jit_cards,
        )
        if inp.plan_only:
            return Graph4Output(
                draft=EventDraft.model_construct(
                    event_id=event_id,
                    run_id=run_id,
                    draft_text="",
                    blocks=[],
                    word_count=0,
                ),
                context_package=context_package,
                budget_report=budget_report,
                execution_report=execution_report,
                namecheck_passed=namecheck_passed,
            )

        # ── 4.5: blocks_write ──────────────────────────────────
        write_input = {
            "event_id": event_id,
            "event_slot": event_slot,
            "event_plan": event_plan,  # 完整规划（含允许/禁止变化、债务清单）
            "scene_plan": block_plan,
            "budget": budget_report,
            "event_route": event_route,
            "world_pulse": world_pulse,
            "event_expansion": event_expansion,
            "prewrite_check": prewrite_check,
            "jit_cards": jit_cards,
            "bible_content": bible_content,
            "char_content": char_content,
            "ledger_content": ledger_content,  # 债务台账
            "volume_content": volume_content,  # 本卷契约（含镜头气候）
            "reg_content": reg_content,
            "context_meta": context_meta,
        }
        best_candidate = None
        previous_valid_score: float | None = None
        attempt_records: list[dict[str, Any]] = []
        retry_feedback: list[str] = []
        attempts_used = 0
        last_invalid_reason = ""

        for attempt in range(1, Defaults.MAX_PROSE_QUALITY_ATTEMPTS + 1):
            attempts_used = attempt
            _logger.info(
                f"graph4_step blocks_write run={run_id} event={event_id} attempt={attempt}"
            )
            write_input["retry_feedback"] = retry_feedback[-4:]
            write_result = self._runner.run(
                step_key="graph4.event.blocks.write",
                input_pack=write_input,
                run_id=run_id,
            )
            write_parsed = self._normalize_blocks_write_output(write_result.parsed)
            valid, invalid_reason = self._validate_blocks_write_output(
                event_id=event_id,
                block_plan=block_plan,
                write_parsed=write_parsed,
                budget_report=budget_report,
            )
            if not write_result.ok or not valid:
                last_invalid_reason = (
                    "正文写作请求失败或重试耗尽"
                    if not write_result.ok
                    else invalid_reason or "正文写作未返回可用正文"
                )
                attempt_records.append(
                    {
                        "attempt": attempt,
                        "valid": False,
                        "reason": last_invalid_reason,
                    }
                )
                retry_feedback.append(last_invalid_reason)
                continue

            candidate_draft = self._assemble_draft(
                event_id=event_id,
                run_id=run_id,
                block_plan=block_plan,
                write_parsed=write_parsed,
                write_text=write_result.text,
            )
            report = self._quality.evaluate(
                candidate_draft.draft_text,
                target_chars=int(budget_report.get("total_chars") or 0),
            )
            improvement = (
                None if previous_valid_score is None else report.score - previous_valid_score
            )
            attempt_records.append(
                {
                    "attempt": attempt,
                    "valid": True,
                    "score": report.score,
                    "passed": report.passed,
                    "issues": report.issues,
                    "improvement": improvement,
                }
            )
            if best_candidate is None or report.score > best_candidate[0]:
                best_candidate = (
                    report.score,
                    candidate_draft,
                    report,
                    attempt,
                )

            if report.passed:
                break
            retry_feedback.extend(report.issues)
            if improvement is not None and improvement < Defaults.QUALITY_PLATEAU_DELTA:
                _logger.info(
                    f"graph4_quality_plateau event={event_id} attempt={attempt} "
                    f"improvement={improvement:.2f}"
                )
                break
            previous_valid_score = report.score

        if best_candidate is None:
            reason = last_invalid_reason or "正文写作未返回可用正文"
            _logger.error(f"graph4_aborted_invalid_blocks_write event={event_id} reason={reason}")
            return Graph4Output(
                draft=EventDraft.model_construct(
                    event_id=event_id,
                    run_id=run_id,
                    draft_text="",
                    blocks=[],
                    word_count=0,
                ),
                context_package=context_package,
                budget_report=budget_report,
                quality_report={
                    "threshold": Defaults.MIN_EVENT_PROSE_SCORE,
                    "attempts": attempt_records,
                },
                execution_report=execution_report,
                quality_attempts=attempts_used,
                namecheck_passed=namecheck_passed,
                aborted=True,
                abort_reason=reason,
            )

        _, draft, selected_report, selected_attempt = best_candidate
        quality_report = selected_report.to_dict()
        quality_report.update(
            {
                "threshold": Defaults.MIN_EVENT_PROSE_SCORE,
                "selected_attempt": selected_attempt,
                "attempts": attempt_records,
            }
        )
        if not selected_report.passed:
            _logger.warning(
                f"graph4_quality_below_threshold event={event_id} "
                f"score={selected_report.score:.2f} attempts={attempts_used}"
            )

        _logger.info(
            f"graph4_done run={run_id} event={event_id} chars={draft.word_count} "
            f"quality={selected_report.score:.2f} attempts={attempts_used}"
        )
        return Graph4Output(
            draft=draft,
            context_package=context_package,
            budget_report=budget_report,
            quality_report=quality_report,
            execution_report=execution_report,
            quality_attempts=attempts_used,
            namecheck_passed=namecheck_passed,
        )

    def _run_approved_execution(
        self,
        *,
        inp: Graph4Input,
        event_id: str,
        context_package: ContextPackage,
        context: dict[str, Any],
    ) -> Graph4Output:
        """Write prose from an already approved execution report only."""

        run_id = inp.run_id
        event_slot = inp.event_slot
        override = deepcopy(inp.execution_override)
        budget_report = dict(override.get("budget_report") or {})
        event_route = dict(override.get("event_route") or {})
        world_pulse = dict(override.get("world_pulse") or {})
        event_expansion = dict(override.get("event_expansion") or {})
        prewrite_check = self.normalize_prewrite_check(override.get("prewrite_check"))
        event_plan = dict(override.get("event_plan") or {})
        block_plan = list(override.get("scene_plan") or event_plan.get("scenes") or [])
        event_plan["scenes"] = block_plan
        jit_cards = list(override.get("jit_cards") or [])
        namecheck = dict(override.get("namecheck") or {})
        namecheck_passed = bool(namecheck.get("passed", True))
        execution_report = self._build_execution_report(
            budget_report=budget_report,
            event_route=event_route,
            world_pulse=world_pulse,
            event_expansion=event_expansion,
            prewrite_check=prewrite_check,
            event_plan=event_plan,
            scene_plan=block_plan,
            jit_cards=jit_cards,
        )
        execution_report["namecheck"] = namecheck
        if not bool(prewrite_check.get("passed")):
            issues = prewrite_check.get("issues") or []
            detail = "；".join(map(str, issues)) if isinstance(issues, list) else str(issues)
            return Graph4Output(
                draft=EventDraft.model_construct(
                    event_id=event_id,
                    run_id=run_id,
                    draft_text="",
                    blocks=[],
                    word_count=0,
                ),
                context_package=context_package,
                budget_report=budget_report,
                execution_report=execution_report,
                aborted=True,
                abort_reason=f"已批准事件规划的正文前检查未通过{f'：{detail}' if detail else ''}",
            )
        if not block_plan:
            return Graph4Output(
                draft=EventDraft.model_construct(
                    event_id=event_id,
                    run_id=run_id,
                    draft_text="",
                    blocks=[],
                    word_count=0,
                ),
                context_package=context_package,
                budget_report=budget_report,
                execution_report=execution_report,
                aborted=True,
                abort_reason="已批准事件规划缺少连续场景，不能生成正文",
            )
        if inp.plan_only:
            return Graph4Output(
                draft=EventDraft.model_construct(
                    event_id=event_id,
                    run_id=run_id,
                    draft_text="",
                    blocks=[],
                    word_count=0,
                ),
                context_package=context_package,
                budget_report=budget_report,
                execution_report=execution_report,
                namecheck_passed=namecheck_passed,
            )

        write_input = {
            "event_id": event_id,
            "event_slot": event_slot,
            "event_plan": event_plan,
            "scene_plan": block_plan,
            "budget": budget_report,
            "event_route": event_route,
            "world_pulse": world_pulse,
            "event_expansion": event_expansion,
            "prewrite_check": prewrite_check,
            "jit_cards": jit_cards,
            "bible_content": context["bible_content"],
            "char_content": context["char_content"],
            "ledger_content": context["ledger_content"],
            "volume_content": context["volume_content"],
            "reg_content": context["reg_content"],
            "context_meta": context["context_meta"],
        }
        best_candidate = None
        previous_valid_score: float | None = None
        attempt_records: list[dict[str, Any]] = []
        retry_feedback: list[str] = []
        attempts_used = 0
        last_invalid_reason = ""

        for attempt in range(1, Defaults.MAX_PROSE_QUALITY_ATTEMPTS + 1):
            attempts_used = attempt
            _logger.info(
                f"graph4_step blocks_write run={run_id} event={event_id} attempt={attempt} "
                "source=approved_plan"
            )
            write_input["retry_feedback"] = retry_feedback[-4:]
            write_result = self._runner.run(
                step_key="graph4.event.blocks.write",
                input_pack=write_input,
                run_id=run_id,
            )
            write_parsed = self._normalize_blocks_write_output(write_result.parsed)
            valid, invalid_reason = self._validate_blocks_write_output(
                event_id=event_id,
                block_plan=block_plan,
                write_parsed=write_parsed,
                budget_report=budget_report,
            )
            if not write_result.ok or not valid:
                last_invalid_reason = (
                    "正文写作请求失败或重试耗尽"
                    if not write_result.ok
                    else invalid_reason or "正文写作未返回可用正文"
                )
                attempt_records.append(
                    {
                        "attempt": attempt,
                        "valid": False,
                        "reason": last_invalid_reason,
                    }
                )
                retry_feedback.append(last_invalid_reason)
                continue

            candidate_draft = self._assemble_draft(
                event_id=event_id,
                run_id=run_id,
                block_plan=block_plan,
                write_parsed=write_parsed,
                write_text=write_result.text,
            )
            report = self._quality.evaluate(
                candidate_draft.draft_text,
                target_chars=int(budget_report.get("total_chars") or 0),
            )
            improvement = (
                None if previous_valid_score is None else report.score - previous_valid_score
            )
            attempt_records.append(
                {
                    "attempt": attempt,
                    "valid": True,
                    "score": report.score,
                    "passed": report.passed,
                    "issues": report.issues,
                    "improvement": improvement,
                }
            )
            if best_candidate is None or report.score > best_candidate[0]:
                best_candidate = (report.score, candidate_draft, report, attempt)
            if report.passed:
                break
            retry_feedback.extend(report.issues)
            if improvement is not None and improvement < Defaults.QUALITY_PLATEAU_DELTA:
                break
            previous_valid_score = report.score

        if best_candidate is None:
            reason = last_invalid_reason or "正文写作未返回可用正文"
            return Graph4Output(
                draft=EventDraft.model_construct(
                    event_id=event_id,
                    run_id=run_id,
                    draft_text="",
                    blocks=[],
                    word_count=0,
                ),
                context_package=context_package,
                budget_report=budget_report,
                quality_report={
                    "threshold": Defaults.MIN_EVENT_PROSE_SCORE,
                    "attempts": attempt_records,
                },
                execution_report=execution_report,
                quality_attempts=attempts_used,
                namecheck_passed=namecheck_passed,
                aborted=True,
                abort_reason=reason,
            )

        _, draft, selected_report, selected_attempt = best_candidate
        quality_report = selected_report.to_dict()
        quality_report.update(
            {
                "threshold": Defaults.MIN_EVENT_PROSE_SCORE,
                "selected_attempt": selected_attempt,
                "attempts": attempt_records,
            }
        )
        return Graph4Output(
            draft=draft,
            context_package=context_package,
            budget_report=budget_report,
            quality_report=quality_report,
            execution_report=execution_report,
            quality_attempts=attempts_used,
            namecheck_passed=namecheck_passed,
        )

    @staticmethod
    def _build_execution_report(
        *,
        budget_report: dict[str, Any],
        event_route: dict[str, Any],
        world_pulse: dict[str, Any],
        event_expansion: dict[str, Any],
        prewrite_check: dict[str, Any],
        event_plan: dict[str, Any],
        scene_plan: list[Any],
        jit_cards: list[Any],
    ) -> dict[str, Any]:
        """Expose the planning trace needed by the workbench without changing prose behavior."""
        return {
            "budget_report": budget_report,
            "event_route": event_route,
            "world_pulse": world_pulse,
            "event_expansion": event_expansion,
            "prewrite_check": prewrite_check,
            "event_plan": event_plan,
            "scene_plan": scene_plan,
            "jit_cards": jit_cards,
        }

    # ── 内部工具 ──────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_budget(budget: dict[str, Any], event_slot: dict[str, Any]) -> dict[str, Any]:
        """Normalize an event-sized coverage target; this is not a chapter quota."""
        normalized = dict(budget or {})
        is_key = bool(event_slot.get("is_key_event"))
        conflict = str(event_slot.get("conflict_form") or "")
        is_breather = "缓冲" in conflict or "breather" in conflict.lower()
        cap = 12000 if is_key else 5000 if is_breather else 8500
        default_total = 8500 if is_key else 3200 if is_breather else 5600

        try:
            total = int(normalized.get("total_chars") or default_total)
        except (TypeError, ValueError):
            total = default_total
        total = max(1200, min(total, cap))

        normalized["total_chars"] = total
        normalized["soft_min_chars"] = max(1200, int(total * 0.72))
        normalized["narrative_weight"] = str(
            normalized.get("narrative_weight")
            or ("epic" if is_key else "small" if is_breather else "standard")
        )
        try:
            expansion_passes = int(normalized.get("expansion_passes") or (4 if is_key else 3))
        except (TypeError, ValueError):
            expansion_passes = 4 if is_key else 3
        normalized["expansion_passes"] = max(2, min(expansion_passes, 5))
        normalized.pop("chars_per_block", None)
        return normalized

    @staticmethod
    def _normalize_block_plan(
        block_plan: object, budget: dict[str, Any], event_slot: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Guarantee a usable scene weave without assigning per-scene word quotas."""
        plans = (
            [dict(item) for item in block_plan if isinstance(item, dict)]
            if isinstance(block_plan, list)
            else []
        )
        target_count = max(2, min(int(budget.get("scene_count_hint") or 4), 8))

        if not plans:
            stages = [
                ("Advance", "以具体场景切入压力，让主要人物作出第一个选择"),
                ("Advance", "通过行动、对话和环境阻力升级冲突并制造转折"),
                ("Settle", "让代价与关系反应落地，形成可见结果并留下章末钩子"),
                ("Foreshadow", "展示对手或势力的后续动作，建立下一事件驱动力"),
                ("Settle", "完成关键兑现，同时保留尚未解决的长期问题"),
            ]
            goal = str(event_slot.get("event_goal") or "推进当前事件")
            deliverables = list(event_slot.get("key_deliverables") or [])
            for i in range(target_count):
                intent, summary = stages[min(i, len(stages) - 1)]
                plans.append(
                    {
                        "scene_id": f"s{i + 1:03d}",
                        "block_intent": intent,
                        "scene_summary": f"{summary}。本场围绕：{goal}",
                        "conflict": str(event_slot.get("conflict_form") or "目标与阻力正面碰撞"),
                        "deliverables": deliverables or ["形成一个可见变化点", "留下后续驱动力"],
                        "beat_chain": [
                            "进入场景",
                            "人物互动",
                            "阻力升级",
                            "选择或反应",
                            "结果留痕",
                        ],
                    }
                )

        for i, plan in enumerate(plans):
            scene_id = str(plan.get("scene_id") or plan.get("block_id") or f"s{i + 1:03d}")
            plan["scene_id"] = scene_id
            plan["block_id"] = scene_id
            plan.pop("chars_hint", None)
            plan.setdefault(
                "beat_chain", ["进入场景", "人物互动", "阻力升级", "选择或反应", "结果留痕"]
            )
            plan.setdefault(
                "state_card_focus",
                {
                    "plot": [],
                    "character": [],
                    "scene": [],
                    "faction": [],
                    "item": [],
                    "ecology": [],
                },
            )
        return plans

    @staticmethod
    def _validate_blocks_write_output(
        event_id: str,
        block_plan: list[Any],
        write_parsed: object,
        budget_report: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        if not isinstance(write_parsed, dict):
            return False, "正文写作输出不是 JSON 对象"

        full_text = write_parsed.get("full_text")
        if not isinstance(full_text, str) or not full_text.strip():
            return False, "正文写作缺少连续的 full_text"
        if "【块－" in full_text or "【块-" in full_text or "【块结束】" in full_text:
            return False, "正文仍含内部块标记"

        expected_ids: list[str] = []
        for i, bp in enumerate(block_plan):
            if not isinstance(bp, dict):
                continue
            block_id = str(bp.get("scene_id") or bp.get("block_id") or f"s{i + 1:03d}")
            expected_ids.append(block_id)
        receipts = write_parsed.get("scene_receipts")
        if not isinstance(receipts, list):
            return False, "正文写作缺少 scene_receipts"
        seen: set[str] = set()
        for item in receipts:
            if not isinstance(item, dict):
                return False, "scene_receipts 中存在非对象条目"
            block_id = str(item.get("scene_id") or "")
            if not block_id:
                return False, "scene_receipts 条目缺少 scene_id"
            if block_id in seen:
                return False, f"场景收据重复：{block_id}"
            seen.add(block_id)

        missing = [block_id for block_id in expected_ids if block_id not in seen]
        if missing:
            return False, f"正文写作缺少场景收据：{', '.join(missing)}"
        if Graph4._looks_like_compressed_gibberish(full_text):
            return False, "正文疑似乱码或压缩词串"

        soft_min = int((budget_report or {}).get("soft_min_chars") or 0)
        actual_total = ProseQualityEvaluator.effective_char_count(full_text)
        if soft_min and actual_total < soft_min:
            return False, f"事件正文展开不足（{actual_total}字，软下限{soft_min}字）"

        return True, ""

    @staticmethod
    def _normalize_blocks_write_output(write_parsed: object) -> object:
        """Accept legacy block output as a migration fallback, but remove all markers."""
        if not isinstance(write_parsed, dict):
            return write_parsed
        if isinstance(write_parsed.get("full_text"), str):
            return write_parsed
        blocks_text = write_parsed.get("blocks_text")
        if not isinstance(blocks_text, list):
            return write_parsed
        texts: list[str] = []
        receipts: list[dict[str, Any]] = []
        for item in blocks_text:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            scene_id = str(item.get("scene_id") or item.get("block_id") or "")
            clean = item["text"]
            if scene_id:
                clean = clean.replace(f"【块－{scene_id}】", "").replace(f"【块-{scene_id}】", "")
            clean = clean.replace("【块结束】", "").strip()
            texts.append(clean)
            receipts.append({"scene_id": scene_id, "delivered_items": []})
        normalized = dict(write_parsed)
        normalized["full_text"] = "\n\n".join(texts)
        normalized["scene_receipts"] = normalized.get("scene_receipts") or receipts
        return normalized

    @staticmethod
    def _looks_like_compressed_gibberish(text: str) -> bool:
        compact = "".join(ch for ch in text if not ch.isspace())
        if len(compact) < 80:
            return False
        punctuation = set("，。！？；：、“”‘’（）《》—…,.!?;:")
        punct_count = sum(1 for ch in compact if ch in punctuation)
        if punct_count == 0:
            return True
        long_runs = [
            len(part)
            for part in "".join(
                ch if ch not in punctuation else "\n" for ch in compact
            ).splitlines()
            if part
        ]
        if max(long_runs, default=0) > 90:
            return True
        common_words = (
            "他",
            "她",
            "林深",
            "说道",
            "看见",
            "听见",
            "伸手",
            "转身",
            "低声",
            "眼前",
            "空气",
            "声音",
        )
        hits = sum(1 for word in common_words if word in compact)
        return len(compact) > 120 and hits == 0 and punct_count < max(3, len(compact) // 120)

    @staticmethod
    def _assemble_draft(
        event_id: str,
        run_id: str,
        block_plan: list[Any],
        write_parsed: object,
        write_text: str,
    ) -> EventDraft:
        """将 blocks_write 的输出组装成 EventDraft。"""
        full_text = ""
        block_specs: list[BlockSpec] = []

        if isinstance(write_parsed, dict):
            full_text = write_parsed.get("full_text", "")

            # 从 block_plan 构建 BlockSpec 列表
            for i, bp in enumerate(block_plan):
                if not isinstance(bp, dict):
                    continue
                # 找到对应的 blocks_text 条目
                block_id = bp.get("scene_id") or bp.get("block_id", f"s{i + 1:03d}")

                intent_raw = bp.get("block_intent", "Advance")
                try:
                    intent = BlockIntent(intent_raw)
                except ValueError:
                    intent = BlockIntent.ADVANCE

                spec = BlockSpec(
                    block_id=block_id,
                    block_intent=intent,
                    block_deliverables=bp.get("deliverables", []),
                    min_chars=None,
                    max_chars=None,
                )
                block_specs.append(spec)

        return EventDraft(
            event_id=event_id,
            run_id=run_id,
            draft_text=full_text,
            blocks=block_specs,
            word_count=len(full_text),
        )
