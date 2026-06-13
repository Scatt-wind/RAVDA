import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.datasets import router as datasets_router
from app.api.query import router as query_router
from app.api.sessions import router as sessions_router
from app.db.schema import init_schema
from app.models.schemas import HealthResponse
from app.services.ragflow_client import is_rag_configured

_DIFY_OPENAPI_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dify_openapi.json"
_WEB_DIR = Path(__file__).resolve().parent.parent / "frontend" / "web"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_schema()
    yield


app = FastAPI(
    title="RAVDA",
    description="Retrieval-Augmented Visual Data Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(datasets_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="ravda", rag_configured=is_rag_configured())


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "message": "RAVDA API is running",
        "docs": "/docs",
        "web_app": "/app/",
    }


@app.get("/api/v1/public-config", tags=["system"])
def public_config() -> dict[str, str]:
    return {
        "difyEmbedUrl": os.getenv("DIFY_EMBED_URL", "").strip(),
        "pollIntervalSec": os.getenv("WEB_POLL_INTERVAL_SEC", "4").strip(),
    }


@app.get("/openapi-dify.json", include_in_schema=False)
def openapi_dify() -> JSONResponse:
    """Dify-compatible OpenAPI 3.0 subset (avoid importing auto-generated /openapi.json)."""
    try:
        with _DIFY_OPENAPI_PATH.open(encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return JSONResponse(status_code=500, content={"detail": f"Failed to load Dify OpenAPI: {exc}"})
    return JSONResponse(content=payload)


if _WEB_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=_WEB_DIR, html=True), name="web")
