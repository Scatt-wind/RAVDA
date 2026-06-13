from fastapi.testclient import TestClient


def test_upload_returns_rag_index_status(
    client: TestClient,
    monkeypatch,
):
    monkeypatch.setattr("app.services.rag_service.is_rag_configured", lambda: False)
    sample = "tests/data/sample_sales.csv"
    with open(sample, "rb") as handle:
        response = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("sample_sales.csv", handle, "text/csv")},
        )
    assert response.status_code == 200
    data = response.json()
    assert "rag_index_status" in data
    assert data["rag_index_status"] == "skipped"


def test_get_dataset_rag_status(sample_dataset_id: str, client: TestClient):
    response = client.get(f"/api/v1/datasets/{sample_dataset_id}/rag")
    assert response.status_code == 200
    data = response.json()
    assert data["dataset_id"] == sample_dataset_id
    assert "rag_index_status" in data
    assert data["rag_configured"] is False


def test_health_includes_rag_configured(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert "rag_configured" in response.json()
