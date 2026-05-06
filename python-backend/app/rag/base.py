"""RAG 模块接口契约（Protocol 定义）。

本模块使用 typing.Protocol 定义 RAG 各核心组件的接口，
具体实现类只需满足结构化子类型（structural subtyping）即可，
无需显式继承，便于后续替换底层实现（如从 DashScope 切换到 OpenAI）。

依赖：
- 仅使用 Python 标准库 + langchain.schema.Document
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from langchain.schema import Document


@runtime_checkable
class BaseEmbedder(Protocol):
    """文本向量化接口。

    职责：将文本转换为稠密向量表示。

    使用场景：
    - 入库时对 chunk 批量向量化（embed_documents）
    - 检索时对用户 query 向量化（embed_query）

    实现示例：DashScopeEmbedder、OpenAIEmbedder 等。
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量将文本列表转换为向量。

        Args:
            texts: 待向量化的文本列表。

        Returns:
            与 texts 等长的向量列表，每个向量为 float 数组。

        Raises:
            EmbeddingError: Embedding 服务调用失败时抛出。
        """
        ...

    def embed_query(self, text: str) -> list[float]:
        """将单条查询文本转换为向量。

        Args:
            text: 待向量化的查询文本。

        Returns:
            查询文本对应的向量（float 数组）。

        Raises:
            EmbeddingError: Embedding 服务调用失败时抛出。
        """
        ...


@runtime_checkable
class BaseVectorStore(Protocol):
    """向量存储接口。

    职责：管理向量的持久化存储与相似度检索。

    使用场景：
    - 入库阶段：将 Document + Embedding 写入向量库
    - 检索阶段：根据 query 向量做 Top-K 相似度搜索
    - 管理阶段：按 ID 删除过期或低质量文档

    实现示例：QdrantVectorStore、FAISSVectorStore 等。
    """

    def add_documents(
        self,
        docs: list[Document],
        embeddings: list[list[float]],
    ) -> list[str]:
        """将文档及其向量写入向量库。

        Args:
            docs: LangChain Document 列表，每个 Document 包含
                page_content 和 metadata。
            embeddings: 与 docs 一一对应的向量列表。

        Returns:
            写入成功后返回的文档 ID 列表（与 docs 等长）。

        Raises:
            VectorStoreError: 向量库写入失败时抛出。
        """
        ...

    def similarity_search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[Document]:
        """基于向量相似度检索文档。

        Args:
            query_vector: 查询向量。
            top_k: 返回的最大文档数量。
            filters: 可选的元数据过滤条件，键值对形式，
                如 ``{"platform": "zhihu", "quality_score__gte": 7}``。

        Returns:
            按相似度降序排列的 Document 列表。

        Raises:
            VectorStoreError: 向量库查询失败时抛出。
        """
        ...

    def delete(self, ids: list[str]) -> None:
        """按 ID 批量删除向量库中的文档。

        Args:
            ids: 待删除的文档 ID 列表。

        Raises:
            VectorStoreError: 向量库删除操作失败时抛出。
        """
        ...


@runtime_checkable
class BaseRetriever(Protocol):
    """检索器接口。

    职责：封装"query → 相关文档"的完整检索流程，
    内部可组合 Embedding、VectorStore、Rerank 等组件。

    使用场景：
    - 作为 Agent 编排层调用的统一检索入口
    - 内部可实现 Query Rewrite → Hybrid Search → MMR → Rerank 等流程

    实现示例：HybridRetriever、SimpleRetriever 等。
    """

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[Document]:
        """根据查询文本检索相关文档。

        Args:
            query: 用户查询文本（原始自然语言）。
            top_k: 返回的最大文档数量。
            filters: 可选的元数据过滤条件。

        Returns:
            按相关性降序排列的 Document 列表。

        Raises:
            RetrievalError: 检索过程中任一环节失败时抛出。
        """
        ...


@runtime_checkable
class BasePipelineStep(Protocol):
    """Pipeline 步骤统一接口。

    职责：定义 RAG 入库 / 检索流水线中每个步骤的通用契约，
    使各步骤可按需组合、替换、重排。

    使用场景：
    - 入库 Pipeline：LoadStep → CleanStep → MetadataStep → ChunkStep → EmbedStep → StoreStep
    - 检索 Pipeline：RewriteStep → SearchStep → RerankStep → PackStep

    实现示例：TextCleanStep、MetadataExtractStep、ChunkStep 等。
    """

    def run(self, input: Any) -> Any:
        """执行当前步骤的处理逻辑。

        Args:
            input: 上一步的输出，具体类型由 Pipeline 编排决定。

        Returns:
            当前步骤的处理结果，将传递给下一步。

        Raises:
            RAGBaseException: 步骤执行失败时抛出对应的子类异常。
        """
        ...
