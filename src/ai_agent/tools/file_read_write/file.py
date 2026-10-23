import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.middleware import Middleware as StarletteMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ai_agent.core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

DESKTOP_PATH = (Path.home() / "Desktop").resolve()
MAX_READ_SIZE = 1_000_000

mcp = FastMCP("Desktop File Tools")


class JsonRpcTraceMiddleware:
    """Capture raw MCP JSON-RPC messages at the Streamable HTTP boundary."""

    def __init__(self, app: ASGIApp, log_path: Path) -> None:
        self.app = app
        self._logger = logging.getLogger("ai_agent.mcp.jsonrpc")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        resolved_log_path = log_path.resolve()

        if not any(
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename) == resolved_log_path
            for handler in self._logger.handlers
        ):
            resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
            self._logger.addHandler(
                RotatingFileHandler(
                    resolved_log_path,
                    maxBytes=10_000_000,
                    backupCount=5,
                    encoding="utf-8",
                )
            )

    @staticmethod
    def _decode_messages(body: bytes, content_type: str) -> list[object]:
        if not body:
            return []

        if "text/event-stream" in content_type:
            payloads = [
                line[5:].strip()
                for line in body.decode("utf-8").splitlines()
                if line.startswith("data:")
            ]
            messages = [json.loads(payload) for payload in payloads if payload]
        else:
            decoded = json.loads(body)
            messages = decoded if isinstance(decoded, list) else [decoded]

        return [message for message in messages if isinstance(message, dict)]

    def _write_trace(
        self,
        request_body: bytes,
        response_body: bytes,
        response_content_type: str,
    ) -> None:
        requests = self._decode_messages(request_body, "application/json")
        responses = self._decode_messages(response_body, response_content_type)
        responses_by_id = {
            json.dumps(response.get("id"), sort_keys=True): response
            for response in responses
            if "id" in response
        }

        for request in requests:
            response = None
            if "id" in request:
                response = responses_by_id.get(
                    json.dumps(request["id"], sort_keys=True)
                )
            self._logger.info(
                "%s",
                json.dumps(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "request": request,
                        "response": response,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_chunks: list[bytes] = []
        response_chunks: list[bytes] = []
        response_content_type = ""

        async def capture_request() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                request_chunks.append(message.get("body", b""))
            return message

        async def capture_response(message: Message) -> None:
            nonlocal response_content_type
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                response_content_type = headers.get(b"content-type", b"").decode(
                    "latin-1"
                )
            elif message["type"] == "http.response.body":
                response_chunks.append(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, capture_request, capture_response)
        finally:
            try:
                self._write_trace(
                    b"".join(request_chunks),
                    b"".join(response_chunks),
                    response_content_type,
                )
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                self._logger.warning(
                    "Could not decode MCP HTTP message for JSON-RPC trace: %s",
                    error,
                )


def get_file_mcp_url() -> str:
    """Return the Streamable HTTP endpoint used by the agent."""
    port = os.getenv("AI_AGENT_FILE_MCP_PORT", "8001")
    return os.getenv(
        "AI_AGENT_FILE_MCP_URL",
        f"http://127.0.0.1:{port}/mcp",
    )


def get_desktop_file(filename: str) -> Path:
    """Resolve a filename and restrict access to the Desktop."""
    path = (DESKTOP_PATH / filename).resolve()

    if path == DESKTOP_PATH or DESKTOP_PATH not in path.parents:
        raise ValueError("Access is restricted to files on the Desktop.")

    return path


@mcp.tool
def read_desktop_file(filename: str) -> str:
    """Read a UTF-8 text file from the user's Desktop.

    Use when the user asks to read, inspect, or retrieve the contents of a
    Desktop file.

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


@mcp.tool
def write_desktop_file(
    filename: str,
    content: str,
    overwrite: bool = False,
) -> str:
    """Write text to a file on the user's Desktop.

    Creates a new file by default. Existing files are preserved unless
    overwrite=True is explicitly provided.

    Use when the user asks to save text, notes, or generated content to a
    Desktop file.

    Args:
        filename: File name or relative path, e.g. notes.txt.
        content: Text to write to the file.
        overwrite: Set True only when replacing an existing file is explicitly
            requested by the user.
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


@mcp.tool
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


def main() -> None:
    """Run the Desktop file tools over Streamable HTTP."""
    load_dotenv()
    mcp.run(
        transport="http",
        host=os.getenv("AI_AGENT_FILE_MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("AI_AGENT_FILE_MCP_PORT", "8001")),
        path="/mcp",
        middleware=[
            StarletteMiddleware(
                JsonRpcTraceMiddleware,
                log_path=Path(__file__).resolve().parents[4]
                / "logs"
                / "mcp_jsonrpc.jsonl",
            )
        ],
    )


if __name__ == "__main__":
    main()
