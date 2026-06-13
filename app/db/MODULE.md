# app/db

## 职责

- MySQL 持久化层：连接管理、自动建库建表、数据集与会话的仓储 CRUD
- 不处理 HTTP、画像计算或沙箱执行

## 关键文件

| 文件 | 说明 |
|------|------|
| `connection.py` | PyMySQL 连接、`ensure_database()`、`db_cursor()` 上下文 |
| `schema.py` | `init_schema()` — 建表 + `datasets` RAG / `content_hash` 列迁移 |
| `repositories/dataset_repo.py` | 数据集与画像 JSON 读写、去重查询、最近列表 |
| `repositories/conversation_repo.py` | 会话与轮次读写 |

## 对外接口

| 函数 | 说明 |
|------|------|
| `ensure_database()` | 若不存在则创建 `MYSQL_DATABASE` |
| `init_schema()` | 建库 + 建表（启动时由 `main.py` lifespan 调用） |
| `db_cursor()` | 事务上下文，自动 commit/rollback |
| `save_dataset(..., content_hash)` | 插入数据集记录与 `profile_json` |
| `get_profile(dataset_id)` | 从库读取 `DatasetProfile` |
| `find_dataset_by_content_hash(hash)` | 按内容哈希查找已有 `dataset_id` |
| `list_recent_datasets(limit=10)` | 按 `created_at DESC` 返回最近数据集摘要 |
| `get_rag_meta` / `update_rag_meta` | RAGFlow 知识库 ID 与索引状态 |
| `dataset_exists` / `delete_dataset` | 数据集存在检查与删除 |
| `create_session(dataset_id)` | 创建会话（需数据集已入库） |
| `get_session` / `delete_session` | 读取/删除会话及关联轮次 |
| `get_latest_session_for_dataset(dataset_id)` | 按 `updated_at DESC` 取最近一条会话及轮次 |
| `append_turn(session_id, turn)` | 追加轮次，超出 `MAX_CONVERSATION_TURNS` 截断旧轮 |

**表结构**：

- `datasets` — 文件元数据 + `profile_json` + `content_hash`（唯一索引）+ `ragflow_kb_id` / `rag_index_status` / `rag_index_error`
- `conversation_sessions` — `session_id`、`dataset_id`、时间戳
- `conversation_turns` — 问题、代码、结果、图表、成功状态等

## 依赖关系

- **上游**：`app/main.py`（启动建表）、`app/services/dataset_store.py`、`app/services/conversation_store.py`、`tests/conftest.py`
- **下游**：PyMySQL、`app/config.py`（MySQL 连接参数）、`app/models/schemas.py`

## 修改时注意

- 会话表外键依赖 `datasets`；创建会话前数据集须已入库
- `profile_json` / `result_json` / `charts_json` 使用 MySQL JSON 列
- 仓储层抛 `ValueError` 或返回 `None`，由上层转换为 HTTP 错误
- 表结构变更保持 `CREATE TABLE IF NOT EXISTS` 幂等；新列通过 `_migrate_*` 函数追加
- 旧数据无 `content_hash` 时去重不生效，需重新上传一次才会写入哈希

## 子模块

| 路径 | 说明 |
|------|------|
| `repositories/` | 按领域拆分的数据访问函数 |
