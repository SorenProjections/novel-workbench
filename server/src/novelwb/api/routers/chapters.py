"""章节查询路由 /projects/{project_id}/chapters。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from novelwb.api.deps import ok, require_project

router = APIRouter(
    prefix="/projects/{project_id}/chapters",
    tags=["chapters"],
    dependencies=[Depends(require_project)],
)


@router.get("")
def list_chapters(project_id: str) -> dict[str, Any]:
    """列出项目所有已发布章节。"""
    from novelwb.storage import PublishStore

    layout = require_project(project_id)
    if not layout.project_dir.exists():
        raise HTTPException(404, f"项目不存在: {project_id}")
    store = PublishStore(layout)
    latest_by_index = {}
    for row in store.list_index():
        chapter_id = row.get("chapter_id")
        if chapter_id:
            meta = store.load_meta_optional(chapter_id)
            chapter_index = (
                getattr(meta, "chapter_index", row.get("chapter_index", 0))
                if meta
                else row.get("chapter_index", 0)
            )
            latest_by_index[int(chapter_index or 0)] = (row, meta)

    records = []
    for _, (row, meta) in sorted(latest_by_index.items()):
        chapter_id = row.get("chapter_id")
        item = dict(row)
        if chapter_id and meta:
            item.update(
                {
                    "chapter_index": meta.chapter_index,
                    "chapter_intent": getattr(meta.chapter_intent, "value", meta.chapter_intent),
                    "word_count": meta.word_count,
                    "source_event_ids": meta.source_event_ids,
                    "committed_at": meta.committed_at,
                }
            )
        records.append(item)
    records.sort(key=lambda r: (r.get("chapter_index") or 0, r.get("created_at") or ""))
    return ok(records)


@router.get("/{chapter_id}")
def get_chapter(project_id: str, chapter_id: str) -> dict[str, Any]:
    """获取单章内容。"""
    from novelwb.storage import PublishStore

    layout = require_project(project_id)
    if not layout.project_dir.exists():
        raise HTTPException(404, f"项目不存在: {project_id}")
    store = PublishStore(layout)
    text = store.load_markdown_optional(chapter_id)
    if text is None:
        raise HTTPException(404, f"章节不存在: {chapter_id}")
    return ok({"chapter_id": chapter_id, "text": text})
