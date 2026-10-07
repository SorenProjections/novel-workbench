"""EventsStore — 事件层读写。

存储格式：
  events/{event_id}.json      — 单个 EventRecord 完整体
  events/index.jsonl          — 轻量索引（event_id / status / chapter_ids）
"""

from __future__ import annotations

from typing import Any

from novelwb.core.schemas.domain_models import EventRecord
from novelwb.storage.locks import lock_path
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.io_atomic import atomic_write_json, read_json
from novelwb.utils.jsonl import append_jsonl, read_jsonl_all, read_last_jsonl
from novelwb.utils.timeutil import to_iso
from novelwb.utils.transactions import guarded_store


@guarded_store
class EventsStore:
    """管理 events/ 目录下的 EventRecord 文件及 index.jsonl。"""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self._layout = layout

    # ── 写入 ────────────────────────────────────────────────────

    def save(self, record: EventRecord) -> None:
        """原子写入事件记录，并追加索引行。"""
        path = self._layout.event_path(record.event_id)
        with lock_path(path):
            atomic_write_json(path, record.model_dump(mode="json"))
            self._append_index(record)

    def _append_index(self, record: EventRecord) -> None:
        entry = {
            "event_id": record.event_id,
            "committed_by_run_id": getattr(record, "committed_by_run_id", ""),
            "committed_at": to_iso(record.committed_at)
            if hasattr(record, "committed_at")
            and record.committed_at
            and not isinstance(record.committed_at, str)
            else (record.committed_at or ""),
        }
        append_jsonl(self._layout.events_index_path, entry)

    # ── 读取 ────────────────────────────────────────────────────

    def load(self, event_id: str) -> EventRecord:
        path = self._layout.event_path(event_id)
        data = read_json(path)
        return EventRecord.model_validate(data)

    def exists(self, event_id: str) -> bool:
        return self._layout.event_path(event_id).exists()

    def load_optional(self, event_id: str) -> EventRecord | None:
        if not self.exists(event_id):
            return None
        return self.load(event_id)

    def load_latest(self) -> EventRecord | None:
        row = read_last_jsonl(self._layout.events_index_path)
        if row is None:
            return None
        return self.load(row["event_id"])

    def list_index(self) -> list[dict[str, Any]]:
        return read_jsonl_all(self._layout.events_index_path)

    def list_by_run(self, run_id: str) -> list[EventRecord]:
        """返回属于指定 run_id 的所有事件（按索引顺序）。"""
        index = self.list_index()
        records = []
        for row in index:
            if row.get("committed_by_run_id") == run_id:
                rec = self.load_optional(row["event_id"])
                if rec is not None:
                    records.append(rec)
        return records
