import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from ai_agent.agent.database.repository import (
    create_session,
    delete_session,
    list_sessions,
    session_exists,
)
from ai_agent.api.schemas import SessionCreate, SessionDeleteResponse, SessionResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])

PROJECT_ROOT = Path(__file__).resolve().parents[5]
LOCAL_DATA_DIRS = (
    PROJECT_ROOT / "data" / "uploads",
    PROJECT_ROOT / "vector_store" / "pdf_indexes",
    PROJECT_ROOT / "generated_images",
)


def validate_session_id(session_id: str) -> str:
    try:
        return str(UUID(session_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Session ID must be a UUID.",
        ) from exc


def require_session(session_id: str) -> str:
    validated_id = validate_session_id(session_id)
    if not session_exists(validated_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )
    return validated_id


def cleanup_session_files(paths: list[str]) -> None:
    """Remove only registered files contained in known local data folders."""
    allowed_roots = [root.resolve() for root in LOCAL_DATA_DIRS]
    for stored_path in paths:
        path = Path(stored_path).resolve()
        if not any(path.is_relative_to(root) for root in allowed_roots):
            logger.warning(
                "Skipped deleting session asset outside managed folders: %s",
                path,
            )
            continue

        try:
            if path.is_dir():
                for child in path.iterdir():
                    if child.is_file():
                        child.unlink()
                path.rmdir()
            else:
                path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove local session asset: %s", path)


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chat_session(request: SessionCreate) -> SessionResponse:
    try:
        session_id = create_session(title=request.title)
        session = next(
            row for row in list_sessions() if row["id"] == session_id
        )
    except Exception as exc:
        logger.exception("API could not create chat session")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create a chat session.",
        ) from exc
    return SessionResponse(**session)


@router.get("", response_model=list[SessionResponse])
def get_chat_sessions() -> list[SessionResponse]:
    try:
        return [SessionResponse(**row) for row in list_sessions()]
    except Exception as exc:
        logger.exception("API could not list chat sessions")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load chat sessions.",
        ) from exc


@router.delete(
    "/{session_id}",
    response_model=SessionDeleteResponse,
)
def remove_chat_session(session_id: str) -> SessionDeleteResponse:
    validated_id = require_session(session_id)
    try:
        local_paths = delete_session(validated_id)
        cleanup_session_files(local_paths)
    except Exception as exc:
        logger.exception("API could not delete chat session %s", validated_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not delete the chat session.",
        ) from exc
    return SessionDeleteResponse(deleted=True)
