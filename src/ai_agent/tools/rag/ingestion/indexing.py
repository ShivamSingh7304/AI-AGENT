import logging
from pathlib import Path
from uuid import UUID

from ai_agent.core.logging_config import setup_logging

logger = logging.getLogger(__name__)

from ai_agent.tools.rag.ingestion.loading import ingest_pdf

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

PROJECT_ROOT = Path(__file__).resolve().parents[5]
INDEX_PATH = PROJECT_ROOT / "vector_store" / "faiss_index"
PDF_INDEX_ROOT = PROJECT_ROOT / "vector_store" / "pdf_indexes"


def get_pdf_index_path(document_id: str) -> Path:
    """Build the index path from a validated document UUID."""
    try:
        validated_id = UUID(document_id)
    except ValueError:
        logger.error("Invalid document ID for PDF index path: %s", document_id)
        raise
    index_path = PDF_INDEX_ROOT / str(validated_id)
    logger.debug("Resolved PDF index path for document %s", validated_id)
    return index_path


def vector_stores(
    pdf_path: str | Path,
    index_path: str | Path | None = None,
) -> FAISS:
    pdf_path = Path(pdf_path).expanduser().resolve()
    target_index_path = (
        Path(index_path).expanduser().resolve()
        if index_path is not None
        else INDEX_PATH
    )
    try:
        logger.info("Starting PDF ingestion: %s", pdf_path.name)
        documents = ingest_pdf(str(pdf_path))
        logger.info("PDF ingestion successful: %s", pdf_path.name)
    except Exception:
        logger.exception("PDF ingestion failed: %s", pdf_path.name)
        raise

    if not documents:
        logger.error("PDF contains no extractable text: %s", pdf_path.name)
        raise ValueError("No extractable text was found in the PDF.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=200
    )
    try:
        chunks = splitter.split_documents(documents)
        logger.info("Text splitting successful: %d chunks created", len(chunks))
    except Exception:
        logger.exception("Text splitting failed")
        raise
    try:
        logger.info(
            "Initializing embedding model: "
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
    except Exception:
        logger.exception("Embedding model initialization failed")
        raise
    try:
        vector_store = FAISS.from_documents(
            documents=chunks,
            embedding=embedding_model
        )
    except Exception:
        logger.exception("Failed to create vector store")
        raise
    
    try:
        logger.info("Saving vector store locally: %s", target_index_path.name)
        vector_store.save_local(str(target_index_path))
    except Exception:
        logger.exception("Failed to save vector store: %s", target_index_path.name)
        raise

    logger.info(
        "PDF indexing completed: %s (%d chunks)",
        pdf_path.name,
        len(chunks),
    )
     
    return vector_store

if __name__ == "__main__":
    setup_logging()
    vector_stores(input("Enter the PDF path to index: ").strip().strip('"'))