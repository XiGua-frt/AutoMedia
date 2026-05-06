#!/usr/bin/env python3
"""RAG 入库 Pipeline 联调脚本。

默认使用 dry-run，不写入向量库与 MySQL。
使用 ``--write`` 开启真实写库。
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from app.config import settings
from app.database import SessionLocal
from app.rag.pipeline import create_default_pipeline


def _build_sample_text() -> str:
    """构造用于联调的示例文章。"""
    return f"""# AI 内容创作提效实践（联调样本）

发布时间：{datetime.now().isoformat()}

## 摘要
本文介绍如何将 RAG 引入内容生产流程，通过知识库检索提升标题、大纲与正文质量。

## 背景问题
传统大模型在垂直领域知识不足，容易出现泛化回答、信息密度不够的问题。

## 解决方案
第一步，建立文档入库流程（加载、清洗、抽取、切分、向量化）。
第二步，构建检索链路（Query 重写、过滤、MMR 去重、上下文打包）。
第三步，将检索结果注入写作智能体，提高可控性与复用率。

## 结论
RAG 并不是替代大模型，而是用高质量外部知识稳定输出质量。
"""


async def main() -> None:
    """执行 Pipeline 联调。"""
    parser = argparse.ArgumentParser(description="测试 RAG 入库流程")
    parser.add_argument(
        "--write",
        action="store_true",
        help="开启真实写库（MySQL + Qdrant）。默认仅 dry-run。",
    )
    parser.add_argument(
        "--source-type",
        default="text",
        choices=["text", "file_md", "file_txt", "file_pdf", "url"],
        help="输入类型，默认 text。",
    )
    parser.add_argument(
        "--source",
        default="",
        help="当 source-type 非 text 时，指定文件路径或 URL。",
    )
    args = parser.parse_args()

    source = _build_sample_text() if args.source_type == "text" else args.source
    if args.source_type != "text" and not source:
        raise ValueError("当 source_type 不是 text 时，必须通过 --source 提供输入")

    db = SessionLocal()
    try:
        pipeline = create_default_pipeline(settings, db)
        result = await pipeline.run(
            source=source,
            source_type=args.source_type,
            hint={"trigger": "manual_test_script"},
            dry_run=not args.write,
        )
    finally:
        db.close()

    print("\n===== Ingestion Result =====")
    print(f"status            : {result.status}")
    print(f"doc_id            : {result.doc_id}")
    print(f"chunk_count       : {result.chunk_count}")
    print(f"duration_seconds  : {result.duration_seconds:.3f}")
    print(f"metadata          : {result.metadata}")

    if args.write and result.doc_id != "dry_run":
        print("\n===== 查询写库结果（MySQL）=====")
        print(f"1) 文档主记录：")
        print(
            "SELECT id,title,platform,category,style,quality_score,created_at "
            f"FROM knowledge_document WHERE id='{result.doc_id}';",
        )
        print("\n2) chunk 记录：")
        print(
            "SELECT id,doc_id,chunk_index,section_title,chunk_type,qdrant_point_id,created_at "
            f"FROM knowledge_chunk WHERE doc_id='{result.doc_id}' ORDER BY chunk_index ASC;",
        )
        print("\n3) 验证 point_id 是否写入：")
        print(
            "SELECT doc_id,chunk_index,qdrant_point_id "
            f"FROM knowledge_chunk WHERE doc_id='{result.doc_id}' AND qdrant_point_id IS NOT NULL;",
        )
    else:
        print("\n当前为 dry-run，未写入 MySQL/Qdrant。使用 --write 可执行真实写库。")


if __name__ == "__main__":
    asyncio.run(main())
