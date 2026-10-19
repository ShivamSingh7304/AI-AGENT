import logging

from ai_agent.core.logging_config import setup_logging
from langchain.tools import tool

from .image_generate import generate_image

setup_logging()
logger = logging.getLogger(__name__)


@tool
def generate_image_tool(prompt: str) -> str:
    """
    Generate an image from a text description using the
    Hugging Face Viggle image-generation Space.

    Use this tool when the user explicitly asks to create,
    generate, or visualize an image.
    The generated image is saved locally.
    """
    try:
        logger.info("Image tool invoked with prompt: %s", prompt)
        image_path = generate_image(prompt=prompt)
        logger.info("Image tool completed successfully: %s", image_path.resolve())

        return (
            "Image generated successfully. "
            f"Saved at: {image_path.resolve()}"
        )

    except Exception as exc:
        logger.exception("Image generation failed for prompt: %s", prompt)
        return f"Image generation failed: {exc}"
