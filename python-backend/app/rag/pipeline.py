"""RAG 入库与检索流水线编排器。"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from langchain.schema import Document
from openai import OpenAI
from sqlalchemy import text

from app.rag.embedding.dashscope_embeddings import DashScopeEmbeddings
from app.rag.ingestion.chunker import DocumentChunker
from app.rag.ingestion.document_loader import DocumentLoader
from app.rag.ingestion.metadata_extractor import MetadataExtractor
from app.rag.ingestion.summary_generator import SummaryGenerator
from app.rag.ingestion.text_cleaner import TextCleaner
from app.rag.logging import set_rag_trace
from app.rag.vectorstore.qdrant_store import QdrantVectorStore


@dataclass
class IngestionResult:
    """入库流水线执行结果。"""

    doc_id: str
    chunk_count: int
    metadata: dict
    duration_seconds: float
    status: Literal["success", "partial", "failed"]


@dataclass
class RAGContext:
    """检索流水线输出上下文。"""

    query: str
    rewritten_query: str
    documents: list[Document]
    packed_context: Any


class RAGIngestionPipeline:
    """完整入库流程编排器。"""

    def __init__(
        self,
        loader: DocumentLoader,
        cleaner: TextCleaner,
        metadata_extractor: MetadataExtractor,
        summary_generator: SummaryGenerator,
        chunker: DocumentChunker,
        embedder: DashScopeEmbeddings,
        vector_store: QdrantVectorStore,
        db_session: Any,
    ) -> None:
        """初始化入库流水线依赖。

        Args:
            loader: 文档加载器。
            cleaner: 文本清洗器。
            metadata_extractor: 元数据提取器。
            summary_generator: 摘要与爆款要素生成器。
            chunker: 文档切分器。
            embedder: 向量化器。
            vector_store: 向量库存储器。
            db_session: SQLAlchemy Session（同步）实例。
        """
        self.loader = loader
        self.cleaner = cleaner
        self.metadata_extractor = metadata_extractor
        self.summary_generator = summary_generator
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store
        self.db_session = db_session

    async def run(
        self,
        source: str,
        source_type: str,
        hint: dict | None = None,
        dry_run: bool = False,
    ) -> IngestionResult:
        """执行完整入库流程。

        Args:
            source: 输入源（路径/URL/文本）。
            source_type: 输入类型（file_pdf/file_md/file_txt/url/text）。
            hint: 提取元数据时的附加提示（可选）。
            dry_run: 为 True 时跳过向量库与 MySQL 写入。

        Returns:
            入库执行结果。

        Raises:
            Exception: 任一步骤失败时抛出对应模块异常（不吞异常）。
        """
        started = time.perf_counter()
        trace_id = str(uuid.uuid4())
        set_rag_trace(trace_id=trace_id, doc_id="pending")

        # 1. load
        raw_markdown = self.loader.load(source=source, source_type=source_type)

        # 2. clean
        cleaned_markdown = self.cleaner.clean(raw_markdown)

        # 3. metadata extract
        metadata = self.metadata_extractor.extract(cleaned_markdown, hint=hint)
        metadata["source_type"] = source_type
        if source_type == "url":
            metadata["source_url"] = source

        # 4. summary
        summary = self.summary_generator.generate(cleaned_markdown, metadata=metadata)

        # 5. chunk
        base_chunk_metadata = {
            "platform": metadata.get("platform"),
            "category": metadata.get("category"),
            "style": metadata.get("style"),
            "tags": metadata.get("tags", []),
            "quality_score": metadata.get("quality_score"),
        }
        chunks = self.chunker.split(
            content=cleaned_markdown,
            base_metadata=base_chunk_metadata,
        )

        # 6. embeddings
        chunk_texts = [doc.page_content for doc in chunks]
        embeddings = self.embedder.embed_documents(chunk_texts)

        # 7 + 8. 写库（支持 dry_run）
        if dry_run:
            elapsed = time.perf_counter() - started
            return IngestionResult(
                doc_id="dry_run",
                chunk_count=len(chunks),
                metadata=metadata,
                duration_seconds=elapsed,
                status="partial",
            )

        doc_uuid = str(uuid.uuid4())
        for doc in chunks:
            md = dict(doc.metadata or {})
            md["doc_id"] = doc_uuid
            doc.metadata = md

        point_ids = self.vector_store.add_documents(chunks, embeddings)
        doc_id = self._write_mysql(
            doc_uuid=doc_uuid,
            metadata=metadata,
            summary=summary,
            chunks=chunks,
            point_ids=point_ids,
        )
        set_rag_trace(trace_id=trace_id, doc_id=doc_id)

        elapsed = time.perf_counter() - started
        return IngestionResult(
            doc_id=doc_id,
            chunk_count=len(chunks),
            metadata=metadata,
            duration_seconds=elapsed,
            status="success",
        )

    def _write_mysql(
        self,
        doc_uuid: str,
        metadata: dict,
        summary: dict,
        chunks: list[Document],
        point_ids: list[str],
    ) -> str:
        """写入 knowledge_document 与 knowledge_chunk。

        Args:
            doc_uuid: 文档主键 UUID（与 Qdrant chunk metadata 中 doc_id 一致）。
            metadata: 元数据提取结果。
            summary: 摘要生成结果。
            chunks: 文档分块。
            point_ids: Qdrant point_id 列表。

        Returns:
            新增 knowledge_document 的主键 ID（UUID 字符串）。
        """
        if len(chunks) != len(point_ids):
            raise ValueError(
                f"chunks 与 point_ids 长度不一致: {len(chunks)} != {len(point_ids)}",
            )

        title_raw = (metadata.get("title") or "").strip()
        title = title_raw if title_raw else "未命名文档"
        qs_raw = metadata.get("quality_score")
        quality_score = float(qs_raw) if qs_raw is not None else None

        doc_sql = text(
            """
            INSERT INTO knowledge_document
            (id, title, platform, category, style, source_type, source_url, quality_score, tags,
             summary, structure_summary, viral_elements, status)
            VALUES
            (:id, :title, :platform, :category, :style, :source_type, :source_url, :quality_score, :tags,
             :summary, :structure_summary, :viral_elements, :status)
            """,
        )
        self.db_session.execute(
            doc_sql,
            {
                "id": doc_uuid,
                "title": title,
                "platform": metadata.get("platform"),
                "category": metadata.get("category"),
                "style": metadata.get("style"),
                "source_type": (metadata.get("source_type") or "")[:20] or None,
                "source_url": metadata.get("source_url"),
                "quality_score": quality_score,
                "tags": json.dumps(metadata.get("tags", []), ensure_ascii=False),
                "summary": summary.get("summary"),
                "structure_summary": summary.get("structure_summary"),
                "viral_elements": json.dumps(
                    summary.get("viral_elements", []),
                    ensure_ascii=False,
                ),
                "status": "active",
            },
        )

        chunk_sql = text(
            """
            INSERT INTO knowledge_chunk
            (id, doc_id, chunk_index, section_title, chunk_type, content, keywords, qdrant_point_id)
            VALUES
            (:id, :doc_id, :chunk_index, :section_title, :chunk_type, :content, :keywords, :qdrant_point_id)
            """,
        )
        for chunk, point_id in zip(chunks, point_ids, strict=True):
            chunk_uuid = str(uuid.uuid4())
            body = chunk.page_content or ""
            self.db_session.execute(
                chunk_sql,
                {
                    "id": chunk_uuid,
                    "doc_id": doc_uuid,
                    "chunk_index": int(chunk.metadata.get("chunk_index", 0)),
                    "section_title": chunk.metadata.get("section_title"),
                    "chunk_type": (chunk.metadata.get("chunk_type") or "")[:20] or None,
                    "content": body,
                    "keywords": json.dumps(
                        chunk.metadata.get("tags", []),
                        ensure_ascii=False,
                    ),
                    "qdrant_point_id": (point_id or "")[:36] or None,
                },
            )
        self.db_session.commit()
        return doc_uuid


class RAGRetrievalPipeline:
    """完整检索流程编排器（骨架）。"""

    def __init__(
        self,
        query_rewriter: Any,
        vector_store: QdrantVectorStore,
        embedder: DashScopeEmbeddings,
        context_packer: Any,
    ) -> None:
        """初始化检索流水线依赖。"""
        self.query_rewriter = query_rewriter
        self.vector_store = vector_store
        self.embedder = embedder
        self.context_packer = context_packer

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> RAGContext:
        """执行检索流程骨架。"""
        rewritten_queries = self.query_rewriter.rewrite(query)
        embed_text = (
            rewritten_queries[0]
            if rewritten_queries
            else (query or "").strip()
        )
        query_vec = self.embedder.embed_query(embed_text)
        docs = self.vector_store.mmr_search(
            query_vector=query_vec,
            top_k=top_k,
            filters=filters,
        )
        packed = self.context_packer.pack(docs)
        rewritten_query_str = (
            " | ".join(rewritten_queries) if rewritten_queries else (query or "")
        )
        return RAGContext(
            query=query,
            rewritten_query=rewritten_query_str,
            documents=docs,
            packed_context=packed,
        )


def create_default_pipeline(config: Any, db_session: Any) -> RAGIngestionPipeline:
    """创建默认入库流水线实例（依赖注入工厂）。"""
    llm_client = OpenAI(
        api_key=config.dashscope_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    loader = DocumentLoader()
    cleaner = TextCleaner()
    metadata_extractor = MetadataExtractor(llm_client=llm_client, model="qwen-plus")
    summary_generator = SummaryGenerator(llm_client=llm_client, model="qwen-plus")
    chunker = DocumentChunker()
    embedder = DashScopeEmbeddings(api_key=config.dashscope_api_key)
    vector_store = QdrantVectorStore(
        host=config.qdrant_host,
        port=config.qdrant_port,
        collection_name=config.qdrant_collection,
        vector_size=1024,
        distance="Cosine",
    )
    return RAGIngestionPipeline(
        loader=loader,
        cleaner=cleaner,
        metadata_extractor=metadata_extractor,
        summary_generator=summary_generator,
        chunker=chunker,
        embedder=embedder,
        vector_store=vector_store,
        db_session=db_session,
    )
