"""时间工具 — 统一使用 UTC，ISO8601 格式。"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """返回当前 UTC 时间（带时区信息）。"""
    return datetime.now(tz=UTC)


def utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO8601 字符串。"""
    return utcnow().isoformat()


def to_iso(dt: datetime) -> str:
    """datetime 转 ISO8601 字符串（强制 UTC）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def from_iso(s: str) -> datetime:
    """ISO8601 字符串转 UTC datetime。"""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def elapsed_ms(start: datetime, end: datetime | None = None) -> int:
    """计算两个时间点之间的毫秒数。"""
    if end is None:
        end = utcnow()
    return int((end - start).total_seconds() * 1000)
