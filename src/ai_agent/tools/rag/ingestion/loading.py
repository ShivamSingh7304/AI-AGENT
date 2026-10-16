import logging
from pathlib import Path

from pypdf import PdfReader
from langchain_core.documents import Document

from ai_agent.core.logging_config import setup_logging

logger = logging.getLogger(__name__)


def ingest_pdf(pdf_path: str) -> list[Document]:
    """Extract text from a PDF and return one Document per page."""

    path = Path(pdf_path).expanduser().resolve()

    logger.info("Starting PDF ingestion: %s", path)

    if not path.is_file():
        logger.error("PDF file not found: %s", path)
        raise FileNotFoundError(f"PDF not found: {path}")

    documents = []

    try:
        reader = PdfReader(str(path))
        total_pages = len(reader.pages)

        logger.info("Total pages in PDF: %d", total_pages)

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""

            if not text.strip():
                logger.warning(
                    "No extractable text on page %d of %s",
                    page_number,
                    path.name,
                )
                continue

            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": str(path),
                        "page": page_number,
                    },
                )
            )

        logger.info(
            "PDF ingestion completed: %d/%d pages extracted",
            len(documents),
            total_pages,
        )

        return documents

    except Exception:
        logger.exception("PDF ingestion failed: %s", path)
        raise

if __name__ == "__main__":
    setup_logging()

    # PDF stored in the project root
    #pdf_path = Path(__file__).resolve().parents[3] / ""
    pdf_path = Path("")
    try:
        docs = ingest_pdf(str(pdf_path))

        print(f"\nTotal documents extracted: {len(docs)}")

        for doc in docs[:3]:
            print("\n" + "=" * 50)
            print(f"Page: {doc.metadata['page']}")
            print(f"Source: {doc.metadata['source']}")
            print(doc.page_content[:200])

    except (FileNotFoundError, Exception) as exc:
        logger.error("Test failed: %s", exc)