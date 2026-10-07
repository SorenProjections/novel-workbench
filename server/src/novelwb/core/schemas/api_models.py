"""API 请求/响应模型 — 统一封装，所有路由使用 ResponseEnvelope。"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseEnvelope(BaseModel, Generic[T]):
    """统一 API 响应封装。"""

    ok: bool
    data: T | None = None
    error_code: str | None = None
    error_message: str | None = None
    trace_id: str | None = None

    model_config = {"extra": "forbid"}

    @classmethod
    def success(cls, data: T, trace_id: str | None = None) -> ResponseEnvelope[T]:
        return cls(ok=True, data=data, trace_id=trace_id)

    @classmethod
    def fail(
        cls,
        error_code: str,
        error_message: str,
        trace_id: str | None = None,
    ) -> ResponseEnvelope[None]:
        return ResponseEnvelope[None](
            ok=False,
            error_code=error_code,
            error_message=error_message,
            trace_id=trace_id,
        )


# ── Run 相关请求 ──────────────────────────────────────────────


class CreateRunRequest(BaseModel):
    project_id: str
    step_key: str
    input_pack: dict[str, Any]
    material_ids: list[str] = Field(default_factory=list)
    best_of_n_override: int | None = None

    model_config = {"extra": "forbid"}


class RunStatusResponse(BaseModel):
    run_id: str
    step_key: str
    status: str
    started_at: str
    finished_at: str | None = None
    error_code: str | None = None


# ── Step 相关请求 ─────────────────────────────────────────────


class StepResultResponse(BaseModel):
    step_id: str
    run_id: str
    step_key: str
    status: str
    hardlint_passed: bool | None = None
    judge_score: float | None = None
    output: dict[str, Any] | None = None
    diff_report: dict[str, Any] | None = None


# ── 提交相关请求 ──────────────────────────────────────────────


class CommitRequest(BaseModel):
    run_id: str
    step_id: str
    staging_type: str
    force: bool = False

    model_config = {"extra": "forbid"}


class CommitResponse(BaseModel):
    committed: bool
    receipt_id: str | None = None
    rollback_reason: str | None = None
    fix_level: str | None = None


# ── 项目相关 ──────────────────────────────────────────────────


class ProjectInfo(BaseModel):
    project_id: str
    name: str
    created_at: str
    volume_count: int = 0
    event_count: int = 0
    chapter_count: int = 0
    current_ledger_version: int = 0


class CreateProjectRequest(BaseModel):
    project_id: str
    name: str

    model_config = {"extra": "forbid"}


# ── 素材卡请求 ────────────────────────────────────────────────


class MaterialQueryResponse(BaseModel):
    material_id: str
    card_type: str
    ttl: str
    version: int
    content_preview: dict[str, Any]


# ── 发布相关 ──────────────────────────────────────────────────


class PublishChapterResponse(BaseModel):
    chapter_id: str
    chapter_index: int
    title: str | None = None
    word_count: int
    chapter_intent: str
    published_at: str


# ── Spec 查询 ─────────────────────────────────────────────────


class StepSpecSummary(BaseModel):
    step_key: str
    graph: str
    description: str
    input_schema: str
    output_schema: str
    best_of_n: int
    commit_type: str
    is_key_artifact: bool
