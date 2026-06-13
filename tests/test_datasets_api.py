from pathlib import Path
import uuid

from app.config import UPLOAD_DIR
from app.db.repositories.dataset_repo import delete_dataset

SAMPLE_CSV = Path(__file__).resolve().parent / "data" / "sample_sales.csv"


def test_list_datasets_returns_recent(client, register_dataset):
    dataset_id = register_dataset()
    response = client.get("/api/v1/datasets?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    ids = [item["dataset_id"] for item in payload["datasets"]]
    assert dataset_id in ids


def test_get_dataset_detail(client, register_dataset):
    dataset_id = register_dataset()
    response = client.get(f"/api/v1/datasets/{dataset_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["dataset_id"] == dataset_id
    assert payload["profile"]["filename"] == "sample_sales.csv"


def test_upload_deduplicates_identical_file(client):
    marker = uuid.uuid4().hex
    base = SAMPLE_CSV.read_text(encoding="utf-8").rstrip("\n")
    content = f"{base}\nDedupTest_{marker},0,2099-01-01,Test\n".encode("utf-8")
    first = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sample_sales.csv", content, "text/csv")},
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload.get("deduplicated") is not True
    first_id = first_payload["profile"]["dataset_id"]

    second = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("sample_sales.csv", content, "text/csv")},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload.get("deduplicated") is True
    assert second_payload["profile"]["dataset_id"] == first_id

    delete_dataset(first_id)
    (UPLOAD_DIR / f"{first_id}.csv").unlink(missing_ok=True)
