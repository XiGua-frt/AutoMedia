"""DashScope 文本向量封装。

基于阿里云 DashScope ``TextEmbedding`` API，实现
``langchain.embeddings.base.Embeddings`` 与项目内 ``BaseEmbedder`` 协议，
便于直接接入 LangChain 链路与自定义 RAG 编排。
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any, Optional

import dashscope
from langchain_core.embeddings import Embeddings
from tenacity import Retrying, stop_after_attempt, wait_exponential

from app.rag.exceptions import EmbeddingError

# 百炼文档：text-embedding-v3 / v4 在 input 为字符串列表时，单次最多 10 条。
_DASHSCOPE_LIST_INPUT_MAX: int = 10


class DashScopeEmbeddings(Embeddings):
    """封装 DashScope text-embedding 系列模型，实现 ``Embeddings`` / ``BaseEmbedder``。

    支持批量 ``embed_documents`` 与单条 ``embed_query``；按批次调用 API，
    单批条数取 ``min(batch_size, 10)`` 以符合 DashScope 列表输入上限。
    失败时使用 tenacity 指数退避重试；超限或业务错误抛出 ``EmbeddingError``。

    Attributes:
        无额外公开属性；配置均在构造时注入。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-v3",
        batch_size: int = 25,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        output_dimension: Optional[int] = None,
    ) -> None:
        """初始化 DashScope 向量客户端。

        Args:
            api_key: DashScope API Key，由调用方（如应用配置）注入，禁止在类内读取全局配置。
            model: 模型名称，默认 ``text-embedding-v3``。
            batch_size: 单次请求希望合并的文本条数上限；实际每批不超过 10 条。
            max_retries: API 调用失败时的最大尝试次数（含首次）。
            retry_delay: 指数退避的初始等待秒数。
            output_dimension: 输出向量维度；为 ``None`` 时不传 ``dimension`` 参数，
                由服务端使用模型默认值。若需 1536 维 dense 向量，请使用 ``text-embedding-v4``
                并将本参数设为 ``1536``（以百炼当前文档为准）。
        """
        super().__init__()
        self._api_key = api_key
        self._model = model
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._output_dimension = output_dimension
        self._logger = logging.getLogger(__name__)
        self._retrying = Retrying(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(
                multiplier=1,
                min=retry_delay,
                max=60,
            ),
            reraise=True,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量将文本编码为向量，自动分批并重试。

        Args:
            texts: 待编码文本列表。

        Returns:
            与 ``texts`` 等长的向量列表。

        Raises:
            EmbeddingError: 调用失败且重试耗尽，或返回结构异常时抛出。
        """
        if not texts:
            return []

        chunk = max(1, min(self._batch_size, _DASHSCOPE_LIST_INPUT_MAX))
        out: list[list[float]] = []
        for i in range(0, len(texts), chunk):
            batch = texts[i : i + chunk]
            out.extend(self._retrying(self._call_api, batch))
        return out

    def embed_query(self, text: str) -> list[float]:
        """将单条查询文本编码为向量。

        Args:
            text: 查询文本。

        Returns:
            一维浮点向量。

        Raises:
            EmbeddingError: 调用失败且重试耗尽时抛出。
        """
        vectors = self._retrying(self._call_api, [text])
        if not vectors:
            raise EmbeddingError("DashScope 返回空向量列表")
        return vectors[0]

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        """调用 DashScope TextEmbedding 同步接口（单次请求，不含重试）。

        Args:
            texts: 一批待编码文本（长度不超过 ``_DASHSCOPE_LIST_INPUT_MAX``）。

        Returns:
            与输入顺序一致的向量列表。

        Raises:
            EmbeddingError: HTTP 非 200、缺少字段或请求异常时抛出，信息包含服务端原始描述。
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": texts,
            "api_key": self._api_key,
        }
        if self._output_dimension is not None:
            kwargs["dimension"] = self._output_dimension

        try:
            resp = dashscope.TextEmbedding.call(**kwargs)
        except Exception as exc:  # noqa: BLE001 — 统一封装为 EmbeddingError
            raise EmbeddingError(f"DashScope 请求异常: {exc}") from exc

        if resp.status_code != HTTPStatus.OK:
            detail = self._format_error_response(resp)
            raise EmbeddingError(detail)

        output = resp.get("output") if hasattr(resp, "get") else None
        if output is None:
            output = getattr(resp, "output", None)
        if not output or "embeddings" not in output:
            raise EmbeddingError(f"DashScope 响应缺少 output.embeddings: {resp!r}")

        raw_list = output["embeddings"]
        sorted_items = sorted(raw_list, key=lambda x: x.get("text_index", 0))
        vectors = [item.get("embedding") for item in sorted_items]
        if any(v is None for v in vectors):
            raise EmbeddingError(f"DashScope 响应 embedding 字段异常: {raw_list!r}")
        if len(vectors) != len(texts):
            raise EmbeddingError(
                f"DashScope 返回向量条数 {len(vectors)} 与输入 {len(texts)} 不一致",
            )

        usage = resp.get("usage") if hasattr(resp, "get") else getattr(resp, "usage", None)
        total_tokens: Any = None
        if isinstance(usage, dict):
            total_tokens = usage.get("total_tokens")
        elif usage is not None:
            total_tokens = getattr(usage, "total_tokens", None)

        self._logger.debug(
            "DashScope embedding token usage: total_tokens=%s model=%s batch_len=%s usage=%s",
            total_tokens,
            self._model,
            len(texts),
            usage,
        )

        return vectors  # type: ignore[return-value]

    @staticmethod
    def _format_error_response(resp: Any) -> str:
        """从 DashScope 响应中提取可读错误信息。"""
        code = resp.get("code", "") if hasattr(resp, "get") else getattr(resp, "code", "")
        message = (
            resp.get("message", "")
            if hasattr(resp, "get")
            else getattr(resp, "message", "")
        )
        request_id = (
            resp.get("request_id", "")
            if hasattr(resp, "get")
            else getattr(resp, "request_id", "")
        )
        status = (
            resp.get("status_code", "")
            if hasattr(resp, "get")
            else getattr(resp, "status_code", "")
        )
        return (
            f"DashScope embedding 失败: code={code!r} message={message!r} "
            f"status_code={status!r} request_id={request_id!r}"
        )
