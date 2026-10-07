"""Patch/修复/提交相关模型 — FixPlan/Commit/Verify/AtomicCommit/Receipt。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from novelwb.core.constants import AuthObjectType, FixLevel, StagingType


class FixPlan(BaseModel):
    """修复计划，由 Reconcile/HardLint 失败后生成。"""

    fix_level: FixLevel
    patch_instructions: list[str] = Field(default_factory=list)
    target_block_ids: list[str] = Field(default_factory=list)
    rewrite_chars_hint: int | None = None  # L0 补丁建议重写字数
    reason: str = ""

    model_config = {"extra": "forbid"}


class StagingPacket(BaseModel):
    """暂存区数据包（写入权威层前的缓冲）。"""

    staging_id: str
    run_id: str
    staging_type: StagingType
    content: dict[str, Any]
    diff_report: dict[str, Any] | None = None
    created_at: datetime
    verified: bool = False

    model_config = {"extra": "forbid"}


class AuthPatch(BaseModel):
    """权威层补丁包（STG_AUTH_PATCH 的内容体）。"""

    bible_patch: dict[str, Any] | None = None
    reg_patch: dict[str, Any] | None = None
    char_patch: dict[str, Any] | None = None
    ledger_patch: dict[str, Any] | None = None
    contract_patch: dict[str, Any] | None = None
    motif_patch: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}


class VerifyResult(BaseModel):
    """VERIFY 阶段校验结果。"""

    staging_id: str
    passed: bool
    violations: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    drift: list[str] = Field(default_factory=list)
    fix_plan: FixPlan | None = None
    checked_at: datetime

    model_config = {"extra": "forbid"}


class AtomicCommitSpec(BaseModel):
    """原子提交规格 — 一次性写入的权威层对象清单。"""

    run_id: str
    staging_id: str
    objects_to_write: list[AuthObjectType]
    new_versions: dict[str, int] = Field(default_factory=dict)  # object_type -> new_version
    event_index_entry: dict[str, Any] | None = None
    chapter_index_entry: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}


class CommitReceipt(BaseModel):
    """原子提交成功后的回执。"""

    receipt_id: str
    run_id: str
    staging_id: str
    commit_type: str
    committed_objects: list[str] = Field(default_factory=list)
    new_versions: dict[str, int] = Field(default_factory=dict)
    committed_at: datetime
    # 事件提交额外字段
    committed_event_id: str | None = None
    committed_state_after_key: str | None = None
    committed_ledger_version: int | None = None
    # 章节提交额外字段
    committed_chapter_id: str | None = None

    model_config = {"extra": "forbid"}


class RollbackRecord(BaseModel):
    """回滚记录（ROLLBACK 时写入，不删权威层历史版本）。"""

    rollback_id: str
    run_id: str
    staging_id: str
    reason: str
    fix_level: FixLevel | None = None
    rolled_back_at: datetime
    retrigger_from: str | None = None  # 重新触发的入口节点

    model_config = {"extra": "forbid"}
