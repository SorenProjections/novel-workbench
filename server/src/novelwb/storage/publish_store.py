"""PublishStore — 章节发布层读写。

存储格式：
  publish/{chapter_id}.md          — 正文 Markdown
  publish/{chapter_id}.meta.json   — ChapterCommitRecord 元数据
  publish/index.jsonl              — 发布索引（chapter_id / event_id / created_at）
"""

from __future__ import annotations

from typing import Any

from novelwb.core.schemas.domain_models import ChapterCommitRecord
from novelwb.storage.locks import lock_path
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.io_atomic import atomic_write_json, atomic_write_text, read_json
from novelwb.utils.jsonl import append_jsonl, read_jsonl_all, read_last_jsonl
from novelwb.utils.timeutil import to_iso
from novelwb.utils.transactions import guarded_store


@guarded_store
class PublishStore:
    """管理 publish/ 目录：正文 .md、元数据 .meta.json 及 index.jsonl。"""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self._layout = layout

    # ── 写入 ────────────────────────────────────────────────────

    def publish(self, record: ChapterCommitRecord, markdown: str) -> None:
        """原子发布章节：写正文 + 元数据 + 追加索引。"""
        md_path = self._layout.chapter_publish_path(record.chapter_id)
        meta_path = self._layout.chapter_meta_path(record.chapter_id)

        with lock_path(md_path):
            atomic_write_text(md_path, markdown)
            atomic_write_json(meta_path, record.model_dump(mode="json"))
            self._append_index(record)

    def _append_index(self, record: ChapterCommitRecord) -> None:
        entry = {
            "chapter_id": record.chapter_id,
            "event_id": getattr(record, "event_id", None),
            "chapter_index": record.chapter_index,
            "created_at": to_iso(record.committed_at)
            if record.committed_at and not isinstance(record.committed_at, str)
            else (record.committed_at or ""),
        }
        append_jsonl(self._layout.publish_index_path, entry)

    # ── 读取正文 ─────────────────────────────────────────────────

    def load_markdown(self, chapter_id: str) -> str:
        path = self._layout.chapter_publish_path(chapter_id)
        return path.read_text(encoding="utf-8")

    def load_markdown_optional(self, chapter_id: str) -> str | None:
        path = self._layout.chapter_publish_path(chapter_id)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    # ── 读取元数据 ───────────────────────────────────────────────

    def load_meta(self, chapter_id: str) -> ChapterCommitRecord:
        path = self._layout.chapter_meta_path(chapter_id)
        data = read_json(path)
        return ChapterCommitRecord.model_validate(data)

    def load_meta_optional(self, chapter_id: str) -> ChapterCommitRecord | None:
        path = self._layout.chapter_meta_path(chapter_id)
        if not path.exists():
            return None
        return ChapterCommitRecord.model_validate(read_json(path))

    def exists(self, chapter_id: str) -> bool:
        return self._layout.chapter_publish_path(chapter_id).exists()

    # ── 索引 ────────────────────────────────────────────────────

    def list_index(self) -> list[dict[str, Any]]:
        return read_jsonl_all(self._layout.publish_index_path)

    def load_latest_meta(self) -> ChapterCommitRecord | None:
        row = read_last_jsonl(self._layout.publish_index_path)
        if row is None:
            return None
        return self.load_meta(row["chapter_id"])

    def chapter_count(self) -> int:
        indexes = set()
        for row in self.list_index():
            chapter_id = row.get("chapter_id")
            if not chapter_id:
                continue
            meta = self.load_meta_optional(chapter_id)
            chapter_index = (
                getattr(meta, "chapter_index", row.get("chapter_index", 0))
                if meta
                else row.get("chapter_index", 0)
            )
            if chapter_index:
                indexes.add(int(chapter_index))
        return len(indexes)
