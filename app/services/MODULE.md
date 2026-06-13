# app/services

## 职责

- 业务逻辑层：数据读取与画像、RAG 索引与检索、代码生成、沙箱执行、中文结论、会话存储门面
- 不处理 HTTP 或原始 SQL（持久化委托 `app/db/repositories/`）

## 关键文件

| 文件 | 说明 |
|------|------|
| `profiler.py` | CSV/Excel 读取与 DataFrame 画像 |
| `dataset_store.py` | 文件定位、画像读库缓存、`save_dataset` 入库、历史列表与去重查询 |
| `codegen.py` | LLM 或规则引擎生成 Pandas/Matplotlib 代码；失败重生成；支持历史上下文 |
| `sandbox.py` | AST 校验 + 受限执行 + 图表捕获 |
| `summary.py` | 根据执行结果生成 2–3 句中文结论（LLM 或规则兜底）；支持历史上下文 |
| `conversation_store.py` | 会话门面（委托 `db/repositories/conversation_repo`）与 prompt 历史格式化 |
| `ragflow_client.py` | RAGFlow SDK 客户端封装（`requests` 路径，勿用 `httpx` 直连） |
| `rag_service.py` | 数据集索引（画像 Markdown + 原表）、语义检索、prompt 上下文格式化 |

## 对外接口

| 函数 | 说明 |
|------|------|
| `read_dataframe(file_path)` | 按后缀读取 CSV/Excel，空表抛 `ValueError` |
| `profile_dataframe(df, dataset_id, filename)` | 对已有 DataFrame 生成 `DatasetProfile` |
| `profile_file(file_path, dataset_id, filename)` | 读文件 + 画像（上传时调用） |
| `find_dataset_path(dataset_id)` | 在 `uploads/` 中定位数据集文件 |
| `save_dataset(..., content_hash)` | 上传后将元数据与画像写入 MySQL |
| `get_dataset_profile(dataset_id)` | **优先读库**；无记录时回退 `profile_file` |
| `find_dataset_by_content_hash(hash)` | 按内容哈希查找已有 `dataset_id` |
| `list_recent_datasets(limit=10)` | 返回最近上传数据集摘要列表 |
| `generate_pandas_code(profile, question, *, history=None, rag_context=None)` | 生成可执行代码，返回 `(code, source)` |
| `regenerate_pandas_code(..., *, history=None, rag_context=None)` | 执行失败后 LLM 修正代码（需 `OPENAI_API_KEY`） |
| `is_rag_configured()` | 是否启用 RAGFlow（定义于 `ragflow_client.py`；`RAG_ENABLED` + URL + Key） |
| `schedule_dataset_indexing(dataset_id, path, profile)` | 后台索引（`save_dataset` 自动调用），不阻塞 API |
| `ensure_dataset_indexed(dataset_id)` | 查询前对 `pending`/`failed` 补触发索引 |
| `reindex_dataset(dataset_id)` | 手动重新索引（先清空知识库内旧文档） |
| `get_rag_status(dataset_id)` | 返回 `ragflow_kb_id`、状态与错误信息 |
| `retrieve_context(dataset_id, question)` | 语义检索，失败/未就绪时返回 `RagContext(skipped=True)` |
| `format_rag_context_for_prompt(context)` | 将检索块格式化为 LLM 补充上下文 |
| `profile_to_markdown(profile)` | 画像转 Markdown，供 RAGFlow `naive` 分块 |
| `get_rag_index_status(dataset_id)` | 读取 MySQL `rag_index_status` |
| `execute_pandas_code(code, df)` | 沙箱执行，返回 `SandboxResult` |
| `generate_summary(..., *, history=None, rag_context=None)` | 生成中文结论，返回 `(summary, source)` |
| `create_session(dataset_id)` | 创建会话，返回 `session_id` |
| `get_session(session_id)` | 读取会话（不存在返回 `None`） |
| `get_latest_session_for_dataset(dataset_id)` | 读取该数据集最近更新的会话 |
| `append_turn(session_id, turn)` | 追加轮次到 MySQL，返回 `turn_index` |
| `delete_session(session_id)` | 删除会话 |
| `format_history_for_prompt(turns)` | 将最近 N 轮格式化为 LLM prompt 文本 |

**画像规则**：

- 每列：`dtype`、`null_rate`、`unique_count`
- 数值列：`min` / `max` / `mean`
- 日期列：`date_min` / `date_max`（需 pandas 识别为 datetime）
- 其他列：Top 5 `value_counts`
- 预览：前 5 行，NaN/Inf 转为 JSON 安全的 `null`

**会话规则**：

- 存储：MySQL `conversation_sessions` + `conversation_turns`
- 每轮记录：`question`、`summary`、`generated_code`、`success`、`has_charts`、`result`、`charts`、`error`
- 超出 `MAX_CONVERSATION_TURNS` 时截断最旧轮次；prompt 默认取最近 5 轮

## 依赖关系

- **上游**：`app/api/datasets.py`、`app/api/query.py`、`app/api/sessions.py`
- **下游**：`app/db/repositories/`、Pandas、NumPy、Matplotlib、OpenAI SDK、`ragflow-sdk`、`app/models/schemas.py`、`app/config.py`

## 修改时注意

- 新文件格式在 `read_dataframe` 扩展，并同步 `config.ALLOWED_EXTENSIONS` 与 API 校验
- CSV 中日期列默认可能为 `str`，不会自动走 datetime 分支
- 沙箱禁止 `import` 与危险调用；超时见 `SANDBOX_TIMEOUT_SEC`
- 多轮上下文主要增强 LLM 路径；规则引擎不解析历史
- 查询执行仍从 `uploads/` 读文件；仅画像走库缓存
- RAG 不替代 Profile + 沙箱；检索结果仅作 `codegen` 语义补充；数值统计以 Profile 为准
- 一 `dataset_id` 对应一 RAGFlow 知识库（`ravda-{dataset_id}`）；索引状态存 `datasets.rag_*` 列
- RAGFlow 不可用或 `rag_index_status != ready` 时降级跳过检索，不阻断 `/query`

## 子模块

无（叶子目录）
