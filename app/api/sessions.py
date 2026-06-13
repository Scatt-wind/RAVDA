from fastapi import APIRouter, HTTPException

from app.models.schemas import SessionResponse
from app.services.conversation_store import delete_session, get_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=SessionResponse)
def get_conversation_session(session_id: str) -> SessionResponse:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return SessionResponse(session=session)


@router.delete("/{session_id}")
def delete_conversation_session(session_id: str) -> dict[str, str]:
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"message": "Session deleted"}
