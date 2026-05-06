"""知识库业务服务（入库、列表、删除）。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.exceptions import BusinessException, ErrorCode
from app.rag.pipeline import IngestionResult, RAGIngestionPipeline, create_default_pipeline

_LOGGER = logging.getLogger(__name__)


class KnowledgeService:
    """知识库管理：入库编排、文档分页查询、文档与向量删除。"""

    def __init__(self, pipeline: RAGIngestionPipeline, db_session: Session) -> None:
        """初始化服务。

        Args:
            pipeline: RAG 入库流水线实例（与 db_session 对应同一连接会话）。
            db_session: SQLAlchemy 同步 Session，用于列表与删除等直连 SQL。
        """
        self._pipeline = pipeline
        self._db = db_session

    async def ingest(
        self,
        source: str,
        source_type: str,
        hint: dict[str, Any] | None,
    ) -> IngestionResult:
        """触发入库并返回结果。

        Args:
            source: 输入源（路径 / URL / 文本）。
            source_type: 来源类型，与 ``RAGIngestionPipeline.run`` 约定一致。
            hint: 元数据提取附加提示。

        Returns:
            入库流水线执行结果。
        """
        return await self._pipeline.run(
            source=source,
            source_type=source_type,
            hint=hint,
            dry_run=False,
        )

    @staticmethod
    async def ingest_background(
        task_id: str,
        source: str,
        source_type: str,
        hint: dict[str, Any] | None,
    ) -> None:
        """在独立 Session 中执行入库，供 BackgroundTasks 调用。

        与请求级 ``KnowledgeService`` 解耦，避免响应结束后 Session 已关闭。

        Args:
            task_id: 客户端关联用的任务 ID（仅用于日志）。
            source: 输入源。
            source_type: 来源类型。
            hint: 元数据提取附加提示。
        """
        db = SessionLocal()
        try:
            pipeline = create_default_pipeline(settings, db)
            await pipeline.run(
                source=source,
                source_type=source_type,
                hint=hint,
                dry_run=False,
            )
            _LOGGER.info("知识库入库完成 task_id=%s", task_id)
        except Exception:
            _LOGGER.exception("知识库入库失败 task_id=%s", task_id)
        finally:
            db.close()

    async def list_documents(
        self,
        page: int,
        page_size: int,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        """分页查询 ``knowledge_document`` 表。

        Args:
            page: 页码，从 1 开始。
            page_size: 每页条数。
            filters: 过滤条件，支持 ``platform``、``style``、``quality_score_min``。

        Returns:
            包含 ``items``、``total``、``page`` 的字典，结构与列表 API 一致。
        """
        return await asyncio.to_thread(
            self._list_documents_sync,
            page,
            page_size,
            filters,
        )

    def _list_documents_sync(
        self,
        page: int,
        page_size: int,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        """同步执行分页查询（在线程池中由 ``list_documents`` 调用）。"""
        if page < 1 or page_size < 1:
            raise BusinessException(ErrorCode.PARAMS_ERROR, "page 与 page_size 必须为正整数")

        platform = filters.get("platform")
        style = filters.get("style")
        quality_min = filters.get("quality_score_min")

        where_clauses = ["status = 'active'"]
        params: dict[str, Any] = {}

        if platform:
            where_clauses.append("platform = :platform")
            params["platform"] = platform
        if style:
            where_clauses.append("style = :style")
            params["style"] = style
        if quality_min is not None:
            where_clauses.append("quality_score >= :qmin")
            params["qmin"] = float(quality_min)

        where_sql = " AND ".join(where_clauses)
        offset = (page - 1) * page_size
        params["limit"] = page_size
        params["offset"] = offset

        count_sql = text(f"SELECT COUNT(*) AS c FROM knowledge_document WHERE {where_sql}")
        list_sql = text(
            f"""
            SELECT id, title, platform, style, quality_score, source_type, created_at
            FROM knowledge_document
            WHERE {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
            """,
        )

        total = int(self._db.execute(count_sql, params).scalar_one())

        rows = self._db.execute(list_sql, params).mappings().all()
        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "doc_id": str(row["id"]),
                    "title": row["title"],
                    "platform": row["platform"],
                    "style": row["style"],
                    "quality_score": row["quality_score"],
                    "source_type": row["source_type"],
                    "create_time": row["created_at"],
                },
            )

        return {"items": items, "total": total, "page": page}

    async def delete_document(self, doc_id: str) -> None:
        """删除文档：先删 Qdrant 点，再删 MySQL chunk 与 document。

        Args:
            doc_id: ``knowledge_document.id``（UUID 字符串）。

        Raises:
            BusinessException: 参数非法或文档不存在。
        """
        await asyncio.to_thread(self._delete_document_sync, doc_id)

    def _delete_document_sync(self, doc_id: str) -> None:
        """同步删除逻辑。"""
        doc_id_stripped = (doc_id or "").strip()
        try:
            uuid.UUID(doc_id_stripped)
        except ValueError as exc:
            raise BusinessException(
                ErrorCode.PARAMS_ERROR,
                "doc_id 必须为合法 UUID",
            ) from exc

        exists = self._db.execute(
            text("SELECT 1 FROM knowledge_document WHERE id = :id LIMIT 1"),
            {"id": doc_id_stripped},
        ).first()
        if not exists:
            raise BusinessException(ErrorCode.NOT_FOUND_ERROR, "知识库文档不存在")

        rows = self._db.execute(
            text(
                "SELECT qdrant_point_id FROM knowledge_chunk WHERE doc_id = :doc_id",
            ),
            {"doc_id": doc_id_stripped},
        ).fetchall()
        point_ids = [str(r[0]) for r in rows if r[0]]

        try:
            self._pipeline.vector_store.delete(point_ids)
        except Exception as exc:
            _LOGGER.warning("Qdrant 删除失败 doc_id=%s: %s", doc_id_stripped, exc)
            raise BusinessException(
                ErrorCode.OPERATION_ERROR,
                f"向量库删除失败: {exc}",
            ) from exc

        try:
            self._db.execute(
                text("DELETE FROM knowledge_document WHERE id = :id"),
                {"id": doc_id_stripped},
            )
            self._db.commit()
        except Exception as exc:
            self._db.rollback()
            raise BusinessException(
                ErrorCode.OPERATION_ERROR,
                f"MySQL 删除失败: {exc}",
            ) from exc
