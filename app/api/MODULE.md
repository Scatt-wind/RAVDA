# app/api

## 职责

- HTTP 路由层：参数校验、文件上传、调用 `services/`，返回 Pydantic 模型
- 不写 Pandas 画像、沙箱执行或数据库 SQL

## 关键文件

| 文件 | 说明 |
|------|------|
| `datasets.py` | 数据集上传/列表/详情、RAG 状态与重索引 |
| `query.py` | 自然语言查询 + 会话创建；含 ReAct 重试与中文结论 |
| `sessions.py` | 会话查询与删除 |

## 对外接口

挂载前缀：`/api/v1`（在 `app/main.py` 配置）

**Dify Agent 自定义工具**：导入 `http://host.docker.internal:8000/openapi-dify.json`（或粘贴 `scripts/dify_openapi.json`）；`upload` 需手动注册（multipart）；Dify 负责编排，本层 API 负责执行。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/datasets?limit=10` | 列出最近上传的数据集（默认 10 条，最大 100） |
| GET | `/api/v1/datasets/{dataset_id}` | 获取数据集详情（画像 + `rag_index_status`） |
| POST | `/api/v1/datasets/upload` | 上传 CSV/Excel；**SHA-256 内容去重**；保存文件、画像并写入 MySQL |
| GET | `/api/v1/datasets/{dataset_id}/rag` | 查询 RAGFlow 索引状态 |
| POST | `/api/v1/datasets/{dataset_id}/rag/reindex` | 手动触发重新索引 |
| POST | `/api/v1/datasets/{dataset_id}/sessions` | 创建空对话会话 |
| GET | `/api/v1/datasets/{dataset_id}/sessions/latest` | 返回该数据集最近更新的会话及全部轮次（Web 结果面板轮询用） |
| POST | `/api/v1/datasets/{dataset_id}/query` | 自然语言提问；可选 `session_id`，否则自动创建会话 |
| GET | `/api/v1/sessions/{session_id}` | 返回会话及历史轮次（含 result、charts） |
| DELETE | `/api/v1/sessions/{session_id}` | 删除会话及关联轮次 |

**上传去重**（`datasets.py`）：

1. 计算上传内容 SHA-256 → `content_hash`
2. 若库中已有相同哈希 → 直接返回已有 `UploadResponse`，`deduplicated=true`，不写文件、不触发新索引
3. 否则新建 `dataset_id`、写文件、画像、入库并调度 RAG 索引

**查询流水线**（`query.py`）：

1. `get_dataset_profile` — 优先读库画像
2. 解析/创建 `session_id`，从 MySQL 加载历史轮次
3. `ensure_dataset_indexed` — 对 `pending`/`failed` 数据集自动补触发后台索引
4. `retrieve_context` — RAG 语义检索（未配置或未就绪时降级跳过）
5. `generate_pandas_code(..., history=..., rag_context=...)` — 生成代码
6. `read_dataframe` + `execute_pandas_code` — 从文件加载 df 并沙箱执行
7. 失败且 `attempts < MAX_RETRIES` 且已配置 `OPENAI_API_KEY` 时，`regenerate_pandas_code` 修正后重试
8. `generate_summary(..., history=..., rag_context=...)` — 生成中文结论（LLM 路径注入 RAG）
9. `append_turn` — 持久化本轮；响应含 `rag_used`、`rag_chunk_count`、`rag_skip_reason`

**上传约束**（来自 `config.py`）：

- 允许扩展名：`.csv`、`.xlsx`、`.xls`
- 默认最大体积：50 MB
- 成功响应：`UploadResponse`（含 `profile`、`rag_index_status`、可选 `deduplicated`）

## 依赖关系

- **上游**：`app/main.py`
- **下游**：`app/config.py`、`app/services/`（`profiler`、`dataset_store`、`rag_service`、`codegen`、`sandbox`、`summary`、`conversation_store`）、`app/models/schemas.py`

## 修改时注意

- 校验失败用 `HTTPException`（400 参数/格式，404 资源不存在，413 超大文件，500 内部错误）
- 会话 `dataset_id` 必须与路径参数一致，否则 400
- 画像或入库失败时删除已写入的上传文件，避免脏数据
- `dataset_id` 为 `uuid.uuid4().hex`，文件名 `{dataset_id}{suffix}`
- 列表路由 `GET ""` 须与 `GET /{dataset_id}` 共存；勿与 `/upload` 路径冲突

## 子模块

无（叶子目录）
