# app/models

## 职责

- 定义 API 请求/响应的 Pydantic 模型（OpenAPI schema 来源）
- 不含业务逻辑

## 关键文件

| 文件 | 说明 |
|------|------|
| `schemas.py` | 画像、查询、会话与系统响应模型 |

## 对外接口

| 模型 | 用途 |
|------|------|
| `ColumnProfile` | 单列统计：类型、缺失率、唯一值、数值/日期/Top 值 |
| `DatasetProfile` | 数据集画像：`dataset_id`、行列数、`columns`、`preview` |
| `UploadResponse` | 上传成功：`message`、`profile`、`rag_index_status`、可选 `deduplicated` |
| `DatasetSummary` | 历史列表项：文件名、大小、行列数、`created_at`、RAG 状态 |
| `DatasetListResponse` | 列表响应：`datasets`、`total` |
| `DatasetDetailResponse` | 详情响应：`profile`、`rag_index_status` |
| `DatasetRagStatusResponse` | RAG 索引状态：`ragflow_kb_id`、`rag_index_status`、`rag_index_error`、`rag_configured` |
| `HealthResponse` | `/health`：`status`、`service`、`rag_configured` |
| `RagChunk` / `RagContext` | RAG 检索块与上下文（含 `skipped`、`skip_reason`） |
| `QueryRequest` | 自然语言查询：`question`、可选 `session_id` |
| `QueryResponse` | 查询结果：代码、执行结果、图表、重试、结论、会话信息 |
| `ConversationTurn` | 单轮对话：问题、结论、代码、成功、出图、`result`、`charts`、`error` |
| `ConversationSession` | 会话：`session_id`、`dataset_id`、时间戳、`turns` |
| `CreateSessionResponse` | 创建会话：`session_id`、`dataset_id` |
| `SessionResponse` | 查询会话：`session` |
| `ChartArtifact` | 图表：`format`（png）、Base64 `data`、可选宽高 |

**`QueryResponse` 主要字段**：

- `generated_code` / `codegen_source` — 代码及来源（`llm` / `rule`）
- `result` / `charts` / `stdout` — 执行输出
- `success` / `error` — 执行状态
- `attempts` — 执行失败后的重试次数
- `summary` / `summary_source` — 中文结论及来源（`llm` / `rule`）
- `session_id` / `turn_index` — 会话 ID 与当前轮次索引
- `rag_used` / `rag_chunk_count` / `rag_skip_reason` — RAG 是否注入、片段数及跳过原因

## 依赖关系

- **上游**：`app/api/`、`app/services/`、`app/db/repositories/`、`app/main.py`
- **下游**：Pydantic

## 修改时注意

- 字段变更会直接影响 `/docs`、MySQL JSON 序列化与客户端契约，需保持向后兼容或版本化 API
- `null_rate` 约束为 `[0, 1]`
- `ConversationTurn` 含前向引用 `ChartArtifact`，文件末尾有 `model_rebuild()`

## 子模块

无（叶子目录）
