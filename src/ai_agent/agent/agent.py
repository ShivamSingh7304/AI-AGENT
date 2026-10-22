import time
import logging
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_groq import ChatGroq
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.tools import BaseTool


from ai_agent.core.logging_config import setup_logging

# --------------------------------------------------
# Tools
# --------------------------------------------------
from ai_agent.tools.file_read_write.file import (
    read_desktop_file,
    write_desktop_file,
    append_desktop_file,
)

from ai_agent.tools.rag.ingestion.retrieval import search_pdf
from ai_agent.tools.websearch.web_search import web_search
from ai_agent.tools.weather.weather_search import get_weather
from ai_agent.tools.image_gen.image import generate_image_tool
# --------------------------------------------------
# Configuration
# --------------------------------------------------
load_dotenv()
setup_logging()

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 5

# --------------------------------------------------
# Load SOUL.md
# --------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOUL_PATH = PROJECT_ROOT / "SOUL.md"


def load_system_prompt() -> str:
    """Load the agent's system prompt from SOUL.md."""

    try:
        prompt = SOUL_PATH.read_text(encoding="utf-8").strip()

        if not prompt:
            raise ValueError("SOUL.md is empty.")

        logger.info("SOUL.md loaded successfully")
        return prompt

    except (OSError, ValueError):
        logger.exception("Failed to load SOUL.md")
        raise


soul_prompt = load_system_prompt()


# --------------------------------------------------
# Initialize LLM
# --------------------------------------------------
try:
    llm = ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.3,
        max_retries=3,
        timeout=60,
        max_tokens=2048,
        streaming=True,
    )

    logger.info("LLM initialized successfully")

except Exception:
    logger.exception("LLM initialization failed")
    raise


# --------------------------------------------------
# Register tools
# --------------------------------------------------
tools = [
    read_desktop_file,
    write_desktop_file,
    append_desktop_file,
    search_pdf,
    web_search,
    get_weather,
    generate_image_tool
]


def create_configured_agent(
    agent_tools: list[BaseTool],
    model: ChatGroq = llm,
):
    return create_agent(
        model=model,
        tools=agent_tools,
        system_prompt=soul_prompt,
        middleware=[
            SummarizationMiddleware(
                model=model,
                trigger=("tokens", 6000),
                keep=("messages", 3),
            )
        ],
    )


# The Streamlit app performs retrieval against the session's selected PDF
# before invoking the agent, so it must not also expose the global-index tool.
try:
    app_tools = [
        registered_tool
        for registered_tool in tools
        if registered_tool.name != "search_pdf"
    ]
    agent = create_configured_agent(tools)
    app_agent = create_configured_agent(app_tools)
    app_agent_non_streaming = create_configured_agent(
        app_tools,
        model=llm.model_copy(update={"streaming": False}),
    )
    logger.info("Agents created successfully")
except Exception:
    logger.exception("Agent creation failed")
    raise


# --------------------------------------------------
# Response extraction
# --------------------------------------------------
def extract_final_answer(messages) -> str:
    """Extract the latest assistant response from agent messages."""

    for message in reversed(messages):
        if getattr(message, "type", None) == "ai":
            content = message.content

            if isinstance(content, str):
                return content.strip() or "I couldn't generate a response."

            if isinstance(content, list):
                text_parts = [
                    block["text"]
                    for block in content
                    if isinstance(block, dict)
                    and isinstance(block.get("text"), str)
                ]

                if text_parts:
                    return "\n".join(text_parts).strip()

                return str(content)

            return str(content)

    return "The agent did not return an assistant response."



def trim_history(messages, max_messages=MAX_HISTORY_MESSAGES):
    """
    Limit conversation history to reduce token usage.

    Keep the system prompt separate; create_agent receives it
    through system_prompt.
    """

    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]



def chat():
    """Run an interactive chat session."""

    messages = []

    print("\nAI Agent Chat")
    print("Type 'exit' or 'quit' to end the conversation.")
    print("Type 'clear' to reset conversation history.\n")

    while True:
        try:
            question = input("You: ").strip()

            if question.lower() in {"exit", "quit"}:
                logger.info("Chat session ended")
                print("\nAI Agent: Goodbye!")
                break

            if question.lower() == "clear":
                messages.clear()
                logger.info("Conversation history cleared")
                print("AI Agent: Conversation history cleared.\n")
                continue

            if not question:
                continue

            messages.append(
                {
                    "role": "user",
                    "content": question,
                }
            )

            logger.info("Agent invocation started")
            start_time = time.perf_counter()

            response = agent.invoke({"messages": messages})
            messages = response.get("messages", messages)

            answer = extract_final_answer(messages)

            logger.info(
                "Agent invocation completed in %.2f seconds",
                time.perf_counter() - start_time,
            )

            print(f"\nAI Agent: {answer}\n")
            messages = trim_history(messages)

        except KeyboardInterrupt:
            logger.info("Chat interrupted by user")
            print("\nAI Agent: Goodbye!")
            break

        except EOFError:
            logger.info("Input stream closed")
            print("\nAI Agent: Goodbye!")
            break

        except Exception:
            logger.exception("Agent invocation failed")
            print(
                "\nAI Agent: Something went wrong. "
                "Please check the logs and try again.\n"
            )


# --------------------------------------------------
# Entry point
# --------------------------------------------------
if __name__ == "__main__":
    chat()