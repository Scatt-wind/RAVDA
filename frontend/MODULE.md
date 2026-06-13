# frontend

## 职责

- 用户界面层：数据集上传与管理、分析结果展示；通过 HTTP 调用 FastAPI，不直接访问 MySQL 或沙箱
- **双入口并存**：`web/` 为推荐产品页（Dify 对话 + 结果面板）；`streamlit_app.py` 为直连 API 的调试/备用界面

## 关键文件

| 文件 | 说明 |
|------|------|
| `web/` | 静态 Web 壳（Dify iframe + 侧栏 + 结果轮询），见 `web/MODULE.md` |
| `api_client.py` | Streamlit 用 `RavdaClient`（httpx） |
| `streamlit_app.py` | Streamlit 界面：侧栏上传、内置对话、图表、RAG 状态 |

## 对外接口

**推荐入口**（仅启动后端即可，静态页由 FastAPI 托管）：

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 浏览器：http://127.0.0.1:8000/app/
```

**Streamlit 入口**（需另启进程）：

```powershell
streamlit run frontend/streamlit_app.py --server.port 8501
```

**`RavdaClient` 方法**（`api_client.py`，Streamlit 专用）：

| 方法 | 对应 API |
|------|----------|
| `health()` | GET `/health` |
| `upload_dataset(...)` | POST `/api/v1/datasets/upload` |
| `list_datasets(limit=10)` | GET `/api/v1/datasets?limit=10` |
| `get_dataset(dataset_id)` | GET `/api/v1/datasets/{id}` |
| `get_rag_status` / `reindex_rag` | GET/POST `/api/v1/datasets/{id}/rag` |
| `create_session` / `query` | POST sessions / query |
| `get_session` / `delete_session` | GET/DELETE `/api/v1/sessions/{id}` |

环境变量：`API_BASE_URL`、`API_TIMEOUT_SEC`（Streamlit）；`DIFY_EMBED_URL`、`WEB_POLL_INTERVAL_SEC`（Web 壳，见 `.env.example`）

## 依赖关系

- **上游**：FastAPI `/api/v1`（见 `app/api/MODULE.md`）、Dify Web App（仅 `web/` iframe）
- **下游**：`httpx`、`python-dotenv`、`streamlit`（Streamlit 路径）；原生 fetch（Web 路径）

## 修改时注意

- Web 与 Streamlit 不要重复实现对话：Web 仅 Dify iframe；Streamlit 仍用 `st.chat_input`
- `api_client` 使用 `httpx.Client(trust_env=False)`，避免 localhost 走系统代理
- 查询可能耗时较长，默认 `API_TIMEOUT_SEC=120`
- 侧栏「最近上传」最多 10 条；重复上传相同内容时后端 `deduplicated: true`

## 子模块

| 路径 | 说明 |
|------|------|
| `web/` | 静态 Web 壳（Dify 嵌入 + 结果面板） |
