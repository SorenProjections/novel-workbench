"""领域核心模型 — Run/Step/Candidate/Diff/Material/Auth/Event/Chapter。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from novelwb.core.constants import (
    AuthObjectType,
    BlockIntent,
    CardPatchOperation,
    ChapterIntent,
    ContextPriority,
    FixLevel,
    MaterialCardType,
    StatusCardType,
)

# ── 通用基础 ─────────────────────────────────────────────────


class BaseSchema(BaseModel):
    schema_version: str = Field(default="v1", frozen=True)

    model_config = {"extra": "forbid"}


# ── Run / Step ────────────────────────────────────────────────


class RunManifest(BaseSchema):
    """一次完整执行的运行清单（含规范指纹）。"""

    run_id: str
    project_id: str
    step_key: str
    started_at: datetime
    finished_at: datetime | None = None
    spec_hash: str
    prompt_hash: str
    schema_hash: str
    stepspec_hash: str
    llm_adapter: str
    status: str = "running"  # running | completed | failed
    error_code: str | None = None


class StepRecord(BaseSchema):
    """单个 Step 执行记录。"""

    step_id: str
    run_id: str
    step_key: str
    graph: str
    attempt: int = 1
    started_at: datetime
    finished_at: datetime | None = None
    input_hash: str
    output_schema: str
    status: str = "running"
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    hardlint_passed: bool | None = None
    judge_score: float | None = None


class Candidate(BaseSchema):
    """best-of-n 中的单个候选产物。"""

    candidate_id: str
    step_id: str
    rank: int
    content: dict[str, Any]
    self_check_summary: str | None = None
    selected: bool = False


# ── LLM调用记录 ───────────────────────────────────────────────


class LLMCallRecord(BaseSchema):
    """每次 LLM 调用的完整记录。"""

    call_id: str
    step_id: str
    prompt_key: str
    prompt_version: str
    prompt_hash: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cached: bool = False
    timestamp: datetime


# ── DIFF / 对账报告 ───────────────────────────────────────────


class DiffReport(BaseSchema):
    """Reconcile 对账输出的 DIFF 报告。"""

    event_id: str
    run_id: str
    violated_forbidden: list[str] = Field(default_factory=list)
    missing_due_debts: list[str] = Field(default_factory=list)
    unbridged_state_jump: list[str] = Field(default_factory=list)
    name_collision: list[str] = Field(default_factory=list)
    rule_drift: list[str] = Field(default_factory=list)
    momentum_overflow: bool = False
    passed: bool = False
    fix_level_suggested: FixLevel | None = None
    patch_instructions: list[str] = Field(default_factory=list)
    soft_defects: list[str] = Field(default_factory=list)


# ── 素材卡 ────────────────────────────────────────────────────


class MaterialCard(BaseSchema):
    """RAG 素材卡（外部层，不进 BIBLE 主干）。"""

    material_id: str
    card_type: MaterialCardType
    ttl: datetime
    version: int = 1
    content: dict[str, Any]
    source_summary: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    replaceable: bool = True


# ── 权威层对象 ────────────────────────────────────────────────


class AuthObject(BaseSchema):
    """权威层通用包装（BIBLE/REG/CHAR/LEDGER/CONTRACT/MOTIF）。"""

    object_id: str
    project_id: str
    object_type: AuthObjectType
    version: int = 1
    content: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    committed_by_run_id: str


# ── 状态快照 ──────────────────────────────────────────────────

_STATUS_GROUP_TYPES: dict[str, StatusCardType] = {
    "plot_cards": StatusCardType.PLOT,
    "character_cards": StatusCardType.CHARACTER,
    "scene_cards": StatusCardType.SCENE,
    "faction_cards": StatusCardType.FACTION,
    "item_cards": StatusCardType.ITEM,
    "rule_cards": StatusCardType.RULE,
    "plot": StatusCardType.PLOT,
    "character": StatusCardType.CHARACTER,
    "scene": StatusCardType.SCENE,
    "faction": StatusCardType.FACTION,
    "item": StatusCardType.ITEM,
    "rule": StatusCardType.RULE,
}

_CARD_TYPE_ALIASES: dict[str, StatusCardType] = {
    "情节卡": StatusCardType.PLOT,
    "人物卡": StatusCardType.CHARACTER,
    "场景卡": StatusCardType.SCENE,
    "势力卡": StatusCardType.FACTION,
    "道具卡": StatusCardType.ITEM,
    "规则卡": StatusCardType.RULE,
    **_STATUS_GROUP_TYPES,
}


def _coerce_card_type(value: Any, fallback: StatusCardType = StatusCardType.PLOT) -> StatusCardType:
    if isinstance(value, StatusCardType):
        return value
    text = str(value or "").strip()
    if text in _CARD_TYPE_ALIASES:
        return _CARD_TYPE_ALIASES[text]
    try:
        return StatusCardType(text)
    except ValueError:
        return fallback


def _fallback_card_id(card_type: StatusCardType, name: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", name).strip("_")
    return f"{card_type.value}_{slug or 'unnamed'}"


class SourceRef(BaseSchema):
    """状态卡或上下文片段的可追溯来源。"""

    authority: str
    object_id: str | None = None
    version: int | None = None
    path: str | None = None
    event_id: str | None = None
    evidence: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_source_ref(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"authority": "legacy", "evidence": value}
        return value


class CharacterKnowledge(BaseSchema):
    """单个角色对某张卡所代表事实的知识边界。"""

    known_facts: list[str] = Field(default_factory=list)
    suspicions: list[str] = Field(default_factory=list)
    blind_spots: list[str] = Field(default_factory=list)


class RevelationGate(BaseSchema):
    """揭秘前置条件；供规划和连续性检查使用。"""

    minimum_event_index: int | None = None
    required_fact_ids: list[str] = Field(default_factory=list)
    required_hint_ids: list[str] = Field(default_factory=list)
    satisfied_hint_ids: list[str] = Field(default_factory=list)
    allowed_knowers: list[str] = Field(default_factory=list)


class StatusCard(BaseSchema):
    """权威数据的强类型阅读投影。"""

    card_id: str
    card_type: StatusCardType
    card_name: str
    subject_id: str | None = None
    summary: str | None = None
    current_state: Any = None
    constraints: list[str] = Field(default_factory=list)
    reader_needs: list[str] = Field(default_factory=list)
    reader_knowledge: list[str] = Field(default_factory=list)
    character_knowledge: dict[str, CharacterKnowledge] = Field(default_factory=dict)
    open_questions: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    source_version: int = 1
    last_touched_event_id: str | None = None
    revelation_gate: RevelationGate | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_card(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        card_type = _coerce_card_type(data.get("card_type"))
        data["card_type"] = card_type
        card_name = str(
            data.get("card_name")
            or data.get("name")
            or data.get("title")
            or data.get("card_id")
            or "未命名状态卡"
        )
        data["card_name"] = card_name
        data.setdefault("card_id", _fallback_card_id(card_type, card_name))

        source_refs = list(data.get("source_refs") or [])
        legacy_source = data.pop("source", None)
        if legacy_source:
            source_refs.append({"authority": "legacy", "evidence": str(legacy_source)})
        data["source_refs"] = source_refs

        known = set(cls.model_fields) | {"schema_version", "name", "title"}
        attributes = dict(data.get("attributes") or {})
        for key in list(data):
            if key not in known:
                attributes[key] = data.pop(key)
        data.pop("name", None)
        data.pop("title", None)
        data["attributes"] = attributes
        return data


class ReadingFocus(BaseSchema):
    """一次事件/章节为什么需要读取某张状态卡。"""

    focus_id: str
    card_id: str
    card_type: StatusCardType
    why_needed: str
    priority: ContextPriority = ContextPriority.MEDIUM
    requested_fields: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_focus(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        card_type = _coerce_card_type(data.get("card_type"))
        data["card_type"] = card_type
        data.setdefault(
            "card_id", _fallback_card_id(card_type, str(data.get("card_name") or "unnamed"))
        )
        data.setdefault("focus_id", f"focus_{data['card_id']}")
        data.setdefault("why_needed", str(data.get("reason") or "当前事件需要读取"))
        priority = str(data.get("priority") or "medium").lower()
        data["priority"] = {
            "高": "high",
            "中": "medium",
            "低": "low",
        }.get(priority, priority if priority in {"high", "medium", "low"} else "medium")
        data.pop("reason", None)
        data.pop("card_name", None)
        return data


class CardPatch(BaseSchema):
    """状态卡字段级变更；必须携带正文证据。"""

    patch_id: str
    operation: CardPatchOperation = CardPatchOperation.UPDATE
    card_id: str
    card_type: StatusCardType
    changed_fields: list[str] = Field(default_factory=list)
    card: StatusCard | None = None
    evidence: list[str] = Field(default_factory=list)
    revealed_to: list[str] = Field(default_factory=list)
    base_version: int | None = None
    new_version: int | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_patch(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        card_payload = data.get("card")
        if isinstance(card_payload, StatusCard):
            return data
        if not isinstance(card_payload, dict):
            card_payload = dict(data)
            for key in (
                "patch_id",
                "operation",
                "changed_fields",
                "evidence",
                "revealed_to",
                "base_version",
                "new_version",
            ):
                card_payload.pop(key, None)
            data["card"] = card_payload

        card_type = _coerce_card_type(data.get("card_type") or card_payload.get("card_type"))
        data["card_type"] = card_type
        card_name = str(card_payload.get("card_name") or card_payload.get("name") or "unnamed")
        card_id = str(
            data.get("card_id")
            or card_payload.get("card_id")
            or _fallback_card_id(card_type, card_name)
        )
        data["card_id"] = card_id
        data.setdefault("patch_id", f"patch_{card_id}")
        data.setdefault("operation", "update")
        data.setdefault(
            "changed_fields",
            [
                key
                for key in card_payload
                if key not in {"card_id", "card_type", "card_name", "name", "source", "source_refs"}
            ],
        )
        if not data.get("evidence") and card_payload.get("source"):
            data["evidence"] = [str(card_payload["source"])]
        allowed = set(cls.model_fields) | {"schema_version"}
        data = {key: item for key, item in data.items() if key in allowed}
        return data


class StatusCardIndex(BaseSchema):
    """所有状态卡的派生索引，可从权威层和事件记录重建。"""

    index_version: int = 1
    cards: list[StatusCard] = Field(default_factory=list)
    updated_by_event_id: str | None = None


class ContextSource(BaseSchema):
    source_id: str
    authority: str
    object_id: str | None = None
    version: int | None = None
    path: str
    reason: str
    protected: bool = False
    payload: Any
    estimated_tokens: int = 0


class ContextCardSelection(BaseSchema):
    card: StatusCard
    reason: str
    priority: ContextPriority = ContextPriority.MEDIUM
    relevance_score: float = 0.0
    estimated_tokens: int = 0


class ContextOmission(BaseSchema):
    source_id: str
    reason: str


class ContextPackage(BaseSchema):
    """一次事件真正交给模型的受治理上下文。"""

    context_id: str
    event_id: str
    focus: str
    protected_sources: list[ContextSource] = Field(default_factory=list)
    selected_sources: list[ContextSource] = Field(default_factory=list)
    selected_cards: list[ContextCardSelection] = Field(default_factory=list)
    omitted: list[ContextOmission] = Field(default_factory=list)
    source_versions: dict[str, int] = Field(default_factory=dict)
    token_budget: int
    estimated_tokens: int = 0
    fingerprint: str


class StateSnapshot(BaseSchema):
    """事件前/后状态快照（PreSnapshot / state_after）。"""

    snapshot_key: str
    event_id: str | None = None
    location: str | None = None
    time_in_story: str | None = None
    resources: dict[str, Any] = Field(default_factory=dict)
    hp: dict[str, Any] = Field(default_factory=dict)
    ability_boundary: list[str] = Field(default_factory=list)
    relationship_state: dict[str, Any] = Field(default_factory=dict)
    entity_states: dict[str, dict[str, Any]] = Field(default_factory=dict)
    narrative_line_states: dict[str, dict[str, Any]] = Field(default_factory=dict)
    entity_agendas: dict[str, dict[str, Any]] = Field(default_factory=dict)
    asset_states: dict[str, dict[str, Any]] = Field(default_factory=dict)
    timeline_events: list[dict[str, Any]] = Field(default_factory=list)
    result_state_summary: str | None = None
    open_threads: list[str] = Field(default_factory=list)
    reading_focus: list[ReadingFocus] = Field(default_factory=list)
    status_cards: dict[str, list[StatusCard]] = Field(default_factory=dict)
    context_fingerprint: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_status_card_groups(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        groups = data.get("status_cards")
        if isinstance(groups, dict):
            normalized: dict[str, list[dict[str, Any]]] = {}
            for group, cards in groups.items():
                if not isinstance(cards, list):
                    continue
                fallback = _STATUS_GROUP_TYPES.get(str(group), StatusCardType.PLOT)
                normalized[str(group)] = []
                for card in cards:
                    if isinstance(card, StatusCard):
                        normalized[str(group)].append(card.model_dump(mode="python"))
                        continue
                    if not isinstance(card, dict):
                        continue
                    card_data = dict(card)
                    card_data["card_type"] = _coerce_card_type(card_data.get("card_type"), fallback)
                    normalized[str(group)].append(card_data)
            data["status_cards"] = normalized
        return data


# ── 事件相关 ──────────────────────────────────────────────────


class BlockSpec(BaseSchema):
    """正文块规格。"""

    block_id: str
    block_intent: BlockIntent
    block_deliverables: list[str] = Field(default_factory=list)
    local_deliverables: list[str] = Field(default_factory=list)
    min_chars: int | None = None
    max_chars: int | None = None


class EventDraft(BaseSchema):
    """事件正文草稿（含块注）。"""

    event_id: str
    run_id: str
    draft_text: str
    blocks: list[BlockSpec] = Field(default_factory=list)
    word_count: int = 0
    self_check_summary: str | None = None


class ObservedDelta(BaseSchema):
    """事件后抽取的实际变化。"""

    state_after: StateSnapshot
    changed_items: list[str] = Field(default_factory=list)
    new_entities: list[str] = Field(default_factory=list)
    renamed_entities: list[dict[str, str]] = Field(default_factory=list)
    retired_entities: list[str] = Field(default_factory=list)
    has_bridge_segment: bool = False
    result_state_summary: str
    open_threads_update: list[str] = Field(default_factory=list)
    momentum_debt_delta: int = 0
    card_updates: dict[str, list[CardPatch]] = Field(default_factory=dict)
    narrative_line_updates: list[dict[str, Any]] = Field(default_factory=list)
    entity_agenda_updates: list[dict[str, Any]] = Field(default_factory=list)
    asset_lifecycle_updates: list[dict[str, Any]] = Field(default_factory=list)
    timeline_updates: list[dict[str, Any]] = Field(default_factory=list)
    plan_adjustment_requests: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_card_patch_groups(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        groups = data.get("card_updates")
        if isinstance(groups, dict):
            normalized: dict[str, list[dict[str, Any]]] = {}
            for group, patches in groups.items():
                if not isinstance(patches, list):
                    continue
                fallback = _STATUS_GROUP_TYPES.get(str(group), StatusCardType.PLOT)
                normalized[str(group)] = []
                for patch in patches:
                    if isinstance(patch, CardPatch):
                        normalized[str(group)].append(patch.model_dump(mode="python"))
                        continue
                    if not isinstance(patch, dict):
                        continue
                    patch_data = dict(patch)
                    patch_data["card_type"] = _coerce_card_type(
                        patch_data.get("card_type"), fallback
                    )
                    card = patch_data.get("card")
                    if isinstance(card, dict):
                        card = dict(card)
                        card["card_type"] = _coerce_card_type(card.get("card_type"), fallback)
                        patch_data["card"] = card
                    normalized[str(group)].append(patch_data)
            data["card_updates"] = normalized
        return data


class EventRecord(BaseSchema):
    """已提交的事件完整记录。"""

    event_id: str
    project_id: str
    volume_id: str | None = None
    event_version: int = 1
    draft_text: str
    blocks: list[BlockSpec] = Field(default_factory=list)
    state_before_key: str
    state_after_key: str
    observed_delta: ObservedDelta
    diff_report: DiffReport
    committed_at: datetime
    committed_by_run_id: str
    ledger_version_after: int
    is_key_event: bool = False
    context_package_id: str | None = None
    context_fingerprint: str | None = None


# ── 台账条目 ──────────────────────────────────────────────────


class LedgerEntry(BaseSchema):
    """四账台账单条目。"""

    entry_id: str
    entry_type: str  # Promise|Payoff|HookDebt|EmotionDebt|EmotionPayoff
    content: str
    due_event_id: str | None = None
    overdue: bool = False
    settled: bool = False
    settled_event_id: str | None = None
    momentum_debt_delta: int = 0


# ── 章节相关 ──────────────────────────────────────────────────


class ChapterSpec(BaseSchema):
    """单章规格（章节化产物）。"""

    chapter_id: str
    chapter_index: int
    title: str | None = None
    chapter_intent: ChapterIntent
    deliverables: list[str] = Field(default_factory=list)
    hook_type: str | None = None
    emotion_channel: str | None = None
    block_range: tuple[str, str] | None = None  # (start_block_id, end_block_id)
    start_anchor: str | None = None
    end_anchor: str | None = None
    estimated_chars: int = 0
    end_asset_summary: str | None = None
    ledger_patch: dict[str, Any] = Field(default_factory=dict)
    momentum_debt_delta: int = 0


class ChapterCommitRecord(BaseSchema):
    """已提交的章节化记录（Phase-2）。"""

    chapter_id: str
    project_id: str
    volume_id: str | None = None
    chapter_index: int
    chapter_intent: ChapterIntent
    text: str
    word_count: int
    committed_at: datetime
    committed_by_run_id: str
    source_event_ids: list[str] = Field(default_factory=list)


# ── 卷规划 ────────────────────────────────────────────────────


class VolumeContract(BaseSchema):
    """卷契约 VCON。"""

    volume_id: str
    project_id: str
    sub_question: str
    conflict_form_rotation: list[str] = Field(default_factory=list)
    breather_quota: float = 0.25
    max_consecutive_breather: int = 2
    momentum_debt_max: int = 5
    end_settlement_type: str | None = None
    promise_scenes: list[str] = Field(default_factory=list)
    motif_steps: list[str] = Field(default_factory=list)


class EventSlot(BaseSchema):
    """事件槽位（分卷规划产物）。"""

    slot_id: str
    volume_id: str
    event_goal: str
    result_target: str
    pre_snapshot_key: str | None = None
    required_debts_handling: list[str] = Field(default_factory=list)
    allowed_delta: list[str] = Field(default_factory=list)
    forbidden_delta: list[str] = Field(default_factory=list)
    conflict_form: str | None = None
    block_intent_distribution: list[BlockIntent] = Field(default_factory=list)
    is_key_event: bool = False
    need_ethics_cost: bool = False
    forbid_breather_dilution: bool = False


# ── 疲劳报告 ──────────────────────────────────────────────────


class FatigueReport(BaseSchema):
    """疲劳报告（周期性统计）。"""

    report_id: str
    project_id: str
    volume_id: str | None = None
    chapter_range: tuple[int, int] | None = None
    conflict_form_ratio: dict[str, float] = Field(default_factory=dict)
    advance_delta_frequency: float = 0.0
    hook_repeat_rate: float = 0.0
    breather_usage_rate: float = 0.0
    max_consecutive_breather_seen: int = 0
    momentum_debt_trend: list[int] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    intent_rotation_advice: str | None = None
    generated_at: datetime


# ── 人工审核修订 ──────────────────────────────────────────────


class ReviewRevisionRequest(BaseSchema):
    """人工审核定向修订的完整输入包。"""

    review_kind: str
    file_label: str
    review_feedback: str
    original_content: Any
    required_constraints: dict[str, Any] = Field(default_factory=dict)
    full_context: dict[str, Any] = Field(default_factory=dict)


class ReviewAuditIssue(BaseSchema):
    """审核发现的一项可定位、可执行问题。"""

    severity: str
    category: str
    location_anchor: str
    problem: str
    authority_basis: str
    revision_instruction: str


class ReviewAuditResult(BaseSchema):
    """独立审核步骤的结构化结论，不包含改写后的正文。"""

    verdict: str
    summary: str
    strengths: list[str] = Field(default_factory=list)
    issues: list[ReviewAuditIssue] = Field(default_factory=list)
    revision_feedback: str


class ReviewRevisionResult(BaseSchema):
    """模型依据人工审核意见对当前暂存稿进行的定向修订。"""

    revised_content: Any
    change_summary: str
    preserved_summary: str = ""
