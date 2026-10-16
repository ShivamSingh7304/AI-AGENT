import os
from dotenv import load_dotenv
from tavily import TavilyClient
from langchain.tools import tool

load_dotenv()


# Initialize logging
from ai_agent.core.logging_config import setup_logging
import logging
setup_logging()
logger = logging.getLogger(__name__)



try:
    api_key = os.getenv("TAVILY_API_KEY")
    logger.info("tavily key found successfully")
except:
    logger.exception("TAVILY_API_KEY not found in .env")
    raise

tavily_client = TavilyClient(api_key=api_key)


@tool
def web_search(query: str) -> str:
    """Search the web for current information about a topic.
    Use this tool when the user asks for recent facts, news,
    people, events, or information that needs web research.
    Args:
        query: The search query.
    """
    try:
        response = tavily_client.search(query=query)
        return str(response)
    except Exception as e:
        return f"Web search failed: {e}"


if __name__ == "__main__":
    result = web_search.invoke({"query": "Who is Lionel Messi?"})
    print(result)
