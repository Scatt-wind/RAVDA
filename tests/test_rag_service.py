from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import RagChunk, RagContext
from app.services.profiler import profile_file
from app.services.rag_service import (
    format_rag_context_for_prompt,
    profile_to_markdown,
    retrieve_context,
    schedule_dataset_indexing,
)

SAMPLE_CSV = Path(__file__).resolve().parent / "data" / "sample_sales.csv"


@pytest.fixture
def disable_rag(monkeypatch):
    monkeypatch.setattr("app.config.RAG_ENABLED", False)
    monkeypatch.setattr("app.config.RAGFLOW_BASE_URL", "")
    monkeypatch.setattr("app.config.RAGFLOW_API_KEY", "")
    monkeypatch.setattr("app.services.ragflow_client.RAG_ENABLED", False)
    monkeypatch.setattr("app.services.ragflow_client.RAGFLOW_BASE_URL", "")
    monkeypatch.setattr("app.services.ragflow_client.RAGFLOW_API_KEY", "")
    monkeypatch.setattr("app.services.rag_service.is_rag_configured", lambda: False)


def test_profile_to_markdown_contains_columns():
    profile = profile_file(SAMPLE_CSV, "rag-test", "sample_sales.csv")
    markdown = profile_to_markdown(profile)
    assert "Dataset Profile: sample_sales.csv" in markdown
    assert "### region" in markdown
    assert "### sales_amount" in markdown


def test_format_rag_context_for_prompt_empty_when_skipped():
    assert format_rag_context_for_prompt(RagContext(skipped=True)) == ""
    assert format_rag_context_for_prompt(RagContext()) == ""


def test_format_rag_context_for_prompt_includes_chunks():
    context = RagContext(
        chunks=[
            RagChunk(content="销售额 alias: sales_amount", document_name="profile.md", similarity=0.82),
        ]
    )
    text = format_rag_context_for_prompt(context)
    assert "Relevant knowledge" in text
    assert "sales_amount" in text
    assert "0.820" in text


def test_retrieve_context_skipped_when_not_configured(disable_rag, sample_dataset_id: str):
    context = retrieve_context(sample_dataset_id, "按地区统计销售额")
    assert context.skipped
    assert context.skip_reason == "not_configured"


def test_retrieve_context_returns_chunks(sample_dataset_id: str, monkeypatch):
    monkeypatch.setattr("app.services.rag_service.is_rag_configured", lambda: True)

    mock_chunk = MagicMock()
    mock_chunk.content = "region 表示销售区域"
    mock_chunk.document_name = "dataset_profile.md"
    mock_chunk.similarity = 0.91

    mock_client = MagicMock()
    mock_client.retrieve.return_value = [mock_chunk]
    monkeypatch.setattr("app.services.rag_service.get_ragflow_client", lambda: mock_client)
    monkeypatch.setattr(
        "app.services.rag_service.get_rag_meta",
        lambda _dataset_id: {
            "ragflow_kb_id": "kb-123",
            "rag_index_status": "ready",
            "rag_index_error": None,
        },
    )

    context = retrieve_context(sample_dataset_id, "按地区统计销售额")
    assert not context.skipped
    assert len(context.chunks) == 1
    assert context.chunks[0].content == "region 表示销售区域"


def test_schedule_dataset_indexing_noop_when_disabled(disable_rag, sample_dataset_id: str):
    profile = profile_file(SAMPLE_CSV, sample_dataset_id, "sample_sales.csv")
    with patch("app.services.rag_service.threading.Thread") as thread_cls:
        started = schedule_dataset_indexing(sample_dataset_id, SAMPLE_CSV, profile)
        assert started is False
        thread_cls.assert_not_called()


def test_ensure_dataset_indexed_skips_when_ready(sample_dataset_id: str, monkeypatch):
    from app.services.rag_service import ensure_dataset_indexed

    monkeypatch.setattr("app.services.rag_service.is_rag_configured", lambda: True)
    monkeypatch.setattr("app.services.rag_service.get_rag_index_status", lambda _id: "ready")
    with patch("app.services.rag_service.schedule_dataset_indexing") as schedule:
        status = ensure_dataset_indexed(sample_dataset_id)
        assert status == "ready"
        schedule.assert_not_called()


def test_ensure_dataset_indexed_schedules_when_pending(sample_dataset_id: str, monkeypatch):
    from app.services.rag_service import ensure_dataset_indexed

    monkeypatch.setattr("app.services.rag_service.is_rag_configured", lambda: True)
    monkeypatch.setattr("app.services.rag_service.get_rag_index_status", lambda _id: "pending")
    monkeypatch.setattr("app.services.rag_service.schedule_dataset_indexing", lambda *_a, **_k: True)
    status = ensure_dataset_indexed(sample_dataset_id)
    assert status == "indexing"


def test_find_dataset_by_name_avoids_server_side_name_filter():
    from app.services.rag_service import _find_dataset_by_name

    matching = MagicMock()
    matching.name = "ravda-abc123"
    other = MagicMock()
    other.name = "other-kb"

    client = MagicMock()
    client.list_datasets.return_value = [other, matching]

    found = _find_dataset_by_name(client, "ravda-abc123")
    assert found is matching
    client.list_datasets.assert_called_once_with(page_size=100)

    assert _find_dataset_by_name(client, "missing") is None
