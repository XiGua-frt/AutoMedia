"""RAG 文档切分器（两级切分）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain.schema import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from app.rag.exceptions import ChunkError
from app.rag.logging import RAGLoggerMixin


class DocumentChunker(RAGLoggerMixin):
    """两级切分策略实现。

    Level 1 使用 ``MarkdownHeaderTextSplitter`` 保留章节结构；
    Level 2 使用 ``RecursiveCharacterTextSplitter`` 控制 chunk 长度。

    每个 chunk 会继承文档级 metadata，并自动补充：
    - ``chunk_index``: 序号（从 0 开始）
    - ``section_title``: 所属标题（优先 H3 -> H2 -> H1）
    - ``chunk_type``: ``body`` / ``title_block`` / ``summary``
    - ``char_count``: 字符数
    """

    def __init__(
        self,
        headers_to_split: list[tuple[str, str]] | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50,
    ) -> None:
        """初始化切分器配置。

        Args:
            headers_to_split: Markdown 标题层级配置。默认值为
                ``[("#", "H1"), ("##", "H2"), ("###", "H3")]``。
            chunk_size: 二级切分单块最大字符数。
            chunk_overlap: 二级切分块间重叠字符数。
            min_chunk_size: 低于该字符数的块会并入前一个块。
        """
        self._headers_to_split = headers_to_split or [
            ("#", "H1"),
            ("##", "H2"),
            ("###", "H3"),
        ]
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._min_chunk_size = min_chunk_size

    def split(
        self,
        content: str,
        base_metadata: dict[str, Any],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> list[Document]:
        """执行两级切分并返回 chunk 列表。

        Args:
            content: 清洗后的 Markdown 文本。
            base_metadata: 文档级元数据，将继承到每个 chunk。
            chunk_size: 运行时覆盖的 chunk 大小（可选）。
            chunk_overlap: 运行时覆盖的 chunk 重叠（可选）。

        Returns:
            切分后的 ``Document`` 列表，metadata 已补齐。

        Raises:
            ChunkError: 输入非法或切分过程出错时抛出。
        """
        start = datetime.now()
        if not isinstance(content, str):
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                error_message="content 必须为字符串",
            )
            raise ChunkError("content 必须为字符串")
        if not isinstance(base_metadata, dict):
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                error_message="base_metadata 必须为 dict",
            )
            raise ChunkError("base_metadata 必须为 dict")

        normalized = content.strip()
        if not normalized:
            self.log_to_db(
                "SUCCESS",
                start,
                datetime.now(),
                input_data="empty_content",
                output_data="chunk_count=0",
            )
            return []

        size = chunk_size if chunk_size is not None else self._chunk_size
        overlap = chunk_overlap if chunk_overlap is not None else self._chunk_overlap
        if size <= 0:
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                error_message="chunk_size 必须大于 0",
            )
            raise ChunkError("chunk_size 必须大于 0")
        if overlap < 0:
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                error_message="chunk_overlap 不能为负数",
            )
            raise ChunkError("chunk_overlap 不能为负数")
        if overlap >= size:
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                error_message="chunk_overlap 必须小于 chunk_size",
            )
            raise ChunkError("chunk_overlap 必须小于 chunk_size")

        try:
            header_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=self._headers_to_split,
                strip_headers=False,
            )
            level1_docs = header_splitter.split_text(normalized)
            if not level1_docs:
                level1_docs = [Document(page_content=normalized, metadata={})]

            char_splitter = RecursiveCharacterTextSplitter(
                chunk_size=size,
                chunk_overlap=overlap,
                length_function=len,
            )

            out: list[Document] = []
            for sec_doc in level1_docs:
                section_meta = dict(base_metadata)
                section_meta.update(sec_doc.metadata or {})
                section_title = self._extract_section_title(section_meta)
                chunk_type = self._infer_chunk_type(
                    section_title=section_title,
                    section_content=sec_doc.page_content,
                )

                split_docs = char_splitter.create_documents(
                    texts=[sec_doc.page_content],
                    metadatas=[section_meta],
                )
                for part in split_docs:
                    meta = dict(part.metadata or {})
                    text = part.page_content
                    meta["section_title"] = section_title
                    meta["chunk_type"] = chunk_type
                    meta["char_count"] = len(text)
                    out.append(Document(page_content=text, metadata=meta))

            merged = self._merge_short_chunks(out)
            for idx, doc in enumerate(merged):
                doc.metadata["chunk_index"] = idx
                doc.metadata["char_count"] = len(doc.page_content)
            self.log_to_db(
                "SUCCESS",
                start,
                datetime.now(),
                input_data=(
                    f"text_len={len(content)}, chunk_size={size}, "
                    f"chunk_overlap={overlap}"
                ),
                output_data=f"chunk_count={len(merged)}",
            )
            return merged
        except ChunkError:
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                input_data=(
                    f"text_len={len(content)}, chunk_size={size}, "
                    f"chunk_overlap={overlap}"
                ),
                error_message="ChunkError",
            )
            raise
        except Exception as exc:  # noqa: BLE001
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                input_data=(
                    f"text_len={len(content)}, chunk_size={size}, "
                    f"chunk_overlap={overlap}"
                ),
                error_message=str(exc),
            )
            raise ChunkError(f"文档切分失败: {exc}") from exc

    def run(self, input: Any) -> Any:
        """实现 ``BasePipelineStep`` 兼容入口。

        输入格式支持：
        - ``{"content": str, "base_metadata": dict, "chunk_size": int?, "chunk_overlap": int?}``

        Args:
            input: Pipeline 上一步输出对象。

        Returns:
            ``list[Document]``。

        Raises:
            ChunkError: 输入结构不符合预期时抛出。
        """
        if not isinstance(input, dict):
            raise ChunkError("DocumentChunker.run 输入必须为 dict")
        return self.split(
            content=input.get("content", ""),
            base_metadata=input.get("base_metadata", {}),
            chunk_size=input.get("chunk_size"),
            chunk_overlap=input.get("chunk_overlap"),
        )

    def _merge_short_chunks(self, docs: list[Document]) -> list[Document]:
        """将过短 chunk 合并到前一个 chunk，减少碎片。

        Args:
            docs: 初次切分得到的文档块列表。

        Returns:
            合并后的文档块列表。
        """
        if not docs:
            return []

        merged: list[Document] = []
        for doc in docs:
            text = doc.page_content
            if len(text) < self._min_chunk_size and merged:
                prev = merged[-1]
                combined_text = f"{prev.page_content}\n{text}".strip()
                combined_meta = dict(prev.metadata)
                combined_meta["char_count"] = len(combined_text)
                merged[-1] = Document(
                    page_content=combined_text,
                    metadata=combined_meta,
                )
            else:
                merged.append(doc)
        return merged

    @staticmethod
    def _extract_section_title(metadata: dict[str, Any]) -> str:
        """从标题层级元数据中提取章节标题。"""
        for key in ("H3", "H2", "H1"):
            val = metadata.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return "未命名章节"

    @staticmethod
    def _infer_chunk_type(section_title: str, section_content: str) -> str:
        """推断 chunk 类型。"""
        title_lower = section_title.lower()
        if any(k in title_lower for k in ("summary", "abstract", "总结", "摘要")):
            return "summary"
        stripped = section_content.strip()
        if stripped.startswith("#"):
            return "title_block"
        return "body"
