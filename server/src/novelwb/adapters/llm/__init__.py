"""LLM 适配器包。"""

from novelwb.adapters.llm.base import LLMAdapter, LLMResponse
from novelwb.adapters.llm.deepseek import DeepSeekAdapter
from novelwb.adapters.llm.mock_replay import MockReplayAdapter

__all__ = ["LLMAdapter", "LLMResponse", "MockReplayAdapter", "DeepSeekAdapter"]
