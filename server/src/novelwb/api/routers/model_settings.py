"""Local-only configuration endpoints; credentials are write-only to the browser."""

from __future__ import annotations

import ipaddress
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from novelwb.adapters.llm.configured import ConfiguredAdapter, ModelConnectionError
from novelwb.api import deps
from novelwb.core.model_settings import ProfileInput, ProfileOptions
from novelwb.storage.model_settings_store import ModelSettingsStore


def _loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def local_settings_request(request: Request) -> None:
    if (
        not request.client
        or not _loopback(request.client.host)
        or not _loopback(request.url.hostname)
    ):
        raise HTTPException(403, "模型配置仅允许通过本机 localhost 或回环地址访问")
    origin = request.headers.get("origin")
    if origin:
        allowed = {
            f"{request.url.scheme}://{request.url.netloc}",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }
        if origin not in allowed:
            raise HTTPException(403, "请从本机工作台打开模型配置")
    if request.headers.get("x-model-settings") != "1":
        raise HTTPException(403, "缺少模型配置请求标记")
    if (
        request.method != "GET"
        and request.headers.get("content-type", "").split(";")[0] != "application/json"
    ):
        raise HTTPException(415, "模型配置请求必须使用 JSON")
    if deps.model_settings_disabled() and request.method != "GET":
        raise HTTPException(403, "离线演示已锁定 mock；请启动普通工作台配置真实模型")


router = APIRouter(
    prefix="/settings/models",
    tags=["model-settings"],
    dependencies=[Depends(local_settings_request)],
)


class RevisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)


class ActiveBody(RevisionBody):
    profile_id: str | None = Field(default=None, min_length=1, max_length=64)


class TestBody(ProfileInput):
    profile_id: str | None = None

    def options(self) -> ProfileOptions:
        return ProfileOptions.model_validate(
            self.model_dump(exclude={"revision", "api_key", "clear_api_key", "profile_id"})
        )


def store() -> ModelSettingsStore:
    return ModelSettingsStore(deps.WORKSPACE_ROOT)


def enrich(data: dict[str, Any]) -> dict[str, Any]:
    data["disabled"] = deps.model_settings_disabled()
    adapter = os.environ.get("NOVELWB_LLM_ADAPTER", os.environ.get("LLM_ADAPTER", "mock"))
    data["environment_label"] = (
        "DeepSeek（沿用步骤配置）" if adapter == "deepseek" else "Mock（离线样例）"
    )
    return deps.ok(data)


@router.get("")
def read_settings() -> dict[str, Any]:
    return enrich(store().public())


@router.post("/profiles")
def create_profile(body: ProfileInput) -> dict[str, Any]:
    return enrich(store().save(body))


@router.put("/profiles/{profile_id}")
def update_profile(profile_id: str, body: ProfileInput) -> dict[str, Any]:
    return enrich(store().save(body, profile_id))


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str, body: RevisionBody) -> dict[str, Any]:
    return enrich(store().delete(profile_id, body.revision))


@router.post("/active")
def activate_profile(body: ActiveBody) -> dict[str, Any]:
    return enrich(store().activate(body.profile_id, body.revision))


@router.post("/test")
def test_connection(body: TestBody) -> dict[str, Any]:
    profile = store().draft(body, body.profile_id)
    try:
        return deps.ok(ConfiguredAdapter(profile).test_connection())
    except ModelConnectionError as exc:
        raise HTTPException(502, str(exc)) from None
