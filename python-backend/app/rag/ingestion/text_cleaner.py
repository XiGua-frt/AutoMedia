"""正文清洗器：去除噪声并规范化文本。"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.rag.exceptions import TextCleanError
from app.rag.logging import RAGLoggerMixin


class TextCleaner(RAGLoggerMixin):
    """正文清洗器。

    默认规则顺序：
    1. 去除 HTML 标签残留
    2. 去除广告关键词段落
    3. 去除页眉页脚特征行
    4. 去除无意义短行
    5. 规范化标点与空格
    6. 合并连续空行（>2 行合并为 1 行）
    """

    def __init__(self, ad_keywords: list[str] | None = None) -> None:
        """初始化清洗器。

        Args:
            ad_keywords: 广告关键词列表；为空时使用内置默认词典。
        """
        self._ad_keywords = ad_keywords or [
            "关注",
            "点赞",
            "转发",
            "扫码",
            "广告",
            "推广",
            "商务合作",
            "点击链接",
            "立即购买",
            "领取优惠",
        ]
        self._rules: list[tuple[str, Callable[[str], str]]] = [
            ("strip_html_tags", self._strip_html_tags),
            ("remove_ad_paragraphs", self._remove_ad_paragraphs),
            ("remove_header_footer", self._remove_header_footer),
            ("remove_meaningless_short_lines", self._remove_meaningless_short_lines),
            ("normalize_punctuation", self._normalize_punctuation),
            ("collapse_blank_lines", self._collapse_blank_lines),
        ]

    def clean(self, text: str) -> str:
        """执行清洗规则链。

        Args:
            text: 待清洗 Markdown 文本。

        Returns:
            清洗后的文本。

        Raises:
            TextCleanError: 输入非法或规则执行失败时抛出。
        """
        start = datetime.now()
        if not isinstance(text, str):
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                error_message="text 必须为字符串",
            )
            raise TextCleanError("text 必须为字符串")
        try:
            out = text
            for _, rule in self._rules:
                out = rule(out)
            result = out.strip()
            self.log_to_db(
                "SUCCESS",
                start,
                datetime.now(),
                input_data=f"text_len={len(text)}",
                output_data=f"text_len={len(result)}",
            )
            return result
        except TextCleanError:
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                input_data=f"text_len={len(text)}",
                error_message="TextCleanError",
            )
            raise
        except Exception as exc:  # noqa: BLE001
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                input_data=f"text_len={len(text)}",
                error_message=str(exc),
            )
            raise TextCleanError(f"文本清洗失败: {exc}") from exc

    def run(self, input: Any) -> Any:
        """实现 ``BasePipelineStep`` 兼容入口。

        Args:
            input: 文本字符串，或 ``{'text': str}`` 字典。

        Returns:
            清洗后的文本字符串。
        """
        if isinstance(input, str):
            return self.clean(input)
        if isinstance(input, dict):
            return self.clean(str(input.get("text", "")))
        raise TextCleanError("TextCleaner.run 输入必须为 str 或 {'text': str}")

    def add_rule(self, rule_fn: Callable[[str], str], name: str) -> None:
        """动态添加清洗规则。

        Args:
            rule_fn: 规则函数，输入输出均为字符串。
            name: 规则名称，仅用于调试标识。

        Raises:
            TextCleanError: 规则函数不可调用或名称为空时抛出。
        """
        if not callable(rule_fn):
            raise TextCleanError("rule_fn 必须可调用")
        if not name.strip():
            raise TextCleanError("name 不能为空")
        self._rules.append((name, rule_fn))

    def _strip_html_tags(self, text: str) -> str:
        """去除 HTML 标签残留。"""
        return re.sub(r"<[^>]+>", "", text)

    def _remove_ad_paragraphs(self, text: str) -> str:
        """去除包含广告词的段落。"""
        lines = text.splitlines()
        out: list[str] = []
        for line in lines:
            normalized = line.strip()
            if not normalized:
                out.append("")
                continue
            if any(k in normalized for k in self._ad_keywords):
                continue
            out.append(line)
        return "\n".join(out)

    def _collapse_blank_lines(self, text: str) -> str:
        """将连续空行压缩为单空行。"""
        return re.sub(r"\n{3,}", "\n\n", text)

    def _remove_meaningless_short_lines(self, text: str) -> str:
        """去除无意义短行（小于 5 字且不含标点）。"""
        punctuation = set("，。！？；：,.!?;:")
        lines = text.splitlines()
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                out.append("")
                continue
            if len(stripped) < 5 and not any(ch in punctuation for ch in stripped):
                continue
            out.append(line)
        return "\n".join(out)

    def _normalize_punctuation(self, text: str) -> str:
        """规范化标点与空白。"""
        trans = str.maketrans(
            {
                "，": ",",
                "。": ".",
                "：": ":",
                "；": ";",
                "！": "!",
                "？": "?",
                "（": "(",
                "）": ")",
                "【": "[",
                "】": "]",
                "“": '"',
                "”": '"',
                "‘": "'",
                "’": "'",
                "　": " ",
            },
        )
        out = text.translate(trans)
        out = re.sub(r"[ \t]+", " ", out)
        out = re.sub(r" *\n *", "\n", out)
        return out

    def _remove_header_footer(self, text: str) -> str:
        """去除页眉页脚特征行（页码、版权等）。"""
        patterns = [
            re.compile(r"^第?\s*\d+\s*/\s*\d+\s*页$"),
            re.compile(r"^第?\s*\d+\s*页$"),
            re.compile(r"^\s*copyright\b.*$", re.IGNORECASE),
            re.compile(r"^\s*版权所有.*$"),
            re.compile(r"^\s*未经许可.*$"),
        ]
        lines = text.splitlines()
        kept: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and any(p.match(stripped) for p in patterns):
                continue
            kept.append(line)
        return "\n".join(kept)
