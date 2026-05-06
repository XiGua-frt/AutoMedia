"""知识库管理 API。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse

from app.deps import get_knowledge_service
from app.exceptions import ErrorCode, throw_if
from app.schemas.common import BaseResponse
from app.schemas.knowledge import (
    DeleteResponse,
    DocumentSummary,
    ListResponse,
    UploadAcceptedData,
    UploadRequest,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/upload")
async def upload_knowledge(
    body: UploadRequest,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """异步入库：立即返回 202 与 ``task_id``，实际入库在后台执行。"""
    src = (body.source or "").strip()
    st = (body.source_type or "").strip()
    throw_if(not src, ErrorCode.PARAMS_ERROR, "source 不能为空")
    throw_if(not st, ErrorCode.PARAMS_ERROR, "sourceType 不能为空")

    task_id = str(uuid.uuid4())
    background_tasks.add_task(
        KnowledgeService.ingest_background,
        task_id,
        src,
        st,
        body.hint,
    )
    payload = BaseResponse.success(
        data=UploadAcceptedData(task_id=task_id).model_dump(by_alias=True),
        message="accepted",
    ).model_dump()
    return JSONResponse(status_code=202, content=payload)


@router.get("/list", response_model=BaseResponse[ListResponse])
async def list_knowledge_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    platform: str | None = None,
    style: str | None = None,
    quality_score_min: int | None = Query(
        None,
        ge=0,
        alias="qualityScoreMin",
    ),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> BaseResponse[ListResponse]:
    """分页查询知识库文档。"""
    raw = await service.list_documents(
        page,
        page_size,
        {
            "platform": platform,
            "style": style,
            "quality_score_min": quality_score_min,
        },
    )
    items = [DocumentSummary.model_validate(x) for x in raw["items"]]
    data = ListResponse(
        items=items,
        total=raw["total"],
        page=raw["page"],
    )
    return BaseResponse.success(data=data)


@router.delete("/{doc_id}", response_model=BaseResponse[DeleteResponse])
async def delete_knowledge_document(
    doc_id: str,
    service: KnowledgeService = Depends(get_knowledge_service),
) -> BaseResponse[DeleteResponse]:
    """删除指定知识库文档（MySQL + Qdrant）。"""
    await service.delete_document(doc_id)
    return BaseResponse.success(
        data=DeleteResponse(success=True, message="已删除"),
    )
