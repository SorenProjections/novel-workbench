"""SearchAdapter 抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """单条搜索结果。"""

    doc_id: str
    text: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchAdapter(ABC):
    """搜索/RAG 适配器抽象接口。

    当前版本 RAG 跳过，由 NoopSearchAdapter 实现（返回空列表）。
    将来接入真实向量数据库时实现此接口。
    """

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """执行语义检索，返回最多 top_k 条结果。

        Args:
            query: 查询文本。
            top_k: 最大返回条数。

        Returns:
            SearchResult 列表（按相关度降序）。
        """

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """返回适配器类型标识，与 SearchAdapterType 枚举值对应。"""
