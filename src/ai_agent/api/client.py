import json
import logging
import os
from pathlib import Path
from collections.abc import Callable, Iterator
from typing import Any

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
DEFAULT_API_URL = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


class APIClientError(RuntimeError):
    """A user-displayable error returned by the AI Agent API."""


def _request(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    files: dict | None = None,
) -> Any:
    base_url = os.getenv("AI_AGENT_API_URL", DEFAULT_API_URL).rstrip("/")
    try:
        with httpx.Client(timeout=300.0) as client:
            response = client.request(
                method,
                f"{base_url}{path}",
                json=json,
                files=files,
            )
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise APIClientError(
                f"API request failed ({response.status_code}): {detail}"
            )
        return response.json() if response.content else None
    except APIClientError:
        logger.exception("AI Agent API returned an error for %s %s", method, path)
        raise
    except httpx.HTTPError as exc:
        logger.exception("Could not reach AI Agent API at %s", base_url)
        raise APIClientError(
            f"Could not reach the API at {base_url}. Start it with "
            "`uv run uvicorn ai_agent.api.main:app --app-dir src "
            "--host 127.0.0.1 --port 8000`."
        ) from exc


def list_sessions() -> list[dict]:
    return _request("GET", "/sessions")


def create_session() -> dict:
    return _request("POST", "/sessions", json={})


def delete_session(session_id: str) -> dict:
    return _request("DELETE", f"/sessions/{session_id}")


def list_messages(session_id: str) -> list[dict]:
    return _request("GET", f"/sessions/{session_id}/messages")


def send_message(
    session_id: str,
    content: str,
    *,
    document_id: str | None = None,
) -> dict:
    return _request(
        "POST",
        f"/sessions/{session_id}/messages",
        json={"content": content, "document_id": document_id},
    )


def stream_message(
    session_id: str,
    content: str,
    *,
    document_id: str | None = None,
    on_complete: Callable[[dict], None] | None = None,
) -> Iterator[str]:
    base_url = os.getenv("AI_AGENT_API_URL", DEFAULT_API_URL).rstrip("/")
    path = f"/sessions/{session_id}/messages/stream"
    try:
        with httpx.Client(timeout=300.0) as client:
            with client.stream(
                "POST",
                f"{base_url}{path}",
                json={"content": content, "document_id": document_id},
            ) as response:
                if response.is_error:
                    response.read()
                    try:
                        detail = response.json().get("detail", response.text)
                    except ValueError:
                        detail = response.text
                    raise APIClientError(
                        f"API request failed ({response.status_code}): {detail}"
                    )

                completed = False
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError as exc:
                        raise APIClientError(
                            "The API returned an invalid streaming response."
                        ) from exc

                    if event.get("type") == "token":
                        text = event.get("text")
                        if not isinstance(text, str):
                            raise APIClientError(
                                "The API returned an invalid text chunk."
                            )
                        yield text
                    elif event.get("type") == "done":
                        completed = True
                        if on_complete is not None:
                            on_complete(event)
                    elif event.get("type") == "error":
                        raise APIClientError(
                            f"API request failed "
                            f"({event.get('status_code', 'unknown')}): "
                            f"{event.get('detail', 'Unknown API error')}"
                        )

                if not completed:
                    raise APIClientError(
                        "The API stream ended before generation completed."
                    )
    except APIClientError:
        logger.exception("AI Agent API streaming request failed for %s", path)
        raise
    except httpx.HTTPError as exc:
        logger.exception("Could not stream from AI Agent API at %s", base_url)
        raise APIClientError(
            f"Could not stream from the API at {base_url}. Check that the "
            "FastAPI server is running."
        ) from exc


def persist_message_turn(
    session_id: str,
    turn_id: str,
    user_content: str,
    assistant_content: str,
    *,
    document_id: str | None = None,
    image_path: str | None = None,
) -> dict:
    return _request(
        "POST",
        f"/sessions/{session_id}/messages/persist",
        json={
            "turn_id": turn_id,
            "user_content": user_content,
            "assistant_content": assistant_content,
            "document_id": document_id,
            "image_path": image_path,
        },
    )


def list_documents(session_id: str) -> list[dict]:
    return _request("GET", f"/sessions/{session_id}/documents")


def upload_document(session_id: str, filename: str, contents: bytes) -> dict:
    return _request(
        "POST",
        f"/sessions/{session_id}/documents",
        files={"file": (Path(filename).name, contents, "application/pdf")},
    )


def select_active_document(
    session_id: str,
    document_id: str | None,
) -> list[dict]:
    return _request(
        "PATCH",
        f"/sessions/{session_id}/documents/active",
        json={"document_id": document_id},
    )
