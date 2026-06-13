from app.db.repositories.conversation_repo import append_turn as db_append_turn
from app.db.repositories.conversation_repo import create_session as db_create_session
from app.db.repositories.conversation_repo import delete_session as db_delete_session
from app.db.repositories.conversation_repo import get_latest_session_for_dataset as db_get_latest_session
from app.db.repositories.conversation_repo import get_session as db_get_session
from app.models.schemas import ConversationSession, ConversationTurn

PROMPT_HISTORY_TURNS = 5
CODE_PREVIEW_CHARS = 600


def create_session(dataset_id: str) -> str:
    return db_create_session(dataset_id)


def get_session(session_id: str) -> ConversationSession | None:
    return db_get_session(session_id)


def get_latest_session_for_dataset(dataset_id: str) -> ConversationSession | None:
    return db_get_latest_session(dataset_id)


def delete_session(session_id: str) -> bool:
    return db_delete_session(session_id)


def append_turn(session_id: str, turn: ConversationTurn) -> int:
    return db_append_turn(session_id, turn)


def format_history_for_prompt(
    turns: list[ConversationTurn],
    *,
    max_turns: int = PROMPT_HISTORY_TURNS,
) -> str:
    if not turns:
        return ""

    recent = turns[-max_turns:]
    lines = ["Previous conversation (oldest to newest):"]
    for index, turn in enumerate(recent, 1):
        lines.append(f"Turn {index}:")
        lines.append(f"  User: {turn.question}")
        if turn.summary:
            lines.append(f"  Assistant: {turn.summary}")
        if turn.generated_code and turn.success:
            code_preview = turn.generated_code
            if len(code_preview) > CODE_PREVIEW_CHARS:
                code_preview = code_preview[:CODE_PREVIEW_CHARS] + "..."
            lines.append(f"  Code used:\n```python\n{code_preview}\n```")
    return "\n".join(lines) + "\n\n"
