"""Thin wrapper around ragflow-sdk with RAVDA configuration."""

from __future__ import annotations

import logging
from functools import lru_cache

from ragflow_sdk import RAGFlow

from app.config import RAGFLOW_API_KEY, RAGFLOW_BASE_URL, RAG_ENABLED

logger = logging.getLogger(__name__)


def is_rag_configured() -> bool:
    return bool(RAG_ENABLED and RAGFLOW_BASE_URL and RAGFLOW_API_KEY)


@lru_cache(maxsize=1)
def get_ragflow_client() -> RAGFlow | None:
    if not is_rag_configured():
        return None

    try:
        return RAGFlow(api_key=RAGFLOW_API_KEY, base_url=RAGFLOW_BASE_URL)
    except Exception as exc:
        logger.warning("Failed to initialize RAGFlow client: %s", exc)
        return None
