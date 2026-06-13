# app

## 职责

- FastAPI 应用主包：组装路由、中间件、系统端点、启动时数据库初始化
- 不包含具体业务算法实现（在 `services/`）或 HTTP 细节（在 `api/`）

## 关键文件

| 文件 | 说明 |
|------|------|
| `main.py` | FastAPI 实例、CORS、`lifespan` 建表、路由挂载、系统端点、静态 Web 挂载 `/app/` |
| `config.py` | 从 `.env` 加载上传、LLM、沙箱、重试、会话、MySQL、RAGFlow 等配置；`HOST` 建议 `0.0.0.0` 供 Docker 内 Dify 访问 |

## 对外接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（含 `rag_configured`） |
| GET | `/` | 服务状态；含 `docs`、`web_app`（`/app/`） |
| GET | `/api/v1/public-config` | Web 壳公开配置（`difyEmbedUrl`、`pollIntervalSec`） |
| — | `/app/*` | 静态 Web 前端（`frontend/web/`，`html=True`） |
| — | `/api/v1/*` | 由 `api/` 注册的业务路由 |
| GET | `/docs` | Swagger（FastAPI 自动生成） |
| GET | `/openapi.json` | FastAPI 自动生成 OpenAPI 3.1（Swagger 用；Dify 勿导入） |
| GET | `/openapi-dify.json` | Dify 专用 OpenAPI 3.0 子集（源文件 `scripts/dify_openapi.json`） |

## 依赖关系

- **上游**：Uvicorn 启动 `app.main:app`
- **下游**：`api/`、`db/`、`models/schemas.py`、`config.py`

## 修改时注意

- 新业务路由在 `api/` 定义，在 `main.py` 用 `include_router` 挂载
- 全局配置变更优先改 `config.py`，并同步 `.env.example`
- 表结构变更改 `db/schema.py`，保持 `init_schema()` 幂等
- 修改 Dify 工具集时同步更新 `scripts/dify_openapi.json` 与 `/openapi-dify.json` 路由

## 子模块

| 路径 | 说明 |
|------|------|
| `api/` | HTTP 路由层 |
| `db/` | MySQL 连接、建表、仓储 |
| `services/` | 业务逻辑（画像、代码生成、沙箱、结论、会话门面） |
| `models/` | Pydantic 请求/响应模型 |
