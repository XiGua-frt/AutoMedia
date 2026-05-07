"""Reranker 抽象与实现。"""

from __future__ import annotations

from typing import Protocol

from langchain.schema import Document

from app.rag.exceptions import RetrievalError
from app.rag.logging import RAGLoggerMixin


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


class CrossEncoderReranker(RAGLoggerMixin):
    """基于 sentence-transformers CrossEncoder 的本地重排序器。"""

    def __init__(
        self,
        model_name: str,
        max_length: int = 512,
        batch_size: int = 16,
        stage_name: str = "cross_encoder_v1",
    ) -> None:
        """初始化 CrossEncoder 重排序器。

        Args:
            model_name: CrossEncoder 模型名称或本地路径。
            max_length: 输入最大长度。
            batch_size: 批大小。
            stage_name: 写入 metadata 的重排阶段标识。
        """
        try:
            from sentence_transformers import CrossEncoder
        except Exception as exc:  # noqa: BLE001
            raise RetrievalError(
                "未安装 sentence-transformers，无法启用 CrossEncoder 重排",
            ) from exc

        self._model_name = model_name
        self._max_length = max(32, int(max_length))
        self._batch_size = max(1, int(batch_size))
        self._stage_name = stage_name
        try:
            self._model = CrossEncoder(
                model_name,
                max_length=self._max_length,
            )
        except Exception as exc:  # noqa: BLE001
            raise RetrievalError(f"CrossEncoder 模型加载失败: {exc}") from exc

    def rerank(self, query: str, docs: list[Document], top_n: int) -> list[Document]:
        """按 query 对文档重排并写入相关性分数。

        Args:
            query: 用户查询。
            docs: 候选文档列表。
            top_n: 返回数量上限。

        Returns:
            重排后的文档列表。
        """
        normalized_query = (query or "").strip()
        if not normalized_query or not docs:
            return docs[:top_n]

        pairs = [
            (normalized_query, (doc.page_content or "")[: self._max_length * 2])
            for doc in docs
        ]
        try:
            scores: list[float] = self._model.predict(
                pairs,
                batch_size=self._batch_size,
                show_progress_bar=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise RetrievalError(f"CrossEncoder 推理失败: {exc}") from exc

        scored_docs: list[tuple[float, Document]] = []
        for doc, score in zip(docs, scores, strict=False):
            md = dict(doc.metadata or {})
            md["relevance_score"] = float(score)
            md["rerank_model"] = self._model_name
            md["rerank_stage"] = self._stage_name
            doc.metadata = md
            scored_docs.append((float(score), doc))

        scored_docs.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in scored_docs[:top_n]]
