"""流水线执行路由 /projects/{project_id}/pipeline。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from novelwb.api.deps import get_orchestrator, ok, require_project
from novelwb.core.schemas.domain_models import EventDraft
from novelwb.engine.context_compiler import ContextCompiler
from novelwb.engine.task_service import tasks as tasks
from novelwb.utils.ids import new_event_id, new_run_id

router = APIRouter(
    prefix="/projects/{project_id}/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(require_project)],
)


class RunEventBody(BaseModel):
    draft_text: str
    event_id: str = ""
    run_id: str = ""


class RunAuthBody(BaseModel):
    staging_id: str
    run_id: str = ""


class InitNovelBody(BaseModel):
    brief: str
    volume_index: int = 1
    run_id: str = ""


class PlanVolumeBody(BaseModel):
    volume_index: int = 2
    run_id: str = ""


class WriteEventBody(BaseModel):
    event_goal: str
    result_target: str = ""
    slot_id: str = ""
    run_id: str = ""
    is_key_event: bool = False


class ReviewEventBody(BaseModel):
    staging_id: str
    run_id: str = ""
    draft_text: str | None = None


class SproutEventBody(BaseModel):
    root_event_goal: str
    event_count: int | None = None
    chapter_count: int | None = None  # Legacy alias; event_count takes precedence.
    result_target: str = ""
    run_id: str = ""
    start_index: int = 1
    is_key_event: bool = False


class AutoVolumeBody(BaseModel):
    start_index: int = 1
    max_events: int = 0
    only_key: bool = False
    run_id: str = ""


class WorkflowGenerateBody(BaseModel):
    stage: str
    brief: str = ""
    volume_index: int = 1
    event_index: int = 1
    from_current: bool = False
    run_id: str = ""


class WorkflowReviewBody(BaseModel):
    editable: dict[str, Any] = Field(default_factory=dict)
    run_id: str = ""


class WorkflowRevisionBody(BaseModel):
    editable: dict[str, Any] = Field(default_factory=dict)
    feedback: str = Field(min_length=1, max_length=8000)
    run_id: str = ""


class FoundationRewindBody(BaseModel):
    step_key: str
    run_id: str = ""


class AssetReviewBody(BaseModel):
    content: Any
    run_id: str = ""


# SSE 防缓冲响应头：尽量让中间代理/反代不要缓冲流式响应
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


class StartRunBody(BaseModel):
    run_id: str = ""
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)


def _start_run(project_id: str, run_id: str, kind: str, params: dict[str, Any]) -> dict[str, Any]:
    orch = get_orchestrator(project_id)
    layout = require_project(project_id)
    rid = run_id or new_run_id()
    models: dict[str, type[BaseModel]] = {
        "workflow": WorkflowGenerateBody,
        "auto-volume": AutoVolumeBody,
        "plan-volume": PlanVolumeBody,
        "init-novel": InitNovelBody,
        "sprout": SproutEventBody,
    }
    if kind not in models:
        raise HTTPException(422, "未知运行类型")
    try:
        body = models[kind].model_validate(params)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    clean = body.model_dump(exclude={"run_id"})

    def work(progress: Any) -> dict[str, Any]:
        if kind == "workflow":
            return {"review": orch.generate_workflow_review(run_id=rid, progress=progress, **clean)}
        if kind == "auto-volume":
            return {"result": orch.run_volume_auto(run_id=rid, progress=progress, **clean)}
        if kind == "plan-volume":
            return {"result": _plain_result(orch.run_volume_plan(rid, progress=progress, **clean))}
        if kind == "init-novel":
            return {"result": _plain_result(orch.run_stage_engine(rid, progress=progress, **clean))}
        return {"result": orch.run_event_sprout(run_id=rid, progress=progress, **clean)}

    try:
        return tasks.start(layout, rid, kind, clean, work)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


def _plain_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if isinstance(value, (str, int, float, bool, list, dict, type(None)))
    }


@router.post("/runs")
def start_run(project_id: str, body: StartRunBody) -> dict[str, Any]:
    return ok(_start_run(project_id, body.run_id, body.kind, body.params))


@router.get("/runs")
def list_runs(project_id: str) -> dict[str, Any]:
    return ok(tasks.list(require_project(project_id)))


@router.get("/runs/{run_id}")
def get_run(project_id: str, run_id: str) -> dict[str, Any]:
    try:
        return ok(tasks.get(require_project(project_id), run_id))
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/cancel")
def cancel_run(project_id: str, run_id: str) -> dict[str, Any]:
    try:
        return ok(tasks.cancel(require_project(project_id), run_id))
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/events")
def run_events(
    project_id: str,
    run_id: str,
    after: int = Query(0, ge=0),
    last_event_id: str | None = Header(None),
) -> StreamingResponse:
    layout = require_project(project_id)
    try:
        tasks.get(layout, run_id)
        cursor = max(after, int(last_event_id or 0))
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return StreamingResponse(
        tasks.events(layout, run_id, cursor), media_type="text/event-stream", headers=_SSE_HEADERS
    )


def _legacy_stream(
    project_id: str, run_id: str, kind: str, params: dict[str, Any]
) -> StreamingResponse:
    state = _start_run(project_id, run_id, kind, params)
    return StreamingResponse(
        tasks.events(require_project(project_id), state["run_id"]),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


def _event_slot(body: WriteEventBody) -> dict[str, Any]:
    slot_id = body.slot_id or f"slot_{new_event_id()}"
    return {
        "slot_id": slot_id,
        "event_goal": body.event_goal,
        "result_target": body.result_target or f"完成：{body.event_goal}",
        "is_key_event": body.is_key_event,
        "conflict_form": None,
        "key_deliverables": [],
        "forbidden_delta": [],
        "allowed_delta": [],
    }


def _summarize_write_result(run_id: str, result: dict[str, Any]) -> dict[str, Any]:
    draft = result.get("draft")
    e_out = result.get("event")
    c_out = result.get("chapter")
    context_package = result.get("context_package")
    observed_delta = getattr(e_out, "observed_delta", None)
    selected_cards = getattr(context_package, "selected_cards", []) or []
    selected_sources = [
        *(getattr(context_package, "protected_sources", []) or []),
        *(getattr(context_package, "selected_sources", []) or []),
    ]
    return {
        "run_id": run_id,
        "event_id": getattr(draft, "event_id", None),
        "word_count": getattr(draft, "word_count", 0),
        "namecheck_passed": result.get("namecheck_passed", True),
        "diff_passed": bool(getattr(getattr(e_out, "diff_report", None), "passed", False)),
        "fix_attempts": getattr(e_out, "fix_attempts", 0),
        "budget_report": result.get("budget_report", {}),
        "quality_report": result.get("quality_report", {}),
        "quality_attempts": result.get("quality_attempts", 0),
        "execution_report": result.get("execution_report", {}),
        "context_fingerprint": getattr(context_package, "fingerprint", None),
        "context_summary": {
            "focus": getattr(context_package, "focus", ""),
            "estimated_tokens": getattr(context_package, "estimated_tokens", 0),
            "token_budget": getattr(context_package, "token_budget", 0),
            "sources": [
                {
                    "source_id": source.source_id,
                    "authority": source.authority,
                    "reason": source.reason,
                    "protected": source.protected,
                }
                for source in selected_sources
            ],
            "cards": [
                {
                    "card_id": item.card.card_id,
                    "card_name": item.card.card_name,
                    "card_type": item.card.card_type.value,
                    "reason": item.reason,
                    "priority": item.priority.value,
                }
                for item in selected_cards
            ],
        },
        "state_writeback": (
            {
                "summary": observed_delta.result_state_summary,
                "changed_items": observed_delta.changed_items,
                "new_entities": observed_delta.new_entities,
                "retired_entities": observed_delta.retired_entities,
                "narrative_line_updates": observed_delta.narrative_line_updates,
                "entity_agenda_updates": observed_delta.entity_agenda_updates,
                "asset_lifecycle_updates": observed_delta.asset_lifecycle_updates,
                "timeline_updates": observed_delta.timeline_updates,
                "plan_adjustment_requests": observed_delta.plan_adjustment_requests,
            }
            if observed_delta
            else {}
        ),
        "chapters_generated": len(getattr(c_out, "chapter_specs", []) or []),
        "chapters": [
            spec.model_dump(mode="json") for spec in (getattr(c_out, "chapter_specs", []) or [])
        ],
    }


@router.post("/init-novel")
def init_novel(project_id: str, body: InitNovelBody) -> dict[str, Any]:
    """Run Graph1+Graph2+Graph3 to establish project authority layers."""
    orch = get_orchestrator(project_id)
    run_id = body.run_id or new_run_id()
    result = orch.run_stage_engine(run_id, body.brief, volume_index=body.volume_index)
    if not result.get("success"):
        raise HTTPException(422, detail=result.get("abort_reason", "stage engine failed"))

    spec00 = result.get("spec00")
    longline = result.get("longline")
    volume_contract = result.get("volume_contract")
    return ok(
        {
            "run_id": run_id,
            "success": True,
            "spec00_id": spec00.object_id if spec00 else None,
            "longline_id": longline.object_id if longline else None,
            "volume_contract_id": volume_contract.object_id if volume_contract else None,
            "main_promise": spec00.content.get("main_promise") if spec00 else None,
            "volume_index": body.volume_index,
        }
    )


@router.get("/init-novel/stream")
def init_novel_stream(
    project_id: str,
    brief: str = Query(...),
    volume_index: int = Query(1, ge=1),
    run_id: str = "",
) -> StreamingResponse:
    return _legacy_stream(
        project_id, run_id, "init-novel", {"brief": brief, "volume_index": volume_index}
    )


@router.post("/plan-volume")
def plan_volume(project_id: str, body: PlanVolumeBody) -> dict[str, Any]:
    """承接当前状态，只运行图3规划指定卷。"""
    orch = get_orchestrator(project_id)
    run_id = body.run_id or new_run_id()
    result = orch.run_volume_plan(run_id, volume_index=body.volume_index)
    if not result.get("success"):
        raise HTTPException(422, detail=result.get("abort_reason", "volume plan failed"))
    contract = result.get("volume_contract")
    return ok(
        {
            "run_id": run_id,
            "success": True,
            "volume_index": body.volume_index,
            "event_slots": result.get("event_slots", 0),
            "volume_contract_id": (contract.object_id if contract is not None else None),
        }
    )


@router.get("/plan-volume/stream")
def plan_volume_stream(
    project_id: str,
    volume_index: int = Query(2, ge=1),
    run_id: str = "",
) -> StreamingResponse:
    return _legacy_stream(project_id, run_id, "plan-volume", {"volume_index": volume_index})


@router.post("/event")
def run_event_pipeline(project_id: str, body: RunEventBody) -> dict[str, Any]:
    """同步执行事件提交流水线（图E + 图5）。"""
    orch = get_orchestrator(project_id)
    run_id = body.run_id or new_run_id()
    event_id = body.event_id or new_event_id()

    draft = EventDraft.model_construct(
        event_id=event_id,
        run_id=run_id,
        draft_text=body.draft_text,
        blocks=[],
        word_count=len(body.draft_text),
    )
    result = orch.run_event_pipeline(run_id, event_id, draft)
    if not result["success"]:
        raise HTTPException(422, detail="事件流水线执行失败，请查看日志")

    e_out = result["event"]
    c_out = result["chapter"]
    return ok(
        {
            "run_id": run_id,
            "event_id": event_id,
            "fix_attempts": e_out.fix_attempts,
            "chapters": len(c_out.chapter_specs) if c_out else 0,
            "diff_passed": e_out.diff_report.passed,
        }
    )


@router.post("/write-event")
def write_event(project_id: str, body: WriteEventBody) -> dict[str, Any]:
    """Run Graph4+GraphE+Graph5 from an event goal."""
    orch = get_orchestrator(project_id)
    run_id = body.run_id or new_run_id()
    result = orch.run_event_write(run_id, _event_slot(body))
    if not result.get("success"):
        raise HTTPException(422, detail=result.get("abort_reason", "event write failed"))
    return ok(_summarize_write_result(run_id, result))


@router.post("/write-event/preview")
def preview_event(project_id: str, body: WriteEventBody) -> dict[str, Any]:
    """Generate a reviewable draft without committing event or state changes."""
    orch = get_orchestrator(project_id)
    run_id = body.run_id or new_run_id()
    result = orch.run_event_preview(run_id, _event_slot(body))
    if not result.get("success"):
        raise HTTPException(422, detail=result.get("abort_reason", "event preview failed"))
    payload = _summarize_write_result(run_id, result)
    draft = result.get("draft")
    payload.update(
        {
            "staging_id": result.get("staging_id"),
            "review_required": True,
            "draft_text": getattr(draft, "draft_text", ""),
            "compiled_context": ContextCompiler.render_input_context(result["context_package"]),
        }
    )
    return ok(payload)


@router.post("/write-event/approve")
def approve_event(project_id: str, body: ReviewEventBody) -> dict[str, Any]:
    """Commit a staged draft through GraphE and Graph5."""
    orch = get_orchestrator(project_id)
    result = orch.approve_event_preview(body.staging_id, body.run_id, body.draft_text)
    if not result.get("success"):
        raise HTTPException(422, detail=result.get("abort_reason", "event approval failed"))
    return ok(_summarize_write_result(body.run_id, result))


@router.post("/write-event/reject")
def reject_event(project_id: str, body: ReviewEventBody) -> dict[str, Any]:
    """Discard a staged draft without changing authority or state."""
    orch = get_orchestrator(project_id)
    if not orch.reject_event_preview(body.staging_id):
        raise HTTPException(404, detail="staged event not found")
    return ok({"staging_id": body.staging_id, "rejected": True})


@router.post("/sprout")
def sprout_event(project_id: str, body: SproutEventBody) -> dict[str, Any]:
    """Expand one root event into complete events, then chapterize each naturally."""
    orch = get_orchestrator(project_id)
    run_id = body.run_id or new_run_id()
    result = orch.run_event_sprout(
        run_id=run_id,
        root_event_goal=body.root_event_goal,
        event_count=body.event_count,
        chapter_count=body.chapter_count,
        result_target=body.result_target,
        start_index=body.start_index,
        is_key_event=body.is_key_event,
    )
    if not result.get("success"):
        raise HTTPException(422, detail=result.get("abort_reason", "event sprout failed"))
    return ok(result)


@router.post("/auto-volume")
def auto_volume(project_id: str, body: AutoVolumeBody) -> dict[str, Any]:
    """按图3已规划的事件槽位表，自动连载整卷（图4→图E→图5 逐槽循环）。"""
    orch = get_orchestrator(project_id)
    run_id = body.run_id or new_run_id()
    result = orch.run_volume_auto(
        run_id=run_id,
        start_index=body.start_index,
        max_events=body.max_events,
        only_key=body.only_key,
    )
    if not result.get("success"):
        raise HTTPException(422, detail=result.get("abort_reason", "auto volume failed"))
    return ok(result)


@router.get("/auto-volume/stream")
def auto_volume_stream(
    project_id: str,
    start_index: int = Query(1, ge=1),
    max_events: int = Query(0, ge=0),
    only_key: bool = False,
    run_id: str = "",
) -> StreamingResponse:
    return _legacy_stream(
        project_id,
        run_id,
        "auto-volume",
        {"start_index": start_index, "max_events": max_events, "only_key": only_key},
    )


@router.get("/sprout/stream")
def sprout_event_stream(
    project_id: str,
    root_event_goal: str = Query(...),
    event_count: int | None = Query(None, ge=1, le=12),
    chapter_count: int | None = Query(None, ge=1, le=30),
    result_target: str = "",
    run_id: str = "",
    start_index: int = Query(1, ge=1),
    is_key_event: bool = False,
) -> StreamingResponse:
    return _legacy_stream(
        project_id,
        run_id,
        "sprout",
        {
            "root_event_goal": root_event_goal,
            "event_count": event_count,
            "chapter_count": chapter_count,
            "result_target": result_target,
            "start_index": start_index,
            "is_key_event": is_key_event,
        },
    )


@router.get("/state")
def get_current_state(project_id: str) -> dict[str, Any]:
    """Return latest CHAR authority content and current state snapshot."""
    from collections import defaultdict

    from novelwb.storage import AuthStore, ContextStore, SnapshotsStore

    layout = require_project(project_id)
    auth = AuthStore(layout)
    snapshots = SnapshotsStore(layout)
    contexts = ContextStore(layout)
    char_obj = auth.load_artifact("char_state") or auth.load_artifact("cast")
    latest = snapshots.load_latest()
    card_index = contexts.load_card_index()
    cards_by_type = defaultdict(list)
    for card in card_index.cards:
        cards_by_type[f"{card.card_type.value}_cards"].append(card.model_dump(mode="json"))
    latest_context = contexts.load_package(latest.event_id) if latest and latest.event_id else None
    return ok(
        {
            "char": char_obj.content if char_obj else {},
            "char_version": char_obj.version if char_obj else 0,
            "latest_state": latest.model_dump(mode="json") if latest else None,
            "status_cards": dict(cards_by_type),
            "card_index_version": card_index.index_version,
            "latest_context": (
                {
                    "context_id": latest_context.context_id,
                    "fingerprint": latest_context.fingerprint,
                    "focus": latest_context.focus,
                    "sources": [
                        {
                            "source_id": source.source_id,
                            "authority": source.authority,
                            "version": source.version,
                            "path": source.path,
                            "reason": source.reason,
                            "protected": source.protected,
                            "estimated_tokens": source.estimated_tokens,
                        }
                        for source in [
                            *latest_context.protected_sources,
                            *latest_context.selected_sources,
                        ]
                    ],
                    "cards": [
                        {
                            "card_id": item.card.card_id,
                            "card_name": item.card.card_name,
                            "card_type": item.card.card_type.value,
                            "reason": item.reason,
                            "priority": item.priority.value,
                            "relevance_score": item.relevance_score,
                            "estimated_tokens": item.estimated_tokens,
                        }
                        for item in latest_context.selected_cards
                    ],
                    "omitted": [item.model_dump(mode="json") for item in latest_context.omitted],
                    "source_versions": latest_context.source_versions,
                    "estimated_tokens": latest_context.estimated_tokens,
                    "token_budget": latest_context.token_budget,
                    "compiled_context": ContextCompiler.render_input_context(latest_context),
                }
                if latest_context
                else None
            ),
        }
    )


@router.get("/workflow")
def get_workflow(project_id: str) -> dict[str, Any]:
    """Return model-generated stages, event queue, and human review tasks."""
    return ok(get_orchestrator(project_id).workflow_state())


@router.get("/assets")
def get_layered_assets(project_id: str) -> dict[str, Any]:
    """List stable logical files for foundation, master, volume, event, and runtime layers."""
    return ok(get_orchestrator(project_id).layered_asset_catalog())


@router.get("/assets/{asset_id}")
def get_layered_asset(project_id: str, asset_id: str) -> dict[str, Any]:
    """Load one logical file with its authority and dependency metadata."""
    try:
        asset = get_orchestrator(project_id).layered_asset_detail(asset_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return ok(asset)


@router.post("/assets/{asset_id}/review")
def stage_layered_asset_review(
    project_id: str, asset_id: str, body: AssetReviewBody
) -> dict[str, Any]:
    """Create a human-review task for one logical file; authority remains unchanged."""
    try:
        review = get_orchestrator(project_id).generate_asset_review(
            body.run_id or new_run_id(),
            asset_id,
            body.content,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return ok(review)


@router.post("/workflow/generate")
def generate_workflow_review(project_id: str, body: WorkflowGenerateBody) -> dict[str, Any]:
    try:
        review = get_orchestrator(project_id).generate_workflow_review(
            run_id=body.run_id or new_run_id(),
            stage=body.stage,
            brief=body.brief,
            volume_index=body.volume_index,
            event_index=body.event_index,
            from_current=body.from_current,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return ok(review)


@router.get("/workflow/generate/stream")
def generate_workflow_review_stream(
    project_id: str,
    stage: str = Query(...),
    brief: str = "",
    volume_index: int = Query(1, ge=1),
    event_index: int = Query(1, ge=1),
    from_current: bool = False,
    run_id: str = "",
) -> StreamingResponse:
    return _legacy_stream(
        project_id,
        run_id,
        "workflow",
        {
            "stage": stage,
            "brief": brief,
            "volume_index": volume_index,
            "event_index": event_index,
            "from_current": from_current,
        },
    )


@router.post("/workflow/reviews/{staging_id}/approve")
def approve_workflow_review(
    project_id: str, staging_id: str, body: WorkflowReviewBody
) -> dict[str, Any]:
    try:
        result = get_orchestrator(project_id).approve_workflow_review(
            staging_id,
            body.editable,
            body.run_id,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return ok(result)


@router.post("/workflow/reviews/{staging_id}/revise")
def revise_workflow_review(
    project_id: str, staging_id: str, body: WorkflowRevisionBody
) -> dict[str, Any]:
    try:
        result = get_orchestrator(project_id).revise_workflow_review(
            staging_id,
            body.editable,
            body.feedback,
            body.run_id,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return ok(result)


@router.post("/workflow/reviews/{staging_id}/audit")
def audit_workflow_review(
    project_id: str, staging_id: str, body: WorkflowReviewBody
) -> dict[str, Any]:
    try:
        result = get_orchestrator(project_id).audit_workflow_review(
            staging_id,
            body.editable,
            body.run_id,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return ok(result)


@router.post("/workflow/reviews/{staging_id}/reject")
def reject_workflow_review(project_id: str, staging_id: str) -> dict[str, Any]:
    try:
        result = get_orchestrator(project_id).reject_workflow_review(staging_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return ok(result)


@router.post("/workflow/foundation/rewind")
def rewind_foundation(project_id: str, body: FoundationRewindBody) -> dict[str, Any]:
    """Reopen one approved foundation file without deleting its stored history."""
    try:
        result = get_orchestrator(project_id).rewind_foundation(
            body.step_key,
            body.run_id or new_run_id(),
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return ok(result)


@router.post("/auth")
def run_auth_pipeline(project_id: str, body: RunAuthBody) -> dict[str, Any]:
    """同步执行权威提交流水线（图S）。"""
    from novelwb.storage import StagingStore

    layout = require_project(project_id)
    staging_store = StagingStore(layout)
    packet = staging_store.load_optional(body.staging_id)
    if packet is None:
        raise HTTPException(404, f"暂存包不存在: {body.staging_id}")

    orch = get_orchestrator(project_id)
    run_id = body.run_id or new_run_id()
    out = orch.run_auth_pipeline(run_id, packet)
    if out.aborted:
        raise HTTPException(422, detail="权威提交验证失败")
    return ok(
        {
            "run_id": run_id,
            "staging_id": body.staging_id,
            "committed": True,
            "receipt_id": out.commit_receipt.receipt_id,
        }
    )


@router.post("/regression")
def run_regression(project_id: str, test_types: list[str] | None = None) -> dict[str, Any]:
    """运行回归测试。"""
    orch = get_orchestrator(project_id)
    result = orch.run_regression(test_types=test_types)
    report = result["report"]
    return ok(
        {
            "passed": report.passed,
            "event_count": report.event_count,
            "chapter_count": report.chapter_count,
            "error_count": report.error_count,
            "warning_count": report.warning_count,
            "issues": [
                {"type": i.test_type, "id": i.issue_id, "severity": i.severity, "msg": i.message}
                for i in report.issues
            ],
        }
    )
