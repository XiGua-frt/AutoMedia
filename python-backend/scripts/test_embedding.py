#!/usr/bin/env python3
"""验证 DashScopeEmbeddings（需环境变量 DASHSCOPE_API_KEY）。

运行方式（在 python-backend 目录下）::

    .venv/bin/python scripts/test_embedding.py

默认使用 ``text-embedding-v3`` + ``dimension=1024``（一般账号默认可用）。
若已开通 ``text-embedding-v4`` 并需要 1536 维，可设置环境变量覆盖，例如::

    export DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4
    export DASHSCOPE_EMBEDDING_DIM=1536
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# 将 python-backend 根目录加入 sys.path
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_BACKEND_ROOT / ".env")
except ImportError:
    pass

from app.rag.embedding.dashscope_embeddings import DashScopeEmbeddings


def main() -> None:
    """使用 3 条中文文本调用 embed_documents，校验向量维度并打印耗时。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        print("SKIP: 未设置环境变量 DASHSCOPE_API_KEY，跳过联网验证。")
        sys.exit(0)

    texts = [
        "检索增强生成结合了外部知识与语言模型。",
        "向量数据库用于近似最近邻搜索。",
        "爆款文章需要结构、金句与情绪共鸣。",
    ]

    model = os.environ.get("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3").strip()
    expected_dim = int(os.environ.get("DASHSCOPE_EMBEDDING_DIM", "1024"))
    output_dim = None if expected_dim <= 0 else expected_dim

    embedder = DashScopeEmbeddings(
        api_key=api_key,
        model=model,
        batch_size=25,
        output_dimension=output_dim,
    )

    start = time.perf_counter()
    vectors = embedder.embed_documents(texts)
    elapsed = time.perf_counter() - start

    assert len(vectors) == len(texts), "返回向量条数应与输入一致"
    dim = len(vectors[0])
    assert dim == expected_dim, f"期望向量维度 {expected_dim}，实际为 {dim}"
    for i, row in enumerate(vectors):
        assert len(row) == expected_dim, f"第 {i} 条向量维度异常"

    print(f"embed_documents 成功: {len(vectors)} 条向量, 维度={dim}, 耗时={elapsed:.3f}s")


if __name__ == "__main__":
    main()
