import hashlib
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import UPLOAD_DIR
from app.db.repositories.dataset_repo import dataset_exists, delete_dataset
from app.db.schema import init_schema
from app.main import app
from app.services.dataset_store import save_dataset
from app.services.profiler import profile_file

SAMPLE_CSV = Path(__file__).resolve().parent / "data" / "sample_sales.csv"


def _unique_test_csv_content(dataset_id: str) -> bytes:
    base = SAMPLE_CSV.read_text(encoding="utf-8").rstrip("\n")
    marker_row = f"TestMarker_{dataset_id},0,2099-01-01,Test"
    return f"{base}\n{marker_row}\n".encode("utf-8")


@pytest.fixture(scope="session", autouse=True)
def _init_db() -> None:
    init_schema()


@pytest.fixture(autouse=True)
def disable_rag_by_default(monkeypatch):
    monkeypatch.setattr("app.config.RAG_ENABLED", False)
    monkeypatch.setattr("app.config.RAGFLOW_BASE_URL", "")
    monkeypatch.setattr("app.config.RAGFLOW_API_KEY", "")
    monkeypatch.setattr("app.services.ragflow_client.RAG_ENABLED", False)
    monkeypatch.setattr("app.services.ragflow_client.RAGFLOW_BASE_URL", "")
    monkeypatch.setattr("app.services.ragflow_client.RAGFLOW_API_KEY", "")


def _register_dataset(dataset_id: str | None = None) -> str:
    dataset_id = dataset_id or uuid.uuid4().hex
    if dataset_exists(dataset_id):
        delete_dataset(dataset_id)

    content = _unique_test_csv_content(dataset_id)
    dest = UPLOAD_DIR / f"{dataset_id}.csv"
    dest.write_bytes(content)
    profile = profile_file(dest, dataset_id, "sample_sales.csv")
    save_dataset(
        dataset_id=dataset_id,
        original_filename="sample_sales.csv",
        stored_path=dest,
        profile=profile,
        file_size_bytes=len(content),
        content_hash=hashlib.sha256(content).hexdigest(),
    )
    return dataset_id


@pytest.fixture
def sample_dataset_id() -> str:
    dataset_id = _register_dataset()
    yield dataset_id
    delete_dataset(dataset_id)
    (UPLOAD_DIR / f"{dataset_id}.csv").unlink(missing_ok=True)


@pytest.fixture
def register_dataset() -> Callable[[str | None], str]:
    created: list[str] = []

    def _factory(dataset_id: str | None = None) -> str:
        dataset_id = _register_dataset(dataset_id)
        created.append(dataset_id)
        return dataset_id

    yield _factory

    for dataset_id in created:
        delete_dataset(dataset_id)
        path = UPLOAD_DIR / f"{dataset_id}.csv"
        if path.exists():
            path.unlink(missing_ok=True)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
