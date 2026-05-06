"""知识库 API 请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class UploadRequest(BaseModel):
    """知识库入库请求。"""

    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(..., min_length=1, description="来源：路径 / URL / 文本内容等")
    source_type: str = Field(
        ...,
        alias="sourceType",
        description="来源类型：file_pdf/file_md/file_txt/url/text 等",
    )
    hint: Optional[dict[str, Any]] = Field(
        default=None,
        description="元数据提取时的附加提示",
    )


class UploadAcceptedData(BaseModel):
    """异步入库已受理时返回的数据。"""

    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(..., alias="taskId")


class DocumentSummary(BaseModel):
    """知识库文档列表摘要。"""

    model_config = ConfigDict(populate_by_name=True)

    doc_id: str = Field(..., alias="docId")
    title: Optional[str] = None
    platform: Optional[str] = None
    style: Optional[str] = None
    quality_score: Optional[int] = Field(default=None, alias="qualityScore")
    source_type: Optional[str] = Field(default=None, alias="sourceType")
    create_time: Optional[datetime] = Field(default=None, alias="createTime")


class ListResponse(BaseModel):
    """知识库文档分页列表。"""

    model_config = ConfigDict(populate_by_name=True)

    items: list[DocumentSummary]
    total: int
    page: int


class DeleteResponse(BaseModel):
    """删除操作结果。"""

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    message: str
