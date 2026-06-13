## 项目概述 (Project Overview)

- **作用**：RAVDA（Retrieval-Augmented Visual Data Assistant）面向「上传数据文件 → 自然语言提问 → 自动分析与可视化」场景，目标是构建一个基于 RAG 的智能数据分析与可视化助手。
- **价值**：降低数据分析门槛，让用户用自然语言即可获取统计结果、图表与中文结论，并支持多轮追问，无需手写 Pandas / Matplotlib 代码；相同文件自动去重，侧栏可快速切换最近上传的数据集。

## 技术栈与架构 (Tech Stack & Architecture)

- **语言/框架**：Python 3.11、FastAPI、Uvicorn；前端为静态 Web（`frontend/web/`，FastAPI 托管）与 Streamlit（`frontend/streamlit_app.py`，可选）
- **数据处理与可视化**：Pandas、NumPy、Matplotlib、OpenPyXL（Excel 支持）
- **LLM**：OpenAI 兼容 API（`openai` SDK），用于代码生成、执行失败重试、中文结论与多轮上下文理解
- **数据库**：MySQL 8.x + PyMySQL（数据集画像缓存、多轮会话与查询历史）
- **RAG**：RAGFlow 0.19.x + `ragflow-sdk==0.19.0`（语义检索）
- **配置管理**：python-dotenv
- **目录结构**：
  - `app/` — 应用主代码（`main.py` 入口、`api/` 路由、`services/` 业务逻辑、`models/` 数据模型、`db/` 持久化层）
  - `frontend/` — **Web 壳**（`/app/`，Dify iframe + 侧栏 + 结果面板）与 **Streamlit**（直连 API 调试）
  - `uploads/` — 上传文件本地存储（执行沙箱仍从此读取 DataFrame）
  - `conversations/` — 历史遗留目录（会话已迁至 MySQL，目录保留兼容）
  - `tests/` — pytest 用例与 `tests/data/` 测试数据集
  - `scripts/` — 本地脚本（冒烟测试、RAG 联调、Dify 连通性验证）
- **外部服务**：RAGFlow 0.19.x（`ragflow-sdk`，语义检索）；自托管 **Dify Agent**（HTTP 自定义工具调用 `/api/v1`）；Coze — 计划中

**持久化分工**：

| 数据 | 存储位置 |
|------|----------|
| 原始文件 | `uploads/{dataset_id}.ext` |
| 数据集元数据 + 画像 JSON + 内容哈希 | MySQL `datasets` 表（`content_hash` 唯一索引，用于上传去重） |
| 会话与查询历史 | MySQL `conversation_sessions` / `conversation_turns` 表 |

## 快速启动 / 使用说明 (Quick Start / Usage)

- **前置要求**：Anaconda（或 Miniconda），Python 3.11，**MySQL 8.x**（本地或远程实例）

- **安装（Conda 推荐）**：

  ```powershell
  conda env create -f environment.yml
  conda activate ravda
  pip install -r requirements.txt
  ```

  若环境已存在，仅需安装 pip 依赖：

  ```powershell
  conda activate ravda
  pip install -r requirements.txt
  ```

