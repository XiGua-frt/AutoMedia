"""文档加载器：统一将输入转换为 Markdown 文本。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.rag.exceptions import DocumentLoadError
from app.rag.logging import RAGLoggerMixin


class DocumentLoader(RAGLoggerMixin):
    """统一加载各类输入并输出 Markdown 字符串。

    支持的 ``source_type``：
    - ``file_pdf``: 使用 PyMuPDF 逐页提取文本并转 Markdown
    - ``file_md``: 直接读取 Markdown 文件
    - ``file_txt``: 直接读取文本文件并保留换行
    - ``url``: 请求网页后提取 ``article`` / ``main`` 主体文本
    - ``text``: 原样透传
    """

    _USER_AGENT: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def load(self, source: str, source_type: str) -> str:
        """加载输入并返回 Markdown。

        Args:
            source: 文件路径、URL 或原始文本。
            source_type: 输入类型。

        Returns:
            Markdown 格式文本。

        Raises:
            DocumentLoadError: 加载失败时抛出，包含 source 与原始错误信息。
        """
        start = datetime.now()
        try:
            st = source_type.strip().lower()
            if st == "file_pdf":
                result = self._load_pdf(source)
                self.log_to_db(
                    "SUCCESS",
                    start,
                    datetime.now(),
                    input_data=f"source_type={st}, source={source}",
                    output_data=f"text_len={len(result)}",
                )
                return result
            if st == "file_md":
                result = Path(source).read_text(encoding="utf-8")
                self.log_to_db(
                    "SUCCESS",
                    start,
                    datetime.now(),
                    input_data=f"source_type={st}, source={source}",
                    output_data=f"text_len={len(result)}",
                )
                return result
            if st == "file_txt":
                result = Path(source).read_text(encoding="utf-8")
                self.log_to_db(
                    "SUCCESS",
                    start,
                    datetime.now(),
                    input_data=f"source_type={st}, source={source}",
                    output_data=f"text_len={len(result)}",
                )
                return result
            if st == "url":
                result = self._load_url(source)
                self.log_to_db(
                    "SUCCESS",
                    start,
                    datetime.now(),
                    input_data=f"source_type={st}, source={source}",
                    output_data=f"text_len={len(result)}",
                )
                return result
            if st == "text":
                self.log_to_db(
                    "SUCCESS",
                    start,
                    datetime.now(),
                    input_data=f"source_type={st}",
                    output_data=f"text_len={len(source)}",
                )
                return source
            raise DocumentLoadError(f"不支持的 source_type: {source_type!r}")
        except DocumentLoadError:
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                input_data=f"source_type={source_type}, source={source}",
                error_message="DocumentLoadError",
            )
            raise
        except Exception as exc:  # noqa: BLE001
            self.log_to_db(
                "FAILED",
                start,
                datetime.now(),
                input_data=f"source_type={source_type}, source={source}",
                error_message=str(exc),
            )
            raise DocumentLoadError(
                f"文档加载失败 source={source!r}, source_type={source_type!r}, error={exc}",
            ) from exc

    def run(self, input: Any) -> Any:
        """实现 ``BasePipelineStep`` 兼容入口。

        Args:
            input: 约定为 ``{'source': str, 'source_type': str}``。

        Returns:
            Markdown 文本字符串。

        Raises:
            DocumentLoadError: 输入结构或加载过程不合法时抛出。
        """
        if not isinstance(input, dict):
            raise DocumentLoadError("DocumentLoader.run 输入必须为 dict")
        source = str(input.get("source", ""))
        source_type = str(input.get("source_type", ""))
        return self.load(source=source, source_type=source_type)

    def _load_url(self, url: str) -> str:
        """抓取网页并提取正文区域。

        提取优先级：``<article>`` → ``<main>`` → ``<body>``。

        Args:
            url: 网页 URL。

        Returns:
            提取并归一化后的 Markdown 文本。
        """
        resp = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": self._USER_AGENT},
        )
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        root = soup.find("article") or soup.find("main") or soup.body or soup

        # 清理常见噪声标签
        for tag_name in ("script", "style", "noscript", "iframe", "svg"):
            for tag in root.find_all(tag_name):
                tag.decompose()

        lines: list[str] = []
        for elem in root.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre"],
        ):
            text = elem.get_text(" ", strip=True)
            if not text:
                continue
            name = elem.name.lower()
            if name.startswith("h"):
                level = min(max(int(name[1]), 1), 6)
                lines.append(f"{'#' * level} {text}")
            elif name == "li":
                lines.append(f"- {text}")
            else:
                lines.append(text)

        if not lines:
            plain = root.get_text("\n", strip=True)
            return re.sub(r"\n{3,}", "\n\n", plain)
        return "\n\n".join(lines)

    def _load_pdf(self, path: str) -> str:
        """逐页提取 PDF 文本，保留段落换行。

        Args:
            path: PDF 文件路径。

        Returns:
            提取后的 Markdown 文本。

        Raises:
            DocumentLoadError: 未安装 PyMuPDF 或读取失败时抛出。
        """
        try:
            import fitz  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DocumentLoadError("未安装 PyMuPDF，请先安装 `pymupdf`") from exc

        pdf = fitz.open(path)
        try:
            pages: list[str] = []
            for i, page in enumerate(pdf):
                text = page.get_text("text").strip()
                if not text:
                    continue
                pages.append(f"## Page {i + 1}\n\n{text}")
            return "\n\n".join(pages).strip()
        finally:
            pdf.close()
