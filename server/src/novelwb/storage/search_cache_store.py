"""SearchCacheStore — 搜索/RAG 响应缓存（当前 RAG 已跳过，Noop 实现）。

当 SearchAdapterType.NOOP 时所有方法均为空操作。
接口与 LlmCacheStore 对称，便于将来接入真实 RAG 时替换。
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from novelwb.core.constants import Defaults
from novelwb.storage.workspace_layout import WorkspaceLayout
from novelwb.utils.hashing import stable_hash
from novelwb.utils.io_atomic import atomic_write_json, read_json
from novelwb.utils.timeutil import to_iso, utcnow


@dataclass
class SearchCacheEntry:
    cache_key: str
    query: str
    results: list[Any]  # 原始搜索结果列表（JSON 可序列化）
    cached_at: str
    ttl_seconds: int
    expires_at: float


def _make_search_key(query: str, top_k: int) -> str:
    payload = f"{query}|top_k={top_k}"
    return stable_hash(payload)[:32]


class SearchCacheStore:
    """搜索缓存 Store。

    当 RAG 跳过时（默认），所有操作均为 Noop，不会写磁盘。
    通过 enabled=True 激活真实缓存（供将来 RAG 实现使用）。
    """

    def __init__(
        self,
        layout: WorkspaceLayout,
        ttl_seconds: int = Defaults.LLM_CACHE_TTL_SECONDS,
        enabled: bool = False,  # RAG 跳过期间保持 False
    ) -> None:
        self._layout = layout
        self._ttl = ttl_seconds
        self._enabled = enabled

    # ── 读取 ────────────────────────────────────────────────────

    def get(self, query: str, top_k: int = 5) -> SearchCacheEntry | None:
        """返回有效缓存；未启用 / 未命中 / 过期均返回 None。"""
        if not self._enabled:
            return None
        key = _make_search_key(query, top_k)
        path = self._layout.search_cache_path(key)
        if not path.exists():
            return None
        try:
            data = read_json(path)
            entry = SearchCacheEntry(**data)
        except Exception:
            path.unlink(missing_ok=True)
            return None
        if time.time() > entry.expires_at:
            path.unlink(missing_ok=True)
            return None
        return entry

    # ── 写入 ────────────────────────────────────────────────────

    def put(self, query: str, results: list[Any], top_k: int = 5) -> SearchCacheEntry | None:
        """写入搜索缓存；未启用时直接返回 None。"""
        if not self._enabled:
            return None
        key = _make_search_key(query, top_k)
        now_ts = time.time()
        entry = SearchCacheEntry(
            cache_key=key,
            query=query,
            results=results,
            cached_at=to_iso(utcnow()),
            ttl_seconds=self._ttl,
            expires_at=now_ts + self._ttl,
        )
        path = self._layout.search_cache_path(key)
        atomic_write_json(path, asdict(entry))
        return entry

    # ── 清理 ────────────────────────────────────────────────────

    def clear_all(self) -> int:
        if not self._enabled:
            return 0
        count = 0
        for p in self._layout.cache_dir.glob("srch_*.json"):
            p.unlink(missing_ok=True)
            count += 1
        return count

    def evict_expired(self) -> int:
        if not self._enabled:
            return 0
        count = 0
        now_ts = time.time()
        for p in self._layout.cache_dir.glob("srch_*.json"):
            try:
                data = read_json(p)
                if now_ts > data.get("expires_at", 0):
                    p.unlink(missing_ok=True)
                    count += 1
            except Exception:
                p.unlink(missing_ok=True)
                count += 1
        return count

    def stats(self) -> dict[str, Any]:
        if not self._enabled:
            return {"enabled": False, "total": 0, "expired": 0, "valid": 0}
        total = 0
        expired = 0
        now_ts = time.time()
        for p in self._layout.cache_dir.glob("srch_*.json"):
            total += 1
            try:
                data = read_json(p)
                if now_ts > data.get("expires_at", 0):
                    expired += 1
            except Exception:
                expired += 1
        return {"enabled": True, "total": total, "expired": expired, "valid": total - expired}
