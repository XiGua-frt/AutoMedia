#!/usr/bin/env python3
"""DocumentLoader 集成测试脚本（无外部依赖数据）。

测试覆盖：
- source_type = text
- source_type = file_txt
- source_type = file_md
- source_type = file_pdf（依赖 pymupdf）
- source_type = url（本地临时 HTTP 服务）
"""

from __future__ import annotations

import http.server
import os
import socketserver
import tempfile
import threading
from pathlib import Path

import fitz

from app.rag.ingestion.document_loader import DocumentLoader


def _assert_contains(text: str, expected: str, case_name: str) -> None:
    """断言结果中包含目标子串。"""
    assert expected in text, (
        f"[{case_name}] 断言失败：结果未包含 {expected!r}\n"
        f"实际内容前 200 字符：{text[:200]!r}"
    )


def _create_pdf(path: Path) -> None:
    """创建最小可读 PDF 文件。"""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "PDF sample body")
    doc.save(path)
    doc.close()


def _test_text(loader: DocumentLoader) -> None:
    raw = "# 标题\n\n这是直接文本。"
    out = loader.load(raw, "text")
    assert out == raw
    print("PASS text")


def _test_file_txt(loader: DocumentLoader, root: Path) -> None:
    path = root / "sample.txt"
    path.write_text("TXT 第一行\nTXT 第二行\n", encoding="utf-8")
    out = loader.load(str(path), "file_txt")
    _assert_contains(out, "TXT 第一行", "file_txt")
    print("PASS file_txt")


def _test_file_md(loader: DocumentLoader, root: Path) -> None:
    path = root / "sample.md"
    path.write_text("# MD 标题\n\nMD 段落内容", encoding="utf-8")
    out = loader.load(str(path), "file_md")
    _assert_contains(out, "# MD 标题", "file_md")
    print("PASS file_md")


def _test_file_pdf(loader: DocumentLoader, root: Path) -> None:
    path = root / "sample.pdf"
    _create_pdf(path)
    out = loader.load(str(path), "file_pdf")
    _assert_contains(out, "Page 1", "file_pdf")
    _assert_contains(out, "PDF sample body", "file_pdf")
    print("PASS file_pdf")


def _test_url(loader: DocumentLoader, root: Path) -> None:
    html = """<!doctype html>
<html>
  <body>
    <main>
      <h1>Page Title</h1>
      <p>This is paragraph.</p>
      <ul><li>List Item A</li></ul>
    </main>
  </body>
</html>
"""
    (root / "page.html").write_text(html, encoding="utf-8")

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

    cwd = os.getcwd()
    os.chdir(root)
    try:
        with socketserver.TCPServer(("127.0.0.1", 0), QuietHandler) as httpd:
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{port}/page.html"
                out = loader.load(url, "url")
                _assert_contains(out, "# Page Title", "url")
                _assert_contains(out, "This is paragraph", "url")
                _assert_contains(out, "- List Item A", "url")
                print("PASS url")
            finally:
                httpd.shutdown()
                thread.join(timeout=2)
    finally:
        os.chdir(cwd)


def main() -> None:
    """运行所有测试用例。"""
    loader = DocumentLoader()
    with tempfile.TemporaryDirectory(prefix="doc_loader_test_") as td:
        root = Path(td)
        _test_text(loader)
        _test_file_txt(loader, root)
        _test_file_md(loader, root)
        _test_file_pdf(loader, root)
        _test_url(loader, root)
    print("ALL PASS")


if __name__ == "__main__":
    main()
