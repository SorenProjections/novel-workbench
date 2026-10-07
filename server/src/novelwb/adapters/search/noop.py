"""NoopSearchAdapter — RAG 跳过占位实现。

所有 search() 调用均返回空列表，不抛出异常。
将来启用真实 RAG 时替换此类即可，框架代码无需修改。
"""

from __future__ import annotations

from novelwb.adapters.search.base import SearchAdapter, SearchResult
from novelwb.core.constants import SearchAdapterType


class NoopSearchAdapter(SearchAdapter):
    """Noop 搜索适配器，始终返回空结果。"""

    @property
    def adapter_type(self) -> str:
        return SearchAdapterType.NOOP

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        # RAG 当前版本跳过，直接返回空列表
        return []
