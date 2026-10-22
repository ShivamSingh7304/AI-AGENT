import json
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import httpx
from groq import APIError
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from ai_agent.api import client as api_client
from ai_agent.api.main import app


class ApiEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.session_id = str(uuid4())
        self.now = datetime.now(timezone.utc)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_create_and_list_sessions(self) -> None:
        session_record = {
            "id": self.session_id,
            "title": "Research chat",
            "updated_at": self.now,
        }
        with (
            patch(
                "ai_agent.api.routes.sessions.create_session",
                return_value=self.session_id,
            ),
            patch(
                "ai_agent.api.routes.sessions.list_sessions",
                return_value=[session_record],
            ),
        ):
            created = self.client.post(
                "/sessions",
                json={"title": "Research chat"},
            )
            listed = self.client.get("/sessions")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["id"], self.session_id)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["title"], "Research chat")

    def test_get_messages_validates_session_and_returns_history(self) -> None:
        expected = [
            {
                "id": str(uuid4()),
                "role": "user",
                "content": "Hello",
                "image_path": None,
                "documents": [],
            }
        ]
        with (
            patch(
                "ai_agent.api.routes.messages.require_session",
                return_value=self.session_id,
            ),
            patch(
                "ai_agent.api.routes.messages.get_session_messages",
                return_value=expected,
            ),
        ):
            response = self.client.get(
                f"/sessions/{self.session_id}/messages"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)

    def test_send_message_rejects_blank_content(self) -> None:
        with patch(
            "ai_agent.api.routes.messages.require_session",
            return_value=self.session_id,
        ):
            response = self.client.post(
                f"/sessions/{self.session_id}/messages",
                json={"content": "   "},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "Message content cannot be blank.",
        )

    def test_stream_message_finishes_before_persistence(self) -> None:
        fake_agent = SimpleNamespace()

        def stream_agent(*args, **kwargs):
            self.assertEqual(args[0]["messages"][-1]["role"], "user")
            self.assertEqual(
                args[0]["messages"][-1]["content"],
                "Hello",
            )
            self.assertEqual(kwargs["stream_mode"], "messages")
            return iter(
                [
                    (
                        AIMessageChunk(content="Hi "),
                        {"langgraph_node": "model"},
                    ),
                    (
                        AIMessageChunk(content="there."),
                        {"langgraph_node": "model"},
                    ),
                ]
            )

        fake_agent.stream = stream_agent

        with (
            patch(
                "ai_agent.api.routes.messages.require_session",
                return_value=self.session_id,
            ),
            patch(
                "ai_agent.api.routes.messages.save_message_turn"
            ) as save_turn,
            patch(
                "ai_agent.api.routes.messages.list_session_documents",
                return_value=[],
            ),
            patch(
                "ai_agent.api.routes.messages.get_session_messages",
                return_value=[],
            ),
            patch.dict(
                sys.modules,
                {
                    "ai_agent.agent.agent": SimpleNamespace(
                        MAX_HISTORY_MESSAGES=5,
                        app_agent=fake_agent,
                    )
                },
            ),
        ):
            response = self.client.post(
                f"/sessions/{self.session_id}/messages/stream",
                json={"content": "Hello"},
            )

        self.assertEqual(response.status_code, 200)
        events = [
            json.loads(line)
            for line in response.text.splitlines()
            if line.strip()
        ]
        self.assertEqual(
            [event["text"] for event in events if event["type"] == "token"],
            ["Hi ", "there."],
        )
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(
            events[-1]["answer"],
            "Hi there.",
        )
        save_turn.assert_not_called()

    def test_stream_retries_malformed_groq_tool_call_without_streaming(self) -> None:
        class MalformedStream:
            def __iter__(self):
                raise APIError(
                    "Failed to parse tool call arguments as JSON",
                    httpx.Request(
                        "POST",
                        "https://api.groq.com/openai/v1/chat/completions",
                    ),
                    body=None,
                )

        def stream_agent(*args, **kwargs):
            self.assertEqual(kwargs["stream_mode"], "messages")
            self.assertEqual(
                args[0]["messages"][-1]["content"],
                "Write about FastAPI to fastapi.txt",
            )
            return MalformedStream()

        def fallback_invoke(input_data):
            self.assertEqual(
                input_data["messages"][-1]["content"],
                "Write about FastAPI to fastapi.txt",
            )
            return {
                "messages": [
                    AIMessage(content="Created fastapi.txt on your Desktop.")
                ]
            }

        fake_agent = SimpleNamespace(
            stream=stream_agent
        )
        fallback_agent = SimpleNamespace(
            invoke=fallback_invoke
        )

        with (
            patch(
                "ai_agent.api.routes.messages.require_session",
                return_value=self.session_id,
            ),
            patch(
                "ai_agent.api.routes.messages.list_session_documents",
                return_value=[],
            ),
            patch(
                "ai_agent.api.routes.messages.get_session_messages",
                return_value=[],
            ),
            patch.dict(
                sys.modules,
                {
                    "ai_agent.agent.agent": SimpleNamespace(
                        MAX_HISTORY_MESSAGES=5,
                        app_agent=fake_agent,
                        app_agent_non_streaming=fallback_agent,
                    )
                },
            ),
        ):
            response = self.client.post(
                f"/sessions/{self.session_id}/messages/stream",
                json={"content": "Write about FastAPI to fastapi.txt"},
            )

        events = [
            json.loads(line)
            for line in response.text.splitlines()
            if line.strip()
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [event["text"] for event in events if event["type"] == "token"],
            ["Created fastapi.txt on your Desktop."],
        )
        self.assertEqual(events[-1]["type"], "done")

    def test_persist_endpoint_saves_pair_as_one_turn(self) -> None:
        turn_id = str(uuid4())
        with (
            patch(
                "ai_agent.api.routes.messages.require_session",
                return_value=self.session_id,
            ),
            patch(
                "ai_agent.api.routes.messages.save_message_turn",
                return_value=("user-id", "assistant-id"),
            ) as save_turn,
        ):
            response = self.client.post(
                f"/sessions/{self.session_id}/messages/persist",
                json={
                    "turn_id": turn_id,
                    "user_content": "Hello",
                    "assistant_content": "Hi there.",
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user_message"]["id"], "user-id")
        self.assertEqual(
            response.json()["assistant_message"]["id"],
            "assistant-id",
        )
        save_turn.assert_called_once_with(
            self.session_id,
            "Hello",
            "Hi there.",
            document_id=None,
            image_prompt=None,
            image_path=None,
            turn_id=turn_id,
        )

    def test_non_streaming_message_endpoint_keeps_persisting_turns(self) -> None:
        fake_agent = SimpleNamespace()

        def stream_agent(input_data, *, stream_mode):
            self.assertEqual(stream_mode, "messages")
            self.assertEqual(
                input_data["messages"][-1]["content"],
                "Hello",
            )
            return iter(
                [
                    (
                        AIMessageChunk(content="Hi there."),
                        {"langgraph_node": "model"},
                    )
                ]
            )

        fake_agent.stream = stream_agent
        with (
            patch(
                "ai_agent.api.routes.messages.require_session",
                return_value=self.session_id,
            ),
            patch(
                "ai_agent.api.routes.messages.list_session_documents",
                return_value=[],
            ),
            patch(
                "ai_agent.api.routes.messages.get_session_messages",
                return_value=[],
            ),
            patch(
                "ai_agent.api.routes.messages.save_message_turn",
                return_value=("user-id", "assistant-id"),
            ) as save_turn,
            patch.dict(
                sys.modules,
                {
                    "ai_agent.agent.agent": SimpleNamespace(
                        MAX_HISTORY_MESSAGES=5,
                        app_agent=fake_agent,
                    )
                },
            ),
        ):
            response = self.client.post(
                f"/sessions/{self.session_id}/messages",
                json={"content": "Hello"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["assistant_message"]["content"],
            "Hi there.",
        )
        save_turn.assert_called_once()

    def test_upload_requires_pdf_extension_and_valid_session(self) -> None:
        with patch(
            "ai_agent.api.routes.documents.require_session",
            return_value=self.session_id,
        ):
            response = self.client.post(
                f"/sessions/{self.session_id}/documents",
                files={"file": ("notes.txt", b"not a PDF", "text/plain")},
            )

        self.assertEqual(response.status_code, 415)

    def test_upload_indexes_pdf_for_session(self) -> None:
        indexed_document = {
            "id": str(uuid4()),
            "filename": "notes.pdf",
            "is_active": True,
        }
        with (
            patch(
                "ai_agent.api.routes.documents.require_session",
                return_value=self.session_id,
            ),
            patch(
                "ai_agent.api.routes.documents._index_pdf_bytes",
                return_value=indexed_document,
            ) as index_pdf,
        ):
            response = self.client.post(
                f"/sessions/{self.session_id}/documents",
                files={"file": ("notes.pdf", b"%PDF-test", "application/pdf")},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), indexed_document)
        index_pdf.assert_called_once_with(
            self.session_id,
            "notes.pdf",
            b"%PDF-test",
        )

    def test_select_active_document(self) -> None:
        document_id = str(uuid4())
        documents = [
            {
                "id": document_id,
                "filename": "notes.pdf",
                "is_active": True,
            }
        ]
        with (
            patch(
                "ai_agent.api.routes.documents.require_session",
                return_value=self.session_id,
            ),
            patch(
                "ai_agent.api.routes.documents.set_active_document"
            ) as set_active,
            patch(
                "ai_agent.api.routes.documents.list_session_documents",
                return_value=documents,
            ),
        ):
            response = self.client.patch(
                f"/sessions/{self.session_id}/documents/active",
                json={"document_id": document_id},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), documents)
        set_active.assert_called_once_with(self.session_id, document_id)

    def test_delete_session_cleans_database_records(self) -> None:
        with (
            patch(
                "ai_agent.api.routes.sessions.session_exists",
                return_value=True,
            ),
            patch(
                "ai_agent.api.routes.sessions.delete_session",
                return_value=[],
            ),
            patch("ai_agent.api.routes.sessions.cleanup_session_files"),
        ):
            response = self.client.delete(f"/sessions/{self.session_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": True})

    def test_streaming_api_client_yields_tokens_and_completion(self) -> None:
        body = "\n".join(
            [
                json.dumps({"type": "token", "text": "Hello"}),
                json.dumps(
                    {
                        "type": "done",
                        "answer": "Hello",
                        "documents": [],
                        "image_path": None,
                    }
                ),
            ]
        )
        def handle_request(request: httpx.Request) -> httpx.Response:
            self.assertTrue(request.url.path.endswith("/messages/stream"))
            return httpx.Response(
                200,
                content=body,
                headers={"content-type": "application/x-ndjson"},
            )

        transport = httpx.MockTransport(handle_request)
        stream_client = httpx.Client(transport=transport)
        completed_turn = {}

        with patch(
            "ai_agent.api.client.httpx.Client",
            return_value=stream_client,
        ):
            tokens = list(
                api_client.stream_message(
                    self.session_id,
                    "Hello",
                    on_complete=completed_turn.update,
                )
            )

        self.assertEqual(tokens, ["Hello"])
        self.assertEqual(completed_turn["answer"], "Hello")
        self.assertEqual(completed_turn["documents"], [])

    def test_persist_client_sends_turn_id_and_both_messages(self) -> None:
        turn_id = str(uuid4())

        def handle_request(request: httpx.Request) -> httpx.Response:
            self.assertTrue(request.url.path.endswith("/messages/persist"))
            self.assertEqual(
                json.loads(request.content),
                {
                    "turn_id": turn_id,
                    "user_content": "Hello",
                    "assistant_content": "Hi there.",
                    "document_id": None,
                    "image_path": None,
                },
            )
            return httpx.Response(201, json={"saved": True})

        persistence_client = httpx.Client(
            transport=httpx.MockTransport(handle_request)
        )
        with patch(
            "ai_agent.api.client.httpx.Client",
            return_value=persistence_client,
        ):
            response = api_client.persist_message_turn(
                self.session_id,
                turn_id,
                "Hello",
                "Hi there.",
            )

        self.assertEqual(response, {"saved": True})


if __name__ == "__main__":
    unittest.main()
