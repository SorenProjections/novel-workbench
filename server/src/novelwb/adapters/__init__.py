"""Adapters 包 — LLM 与 Search 适配器入口。"""

from novelwb.adapters.llm import DeepSeekAdapter, LLMAdapter, LLMResponse, MockReplayAdapter
from novelwb.adapters.search import NoopSearchAdapter, SearchAdapter, SearchResult

__all__ = [
    "LLMAdapter",
    "LLMResponse",
    "MockReplayAdapter",
    "DeepSeekAdapter",
    "SearchAdapter",
    "SearchResult",
    "NoopSearchAdapter",
]
