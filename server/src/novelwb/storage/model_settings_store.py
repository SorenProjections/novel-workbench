"""Versioned, atomic local model settings. Public views never contain credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import SecretStr

from novelwb.core.model_settings import ProfileInput, ProfileOptions, ResolvedProfile
from novelwb.utils.file_locks import lock_path
from novelwb.utils.local_secrets import protect, protection_method, reveal
from novelwb.utils.transactions import durable_replace


class SettingsConflict(ValueError):
    pass


class ModelSettingsStore:
    def __init__(self, workspace: Path) -> None:
        self.directory = workspace.resolve() / ".model-settings"
        self.path = self.directory / "model-profiles.json"

    def _check_paths(self) -> None:
        if self.directory.is_symlink() or self.path.is_symlink():
            raise ValueError("模型配置目录和文件不能是符号链接")
        if self.directory.resolve().parent != self.directory.parent:
            raise ValueError("模型配置不能越出工作区")

    def _read(self) -> dict[str, Any]:
        self._check_paths()
        if not self.path.exists():
            return {"schema_version": 1, "revision": 0, "active_profile_id": None, "profiles": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data["schema_version"] != 1 or not isinstance(data["revision"], int):
                raise ValueError
            ids = set()
            for row in data["profiles"]:
                ProfileOptions.model_validate(row["options"])
                if not isinstance(row["secret"], str) or row["id"] in ids:
                    raise ValueError
                ids.add(row["id"])
            if data["active_profile_id"] is not None and data["active_profile_id"] not in ids:
                raise ValueError
            return dict(data)
        except (ValueError, KeyError, TypeError):
            raise ValueError("本机模型配置文件损坏或版本不兼容，请恢复备份；未覆盖原文件") from None

    def _prepare_directory(self) -> None:
        self._check_paths()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            self.directory.chmod(0o700)

    @staticmethod
    def _row(data: dict[str, Any], profile_id: str) -> dict[str, Any]:
        for row in data["profiles"]:
            if row["id"] == profile_id:
                return dict(row)
        raise FileNotFoundError("模型配置不存在，请刷新列表")

    @staticmethod
    def _revision(data: dict[str, Any], expected: int) -> None:
        if expected != data["revision"]:
            raise SettingsConflict("模型配置已在其他页面更新，请刷新后重试；本次没有覆盖")

    @staticmethod
    def _view(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "revision": data["revision"],
            "active_profile_id": data["active_profile_id"],
            "storage_protection": protection_method(),
            "profiles": [
                {"id": row["id"], **row["options"], "has_api_key": bool(row["secret"])}
                for row in data["profiles"]
            ],
        }

    def public(self) -> dict[str, Any]:
        return self._view(self._read())

    def active(self) -> ResolvedProfile | None:
        data = self._read()
        if data["active_profile_id"] is None:
            return None
        row = self._row(data, data["active_profile_id"])
        return ResolvedProfile(
            ProfileOptions.model_validate(row["options"]), SecretStr(reveal(row["secret"]))
        )

    def _secret(self, body: ProfileInput, row: dict[str, Any] | None) -> str:
        if body.clear_api_key:
            if body.api_key is not None:
                raise ValueError("清除密钥和输入新密钥不能同时选择")
            return ""
        if body.api_key is not None:
            return body.api_key.get_secret_value()
        if row is None or not row["secret"]:
            return ""
        previous = row["options"]
        if (previous["base_url"], previous["protocol"]) != (body.base_url, body.protocol):
            raise ValueError("更换 API 地址或协议时，请重新输入密钥，或明确清除旧密钥")
        return reveal(row["secret"])

    def draft(self, body: ProfileInput, profile_id: str | None = None) -> ResolvedProfile:
        data = self._read()
        self._revision(data, body.revision)
        row = self._row(data, profile_id) if profile_id else None
        return ResolvedProfile(body.options(), SecretStr(self._secret(body, row)))

    def _write(self, data: dict[str, Any]) -> dict[str, Any]:
        self._check_paths()
        data["revision"] += 1
        durable_replace(self.path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())
        if os.name != "nt":
            self.path.chmod(0o600)
        return self._view(data)

    def save(self, body: ProfileInput, profile_id: str | None = None) -> dict[str, Any]:
        self._prepare_directory()
        with lock_path(self.directory / "settings"):
            data = self._read()
            self._revision(data, body.revision)
            row = self._row(data, profile_id) if profile_id else None
            secret = self._secret(body, row)
            updated = {
                "id": profile_id or uuid4().hex,
                "options": body.options().model_dump(),
                "secret": protect(secret),
            }
            if row is None:
                if len(data["profiles"]) >= 50:
                    raise ValueError("最多保存 50 套配置，请先删除不再使用的配置")
                data["profiles"].append(updated)
            else:
                data["profiles"] = [
                    updated if item["id"] == profile_id else item for item in data["profiles"]
                ]
            result = self._write(data)
            result["saved_profile_id"] = updated["id"]
            return result

    def activate(self, profile_id: str | None, revision: int) -> dict[str, Any]:
        self._prepare_directory()
        with lock_path(self.directory / "settings"):
            data = self._read()
            self._revision(data, revision)
            if profile_id:
                row = self._row(data, profile_id)
                reveal(row["secret"])  # Fail before switching if an imported secret cannot be read.
            data["active_profile_id"] = profile_id
            return self._write(data)

    def delete(self, profile_id: str, revision: int) -> dict[str, Any]:
        self._prepare_directory()
        with lock_path(self.directory / "settings"):
            data = self._read()
            self._revision(data, revision)
            self._row(data, profile_id)
            if data["active_profile_id"] == profile_id:
                raise ValueError("请先切换到其他配置或环境配置，再删除当前配置")
            data["profiles"] = [row for row in data["profiles"] if row["id"] != profile_id]
            return self._write(data)
