"""Local model profile contracts, independent of the story's authority data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

Protocol = Literal["deepseek", "openai", "openai_responses", "anthropic", "gemini"]


class ProfileOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    protocol: Protocol = "openai"
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=150)
    timeout_seconds: float = Field(default=600, ge=5, le=1800, allow_inf_nan=False)
    max_output_tokens: int = Field(default=32768, ge=1, le=262144)
    max_retries: int = Field(default=0, ge=0, le=2)
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    json_mode: bool = True
    send_temperature: bool = False
    thinking: Literal["steps", "disabled", "enabled"] = "steps"
    reasoning_effort: Literal["", "low", "medium", "high", "max"] = ""

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            _ = parsed.port
        except ValueError:
            raise ValueError("API 地址格式不正确") from None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(char.isspace() or ord(char) < 32 for char in value)
            or "\\" in value
        ):
            raise ValueError("使用 http(s) API 基础地址，不要包含密钥、查询参数或片段")
        # Accept a commonly copied full endpoint without appending it twice.
        value = value.rstrip("/")
        for suffix in ("/chat/completions", "/responses", "/messages"):
            if value.endswith(suffix):
                value = value[: -len(suffix)]
                break
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]*", value) or ".." in value:
            raise ValueError("模型 ID 只能包含字母、数字及 . _ : / @ + -")
        return value


class ProfileInput(ProfileOptions):
    revision: int = Field(ge=0)
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    clear_api_key: bool = False

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value().strip()
        if any(ord(char) < 33 or ord(char) > 126 for char in raw):
            raise ValueError("API Key 不应包含空白、换行或非 ASCII 字符")
        return SecretStr(raw) if raw else None

    def options(self) -> ProfileOptions:
        return ProfileOptions.model_validate(
            self.model_dump(exclude={"revision", "api_key", "clear_api_key"})
        )


@dataclass(frozen=True)
class ResolvedProfile:
    options: ProfileOptions
    api_key: SecretStr
