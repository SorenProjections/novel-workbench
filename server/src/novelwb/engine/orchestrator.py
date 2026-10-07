"""Orchestrator — 顶层调度器。

职责：
- 组装 GraphDeps（LLM adapter + PromptRegistry + StepSpecs）
- 路由到对应的图执行器
- 提供高层 pipeline 入口：run_event_pipeline / run_auth_pipeline / run_regression
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from novelwb.adapters.llm.base import LLMAdapter
from novelwb.adapters.search.base import SearchAdapter
from novelwb.adapters.search.noop import NoopSearchAdapter
from novelwb.core.constants import AuthObjectType, StagingType
from novelwb.core.prompt_registry import PromptRegistry
from novelwb.core.schemas.domain_models import (
    AuthObject,
    ChapterCommitRecord,
    ChapterSpec,
    ContextPackage,
    EventDraft,
    StateSnapshot,
    VolumeContract,
)
from novelwb.core.schemas.patch_models import StagingPacket
from novelwb.core.step_specs_loader import load_all_stepspecs
from novelwb.engine.asset_catalog import LayeredAssetCatalog
from novelwb.engine.complexity import detect_complexity_profile
from novelwb.engine.foundation_validation import (
    foundation_downstream_closure,
)
from novelwb.engine.graphs import (
    FOUNDATION_STEP_LABELS,
    FOUNDATION_STEP_ORDER,
    Graph1,
    Graph1Input,
    Graph2,
    Graph2Input,
    Graph3,
    Graph3Input,
    Graph4,
    Graph4Input,
    Graph5,
    Graph5Input,
    GraphE,
    GraphEInput,
    GraphEOutput,
    GraphP,
    GraphPInput,
    GraphPOutput,
    GraphS,
    GraphSInput,
    GraphSOutput,
    event_plan_step_complete,
    event_plan_steps,
    execution_report_from_event_plan,
    master_plan_step_complete,
    master_plan_steps,
    next_event_plan_step,
    next_master_plan_step,
    next_volume_plan_step,
    volume_plan_step_complete,
    volume_plan_steps,
)
from novelwb.engine.graphs.graph_2 import MasterPlanStep
from novelwb.engine.graphs.graph_3 import VolumePlanStep
from novelwb.engine.graphs.graph_4 import EventPlanStep
from novelwb.engine.hard_lint import HardLintEngine
from novelwb.engine.judge import Judge
from novelwb.engine.policies import RepairPolicy, RetryPolicy
from novelwb.engine.regression import RegressionContext, RegressionRunner
from novelwb.engine.review_service import ReviewService
from novelwb.engine.status_card_projector import project_initial_status_cards
from novelwb.engine.step_runner import GraphDeps, StepRunner
from novelwb.storage import (
    AuthStore,
    ContextStore,
    EventsStore,
    FileLock,
    LockTimeoutError,
    PublishStore,
    SnapshotsStore,
    StagingStore,
)
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.file_locks import shared_thread_lock
from novelwb.utils.ids import new_event_id, new_staging_id
from novelwb.utils.io_atomic import atomic_write_json
from novelwb.utils.logger import get_logger
from novelwb.utils.timeutil import utcnow
from novelwb.utils.transactions import atomic_method, transaction

_logger = get_logger(__name__)


@dataclass
class OrchestratorConfig:
    """Orchestrator 配置。"""

    workspace_root: Path
    project_id: str
    prompts_dir: Path  # src/novelwb/prompts/
    core_dir: Path  # src/novelwb/core/
    llm_adapter: LLMAdapter
    search_adapter: SearchAdapter = field(default_factory=NoopSearchAdapter)
    max_retries: int = 3


class Orchestrator:
    """流水线调度器，组装所有依赖并提供高层 run_* 入口。"""

    def __init__(self, config: OrchestratorConfig) -> None:
        self._cfg = config
        self._layout = WorkspaceLayout(config.workspace_root, config.project_id)

        # 加载 StepSpecs 和 PromptRegistry
        step_specs = load_all_stepspecs(config.core_dir)
        prompt_registry = PromptRegistry(config.prompts_dir)

        # 组装共享依赖
        self._deps = GraphDeps(
            llm=config.llm_adapter,
            prompt_registry=prompt_registry,
            prompts_dir=config.prompts_dir,
            step_specs=step_specs,
            lint_engine=HardLintEngine(),
            judge=Judge(lint_engine=HardLintEngine()),
        )

        self._repair_policy = RepairPolicy(max_retries=config.max_retries)
        self._retry_policy = RetryPolicy(max_retries=config.max_retries)

        # 各图执行器
        self._graph_1 = Graph1(self._deps, self._layout)
        self._graph_2 = Graph2(self._deps, self._layout)
        self._graph_3 = Graph3(self._deps, self._layout)
        self._graph_4 = Graph4(self._deps, self._layout)
        self._graph_e = GraphE(self._deps, self._layout, self._repair_policy)
        self._graph_s = GraphS(self._deps, self._layout)
        self._graph_5 = Graph5(self._deps, self._layout)
        self._graph_p = GraphP(self._deps, self._layout)
        self._review_runner = StepRunner(self._deps)
        self._regression = RegressionRunner()

        # 存储层
        self._auth_store = AuthStore(self._layout)
        self._events_store = EventsStore(self._layout)
        self._publish_store = PublishStore(self._layout)
        self._snapshots_store = SnapshotsStore(self._layout)
        self._context_store = ContextStore(self._layout)
        self._staging_store = StagingStore(self._layout)
        self._asset_catalog = LayeredAssetCatalog(self._layout)
        # Model switches create a new adapter snapshot, but must retain project guards.
        project = self._layout.project_dir
        self._foundation_generation_lock = shared_thread_lock(project, "foundation_generation")
        self._master_generation_lock = shared_thread_lock(project, "master_generation")
        self._volume_generation_lock = shared_thread_lock(project, "volume_generation")
        self._event_generation_lock = shared_thread_lock(project, "event_generation")
        self._event_approval_lock = shared_thread_lock(project, "event_approval")
        self._review_revision_lock = shared_thread_lock(project, "review_revision")
        self._reviews = ReviewService(self)

    # ── 细粒度进度上报（让 StepRunner 的每一步流式可见）────────────────────

    @contextmanager
    def _progress_sink(self, progress: Callable[[dict[str, Any]], None] | None) -> Iterator[None]:
        """临时把进度回调挂到共享 deps 上，让所有 StepRunner 步骤自动上报。"""
        token = self._deps.progress_context.set(progress or self._deps.progress_context.get())
        try:
            yield
        finally:
            self._deps.progress_context.reset(token)

    # ── Human-reviewed workflow ───────────────────────────────────────────

    def workflow_state(self) -> dict[str, Any]:
        packets = sorted(self._staging_store.list_all(), key=lambda item: item.created_at)
        reviews = [
            self._review_payload(packet) for packet in packets if packet.content.get("review_kind")
        ]
        pending = [item for item in reviews if item["status"] == "pending"]
        foundation_objects = {
            key: self._auth_store.load_artifact(key) for key in FOUNDATION_STEP_ORDER
        }
        spec00 = foundation_objects["spec00"]
        foundation_complete = all(foundation_objects.values())
        foundation_approved_count = sum(obj is not None for obj in foundation_objects.values())
        next_foundation_key = next(
            (key for key in FOUNDATION_STEP_ORDER if foundation_objects[key] is None),
            None,
        )
        pending_foundation_steps = {
            str(packet.content.get("internal", {}).get("foundation_step") or "")
            for packet in packets
            if packet.content.get("review_kind") == "foundation"
            and packet.content.get("status", "pending") == "pending"
        }
        longline = self._auth_store.load_artifact("longline")
        cast = foundation_objects.get("cast")
        master_content = longline.content if longline is not None else {}
        master_steps = master_plan_steps(cast.content if cast else {}, master_content)
        master_approved_count = sum(
            master_plan_step_complete(master_content, item) for item in master_steps
        )
        next_master_step = next_master_plan_step(
            master_content,
            cast.content if cast else {},
        )
        master_complete = bool(master_steps) and master_approved_count == len(master_steps)
        pending_master_steps = {
            str(packet.content.get("internal", {}).get("master_step") or "")
            for packet in packets
            if packet.content.get("review_kind") == "master_plan"
            and packet.content.get("status", "pending") == "pending"
        }
        complexity_level = str(
            (spec00.content.get("complexity_profile", {}) if spec00 else {}).get("level")
            or "medium"
        )
        events_per_volume = self._events_per_volume(spec00)
        latest_contract = self._auth_store.load_latest("CONTRACT")
        volume_contract = (
            latest_contract
            if latest_contract
            and isinstance(latest_contract.content, dict)
            and isinstance(latest_contract.content.get("event_slots"), list)
            else None
        )
        volume_content = volume_contract.content if volume_contract is not None else {}
        volume_steps = volume_plan_steps(events_per_volume)
        volume_approved_count = sum(
            volume_plan_step_complete(volume_content, item) for item in volume_steps
        )
        next_volume_step = next_volume_plan_step(volume_content, events_per_volume)
        volume_complete = bool(volume_steps) and volume_approved_count == len(volume_steps)
        pending_volume_steps = {
            str(packet.content.get("internal", {}).get("volume_step") or "")
            for packet in packets
            if packet.content.get("review_kind") == "volume_plan"
            and packet.content.get("status", "pending") == "pending"
        }
        try:
            current_volume_index = int(
                str(volume_content.get("volume_id") or "vol_001").split("_")[-1]
            )
        except (TypeError, ValueError):
            current_volume_index = 1
        event_slots = volume_content.get("event_slots", []) if volume_complete else []
        completed_events = len(self._events_store.list_index())
        next_event_index = completed_events + 1 if completed_events < len(event_slots) else 0
        pending_event_steps = {
            (
                str(packet.content.get("internal", {}).get("event_id") or ""),
                str(packet.content.get("internal", {}).get("event_plan_step") or ""),
            )
            for packet in packets
            if packet.content.get("review_kind") == "event_plan"
            and packet.content.get("status", "pending") == "pending"
        }
        event_plan_progress: dict[str, dict[str, Any]] = {}
        planning_steps = event_plan_steps()
        for position, raw_slot in enumerate(event_slots, start=1):
            if not isinstance(raw_slot, dict):
                continue
            normalized_slot = self._normalize_volume_slot(raw_slot, position)
            event_id = str(normalized_slot.get("slot_id") or f"evt_{position:03d}")
            next_plan_step = next_event_plan_step(volume_content, event_id)
            approved_count = sum(
                event_plan_step_complete(volume_content, event_id, item) for item in planning_steps
            )
            event_plan_progress[event_id] = {
                "event_id": event_id,
                "event_index": position,
                "approved_count": approved_count,
                "total": len(planning_steps),
                "complete": approved_count == len(planning_steps),
                "next_step": next_plan_step.step_id if next_plan_step else None,
                "total_output_budget": sum(item.max_tokens for item in planning_steps),
                "steps": [
                    {
                        "id": item.step_id,
                        "label": item.label,
                        "asset_id": item.asset_id,
                        "index": step_index,
                        "max_tokens": item.max_tokens,
                        "status": (
                            "approved"
                            if event_plan_step_complete(volume_content, event_id, item)
                            else "pending"
                            if (event_id, item.step_id) in pending_event_steps
                            else "available"
                            if next_plan_step and item.step_id == next_plan_step.step_id
                            else "locked"
                        ),
                    }
                    for step_index, item in enumerate(planning_steps, start=1)
                ],
            }
        current_event_id = ""
        if next_event_index:
            current_slot = self._normalize_volume_slot(
                event_slots[next_event_index - 1], next_event_index
            )
            current_event_id = str(current_slot.get("slot_id") or "")
        current_plan_complete = bool(
            current_event_id and event_plan_progress.get(current_event_id, {}).get("complete")
        )
        pending_kinds = {item["review_kind"] for item in pending}
        approved_kinds = {item["review_kind"] for item in reviews if item["status"] == "approved"}

        def stage(stage_id: str, label: str, approved: bool, unlocked: bool) -> dict[str, Any]:
            status = (
                "pending"
                if stage_id in pending_kinds
                else "approved"
                if approved
                else "available"
                if unlocked
                else "locked"
            )
            return {"id": stage_id, "label": label, "status": status}

        return {
            "stages": [
                stage(
                    "foundation",
                    f"作品基座 {foundation_approved_count}/{len(FOUNDATION_STEP_ORDER)}",
                    foundation_complete,
                    True,
                ),
                stage(
                    "master_plan",
                    f"全书总纲与资产 {master_approved_count}/{len(master_steps)}",
                    master_complete,
                    foundation_complete,
                ),
                stage(
                    "volume_plan",
                    f"卷纲与资产 {volume_approved_count}/{len(volume_steps)}",
                    volume_complete,
                    master_complete,
                ),
                stage(
                    "event_plan",
                    "事件展开方案",
                    completed_events > 0 or current_plan_complete or "event_plan" in approved_kinds,
                    bool(event_slots),
                ),
                stage(
                    "prose",
                    "正文草稿",
                    completed_events > 0 or "prose" in approved_kinds,
                    current_plan_complete,
                ),
                stage(
                    "state_delta",
                    "状态差异",
                    completed_events > 0 or "state_delta" in approved_kinds,
                    bool(event_slots),
                ),
                stage(
                    "chapter_plan",
                    "自然切章",
                    completed_events > 0 or "chapter_plan" in approved_kinds,
                    bool(event_slots),
                ),
            ],
            "reviews": reviews,
            "pending_reviews": pending,
            "event_slots": event_slots,
            "completed_events": completed_events,
            "next_event_index": next_event_index,
            "event_plan_progress": event_plan_progress,
            "foundation_progress": {
                "approved_count": foundation_approved_count,
                "total": len(FOUNDATION_STEP_ORDER),
                "complete": foundation_complete,
                "next_step": next_foundation_key,
                "brief": self._foundation_brief_from_packets(packets),
                "invalidated": self._auth_store.invalidation_details(),
                "steps": [
                    {
                        "id": key,
                        "label": FOUNDATION_STEP_LABELS[key],
                        "index": index,
                        "status": (
                            "approved"
                            if foundation_objects[key] is not None
                            else "pending"
                            if key in pending_foundation_steps
                            else "available"
                            if key == next_foundation_key
                            else "locked"
                        ),
                    }
                    for index, key in enumerate(FOUNDATION_STEP_ORDER, start=1)
                ],
            },
            "master_plan_progress": {
                "approved_count": master_approved_count,
                "total": len(master_steps),
                "complete": master_complete,
                "next_step": next_master_step.step_id if next_master_step else None,
                "complexity_level": complexity_level,
                "total_output_budget": sum(
                    item.max_tokens(complexity_level) for item in master_steps
                ),
                "steps": [
                    {
                        "id": item.step_id,
                        "label": item.label,
                        "asset_id": item.asset_id,
                        "index": index,
                        "max_tokens": item.max_tokens(complexity_level),
                        "character_id": item.character_id or None,
                        "status": (
                            "approved"
                            if master_plan_step_complete(master_content, item)
                            else "pending"
                            if item.step_id in pending_master_steps
                            else "available"
                            if next_master_step and item.step_id == next_master_step.step_id
                            else "locked"
                        ),
                    }
                    for index, item in enumerate(master_steps, start=1)
                ],
            },
            "volume_plan_progress": {
                "approved_count": volume_approved_count,
                "total": len(volume_steps),
                "complete": volume_complete,
                "next_step": next_volume_step.step_id if next_volume_step else None,
                "volume_index": current_volume_index,
                "events_per_volume": events_per_volume,
                "total_output_budget": sum(item.max_tokens for item in volume_steps),
                "steps": [
                    {
                        "id": item.step_id,
                        "label": item.label,
                        "asset_id": item.asset_id,
                        "index": index,
                        "max_tokens": item.max_tokens,
                        "start_event": item.start_index + 1 if item.is_chunk else None,
                        "end_event": item.end_index if item.is_chunk else None,
                        "status": (
                            "approved"
                            if volume_plan_step_complete(volume_content, item)
                            else "pending"
                            if item.step_id in pending_volume_steps
                            else "available"
                            if next_volume_step and item.step_id == next_volume_step.step_id
                            else "locked"
                        ),
                    }
                    for index, item in enumerate(volume_steps, start=1)
                ],
            },
        }

    @atomic_method
    def rewind_foundation(self, step_key: str, run_id: str) -> dict[str, Any]:
        """Non-destructively reopen one foundation file and all dependent files."""
        if step_key not in FOUNDATION_STEP_ORDER:
            raise ValueError(f"未知作品基座步骤：{step_key}")
        if (
            self._auth_store.load_artifact("longline") is not None
            or self._auth_store.load_latest("CONTRACT") is not None
            or self._events_store.list_index()
        ):
            raise ValueError(
                "项目已经进入总纲、卷纲或正文阶段；不能直接退回作品基座，以免让已写内容失去依据"
            )

        affected = foundation_downstream_closure(step_key)
        existing = {
            key: self._auth_store.load_artifact(key, include_invalidated=True)
            for key in FOUNDATION_STEP_ORDER
        }
        if existing.get(step_key) is None:
            raise ValueError(f"作品基座文件 {step_key} 尚未生成，无需退回")

        now = utcnow()
        snapshot_key = f"foundation_rewind_{now.strftime('%Y%m%dT%H%M%S')}_{run_id[-8:]}"
        snapshot_path = self._layout.snapshot_path(snapshot_key)
        atomic_write_json(
            snapshot_path,
            {
                "snapshot_kind": "foundation_rewind",
                "project_id": self._cfg.project_id,
                "run_id": run_id,
                "from_step": step_key,
                "affected": affected,
                "created_at": now.isoformat(),
                "artifacts": {
                    key: obj.model_dump(mode="json") if obj is not None else None
                    for key, obj in existing.items()
                },
            },
        )

        packets = self._staging_store.list_all()
        for packet in packets:
            internal = packet.content.get("internal", {})
            pending_step = str(internal.get("foundation_step") or "")
            if (
                packet.content.get("review_kind") == "foundation"
                and packet.content.get("status", "pending") == "pending"
                and pending_step in affected
            ):
                self._mark_review(
                    packet,
                    "rejected",
                    dict(packet.content.get("editable") or {}),
                )

        self._auth_store.invalidate_artifacts(
            affected,
            run_id=run_id,
            reason=f"从 {step_key} 退回重新生成",
            from_step=step_key,
        )
        cards = project_initial_status_cards(self._auth_store.load_bundle())
        self._context_store.seed_authority_cards(cards, run_id)
        return {
            "rewound": True,
            "from_step": step_key,
            "affected": affected,
            "snapshot_key": snapshot_key,
            "snapshot_path": str(snapshot_path),
        }

    @staticmethod
    def _foundation_brief_from_packets(packets: list[StagingPacket]) -> str:
        for packet in reversed(packets):
            if packet.content.get("review_kind") != "foundation":
                continue
            brief = str(packet.content.get("internal", {}).get("brief") or "").strip()
            if brief:
                return brief
        return ""

    def layered_asset_catalog(self) -> dict[str, Any]:
        """Return the stable logical-file catalog used by the layer workbench."""
        return self._asset_catalog.list_catalog()

    def layered_asset_detail(self, asset_id: str) -> dict[str, Any]:
        """Return one logical file and its edit/lineage metadata."""
        return self._asset_catalog.get_asset(asset_id)

    def generate_asset_review(self, run_id: str, asset_id: str, content: Any) -> dict[str, Any]:
        """Stage a local logical-file edit without mutating current authority."""
        for packet in self._staging_store.list_all():
            packet_content = dict(packet.content)
            internal = dict(packet_content.get("internal") or {})
            if (
                packet_content.get("review_kind") == "asset_edit"
                and packet_content.get("status", "pending") == "pending"
                and internal.get("asset_id") == asset_id
            ):
                raise ValueError("该分层资产已有待审核版本，请先批准或驳回现有审核稿")
        spec, obj, original = self._asset_catalog.authority_edit_base(asset_id)
        # Validate shape, identity fields, and the merge path before persisting the review.
        self._asset_catalog.merge_authority_edit(
            asset_id,
            content,
            expected_version=obj.version,
        )
        detail = self._asset_catalog.get_asset(asset_id)
        detail.pop("content", None)
        packet = self._save_review_packet(
            run_id=run_id,
            review_kind="asset_edit",
            title=f"微调：{spec.label}",
            staging_type=StagingType.STG_AUTH_PATCH,
            editable={"asset_id": asset_id, "content": content},
            internal={
                "asset_id": asset_id,
                "artifact_key": spec.artifact_key,
                "base_version": obj.version,
                "original_content": original,
                "asset_meta": detail,
            },
        )
        return self._review_payload(packet)

    def generate_workflow_review(
        self,
        *,
        run_id: str,
        stage: str,
        brief: str = "",
        volume_index: int = 1,
        event_index: int = 1,
        from_current: bool = False,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        step: MasterPlanStep | VolumePlanStep | EventPlanStep | None
        steps: list[MasterPlanStep] | list[VolumePlanStep] | list[EventPlanStep]
        with self._progress_sink(progress):
            if from_current:
                return self._review_current_authority(run_id, stage)

            if stage == "foundation":
                # Serialize the read/generate/save window so two concurrent API
                # requests cannot create duplicate pending reviews for one step.
                with self._foundation_generation_lock:
                    packets = sorted(
                        self._staging_store.list_all(), key=lambda item: item.created_at
                    )
                    effective_brief = brief.strip() or self._foundation_brief_from_packets(packets)
                    if not effective_brief:
                        raise ValueError("作品基座需要一段创作意图")
                    if any(
                        packet.content.get("review_kind") == "foundation"
                        and packet.content.get("status", "pending") == "pending"
                        for packet in packets
                    ):
                        raise ValueError("当前作品基座文件仍在等待审核，请先批准或驳回")
                    approved = {
                        key: obj
                        for key in FOUNDATION_STEP_ORDER
                        if (obj := self._auth_store.load_artifact(key)) is not None
                    }
                    next_key = next(
                        (key for key in FOUNDATION_STEP_ORDER if key not in approved),
                        None,
                    )
                    if next_key is None:
                        raise ValueError("作品基座八个文件已经全部批准")
                    profile = detect_complexity_profile(effective_brief)
                    artifact = self._graph_1.generate_step(
                        Graph1Input(
                            run_id=run_id,
                            project_id=self._cfg.project_id,
                            user_brief=effective_brief,
                            commit=False,
                            complexity_profile=profile,
                        ),
                        next_key,
                        approved,
                    )
                    step_index = FOUNDATION_STEP_ORDER.index(next_key) + 1
                    return self._save_auth_review(
                        run_id,
                        "foundation",
                        (
                            f"作品基座 {step_index}/{len(FOUNDATION_STEP_ORDER)} "
                            f"· {FOUNDATION_STEP_LABELS[next_key]}"
                        ),
                        [artifact],
                        extra={
                            "brief": effective_brief,
                            "complexity_profile": profile,
                            "foundation_step": next_key,
                            "step_index": step_index,
                            "step_total": len(FOUNDATION_STEP_ORDER),
                        },
                    )

            if stage == "master_plan":
                with self._master_generation_lock:
                    packets = sorted(
                        self._staging_store.list_all(), key=lambda item: item.created_at
                    )
                    if any(
                        packet.content.get("review_kind") == "master_plan"
                        and packet.content.get("status", "pending") == "pending"
                        for packet in packets
                    ):
                        raise ValueError("当前全书规划文件仍在等待审核，请先批准或驳回")
                    foundation = {
                        key: self._auth_store.load_artifact(key) for key in FOUNDATION_STEP_ORDER
                    }
                    missing = [
                        FOUNDATION_STEP_LABELS[key]
                        for key, artifact in foundation.items()
                        if artifact is None
                    ]
                    if missing:
                        raise ValueError(
                            f"请先批准作品基座全部八个文件；尚缺：{', '.join(missing)}"
                        )
                    spec00 = foundation["spec00"]
                    world_a = foundation["world_a"]
                    cast = foundation["cast"]
                    assert spec00 is not None and world_a is not None and cast is not None
                    current = self._auth_store.load_artifact("longline")
                    current_content = current.content if current is not None else {}
                    step = next_master_plan_step(current_content, cast.content)
                    if step is None:
                        raise ValueError("全书总纲与资产的所有文件已经全部批准")
                    profile = spec00.content.get("complexity_profile", {})
                    generated = self._graph_2.generate_step(
                        Graph2Input(
                            run_id=run_id,
                            project_id=self._cfg.project_id,
                            spec00=spec00,
                            world_a=world_a,
                            cast=cast,
                            commit=False,
                            complexity_profile=profile,
                        ),
                        step.step_id,
                        current_content,
                    )
                    steps = master_plan_steps(cast.content, current_content)
                    step_index = next(
                        index
                        for index, item in enumerate(steps, start=1)
                        if item.step_id == step.step_id
                    )
                    packet = self._save_review_packet(
                        run_id=run_id,
                        review_kind="master_plan",
                        title=(f"全书规划 {step_index}/{len(steps)} · {step.label}"),
                        staging_type=StagingType.STG_AUTH_PATCH,
                        editable={"content": generated},
                        internal={
                            "master_step": step.step_id,
                            "asset_id": step.asset_id,
                            "base_version": current.version if current is not None else 0,
                            "step_index": step_index,
                            "step_total": len(steps),
                            "max_tokens": step.max_tokens(str(profile.get("level") or "medium")),
                            "complexity_profile": profile,
                        },
                    )
                    return self._review_payload(packet)

            if stage == "volume_plan":
                with self._volume_generation_lock:
                    packets = sorted(
                        self._staging_store.list_all(), key=lambda item: item.created_at
                    )
                    if any(
                        packet.content.get("review_kind") == "volume_plan"
                        and packet.content.get("status", "pending") == "pending"
                        for packet in packets
                    ):
                        raise ValueError("当前卷规划文件仍在等待审核，请先批准或驳回")
                    longline = self._load_latest_longline()
                    cast = self._auth_store.load_artifact("cast")
                    if (
                        longline is None
                        or next_master_plan_step(
                            longline.content,
                            cast.content if cast else {},
                        )
                        is not None
                    ):
                        raise ValueError("请先逐文件批准完整的全书总纲与资产")
                    index = max(1, int(volume_index))
                    spec00 = self._auth_store.load_artifact("spec00")
                    events_per_volume = self._events_per_volume(spec00)
                    profile = spec00.content.get("complexity_profile", {}) if spec00 else {}
                    current = self._load_volume_contract(index)
                    current_content = current.content if current is not None else {}
                    step = next_volume_plan_step(current_content, events_per_volume)
                    if step is None:
                        raise ValueError(f"第{index}卷的所有规划文件已经全部批准")
                    generated = self._graph_3.generate_review_step(
                        Graph3Input(
                            run_id=run_id,
                            project_id=self._cfg.project_id,
                            longline=longline,
                            volume_index=index,
                            carryover_context=self._build_volume_carryover_context(
                                self._load_volume_contract(index - 1) if index > 1 else None
                            ),
                            commit=False,
                            complexity_profile=profile,
                            events_per_volume=events_per_volume,
                        ),
                        step,
                        current_content,
                    )
                    steps = volume_plan_steps(events_per_volume)
                    step_index = next(
                        position
                        for position, item in enumerate(steps, start=1)
                        if item.step_id == step.step_id
                    )
                    packet = self._save_review_packet(
                        run_id=run_id,
                        review_kind="volume_plan",
                        title=f"第{index}卷 {step_index}/{len(steps)} · {step.label}",
                        staging_type=StagingType.STG_AUTH_PATCH,
                        editable={"content": generated},
                        internal={
                            "volume_step": step.step_id,
                            "volume_index": index,
                            "asset_id": step.asset_id,
                            "base_version": current.version if current is not None else 0,
                            "step_index": step_index,
                            "step_total": len(steps),
                            "max_tokens": step.max_tokens,
                            "events_per_volume": events_per_volume,
                            "complexity_profile": profile,
                        },
                    )
                    return self._review_payload(packet)

            if stage == "event_plan":
                with self._event_generation_lock:
                    contract = self._load_volume_contract(
                        max(1, int(volume_index))
                    ) or self._auth_store.load_latest("CONTRACT")
                    slots = contract.content.get("event_slots", []) if contract else []
                    index = max(1, int(event_index))
                    if contract is None or index > len(slots):
                        raise ValueError("卷事件队列中没有这个事件")
                    event_slot = self._normalize_volume_slot(slots[index - 1], index)
                    event_id = str(event_slot.get("slot_id") or "")
                    packets = self._staging_store.list_all()
                    if any(
                        packet.content.get("review_kind") == "event_plan"
                        and packet.content.get("status", "pending") == "pending"
                        and (
                            str(packet.content.get("internal", {}).get("event_id") or "")
                            == event_id
                            or int(packet.content.get("internal", {}).get("event_index") or 0)
                            == index
                        )
                        for packet in packets
                    ):
                        raise ValueError("当前事件规划文件仍在等待审核，请先批准或驳回")
                    step = next_event_plan_step(contract.content, event_id)
                    if step is None:
                        raise ValueError("当前事件的五个规划文件已经全部批准；请生成正文草稿")
                    approved_execution = execution_report_from_event_plan(
                        contract.content, event_id
                    )
                    generated, context_package = self._graph_4.generate_review_step(
                        Graph4Input(
                            run_id=run_id,
                            project_id=self._cfg.project_id,
                            event_slot=event_slot,
                            authority_bundle=self._auth_store.load_bundle(),
                            latest_snapshot=self._snapshots_store.load_latest(),
                            plan_only=True,
                        ),
                        step,
                        approved_execution,
                    )
                    steps = event_plan_steps()
                    step_index = next(
                        position
                        for position, item in enumerate(steps, start=1)
                        if item.step_id == step.step_id
                    )
                    packet = self._save_review_packet(
                        run_id=run_id,
                        review_kind="event_plan",
                        title=f"事件 {index} · {step_index}/{len(steps)} · {step.label}",
                        staging_type=StagingType.STG_EVENT,
                        editable={"content": generated},
                        internal={
                            "event_plan_step": step.step_id,
                            "event_id": event_id,
                            "event_index": index,
                            "volume_index": max(1, int(volume_index)),
                            "asset_id": step.asset_id,
                            "base_version": contract.version,
                            "step_index": step_index,
                            "step_total": len(steps),
                            "max_tokens": step.max_tokens,
                            "event_slot": event_slot,
                            "context_package": context_package.model_dump(mode="json"),
                        },
                    )
                    return self._review_payload(packet)

            if stage == "prose":
                with self._event_generation_lock:
                    contract = self._load_volume_contract(
                        max(1, int(volume_index))
                    ) or self._auth_store.load_latest("CONTRACT")
                    slots = contract.content.get("event_slots", []) if contract else []
                    index = max(1, int(event_index))
                    if contract is None or index > len(slots):
                        raise ValueError("卷事件队列中没有这个事件")
                    event_slot = self._normalize_volume_slot(slots[index - 1], index)
                    event_id = str(event_slot.get("slot_id") or "")
                    if next_event_plan_step(contract.content, event_id) is not None:
                        raise ValueError("请先逐文件批准当前事件的五步展开方案")
                    if any(
                        packet.content.get("review_kind") == "prose"
                        and packet.content.get("status", "pending") == "pending"
                        and int(packet.content.get("internal", {}).get("event_index") or 0) == index
                        for packet in self._staging_store.list_all()
                    ):
                        raise ValueError("当前事件正文仍在等待审核，请先批准或驳回")
                    execution_report = execution_report_from_event_plan(contract.content, event_id)
                    out = self._graph_4.run(
                        Graph4Input(
                            run_id=run_id,
                            project_id=self._cfg.project_id,
                            event_slot=event_slot,
                            authority_bundle=self._auth_store.load_bundle(),
                            latest_snapshot=self._snapshots_store.load_latest(),
                            execution_override=execution_report,
                        )
                    )
                    if out.aborted:
                        raise ValueError(out.abort_reason)
                    packet = self._save_review_packet(
                        run_id=run_id,
                        review_kind="prose",
                        title=f"事件 {index} · 正文草稿",
                        staging_type=StagingType.STG_EVENT,
                        editable={"draft_text": out.draft.draft_text},
                        internal={
                            "event_id": event_id,
                            "event_index": index,
                            "volume_index": max(1, int(volume_index)),
                            "event_slot": event_slot,
                            "draft": out.draft.model_dump(mode="json"),
                            "context_package": out.context_package.model_dump(mode="json"),
                            "execution_report": out.execution_report,
                            "budget_report": out.budget_report,
                            "quality_report": out.quality_report,
                            "volume_version": contract.version,
                        },
                    )
                    return self._review_payload(packet)

        raise ValueError(f"不支持生成阶段: {stage}")

    def _review_current_authority(self, run_id: str, stage: str) -> dict[str, Any]:
        if stage == "foundation":
            raise ValueError("作品基座必须在分层资产面板逐文件微调，不能创建八文件整包审核稿")
        elif stage == "master_plan":
            longline = self._load_latest_longline()
            artifacts = [longline] if longline is not None else []
            title = "微调全书总纲与资产"
        elif stage == "volume_plan":
            contract = self._auth_store.load_latest("CONTRACT")
            artifacts = [contract] if contract is not None else []
            title = "微调当前卷纲与事件队列"
        else:
            raise ValueError("只有作品基座、全书总纲和卷纲支持从当前版本创建审核稿")
        if not artifacts:
            raise ValueError("当前阶段还没有可供审核的已批准内容")
        return self._save_auth_review(run_id, stage, title, artifacts, extra={"from_current": True})

    def audit_workflow_review(
        self, staging_id: str, edited: dict[str, Any], run_id: str = ""
    ) -> dict[str, Any]:
        return self._reviews.audit_workflow_review(staging_id, edited, run_id)

    def revise_workflow_review(
        self, staging_id: str, edited: dict[str, Any], feedback: str, run_id: str = ""
    ) -> dict[str, Any]:
        return self._reviews.revise_workflow_review(staging_id, edited, feedback, run_id)

    def approve_workflow_review(
        self, staging_id: str, edited: dict[str, Any], run_id: str = ""
    ) -> dict[str, Any]:
        return self._reviews.approve_workflow_review(staging_id, edited, run_id)

    def reject_workflow_review(self, staging_id: str) -> dict[str, Any]:
        return self._reviews.reject_workflow_review(staging_id)

    def _save_auth_review(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._reviews._save_auth_review(*args, **kwargs)

    def _save_review_packet(self, *args: Any, **kwargs: Any) -> StagingPacket:
        return self._reviews._save_review_packet(*args, **kwargs)

    def _foundation_complexity_level(self, *args: Any, **kwargs: Any) -> str:
        return self._reviews._foundation_complexity_level(*args, **kwargs)

    def _mark_review(self, packet: StagingPacket, status: str, editable: dict[str, Any]) -> None:
        self._reviews._mark_review(packet, status, editable)

    _review_payload = staticmethod(ReviewService._review_payload)

    # ── 舞台引擎：图1 + 图2 + 图3 ────────────────────────────────────────

    def run_stage_engine(
        self,
        run_id: str,
        user_brief: str,
        volume_index: int = 1,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """运行图1 + 图2 + 图3，建立项目权威层基础设施。

        Returns:
            {
                "success": bool,
                "spec00": AuthObject,
                "world_a": AuthObject,
                "world_b": AuthObject,
                "pow_l": AuthObject,
                "pow_s": AuthObject,
                "pow_e": AuthObject,
                "opp_eco": AuthObject,
                "longline": AuthObject,
                "volume_contract": AuthObject,
                "fatigue_report": FatigueReport,
                "aborted": bool,
                "abort_reason": str,
            }
        """
        project_id = self._cfg.project_id
        complexity_profile = detect_complexity_profile(user_brief)
        _logger.info(
            f"stage_engine_start run={run_id} project={project_id} "
            f"complexity={complexity_profile['level']}"
        )

        def emit(event: str, **payload: Any) -> None:
            if progress:
                progress({"event": event, **payload})

        stage_lock = FileLock(self._layout.project_dir / "stage_engine", timeout=0.2)
        try:
            stage_lock.acquire()
        except LockTimeoutError:
            reason = "当前项目已有初始化正在运行，请等待那次运行结束后再启动"
            _logger.warning(f"stage_engine_lock_busy run={run_id} project={project_id}")
            emit("init_failed", graph="lock", reason=reason)
            return {
                "success": False,
                "aborted": True,
                "abort_reason": reason,
            }

        try:
            with self._progress_sink(progress):
                emit("init_start", run_id=run_id, project_id=project_id, volume_index=volume_index)

                # 图1：舞台引擎
                emit("graph_start", graph="graph1", title="图1 舞台引擎")
                g1_out = self._graph_1.run(
                    Graph1Input(
                        run_id=run_id,
                        project_id=project_id,
                        user_brief=user_brief,
                        commit=False,
                        complexity_profile=complexity_profile,
                    )
                )
                if g1_out.aborted:
                    _logger.error(f"stage_engine_aborted_at_graph1 run={run_id}")
                    emit("init_failed", graph="graph1", reason=g1_out.abort_reason)
                    return {
                        "success": False,
                        "aborted": True,
                        "abort_reason": g1_out.abort_reason,
                    }
                emit("graph_done", graph="graph1", title="图1 舞台引擎")

                # 图2：长线骨架
                emit("graph_start", graph="graph2", title="图2 长线骨架")
                g2_out = self._graph_2.run(
                    Graph2Input(
                        run_id=run_id,
                        project_id=project_id,
                        spec00=g1_out.spec00,
                        world_a=g1_out.world_a,
                        cast=g1_out.cast,
                        commit=False,
                        complexity_profile=complexity_profile,
                    )
                )
                if g2_out.aborted:
                    _logger.error(f"stage_engine_aborted_at_graph2 run={run_id}")
                    emit("init_failed", graph="graph2", reason=g2_out.abort_reason)
                    return {
                        "success": False,
                        "aborted": True,
                        "abort_reason": g2_out.abort_reason,
                        "spec00": g1_out.spec00,
                    }
                emit("graph_done", graph="graph2", title="图2 长线骨架")

                # 图3：分卷规划
                emit("graph_start", graph="graph3", title="图3 分卷规划")
                g3_out = self._graph_3.run(
                    Graph3Input(
                        run_id=run_id,
                        project_id=project_id,
                        longline=g2_out.longline,
                        volume_index=volume_index,
                        commit=False,
                        complexity_profile=complexity_profile,
                        events_per_volume=self._events_per_volume(g1_out.spec00),
                    )
                )
                if g3_out.aborted:
                    _logger.error(f"stage_engine_aborted_at_graph3 run={run_id}")
                    emit("init_failed", graph="graph3", reason=g3_out.abort_reason)
                    return {
                        "success": False,
                        "aborted": True,
                        "abort_reason": g3_out.abort_reason,
                        "spec00": g1_out.spec00,
                        "longline": g2_out.longline,
                    }
                emit("graph_done", graph="graph3", title="图3 分卷规划")

                with transaction(self._layout.project_dir):
                    # No authority file is written until every init artifact validates.
                    for field_name in (
                        "spec00",
                        "world_a",
                        "world_b",
                        "pow_l",
                        "pow_s",
                        "pow_e",
                        "opp_eco",
                        "cast",
                    ):
                        setattr(
                            g1_out, field_name, self._auth_store.commit(getattr(g1_out, field_name))
                        )
                    g2_out.longline = self._auth_store.commit(g2_out.longline)
                    assert g3_out.volume_contract is not None
                    g3_out.volume_contract = self._auth_store.commit(g3_out.volume_contract)

                    initial_cards = project_initial_status_cards(
                        [
                            g1_out.spec00,
                            g1_out.world_a,
                            g1_out.world_b,
                            g1_out.pow_l,
                            g1_out.pow_s,
                            g1_out.pow_e,
                            g1_out.cast,
                            g1_out.opp_eco,
                            g2_out.longline,
                            g3_out.volume_contract,
                        ]
                    )
                    card_index = self._context_store.seed_authority_cards(initial_cards, run_id)

            _logger.info(f"stage_engine_done run={run_id}")
            slot_count = (
                len(g3_out.volume_contract.content.get("event_slots", []))
                if g3_out.volume_contract
                else 0
            )
            emit(
                "init_done",
                run_id=run_id,
                main_promise=(g1_out.spec00.content.get("main_promise") if g1_out.spec00 else None),
                event_slots=slot_count,
                status_cards=len(card_index.cards),
            )
            return {
                "success": True,
                "aborted": False,
                "abort_reason": "",
                "spec00": g1_out.spec00,
                "world_a": g1_out.world_a,
                "world_b": g1_out.world_b,
                "pow_l": g1_out.pow_l,
                "pow_s": g1_out.pow_s,
                "pow_e": g1_out.pow_e,
                "opp_eco": g1_out.opp_eco,
                "cast": g1_out.cast,
                "longline": g2_out.longline,
                "volume_contract": g3_out.volume_contract,
                "fatigue_report": g3_out.fatigue_report,
                "status_card_index": card_index,
                "complexity_profile": complexity_profile,
            }
        except Exception as exc:
            reason = f"初始化结构化输出失败：{exc}"
            _logger.exception(f"stage_engine_failed run={run_id}")
            emit("init_failed", graph="validation", reason=reason)
            return {"success": False, "aborted": True, "abort_reason": reason}
        finally:
            stage_lock.release()

    def _restore_contract_latest(self, previous_contract: AuthObject | None, run_id: str) -> None:
        """初始化中途失败时，恢复进入图1前的 CONTRACT.latest，避免坏半成品顶掉好卷契约。"""
        if previous_contract is None:
            return
        self._auth_store.commit(previous_contract)
        _logger.info(
            f"contract_latest_restored run={run_id} restored_object={previous_contract.object_id}"
        )

    # ── 后续卷规划：只跑图3，不重建图1/图2 ───────────────────────────────

    def run_volume_plan(
        self,
        run_id: str,
        volume_index: int,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """承接当前项目状态，只重新规划指定卷的 CONTRACT.event_slots。"""
        project_id = self._cfg.project_id
        volume_index = max(1, int(volume_index))

        def emit(event: str, **payload: Any) -> None:
            if progress:
                progress({"event": event, **payload})

        plan_lock = FileLock(self._layout.project_dir / "volume_plan", timeout=0.2)
        try:
            plan_lock.acquire()
        except LockTimeoutError:
            reason = "当前项目已有卷规划正在运行，请等待那次运行结束后再启动"
            emit("volume_plan_failed", graph="lock", reason=reason)
            return {"success": False, "aborted": True, "abort_reason": reason}

        previous_contract = self._auth_store.load_latest("CONTRACT")
        try:
            longline = self._load_latest_longline()
            if longline is None:
                reason = "未找到长线骨架，请先运行完整初始化（图1→图2→图3）"
                emit("volume_plan_failed", graph="graph2", reason=reason)
                return {"success": False, "aborted": True, "abort_reason": reason}

            carryover_context = self._build_volume_carryover_context(previous_contract)
            spec00 = self._auth_store.load_artifact("spec00")
            complexity_profile = spec00.content.get("complexity_profile", {}) if spec00 else {}
            with self._progress_sink(progress):
                emit(
                    "volume_plan_start",
                    run_id=run_id,
                    project_id=project_id,
                    volume_index=volume_index,
                )
                emit("graph_start", graph="graph3", title=f"图3 第{volume_index}卷规划")
                g3_out = self._graph_3.run(
                    Graph3Input(
                        run_id=run_id,
                        project_id=project_id,
                        longline=longline,
                        volume_index=volume_index,
                        carryover_context=carryover_context,
                        complexity_profile=complexity_profile,
                        events_per_volume=self._events_per_volume(spec00),
                    )
                )
                if g3_out.aborted:
                    self._restore_contract_latest(previous_contract, run_id)
                    emit("volume_plan_failed", graph="graph3", reason=g3_out.abort_reason)
                    return {
                        "success": False,
                        "aborted": True,
                        "abort_reason": g3_out.abort_reason,
                    }
                emit("graph_done", graph="graph3", title=f"图3 第{volume_index}卷规划")

            slot_count = (
                len(g3_out.volume_contract.content.get("event_slots", []))
                if g3_out.volume_contract
                else 0
            )
            emit(
                "volume_plan_done",
                run_id=run_id,
                volume_index=volume_index,
                event_slots=slot_count,
            )
            return {
                "success": True,
                "aborted": False,
                "abort_reason": "",
                "run_id": run_id,
                "volume_index": volume_index,
                "volume_contract": g3_out.volume_contract,
                "fatigue_report": g3_out.fatigue_report,
                "event_slots": slot_count,
            }
        finally:
            plan_lock.release()

    def _load_volume_contract(self, volume_index: int) -> AuthObject | None:
        if volume_index < 1:
            return None
        volume_id = f"vol_{volume_index:03d}"
        artifact = self._auth_store.load_artifact(f"volume_{volume_id}")
        if (
            artifact is not None
            and isinstance(artifact.content, dict)
            and str(artifact.content.get("volume_id")) == volume_id
        ):
            return artifact
        for obj in reversed(self._auth_store.load_history("CONTRACT")):
            content = obj.content if isinstance(obj.content, dict) else {}
            if str(content.get("volume_id")) == volume_id and isinstance(
                content.get("event_slots"), list
            ):
                return obj
        return None

    @staticmethod
    def _events_per_volume(spec00: AuthObject | dict[str, Any] | None) -> int:
        content = spec00.content if isinstance(spec00, AuthObject) else spec00
        if not isinstance(content, dict):
            return 30
        budget = content.get("budget", {})
        if not isinstance(budget, dict):
            return 30
        try:
            return max(1, int(budget.get("events_per_volume", 30)))
        except (TypeError, ValueError):
            return 30

    def _load_latest_longline(self) -> AuthObject | None:
        latest = self._auth_store.load_artifact("longline")
        if latest is not None:
            return latest
        for obj in reversed(self._auth_store.load_history("CONTRACT")):
            content = obj.content if isinstance(obj.content, dict) else {}
            if "event_slots" in content:
                continue
            if "stage_nodes" in content or "dq_promise" in content or "total_stages" in content:
                return obj
        return None

    def _build_volume_carryover_context(
        self, previous_contract: AuthObject | None
    ) -> dict[str, Any]:
        latest_snapshot = self._snapshots_store.load_latest()
        char_obj = self._auth_store.load_artifact("char_state") or self._auth_store.load_artifact(
            "cast"
        )
        ledger_obj = self._auth_store.load_latest("LEDGER")
        chapters = self._publish_store.list_index()[-12:]
        events = self._events_store.list_index()[-12:]
        return {
            "previous_volume_contract": (
                previous_contract.content
                if previous_contract
                and isinstance(previous_contract.content, dict)
                and previous_contract.content.get("event_slots")
                else {}
            ),
            "latest_state": latest_snapshot.model_dump(mode="json") if latest_snapshot else {},
            "char_content": char_obj.content if char_obj else {},
            "ledger_content": ledger_obj.content if ledger_obj else {},
            "recent_events": events,
            "recent_chapters": chapters,
            "published_chapter_count": len(self._publish_store.list_index()),
        }

    # ── 事件写作：图4 + 图E + 图5 ─────────────────────────────────────────

    def run_event_write(
        self,
        run_id: str,
        event_slot: dict[str, Any],
        history_chapter_specs: list[ChapterSpec] | None = None,
    ) -> dict[str, Any]:
        """运行图4生成事件草稿，再交给图E提交，最后图5章节化。

        Args:
            run_id: 运行ID
            event_slot: 来自卷契约的事件槽位规格（EventSlot.dict）
            history_chapter_specs: 历史章节规格（供图5参考）

        Returns:
            {
                "success": bool,
                "draft": EventDraft,
                "event": GraphEOutput,
                "chapter": Graph5Output,
            }
        """
        project_id = self._cfg.project_id
        _logger.info(f"event_write_start run={run_id} slot={event_slot.get('slot_id', '?')}")

        # 加载权威层（BIBLE、CHAR、LEDGER、CONTRACT）
        authority_bundle = self._auth_store.load_bundle()
        latest_snapshot = self._snapshots_store.load_latest()

        # 图4：事件执行
        g4_out = self._graph_4.run(
            Graph4Input(
                run_id=run_id,
                project_id=project_id,
                event_slot=event_slot,
                authority_bundle=authority_bundle,
                latest_snapshot=latest_snapshot,
            )
        )
        if g4_out.aborted:
            _logger.error(f"event_write_aborted_at_graph4 run={run_id}")
            return {
                "success": False,
                "aborted": True,
                "abort_reason": g4_out.abort_reason,
                "quality_report": g4_out.quality_report,
                "quality_attempts": g4_out.quality_attempts,
                "execution_report": getattr(g4_out, "execution_report", {}),
                "context_package": g4_out.context_package,
            }

        draft = g4_out.draft
        event_id = draft.event_id

        # 图E + 图5：提交事件 → 章节化
        pipeline_result = self.run_event_pipeline(
            run_id=run_id,
            event_id=event_id,
            draft=draft,
            history_chapter_specs=history_chapter_specs,
            context_package=g4_out.context_package,
        )

        _logger.info(f"event_write_done run={run_id} event={event_id}")
        committed_draft = pipeline_result.get("draft") or draft
        return {
            "success": pipeline_result["success"],
            "draft": committed_draft,
            "budget_report": g4_out.budget_report,
            "quality_report": g4_out.quality_report,
            "quality_attempts": g4_out.quality_attempts,
            "execution_report": getattr(g4_out, "execution_report", {}),
            "context_package": g4_out.context_package,
            "namecheck_passed": g4_out.namecheck_passed,
            "event": pipeline_result.get("event"),
            "chapter": pipeline_result.get("chapter"),
        }

    # ── 事件蔓生：一个根事件展开为 N 个完整连续事件 ─────────────────────

    def run_event_preview(self, run_id: str, event_slot: dict[str, Any]) -> dict[str, Any]:
        """Generate an event draft into staging without mutating story state."""
        g4_out = self._graph_4.run(
            Graph4Input(
                run_id=run_id,
                project_id=self._cfg.project_id,
                event_slot=event_slot,
                authority_bundle=self._auth_store.load_bundle(),
                latest_snapshot=self._snapshots_store.load_latest(),
            )
        )
        if g4_out.aborted:
            return {
                "success": False,
                "aborted": True,
                "abort_reason": g4_out.abort_reason,
                "quality_report": g4_out.quality_report,
                "execution_report": getattr(g4_out, "execution_report", {}),
                "context_package": g4_out.context_package,
            }

        staging_id = new_staging_id()
        self._staging_store.save(
            StagingPacket(
                staging_id=staging_id,
                run_id=run_id,
                staging_type=StagingType.STG_EVENT,
                content={
                    "event_slot": event_slot,
                    "draft": g4_out.draft.model_dump(mode="json"),
                    "context_package": g4_out.context_package.model_dump(mode="json"),
                    "budget_report": g4_out.budget_report,
                    "quality_report": g4_out.quality_report,
                    "quality_attempts": g4_out.quality_attempts,
                    "execution_report": getattr(g4_out, "execution_report", {}),
                    "namecheck_passed": g4_out.namecheck_passed,
                },
                created_at=utcnow(),
                verified=True,
            )
        )
        return {
            "success": True,
            "review_required": True,
            "staging_id": staging_id,
            "draft": g4_out.draft,
            "context_package": g4_out.context_package,
            "budget_report": g4_out.budget_report,
            "quality_report": g4_out.quality_report,
            "quality_attempts": g4_out.quality_attempts,
            "execution_report": getattr(g4_out, "execution_report", {}),
            "namecheck_passed": g4_out.namecheck_passed,
        }

    @atomic_method
    def approve_event_preview(
        self,
        staging_id: str,
        run_id: str = "",
        draft_text: str | None = None,
    ) -> dict[str, Any]:
        packet = self._staging_store.load_optional(staging_id)
        if packet is None or packet.staging_type != StagingType.STG_EVENT:
            return {"success": False, "abort_reason": "待审核事件不存在或已处理"}
        content = packet.content
        draft = EventDraft.model_validate(content.get("draft", {}))
        if draft_text is not None and draft_text.strip():
            draft = draft.model_copy(
                update={
                    "draft_text": draft_text.strip(),
                    "word_count": len(draft_text.strip()),
                }
            )
        context_package = ContextPackage.model_validate(content.get("context_package", {}))
        result = self.run_event_pipeline(
            run_id=run_id or packet.run_id,
            event_id=draft.event_id,
            draft=draft,
            context_package=context_package,
        )
        result.update(
            {
                "staging_id": staging_id,
                "context_package": context_package,
                "budget_report": content.get("budget_report", {}),
                "quality_report": content.get("quality_report", {}),
                "quality_attempts": content.get("quality_attempts", 0),
                "execution_report": content.get("execution_report", {}),
                "namecheck_passed": content.get("namecheck_passed", True),
            }
        )
        if result.get("success"):
            self._staging_store.delete(staging_id)
        return result

    def reject_event_preview(self, staging_id: str) -> bool:
        if not self._staging_store.exists(staging_id):
            return False
        self._staging_store.delete(staging_id)
        return True

    def run_event_sprout(
        self,
        run_id: str,
        root_event_goal: str,
        *,
        event_count: int | None = None,
        chapter_count: int | None = None,
        result_target: str = "",
        is_key_event: bool = False,
        start_index: int = 1,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """将一个根事件目标展开为 N 个完整事件并逐个写作提交。

        每个事件独立经过图4→图E→图5；事件正文完整生成后再自然切章，
        因而事件数只是蔓生上限，不是章节配额。
        """
        requested_events = event_count if event_count is not None else chapter_count
        total = max(1, min(int(requested_events or 6), 12))
        start = max(1, int(start_index))
        history = self._load_published_chapter_specs()
        previous_summary = ""
        chapters: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        def emit(event: str, **payload: Any) -> None:
            if progress:
                progress({"event": event, **payload})

        emit(
            "sprout_start",
            run_id=run_id,
            project_id=self._cfg.project_id,
            event_count=total,
            total_slots=total,
        )

        for offset in range(total):
            event_index = start + offset
            slot_id = f"sprout_{new_event_id()}"
            event_slot = self._build_sprout_event_slot(
                slot_id=slot_id,
                root_event_goal=root_event_goal,
                result_target=result_target,
                event_index=event_index,
                event_count=total,
                offset=offset,
                previous_summary=previous_summary,
                is_key_event=is_key_event,
            )

            emit(
                "sprout_event_start",
                event_index=event_index,
                event_count=total,
                slot_id=slot_id,
                event_goal=event_slot["event_goal"],
            )

            with self._progress_sink(progress):
                result = self.run_event_write(
                    run_id=run_id,
                    event_slot=event_slot,
                    history_chapter_specs=history,
                )
            if not result.get("success"):
                emit(
                    "sprout_event_failed",
                    event_index=event_index,
                    event_count=total,
                    slot_id=slot_id,
                    reason=result.get("abort_reason", "unknown"),
                )
                return {
                    "success": False,
                    "run_id": run_id,
                    "completed_slots": offset,
                    "completed_events": offset,
                    "event_count": total,
                    "events": events,
                    "chapters": chapters,
                    "abort_reason": result.get("abort_reason", "事件蔓生中断"),
                }

            draft = result.get("draft")
            event_out = result.get("event")
            chapter_out = result.get("chapter")
            chapter_specs = list(getattr(chapter_out, "chapter_specs", []) or [])
            history.extend(chapter_specs)
            previous_summary = self._summarize_sprout_result(draft, event_out)

            event_info = {
                "slot_index": offset + 1,
                "event_index": event_index,
                "slot_id": slot_id,
                "event_id": getattr(draft, "event_id", slot_id),
                "word_count": getattr(draft, "word_count", 0),
                "diff_passed": bool(
                    getattr(getattr(event_out, "diff_report", None), "passed", False)
                ),
                "fix_attempts": getattr(event_out, "fix_attempts", 0),
            }
            chapter_info = [
                {
                    "chapter_id": spec.chapter_id,
                    "chapter_index": spec.chapter_index,
                    "chapter_intent": getattr(spec.chapter_intent, "value", spec.chapter_intent),
                    "title": spec.title,
                }
                for spec in chapter_specs
            ]
            events.append(event_info)
            chapters.extend(chapter_info)

            emit(
                "sprout_event_done",
                **event_info,
                completed_events=offset + 1,
                event_count=total,
                chapters=chapter_info,
            )

        emit(
            "sprout_done",
            run_id=run_id,
            completed_events=total,
            event_count=total,
            events=events,
            chapters=chapters,
        )
        return {
            "success": True,
            "run_id": run_id,
            "completed_slots": total,
            "completed_events": total,
            "event_count": total,
            "events": events,
            "chapters": chapters,
        }

    # ── 按图3规划自动连载整卷 ─────────────────────────────────────────────

    def run_volume_auto(
        self,
        run_id: str,
        *,
        start_index: int = 1,
        max_events: int = 0,
        only_key: bool = False,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """读取图3已规划的事件槽位表（CONTRACT.event_slots），逐槽自动写作提交。

        这是“初始化”与“写作”之间缺失的桥：图3 已经把整卷事件规划好并存入
        CONTRACT 权威对象，本方法直接消费这批槽位，依次跑 图4→图E→图5，
        章节间的状态承接由 _update_auth_from_event + history_chapter_specs 自动完成。

        Args:
            run_id: 运行ID
            start_index: 从第几个槽位开始（1-indexed）
            max_events: 最多写多少个槽位（0 表示写到末尾）
            only_key: 仅写 is_key_event=true 的槽位
            progress: 进度回调，签名 progress({"event": ..., ...})
        """

        def emit(event: str, **payload: Any) -> None:
            if progress:
                progress({"event": event, **payload})

        contract = self._auth_store.load_latest("CONTRACT")
        if contract is None:
            return {
                "success": False,
                "run_id": run_id,
                "completed_slots": 0,
                "events": [],
                "chapters": [],
                "abort_reason": "尚未找到卷契约，请先运行初始化（图1→图2→图3）",
            }

        raw_slots = contract.content.get("event_slots", [])
        slots = [s for s in raw_slots if isinstance(s, dict)]
        if only_key:
            slots = [s for s in slots if s.get("is_key_event")]
        if not slots:
            return {
                "success": False,
                "run_id": run_id,
                "completed_slots": 0,
                "events": [],
                "chapters": [],
                "abort_reason": "卷规划中没有可用的 event_slots，请检查图3输出或重新初始化",
            }

        start = max(1, int(start_index))
        selected = slots[start - 1 :]
        if max_events and max_events > 0:
            selected = selected[: int(max_events)]
        total = len(selected)
        if total == 0:
            return {
                "success": False,
                "run_id": run_id,
                "completed_slots": 0,
                "events": [],
                "chapters": [],
                "abort_reason": f"start_index={start} 超出了规划的事件数（共{len(slots)}个）",
            }

        history = self._load_published_chapter_specs(before_chapter_index=start)
        chapters: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        emit(
            "volume_start",
            run_id=run_id,
            project_id=self._cfg.project_id,
            volume_id=contract.content.get("volume_id", ""),
            chapter_count=total,
            total_planned=len(slots),
        )

        for offset, slot in enumerate(selected):
            slot_index = start + offset
            event_slot = self._normalize_volume_slot(slot, slot_index)
            slot_id = event_slot["slot_id"]

            emit(
                "chapter_start",
                chapter_index=slot_index,
                slot_id=slot_id,
                event_goal=event_slot["event_goal"],
            )

            with self._progress_sink(progress):
                result = self.run_event_write(
                    run_id=run_id,
                    event_slot=event_slot,
                    history_chapter_specs=history,
                )
            if not result.get("success"):
                emit(
                    "chapter_failed",
                    chapter_index=slot_index,
                    slot_id=slot_id,
                    reason=result.get("abort_reason", "unknown"),
                )
                return {
                    "success": False,
                    "run_id": run_id,
                    "completed_slots": offset,
                    "events": events,
                    "chapters": chapters,
                    "abort_reason": result.get("abort_reason", "自动连载中断"),
                }

            draft = result.get("draft")
            event_out = result.get("event")
            chapter_out = result.get("chapter")
            chapter_specs = list(getattr(chapter_out, "chapter_specs", []) or [])
            history.extend(chapter_specs)

            event_info = {
                "slot_index": offset + 1,
                "chapter_index": slot_index,
                "slot_id": slot_id,
                "event_id": getattr(draft, "event_id", slot_id),
                "word_count": getattr(draft, "word_count", 0),
                "diff_passed": bool(
                    getattr(getattr(event_out, "diff_report", None), "passed", False)
                ),
                "fix_attempts": getattr(event_out, "fix_attempts", 0),
            }
            chapter_info = [
                {
                    "chapter_id": spec.chapter_id,
                    "chapter_index": spec.chapter_index,
                    "chapter_intent": getattr(spec.chapter_intent, "value", spec.chapter_intent),
                    "title": spec.title,
                }
                for spec in chapter_specs
            ]
            events.append(event_info)
            chapters.extend(chapter_info)

            emit("chapter_done", **event_info, chapters=chapter_info)

        emit("volume_done", run_id=run_id, events=events, chapters=chapters)
        return {
            "success": True,
            "run_id": run_id,
            "completed_slots": total,
            "events": events,
            "chapters": chapters,
        }

    @staticmethod
    def _normalize_volume_slot(slot: dict[str, Any], slot_index: int) -> dict[str, Any]:
        """把图3规划的事件槽位补齐成图4可消费的 event_slot。

        图3的槽位字段（allowed_changes/forbidden_changes/key_deliverables/
        conflict_form/is_key_event 等）会被图4直接序列化进提示词，这里只补默认值。
        """
        normalized = dict(slot)
        normalized["slot_id"] = slot.get("slot_id") or f"slot_auto_{slot_index:03d}"
        normalized.setdefault("event_goal", f"第{slot_index}个规划事件")
        normalized.setdefault("result_target", f"完成：{normalized['event_goal']}")
        normalized.setdefault("is_key_event", False)
        normalized.setdefault("conflict_form", None)
        normalized.setdefault("key_deliverables", [])
        # 兼容图4/图E习惯的 allowed_delta / forbidden_delta 命名
        normalized.setdefault("allowed_delta", slot.get("allowed_changes", []))
        normalized.setdefault("forbidden_delta", slot.get("forbidden_changes", []))
        return normalized

    def _load_published_chapter_specs(
        self, before_chapter_index: int | None = None
    ) -> list[ChapterSpec]:
        latest_by_index: dict[int, tuple[str, ChapterCommitRecord]] = {}
        for row in self._publish_store.list_index():
            cid = row.get("chapter_id")
            if not cid:
                continue
            meta = self._publish_store.load_meta_optional(cid)
            if not meta:
                continue
            chapter_index = int(getattr(meta, "chapter_index", row.get("chapter_index", 0)) or 0)
            if before_chapter_index is not None and chapter_index >= before_chapter_index:
                continue
            latest_by_index[chapter_index] = (cid, meta)

        specs: list[ChapterSpec] = []
        for chapter_index in sorted(latest_by_index):
            cid, meta = latest_by_index[chapter_index]
            specs.append(
                ChapterSpec.model_construct(
                    chapter_id=cid,
                    chapter_index=chapter_index,
                    chapter_intent=getattr(meta, "chapter_intent", "Advance"),
                )
            )
        return specs

    @staticmethod
    def _build_sprout_event_slot(
        *,
        slot_id: str,
        root_event_goal: str,
        result_target: str,
        event_index: int,
        event_count: int,
        offset: int,
        previous_summary: str,
        is_key_event: bool,
    ) -> dict[str, Any]:
        phase_names = [
            "开场钩子与不稳定因素",
            "压力升级与第一处代价",
            "信息差扩大与误判",
            "正面碰撞与资源受限",
            "中段反转与新债生成",
            "短暂收束与关系迁移",
            "对手反制与局势翻面",
            "主角选择与代价落地",
            "清算前夜与最后阻力",
            "阶段清算与下一事件钩子",
        ]
        progress = offset / max(1, event_count - 1)
        phase_index = round(progress * (len(phase_names) - 1))
        phase = phase_names[phase_index]
        if progress <= 0.2:
            arc_layer = "建立层"
        elif progress <= 0.55:
            arc_layer = "升级层"
        elif progress <= 0.8:
            arc_layer = "反转层"
        else:
            arc_layer = "兑现层"
        goal = (
            f"{root_event_goal}\n"
            f"本次为根事件蔓生出的第{offset + 1}/{event_count}个完整事件，事件序号为{event_index}。"
            f"本事件位于{arc_layer}，职责：{phase}。"
        )
        if previous_summary:
            goal += f"\n必须承接上一段结果：{previous_summary}"
        return {
            "slot_id": slot_id,
            "event_goal": goal,
            "result_target": result_target or f"完成第{offset + 1}个蔓生事件：{phase}",
            "is_key_event": is_key_event or phase_index in {4, 7, 9},
            "conflict_form": phase,
            "key_deliverables": [
                "本事件必须形成一个可见变化点，并完整展开其触发、选择、后果与余波",
                "至少展开两个有进入、互动、升级和后果的完整场景单元",
                "至少一名配角或对手根据自身目标主动行动，并产生可见反应链",
                "场景或势力压力必须通过物件、人员、资源、命令或制度限制具体显形",
                "事件结尾必须留下后续驱动力，但不得为了制造章末钩子截断当前场景",
                "不得提前完成根事件清算"
                if offset < event_count - 1
                else "完成本轮根事件的阶段性清算",
            ],
            "forbidden_delta": [
                "不得跳过上一段造成的状态变化",
                "不得突然解决根事件的核心矛盾"
                if offset < event_count - 1
                else "不得留下无解释的核心状态跳变",
            ],
            "allowed_delta": [
                "允许推进信息、权力或亲密关系中的至少一项",
                "允许制造新债，但必须登记可回收窗口",
            ],
            "expansion_layers": {
                "plot": "推进当前阶段的因果节点，并展示触发、阻力、选择和后果",
                "character": "让主角、配角或对手之间至少发生一次双向关系反应",
                "scene": "使用可互动空间、物件和感官变化承载行动，不得用概述跳过过程",
                "faction": "若势力介入，必须通过成员、资源、命令、规则或声望压力落地",
                "aftermath": "在事件结束前展示余波和状态留痕，而不是冲突结束即切断",
            },
            "required_card_focus": {
                "plot": ["总事件当前阶段", "上一段未完成的因果或债务"],
                "character": ["本事件实际行动的主角、配角和对手"],
                "scene": ["本事件所需主要场景及其可互动限制"],
                "faction": ["仅在实际施加人员、资源、命令或制度压力时读取"],
            },
            "sprout": {
                "root_event_goal": root_event_goal,
                "event_index": event_index,
                "slot_index": offset + 1,
                "slot_count": event_count,
                "arc_layer": arc_layer,
                "phase_index": phase_index,
                "phase": phase,
                "previous_summary": previous_summary,
                "natural_chapterization": True,
                "scene_unit_target": 3 if is_key_event or phase_index in {4, 7, 9} else 2,
                "hierarchy": ["根事件", arc_layer, f"第{offset + 1}个事件", "场景单元", "场景节拍"],
            },
        }

    @staticmethod
    def _summarize_sprout_result(draft: EventDraft | None, event_out: GraphEOutput | None) -> str:
        if event_out and getattr(event_out, "observed_delta", None):
            summary = getattr(event_out.observed_delta, "result_state_summary", "")
            if summary:
                return str(summary)[:600]
        if draft and draft.draft_text:
            text = " ".join(draft.draft_text.split())
            return text[:600]
        return ""

    # ── 事件流水线：图E + 图5 ─────────────────────────────────────────────

    @atomic_method
    def run_event_pipeline(
        self,
        run_id: str,
        event_id: str,
        draft: EventDraft,
        history_chapter_specs: list[ChapterSpec] | None = None,
        volume_contract: VolumeContract | None = None,
        context_package: ContextPackage | None = None,
    ) -> dict[str, Any]:
        """执行完整事件提交流水线（图E → 图5）。

        Returns:
            {
                "event": GraphEOutput,
                "chapter": Graph5Output,
                "success": bool,
            }
        """
        bible_auth = self._auth_store.load_artifact("spec00") or self._auth_store.load_latest(
            "BIBLE"
        )

        # 图E
        e_out = self._graph_e.run(
            GraphEInput(
                run_id=run_id,
                event_id=event_id,
                draft=draft,
                bible_auth=bible_auth,
                context_package=context_package,
            )
        )
        if e_out.aborted:
            _logger.error(f"event_pipeline_aborted event={event_id}")
            return {"event": e_out, "chapter": None, "success": False}

        # 图E提交后先更新可重建的状态卡索引，再增量更新 CHAR / LEDGER。
        self._context_store.apply_event_delta(e_out.observed_delta, event_id)
        self._update_auth_from_event(e_out, event_id, run_id)

        committed_draft = EventDraft.model_construct(
            event_id=event_id,
            run_id=run_id,
            draft_text=e_out.event_record.draft_text,
            blocks=e_out.event_record.blocks,
            word_count=len(e_out.event_record.draft_text or ""),
        )

        # 图5
        c_out = self._graph_5.run(
            Graph5Input(
                run_id=run_id,
                event_id=event_id,
                draft=committed_draft,
                history_chapter_specs=history_chapter_specs or [],
                volume_contract=volume_contract,
                project_id=self._cfg.project_id,
            )
        )

        _logger.info(f"event_pipeline_done event={event_id} chapters={len(c_out.chapter_specs)}")
        return {"event": e_out, "chapter": c_out, "draft": committed_draft, "success": True}

    # ── 图E后权威层增量更新 ──────────────────────────────────────────────

    def _update_auth_from_event(self, e_out: GraphEOutput, event_id: str, run_id: str) -> None:
        """将图E提交后的 ObservedDelta 增量更新到 CHAR_BIBLE 和 LEDGER。"""
        from novelwb.utils.timeutil import utcnow

        delta = e_out.observed_delta
        project_id = self._cfg.project_id
        now = utcnow()

        # 更新 CHAR（追加新实体 + 合并人物当前状态）
        char_obj = self._auth_store.load_artifact("char_state")
        if char_obj and char_obj.content.get("last_updated_by_event") == event_id:
            return
        if char_obj:
            content = dict(char_obj.content)
            object_id = char_obj.object_id
            version = char_obj.version + 1
            created_at = char_obj.created_at
            object_type = char_obj.object_type
        else:
            content = {}
            cast_obj = self._auth_store.load_artifact("cast")
            content = dict(cast_obj.content) if cast_obj else {}
            object_id = "char_state"
            version = 1
            created_at = now
            object_type = AuthObjectType.CHAR

        existing: list[Any] = list(content.get("characters", []))
        existing_names = {str(e).split("（")[0].split("(")[0].strip() for e in existing}
        added = 0
        for entity in delta.new_entities:
            name = str(entity).split("（")[0].split("(")[0].strip()
            if name and name not in existing_names:
                existing.append(entity)
                existing_names.add(name)
                added += 1
        if existing:
            content["characters"] = existing

        self._merge_character_state_content(content, delta.state_after, event_id)
        content["last_updated_by_event"] = event_id
        content["latest_state_snapshot_key"] = delta.state_after.snapshot_key
        content["latest_state_summary"] = delta.result_state_summary
        self._auth_store.commit(
            AuthObject(
                object_id=object_id,
                project_id=project_id,
                object_type=object_type,
                version=version,
                content=content,
                created_at=created_at,
                updated_at=now,
                committed_by_run_id=run_id,
            )
        )
        _logger.info(f"char_updated event={event_id} added={added}")

        # 更新 LEDGER（追加开放线程 + 动量债）
        ledger_obj = self._auth_store.load_latest("LEDGER")
        if ledger_obj and (delta.open_threads_update or delta.momentum_debt_delta):
            content = dict(ledger_obj.content)
            open_threads: list[Any] = list(content.get("open_threads", []))
            new_threads = [t for t in delta.open_threads_update if t not in open_threads]
            open_threads.extend(new_threads)
            content["open_threads"] = open_threads
            if delta.momentum_debt_delta:
                content["momentum_debt"] = (
                    content.get("momentum_debt", 0) + delta.momentum_debt_delta
                )
            content["last_updated_by_event"] = event_id
            self._auth_store.commit(
                AuthObject(
                    object_id=ledger_obj.object_id,
                    project_id=project_id,
                    object_type=ledger_obj.object_type,
                    version=ledger_obj.version + 1,
                    content=content,
                    created_at=ledger_obj.created_at,
                    updated_at=now,
                    committed_by_run_id=run_id,
                )
            )
            _logger.info(
                f"ledger_updated event={event_id} threads={len(new_threads)} "
                f"debt_delta={delta.momentum_debt_delta}"
            )

    @staticmethod
    def _merge_character_state_content(
        content: dict[str, Any], state_after: StateSnapshot, event_id: str
    ) -> None:
        states_raw = content.get("character_states", {})
        states: dict[str, Any] = dict(states_raw) if isinstance(states_raw, dict) else {}

        if state_after.entity_states:
            # 群像模式：所有被事件触碰的实体按同一规则增量合并，不设主角特权。
            for entity_id, entity_state in state_after.entity_states.items():
                key = str(entity_id).strip()
                if not key or not isinstance(entity_state, dict):
                    continue
                record = dict(states.get(key, {}) or {})
                record.update(entity_state)
                record["last_event_id"] = event_id
                record["snapshot_key"] = state_after.snapshot_key
                states[key] = record
        else:
            # 兼容旧快照；新提示词应优先输出 entity_states。
            protagonist = dict(states.get("protagonist", {}) or {})
            protagonist["last_event_id"] = event_id
            protagonist["snapshot_key"] = state_after.snapshot_key
            if state_after.location:
                protagonist["location"] = state_after.location
            if state_after.time_in_story:
                protagonist["time_in_story"] = state_after.time_in_story
            if state_after.resources:
                protagonist["resources"] = state_after.resources
            if state_after.hp:
                protagonist["hp"] = (
                    state_after.hp.get("protagonist")
                    or state_after.hp.get("主角")
                    or state_after.hp
                )
            if state_after.ability_boundary:
                protagonist["ability_boundary"] = state_after.ability_boundary
            if state_after.open_threads:
                protagonist["open_threads"] = state_after.open_threads
            if state_after.result_state_summary:
                protagonist["state_summary"] = state_after.result_state_summary
            states["protagonist"] = protagonist

        for name, relationship in state_after.relationship_state.items():
            key = str(name).strip()
            if not key:
                continue
            record = dict(states.get(key, {}) or {})
            record["last_event_id"] = event_id
            record["snapshot_key"] = state_after.snapshot_key
            record["relationship_state"] = relationship
            states[key] = record

        content["character_states"] = states
        # 状态卡属于可重建的阅读投影，由 ContextStore 独立维护；CHAR 只保存人物真值。
        current_state = state_after.model_dump(mode="json")
        current_state.pop("reading_focus", None)
        current_state.pop("status_cards", None)
        content["current_state"] = current_state
        content["last_context_fingerprint"] = state_after.context_fingerprint

    # ── 权威提交流水线：图S ───────────────────────────────────────────────

    def run_auth_pipeline(
        self,
        run_id: str,
        staging_packet: StagingPacket,
    ) -> GraphSOutput:
        """执行权威提交流水线（图S）。"""
        return self._graph_s.run(
            GraphSInput(
                run_id=run_id,
                staging_packet=staging_packet,
            )
        )

    # ── 章节许可：图P ─────────────────────────────────────────────────────

    def run_chapter_license(
        self,
        run_id: str,
        event_id: str,
        chapter_index: int,
        input_pack: dict[str, Any] | None = None,
        history: list[ChapterSpec] | None = None,
    ) -> GraphPOutput:
        """执行章节许可（图P）。"""
        return self._graph_p.run(
            GraphPInput(
                run_id=run_id,
                event_id=event_id,
                chapter_index=chapter_index,
                input_pack=input_pack or {},
                history_chapter_specs=history or [],
            )
        )

    # ── 回归测试：图6 ─────────────────────────────────────────────────────

    def run_regression(
        self,
        run_id: str = "",
        test_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """运行回归测试套件（图6）。

        Returns:
            {"report": RegressionReport, "passed": bool}
        """
        event_records = (
            self._events_store.list_by_run(run_id)
            if run_id
            else [
                self._events_store.load(row["event_id"]) for row in self._events_store.list_index()
            ]
        )
        chapter_specs_raw = self._publish_store.list_index()
        chapter_specs: list[ChapterSpec] = []
        for row in chapter_specs_raw:
            cid = row.get("chapter_id")
            if cid:
                meta = self._publish_store.load_meta_optional(cid)
                if meta:
                    chapter_specs.append(
                        ChapterSpec.model_construct(
                            chapter_id=cid,
                            chapter_index=row.get("chapter_index", 0),
                            chapter_intent=getattr(meta, "chapter_intent", "Advance"),
                        )
                    )

        bible_auth = self._auth_store.load_artifact("spec00") or self._auth_store.load_latest(
            "BIBLE"
        )
        ctx = RegressionContext(
            run_id=run_id,
            project_id=self._cfg.project_id,
            event_records=event_records,
            chapter_specs=chapter_specs,
            bible_auth=bible_auth,
            test_types=test_types or ["prose", "mechanic", "boundary", "chapter"],
        )
        report = self._regression.run(ctx)
        return {"report": report, "passed": report.passed}
