"""Prompt 相关模型 — PromptSpec/Meta/Render/CallRecord。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PromptMeta(BaseModel):
    """prompts/registry.yaml 中单条 prompt 元数据。"""

    prompt_key: str
    prompt_version: str
    schema_name: str  # 对应 schema_registry 中的 output schema
    path: str  # 相对于 prompts/ 的目录路径
    description: str = ""
    offline_only: bool = True  # 默认断网

    model_config = {"extra": "forbid"}


class PromptSpec(BaseModel):
    """prompt.yaml 单文件内容（版本化）。"""

    prompt_key: str
    version: str
    description: str = ""
    shared_fragments: list[str] = Field(default_factory=list)  # _shared/ 片段名
    variables: list[str] = Field(default_factory=list)  # Jinja2 变量列表
    output_format: str = "json"  # json | text

    model_config = {"extra": "forbid"}


class PromptRenderResult(BaseModel):
    """Prompt 渲染结果（含 hash，用于缓存 key）。"""

    prompt_key: str
    prompt_version: str
    rendered_text: str
    input_hash: str  # 渲染变量的 hash，用于缓存命中
    prompt_hash: str  # 模板本身的 hash
    render_at: datetime

    model_config = {"extra": "forbid"}


class PromptCallRecord(BaseModel):
    """单次 LLM Prompt 调用完整记录（写入 run_manifest）。"""

    call_id: str
    step_id: str
    prompt_key: str
    prompt_version: str
    prompt_hash: str
    input_hash: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cached: bool = False
    raw_output: str = ""
    parsed_output: dict[str, Any] | None = None
    parse_success: bool = True
    timestamp: datetime

    model_config = {"extra": "forbid"}
