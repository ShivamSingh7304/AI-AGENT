from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class SessionResponse(BaseModel):
    id: str
    title: str
    updated_at: datetime


class DocumentResponse(BaseModel):
    id: str
    filename: str
    is_active: bool


class ActiveDocumentRequest(BaseModel):
    document_id: str | None


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    document_id: str | None = None


class PersistMessageTurnRequest(BaseModel):
    turn_id: UUID = Field(default_factory=uuid4)
    user_content: str = Field(min_length=1, max_length=20_000)
    assistant_content: str = Field(min_length=1, max_length=20_000)
    document_id: str | None = None
    image_path: str | None = None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    image_path: str | None = None
    documents: list[dict[str, str]] = Field(default_factory=list)


class MessageTurnResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse


class SessionDeleteResponse(BaseModel):
    deleted: bool
