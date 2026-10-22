from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ai_agent.agent.database.connection import get_session_factory
from ai_agent.agent.database.models import (
    Document,
    GeneratedImage,
    Message,
    MessageDocument,
    SessionDocument,
    SessionRecord,
)

logger = logging.getLogger(__name__)


@contextmanager
def _database_session(operation: str, *, write: bool = False) -> Iterator[Session]:
    """Log database failures consistently and preserve their exceptions."""
    try:
        factory = get_session_factory()
        if write:
            with factory.begin() as db:
                yield db
        else:
            with factory() as db:
                yield db
    except Exception:
        logger.exception("Database operation failed: %s", operation)
        raise


def create_session() -> str:
    session_id = str(uuid4())
    with _database_session("create chat session", write=True) as db:
        db.add(SessionRecord(id=session_id))
    logger.info("Created chat session %s", session_id)
    return session_id


def list_sessions() -> list[dict]:
    with _database_session("list chat sessions") as db:
        rows = db.scalars(
            select(SessionRecord).order_by(
                SessionRecord.updated_at.desc(),
                SessionRecord.id,
            )
        ).all()
        sessions = [
            {
                "id": row.id,
                "title": row.title or "New conversation",
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
    logger.debug("Loaded %d chat sessions", len(sessions))
    return sessions


def save_message(
    session_id: str,
    role: str,
    content: str,
    *,
    image_prompt: str | None = None,
    image_path: str | None = None,
) -> str:
    if role not in {"user", "assistant"}:
        logger.error("Rejected unsupported message role: %s", role)
        raise ValueError("Message role must be 'user' or 'assistant'.")
    if (image_prompt is None) != (image_path is None):
        logger.error("Rejected incomplete generated image metadata")
        raise ValueError("An image prompt and path must be provided together.")

    message_id = str(uuid4())
    with _database_session("save chat message", write=True) as db:
        chat_session = db.scalar(
            select(SessionRecord)
            .where(SessionRecord.id == session_id)
            .with_for_update()
        )
        if chat_session is None:
            raise ValueError(f"Chat session not found: {session_id}")

        sequence = db.scalar(
            select(func.coalesce(func.max(Message.sequence), 0) + 1).where(
                Message.session_id == session_id
            )
        )
        db.add(
            Message(
                id=message_id,
                session_id=session_id,
                sequence=sequence,
                role=role,
                content=content,
            )
        )
        if image_prompt is not None and image_path is not None:
            # Ensure the referenced message exists before inserting its image.
            db.flush()

        if role == "user" and chat_session.title is None:
            chat_session.title = content.strip()[:200] or "New conversation"
        chat_session.updated_at = func.now()
        if image_prompt is not None and image_path is not None:
            db.add(
                GeneratedImage(
                    message_id=message_id,
                    prompt=image_prompt,
                    file_path=image_path,
                )
            )

    logger.info(
        "Saved %s message %s for chat session %s",
        role,
        message_id,
        session_id,
    )
    return message_id


def get_session_messages(session_id: str) -> list[dict]:
    with _database_session("load chat messages") as db:
        messages = db.scalars(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.sequence)
        ).all()
        if not messages:
            logger.debug("No messages found for chat session %s", session_id)
            return []

        message_ids = [message.id for message in messages]
        document_rows = db.execute(
            select(MessageDocument.message_id, Document.id, Document.filename)
            .join(Document, Document.id == MessageDocument.document_id)
            .where(MessageDocument.message_id.in_(message_ids))
        ).all()
        image_rows = db.execute(
            select(GeneratedImage.message_id, GeneratedImage.file_path)
            .where(GeneratedImage.message_id.in_(message_ids))
        ).all()

        documents_by_message: dict[str, list[dict[str, str]]] = {}
        for message_id, document_id, filename in document_rows:
            documents_by_message.setdefault(message_id, []).append(
                {"id": document_id, "filename": filename}
            )
        images_by_message = {
            message_id: file_path for message_id, file_path in image_rows
        }

        result = [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "image_path": images_by_message.get(message.id),
                "documents": documents_by_message.get(message.id, []),
            }
            for message in messages
        ]
    logger.debug(
        "Loaded %d messages for chat session %s",
        len(result),
        session_id,
    )
    return result


def add_document_to_session(
    session_id: str,
    document_id: str,
    filename: str,
    file_path: str,
    index_path: str,
) -> None:
    with _database_session("attach PDF to chat session", write=True) as db:
        if db.get(SessionRecord, session_id) is None:
            raise ValueError(f"Chat session not found: {session_id}")

        db.add(
            Document(
                id=document_id,
                filename=filename,
                file_path=file_path,
                index_path=index_path,
            )
        )
        db.execute(
            update(SessionDocument)
            .where(SessionDocument.session_id == session_id)
            .values(is_active=False)
        )
        db.add(
            SessionDocument(
                session_id=session_id,
                document_id=document_id,
                is_active=True,
            )
        )
    logger.info(
        "Attached PDF %s to chat session %s",
        document_id,
        session_id,
    )


def list_session_documents(session_id: str) -> list[dict]:
    with _database_session("list session PDFs") as db:
        rows = db.execute(
            select(
                Document.id,
                Document.filename,
                Document.index_path,
                SessionDocument.is_active,
            )
            .join(SessionDocument, SessionDocument.document_id == Document.id)
            .where(SessionDocument.session_id == session_id)
            .order_by(Document.created_at.desc())
        ).all()
        documents = [
            {
                "id": document_id,
                "filename": filename,
                "index_path": index_path,
                "is_active": is_active,
            }
            for document_id, filename, index_path, is_active in rows
        ]
    logger.debug(
        "Loaded %d PDFs for chat session %s",
        len(documents),
        session_id,
    )
    return documents


def set_active_document(session_id: str, document_id: str | None) -> None:
    with _database_session("set active session PDF", write=True) as db:
        if document_id is not None:
            link = db.get(SessionDocument, (session_id, document_id))
            if link is None:
                raise ValueError(
                    "The selected PDF is not linked to this chat session."
                )

        db.execute(
            update(SessionDocument)
            .where(SessionDocument.session_id == session_id)
            .values(is_active=False)
        )
        if document_id is not None:
            db.execute(
                update(SessionDocument)
                .where(
                    SessionDocument.session_id == session_id,
                    SessionDocument.document_id == document_id,
                )
                .values(is_active=True)
            )
    logger.info(
        "Set active PDF for session %s to %s",
        session_id,
        document_id or "none",
    )


def attach_document_to_message(message_id: str, document_id: str) -> None:
    with _database_session("link PDF to chat message", write=True) as db:
        message = db.get(Message, message_id)
        if message is None:
            raise ValueError(f"Chat message not found: {message_id}")
        if db.get(SessionDocument, (message.session_id, document_id)) is None:
            raise ValueError("The PDF is not linked to this message's chat.")

        if db.get(MessageDocument, (message_id, document_id)) is None:
            db.add(MessageDocument(message_id=message_id, document_id=document_id))
    logger.info(
        "Linked PDF %s to message %s",
        document_id,
        message_id,
    )
