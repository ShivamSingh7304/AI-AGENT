
import logging
from pathlib import Path

from langchain.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from ai_agent.core.logging_config import setup_logging


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[5]
INDEX_PATH = PROJECT_ROOT / "vector_store" / "faiss_index"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_K = 4


def load_vector_store() -> FAISS:
    """Load the persisted FAISS index from disk."""

    if not (INDEX_PATH / "index.faiss").is_file():
        raise FileNotFoundError(
            f"FAISS index not found at {INDEX_PATH}. "
            "Run indexing.py first."
        )

    logger.info("Loading embedding model: %s", EMBEDDING_MODEL)

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
    )

    logger.info("Loading FAISS index: %s", INDEX_PATH)

    vector_store = FAISS.load_local(
        str(INDEX_PATH),
        embeddings,
        # Only load indexes that you created and trust.
        allow_dangerous_deserialization=True,
    )

    logger.info(
        "FAISS index loaded successfully: %d vectors",
        vector_store.index.ntotal,
    )

    return vector_store


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

    logger.info("Searching indexed PDF for: %s", query)

    try:
        vector_store = load_vector_store()

        results = vector_store.similarity_search(
            query=query,
            k=DEFAULT_K,
        )

        if not results:
            logger.info("No matching PDF chunks found")
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

        logger.info("PDF search completed: %d results", len(results))

        return "\n\n---\n\n".join(formatted_results)

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

        result = search_pdf.invoke({"query": question})

        print("\nRetrieval results:\n")
        print(result)

    except Exception:
        logger.exception("Retrieval test failed")
