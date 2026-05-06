"""RAG（检索增强生成）模块。

提供面向爆款文章创作的知识库能力，包括文档入库、
向量化、混合检索、以及与 Agent 编排层的集成。

本包导出所有自定义异常类和 Protocol 接口契约。
"""

from app.rag.base import (
    BaseEmbedder,
    BasePipelineStep,
    BaseRetriever,
    BaseVectorStore,
)
from app.rag.exceptions import (
    ChunkError,
    DocumentLoadError,
    EmbeddingError,
    MetadataExtractError,
    RAGBaseException,
    RetrievalError,
    TextCleanError,
    VectorStoreError,
)
from app.rag.logging import RAGLoggerMixin, get_rag_trace, set_rag_trace

__all__ = [
    # Protocol 接口
    "BaseEmbedder",
    "BasePipelineStep",
    "BaseRetriever",
    "BaseVectorStore",
    # 异常类
    "ChunkError",
    "DocumentLoadError",
    "EmbeddingError",
    "MetadataExtractError",
    "RAGBaseException",
    "RetrievalError",
    "TextCleanError",
    "VectorStoreError",
    # 日志与 trace
    "RAGLoggerMixin",
    "set_rag_trace",
    "get_rag_trace",
]
