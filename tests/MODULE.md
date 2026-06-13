# tests

## 职责

- pytest 用例与静态测试数据
- 覆盖代码生成、沙箱、查询 API、中文结论、多轮对话、MySQL 持久化、数据集历史/去重与会话 API

## 关键文件

| 路径 | 说明 |
|------|------|
| `conftest.py` | 会话级 `init_schema()`、`sample_dataset_id` / `register_dataset` / `client` fixtures |
| `test_query_pipeline.py` | 规则 codegen、沙箱、结论、查询/会话 API、画像读库、多轮对话集成测试 |
| `test_datasets_api.py` | 历史列表、详情、上传内容去重 |
| `test_rag_api.py` | 上传 RAG 状态、`/rag` 端点、`/health` 的 `rag_configured` |
| `test_rag_service.py` | RAG 服务单元测试：Markdown 画像、上下文格式化、索引调度 |
| `data/sample_sales.csv` | 销售样例 CSV，供上传 API 与测试 fixture 使用 |

## 对外接口

```powershell
# 在项目根目录执行（需可连接的 MySQL，配置与 .env 一致）
pytest tests/ -v

# 或按模块
pytest tests/test_datasets_api.py tests/test_query_pipeline.py tests/test_rag_api.py -v
```

## 依赖关系

- **上游**：开发者 / CI 运行 pytest
- **下游**：`app/`、`app/db/`、`tests/data/sample_sales.csv`、`app/config.UPLOAD_DIR`、MySQL

## 修改时注意

- 修改样例数据结构时，同步更新 `scripts/smoke_test.py` 与相关断言
- `sample_dataset_id` 会写 `uploads/` 并入库，teardown 删除文件与 DB 记录
- `_register_dataset` 为每个 `dataset_id` 追加唯一 marker 行，避免 `content_hash` 唯一约束冲突
- 会话测试通过 `session_cleanup` 删除 MySQL 会话；`register_dataset` 满足外键约束
- 规则引擎相关测试使用 `disable_llm` fixture 屏蔽 `.env` 中的 LLM Key
- `conftest.py` 中 `disable_rag_by_default` 默认关闭 RAG，避免 CI/本地无 RAGFlow 时索引失败
- `test_get_dataset_profile_reads_from_db` 验证画像优先读库、不调用 `profile_file`

## 子模块

| 路径 | 说明 |
|------|------|
| `data/` | 静态测试数据集 |
