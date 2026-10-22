
import logging
from functools import lru_cache
from pathlib import Path

from langchain.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from ai_agent.core.logging_config import setup_logging


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[5]
INDEX_PATH = PROJECT_ROOT / "vector_store" / "faiss_index"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_K = 3


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """Load and reuse the embedding model."""
    logger.info("Loading embedding model: %s", EMBEDDING_MODEL)

    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
    )


@lru_cache(maxsize=16)
def load_vector_store(index_path: str | Path | None = None) -> FAISS:
    """Load and reuse the persisted FAISS index at the requested path."""
    selected_index_path = (
        Path(index_path).expanduser().resolve()
        if index_path is not None
        else INDEX_PATH
    )
    index_file = selected_index_path / "index.faiss"

    if not index_file.is_file():
        raise FileNotFoundError(
            f"FAISS index not found at {selected_index_path}. "
            "Run indexing.py first."
        )

    embeddings = get_embeddings()

    logger.info("Loading FAISS index: %s", selected_index_path)

    vector_store = FAISS.load_local(
        str(selected_index_path),
        embeddings,
        allow_dangerous_deserialization=True,
    )

    logger.info(
        "FAISS index loaded successfully: %d vectors",
        vector_store.index.ntotal,
    )

    return vector_store


def search_pdf_index(query: str, index_path: str | Path) -> str:
    """Search one session's PDF index and format its matching passages."""
    if not query.strip():
        logger.warning("Rejected empty PDF retrieval query")
        return "Please provide a non-empty search query."

    logger.info("Searching PDF index: %s", index_path)
    try:
        vector_store = load_vector_store(index_path)
        results = vector_store.similarity_search(query=query, k=DEFAULT_K)
    except Exception:
        logger.exception("PDF search failed for index: %s", index_path)
        raise
    if not results:
        logger.info("No relevant passages found in PDF index: %s", index_path)
        return "No relevant information was found in the indexed PDF."

    formatted_results = []
    for index, document in enumerate(results, start=1):
        source = document.metadata.get("source", "Unknown source")
        page = document.metadata.get("page", "Unknown page")
        formatted_results.append(
            f"Result {index}\n"
            f"Source: {source}\n"
            f"Page: {page}\n"
            f"Content:\n{document.page_content}"
        )
    logger.info(
        "PDF search returned %d passages from index %s",
        len(results),
        index_path,
    )
    return "\n\n---\n\n".join(formatted_results)


@tool
def search_pdf(query: str) -> str:
    """Search the indexed PDF for information relevant to a question.

    Use this tool when the user asks questions about the contents
    of the PDF that has already been indexed.

    Args:
        query: A specific question or search query about the PDF.
    """
    if not query.strip():
        return "Please provide a non-empty search query."

    logger.info("Searching the default indexed PDF")

    try:
        result = search_pdf_index(query, INDEX_PATH)
        logger.info("PDF search completed")
        return result

    except Exception:
        logger.exception("PDF retrieval failed")
        return (
            "PDF retrieval failed. Check that the FAISS index exists "
            "and the embedding model can be loaded."
        )


if __name__ == "__main__":
    setup_logging()

    try:
        question = input("Ask a question about the indexed PDF: ")
        print(search_pdf.invoke({"query": question}))

    except Exception:
        logger.exception("Retrieval test failed")
