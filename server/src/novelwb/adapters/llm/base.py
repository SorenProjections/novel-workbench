"""LLMAdapter 抽象基类 — 所有 LLM 实现必须继承此类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from novelwb.core.schemas.domain_models import LLMCallRecord


@dataclass
class LLMResponse:
    """LLM 调用的原始返回值。"""

    text: str
    record: LLMCallRecord


class LLMAdapter(ABC):
    """LLM 适配器抽象接口。

    子类实现 `call()`；框架层通过此接口统一调用，不感知具体 LLM 供应商。
    """

    @abstractmethod
    def call(
        self,
        rendered_prompt: str,
        *,
        step_id: str,
        prompt_key: str,
        prompt_version: str,
        prompt_hash: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        model: str | None = None,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
        response_format: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        """发起一次 LLM 调用，返回文本与调用记录。

        Args:
            rendered_prompt: 已渲染的完整 prompt 字符串。
            step_id:         当前步骤 ID（用于追踪）。
            prompt_key:      prompt 键（如 "graph1.spec00"）。
            prompt_version:  prompt 版本（如 "1.0"）。
            prompt_hash:     rendered_prompt 的稳定哈希（用于缓存 key）。
            max_tokens:      最大输出 token 数。
            temperature:     采样温度。

        Returns:
            LLMResponse(text=..., record=LLMCallRecord(...))
        """

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """返回适配器类型标识，与 LLMAdapterType 枚举值对应。"""
