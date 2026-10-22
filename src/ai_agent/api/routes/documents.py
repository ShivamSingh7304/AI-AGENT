import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from ai_agent.agent.database.repository import (
    add_document_to_session,
    list_session_documents,
    set_active_document,
)
from ai_agent.api.routes.sessions import require_session
from ai_agent.api.schemas import (
    ActiveDocumentRequest,
    DocumentResponse,
)
from ai_agent.tools.rag.ingestion.indexing import (
    PROJECT_ROOT,
    get_pdf_index_path,
    vector_stores,
)
from ai_agent.tools.rag.ingestion.retrieval import (
    get_embeddings,
    load_vector_store,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions/{session_id}/documents", tags=["documents"])
MAX_PDF_SIZE = 25 * 1024 * 1024


def _index_pdf_bytes(
    session_id: str,
    filename: str,
    contents: bytes,
) -> dict:
    document_id = str(uuid4())
    safe_name = Path(filename.replace("\\", "/")).name
    upload_dir = PROJECT_ROOT / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{uuid4().hex}_{safe_name}"
    index_path = get_pdf_index_path(document_id)

    try:
        upload_path.write_bytes(contents)
        vector_stores(upload_path, index_path=index_path)
        load_vector_store.cache_clear()
        get_embeddings.cache_clear()
        add_document_to_session(
            session_id=session_id,
            document_id=document_id,
            filename=safe_name,
            file_path=str(upload_path.resolve()),
            index_path=str(index_path.resolve()),
        )
    except Exception:
        logger.exception(
            "Could not index PDF %s for session %s",
            safe_name,
            session_id,
        )
        upload_path.unlink(missing_ok=True)
        if index_path.is_dir():
            for child in index_path.iterdir():
                if child.is_file():
                    child.unlink()
            index_path.rmdir()
        raise

    logger.info("Indexed PDF %s for session %s", safe_name, session_id)
    return {
        "id": document_id,
        "filename": safe_name,
        "is_active": True,
    }


@router.get("", response_model=list[DocumentResponse])
def get_documents(session_id: str) -> list[DocumentResponse]:
    validated_id = require_session(session_id)
    try:
        documents = list_session_documents(validated_id)
    except Exception as exc:
        logger.exception("Could not list PDFs for session %s", validated_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load this chat's PDFs.",
        ) from exc
    return [
        DocumentResponse(
            id=document["id"],
            filename=document["filename"],
            is_active=document["is_active"],
        )
        for document in documents
    ]


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    session_id: str,
    file: UploadFile = File(...),
) -> DocumentResponse:
    validated_id = require_session(session_id)
    filename = Path((file.filename or "").replace("\\", "/")).name
    if not filename or Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a file with a .pdf extension.",
        )

    try:
        contents = await file.read(MAX_PDF_SIZE + 1)
        if len(contents) > MAX_PDF_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="PDF uploads must be 25 MB or smaller.",
            )
        if not contents:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The uploaded PDF is empty.",
            )

        document = await run_in_threadpool(
            _index_pdf_bytes,
            validated_id,
            filename,
            contents,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("API failed to index PDF for session %s", validated_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The PDF could not be indexed.",
        ) from exc
    finally:
        await file.close()

    return DocumentResponse(**document)


@router.patch("/active", response_model=list[DocumentResponse])
def select_active_document(
    session_id: str,
    request: ActiveDocumentRequest,
) -> list[DocumentResponse]:
    validated_id = require_session(session_id)
    try:
        set_active_document(validated_id, request.document_id)
        documents = list_session_documents(validated_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Could not update active PDF for %s", validated_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not select the active PDF.",
        ) from exc

    return [
        DocumentResponse(
            id=document["id"],
            filename=document["filename"],
            is_active=document["is_active"],
        )
        for document in documents
    ]
