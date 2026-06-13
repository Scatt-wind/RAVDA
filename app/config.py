import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# LLM (OpenAI-compatible API)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TIMEOUT_SEC = int(os.getenv("LLM_TIMEOUT_SEC", "60"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))

# Sandbox
SANDBOX_TIMEOUT_SEC = int(os.getenv("SANDBOX_TIMEOUT_SEC", "30"))
MAX_CHART_COUNT = int(os.getenv("MAX_CHART_COUNT", "5"))

# Conversation
CONVERSATION_DIR = Path(os.getenv("CONVERSATION_DIR", BASE_DIR / "conversations"))
MAX_CONVERSATION_TURNS = int(os.getenv("MAX_CONVERSATION_TURNS", "10"))

# MySQL
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ravda")

# RAGFlow
RAGFLOW_BASE_URL = os.getenv("RAGFLOW_BASE_URL", "").rstrip("/")
RAGFLOW_API_KEY = os.getenv("RAGFLOW_API_KEY", "")
RAGFLOW_EMBEDDING_MODEL = os.getenv(
    "RAGFLOW_EMBEDDING_MODEL",
    "text-embedding-v3@Tongyi-Qianwen",
)
RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() in ("1", "true", "yes")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.2"))
RAG_INDEX_POLL_INTERVAL_SEC = int(os.getenv("RAG_INDEX_POLL_INTERVAL_SEC", "5"))
RAG_INDEX_MAX_WAIT_SEC = int(os.getenv("RAG_INDEX_MAX_WAIT_SEC", "300"))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CONVERSATION_DIR.mkdir(parents=True, exist_ok=True)
