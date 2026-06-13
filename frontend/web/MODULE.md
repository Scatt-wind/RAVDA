# frontend/web

## 职责

- 独立静态 Web 壳（方案 B）：侧栏管理数据集，主区嵌入 Dify Agent iframe，右侧展示分析结果（表格、图表、结论）
- 对话仅在 Dify iframe 内进行，不重复实现 chat 输入
- 通过同源 FastAPI 调用 `/api/v1`，不直接访问 MySQL

## 关键文件

| 文件 | 说明 |
|------|------|
| `index.html` | 三栏布局：侧栏 / Dify iframe / 分析结果面板 |
| `css/app.css` | 页面样式与响应式布局 |
| `js/api.js` | `createApiClient`：fetch 封装与 API 方法 |
| `js/app.js` | 上传、数据集切换、RAG 状态、iframe 加载、结果轮询与渲染 |

## 对外接口

**访问**（需先启动后端，`frontend/web` 由 FastAPI 挂载）：

```text
http://127.0.0.1:8000/app/
```

**前端读取配置**：GET `/api/v1/public-config` → `difyEmbedUrl`、`pollIntervalSec`

**调用的 API**（`js/api.js`）：

| 方法 | 对应 API |
|------|----------|
| `health()` | GET `/health` |
| `uploadDataset(file)` | POST `/api/v1/datasets/upload` |
| `listDatasets(limit)` | GET `/api/v1/datasets?limit=` |
| `getDataset(id)` | GET `/api/v1/datasets/{id}` |
| `getRagStatus(id)` | GET `/api/v1/datasets/{id}/rag` |
| `reindexRag(id)` | POST `/api/v1/datasets/{id}/rag/reindex` |
| `getLatestSession(id)` | GET `/api/v1/datasets/{id}/sessions/latest` |

环境变量（后端 `.env`，经 `public-config` 暴露嵌入地址）：`DIFY_EMBED_URL`、`WEB_POLL_INTERVAL_SEC`

## 依赖关系

- **上游**：FastAPI 静态挂载（`app/main.py` → `/app/`）、Dify Web App（iframe）
- **下游**：浏览器 fetch → RAVDA `/api/v1`

## 修改时注意

- iframe 与外壳跨源（Dify 通常在 `localhost:80`），无法 JS 通信；`dataset_id` 由 Agent 系统提示词维护
- 结果面板轮询 `sessions/latest`，取最近会话最后一轮；无会话时显示空状态
- 展示 `summary`、结构化 `result` 表格、Base64 `charts`；**不展示** `generated_code`
- 当前选中 `dataset_id` 存 `localStorage`（键 `ravda.activeDatasetId`）
- 修改 `DIFY_EMBED_URL` 后重启 uvicorn；iframe 空白时检查 Dify X-Frame-Options

## 子模块

无（叶子目录）
