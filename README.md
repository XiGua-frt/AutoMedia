# AI 爆款文章创作器

基于 **Python（FastAPI）多智能体编排** 与 **Vue 3** 的图文创作平台：从选题到标题、大纲、正文、配图与图文合成，全流程可流式反馈、关键节点可人工介入。

Python
FastAPI
Vue
License

更完整的产品说明、接口与协议见 **[docs/产品技术文档.md](docs/产品技术文档.md)**。

---

## 项目简介

用户输入主题并选择风格后，系统通过多个专职智能体串联完成：

- **阶段 1**：生成多条标题方案 → 用户选择  
- **阶段 2**：流式生成大纲 → 用户可编辑后确认  
- **阶段 3**：流式生成正文 → 分析配图需求 → 并行配图 → 合成带图的 Markdown

创作过程通过 **SSE** 推送进度；支持文章管理、Markdown 导入导出、VIP（Stripe）与管理员统计等能力。

---

## 核心价值


| 维度        | 说明                                                       |
| --------- | -------------------------------------------------------- |
| **自动化**   | 多智能体分工：检索（可选）→ 标题 → 大纲 → 正文 → 配图分析 → 并行配图 → 合成           |
| **个性化**   | 科技 / 情感 / 教育 / 幽默等文章风格（见 `ArticleStyleEnum`）             |
| **知识增强**  | RAG：上传素材文档，创作前检索并注入上下文（见下文「知识库与 RAG」）                    |
| **多样化配图** | Pexels、Mermaid、Iconify、表情包、Nano Banana、SVG 示意图等策略 + 失败降级 |
| **实时反馈**  | 大纲与正文流式输出；配图与阶段事件实时推送                                    |
| **可介入性**  | 标题选择、大纲编辑两个节点支持用户干预                                      |


---

## 系统架构（概要）

- **客户端**：浏览器访问 Vue 3 前端（生产环境可由 Nginx 托管静态资源并反向代理 API）。  
- **接入与接口层**：`python-backend` 内 **FastAPI**，统一前缀 `/api`，Session 鉴权（Redis）、CORS、全局异常处理。  
- **业务与智能体层**：`app/services/`* 与 `app/agent/orchestrator.py` 编排多智能体异步任务；`app/managers/sse_manager.py` 管理 SSE。  
- **数据与外部能力**：MySQL 持久化；Redis 用于 Session 等；向量检索与入库见「知识库与 RAG」；配图上传腾讯云 COS；大模型与 Embedding 走阿里云 DashScope；可选 Stripe、Gemini 生图等。

详细分层图与模块说明仍以 **[docs/产品技术文档.md](docs/产品技术文档.md)** 为准。

---

## 多智能体编排


| 智能体                    | 阶段      | 职责                             |
| ---------------------- | ------- | ------------------------------ |
| RAGReriverAgent        | 标题前（隐式） | 按主题与风格检索知识片段，写入状态供后续 Prompt 使用 |
| TitleGeneratorAgent    | 阶段 1    | 生成 3～5 个标题备选                   |
| OutlineGeneratorAgent  | 阶段 2    | 流式生成大纲（可带知识上下文）                |
| ContentGeneratorAgent  | 阶段 3    | 流式按大纲生成 Markdown 正文            |
| ImageAnalyzerAgent     | 阶段 3    | 分析配图需求（关键词与推荐配图方式）             |
| ParallelImageGenerator | 阶段 3    | 并行拉取/生成图片并上传 COS               |
| ContentMergerAgent     | 阶段 3    | 将图片 URL 插入正文，输出成稿              |


并行配图相关配置见 `app/config.py`：`agent_image_max_concurrency`、`agent_image_fail_fast`。

---

## 知识库与 RAG

产品文档中描述了「文档清洗 → 分块 → DashScope Embedding → **向量库存储** → 创作时检索注入」的完整链路，并给出了 **Redis Stack** 作为向量检索的一种设计叙述。

**当前本仓库 Python 后端默认实现**为：

- 向量库：**Qdrant**（`python-backend/docker-compose.yml` 中的 `qdrant` 服务）。  
- 代码模块：`python-backend/app/rag/`（入库管道、检索、与 `app/routers/knowledge.py` 等）。  
- 关系型元数据：MySQL 知识库相关表由 `sql/add_knowledge_tables.sql` 等于启动时挂载的脚本初始化。

若你希望完全对齐文档中的 **Redis Stack** 向量索引方案，需在部署层替换 Redis 镜像并调整检索实现；详见产品文档第 4.7、6、10.5 节。

知识管理 HTTP 接口（前缀均为 `/api`）包括：`POST /knowledge/upload`、`GET /knowledge/`、`GET /knowledge/{id}`、`DELETE /knowledge/{id}`、`POST /knowledge/search` 等，详见产品文档 **§8.5**。

---

## 技术栈

### 后端（`python-backend/`）


| 技术                                             | 说明               |
| ---------------------------------------------- | ---------------- |
| Python 3.11+                                   | 运行环境             |
| FastAPI + Uvicorn                              | Web 与 ASGI       |
| SQLAlchemy / databases + PyMySQL               | 异步访问 MySQL       |
| Redis                                          | Session 等        |
| Pydantic Settings                              | 配置               |
| DashScope（OpenAI 兼容调用）                         | 对话与 Embedding    |
| Qdrant                                         | 向量存储（默认 Compose） |
| 可选：Stripe、腾讯云 COS、`google-genai`（Nano Banana）等 | 支付、对象存储、AI 生图    |


