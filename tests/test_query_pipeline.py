from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.codegen import generate_pandas_code
from app.services.conversation_store import (
    append_turn,
    create_session,
    delete_session,
    format_history_for_prompt,
    get_session,
)
from app.models.schemas import ConversationTurn
from app.services.profiler import profile_file, read_dataframe
from app.services.sandbox import execute_pandas_code
from app.services.summary import generate_summary

SAMPLE_CSV = Path(__file__).resolve().parent / "data" / "sample_sales.csv"


@pytest.fixture
def disable_llm(monkeypatch):
    monkeypatch.setattr("app.config.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.services.codegen.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.services.summary.OPENAI_API_KEY", "")
    monkeypatch.setattr("app.api.query.OPENAI_API_KEY", "")


@pytest.fixture
def session_cleanup():
    created: list[str] = []
    yield created
    for session_id in created:
        delete_session(session_id)


def test_rule_codegen_groupby_bar(disable_llm):
    profile = profile_file(SAMPLE_CSV, "test", "sample_sales.csv")
    code, source = generate_pandas_code(profile, "按地区统计销售额并画柱状图")
    assert source == "rule"
    assert "groupby" in code
    assert "plt.bar" in code or "plt.figure" in code


def test_sandbox_executes_and_returns_chart():
    df = read_dataframe(SAMPLE_CSV)
    code = (
        "result = df.groupby('region')['sales_amount'].sum().reset_index()\n"
        "plt.figure()\n"
        "plt.bar(result['region'], result['sales_amount'])\n"
        "plt.tight_layout()"
    )
    result = execute_pandas_code(code, df)
    assert result.success
    assert result.result is not None
    assert len(result.charts) == 1
    assert result.charts[0].format == "png"
    assert len(result.charts[0].data) > 0


def test_sandbox_rejects_import():
    df = read_dataframe(SAMPLE_CSV)
    result = execute_pandas_code("import os\nresult = 1", df)
    assert not result.success
    assert "Import" in result.error or "not allowed" in result.error


def test_rule_summary_for_grouped_result(disable_llm):
    df = read_dataframe(SAMPLE_CSV)
    sandbox_result = execute_pandas_code(
        "result = df.groupby('region')['sales_amount'].sum().reset_index()",
        df,
    )
    summary, source = generate_summary(
        "按地区统计销售额",
        sandbox_result.result,
        has_charts=False,
        success=True,
    )
    assert source == "rule"
    assert "East" in summary
    assert "销售额" in summary
    assert "占比" in summary or "占总" in summary


def test_rule_summary_mentions_chart(disable_llm):
    summary, source = generate_summary(
        "按地区统计销售额并画柱状图",
        {"type": "dataframe", "rows": [{"region": "East", "sales_amount": 100}], "total_rows": 1},
        has_charts=True,
        success=True,
    )
    assert source == "rule"
    assert "图表" in summary


def test_conversation_store_roundtrip(
    session_cleanup: list[str],
    register_dataset,
):
    dataset_id = register_dataset("dataset-1")
    session_id = create_session(dataset_id)
    session_cleanup.append(session_id)

    turn_index = append_turn(
        session_id,
        ConversationTurn(
            question="按地区统计销售额",
            summary="East 销售额最高",
            generated_code="result = 1",
            success=True,
            has_charts=False,
            result={"type": "scalar", "value": 1},
        ),
    )
    assert turn_index == 0

    session = get_session(session_id)
    assert session is not None
    assert session.dataset_id == dataset_id
    assert len(session.turns) == 1
    assert session.turns[0].question == "按地区统计销售额"
    assert session.turns[0].result == {"type": "scalar", "value": 1}


def test_format_history_for_prompt():
    turns = [
        ConversationTurn(question="Q1", summary="A1", generated_code="code1", success=True),
        ConversationTurn(question="Q2", summary="A2"),
    ]
    text = format_history_for_prompt(turns)
    assert "Previous conversation" in text
    assert "Q1" in text
    assert "A2" in text
    assert "code1" in text


def test_query_api(sample_dataset_id: str, client: TestClient, disable_llm):
    response = client.post(
        f"/api/v1/datasets/{sample_dataset_id}/query",
        json={"question": "按地区统计销售额并画柱状图"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"]
    assert data["codegen_source"] == "rule"
    assert data["attempts"] == 0
    assert data["summary_source"] == "rule"
    assert data["summary"]
    assert data["session_id"]
    assert data["turn_index"] == 0
    assert data["rag_used"] is False
    assert data["rag_chunk_count"] == 0
    assert data["rag_skip_reason"] == "not_configured"
    assert "groupby" in data["generated_code"]
    assert len(data["charts"]) >= 1

    delete_session(data["session_id"])


def test_multi_turn_query(
    sample_dataset_id: str,
    client: TestClient,
    session_cleanup: list[str],
):
    first = client.post(
        f"/api/v1/datasets/{sample_dataset_id}/query",
        json={"question": "按地区统计销售额"},
    )
    assert first.status_code == 200
    first_data = first.json()
    session_id = first_data["session_id"]
    session_cleanup.append(session_id)
    assert first_data["turn_index"] == 0

    second = client.post(
        f"/api/v1/datasets/{sample_dataset_id}/query",
        json={"question": "按产品统计销售额", "session_id": session_id},
    )
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["session_id"] == session_id
    assert second_data["turn_index"] == 1

    session_resp = client.get(f"/api/v1/sessions/{session_id}")
    assert session_resp.status_code == 200
    turns = session_resp.json()["session"]["turns"]
    assert len(turns) == 2
    assert turns[0]["question"] == "按地区统计销售额"
    assert turns[1]["question"] == "按产品统计销售额"


def test_create_session_endpoint(sample_dataset_id: str, client: TestClient, session_cleanup: list[str]):
    response = client.post(f"/api/v1/datasets/{sample_dataset_id}/sessions")
    assert response.status_code == 200
    data = response.json()
    session_cleanup.append(data["session_id"])
    assert data["dataset_id"] == sample_dataset_id


def test_query_session_wrong_dataset(
    sample_dataset_id: str,
    client: TestClient,
    session_cleanup: list[str],
    register_dataset,
):
    other_dataset_id = register_dataset("other-dataset")
    session_id = create_session(other_dataset_id)
    session_cleanup.append(session_id)

    response = client.post(
        f"/api/v1/datasets/{sample_dataset_id}/query",
        json={"question": "统计销售额", "session_id": session_id},
    )
    assert response.status_code == 400


def test_delete_session_endpoint(client: TestClient, register_dataset):
    dataset_id = register_dataset("dataset-x")
    session_id = create_session(dataset_id)
    response = client.delete(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 200
    assert get_session(session_id) is None


def test_get_dataset_profile_reads_from_db(sample_dataset_id: str, monkeypatch):
    from app.services import dataset_store

    def fail_profile(*_args, **_kwargs):
        raise AssertionError("profile_file should not be called when DB has profile")

    monkeypatch.setattr(dataset_store, "profile_file", fail_profile)
    profile = dataset_store.get_dataset_profile(sample_dataset_id)
    assert profile is not None
    assert profile.dataset_id == sample_dataset_id


def test_query_api_not_found(client: TestClient):
    response = client.post(
        "/api/v1/datasets/nonexistent/query",
        json={"question": "show summary"},
    )
    assert response.status_code == 404
