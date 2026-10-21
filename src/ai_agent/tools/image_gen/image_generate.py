
import logging
import os
import shutil
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from gradio_client import Client

from ai_agent.core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


# --------------------------------------------------
# Configuration
# --------------------------------------------------

# Project root: AI-AGENT/
PROJECT_ROOT = Path(__file__).resolve().parents[4]

load_dotenv(PROJECT_ROOT / ".env")

SPACE_ID = "Viggle/Qwen-Image-2.1-viggle-turbo"

OUTPUT_DIR = PROJECT_ROOT / "generated_images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from functools import lru_cache


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Initialize the Hugging Face Space client only when needed."""

    token = os.getenv("HF_TOKEN")
    client_kwargs = {"token": token} if token else {}

    logger.info("Connecting to image-generation Space: %s", SPACE_ID)

    return Client(SPACE_ID, **client_kwargs)

# --------------------------------------------------
# Image generation
# --------------------------------------------------

def generate_image(
    prompt: str,
    output_name: str = "generated_image.png",
) -> Path:
    """
    Generate an image through the public Hugging Face Space
    and save it locally.
    """

    logger.info("Starting image generation for prompt: %s", prompt)

    if not prompt or not prompt.strip():
        logger.error("Image generation rejected: empty prompt")
        raise ValueError("Prompt cannot be empty.")

    if Path(output_name).name != output_name:
        logger.error("Image generation rejected: invalid output_name: %s", output_name)
        raise ValueError("output_name must be a filename, not a path.")

    if not output_name.lower().endswith(
        (".png", ".jpg", ".jpeg", ".webp")
    ):
        logger.error("Image generation rejected: unsupported format for %s", output_name)
        raise ValueError("Use a .png, .jpg, .jpeg, or .webp filename.")

    logger.info("Generating image with output_name=%s", output_name)

    # Call the Space's documented generation endpoint.
    try:
        client = get_client()

        result = client.predict(
            prompt=prompt,
            refs=[],
            size_label="1:1 · 512×512 (512² area)",
            seed=0,
            randomize_seed=True,
            enhance="Auto",
            steps=6,
            custom_width=512,
            custom_height=512,
            version="v0.3",
            api_name="/generate",
        )
    except Exception:
        logger.exception("Image generation request failed for prompt: %s", prompt)
        raise

    logger.info("Received result from Space for prompt: %s", prompt)

    if not isinstance(result, (tuple, list)) or not result:
        logger.error("Unexpected image response from Space: %r", result)
        raise RuntimeError(
            f"Unexpected response from Space: {result!r}"
        )

    image_info = result[0]
    destination = OUTPUT_DIR / output_name

    # Case 1: Gradio returns image metadata as a dictionary.
    if isinstance(image_info, dict):
        image_path = image_info.get("path")
        image_url = image_info.get("url")

    # Case 2: Gradio returns a string path or URL.
    elif isinstance(image_info, str):
        if Path(image_info).is_file():
            image_path = image_info
            image_url = None
        elif image_info.startswith(("http://", "https://")):
            image_path = None
            image_url = image_info
        else:
            raise RuntimeError(
                "The Space returned a string that is neither "
                f"a local file nor a URL: {image_info!r}"
            )

    else:
        raise TypeError(
            "Unexpected image result type: "
            f"{type(image_info).__name__}. "
            f"Full result: {result!r}"
        )

    # Save the image locally.
    try:
        if image_path and Path(image_path).is_file():
            logger.info("Copying generated image from local path %s to %s", image_path, destination)
            shutil.copy2(image_path, destination)

        elif image_url:
            parsed_url = urlparse(image_url)

            if parsed_url.scheme not in ("http", "https"):
                logger.error("Returned image URL is invalid: %s", image_url)
                raise RuntimeError("The returned image URL is invalid.")

            logger.info("Downloading generated image from %s", image_url)

            request = urllib.request.Request(
                image_url,
                headers={"User-Agent": "AI-Agent/1.0"},
            )

            with urllib.request.urlopen(request, timeout=120) as response:
                content_type = response.headers.get("Content-Type", "")

                if not content_type.startswith("image/"):
                    logger.error("Returned URL did not provide an image: %s", content_type)
                    raise RuntimeError(
                        "The returned URL did not provide an image. "
                        f"Content-Type: {content_type}"
                    )

                destination.write_bytes(response.read())

        else:
            logger.error("No accessible image path or URL was returned: %r", image_info)
            raise RuntimeError(
                "No accessible image path or URL was returned.\n"
                f"Image result: {image_info!r}"
            )
    except Exception:
        logger.exception("Failed while saving generated image for prompt: %s", prompt)
        raise

    logger.info("Image saved successfully: %s", destination.resolve())

    return destination


# --------------------------------------------------
# Run directly
# --------------------------------------------------

if __name__ == "__main__":
    try:
        saved_image = generate_image(
            prompt=(
                "A futuristic AI laboratory with a robotic assistant, "
                "cinematic lighting, highly detailed, realistic"
            )
        )

        print(f"Done: {saved_image}")

    except Exception as exc:
        print(f"Image generation failed: {exc}")
        raise