- **配置环境变量**：

  ```powershell
  copy .env.example .env
  ```

  关键变量（完整列表见 `.env.example`）：

  | 变量 | 说明 |
  |------|------|
  | `HOST` / `PORT` | 服务监听地址与端口；Docker 内 Dify 访问时 `HOST` 用 `0.0.0.0` |
  | `DIFY_TOOL_BASE_URL` | Dify Agent 自定义工具 Base URL（Docker Desktop：`http://host.docker.internal:8000`） |
  | `UPLOAD_DIR` / `MAX_UPLOAD_SIZE_MB` | 上传目录与大小限制 |
  | `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | MySQL 连接；启动时自动建库建表 |
  | `OPENAI_API_KEY` | LLM Key；留空则代码生成与结论均走规则引擎 |
  | `OPENAI_BASE_URL` / `LLM_MODEL` / `LLM_TIMEOUT_SEC` | OpenAI 兼容 API 配置 |
  | `MAX_RETRIES` | 代码执行失败后的 LLM 重试次数（默认 `2`，最多 3 轮执行） |
  | `SANDBOX_TIMEOUT_SEC` / `MAX_CHART_COUNT` | 沙箱超时与单次最多返回图表数 |
  | `MAX_CONVERSATION_TURNS` | 每会话最多保留轮次（默认 `10`） |
  | `RAGFLOW_BASE_URL` / `RAGFLOW_API_KEY` | RAGFlow 地址与 Key；留空则跳过检索 |
  | `RAGFLOW_EMBEDDING_MODEL` | RAGFlow 嵌入模型（默认 `text-embedding-v3@Tongyi-Qianwen`） |
  | `RAG_ENABLED` / `RAG_TOP_K` / `RAG_SIMILARITY_THRESHOLD` | 是否启用 RAG 与检索参数 |
  | `RAG_INDEX_POLL_INTERVAL_SEC` / `RAG_INDEX_MAX_WAIT_SEC` | 上传后后台索引轮询间隔与超时 |
  | `API_BASE_URL` / `API_TIMEOUT_SEC` / `STREAMLIT_PORT` | Streamlit 连接后端与超时 |
  | `DIFY_EMBED_URL` / `WEB_POLL_INTERVAL_SEC` | Web 壳 Dify iframe 地址与结果轮询间隔（秒） |

- **运行（开发模式）**：

  ```powershell
  cd c:\Python_Project\RAVDA
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
  ```

  启动时通过 `lifespan` 自动执行 `init_schema()`（创建数据库与表）。

  - API 文档：http://127.0.0.1:8000/docs
  - **推荐 Web 入口**：http://127.0.0.1:8000/app/（侧栏上传/选数据集，Dify Agent 对话，右侧表格与图表）

- **Web 壳（Dify 嵌入，推荐）**：

  仅需启动后端（见上）。在 `.env` 配置 `DIFY_EMBED_URL`（Dify 发布的 chatbot 嵌入 URL，如 `http://localhost/chatbot/...`）。

  | 区域 | 说明 |
  |------|------|
  | 左栏 | 上传 CSV/Excel、最近数据集、RAG 状态、复制 `dataset_id` |
  | 中栏 | Dify Agent iframe（唯一对话入口） |
  | 右栏 | 轮询 `sessions/latest`，展示结论、表格、图表（不展示代码） |

  `dataset_id` 由 Dify Agent 系统提示词维护；Agent 工具需配置 `list` 与 `query`（见下文 Dify 接入）。

- **Dify Agent 接入**（自托管 Docker）：

  Dify 做对话编排，RAVDA 做分析执行。容器内 **不要用** `127.0.0.1`，须用：

  ```text
  http://host.docker.internal:8000
  ```

  | 步骤 | 说明 |
  |------|------|
  | 1. 启动 RAVDA | `--host 0.0.0.0`（见上） |
  | 2. 导入 OpenAPI | **用** `http://host.docker.internal:8000/openapi-dify.json`（OpenAPI 3.0 简化版）；**勿用** `/openapi.json`（3.1 + `$ref`，Dify 会报 invalid schema） |
  | 3. 备选：粘贴 Schema | 复制 `scripts/dify_openapi.json` 全文，在 Dify 选「从 Schema 导入」 |
  | 4. 上传工具 | `multipart` 无法自动导入，需手动添加 `POST /api/v1/datasets/upload`（form-data 字段 `file`） |
  | 5. Agent 提示词 | 保存 `dataset_id`；追问传 `session_id`；用 `summary` 组织回复 |
  | 6. Dify SSRF 超时 | `SSRF_DEFAULT_*_TIME_OUT` 建议 ≥120s（`/query` 较慢） |
  | 7. 连通性自检 | `python scripts/dify_connectivity_test.py` |

