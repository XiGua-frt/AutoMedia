"""LLM 驱动的摘要与爆款要素生成器。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.constants.prompt import PromptConstant
from app.rag.exceptions import MetadataExtractError
from app.rag.logging import RAGLoggerMixin


class SummaryGenerator(RAGLoggerMixin):
    """生成摘要、结构总结与爆款要素。"""

    SUMMARY_PROMPT = PromptConstant.RAG_SUMMARY_PROMPT

    def __init__(self, llm_client: Any, model: str = "qwen-plus") -> None:
        """初始化摘要生成器。

        Args:
            llm_client: LLM 客户端（需支持 ``chat.completions.create``）。
            model: 模型名称，默认 ``qwen-plus``。
        """
        self._llm_client = llm_client
        self._model = model

    def generate(self, content: str, metadata: dict) -> dict:
        """生成摘要与爆款要素。

        Args:
            content: 文章正文。
            metadata: 已提取的元数据字典（需至少包含 title）。

        Returns:
            结构化摘要信息。

        Raises:
            MetadataExtractError: LLM 调用、JSON 解析或字段校验失败时抛出。
        """
        if not isinstance(content, str) or not content.strip():
            raise MetadataExtractError("content 不能为空字符串")
        if not isinstance(metadata, dict):
            raise MetadataExtractError("metadata 必须为字典")

        start = datetime.now()
        title = str(metadata.get("title", "")).strip() or "未命名文章"
        prompt = self.SUMMARY_PROMPT.format(title=title, content=content[:2500])
        last_exc: Exception | None = None

        for attempt in range(1, 4):  # 首次 + 重试 2 次
            try:
                raw = self._call_llm(prompt)
                parsed = self._parse_json(raw)
                normalized = self._normalize(parsed)
                self.log_to_db(
                    "SUCCESS",
                    start,
                    datetime.now(),
                    input_data=(
                        f"title={title}, content_len={len(content)}, attempt={attempt}"
                    ),
                    output_data=json.dumps(normalized, ensure_ascii=False),
                    prompt=prompt,
                )
                return normalized
            except MetadataExtractError as exc:
                last_exc = exc
                if attempt >= 3:
                    self.log_to_db(
                        "FAILED",
                        start,
                        datetime.now(),
                        input_data=f"title={title}, content_len={len(content)}",
                        error_message=str(exc),
                        prompt=prompt,
                    )
                    raise
                self.logger.warning(
                    "SummaryGenerator 生成失败，准备重试 attempt=%s error=%s",
                    attempt,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= 3:
                    wrapped = MetadataExtractError(f"摘要生成失败: {exc}")
                    self.log_to_db(
                        "FAILED",
                        start,
                        datetime.now(),
                        input_data=f"title={title}, content_len={len(content)}",
                        error_message=str(wrapped),
                        prompt=prompt,
                    )
                    raise wrapped from exc
                self.logger.warning(
                    "SummaryGenerator 调用异常，准备重试 attempt=%s error=%s",
                    attempt,
                    exc,
                )
        raise MetadataExtractError(f"摘要生成失败: {last_exc}")

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM 并返回文本结果。"""
        try:
            response = self._llm_client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            if not content:
                raise MetadataExtractError("LLM 返回空内容")
            return content
        except MetadataExtractError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MetadataExtractError(f"LLM 调用失败: {exc}") from exc

    def _parse_json(self, raw: str) -> dict:
        """解析 LLM JSON 输出。"""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.logger.warning("SummaryGenerator JSON 解析失败，原始响应: %s", raw)
            raise MetadataExtractError("摘要 JSON 解析失败") from exc
        if not isinstance(parsed, dict):
            self.logger.warning("SummaryGenerator JSON 结构错误，原始响应: %s", raw)
            raise MetadataExtractError("摘要响应必须为 JSON 对象")
        return parsed

    def _normalize(self, data: dict) -> dict:
        """校验并归一化摘要字段。"""
        summary = str(data.get("summary", "")).strip()
        structure_summary = str(data.get("structure_summary", "")).strip()
        viral_elements_raw = data.get("viral_elements", [])
        key_quotes_raw = data.get("key_quotes", [])

        if not summary:
            raise MetadataExtractError("summary 不能为空")
        if not structure_summary:
            raise MetadataExtractError("structure_summary 不能为空")
        if not isinstance(viral_elements_raw, list):
            raise MetadataExtractError("viral_elements 必须为列表")
        if not isinstance(key_quotes_raw, list):
            raise MetadataExtractError("key_quotes 必须为列表")

        viral_elements = [str(x).strip() for x in viral_elements_raw if str(x).strip()]
        key_quotes = [str(x).strip() for x in key_quotes_raw if str(x).strip()][:3]

        return {
            "summary": summary[:100],
            "structure_summary": structure_summary,
            "viral_elements": viral_elements,
            "key_quotes": key_quotes,
        }
