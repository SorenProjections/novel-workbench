"""搜索/RAG 适配器包（当前版本 RAG 跳过，仅 Noop 实现）。"""

from novelwb.adapters.search.base import SearchAdapter, SearchResult
from novelwb.adapters.search.noop import NoopSearchAdapter

__all__ = ["SearchAdapter", "SearchResult", "NoopSearchAdapter"]
