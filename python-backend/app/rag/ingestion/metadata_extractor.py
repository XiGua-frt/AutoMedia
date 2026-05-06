"""LLM 驱动的元数据提取器。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.constants.prompt import PromptConstant
from app.rag.exceptions import MetadataExtractError
from app.rag.logging import RAGLoggerMixin


class MetadataExtractor(RAGLoggerMixin):
    """从文章中提取结构化元数据，并生成中文标题增强。"""

    EXTRACT_PROMPT = PromptConstant.RAG_METADATA_EXTRACT_PROMPT

    def __init__(self, llm_client: Any, model: str = "qwen-plus") -> None:
        """初始化元数据提取器。

        Args:
            llm_client: LLM 客户端（需支持 ``chat.completions.create``）。
            model: 模型名称，默认 ``qwen-plus``。
        """
        self._llm_client = llm_client
        self._model = model

    def extract(self, content: str, hint: dict | None = None) -> dict:
        """提取结构化元数据。

        Args:
            content: 文章正文。
            hint: 可选提示信息（用于后续扩展，目前仅记录到日志）。

        Returns:
            结构化元数据字典。

        Raises:
            MetadataExtractError: LLM 调用、JSON 解析或字段校验失败时抛出。
        """
        if not isinstance(content, str) or not content.strip():
            raise MetadataExtractError("content 不能为空字符串")

        start = datetime.now()
        snippet = content[:2000]
        prompt = self.EXTRACT_PROMPT.format(content=snippet)
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
                        f"content_len={len(content)}, snippet_len={len(snippet)}, "
                        f"attempt={attempt}, hint_keys={sorted((hint or {}).keys())}"
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
                        input_data=f"content_len={len(content)}, attempt={attempt}",
                        error_message=str(exc),
                        prompt=prompt,
                    )
                    raise
                self.logger.warning(
                    "MetadataExtractor 提取失败，准备重试 attempt=%s error=%s",
                    attempt,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= 3:
                    wrapped = MetadataExtractError(f"元数据提取失败: {exc}")
                    self.log_to_db(
                        "FAILED",
                        start,
                        datetime.now(),
                        input_data=f"content_len={len(content)}, attempt={attempt}",
                        error_message=str(wrapped),
                        prompt=prompt,
                    )
                    raise wrapped from exc
                self.logger.warning(
                    "MetadataExtractor 调用异常，准备重试 attempt=%s error=%s",
                    attempt,
                    exc,
                )
        raise MetadataExtractError(f"元数据提取失败: {last_exc}")

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
            self.logger.warning("MetadataExtractor JSON 解析失败，原始响应: %s", raw)
            raise MetadataExtractError("元数据 JSON 解析失败") from exc
        if not isinstance(parsed, dict):
            self.logger.warning("MetadataExtractor JSON 结构错误，原始响应: %s", raw)
            raise MetadataExtractError("元数据响应必须为 JSON 对象")
        return parsed

    def _normalize(self, data: dict) -> dict:
        """校验并归一化字段。"""
        title = str(data.get("title", "")).strip()
        if not title:
            raise MetadataExtractError("title 不能为空")

        enhanced_titles_raw = data.get("enhanced_titles", [])
        if not isinstance(enhanced_titles_raw, list):
            raise MetadataExtractError("enhanced_titles 必须为列表")
        enhanced_titles = [str(x).strip() for x in enhanced_titles_raw if str(x).strip()]
        if len(enhanced_titles) < 3:
            raise MetadataExtractError("enhanced_titles 至少需要 3 条")

        tags_raw = data.get("tags", [])
        if not isinstance(tags_raw, list):
            raise MetadataExtractError("tags 必须为列表")
        tags = [str(x).strip() for x in tags_raw if str(x).strip()][:5]

        try:
            quality_score = float(data.get("quality_score", 0))
        except (TypeError, ValueError) as exc:
            raise MetadataExtractError("quality_score 必须为数值") from exc
        quality_score = max(1.0, min(10.0, quality_score))

        platform = str(data.get("platform", "其他")).strip() or "其他"
        if platform not in {"微信", "抖音", "小红书", "知乎", "其他"}:
            platform = "其他"

        style = str(data.get("style", "其他")).strip() or "其他"
        if style not in {"干货", "故事", "情感", "产品", "其他"}:
            style = "其他"

        category = str(data.get("category", "未分类")).strip() or "未分类"

        return {
            "title": title,
            "enhanced_titles": enhanced_titles[:3],
            "platform": platform,
            "category": category,
            "style": style,
            "tags": tags,
            "quality_score": quality_score,
        }
