
import os
import logging
from functools import lru_cache

from dotenv import load_dotenv
from tavily import TavilyClient
from langchain.tools import tool

from ai_agent.core.logging_config import setup_logging


# --------------------------------------------------
# Configuration
# --------------------------------------------------

setup_logging()
logger = logging.getLogger(__name__)

load_dotenv()


# --------------------------------------------------
# Lazy Tavily client initialization
# --------------------------------------------------

@lru_cache(maxsize=1)
def get_tavily_client() -> TavilyClient:
    """Create the Tavily client only when web search is requested."""

    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        logger.error("TAVILY_API_KEY is missing from the environment")
        raise RuntimeError(
            "TAVILY_API_KEY is missing. Check your project-root .env file."
        )

    logger.info("Initializing Tavily client")

    return TavilyClient(api_key=api_key)


# --------------------------------------------------
# Web search tool
# --------------------------------------------------

@tool
def web_search(query: str) -> str:
    """
    Search the web for current information about a topic.

    Use this tool for recent facts, news, people, events,
    or information that needs web research.

    Args:
        query: The search query.
    """
    if not query or not query.strip():
        return "Web search failed: query cannot be empty."

    try:
        logger.info("Web search requested: %s", query)

        client = get_tavily_client()
        response = client.search( query=query.strip(),
            max_results=2,)

        logger.info("Web search completed successfully")
        return str(response)

    except Exception:
        logger.exception("Web search failed")
        return "Web search failed. Check the logs for details."


# --------------------------------------------------
# Standalone test
# --------------------------------------------------

if __name__ == "__main__":
    result = web_search.invoke(
        {"query": "Who is Lionel Messi?"}
    )
    print(result)
