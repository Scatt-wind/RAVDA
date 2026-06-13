from pathlib import Path

from app.config import ALLOWED_EXTENSIONS, UPLOAD_DIR
from app.db.repositories.dataset_repo import find_dataset_by_content_hash as find_by_hash_in_db
from app.db.repositories.dataset_repo import get_profile as get_profile_from_db
from app.db.repositories.dataset_repo import list_recent_datasets as list_recent_from_db
from app.db.repositories.dataset_repo import save_dataset as save_dataset_to_db
from app.models.schemas import DatasetProfile
from app.services.profiler import profile_file
from app.services.rag_service import schedule_dataset_indexing


def find_dataset_path(dataset_id: str) -> Path | None:
    for ext in ALLOWED_EXTENSIONS:
        path = UPLOAD_DIR / f"{dataset_id}{ext}"
        if path.is_file():
            return path
    return None


def save_dataset(
    dataset_id: str,
    original_filename: str,
    stored_path: Path,
    profile: DatasetProfile,
    file_size_bytes: int,
    content_hash: str,
) -> None:
    save_dataset_to_db(
        dataset_id=dataset_id,
        original_filename=original_filename,
        stored_path=stored_path,
        profile=profile,
        file_size_bytes=file_size_bytes,
        content_hash=content_hash,
    )
    schedule_dataset_indexing(dataset_id, stored_path, profile)


def find_dataset_by_content_hash(content_hash: str) -> str | None:
    return find_by_hash_in_db(content_hash)


def list_recent_datasets(limit: int = 10) -> list[dict[str, object]]:
    return list_recent_from_db(limit)


def get_dataset_profile(dataset_id: str) -> DatasetProfile | None:
    profile = get_profile_from_db(dataset_id)
    if profile is not None:
        return profile

    path = find_dataset_path(dataset_id)
    if path is None:
        return None
    return profile_file(path, dataset_id, path.name)
