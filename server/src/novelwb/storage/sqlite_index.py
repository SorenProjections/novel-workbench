"""SqliteIndex — 可搜索索引（SQLite），从文件系统重建。

表结构（仅供查询加速，非权威数据）：
  runs(run_id, project_id, status, created_at)
  events(event_id, run_id, status, created_at)
  chapters(chapter_id, event_id, chapter_index, created_at)
  auth_objects(object_type, object_id, version_seq, created_at)
"""

from __future__ import annotations

import sqlite3
from typing import Any

from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.jsonl import read_jsonl


class SqliteIndex:
    """SQLite 辅助索引，用于快速列表查询与统计。

    所有数据均可从 jsonl 文件重建，SQLite 不是权威来源。
    """

    def __init__(self, layout: WorkspaceLayout) -> None:
        self._layout = layout
        self._db_path = layout.index_db_path
        self._conn: sqlite3.Connection | None = None

    # ── 连接管理 ─────────────────────────────────────────────────

    def connect(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._init_schema()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> SqliteIndex:
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── 建表 ────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        assert self._conn is not None
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id      TEXT PRIMARY KEY,
                project_id  TEXT,
                status      TEXT,
                created_at  TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id    TEXT PRIMARY KEY,
                run_id      TEXT,
                status      TEXT,
                created_at  TEXT
            );
            CREATE TABLE IF NOT EXISTS chapters (
                chapter_id      TEXT PRIMARY KEY,
                event_id        TEXT,
                chapter_index   INTEGER,
                created_at      TEXT
            );
            CREATE TABLE IF NOT EXISTS auth_objects (
                object_type TEXT,
                object_id   TEXT,
                version_seq INTEGER,
                created_at  TEXT,
                PRIMARY KEY (object_type, version_seq)
            );
            CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
            CREATE INDEX IF NOT EXISTS idx_chapters_event ON chapters(event_id);
        """)
        self._conn.commit()

    # ── 重建 ────────────────────────────────────────────────────

    def rebuild(self) -> None:
        """从 jsonl 文件全量重建索引（清空后重新插入）。"""
        self.connect()
        assert self._conn is not None
        cur = self._conn.cursor()

        cur.executescript(
            "DELETE FROM runs; DELETE FROM events; DELETE FROM chapters; DELETE FROM auth_objects;"
        )

        # runs
        for row in read_jsonl(self._layout.runs_index_path):
            cur.execute(
                "INSERT OR REPLACE INTO runs VALUES (?,?,?,?)",
                (
                    row.get("run_id"),
                    row.get("project_id"),
                    row.get("status"),
                    row.get("created_at"),
                ),
            )

        # events
        for row in read_jsonl(self._layout.events_index_path):
            cur.execute(
                "INSERT OR REPLACE INTO events VALUES (?,?,?,?)",
                (row.get("event_id"), row.get("run_id"), row.get("status"), row.get("created_at")),
            )

        # chapters
        for row in read_jsonl(self._layout.publish_index_path):
            cur.execute(
                "INSERT OR REPLACE INTO chapters VALUES (?,?,?,?)",
                (
                    row.get("chapter_id"),
                    row.get("event_id"),
                    row.get("chapter_index"),
                    row.get("created_at"),
                ),
            )

        # auth_objects — 从 auth/*.jsonl 历史行中读取
        for hist_path in sorted(self._layout.auth_dir.glob("*.jsonl")):
            object_type = hist_path.stem  # e.g. "BIBLE"
            for seq, row in enumerate(read_jsonl(hist_path)):
                cur.execute(
                    "INSERT OR REPLACE INTO auth_objects VALUES (?,?,?,?)",
                    (object_type, row.get("object_id"), seq, row.get("created_at")),
                )

        self._conn.commit()

    # ── 查询 ────────────────────────────────────────────────────

    def _fetch(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.connect()
        assert self._conn is not None
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def list_runs(self) -> list[dict[str, Any]]:
        return self._fetch("SELECT * FROM runs ORDER BY created_at DESC")

    def list_events(self, run_id: str | None = None) -> list[dict[str, Any]]:
        if run_id:
            return self._fetch("SELECT * FROM events WHERE run_id=? ORDER BY created_at", (run_id,))
        return self._fetch("SELECT * FROM events ORDER BY created_at")

    def list_chapters(self, event_id: str | None = None) -> list[dict[str, Any]]:
        if event_id:
            return self._fetch(
                "SELECT * FROM chapters WHERE event_id=? ORDER BY chapter_index",
                (event_id,),
            )
        return self._fetch("SELECT * FROM chapters ORDER BY chapter_index")

    def chapter_count(self) -> int:
        self.connect()
        assert self._conn is not None
        row = self._conn.execute("SELECT COUNT(*) FROM chapters").fetchone()
        return int(row[0]) if row else 0

    def run_count(self) -> int:
        self.connect()
        assert self._conn is not None
        row = self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()
        return int(row[0]) if row else 0
