"""文章多智能体编排器"""

import logging
from typing import TYPE_CHECKING

from app.agent.agents.content_generator import ContentGeneratorAgent
from app.agent.agents.content_merger import ContentMergerAgent
from app.agent.agents.image_analyzer import ImageAnalyzerAgent
from app.agent.agents.outline_generator import OutlineGeneratorAgent
from app.agent.agents.rag_retriever import RAGRetrieverAgent
from app.agent.agents.title_generator import TitleGeneratorAgent
from app.agent.context.stream_handler import StreamHandlerContext
from app.config import settings
from app.models.enums import SseMessageTypeEnum
from app.rag.embedding.dashscope_embeddings import DashScopeEmbeddings
from app.rag.pipeline import RAGRetrievalPipeline
from app.rag.retrieval import ContextPacker, QueryRewriter
from app.rag.vectorstore.qdrant_store import QdrantVectorStore
from app.schemas.article import ArticleState

if TYPE_CHECKING:
    from app.services.article_agent_service import ArticleAgentService

logger = logging.getLogger(__name__)


class ArticleAgentOrchestrator:
    """多智能体编排器"""

    def __init__(self):
        self.title_agent = TitleGeneratorAgent()
        self.outline_agent = OutlineGeneratorAgent()
        self.content_agent = ContentGeneratorAgent()
        self.image_analyzer_agent = ImageAnalyzerAgent()
        self.content_merger_agent = ContentMergerAgent()
        retrieval_pipeline = RAGRetrievalPipeline(
            query_rewriter=QueryRewriter(),
            vector_store=QdrantVectorStore(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                collection_name=settings.qdrant_collection,
                vector_size=1024,
                distance="Cosine",
            ),
            embedder=DashScopeEmbeddings(
                api_key=settings.dashscope_api_key,
                output_dimension=1024,
            ),
            context_packer=ContextPacker(),
        )
        self.rag_retriever_agent = RAGRetrieverAgent(retrieval_pipeline)

    async def execute_phase0(self, state: ArticleState) -> None:
        """阶段0：RAG 检索（失败仅告警，不阻断创作链路）。"""
        try:
            await self.rag_retriever_agent.execute(state)
        except Exception as exc:
            logger.warning(
                "阶段0（RAG 检索）失败或跳过, taskId=%s, error=%s",
                state.task_id,
                exc,
            )

    async def execute_phase1(
        self,
        service: "ArticleAgentService",
        state: ArticleState,
        stream_handler,
    ):
        await self.execute_phase0(state)
        stream_context = StreamHandlerContext(stream_handler)
        logger.info("阶段1：开始生成标题方案, taskId=%s", state.task_id)
        await self.title_agent.run(service, state)
        stream_context.emit(SseMessageTypeEnum.AGENT1_COMPLETE.value)
        logger.info(
            "阶段1：标题方案生成成功, taskId=%s, optionsCount=%s",
            state.task_id,
            len(state.title_options or []),
        )

    async def execute_phase2(
        self,
        service: "ArticleAgentService",
        state: ArticleState,
        stream_handler,
    ):
        stream_context = StreamHandlerContext(stream_handler)
        logger.info("阶段2：开始生成大纲, taskId=%s", state.task_id)
        await self.outline_agent.run(service, state, stream_context.emit)
        stream_context.emit(SseMessageTypeEnum.AGENT2_COMPLETE.value)
        logger.info("阶段2：大纲生成成功, taskId=%s", state.task_id)

    async def execute_phase3(
        self,
        service: "ArticleAgentService",
        state: ArticleState,
        stream_handler,
    ):
        stream_context = StreamHandlerContext(stream_handler)
        logger.info("阶段3：开始生成正文, taskId=%s", state.task_id)
        await self.content_agent.run(service, state, stream_context.emit)
        stream_context.emit(SseMessageTypeEnum.AGENT3_COMPLETE.value)

        logger.info("阶段3：开始分析配图需求, taskId=%s", state.task_id)
        await self.image_analyzer_agent.run(service, state)
        stream_context.emit(SseMessageTypeEnum.AGENT4_COMPLETE.value)

        logger.info("阶段3：开始生成配图, taskId=%s", state.task_id)
        await service.agent5_generate_images(state, stream_context.emit)
        stream_context.emit(SseMessageTypeEnum.AGENT5_COMPLETE.value)

        logger.info("阶段3：开始图文合成, taskId=%s", state.task_id)
        self.content_merger_agent.run(service, state)
        stream_context.emit(SseMessageTypeEnum.MERGE_COMPLETE.value)

