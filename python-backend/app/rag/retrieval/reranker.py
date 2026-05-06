"""Reranker 抽象与一期占位实现。"""

from __future__ import annotations

from typing import Protocol

from langchain.schema import Document


class BaseReranker(Protocol):
    """重排序器接口契约。"""

    def rerank(self, query: str, docs: list[Document], top_n: int) -> list[Document]:
        """按照 query 相关性对 docs 重排序并截断。"""
        ...


class PassthroughReranker:
    """第一期占位，直接返回原列表。"""

    def rerank(self, query: str, docs: list[Document], top_n: int) -> list[Document]:
        """不做重排序，直接保留前 top_n 条。"""
        del query
        return docs[:top_n]
