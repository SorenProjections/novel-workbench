"""Workspace 布局 — 禁止拼接路径，所有路径从此处取。"""

from __future__ import annotations

import re
from pathlib import Path

from novelwb.core.constants import WorkspaceDirs


class WorkspaceLayout:
    """单个项目的目录结构，所有 Store 通过此类获取路径。"""

    @staticmethod
    def validate_id(value: str) -> str:
        if (
            not value
            or value != value.strip()
            or value in {".", ".."}
            or value.endswith((".", " "))
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
            or value.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10)),
            }
        ):
            raise ValueError("名称非法：请使用普通文件名，不能包含路径或保留名称")
        return value

    def __init__(self, workspace_root: Path, project_id: str, *, create: bool = True) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.project_id = self.validate_id(project_id)
        self.project_dir = (self.workspace_root / self.project_id).resolve()
        if self.project_dir.parent != self.workspace_root:
            raise ValueError("项目目录不能越出工作区")
        if create:
            self._ensure_dirs()
        elif not self.project_dir.is_dir():
            raise FileNotFoundError(f"项目不存在: {project_id}")

    def _directory(self, name: str) -> Path:
        path = (self.project_dir / name).resolve()
        if not path.is_relative_to(self.project_dir):
            raise ValueError("项目子目录不能越出项目目录")
        return path

    def _file(self, directory: Path, name: str, suffix: str) -> Path:
        self.validate_id(name)
        path = (directory / f"{name}{suffix}").resolve()
        if not path.is_relative_to(self.project_dir):
            raise ValueError("文件路径不能越出项目目录")
        return path

    def _ensure_dirs(self) -> None:
        for key, name in vars(WorkspaceDirs).items():
            if key.isupper() and isinstance(name, str) and name != WorkspaceDirs.INDEX_DB:
                directory = (self.project_dir / name).resolve()
                if not directory.is_relative_to(self.project_dir):
                    raise ValueError("项目子目录不能越出项目目录")
                directory.mkdir(parents=True, exist_ok=True)

    # ── 权威层 ────────────────────────────────────────────────
    @property
    def auth_dir(self) -> Path:
        return self._directory(WorkspaceDirs.AUTH)

    def auth_object_path(self, object_type: str) -> Path:
        return self._file(self.auth_dir, object_type, ".jsonl")

    def auth_latest_path(self, object_type: str) -> Path:
        return self._file(self.auth_dir, object_type, ".latest.json")

    @property
    def auth_artifacts_dir(self) -> Path:
        path = (self.auth_dir / "artifacts").resolve()
        if not path.is_relative_to(self.project_dir):
            raise ValueError("资产目录不能越出项目目录")
        return path

    def auth_artifact_history_path(self, artifact_key: str) -> Path:
        return self._file(self.auth_artifacts_dir, artifact_key, ".jsonl")

    def auth_artifact_latest_path(self, artifact_key: str) -> Path:
        return self._file(self.auth_artifacts_dir, artifact_key, ".latest.json")

    @property
    def foundation_invalidations_path(self) -> Path:
        """Logical tombstones for foundation files kept on disk for rollback."""
        return self.auth_dir / "foundation_invalidations.json"

    # ── 暂存区 ────────────────────────────────────────────────
    @property
    def staging_dir(self) -> Path:
        return self._directory(WorkspaceDirs.STAGING)

    def staging_packet_path(self, staging_id: str) -> Path:
        return self._file(self.staging_dir, staging_id, ".json")

    # ── 事件 ──────────────────────────────────────────────────
    @property
    def events_dir(self) -> Path:
        return self._directory(WorkspaceDirs.EVENTS)

    def event_path(self, event_id: str) -> Path:
        return self._file(self.events_dir, event_id, ".json")

    @property
    def events_index_path(self) -> Path:
        return self.events_dir / "index.jsonl"

    # ── 快照 ──────────────────────────────────────────────────
    @property
    def snapshots_dir(self) -> Path:
        return self._directory(WorkspaceDirs.SNAPSHOTS)

    def snapshot_path(self, snapshot_key: str) -> Path:
        return self._file(self.snapshots_dir, snapshot_key, ".json")

    # ── 素材库 ────────────────────────────────────────────────
    @property
    def materials_dir(self) -> Path:
        return self._directory(WorkspaceDirs.MATERIALS)

    def material_path(self, material_id: str) -> Path:
        return self._file(self.materials_dir, material_id, ".json")

    # ── 发布层 ────────────────────────────────────────────────
    @property
    def publish_dir(self) -> Path:
        return self._directory(WorkspaceDirs.PUBLISH)

    def chapter_publish_path(self, chapter_id: str) -> Path:
        return self._file(self.publish_dir, chapter_id, ".md")

    def chapter_meta_path(self, chapter_id: str) -> Path:
        return self._file(self.publish_dir, chapter_id, ".meta.json")

    @property
    def publish_index_path(self) -> Path:
        return self.publish_dir / "index.jsonl"

    # ── 运行记录 ──────────────────────────────────────────────
    @property
    def runs_dir(self) -> Path:
        return self._directory(WorkspaceDirs.RUNS)

    def run_manifest_path(self, run_id: str) -> Path:
        return self._file(self.runs_dir, run_id, ".json")

    def run_failure_path(self, run_id: str, step_key: str) -> Path:
        safe_run = (
            "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in run_id).strip("_")
            or "unknown_run"
        )
        safe_step = (
            "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in step_key).strip("_")
            or "unknown"
        )
        return self._file(self.runs_dir / "failures", f"{safe_run}_{safe_step}", ".json")

    @property
    def runs_index_path(self) -> Path:
        return self.runs_dir / "index.jsonl"

    # ── 上下文编译产物（派生数据，不属于权威层） ────────────────
    @property
    def contexts_dir(self) -> Path:
        return self._directory(WorkspaceDirs.CONTEXTS)

    def context_package_path(self, event_id: str) -> Path:
        return self._file(self.contexts_dir, event_id, ".context.json")

    @property
    def status_card_index_path(self) -> Path:
        return self.contexts_dir / "status_card_index.json"

    # ── 缓存 ──────────────────────────────────────────────────
    @property
    def cache_dir(self) -> Path:
        return self._directory(WorkspaceDirs.CACHE)

    def llm_cache_path(self, cache_key: str) -> Path:
        return self._file(self.cache_dir, f"llm_{cache_key}", ".json")

    def search_cache_path(self, cache_key: str) -> Path:
        return self._file(self.cache_dir, f"srch_{cache_key}", ".json")

    # ── SQLite 索引 ───────────────────────────────────────────
    @property
    def index_db_path(self) -> Path:
        return self._directory(WorkspaceDirs.INDEX_DB)