- **Streamlit 前端**（可选，直连 API 调试；需先启动后端）：

  ```powershell
  streamlit run frontend/streamlit_app.py --server.port 8501
  ```

  浏览器打开 http://127.0.0.1:8501 。侧栏可配置 `API_BASE_URL`（默认 `http://127.0.0.1:8000`），展示**最近上传**历史列表（最多 10 条），点击即可切换数据集，无需重复上传。

- **API 接口**：

  | 方法 | 路径 | 说明 |
  |------|------|------|
  | GET | `/health` | 健康检查（含 `rag_configured`） |
  | GET | `/` | 服务状态（含 `web_app`、`docs`） |
  | GET | `/api/v1/public-config` | Web 壳配置（`difyEmbedUrl`、`pollIntervalSec`） |
  | — | `/app/` | 静态 Web 前端（Dify 嵌入页） |
  | GET | `/openapi-dify.json` | Dify 专用 OpenAPI 3.0 子集 |
  | POST | `/api/v1/datasets/upload` | 上传 CSV/Excel，写文件 + 画像入库 + 触发 RAG 后台索引；**相同内容自动去重**（SHA-256），响应含 `deduplicated` |
  | GET | `/api/v1/datasets?limit=10` | 列出最近上传的数据集（默认 10 条） |
  | GET | `/api/v1/datasets/{dataset_id}` | 获取历史数据集详情（画像 + RAG 状态） |
  | GET | `/api/v1/datasets/{dataset_id}/rag` | 查询 RAGFlow 索引状态 |
  | POST | `/api/v1/datasets/{dataset_id}/rag/reindex` | 手动重新索引 |
  | POST | `/api/v1/datasets/{dataset_id}/sessions` | 创建空对话会话 |
  | GET | `/api/v1/datasets/{dataset_id}/sessions/latest` | 该数据集最近会话及轮次（Web 结果面板） |
  | POST | `/api/v1/datasets/{dataset_id}/query` | 自然语言提问（支持多轮 `session_id`） |
  | GET | `/api/v1/sessions/{session_id}` | 查看会话历史（含结果与图表） |
  | DELETE | `/api/v1/sessions/{session_id}` | 删除会话 |

  支持文件类型：`.csv`、`.xlsx`、`.xls`（默认最大 50 MB）

- **测试上传**：

  ```powershell
  curl -X POST "http://127.0.0.1:8000/api/v1/datasets/upload" -F "file=@tests/data/sample_sales.csv"
  ```

- **自然语言查询**（将 `DATASET_ID` 替换为上传返回的 `dataset_id`）：

  ```powershell
  curl -X POST "http://127.0.0.1:8000/api/v1/datasets/DATASET_ID/query" ^
    -H "Content-Type: application/json" ^
    -d "{\"question\": \"按地区统计销售额并画柱状图\"}"
  ```

  响应会返回 `session_id`，后续追问时传入：

  ```powershell
  curl -X POST "http://127.0.0.1:8000/api/v1/datasets/DATASET_ID/query" ^
    -H "Content-Type: application/json" ^
    -d "{\"question\": \"换成折线图\", \"session_id\": \"YOUR_SESSION_ID\"}"
  ```

  查询响应主要字段：

  | 字段 | 说明 |
  |------|------|
  | `generated_code` / `codegen_source` | 生成的 Pandas 代码；来源 `llm` 或 `rule` |
  | `result` | 表格/数值等结构化执行结果 |
  | `charts` | Base64 PNG 图表列表 |
  | `success` / `error` | 执行是否成功及错误信息 |
  | `attempts` | 执行失败后的重试次数（首次成功为 `0`） |
  | `summary` / `summary_source` | 2–3 句中文结论；来源 `llm` 或 `rule` |
  | `session_id` / `turn_index` | 对话会话 ID 与当前轮次索引（从 0 开始） |
  | `rag_used` / `rag_chunk_count` / `rag_skip_reason` | RAG 是否注入上下文、片段数及跳过原因 |

  配置 `OPENAI_API_KEY` 后优先使用 LLM 生成代码；执行失败时按 `MAX_RETRIES` 将 error + 代码 + 画像反馈给 LLM 修正（ReAct 循环）。多轮对话历史注入 LLM prompt，便于追问（如「换成折线图」）。未配置 Key 时使用内置规则引擎，且不进行 LLM 重试。

