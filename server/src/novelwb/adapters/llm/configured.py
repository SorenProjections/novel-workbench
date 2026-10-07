"""Explicit model profiles for common text generation API protocols."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from novelwb.adapters.llm.base import LLMAdapter, LLMResponse
from novelwb.core.model_settings import ResolvedProfile
from novelwb.core.schemas.domain_models import LLMCallRecord
from novelwb.utils.ids import new_call_id
from novelwb.utils.timeutil import utcnow


class ModelConnectionError(RuntimeError):
    """A safe error: never includes provider response bodies, URLs or request headers."""


class ConfiguredAdapter(LLMAdapter):
    def __init__(self, profile: ResolvedProfile) -> None:
        self.profile = profile

    @property
    def adapter_type(self) -> str:
        return self.profile.options.protocol

    def _request(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        thinking: str | None,
        reasoning_effort: str | None,
        response_format: str | dict[str, Any] | None,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        options = self.profile.options
        key = self.profile.api_key.get_secret_value()
        headers = {"Content-Type": "application/json"}
        protocol = options.protocol
        base = options.base_url.rstrip("/")
        if not urlsplit(base).path.rstrip("/"):
            base += "/v1beta" if protocol == "gemini" else "/v1"
        budget = min(max_tokens, options.max_output_tokens)
        format_type = (
            response_format
            if isinstance(response_format, str)
            else (response_format or {}).get("type")
        )
        wants_json = format_type in {"json_object", "json_schema"}
        if wants_json:
            prompt += "\nReturn only valid JSON, without Markdown fences or commentary."
        body: dict[str, Any]
        if protocol == "gemini":
            if key:
                headers["x-goog-api-key"] = key
            config: dict[str, Any] = {"maxOutputTokens": budget}
            if options.send_temperature:
                config["temperature"] = temperature
            if wants_json and options.json_mode:
                config["responseMimeType"] = "application/json"
            body = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": config,
            }
            model_id = options.model.removeprefix("models/")
            return f"{base}/models/{quote(model_id, safe='')}:generateContent", headers, body
        if protocol == "anthropic":
            if key:
                headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"
            body = {
                "model": options.model,
                "max_tokens": budget,
                "messages": [{"role": "user", "content": prompt}],
            }
            endpoint = "messages"
        elif protocol == "openai_responses":
            body = {
                "model": options.model,
                "input": prompt,
                "max_output_tokens": budget,
                "store": False,
            }
            endpoint = "responses"
            if wants_json and options.json_mode:
                body["text"] = {"format": {"type": "json_object"}}
            if options.reasoning_effort:
                body["reasoning"] = {"effort": options.reasoning_effort}
        else:
            body = {
                "model": options.model,
                "messages": [{"role": "user", "content": prompt}],
                options.token_parameter: budget,
            }
            endpoint = "chat/completions"
            if wants_json and options.json_mode:
                body["response_format"] = {"type": "json_object"}
            if protocol == "deepseek":
                mode = (thinking or "disabled") if options.thinking == "steps" else options.thinking
                body["thinking"] = {"type": mode}
                if mode == "enabled":
                    body["reasoning_effort"] = (
                        options.reasoning_effort or reasoning_effort or "high"
                    )
            elif options.reasoning_effort:
                body["reasoning_effort"] = options.reasoning_effort
        if key and protocol != "anthropic":
            headers["Authorization"] = f"Bearer {key}"
        if options.send_temperature and body.get("thinking", {}).get("type") != "enabled":
            body["temperature"] = temperature
        return f"{base}/{endpoint}", headers, body

    def _parse(self, data: Any) -> tuple[str, int, int]:
        protocol = self.profile.options.protocol
        try:
            usage = data.get("usage", {})
            if protocol == "anthropic":
                text = "".join(
                    item["text"] for item in data["content"] if item.get("type") == "text"
                )
                inputs = sum(
                    int(usage.get(key, 0))
                    for key in (
                        "input_tokens",
                        "cache_read_input_tokens",
                        "cache_creation_input_tokens",
                    )
                )
                outputs = int(usage.get("output_tokens", 0))
            elif protocol == "gemini":
                text = "".join(
                    part.get("text", "")
                    for part in data["candidates"][0]["content"]["parts"]
                    if not part.get("thought")
                )
                usage = data.get("usageMetadata", {})
                inputs = int(usage.get("promptTokenCount", 0))
                outputs = int(usage.get("candidatesTokenCount", 0)) + int(
                    usage.get("thoughtsTokenCount", 0)
                )
            elif protocol == "openai_responses":
                text = "".join(
                    part["text"]
                    for item in data["output"]
                    if item.get("type") == "message"
                    for part in item.get("content", [])
                    if part.get("type") == "output_text"
                )
                inputs, outputs = (
                    int(usage.get("input_tokens", 0)),
                    int(usage.get("output_tokens", 0)),
                )
            else:
                text = data["choices"][0]["message"]["content"]
                if isinstance(text, list):
                    text = "".join(
                        item.get("text", "") for item in text if item.get("type") == "text"
                    )
                inputs, outputs = (
                    int(usage.get("prompt_tokens", 0)),
                    int(usage.get("completion_tokens", 0)),
                )
            if not isinstance(text, str) or not text.strip():
                raise ModelConnectionError(
                    "服务返回了空正文；请检查模型能力、输出上限或内容拦截设置"
                )
            return text, inputs, outputs
        except (KeyError, TypeError, IndexError, ValueError, AttributeError):
            raise ModelConnectionError(
                "服务响应与所选 API 协议不匹配，请检查协议和模型 ID"
            ) from None

    @staticmethod
    def _http_error(status: int) -> str:
        message = {
            401: "密钥无效或已过期",
            403: "没有访问该模型的权限",
            404: "API 地址或模型 ID 不存在",
            400: "模型不接受当前参数，请检查协议、输出上限和高级选项",
            422: "模型不接受当前参数，请检查协议、输出上限和高级选项",
            429: "触发限流或额度不足",
            301: "API 地址发生重定向，请填写最终地址",
            302: "API 地址发生重定向，请填写最终地址",
            307: "API 地址发生重定向，请填写最终地址",
            308: "API 地址发生重定向，请填写最终地址",
        }.get(status, "模型服务暂时不可用")
        return f"HTTP {status}：{message}"

    def _generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float = 0.7,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
        response_format: str | dict[str, Any] | None = None,
        testing: bool = False,
    ) -> tuple[str, int, int, int]:
        options = self.profile.options
        url, headers, body = self._request(
            prompt, max_tokens, temperature, thinking, reasoning_effort, response_format
        )
        timeout = min(options.timeout_seconds, 20) if testing else options.timeout_seconds
        retries = 0 if testing else options.max_retries
        started = time.monotonic()
        error = "模型服务连接失败"
        # A per-call client is closed even when settings switch while an older run is active.
        # Never follow redirects carrying a key, and preserve DeepSeek's direct connection policy.
        with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            for attempt in range(retries + 1):
                if attempt:
                    time.sleep(2**attempt)
                try:
                    response = client.post(url, json=body, headers=headers)
                    if response.status_code >= 300:
                        error = self._http_error(response.status_code)
                        if response.status_code not in {429, 500, 502, 503, 504}:
                            raise ModelConnectionError(error)
                        continue
                    try:
                        data = response.json()
                    except ValueError:
                        raise ModelConnectionError(
                            "API 返回的不是 JSON，请检查基础地址与协议"
                        ) from None
                    text, inputs, outputs = self._parse(data)
                    return text, inputs, outputs, int((time.monotonic() - started) * 1000)
                except httpx.TimeoutException:
                    error = "连接或响应超时，请检查 API 地址，或增加生成超时"
                except httpx.RequestError:
                    error = "无法连接模型服务，请检查地址、网络和 TLS 证书"
        raise ModelConnectionError(error) from None

    def test_connection(self) -> dict[str, Any]:
        _, inputs, outputs, latency = self._generate(
            "Reply with the single word OK.", max_tokens=256, testing=True
        )
        return {
            "success": True,
            "latency_ms": latency,
            "input_tokens": inputs,
            "output_tokens": outputs,
        }

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
        # Explicit UI selection overrides legacy per-step DeepSeek model names.
        text, inputs, outputs, latency = self._generate(
            rendered_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking=thinking,
            reasoning_effort=reasoning_effort,
            response_format=response_format,
        )
        return LLMResponse(
            text=text,
            record=LLMCallRecord(
                call_id=new_call_id(),
                step_id=step_id,
                prompt_key=prompt_key,
                prompt_version=prompt_version,
                prompt_hash=prompt_hash,
                model=self.profile.options.model,
                input_tokens=inputs,
                output_tokens=outputs,
                latency_ms=latency,
                cached=False,
                timestamp=utcnow(),
            ),
        )
