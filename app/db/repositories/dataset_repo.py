import json
from datetime import UTC, datetime
from pathlib import Path

import pymysql

from app.db.connection import db_cursor
from app.models.schemas import DatasetProfile


def _now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def save_dataset(
    dataset_id: str,
    original_filename: str,
    stored_path: Path,
    profile: DatasetProfile,
    file_size_bytes: int,
    content_hash: str,
) -> None:
    now = _now_utc()
    profile_json = profile.model_dump_json()
    stored_filename = stored_path.name
    file_ext = stored_path.suffix.lower()

    try:
        with db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO datasets (
                    dataset_id, original_filename, stored_filename, file_ext,
                    file_size_bytes, row_count, column_count, profile_json,
                    content_hash, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    dataset_id,
                    original_filename,
                    stored_filename,
                    file_ext,
                    file_size_bytes,
                    profile.row_count,
                    profile.column_count,
                    profile_json,
                    content_hash,
                    now,
                    now,
                ),
            )
    except pymysql.Error as exc:
        raise ValueError(f"Failed to save dataset to database: {exc}") from exc


def get_profile(dataset_id: str) -> DatasetProfile | None:
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT profile_json FROM datasets WHERE dataset_id = %s",
                (dataset_id,),
            )
            row = cursor.fetchone()
    except pymysql.Error:
        return None

    if row is None:
        return None

    try:
        raw = row["profile_json"]
        if isinstance(raw, (dict, list)):
            data = raw
        else:
            data = json.loads(raw)
        return DatasetProfile.model_validate(data)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def dataset_exists(dataset_id: str) -> bool:
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM datasets WHERE dataset_id = %s LIMIT 1",
                (dataset_id,),
            )
            return cursor.fetchone() is not None
    except pymysql.Error:
        return False


def get_rag_meta(dataset_id: str) -> dict[str, str | None] | None:
    try:
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT ragflow_kb_id, rag_index_status, rag_index_error
                FROM datasets
                WHERE dataset_id = %s
                """,
                (dataset_id,),
            )
            row = cursor.fetchone()
    except pymysql.Error:
        return None

    if row is None:
        return None

    return {
        "ragflow_kb_id": row.get("ragflow_kb_id"),
        "rag_index_status": row.get("rag_index_status") or "pending",
        "rag_index_error": row.get("rag_index_error"),
    }


def update_rag_meta(
    dataset_id: str,
    *,
    ragflow_kb_id: str | None = None,
    rag_index_status: str | None = None,
    rag_index_error: str | None = None,
) -> None:
    fields: list[str] = []
    values: list[object] = []

    if ragflow_kb_id is not None:
        fields.append("ragflow_kb_id = %s")
        values.append(ragflow_kb_id)
    if rag_index_status is not None:
        fields.append("rag_index_status = %s")
        values.append(rag_index_status)
    if rag_index_error is not None:
        fields.append("rag_index_error = %s")
        values.append(rag_index_error)

    if not fields:
        return

    fields.append("updated_at = %s")
    values.append(_now_utc())
    values.append(dataset_id)

    try:
        with db_cursor() as cursor:
            cursor.execute(
                f"UPDATE datasets SET {', '.join(fields)} WHERE dataset_id = %s",
                tuple(values),
            )
    except pymysql.Error as exc:
        raise ValueError(f"Failed to update RAG metadata: {exc}") from exc


def find_dataset_by_content_hash(content_hash: str) -> str | None:
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT dataset_id FROM datasets WHERE content_hash = %s LIMIT 1",
                (content_hash,),
            )
            row = cursor.fetchone()
    except pymysql.Error:
        return None

    if row is None:
        return None
    return row["dataset_id"]


def list_recent_datasets(limit: int = 10) -> list[dict[str, object]]:
    safe_limit = max(1, min(limit, 100))
    try:
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT dataset_id, original_filename, file_size_bytes,
                       row_count, column_count, created_at, rag_index_status
                FROM datasets
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            rows = cursor.fetchall()
    except pymysql.Error:
        return []

    results: list[dict[str, object]] = []
    for row in rows:
        created_at = row.get("created_at")
        results.append(
            {
                "dataset_id": row["dataset_id"],
                "original_filename": row["original_filename"],
                "file_size_bytes": row["file_size_bytes"],
                "row_count": row["row_count"],
                "column_count": row["column_count"],
                "created_at": created_at.isoformat() if created_at else "",
                "rag_index_status": row.get("rag_index_status") or "pending",
            }
        )
    return results


def delete_dataset(dataset_id: str) -> bool:
    try:
        with db_cursor() as cursor:
            affected = cursor.execute(
                "DELETE FROM datasets WHERE dataset_id = %s",
                (dataset_id,),
            )
            return affected > 0
    except pymysql.Error:
        return False
