import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pymysql

from app.config import MAX_CONVERSATION_TURNS
from app.db.connection import db_cursor
from app.models.schemas import ChartArtifact, ConversationSession, ConversationTurn


def _now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _dt_to_iso(value: datetime) -> str:
    if value.tzinfo is not None:
        return value.astimezone(UTC).isoformat()
    return value.replace(tzinfo=UTC).isoformat()


def _row_to_turn(row: dict[str, Any]) -> ConversationTurn:
    result = row.get("result_json")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = None

    charts_raw = row.get("charts_json")
    charts: list[ChartArtifact] = []
    if charts_raw:
        if isinstance(charts_raw, str):
            try:
                charts_raw = json.loads(charts_raw)
            except json.JSONDecodeError:
                charts_raw = []
        if isinstance(charts_raw, list):
            charts = [ChartArtifact.model_validate(item) for item in charts_raw]

    return ConversationTurn(
        question=row["question"],
        summary=row.get("summary") or "",
        generated_code=row.get("generated_code"),
        success=bool(row.get("success", True)),
        has_charts=bool(row.get("has_charts", False)),
        result=result,
        charts=charts,
        error=row.get("error"),
    )


def create_session(dataset_id: str) -> str:
    session_id = uuid.uuid4().hex
    now = _now_utc()

    try:
        with db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversation_sessions (session_id, dataset_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                """,
                (session_id, dataset_id, now, now),
            )
    except pymysql.IntegrityError as exc:
        raise ValueError(f"Dataset '{dataset_id}' not found; cannot create session") from exc
    except pymysql.Error as exc:
        raise ValueError(f"Failed to create conversation session: {exc}") from exc

    return session_id


def get_latest_session_for_dataset(dataset_id: str) -> ConversationSession | None:
    try:
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT session_id, dataset_id, created_at, updated_at
                FROM conversation_sessions
                WHERE dataset_id = %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (dataset_id,),
            )
            session_row = cursor.fetchone()
            if session_row is None:
                return None

            cursor.execute(
                """
                SELECT question, summary, generated_code, success, has_charts,
                       result_json, charts_json, error
                FROM conversation_turns
                WHERE session_id = %s
                ORDER BY turn_index ASC
                """,
                (session_row["session_id"],),
            )
            turn_rows = cursor.fetchall()
    except pymysql.Error:
        return None

    turns = [_row_to_turn(row) for row in turn_rows]
    return ConversationSession(
        session_id=session_row["session_id"],
        dataset_id=session_row["dataset_id"],
        created_at=_dt_to_iso(session_row["created_at"]),
        updated_at=_dt_to_iso(session_row["updated_at"]),
        turns=turns,
    )


def get_session(session_id: str) -> ConversationSession | None:
    try:
        with db_cursor() as cursor:
            cursor.execute(
                """
                SELECT session_id, dataset_id, created_at, updated_at
                FROM conversation_sessions
                WHERE session_id = %s
                """,
                (session_id,),
            )
            session_row = cursor.fetchone()
            if session_row is None:
                return None

            cursor.execute(
                """
                SELECT question, summary, generated_code, success, has_charts,
                       result_json, charts_json, error
                FROM conversation_turns
                WHERE session_id = %s
                ORDER BY turn_index ASC
                """,
                (session_id,),
            )
            turn_rows = cursor.fetchall()
    except pymysql.Error:
        return None

    turns = [_row_to_turn(row) for row in turn_rows]
    return ConversationSession(
        session_id=session_row["session_id"],
        dataset_id=session_row["dataset_id"],
        created_at=_dt_to_iso(session_row["created_at"]),
        updated_at=_dt_to_iso(session_row["updated_at"]),
        turns=turns,
    )


def delete_session(session_id: str) -> bool:
    try:
        with db_cursor() as cursor:
            affected = cursor.execute(
                "DELETE FROM conversation_sessions WHERE session_id = %s",
                (session_id,),
            )
            return affected > 0
    except pymysql.Error:
        return False


def append_turn(session_id: str, turn: ConversationTurn) -> int:
    now = _now_utc()
    result_json = json.dumps(turn.result, ensure_ascii=False, default=str) if turn.result is not None else None
    charts_json = (
        json.dumps([chart.model_dump() for chart in turn.charts], ensure_ascii=False)
        if turn.charts
        else None
    )

    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT dataset_id FROM conversation_sessions WHERE session_id = %s",
                (session_id,),
            )
            if cursor.fetchone() is None:
                raise ValueError(f"Session '{session_id}' not found")

            cursor.execute(
                "SELECT COALESCE(MAX(turn_index), -1) AS max_index FROM conversation_turns WHERE session_id = %s",
                (session_id,),
            )
            max_index = int(cursor.fetchone()["max_index"])
            turn_index = max_index + 1

            cursor.execute(
                """
                INSERT INTO conversation_turns (
                    session_id, turn_index, question, summary, generated_code,
                    success, has_charts, result_json, charts_json, error, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    turn_index,
                    turn.question,
                    turn.summary,
                    turn.generated_code,
                    int(turn.success),
                    int(turn.has_charts),
                    result_json,
                    charts_json,
                    turn.error,
                    now,
                ),
            )

            cursor.execute(
                "UPDATE conversation_sessions SET updated_at = %s WHERE session_id = %s",
                (now, session_id),
            )

            cursor.execute(
                """
                SELECT id FROM conversation_turns
                WHERE session_id = %s
                ORDER BY turn_index DESC
                """,
                (session_id,),
            )
            turn_ids = [row["id"] for row in cursor.fetchall()]
            if len(turn_ids) > MAX_CONVERSATION_TURNS:
                stale_ids = turn_ids[MAX_CONVERSATION_TURNS:]
                placeholders = ", ".join(["%s"] * len(stale_ids))
                cursor.execute(
                    f"DELETE FROM conversation_turns WHERE id IN ({placeholders})",
                    stale_ids,
                )

    except ValueError:
        raise
    except pymysql.Error as exc:
        raise ValueError(f"Failed to save conversation turn: {exc}") from exc

    return turn_index
