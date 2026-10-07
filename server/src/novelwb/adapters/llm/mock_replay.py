"""MockReplayAdapter — 离线测试用 LLM 适配器。

两种工作模式：
1. 固定响应模式（default_response）：对所有请求返回同一文本。
2. Fixtures 模式：从 fixtures_dir 中按 prompt_key 匹配 .json 文件加载预录响应。
   文件格式：{"response_text": "...", "input_tokens": 100, "output_tokens": 50}
   文件名：{prompt_key.replace('.', '_')}.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from novelwb.adapters.llm.base import LLMAdapter, LLMResponse
from novelwb.core.constants import LLMAdapterType
from novelwb.core.schemas.domain_models import LLMCallRecord
from novelwb.utils.ids import new_call_id
from novelwb.utils.timeutil import utcnow

_DEFAULT_MOCK_JSON = json.dumps({"mock": True, "result": "mock_response"}, ensure_ascii=False)


class MockReplayAdapter(LLMAdapter):
    """离线 Mock 适配器，不发送任何网络请求。"""

    def __init__(
        self,
        default_response: str | None = None,
        fixtures_dir: Path | None = None,
        fake_latency_ms: int = 50,
    ) -> None:
        self._default = default_response or _DEFAULT_MOCK_JSON
        self._fixtures_dir = Path(fixtures_dir) if fixtures_dir else None
        self._fake_latency_ms = fake_latency_ms

    @property
    def adapter_type(self) -> str:
        return LLMAdapterType.MOCK_REPLAY

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
        t0 = time.monotonic()

        text, input_tokens, output_tokens = self._resolve(prompt_key, rendered_prompt)

        elapsed = int((time.monotonic() - t0) * 1000) + self._fake_latency_ms

        record = LLMCallRecord(
            call_id=new_call_id(),
            step_id=step_id,
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            model="mock",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed,
            cached=False,
            timestamp=utcnow(),
        )
        return LLMResponse(text=text, record=record)

    def _resolve(self, prompt_key: str, rendered_prompt: str) -> tuple[str, int, int]:
        """返回 (response_text, input_tokens, output_tokens)。"""
        if self._fixtures_dir:
            fixture_file = self._fixtures_dir / f"{prompt_key.replace('.', '_')}.json"
            if fixture_file.exists():
                data = json.loads(fixture_file.read_text(encoding="utf-8"))
                return (
                    data.get("response_text", self._default),
                    data.get("input_tokens", len(rendered_prompt) // 4),
                    data.get("output_tokens", 50),
                )
        # 固定响应
        return (
            self._default,
            len(rendered_prompt) // 4,
            len(self._default) // 4,
        )
