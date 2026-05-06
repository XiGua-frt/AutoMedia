"""RAG 模块日志复用工具。

该模块基于 contextvars 维护链路上下文（trace_id/doc_id），并通过
RAGLoggerMixin 统一提供：
- 标准 logging.Logger 控制台日志能力
- 复用 AgentLogService 的异步日志落库能力
"""

from __future__ import annotations

import contextvars
import logging
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Optional

if TYPE_CHECKING:
    from app.services.agent_log_service import AgentLogService


_rag_trace_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "rag_trace_ctx",
    default={},
)


def set_rag_trace(trace_id: str, doc_id: str = "") -> None:
    """绑定当前 RAG 任务的上下文信息。

    建议在 Pipeline 入口处调用一次，后续链路中的任意模块均可通过
    ``get_rag_trace()`` 读取当前上下文，无需手动传参。

    Args:
        trace_id: 当前任务唯一追踪 ID。
        doc_id: 当前文档 ID。若暂不可得，可留空字符串。
    """
    _rag_trace_ctx.set({"trace_id": trace_id, "doc_id": doc_id})


def get_rag_trace() -> dict:
    """获取当前上下文中的 trace 信息。

    Returns:
        包含 ``trace_id`` 与 ``doc_id`` 的字典；若未设置则返回空字典。
    """
    return _rag_trace_ctx.get()


class RAGLoggerMixin:
    """RAG 模块统一日志 Mixin。

    各 RAG 组件继承后可获得：
    - ``self.logger``: 标准 logging.Logger，用于控制台日志输出
    - ``self.log_to_db(...)``: 复用 AgentLogService.save_log_async 异步落库

    说明：
    - ``agentName`` 自动使用「模块路径 + 类名」
    - ``taskId`` 自动从 contextvars 中读取 trace_id
    - 当 AgentLogService 尚未注入时，自动降级为 warning，不抛异常
    """

    _agent_log_service: ClassVar[Optional["AgentLogService"]] = None

    @classmethod
    def init_log_service(cls, agent_log_service: "AgentLogService") -> None:
        """注入全局 AgentLogService 单例。

        建议在应用启动时执行一次（如 `main.py` 或 lifespan 事件）：
        ``RAGLoggerMixin.init_log_service(agent_log_service)``

        Args:
            agent_log_service: 项目已有的 AgentLogService 实例。
        """
        cls._agent_log_service = agent_log_service

    @property
    def logger(self) -> logging.Logger:
        """获取当前类对应的标准 Logger 实例。"""
        return logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}",
        )

    def log_to_db(
        self,
        status: str,
        start_time: datetime,
        end_time: datetime,
        input_data: str | None = None,
        output_data: str | None = None,
        error_message: str | None = None,
        prompt: str | None = None,
    ) -> None:
        """异步写入 Agent 执行日志。

        该方法内部调用 ``save_log_async``，不会阻塞主链路。
        ``taskId`` 与 ``agentName`` 自动填充，调用方无需传入。

        Args:
            status: 执行状态，通常为 "SUCCESS"、"FAILED" 或 "RUNNING"。
            start_time: 开始时间。
            end_time: 结束时间。
            input_data: 输入数据（可选，通常为序列化字符串）。
            output_data: 输出数据（可选，通常为序列化字符串）。
            error_message: 错误信息（可选）。
            prompt: 关联 Prompt（可选）。
        """
        trace = get_rag_trace()
        log_data = {
            "taskId": trace.get("trace_id", "unknown"),
            "agentName": f"{self.__class__.__module__}.{self.__class__.__name__}",
            "startTime": start_time,
            "endTime": end_time,
            "durationMs": int((end_time - start_time).total_seconds() * 1000),
            "status": status,
            "errorMessage": error_message,
            "prompt": prompt,
            "inputData": input_data,
            "outputData": output_data,
        }

        if self._agent_log_service:
            self._agent_log_service.save_log_async(log_data)
            return

        self.logger.warning("AgentLogService 未注入，跳过落库: %s", log_data)
