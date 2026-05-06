# Agent 会话概述（RAG 技术落地）

## 1. 项目概况（当前代码以 Python 为准）
- 前端：`frontend/`（Vue3 + Vite）
- 后端：`python-backend/`（FastAPI，多智能体文章创作编排）
- 数据库与缓存：
  - MySQL：文章与智能体执行日志等元数据
  - Redis：会话/缓存用途（当前未用于向量检索）
- LLM 与外部能力：DashScope（文档里用于 embedding/元数据/摘要生成；也在当前创作链路中复用）

## 2. 现状对齐（已完成的 RAG 基础设施）
- `python-backend/app/agent/orchestrator.py` 仍以创作三阶段为主（phase1/phase2/phase3）。
- 但 RAG 一期核心基础设施已落地（见 `python-backend/app/rag/`）：
  - `rag/exceptions.py`：统一异常体系（`RAGBaseException` 及子类）
  - `rag/base.py`：`BaseEmbedder` / `BaseVectorStore` / `BaseRetriever` / `BasePipelineStep`
  - `rag/logging.py`：`RAGLoggerMixin` + `set_rag_trace/get_rag_trace`
  - `rag/embedding/dashscope_embeddings.py`：DashScope Embedding 封装（重试、分批、LangChain Embeddings 兼容）
  - `rag/vectorstore/qdrant_store.py`：Qdrant 写入/检索/MMR/过滤/删除
  - `rag/ingestion/*`：`DocumentLoader` / `TextCleaner` / `MetadataExtractor` / `SummaryGenerator` / `DocumentChunker`
  - `rag/pipeline.py`：`RAGIngestionPipeline` + `RAGRetrievalPipeline`（骨架）+ `create_default_pipeline`
- SQL 侧已新增知识库表脚本：`sql/add_knowledge_tables.sql`。

## 3. RAG 目标（从 `RAG_TECH_DESIN.md` 落地）
### 3.1 RAG 作用定位
- 面向“爆款文章创作”知识库：为标题/大纲/正文/金句/案例/CTA 提供可复用写作素材。

### 3.2 技术栈建议（与文档一致）
- LangChain：`langchain` / `langchain-community` / `langchain-qdrant` / `langchain-text-splitters`
- 向量库：
  - 生产主库：Qdrant
  - 兼容/降级：FAISS（可选）
- 关系型数据：MySQL（新增知识库元数据与 chunk 元数据表）
- Embedding：DashScope embedding
- 稀疏检索：Qdrant FastEmbedSparse / BM25
- 重排序（可选演进）：DashScope reranker / bge-reranker

### 3.3 入库流程（`RAG_TECH_DESIN.md`）
- 上传/URL/文本统一转 Markdown
- 正文清洗（去广告/导航/无关内容）
- LLM 提取元数据（标题/平台/标签/风格/质量分等）
- 中文标题增强（用于 metadata/query expansion）
- 文档摘要 + 爆款要素提取
- 两级切分：
  - `MarkdownHeaderTextSplitter`（结构切分）
  - `RecursiveCharacterTextSplitter`（中文递归切分）
- Embedding + 写入 Qdrant
- 写入 MySQL chunk 元数据

### 3.4 检索流程（`RAG_TECH_DESIN.md`）
- Query Rewrite / 中文标题增强（多 query 扩展）
- Metadata Filter（platform/style/tags/quality_score 等）
- Hybrid Search（Dense + Sparse）
- MMR 去重
- （一期可不做）Rerank 重排序
- Context Packing（打包“标题套路/结构/金句/案例/CTA”等素材）
- 注入到 Agent（作为后续标题/大纲/正文生成的上下文）

## 4. 建议的数据模型与变更点（文档规划）
- Qdrant Collection：`article_chunks`
  - dense 向量 + sparse 向量 + payload（与 MySQL chunk 元数据对齐）
- MySQL 新增表：
  - `knowledge_document`（文档级元数据、摘要、结构摘要、爆款要素等）
  - `knowledge_chunk`（chunk 级内容、keywords、对应 qdrant id 等）

