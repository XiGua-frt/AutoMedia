"""检索结果上下文打包模块。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from langchain.schema import Document

from app.rag.logging import RAGLoggerMixin


@dataclass
class RAGContext:
    """注入 ArticleState 的检索结果。"""

    title_patterns: list[str]
    structures: list[str]
    key_quotes: list[str]
    reference_cases: list[str]
    raw_chunks: list[Document]
    source_doc_ids: list[str]


class ContextPacker(RAGLoggerMixin):
    """将检索到的 chunks 整理为可注入的大模型上下文。"""

    def __init__(self, max_tokens: int = 3000) -> None:
        """初始化打包器。

        Args:
            max_tokens: reference_cases 的最大 token 预算。
        """
        self.max_tokens = max_tokens

    def pack(self, docs: list[Document]) -> RAGContext:
        """按 chunk_type 分类聚合并控制 body 内容 token。

        Args:
            docs: 检索得到的文档块列表。

        Returns:
            分类聚合后的 RAGContext。
        """
        start = datetime.now()
        try:
            title_patterns: list[str] = []
            structures: list[str] = []
            key_quotes: list[str] = []
            reference_cases: list[str] = []
            source_doc_ids: list[str] = []

            used_tokens = 0
            for doc in docs:
                chunk_type = str(doc.metadata.get("chunk_type", "")).strip().lower()
                content = doc.page_content.strip()
                if not content:
                    continue

                doc_id = self._extract_doc_id(doc)
                if doc_id and doc_id not in source_doc_ids:
                    source_doc_ids.append(doc_id)

                if chunk_type == "title_block":
                    title_patterns.extend(self._split_lines(content))
                    continue

                if chunk_type == "summary":
                    summary_lines = self._split_lines(content)
                    if summary_lines:
                        structures.append(summary_lines[0])
                        key_quotes.extend(summary_lines[1:])
                    continue

                if chunk_type == "body":
                    remaining_tokens = self.max_tokens - used_tokens
                    if remaining_tokens <= 0:
                        break

                    clipped = self._clip_by_token_budget(content, remaining_tokens)
                    if clipped:
                        reference_cases.append(clipped)
                        used_tokens += self._estimate_tokens(clipped)

            ctx = RAGContext(
                title_patterns=self._dedupe_keep_order(title_patterns),
                structures=self._dedupe_keep_order(structures),
                key_quotes=self._dedupe_keep_order(key_quotes),
                reference_cases=self._dedupe_keep_order(reference_cases),
                raw_chunks=docs,
                source_doc_ids=source_doc_ids,
            )
            end = datetime.now()
            self.log_to_db(
                "SUCCESS",
                start,
                end,
                input_data=f"doc_count={len(docs)},max_tokens={self.max_tokens}",
                output_data=(
                    f"title_patterns={len(ctx.title_patterns)},"
                    f"structures={len(ctx.structures)},"
                    f"key_quotes={len(ctx.key_quotes)},"
                    f"reference_cases={len(ctx.reference_cases)},"
                    f"source_doc_ids={len(ctx.source_doc_ids)}"
                ),
            )
            return ctx
        except Exception as e:
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                input_data=f"doc_count={len(docs)},max_tokens={self.max_tokens}",
                error_message=str(e),
            )
            raise

    def _extract_doc_id(self, doc: Document) -> str:
        """从 metadata 提取文档 ID。"""
        for key in ("doc_id", "source_doc_id", "knowledge_doc_id"):
            value = doc.metadata.get(key)
            if value:
                return str(value)
        return ""

    def _split_lines(self, content: str) -> list[str]:
        """按换行拆分并清洗条目。"""
        return [line.strip("-* \t") for line in content.splitlines() if line.strip()]

    def _estimate_tokens(self, text: str) -> int:
        """粗略估算 token 数量（中文场景近似）。"""
        return max(1, len(text) // 2)

    def _clip_by_token_budget(self, text: str, remaining_tokens: int) -> str:
        """根据剩余 token 预算裁剪文本。"""
        if self._estimate_tokens(text) <= remaining_tokens:
            return text
        max_chars = max(1, remaining_tokens * 2)
        return text[:max_chars].rstrip()

    def _dedupe_keep_order(self, items: list[str]) -> list[str]:
        """去重并保持原有顺序。"""
        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item and item not in seen:
                result.append(item)
                seen.add(item)
        return result
