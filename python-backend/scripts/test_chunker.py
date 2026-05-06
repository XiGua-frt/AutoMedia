#!/usr/bin/env python3
"""DocumentChunker 测试脚本。"""

from __future__ import annotations

from app.rag.ingestion.chunker import DocumentChunker


def _assert_metadata_complete() -> None:
    """验证 chunk metadata 字段完整性。"""
    content = """# 总标题

这是第一段正文，用于测试一级标题场景。

## 摘要
这里是摘要部分，应该被标记为 summary 类型。

## 章节一
这是章节一正文内容。"""
    base_metadata = {
        "knowledge_id": "k-001",
        "platform": "wechat",
    }
    chunker = DocumentChunker(chunk_size=80, chunk_overlap=10, min_chunk_size=20)
    chunks = chunker.split(content=content, base_metadata=base_metadata)

    assert len(chunks) >= 2, "至少应切出 2 个 chunk"
    for i, doc in enumerate(chunks):
        meta = doc.metadata
        assert meta["chunk_index"] == i, "chunk_index 应连续递增"
        assert "section_title" in meta and isinstance(meta["section_title"], str)
        assert "chunk_type" in meta and meta["chunk_type"] in (
            "body",
            "title_block",
            "summary",
        )
        assert "char_count" in meta and meta["char_count"] == len(doc.page_content)
        # 继承父级 metadata
        assert meta["knowledge_id"] == "k-001"
        assert meta["platform"] == "wechat"

    assert any(d.metadata["chunk_type"] == "summary" for d in chunks), (
        "包含“摘要”标题时，应至少有一个 summary chunk"
    )
    print("PASS metadata_complete")


def _assert_merge_short_chunks() -> None:
    """验证短 chunk 合并逻辑。"""
    docs_text = """# A

这一段比较长的内容用于形成主要 chunk，长度足够。

## B
短句"""
    chunker = DocumentChunker(chunk_size=60, chunk_overlap=5, min_chunk_size=10)
    chunks = chunker.split(content=docs_text, base_metadata={"doc_id": "d1"})

    # 由于“短句”很短，期望被并入前一个 chunk（最终 chunk 数较少）
    assert len(chunks) <= 2, "短 chunk 应合并，避免碎片化过多"
    print("PASS merge_short_chunks")


def _assert_runtime_override() -> None:
    """验证 split 的运行时参数覆盖。"""
    content = "# T\n\n" + ("内容" * 300)
    chunker = DocumentChunker(chunk_size=500, chunk_overlap=50, min_chunk_size=20)

    large = chunker.split(content=content, base_metadata={}, chunk_size=300, chunk_overlap=30)
    small = chunker.split(content=content, base_metadata={}, chunk_size=120, chunk_overlap=10)
    assert len(small) > len(large), "更小的 chunk_size 应产生更多 chunk"
    print("PASS runtime_override")


def _assert_run_entry() -> None:
    """验证 BasePipelineStep 风格 run 入口。"""
    chunker = DocumentChunker()
    out = chunker.run(
        {
            "content": "# 标题\n\n正文内容",
            "base_metadata": {"k": "v"},
            "chunk_size": 80,
            "chunk_overlap": 10,
        },
    )
    assert isinstance(out, list)
    assert out and out[0].metadata["k"] == "v"
    print("PASS run_entry")


def main() -> None:
    """执行全部用例。"""
    _assert_metadata_complete()
    _assert_merge_short_chunks()
    _assert_runtime_override()
    _assert_run_entry()
    print("ALL PASS")


if __name__ == "__main__":
    main()
