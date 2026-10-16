
import time
import logging
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_groq import ChatGroq

from ai_agent.core.logging_config import setup_logging

load_dotenv()

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Load SOUL.md
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOUL_PATH = PROJECT_ROOT / "SOUL.md"

try:
    soul_prompt = SOUL_PATH.read_text(encoding="utf-8")
    logger.info("SOUL.md loaded successfully")
except OSError:
    logger.exception("Failed to load SOUL.md")
    raise

# Initialize LLM
try:
    llm = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.3,
        max_retries=2,
    )
    logger.info("LLM initialized successfully")
except Exception:
    logger.exception("LLM initialization failed")
    raise

# Create agent
tools = []

try:
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=soul_prompt,
    )
    logger.info("Agent created successfully")
except Exception:
    logger.exception("Agent creation failed")
    raise


def chat():
    """Run an interactive chat session with conversation history."""

    messages = []

    print("\nAI Agent Chat")
    print("Type 'exit' or 'quit' to end the conversation.\n")

    while True:
        try:
            question = input("You: ").strip()

            if question.lower() in {"exit", "quit"}:
                logger.info("Chat session ended")
                print("AI Agent: Goodbye!")
                break

            if not question:
                continue

            # Add the user's message to the conversation
            messages.append({
                "role": "user",
                "content": question,
            })

            logger.info("Agent invocation started")
            start_time = time.perf_counter()

            response = agent.invoke({
                "messages": messages
            })

            # Preserve the complete conversation state
            messages = response["messages"]

            answer = messages[-1].content

            logger.info(
                "Agent invocation completed in %.2f seconds",
                time.perf_counter() - start_time,
            )

            print(f"\nAI Agent: {answer}\n")

        except KeyboardInterrupt:
            logger.info("Chat interrupted by user")
            print("\nAI Agent: Goodbye!")
            break

        except Exception:
            logger.exception("Agent invocation failed")
            print("AI Agent: Something went wrong. Please try again.")


if __name__ == "__main__":
    chat()
