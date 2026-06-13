# scripts

## 职责

- 存放本地开发、调试、冒烟测试脚本（非生产入口）
- 不参与 FastAPI 运行时加载

## 关键文件

| 文件 | 说明 |
|------|------|
| `smoke_test.py` | 调用 `profile_file` 验证画像逻辑（8 行 × 4 列断言） |
| `ragflow_smoke_test.py` | RAGFlow 连通性冒烟：`list_datasets` + 可选 `retrieve`（走 `ragflow-sdk`） |
| `rag_e2e_test.py` | RAG 端到端：health → upload → 轮询索引 → query → 校验 `rag_used`（需运行中的后端） |
| `dify_openapi.json` | Dify 可解析的 OpenAPI 3.0 子集；由 `app/main.py` 的 `/openapi-dify.json` 提供 |
| `dify_connectivity_test.py` | Dify Docker 连通性：宿主机 `/health` + `dify-api-1` 经 SSRF 代理访问 `host.docker.internal:8000` |

## 对外接口

```powershell
# 在项目根目录执行
python scripts/smoke_test.py

# RAGFlow 连通性（需 .env 配置 RAGFLOW_*；不打印完整 API Key）
python scripts/ragflow_smoke_test.py
python scripts/ragflow_smoke_test.py --dataset-id <ravda_dataset_id>
python scripts/ragflow_smoke_test.py --skip-retrieve

# RAG 端到端（需先 uvicorn 启动后端 + .env 配置 RAGFLOW_*）
python scripts/rag_e2e_test.py
python scripts/rag_e2e_test.py --base-url http://127.0.0.1:8000

# Dify Docker 连通性（需 RAVDA 监听 0.0.0.0:8000，且 dify-api-1 容器在运行）
python scripts/dify_connectivity_test.py
```

脚本会将项目根加入 `sys.path`。`smoke_test.py` 依赖 `tests/data/sample_sales.csv`；RAG 相关脚本依赖 `.env` 与可选的已索引知识库；`rag_e2e_test.py` 使用 `requests` 调用 HTTP API。

## 依赖关系

- **上游**：开发者手动运行
- **下游**：`app/services/profiler.py`、`app/services/ragflow_client.py`、`app/config.py`

## 修改时注意

- 新脚本保持「从项目根运行」或自行设置 `sys.path`
- 冒烟测试不启动 HTTP 服务；API 测试可用 curl 或 TestClient（需 `httpx`）
- RAGFlow 冒烟勿用 `httpx` 直连 `RAGFLOW_BASE_URL`（易 502）；脚本已固定走 `ragflow-sdk`
- `dify_connectivity_test.py` 默认容器名 `dify-api-1`；Dify 工具 Base URL 须为 `http://host.docker.internal:8000`，勿用 `127.0.0.1`
- Dify 导入 URL 用 `/openapi-dify.json`，勿用 FastAPI 的 `/openapi.json`（会报 invalid schema）
- 改 `dify_openapi.json` 后无需重启即可生效（每次请求读取文件）

## 子模块

无（叶子目录）