- **运行测试**（需可连接的 MySQL，配置与 `.env` 一致）：

  ```powershell
  pytest tests/ -v
  ```

  RAG 联调（需运行中的后端 + RAGFlow 配置）：

  ```powershell
  python scripts/ragflow_smoke_test.py
  python scripts/rag_e2e_test.py
  ```

  Dify Docker 连通性（需 RAVDA 监听 `0.0.0.0:8000` 且 `dify-api-1` 在运行）：

  ```powershell
  python scripts/dify_connectivity_test.py
  ```

## Agent 上下文 / 开发者备注 (Agent Context)

- **当前状态**：
  - ✅ 已完成：Conda 虚拟环境 `ravda`、依赖清单、FastAPI 后端骨架
  - ✅ 已完成：`POST /api/v1/datasets/upload`、Pandas 数据画像（列统计、数值摘要、Top 值、前 5 行预览）
  - ✅ 已完成：自然语言查询流水线（代码生成 → AST 沙箱执行 → 图表捕获）
  - ✅ 已完成：执行失败 ReAct 重试（`MAX_RETRIES`，需 LLM Key）
  - ✅ 已完成：中文结论生成（`summary.py`，LLM + 规则 Top1/占比兜底）
  - ✅ 已完成：多轮对话（MySQL 持久化 + 会话 API；服务重启后会话仍在）
  - ✅ 已完成：MySQL 持久化（上传画像入库、查询历史、画像缓存优先读库）
  - ✅ 已完成：`.env.example`、`.gitignore`、pytest 用例、测试数据 `tests/data/sample_sales.csv`
  - ✅ 已完成：RAGFlow 检索（上传后后台索引，查询前语义补充注入 `codegen`）
  - ✅ 已完成：Streamlit 前端（侧栏上传、内置对话、RAG 状态；调试/备用入口）
  - ✅ 已完成：静态 Web 壳（`frontend/web/`，`/app/`，Dify iframe + 结果面板轮询）
  - ✅ 已完成：历史数据集管理（内容哈希去重、最近 10 条列表、侧栏切换历史数据集）
  - ✅ 已完成：Dify Agent 自定义工具接入（`openapi-dify.json`、`dify_connectivity_test.py`）
  - ⏳ 计划中：Coze 编排；Dify 完整工作流模板

- **核心约定**：
  - 虚拟环境名称：`ravda`
  - API 版本前缀：`/api/v1`
  - 查询流水线：读库画像 → RAG 检索（可降级）→ 加载会话历史 → `codegen` → 读文件执行 `sandbox` →（失败时）`regenerate_pandas_code` → `generate_summary` → 写库追加轮次
  - `get_dataset_profile` 优先读 MySQL，无记录时回退 `profile_file`（兼容旧文件）
  - 会话与 `dataset_id` 绑定；模块边界见各目录 `MODULE.md`

- **近期变更**：
  - 新增静态 Web 壳 `frontend/web/`：FastAPI 挂载 `/app/`，嵌入 Dify Agent；侧栏管理数据集，右侧轮询展示表格/图表
  - 新增 `GET /api/v1/public-config`、`GET /api/v1/datasets/{id}/sessions/latest`；`.env` 增加 `DIFY_EMBED_URL`、`WEB_POLL_INTERVAL_SEC`
  - 新增 `/openapi-dify.json` 与 `scripts/dify_openapi.json`，解决 Dify 导入 `/openapi.json` 报 invalid schema
  - Dify Docker 接入：`HOST=0.0.0.0`、`DIFY_TOOL_BASE_URL`、`scripts/dify_connectivity_test.py`
  - 新增历史数据集管理：`content_hash` 去重、`GET /api/v1/datasets` 最近 10 条
  - RAG 与 Streamlit：`rag_used` 等字段、RAG 状态展示与手动重索引

- **待办事项**：
  - 第三期：Coze 工作流编排；Dify Agent 预置工作流与提示词模板
