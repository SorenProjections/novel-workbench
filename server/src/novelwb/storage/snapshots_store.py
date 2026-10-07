"""SnapshotsStore — PreSnapshot / PostSnapshot 存储。

存储格式：
  snapshots/{snapshot_key}.json — 单个 StateSnapshot
snapshot_key 格式由调用方决定，推荐：
  pre_{event_id}   — 事件前快照
  post_{event_id}  — 事件后快照（若需要）
"""

from __future__ import annotations

from novelwb.core.schemas.domain_models import StateSnapshot
from novelwb.storage.locks import lock_path
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.io_atomic import atomic_write_json, read_json
from novelwb.utils.transactions import guarded_store


@guarded_store
class SnapshotsStore:
    """管理 snapshots/ 目录下的 StateSnapshot 文件。"""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self._layout = layout

    # ── 写入 ────────────────────────────────────────────────────

    def save(self, snapshot: StateSnapshot, snapshot_key: str) -> None:
        path = self._layout.snapshot_path(snapshot_key)
        with lock_path(path):
            atomic_write_json(path, snapshot.model_dump(mode="json"))

    def save_pre(self, snapshot: StateSnapshot, event_id: str) -> None:
        self.save(snapshot, f"pre_{event_id}")

    def save_post(self, snapshot: StateSnapshot, event_id: str) -> None:
        self.save(snapshot, f"post_{event_id}")

    def save_latest(self, snapshot: StateSnapshot) -> None:
        self.save(snapshot, "latest")

    # ── 读取 ────────────────────────────────────────────────────

    def load(self, snapshot_key: str) -> StateSnapshot:
        path = self._layout.snapshot_path(snapshot_key)
        data = read_json(path)
        return StateSnapshot.model_validate(data)

    def load_optional(self, snapshot_key: str) -> StateSnapshot | None:
        if not self._layout.snapshot_path(snapshot_key).exists():
            return None
        return self.load(snapshot_key)

    def load_pre(self, event_id: str) -> StateSnapshot | None:
        return self.load_optional(f"pre_{event_id}")

    def load_post(self, event_id: str) -> StateSnapshot | None:
        return self.load_optional(f"post_{event_id}")

    def load_latest(self) -> StateSnapshot | None:
        return self.load_optional("latest")

    def exists(self, snapshot_key: str) -> bool:
        return self._layout.snapshot_path(snapshot_key).exists()
