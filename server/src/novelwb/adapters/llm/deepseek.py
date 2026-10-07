"""DeepSeekAdapter — DeepSeek API LLM 适配器。

特性：
- 同步 httpx 调用（与 FastAPI 可通过 run_in_executor 配合）
- DeepSeek 连接强制直连，忽略 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY
- 集成 LlmCacheStore（命中则直接返回，不发网络请求）
- 指数退避重试：429 / 5xx 最多 MAX_RETRY_COUNT 次
- 记录完整 LLMCallRecord（latency / tokens / cached 标志）
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from novelwb.adapters.llm.base import LLMAdapter, LLMResponse
from novelwb.core.constants import Defaults, LLMAdapterType
from novelwb.core.schemas.domain_models import LLMCallRecord
from novelwb.storage.llm_cache_store import LlmCacheStore
from novelwb.utils.ids import new_call_id
from novelwb.utils.logger import get_logger
from novelwb.utils.timeutil import utcnow

_logger = get_logger(__name__)

_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEEPSEEK_MODEL = "deepseek-v4-pro"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DeepSeekAdapter(LLMAdapter):
    """DeepSeek Chat Completions API 适配器。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEEPSEEK_MODEL,
        base_url: str = _DEEPSEEK_BASE_URL,
        cache: LlmCacheStore | None = None,
        max_retries: int = Defaults.MAX_RETRY_COUNT,
        timeout: float = 60.0,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not self._api_key:
            raise ValueError("DeepSeek API key 未设置（环境变量 DEEPSEEK_API_KEY 或构造参数）")
        self._model = os.environ.get("DEEPSEEK_MODEL", model)
        self._base_url = base_url.rstrip("/")
        self._cache = cache
        self._max_retries = int(os.environ.get("DEEPSEEK_MAX_RETRIES", max_retries))
        self._timeout = float(os.environ.get("DEEPSEEK_TIMEOUT", timeout))
        # Graph 2 responses are deliberately larger than ordinary routing
        # calls.  Give a single request enough read time, but keep transport
        # retries bounded so a timeout cannot silently multiply token spend.
        self._graph2_timeout = float(os.environ.get("DEEPSEEK_GRAPH2_TIMEOUT", 300.0))
        self._graph2_retries = int(os.environ.get("DEEPSEEK_GRAPH2_RETRIES", 1))
        # Graph 3 carries the complete approved longline and can produce a
        # 30-slot volume contract. Keep its timeout and transport retries
        # independent from ordinary short routing calls.
        self._graph3_timeout = float(os.environ.get("DEEPSEEK_GRAPH3_TIMEOUT", 600.0))
        self._graph3_retries = int(os.environ.get("DEEPSEEK_GRAPH3_RETRIES", 1))
        # Event planning contains several high-reasoning JSON calls.  Keep it
        # independent from both short routing calls and prose generation.
        self._graph4_plan_timeout = float(os.environ.get("DEEPSEEK_GRAPH4_PLAN_TIMEOUT", 300.0))
        self._graph4_plan_retries = int(os.environ.get("DEEPSEEK_GRAPH4_PLAN_RETRIES", 1))
        self._blocks_timeout = float(os.environ.get("DEEPSEEK_BLOCKS_TIMEOUT", 180.0))
        self._blocks_retries = int(os.environ.get("DEEPSEEK_BLOCKS_RETRIES", 1))
        # Graph E is already responsible for schema and reconciliation
        # retries. Transport retries here would multiply the approval wait
        # into tens of minutes while restarting the same large JSON output.
        self._graph_e_timeout = float(os.environ.get("DEEPSEEK_GRAPHE_TIMEOUT", 180.0))
        self._graph_e_retries = int(os.environ.get("DEEPSEEK_GRAPHE_RETRIES", 0))
        self._thinking = (thinking or os.environ.get("DEEPSEEK_THINKING") or "disabled").lower()
        self._reasoning_effort = (
            reasoning_effort or os.environ.get("DEEPSEEK_REASONING_EFFORT") or "high"
        )
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
            # DeepSeek 请求必须直连。httpx 默认 trust_env=True，会自动读取
            # HTTP_PROXY / HTTPS_PROXY / ALL_PROXY，并被导向本机代理端口。
            trust_env=False,
        )

    @property
    def adapter_type(self) -> str:
        return LLMAdapterType.DEEPSEEK

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
        call_model = model or self._model
        call_thinking = (thinking or self._thinking).lower()
        call_effort = reasoning_effort or self._reasoning_effort
        cache_variant = self._cache_variant(
            model=call_model,
            thinking=call_thinking,
            reasoning_effort=call_effort,
            response_format=response_format,
        )
        # ── 缓存命中 ───────────────────────────────────────────
        if self._cache:
            cached = self._cache.get(
                prompt_key,
                prompt_version,
                rendered_prompt,
                cache_variant=cache_variant,
            )
            if cached:
                record = LLMCallRecord(
                    call_id=new_call_id(),
                    step_id=step_id,
                    prompt_key=prompt_key,
                    prompt_version=prompt_version,
                    prompt_hash=prompt_hash,
                    model=cached.model or call_model,
                    input_tokens=cached.input_tokens,
                    output_tokens=cached.output_tokens,
                    latency_ms=0,
                    cached=True,
                    timestamp=utcnow(),
                )
                _logger.debug("llm_cache_hit", extra={"prompt_key": prompt_key})
                return LLMResponse(text=cached.response_text, record=record)

        # ── 真实调用（带重试）────────────────────────────────────
        if prompt_key.startswith("graph2."):
            call_timeout = self._graph2_timeout
            call_retries = self._graph2_retries
        elif prompt_key.startswith("graph3."):
            call_timeout = self._graph3_timeout
            call_retries = self._graph3_retries
        elif prompt_key == "graph4.blocksWrite":
            call_timeout = self._blocks_timeout
            call_retries = self._blocks_retries
        elif prompt_key.startswith("graph4."):
            call_timeout = self._graph4_plan_timeout
            call_retries = self._graph4_plan_retries
        elif prompt_key.startswith("graphE."):
            call_timeout = self._graph_e_timeout
            call_retries = self._graph_e_retries
        else:
            call_timeout = self._timeout
            call_retries = self._max_retries
        text, input_tokens, output_tokens, latency_ms = self._call_with_retry(
            rendered_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            model=call_model,
            thinking=call_thinking,
            reasoning_effort=call_effort,
            response_format=response_format,
            prompt_key=prompt_key,
            timeout=call_timeout,
            max_retries=call_retries,
        )

        # ── 写缓存 ─────────────────────────────────────────────
        if self._cache:
            self._cache.put(
                prompt_key=prompt_key,
                prompt_version=prompt_version,
                rendered_prompt=rendered_prompt,
                response_text=text,
                cache_variant=cache_variant,
                model=call_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        record = LLMCallRecord(
            call_id=new_call_id(),
            step_id=step_id,
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            model=call_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cached=False,
            timestamp=utcnow(),
        )
        return LLMResponse(text=text, record=record)

    # ── 内部：带重试的 HTTP 调用 ──────────────────────────────────

    def _call_with_retry(
        self,
        rendered_prompt: str,
        max_tokens: int,
        temperature: float,
        model: str,
        thinking: str,
        reasoning_effort: str,
        response_format: str | dict[str, Any] | None,
        prompt_key: str,
        timeout: float,
        max_retries: int,
    ) -> tuple[str, int, int, int]:
        """返回 (response_text, input_tokens, output_tokens, latency_ms)。"""
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": rendered_prompt}],
            "max_tokens": max_tokens,
            "thinking": {"type": thinking},
        }
        if thinking == "enabled":
            payload["reasoning_effort"] = reasoning_effort
        else:
            payload["temperature"] = temperature
        if response_format:
            payload["response_format"] = (
                {"type": response_format} if isinstance(response_format, str) else response_format
            )
        last_exc: Exception = RuntimeError("未执行任何重试")
        for attempt in range(max_retries + 1):
            if attempt > 0:
                wait = 2**attempt
                _logger.warning(f"llm_retry prompt={prompt_key} attempt={attempt} wait_s={wait}")
                time.sleep(wait)
            t0 = time.monotonic()
            try:
                _logger.info(
                    f"llm_call_start prompt={prompt_key} attempt={attempt + 1}/{max_retries + 1} "
                    f"timeout={timeout} max_tokens={max_tokens}"
                )
                resp = self._client.post("/v1/chat/completions", json=payload, timeout=timeout)
                latency_ms = int((time.monotonic() - t0) * 1000)
                if resp.status_code in _RETRYABLE_STATUS:
                    last_exc = RuntimeError(
                        f"DeepSeek API 可重试错误 HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    continue
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                _logger.info(
                    f"llm_call_done prompt={prompt_key} attempt={attempt + 1}/{max_retries + 1} "
                    f"latency_ms={latency_ms} output_tokens={usage.get('completion_tokens', 0)}"
                )
                return (
                    text,
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    latency_ms,
                )
            except httpx.TimeoutException as exc:
                last_exc = exc
                _logger.warning(
                    f"llm_timeout prompt={prompt_key} attempt={attempt + 1}/{max_retries + 1}"
                )
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"DeepSeek API 不可重试错误 HTTP "
                    f"{exc.response.status_code}: {exc.response.text[:200]}"
                ) from exc
        raise RuntimeError(f"DeepSeek API 重试耗尽（{max_retries}次）: {last_exc}") from last_exc

    @staticmethod
    def _cache_variant(
        *,
        model: str,
        thinking: str,
        reasoning_effort: str,
        response_format: str | dict[str, Any] | None,
    ) -> str:
        return (
            f"model={model}|thinking={thinking}|"
            f"reasoning_effort={reasoning_effort}|response_format={response_format}"
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DeepSeekAdapter:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
