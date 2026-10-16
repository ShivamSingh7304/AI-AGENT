
import logging
from ai_agent.core.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

import tempfile
from pathlib import Path

from langchain.tools import tool

# Windows Desktop directory
DESKTOP_PATH = (Path.home() / "Desktop").resolve()

MAX_READ_SIZE = 1_000_000  # 1 MB


def get_desktop_file(filename: str) -> Path:
    """Resolve a filename and restrict access to the Desktop."""
    path = (DESKTOP_PATH / filename).resolve()

    if path == DESKTOP_PATH or DESKTOP_PATH not in path.parents:
        raise ValueError("Access is restricted to files on the Desktop.")

    return path


@tool
def read_desktop_file(filename: str) -> str:
    """Read a UTF-8 text file from the user's Desktop.

    Use when the user asks to read, inspect, or retrieve
    the contents of a Desktop file.

    Args:
        filename: File name or relative path, e.g. notes.txt.
    """
    try:
        path = get_desktop_file(filename)

        if not path.is_file():
            return f"File not found: {filename}"

        if path.stat().st_size > MAX_READ_SIZE:
            return "File is too large to read (maximum 1 MB)."

        content = path.read_text(encoding="utf-8")

        logger.info("Read Desktop file: %s", path.name)
        return content

    except (OSError, UnicodeError, ValueError):
        logger.exception("Failed to read Desktop file")
        return "Unable to read the file. Check its path, permissions, and encoding."


@tool
def write_desktop_file(
    filename: str,
    content: str,
    overwrite: bool = False,
) -> str:
    """Write text to a file on the user's Desktop.

    Creates a new file by default. Existing files are preserved
    unless overwrite=True is explicitly provided.

    Use when the user asks to save text, notes, or generated
    content to a Desktop file.

    Args:
        filename: File name or relative path, e.g. notes.txt.
        content: Text to write to the file.
        overwrite: Set True only when replacing an existing file
            is explicitly requested by the user.
    """
    try:
        path = get_desktop_file(filename)

        if path.exists() and not overwrite:
            return (
                f"File already exists: {filename}. "
                "Choose another filename or explicitly request an overwrite."
            )

        if path.exists() and not path.is_file():
            return "The target path is not a regular file."

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        logger.info("Wrote Desktop file: %s", path.name)
        return f"Successfully saved file: {path.name}"

    except (OSError, UnicodeError, ValueError):
        logger.exception("Failed to write Desktop file")
        return "Unable to write the file. Check the path and permissions."


@tool
def append_desktop_file(filename: str, content: str) -> str:
    """Append text to a file on the user's Desktop.

    Creates the file if it does not already exist.

    Use when the user asks to add text to the end of a Desktop file.

    Args:
        filename: File name or relative path, e.g. notes.txt.
        content: Text to append to the file.
    """
    try:
        path = get_desktop_file(filename)

        if path.exists() and not path.is_file():
            return "The target path is not a regular file."

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(content)

        logger.info("Appended to Desktop file: %s", path.name)
        return f"Successfully appended to file: {path.name}"

    except (OSError, UnicodeError, ValueError):
        logger.exception("Failed to append to Desktop file")
        return "Unable to append to the file. Check the path and permissions."


if __name__ == "__main__":
    '''result = read_desktop_file.invoke({"filename": "test_file.txt"})
    print(result)'''
    
    '''write_result = write_desktop_file.invoke({"filename": "test_file.txt", "content": "This is a test file.", "overwrite": True})
    print(write_result)'''

    '''append_result = append_desktop_file.invoke({"filename": "test_file.txt", "content": "\nThis is an appended line."})
    print(append_result)'''