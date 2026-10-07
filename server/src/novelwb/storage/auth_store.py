"""Versioned authority storage.

Legacy files retain one history per authority type for compatibility. Logical
artifacts are also stored independently so multiple BIBLE/REG/CHAR documents
can coexist without overwriting each other's latest pointer.
"""

from __future__ import annotations

import re
from typing import Any

from novelwb.core.constants import AuthObjectType
from novelwb.core.schemas.domain_models import AuthObject
from novelwb.storage.locks import lock_path
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.io_atomic import atomic_write_json, read_json
from novelwb.utils.jsonl import append_jsonl, read_jsonl_all
from novelwb.utils.timeutil import utcnow
from novelwb.utils.transactions import atomic_method, guarded_store


@guarded_store
class AuthStore:
    """Manage authority histories and latest logical-document snapshots."""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self._layout = layout

    @staticmethod
    def _key(object_type: str | AuthObjectType) -> str:
        if isinstance(object_type, AuthObjectType):
            return str(object_type)
        try:
            return str(AuthObjectType(object_type))
        except (ValueError, KeyError):
            return str(object_type)

    @staticmethod
    def artifact_key(obj: AuthObject) -> str:
        """Return a stable key, including for old run-prefixed object ids."""
        object_id = obj.object_id.strip().lower()
        stable_ids = {
            "spec00",
            "world_a",
            "world_b",
            "pow_l",
            "pow_s",
            "pow_e",
            "opp_eco",
            "cast",
            "char_state",
            "ledger",
            "longline",
        }
        if object_id in stable_ids:
            return object_id
        for suffix in sorted(stable_ids, key=len, reverse=True):
            if object_id.endswith(f"_{suffix}"):
                return suffix

        content = obj.content if isinstance(obj.content, dict) else {}
        volume_id = str(content.get("volume_id", "")).strip().lower()
        if volume_id and isinstance(content.get("event_slots"), list):
            return f"volume_{volume_id}"
        if "stage_nodes" in content or "dq_promise" in content or "total_stages" in content:
            return "longline"
        if obj.object_type == AuthObjectType.CHAR:
            if "character_states" in content or "latest_state_snapshot_key" in content:
                return "char_state"
            if "characters" in content or "relationships" in content:
                return "cast"
            if "opponent_tiers" in content or "opponent_ecology" in content:
                return "opp_eco"

        safe_id = re.sub(r"[^a-z0-9_-]+", "_", object_id).strip("_")
        return safe_id or obj.object_type.value.lower()

    def commit(self, obj: AuthObject, *, expected_version: int | None = None) -> AuthObject:
        """Commit one logical document and return the stored version."""
        type_key = self._key(obj.object_type)
        type_history = self._layout.auth_object_path(type_key)
        type_latest = self._layout.auth_latest_path(type_key)
        artifact_key = self.artifact_key(obj)
        artifact_history = self._layout.auth_artifact_history_path(artifact_key)
        artifact_latest = self._layout.auth_artifact_latest_path(artifact_key)

        committed = obj
        previous = (
            AuthObject.model_validate(read_json(artifact_latest))
            if artifact_latest.exists()
            else self.load_artifact(artifact_key)
        )
        current_version = previous.version if previous is not None else 0
        if expected_version is not None and current_version != expected_version:
            raise ValueError(f"权威版本冲突: 期望 v{expected_version}，实际 v{current_version}")
        if previous is not None:
            committed = obj.model_copy(
                update={
                    "object_id": artifact_key,
                    "version": max(previous.version + 1, obj.version),
                    "created_at": previous.created_at,
                }
            )
        elif obj.object_id != artifact_key:
            committed = obj.model_copy(update={"object_id": artifact_key})

        data = committed.model_dump(mode="json")
        with lock_path(type_history):
            append_jsonl(type_history, data)
            atomic_write_json(type_latest, data)
        with lock_path(artifact_history):
            append_jsonl(artifact_history, data)
            atomic_write_json(artifact_latest, data)
        self.reactivate_artifact(artifact_key)
        return committed

    def load_latest(self, object_type: str) -> AuthObject | None:
        """Compatibility API: load the last object committed for a type."""
        latest_path = self._layout.auth_latest_path(self._key(object_type))
        if not latest_path.exists():
            return None
        latest = AuthObject.model_validate(read_json(latest_path))
        invalidated = self.invalidated_artifacts()
        if self.artifact_key(latest) not in invalidated:
            return latest
        for candidate in reversed(self.load_history(object_type)):
            if self.artifact_key(candidate) not in invalidated:
                return candidate
        return None

    def require_latest(self, object_type: str) -> AuthObject:
        obj = self.load_latest(object_type)
        if obj is None:
            raise FileNotFoundError(
                f"Authority object does not exist: {object_type} "
                f"(project: {self._layout.project_id})"
            )
        return obj

    def load_artifact(
        self,
        artifact_key: str,
        *,
        include_invalidated: bool = False,
    ) -> AuthObject | None:
        """Load one logical authority document by stable key."""
        safe_key = re.sub(r"[^a-z0-9_-]+", "_", artifact_key.lower()).strip("_")
        if not include_invalidated and safe_key in self.invalidated_artifacts():
            return None
        latest_path = self._layout.auth_artifact_latest_path(safe_key)
        if latest_path.exists():
            return AuthObject.model_validate(read_json(latest_path))
        if self._layout.auth_dir.joinpath("artifacts_complete.json").exists():
            return None
        matches = [obj for obj in self._load_legacy_bundle() if self.artifact_key(obj) == safe_key]
        return matches[-1] if matches else None

    @atomic_method
    def load_bundle(
        self,
        object_types: set[str] | None = None,
        *,
        include_invalidated: bool = False,
    ) -> list[AuthObject]:
        """Load the latest version of every logical authority document."""
        paths = sorted(self._layout.auth_artifacts_dir.glob("*.latest.json"))
        by_artifact = (
            {}
            if self._layout.auth_dir.joinpath("artifacts_complete.json").exists()
            else {self.artifact_key(obj): obj for obj in self._load_legacy_bundle()}
        )
        for path in paths:
            obj = AuthObject.model_validate(read_json(path))
            by_artifact[self.artifact_key(obj)] = obj

        if not self._layout.auth_dir.joinpath("artifacts_complete.json").exists():
            for key, obj in by_artifact.items():
                atomic_write_json(
                    self._layout.auth_artifact_latest_path(key), obj.model_dump(mode="json")
                )
            atomic_write_json(self._layout.auth_dir / "artifacts_complete.json", {"complete": True})

        normalized = {self._key(item) for item in object_types} if object_types else None
        invalidated = set() if include_invalidated else self.invalidated_artifacts()
        return [
            obj
            for _, obj in sorted(by_artifact.items())
            if self.artifact_key(obj) not in invalidated
            and (normalized is None or self._key(obj.object_type) in normalized)
        ]

    def invalidated_artifacts(self) -> set[str]:
        """Return logical files hidden by a non-destructive rewind."""
        data = read_json(self._layout.foundation_invalidations_path) or {}
        artifacts = data.get("artifacts", {}) if isinstance(data, dict) else {}
        return {str(key) for key in artifacts}

    def invalidation_details(self) -> dict[str, dict[str, Any]]:
        data = read_json(self._layout.foundation_invalidations_path) or {}
        artifacts = data.get("artifacts", {}) if isinstance(data, dict) else {}
        return {
            str(key): dict(value) if isinstance(value, dict) else {}
            for key, value in artifacts.items()
        }

    def invalidate_artifacts(
        self,
        artifact_keys: list[str] | tuple[str, ...] | set[str],
        *,
        run_id: str,
        reason: str,
        from_step: str,
    ) -> None:
        """Hide current latest pointers without deleting histories or snapshots."""
        path = self._layout.foundation_invalidations_path
        with lock_path(path):
            data = read_json(path) or {"artifacts": {}}
            artifacts = dict(data.get("artifacts") or {})
            now = utcnow().isoformat()
            for key in artifact_keys:
                safe_key = re.sub(r"[^a-z0-9_-]+", "_", str(key).lower()).strip("_")
                artifacts[safe_key] = {
                    "run_id": run_id,
                    "reason": reason,
                    "from_step": from_step,
                    "invalidated_at": now,
                }
            atomic_write_json(path, {"artifacts": artifacts, "updated_at": now})

    def reactivate_artifact(self, artifact_key: str) -> None:
        """Clear a logical tombstone after a newly reviewed version is committed."""
        path = self._layout.foundation_invalidations_path
        if not path.exists():
            return
        safe_key = re.sub(r"[^a-z0-9_-]+", "_", artifact_key.lower()).strip("_")
        with lock_path(path):
            data = read_json(path) or {"artifacts": {}}
            artifacts = dict(data.get("artifacts") or {})
            if safe_key not in artifacts:
                return
            artifacts.pop(safe_key, None)
            atomic_write_json(
                path,
                {
                    "artifacts": artifacts,
                    "updated_at": utcnow().isoformat(),
                },
            )

    def _load_legacy_bundle(self) -> list[AuthObject]:
        latest_by_artifact: dict[str, AuthObject] = {}
        for object_type in AuthObjectType:
            for obj in self.load_history(object_type.value):
                latest_by_artifact[self.artifact_key(obj)] = obj
        return list(latest_by_artifact.values())

    def load_history(self, object_type: str) -> list[AuthObject]:
        rows = read_jsonl_all(self._layout.auth_object_path(self._key(object_type)))
        return [AuthObject.model_validate(row) for row in rows]

    def load_version(self, object_type: str, version: int) -> AuthObject | None:
        history = self.load_history(object_type)
        if version < 0 or version >= len(history):
            return None
        return history[version]

    def exists(self, object_type: str) -> bool:
        return self._layout.auth_latest_path(self._key(object_type)).exists()
