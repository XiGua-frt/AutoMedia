"""Agent 0：RAG 检索，为后续标题 / 大纲生成提供素材上下文。"""

from __future__ import annotations

from typing import Any

from app.rag.pipeline import RAGRetrievalPipeline
from app.schemas.article import ArticleState


class RAGRetrieverAgent:
    """在 phase1（标题生成）前执行检索，将结果写入 ``ArticleState.rag_context``。"""

    def __init__(self, retrieval_pipeline: RAGRetrievalPipeline) -> None:
        """初始化 Agent。

        Args:
            retrieval_pipeline: RAG 检索流水线实例。
        """
        self._retrieval_pipeline = retrieval_pipeline

    async def execute(self, state: ArticleState) -> ArticleState:
        """根据选题与可选元数据过滤条件执行检索并写回状态。

        Args:
            state: 文章编排状态；读取 ``topic``、``platform``（若存在）、``style``。

        Returns:
            同一 ``state`` 引用，便于链式调用。
        """
        query = (state.topic or "").strip()
        if not query:
            state.rag_context = None
            return state

        filters = self._build_filters(state)
        rag_ctx = await self._retrieval_pipeline.retrieve(
            query=query,
            top_k=5,
            filters=filters,
        )
        state.rag_context = rag_ctx
        return state

    def _build_filters(self, state: ArticleState) -> dict[str, Any] | None:
        """从状态中组装 Qdrant Payload 过滤字段。"""
        flt: dict[str, Any] = {}
        platform = getattr(state, "platform", None)
        if platform:
            flt["platform"] = platform
        style = getattr(state, "style", None)
        if style:
            flt["style"] = style
        return flt if flt else None
