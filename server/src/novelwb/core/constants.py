"""系统常量与枚举 — 冻结枚举，只追加，不删改。"""

from enum import Enum


# ── LLM 适配器 ────────────────────────────────────────────────
class LLMAdapterType(str, Enum):
    DEEPSEEK = "deepseek"
    MOCK_REPLAY = "mock_replay"
    OPENAI = "openai"
    OPENAI_RESPONSES = "openai_responses"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


# ── 搜索/RAG 适配器 ───────────────────────────────────────────
class SearchAdapterType(str, Enum):
    NOOP = "noop"  # 当前版本跳过RAG


# ── 产物提交类型 ──────────────────────────────────────────────
class CommitType(str, Enum):
    EVENT = "event"
    CHAPTER = "chapter"
    AUTH_PATCH = "auth_patch"
    NONE = "none"


# ── ChapterIntent 体系 ────────────────────────────────────────
class ChapterIntent(str, Enum):
    ADVANCE = "Advance"
    SETTLE = "Settle"
    FORESHADOW = "Foreshadow"
    BREATHER = "Breather"


# ── block_intent 体系 ─────────────────────────────────────────
class BlockIntent(str, Enum):
    ADVANCE = "Advance"
    SETTLE = "Settle"
    FORESHADOW = "Foreshadow"
    BREATHER = "Breather"


# ── 修复级别 ──────────────────────────────────────────────────
class FixLevel(str, Enum):
    L0 = "L0"  # 边界补丁（200-800字）
    L1 = "L1"  # 局部回滚（前1-2块）
    L2 = "L2"  # 整事件回滚


# ── 素材卡类型 ────────────────────────────────────────────────
class MaterialCardType(str, Enum):
    FACT_CARD = "FACT_CARD"
    STYLE_MATERIAL = "STYLE_MATERIAL"
    PLATFORM_CONSTRAINT = "PLATFORM_CONSTRAINT"
    NAMECHECK = "NAMECHECK"


# ── 阅读状态卡 ────────────────────────────────────────────────
class StatusCardType(str, Enum):
    """状态卡是权威数据的阅读投影，不是新的权威真值。"""

    PLOT = "plot"
    CHARACTER = "character"
    SCENE = "scene"
    FACTION = "faction"
    ITEM = "item"
    RULE = "rule"


class ContextPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CardPatchOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    RETIRE = "retire"


# ── 权威层对象类型 ────────────────────────────────────────────
class AuthObjectType(str, Enum):
    BIBLE = "BIBLE"
    REG = "REG"
    CHAR = "CHAR"
    LEDGER = "LEDGER"
    CONTRACT = "CONTRACT"
    MOTIF = "MOTIF"


# ── 暂存区类型 ────────────────────────────────────────────────
class StagingType(str, Enum):
    STG_EVENT = "STG_EVENT"
    STG_CHAPTER = "STG_CHAPTER"
    STG_AUTH_PATCH = "STG_AUTH_PATCH"


# ── 默认阈值 ──────────────────────────────────────────────────
class Defaults:
    # Breather 配额
    BREATHER_QUOTA_PER_VOLUME_RATIO: float = 0.25  # 卷内Breather章占比上限
    MAX_CONSECUTIVE_BREATHER: int = 2  # 最大连续Breather章数
    MOMENTUM_DEBT_MAX: int = 5  # MomentumDebt上限

    # 预算
    DEFAULT_EVENT_MAX_TOKENS: int = 4000
    DEFAULT_CHAPTER_MAX_CHARS: int = 3000
    DEFAULT_CONTEXT_INPUT_TOKENS: int = 12000
    DEFAULT_CONTEXT_CARDS_PER_TYPE: int = 4

    # 质量回路
    DEFAULT_BEST_OF_N: int = 1
    MAX_RETRY_COUNT: int = 3
    MIN_EVENT_PROSE_SCORE: float = 72.0
    MAX_PROSE_QUALITY_ATTEMPTS: int = 3
    QUALITY_PLATEAU_DELTA: float = 2.0
    HUMAN_OVERRIDE_THRESHOLD: int = 5  # 连续失败N次触发人工介入

    # LLM缓存
    LLM_CACHE_TTL_SECONDS: int = 86400 * 7  # 7天


# ── 目录名约定 ────────────────────────────────────────────────
class WorkspaceDirs:
    AUTH = "auth"
    STAGING = "staging"
    EVENTS = "events"
    PUBLISH = "publish"
    MATERIALS = "materials"
    SNAPSHOTS = "snapshots"
    RUNS = "runs"
    CONTEXTS = "contexts"
    CACHE = "cache"
    INDEX_DB = "index.db"
