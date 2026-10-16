import logging
from pathlib import Path

from ai_agent.core.logging_config import setup_logging

logger = logging.getLogger(__name__)

from ai_agent.tools.rag.ingestion.loading import ingest_pdf

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

PROJECT_ROOT = Path(__file__).resolve().parents[5]
INDEX_PATH = PROJECT_ROOT / "vector_store" / "faiss_index"


def vector_stores(pdf_path: str | Path) -> FAISS:
    pdf_path = Path(pdf_path).expanduser().resolve()
    try:
        logger.info("Starting PDF ingestion: %s", pdf_path)
        documents = ingest_pdf(str(pdf_path))
        logger.info("PDF ingestion successful: %s", pdf_path)
    except Exception:
        logger.exception("PDF ingestion failed: %s", pdf_path)
        raise

    if not documents:
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
        logger.info("Initializing embedding model: sentence-transformers/all-MiniLM-L6-v2") 
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
    
    logger.info("Saving vector store locally: %s", INDEX_PATH)
    vector_store.save_local(str(INDEX_PATH))
     
    return vector_store

if __name__ == "__main__":
    vector_stores(input("Enter the PDF path to index: ").strip().strip('"'))