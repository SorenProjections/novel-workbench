"""SchemaRegistry — schema_name → Pydantic 模型的唯一真值映射。"""

from __future__ import annotations

from pydantic import BaseModel

from novelwb.core.schemas.api_models import (
    CommitRequest,
    CommitResponse,
    CreateProjectRequest,
    CreateRunRequest,
    ProjectInfo,
    PublishChapterResponse,
    ResponseEnvelope,
    RunStatusResponse,
    StepResultResponse,
    StepSpecSummary,
)
from novelwb.core.schemas.domain_models import (
    AuthObject,
    BlockSpec,
    Candidate,
    CardPatch,
    ChapterCommitRecord,
    ChapterSpec,
    CharacterKnowledge,
    ContextCardSelection,
    ContextOmission,
    ContextPackage,
    ContextSource,
    DiffReport,
    EventDraft,
    EventRecord,
    EventSlot,
    FatigueReport,
    LedgerEntry,
    LLMCallRecord,
    MaterialCard,
    ObservedDelta,
    ReadingFocus,
    RevelationGate,
    ReviewAuditIssue,
    ReviewAuditResult,
    ReviewRevisionRequest,
    ReviewRevisionResult,
    RunManifest,
    SourceRef,
    StateSnapshot,
    StatusCard,
    StatusCardIndex,
    StepRecord,
    VolumeContract,
)
from novelwb.core.schemas.patch_models import (
    AtomicCommitSpec,
    AuthPatch,
    CommitReceipt,
    FixPlan,
    RollbackRecord,
    StagingPacket,
    VerifyResult,
)
from novelwb.core.schemas.prompt_models import (
    PromptCallRecord,
    PromptMeta,
    PromptRenderResult,
    PromptSpec,
)
from novelwb.core.schemas.stats_models import (
    FatigueSummary,
    FatigueWarning,
    HookRotationStats,
    IntentDistribution,
    MomentumDebtStats,
    VolumeStats,
)

# schema_name → Pydantic 模型（唯一真值，只追加不删改）
_REGISTRY: dict[str, type[BaseModel]] = {
    # domain
    "RunManifest": RunManifest,
    "StepRecord": StepRecord,
    "Candidate": Candidate,
    "LLMCallRecord": LLMCallRecord,
    "MaterialCard": MaterialCard,
    "AuthObject": AuthObject,
    "SourceRef": SourceRef,
    "CharacterKnowledge": CharacterKnowledge,
    "RevelationGate": RevelationGate,
    "StatusCard": StatusCard,
    "ReadingFocus": ReadingFocus,
    "CardPatch": CardPatch,
    "StatusCardIndex": StatusCardIndex,
    "ContextSource": ContextSource,
    "ContextCardSelection": ContextCardSelection,
    "ContextOmission": ContextOmission,
    "ContextPackage": ContextPackage,
    "StateSnapshot": StateSnapshot,
    "BlockSpec": BlockSpec,
    "EventDraft": EventDraft,
    "DiffReport": DiffReport,
    "ObservedDelta": ObservedDelta,
    "EventRecord": EventRecord,
    "LedgerEntry": LedgerEntry,
    "ChapterSpec": ChapterSpec,
    "ChapterCommitRecord": ChapterCommitRecord,
    "VolumeContract": VolumeContract,
    "EventSlot": EventSlot,
    "FatigueReport": FatigueReport,
    "ReviewAuditIssue": ReviewAuditIssue,
    "ReviewAuditResult": ReviewAuditResult,
    "ReviewRevisionRequest": ReviewRevisionRequest,
    "ReviewRevisionResult": ReviewRevisionResult,
    # api
    "ResponseEnvelope": ResponseEnvelope,
    "CreateRunRequest": CreateRunRequest,
    "RunStatusResponse": RunStatusResponse,
    "StepResultResponse": StepResultResponse,
    "CommitRequest": CommitRequest,
    "CommitResponse": CommitResponse,
    "ProjectInfo": ProjectInfo,
    "CreateProjectRequest": CreateProjectRequest,
    "PublishChapterResponse": PublishChapterResponse,
    "StepSpecSummary": StepSpecSummary,
    # patch
    "FixPlan": FixPlan,
    "StagingPacket": StagingPacket,
    "AuthPatch": AuthPatch,
    "VerifyResult": VerifyResult,
    "AtomicCommitSpec": AtomicCommitSpec,
    "CommitReceipt": CommitReceipt,
    "RollbackRecord": RollbackRecord,
    # prompt
    "PromptMeta": PromptMeta,
    "PromptSpec": PromptSpec,
    "PromptRenderResult": PromptRenderResult,
    "PromptCallRecord": PromptCallRecord,
    # stats
    "IntentDistribution": IntentDistribution,
    "HookRotationStats": HookRotationStats,
    "MomentumDebtStats": MomentumDebtStats,
    "VolumeStats": VolumeStats,
    "FatigueWarning": FatigueWarning,
    "FatigueSummary": FatigueSummary,
}


def get_schema(schema_name: str) -> type[BaseModel]:
    if schema_name not in _REGISTRY:
        raise KeyError(f"schema_name 未注册: '{schema_name}'")
    return _REGISTRY[schema_name]


def all_schema_names() -> set[str]:
    return set(_REGISTRY.keys())