### 前端（`frontend/`）

Vue 3、TypeScript、Vite、Pinia、Ant Design Vue、Vue Router、Markdown 渲染等（版本以各 `package.json` 为准）。

### 数据与中间件

- MySQL 8.0  
- Redis 7（Compose 默认 `redis:7-alpine`，用于缓存与 Session；**不等同于**文档中的 Redis Stack 向量方案）  
- Qdrant（向量库）

---

## 快速开始（Docker，推荐）

在 `**python-backend`** 目录使用 Compose（会拉起 MySQL、Redis、Qdrant、后端、前端）：

```bash
cd python-backend
# 在同级目录创建 .env（pydantic 从 python-backend/.env 读取，见 app/config.py）
# 至少包含：数据库、Redis、SESSION_SECRET_KEY、PASSWORD_SALT、
# DASHSCOPE_API_KEY、PEXELS_API_KEY、腾讯云 COS、NANO_BANANA_API_KEY（可为空字符串视你环境而定）等
docker compose up -d --build
```

默认访问（可通过环境变量改端口）：


| 服务         | 说明                                          |
| ---------- | ------------------------------------------- |
| 前端         | `http://localhost`（`FRONTEND_PORT`，默认 80）   |
| 后端 API     | `http://localhost:8123/api`（`BACKEND_PORT`） |
| OpenAPI 文档 | `http://localhost:8123/docs`                |
| Qdrant 控制台 | 宿主机 `6333`（见 compose 中 `qdrant` 的 `ports`）  |


国内镜像拉取困难时，可尝试同目录下的 `docker-compose.mirror.yml`。

数据库初始化：Compose 已将项目根目录 `sql/` 下若干脚本挂载到 MySQL `docker-entrypoint-initdb.d/`（建表、阶段字段、VIP、知识库表等），首次启动自动执行。

---

## 本地开发

**后端**

```bash
cd python-backend
# 配置 python-backend/.env，并确保本机可访问 MySQL、Redis、Qdrant
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8567
```

默认 `app/config.py` 中 `server_port` 为 `8567`；Docker 内后端进程监听 **8123**，以 compose 环境变量为准。

**前端**

```bash
cd frontend
npm install
npm run dev
```

开发时前端多为 `http://localhost:5173`，请与 `app/main.py` 中 CORS 配置一致。

---

## 环境变量（摘要）

变量名使用环境变量形式（不区分大小写，与 `Settings` 字段对应）。**完整列表与语义**见 [docs/产品技术文档.md §11](docs/产品技术文档.md) 与 `python-backend/app/config.py`。


| 类别     | 示例变量                                                                                       |
| ------ | ------------------------------------------------------------------------------------------ |
| 服务     | `SERVER_HOST`、`SERVER_PORT`                                                                |
| MySQL  | `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD`                                      |
| Redis  | `REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`、`REDIS_DB`                                      |
| 安全     | `SESSION_SECRET_KEY`、`PASSWORD_SALT`                                                       |
| AI     | `DASHSCOPE_API_KEY`、`DASHSCOPE_MODEL`、`PEXELS_API_KEY`                                     |
| COS    | `TENCENT_COS_SECRET_ID`、`TENCENT_COS_SECRET_KEY`、`TENCENT_COS_REGION`、`TENCENT_COS_BUCKET` |
| 向量库    | `QDRANT_HOST`、`QDRANT_PORT`、`QDRANT_COLLECTION`                                            |
| RAG 调参 | `RAG_CHUNK_SIZE`、`RAG_CHUNK_OVERLAP`、`RAG_TOP_K`、`RAG_MAX_CONTEXT_TOKENS` 等                |
| 可选     | `STRIPE_`*、`NANO_BANANA_`*、`AGENT_IMAGE_*` 等                                               |


---

## 仓库结构（节选）

```
ai-passage-creator/
├── docs/
│   └── 产品技术文档.md      # 产品与技术说明（主参考）
├── frontend/                 # Vue 3 前端
├── python-backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 入口
│   │   ├── config.py        # 配置
│   │   ├── agent/           # 编排器与各智能体
│   │   ├── routers/         # 路由（article / user / payment / knowledge …）
│   │   ├── services/        # 业务服务
│   │   ├── rag/             # RAG 管道与向量库封装
│   │   ├── models/、schemas/、managers/ …
│   ├── docker-compose.yml   # 推荐的一体化编排
│   └── pyproject.toml
└── sql/                      # 建表与迁移脚本（被 compose 挂载）
```

---

## API 与 SSE

- **统一响应**：`{ "code", "data", "message" }`（`code === 0` 表示成功）。  
- **主要路由**：用户 `/api/user/`*、文章 `/api/article/`*、支付 `/api/payment/*`、统计 `/api/statistics/*`、知识库 `/api/knowledge/*`、健康检查 `/api/health/`。  
- **SSE**：`GET /api/article/{id}/sse`，事件类型含 `AGENT0_COMPLETE` / `AGENT0_SKIP`、`TITLES_GENERATED`、`AGENT2_STREAMING`、`OUTLINE_GENERATED`、`AGENT3_STREAMING`、`IMAGE_COMPLETE`、`MERGE_COMPLETE`、`ALL_COMPLETE`、`ERROR` 等。

完整接口表与事件载荷见 **[docs/产品技术文档.md](docs/产品技术文档.md)** 第 8、9 章。

---

## License

MIT（以仓库内许可证文件为准）。