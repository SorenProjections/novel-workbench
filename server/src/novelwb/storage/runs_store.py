"""RunsStore — 运行记录的读写与索引。"""

from __future__ import annotations

from typing import Any

from novelwb.core.schemas.domain_models import RunManifest
from novelwb.storage.locks import lock_path
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.io_atomic import atomic_write_json, read_json
from novelwb.utils.jsonl import append_jsonl, read_jsonl_all, read_last_jsonl
from novelwb.utils.timeutil import to_iso, utcnow
from novelwb.utils.transactions import guarded_store


@guarded_store
class RunsStore:
    """管理 runs/ 目录下的 RunManifest 文件及 index.jsonl。"""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self._layout = layout

    # ── 写入 ────────────────────────────────────────────────────

    def save(self, manifest: RunManifest) -> None:
        """将 RunManifest 原子写入磁盘并更新索引。"""
        path = self._layout.run_manifest_path(manifest.run_id)
        with lock_path(path):
            atomic_write_json(path, manifest.model_dump(mode="json"))
            self._upsert_index(manifest)

    def _upsert_index(self, manifest: RunManifest) -> None:
        """追加或更新 index.jsonl 中的轻量摘要行。"""
        entry = {
            "run_id": manifest.run_id,
            "project_id": manifest.project_id,
            "status": manifest.status,
            "created_at": to_iso(manifest.started_at)
            if hasattr(manifest, "started_at")
            else to_iso(utcnow()),
            "updated_at": to_iso(utcnow()),
        }
        append_jsonl(self._layout.runs_index_path, entry)

    # ── 读取 ────────────────────────────────────────────────────

    def load(self, run_id: str) -> RunManifest:
        path = self._layout.run_manifest_path(run_id)
        data = read_json(path)
        return RunManifest.model_validate(data)

    def exists(self, run_id: str) -> bool:
        return self._layout.run_manifest_path(run_id).exists()

    def load_latest(self) -> RunManifest | None:
        """从索引末行取最新 run_id，再加载完整清单。"""
        row = read_last_jsonl(self._layout.runs_index_path)
        if row is None:
            return None
        return self.load(row["run_id"])

    def list_index(self) -> list[dict[str, Any]]:
        """返回 index.jsonl 中所有摘要行（轻量列表）。"""
        return read_jsonl_all(self._layout.runs_index_path)
