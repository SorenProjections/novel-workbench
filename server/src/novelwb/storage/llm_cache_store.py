"""LlmCacheStore — LLM 响应磁盘缓存。

缓存键：SHA256(prompt_key + prompt_version + rendered_prompt + cache_variant)
存储格式：cache/llm_{cache_key}.json
TTL：Defaults.LLM_CACHE_TTL_SECONDS（默认7天），在读取时检查。
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
class LlmCacheEntry:
    cache_key: str
    prompt_key: str
    prompt_version: str
    response_text: str
    cached_at: str  # ISO8601
    ttl_seconds: int
    expires_at: float  # Unix timestamp（用于快速过期检查）
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


def _make_cache_key(
    prompt_key: str,
    prompt_version: str,
    rendered_prompt: str,
    cache_variant: str = "",
) -> str:
    """生成缓存键：对 (prompt_key, prompt_version, rendered_prompt) 做稳定哈希。"""
    payload = f"{prompt_key}|{prompt_version}|{cache_variant}|{rendered_prompt}"
    return stable_hash(payload)[:32]


class LlmCacheStore:
    """管理 LLM 响应的磁盘缓存。

    - 命中：返回 LlmCacheEntry
    - 未命中 / 已过期：返回 None，调用方负责发起真实 LLM 调用后写回
    """

    def __init__(
        self,
        layout: WorkspaceLayout,
        ttl_seconds: int = Defaults.LLM_CACHE_TTL_SECONDS,
    ) -> None:
        self._layout = layout
        self._ttl = ttl_seconds

    # ── 读取 ────────────────────────────────────────────────────

    def get(
        self,
        prompt_key: str,
        prompt_version: str,
        rendered_prompt: str,
        cache_variant: str = "",
    ) -> LlmCacheEntry | None:
        """返回有效缓存条目，过期或不存在时返回 None。"""
        key = _make_cache_key(prompt_key, prompt_version, rendered_prompt, cache_variant)
        path = self._layout.llm_cache_path(key)
        if not path.exists():
            return None
        try:
            data = read_json(path)
            entry = LlmCacheEntry(**data)
        except Exception:
            # 损坏的缓存文件 → 视为未命中
            path.unlink(missing_ok=True)
            return None
        if time.time() > entry.expires_at:
            path.unlink(missing_ok=True)
            return None
        return entry

    # ── 写入 ────────────────────────────────────────────────────

    def put(
        self,
        prompt_key: str,
        prompt_version: str,
        rendered_prompt: str,
        response_text: str,
        cache_variant: str = "",
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> LlmCacheEntry:
        """将 LLM 响应写入缓存并返回条目。"""
        key = _make_cache_key(prompt_key, prompt_version, rendered_prompt, cache_variant)
        now_ts = time.time()
        entry = LlmCacheEntry(
            cache_key=key,
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            response_text=response_text,
            cached_at=to_iso(utcnow()),
            ttl_seconds=self._ttl,
            expires_at=now_ts + self._ttl,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        path = self._layout.llm_cache_path(key)
        atomic_write_json(path, asdict(entry))
        return entry

    # ── 删除 ────────────────────────────────────────────────────

    def invalidate(
        self,
        prompt_key: str,
        prompt_version: str,
        rendered_prompt: str,
        cache_variant: str = "",
    ) -> None:
        key = _make_cache_key(prompt_key, prompt_version, rendered_prompt, cache_variant)
        self._layout.llm_cache_path(key).unlink(missing_ok=True)

    def clear_all(self) -> int:
        """清空全部 LLM 缓存文件，返回删除数量。"""
        count = 0
        for p in self._layout.cache_dir.glob("llm_*.json"):
            p.unlink(missing_ok=True)
            count += 1
        return count

    def evict_expired(self) -> int:
        """删除已过期的缓存条目，返回删除数量。"""
        count = 0
        now_ts = time.time()
        for p in self._layout.cache_dir.glob("llm_*.json"):
            try:
                data = read_json(p)
                if now_ts > data.get("expires_at", 0):
                    p.unlink(missing_ok=True)
                    count += 1
            except Exception:
                p.unlink(missing_ok=True)
                count += 1
        return count

    # ── 统计 ────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        total = 0
        expired = 0
        now_ts = time.time()
        for p in self._layout.cache_dir.glob("llm_*.json"):
            total += 1
            try:
                data = read_json(p)
                if now_ts > data.get("expires_at", 0):
                    expired += 1
            except Exception:
                expired += 1
        return {"total": total, "expired": expired, "valid": total - expired}
