# RAVDA（项目根）

## 职责

- RAVDA 项目根：智能数据分析与可视化助手（MVP：上传 + 数据画像 + 自然语言查询 + ReAct 重试 + 中文结论 + 多轮对话 + MySQL 持久化）
- 本文件为 **模块索引**；各子目录详见对应 `MODULE.md`

## 关键文件

| 文件 | 说明 |
|------|------|
| `README.md` | 人类可读：安装、运行、API 概览 |
| `requirements.txt` / `environment.yml` | Python 依赖与 Conda 环境 |
| `.env.example` | 环境变量模板（含 MySQL、RAGFlow、Dify 工具 Base URL） |
| `app/main.py` | FastAPI 应用入口，启动时 `init_schema()` |

## 对外接口

- 服务启动：`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`（本机浏览器仍可用 `127.0.0.1:8000`）
- HTTP 根路径：`/`、`/health`、`/docs`、`/app/`（Web 壳）、`/openapi-dify.json`（Dify 导入用）
- 公开配置：`GET /api/v1/public-config`（`DIFY_EMBED_URL` 等）
- 业务 API 前缀：`/api/v1`

## 依赖关系

- **下游**：`app/`（应用逻辑）、`uploads/`（数据集文件）、MySQL（画像与会话）、`tests/data/`（测试数据）
- **外部**：RAGFlow 0.19.x（语义检索；`app/services/rag_service.py`）；自托管 Dify Agent（HTTP 自定义工具，见下文）

## RAGFlow 接入踩坑（已验证 / 设计约束）

> 当前环境：服务端 **0.19.0**；业务代码已接入 `rag_service.py`，以下供联调与排障对照。

### HTTP 客户端

| 方式 | 结果 | 建议 |
|------|------|------|
| `httpx` 直连 `RAGFLOW_BASE_URL` | 易返回 **502**（空 body） | **不要用** |
| `requests` / `ragflow-sdk` | `GET /api/v1/datasets` → **200** | **优先使用** |

SDK 实际请求地址为 `{RAGFLOW_BASE_URL}/api/v1/...`，鉴权头：`Authorization: Bearer <RAGFLOW_API_KEY>`。

### 服务端 vs SDK 版本

- PyPI 提供多版本 SDK；`requirements.txt` 固定 **`ragflow-sdk==0.19.0`**，与 RAGFlow 服务端 0.19.x 对齐。
- 若后续升级服务端或 SDK，先跑 `scripts/ragflow_smoke_test.py` 与 `scripts/rag_e2e_test.py` 验证，勿盲目升到最新组合。

**0.19.0 可用（RAVDA MVP 范围）**

- 知识库 CRUD、`retrieve` 检索、文档上传/解析/分块
- `chunk_method=table`（CSV/Excel）、`chunk_method=naive`（画像 Markdown）
- `cross_languages`（中英文混合检索）、`keyword=True`
- 文档 metadata 保存

**0.19.0 不可用 / 勿调用（高版本才有）**

| 能力 | 大致版本 | RAVDA 替代 |
|------|----------|------------|
| Memory API | 0.24+ | MySQL 多轮会话 |
| `auto_metadata_config` | 较新 SDK | 手动写 metadata |
| `use_kg` / `toc_enhance`（retrieve 参数） | 较新 | 不传，避免服务端异常 |
| 新版 Agent Launch / Chat 路径变更 | 0.24+ | 第三期 Dify/Coze 编排 |

`retrieve()` 调用时 **只传基础参数**；解析完成度需自行轮询文档 `run_status`，勿依赖高版本 SDK 专有参数。

### 配置与端口

- `.env` 中 `RAGFLOW_BASE_URL` 通常填 Web/反代端口（如 **8880**），不必强行改成 `9380`（两端口可能均开放）。
- `app/config.py` 已读取 `RAGFLOW_*` 与 `RAG_*` 调优项；见 `.env.example`。
- Key 仅放 `.env`，连通性测试脚本勿打印 Key 内容。

### 检索与业务边界

- **`retrieve` 必须传 `dataset_ids`**；无知识库时无法测检索（`list_datasets` 为空属正常）。
- RAGFlow **不替代**现有链路：`DatasetProfile`（MySQL）+ Pandas 沙箱执行；检索结果只作为 `codegen` 前的 **语义补充**。
- 不要用 RAGFlow Chat/Agent **替换** `codegen + sandbox`（编排留给第三期）。
- 数值统计（min/max/mean）以 **Profile 为准**；业务语义、字段别名以 **检索结果为准**。
- 建议 **一 RAVDA `dataset_id` 对应一 RAGFlow 知识库**，检索时用 `dataset_ids=[kb_id]` 隔离。
- 勿将全量 DataFrame 行数据灌入向量库；画像 Markdown + 原始表 `table` 分块 + 可选说明文档即可。
- RAGFlow 不可用或索引未就绪时 **降级跳过检索**，不阻断 `/query`。

### 0.19.0 API 行为差异

- 部分文档列表接口由 GET 改为 **POST**（breaking change）；优先走 `ragflow-sdk`，避免手写过时路径。
- 上传后解析可能耗时数分钟；**上传 API 不应阻塞**等索引完成，异步轮询后再标记 `ready`。

## Dify Agent 接入（Docker 自托管）

> Dify 做对话编排，RAVDA 做分析执行；勿在 Dify 内重写 `codegen + sandbox`。

### 网络（已验证）

| 场景 | 地址 | 结果 |
|------|------|------|
| Dify 容器经 SSRF 代理 | `http://host.docker.internal:8000` | ✅ 可达 RAVDA |
| Dify 容器填 localhost | `http://127.0.0.1:8000` | ❌ 指向容器自身，非 RAVDA |

- `.env`：`HOST=0.0.0.0`，`DIFY_TOOL_BASE_URL=http://host.docker.internal:8000`
- Dify 侧：`SSRF_DEFAULT_*_TIME_OUT` 建议 ≥120s（`/query` 可能较慢）
- 自检：`python scripts/dify_connectivity_test.py`

### 工具注册

- 导入 OpenAPI：`http://host.docker.internal:8000/openapi-dify.json`（**勿用** `/openapi.json`，Dify 无法解析 3.1 + `$ref`）
- 备选：粘贴 `scripts/dify_openapi.json` 到 Dify「从 Schema 导入」
- 自动导入含：`ravda_health`、`ravda_list_datasets`、`ravda_create_session`、`ravda_query`
- 上传须手动添加：`POST /api/v1/datasets/upload`（`multipart/form-data`，字段 `file`）
- Agent 须维护 `dataset_id`、`session_id`（追问时传入）

## 修改时注意

- 新增顶层目录时，同步创建该目录 `MODULE.md` 并更新本索引
- 密钥仅放 `.env`，勿提交版本库
- 服务依赖 MySQL；启动前确保 `.env` 中数据库可连接
- 修改 RAG 行为时遵循上文「RAGFlow 接入踩坑」，同步更新 `app/services/MODULE.md`

## 模块索引

| 路径 | 职责摘要 |
|------|----------|
| `app/` | FastAPI 应用：配置、路由、服务、模型、数据库层 |
| `conversations/` | 历史遗留目录（会话已迁至 MySQL） |
| `scripts/` | 本地开发与冒烟脚本（含 `dify_openapi.json`、`dify_connectivity_test.py`） |
| `frontend/` | 双前端：`web/` 静态壳（Dify 嵌入，推荐）+ Streamlit 调试页 |
| `tests/` | pytest 用例与静态测试数据 |
| `uploads/` | 用户上传文件本地存储（运行时） |