## 5. 与现有系统集成方式（后续实现时重点看）
- `python-backend/app/config.py`：补齐 Qdrant 配置项（`qdrant_host/qdrant_port/qdrant_collection` 等）
- `docker-compose.yml`（或 `python-backend/docker-compose.yml`）：新增/启动 Qdrant 服务
- `sql/`：新增 `add_knowledge_tables.sql`（用于建知识库表）
- `python-backend/app/agent/orchestrator.py`：
  - 在 execute_phase1 前插入 `execute_phase0`（新增 “Agent 0：RAG 检索”）
  - 将检索结果写入 `ArticleState` 的 `rag_context`（后续给标题/大纲/正文 Agent 使用）
- 新增模块建议目录：见 `RAG_TECH_DESIN.md` 的 `app/rag/*`、`agent/agents/rag_retriever.py`、`routers/knowledge.py`、`services/knowledge_service.py`

## 6. 当前可运行链路（已验证）
- Embedding 单测脚本：`python-backend/scripts/test_embedding.py`
- DocumentLoader 联调脚本：`python-backend/scripts/test_document_loader.py`
- Chunker 联调脚本：`python-backend/scripts/test_chunker.py`
- 入库 Pipeline 联调脚本：`python-backend/scripts/test_pipeline_ingestion.py`
  - 默认 dry-run：只跑流程不写库
  - `--write`：真实写入 Qdrant + MySQL

## 7. 运行前置条件与常见问题
- Qdrant 必须可用（默认 `localhost:6333`），否则 `QdrantVectorStore.ensure_collection()` 会报连接拒绝。
- MySQL 账号密码必须与 `.env` 一致，否则 `_write_mysql()` 会报 `1045 Access denied`。
- `AgentLogService 未注入，跳过落库` 为预期降级日志，不影响主流程；生产环境需在启动时调用：
  - `RAGLoggerMixin.init_log_service(agent_log_service)`
- PDF 加载依赖 `pymupdf`（已加入 `pyproject.toml`）。

【全局约定 - 每个对话都需遵守】

项目路径：python-backend/app/
语言：Python 3.11+
代码规范：
  - 所有公共类/函数必须有 Google 风格 docstring
  - 使用 Protocol / ABC 定义接口，具体实现分离，便于后续替换
  - 所有可配置项（API Key、Host、阈值等）通过 config.py 注入，禁止硬编码
  - 异常统一使用自定义异常类，在 rag/exceptions.py 中定义
  - 新增文件不修改现有文件，集成点单独说明

技术栈（已安装）：
  - langchain / langchain-community / langchain-qdrant / langchain-text-splitters
  - qdrant-client / dashscope / pymysql
  - 现有 config.py 中已有 dashscope_api_key


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
各模块使用规范（补充进全局约定）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

所有 RAG 模块类均继承 RAGLoggerMixin：

  class DocumentChunker(RAGLoggerMixin):
      def split(self, content, base_metadata):
          start = datetime.now()
          try:
              # ... 业务逻辑 ...
              self.log_to_db("SUCCESS", start, datetime.now(), output_data=f"{len(docs)} chunks")
              return docs
          except Exception as e:
              self.log_to_db("FAILED", start, datetime.now(), error_message=str(e))
              raise ChunkError(str(e)) from e

Pipeline 入口（pipeline.py 的 run() 方法）负责调用 set_rag_trace()，
各子模块通过 get_rag_trace() 自动读取，无需层层传参：

  async def run(self, source, source_type, ...):
      trace_id = str(uuid.uuid4())
      set_rag_trace(trace_id=trace_id, doc_id="pending")
      # 后续所有模块的 log_to_db 自动携带此 trace_id

【不需要新建的内容】
- 不新建 logging handler / formatter（复用现有 logging 配置）
- 不新建 agent_log 表（复用现有表结构）
- 不修改 AgentLogService（零侵入）