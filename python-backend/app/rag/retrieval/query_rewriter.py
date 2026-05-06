"""检索 Query 改写模块。"""

from __future__ import annotations

import re
from datetime import datetime

from app.rag.logging import RAGLoggerMixin


class QueryRewriter(RAGLoggerMixin):
    """将用户选题改写为检索友好的多路 query。"""

    _STOPWORDS = {
        "的",
        "了",
        "和",
        "与",
        "及",
        "在",
        "是",
        "把",
        "将",
        "让",
        "就",
        "都",
        "也",
        "还",
        "吗",
        "呢",
        "啊",
        "呀",
        "请",
        "如何",
        "怎么",
        "怎样",
        "一个",
        "一些",
        "以及",
        "对于",
        "关于",
    }

    _TITLE_TEMPLATES = (
        "为什么说{topic}正在悄悄改变行业格局？",
        "{topic}的底层逻辑：从入门到实战的一套方法",
        "{topic}怎么做才有效？这份清单直接拿去用",
    )

    def rewrite(self, query: str) -> list[str]:
        """改写 query 并生成多路检索表达。

        Args:
            query: 用户原始查询。

        Returns:
            改写后的查询列表。第一条始终是原始 query。
        """
        start = datetime.now()
        try:
            normalized_query = (query or "").strip()
            rewritten: list[str] = [normalized_query]

            if not normalized_query:
                self.log_to_db(
                    "SUCCESS",
                    start,
                    datetime.now(),
                    input_data="empty_query",
                    output_data="rewrite_count=1",
                )
                return rewritten

            for template in self._TITLE_TEMPLATES:
                rewritten.append(template.format(topic=normalized_query))

            keyword_query = self._extract_keywords(normalized_query)
            rewritten.append(keyword_query if keyword_query else normalized_query)

            # 去重并保持顺序，避免模板和关键词 query 重复。
            deduplicated: list[str] = []
            seen: set[str] = set()
            for candidate in rewritten:
                if candidate not in seen:
                    deduplicated.append(candidate)
                    seen.add(candidate)
            end = datetime.now()
            self.log_to_db(
                "SUCCESS",
                start,
                end,
                input_data=self._truncate_for_log(normalized_query),
                output_data=f"rewrite_count={len(deduplicated)}",
            )
            return deduplicated
        except Exception as e:
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                input_data=self._truncate_for_log((query or "").strip()),
                error_message=str(e),
            )
            raise

    def _extract_keywords(self, query: str) -> str:
        """提取关键词表达，尽量去除常见虚词。

        Args:
            query: 原始查询文本。

        Returns:
            空格分隔的关键词字符串。
        """
        tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", query)
        keywords: list[str] = []

        for token in tokens:
            if token in self._STOPWORDS:
                continue
            if len(token) == 1 and re.fullmatch(r"[\u4e00-\u9fff]", token):
                # 单字中文通常信息量较低，默认过滤。
                continue
            keywords.append(token)

        return " ".join(keywords)

    def _truncate_for_log(self, text: str, max_len: int = 500) -> str:
        """截断过长文本，避免落库 input 过大。"""
        if len(text) <= max_len:
            return text
        return text[:max_len] + "…"
