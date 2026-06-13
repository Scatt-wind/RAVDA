import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB, UPLOAD_DIR
from app.models.schemas import (
    DatasetDetailResponse,
    DatasetListResponse,
    DatasetRagStatusResponse,
    DatasetSummary,
    UploadResponse,
)
from app.services.dataset_store import (
    find_dataset_by_content_hash,
    get_dataset_profile,
    list_recent_datasets,
    save_dataset,
)
from app.services.profiler import profile_file
from app.services.rag_service import get_rag_index_status, get_rag_status, reindex_dataset
from app.services.ragflow_client import is_rag_configured

router = APIRouter(prefix="/datasets", tags=["datasets"])

MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


def _validate_extension(filename: str) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {allowed}",
        )
    return suffix


@router.get("", response_model=DatasetListResponse)
def list_datasets(
    limit: int = Query(default=10, ge=1, le=100, description="Max datasets to return"),
) -> DatasetListResponse:
    rows = list_recent_datasets(limit)
    datasets = [DatasetSummary.model_validate(row) for row in rows]
    return DatasetListResponse(datasets=datasets, total=len(datasets))


@router.get("/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(dataset_id: str) -> DatasetDetailResponse:
    profile = get_dataset_profile(dataset_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")

    return DatasetDetailResponse(
        profile=profile,
        rag_index_status=get_rag_index_status(dataset_id),
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(file: UploadFile = File(...)) -> UploadResponse:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = _validate_extension(file.filename)

    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {exc}") from exc

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_MB} MB",
        )

    content_hash = hashlib.sha256(content).hexdigest()
    existing_id = find_dataset_by_content_hash(content_hash)
    if existing_id is not None:
        profile = get_dataset_profile(existing_id)
        if profile is not None:
            return UploadResponse(
                message="Dataset already exists, reusing existing upload",
                profile=profile,
                rag_index_status=get_rag_index_status(existing_id),
                deduplicated=True,
            )

    dataset_id = uuid.uuid4().hex
    saved_name = f"{dataset_id}{suffix}"
    saved_path = UPLOAD_DIR / saved_name

    try:
        saved_path.write_bytes(content)
        profile = profile_file(saved_path, dataset_id, file.filename)
        save_dataset(
            dataset_id=dataset_id,
            original_filename=file.filename,
            stored_path=saved_path,
            profile=profile,
            file_size_bytes=len(content),
            content_hash=content_hash,
        )
    except ValueError as exc:
        if saved_path.exists():
            saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if saved_path.exists():
            saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to profile dataset: {exc}") from exc

    return UploadResponse(
        message="Dataset uploaded and profiled successfully",
        profile=profile,
        rag_index_status=get_rag_index_status(dataset_id),
    )


@router.get("/{dataset_id}/rag", response_model=DatasetRagStatusResponse)
def get_dataset_rag_status(dataset_id: str) -> DatasetRagStatusResponse:
    profile = get_dataset_profile(dataset_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")

    meta = get_rag_status(dataset_id)
    return DatasetRagStatusResponse(
        dataset_id=dataset_id,
        rag_index_status=meta.get("rag_index_status") or "pending",
        ragflow_kb_id=meta.get("ragflow_kb_id"),
        rag_index_error=meta.get("rag_index_error"),
        rag_configured=is_rag_configured(),
    )


@router.post("/{dataset_id}/rag/reindex", response_model=DatasetRagStatusResponse)
def reindex_dataset_rag(dataset_id: str) -> DatasetRagStatusResponse:
    profile = get_dataset_profile(dataset_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")

    try:
        status = reindex_dataset(dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meta = get_rag_status(dataset_id)
    return DatasetRagStatusResponse(
        dataset_id=dataset_id,
        rag_index_status=status or meta.get("rag_index_status") or "pending",
        ragflow_kb_id=meta.get("ragflow_kb_id"),
        rag_index_error=meta.get("rag_index_error"),
        rag_configured=is_rag_configured(),
    )
