import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from ai_agent.agent.database.models import Base
from ai_agent.agent.database.repository import (
    add_document_to_session,
    attach_document_to_message,
    create_session,
    get_session_messages,
    list_session_documents,
    list_sessions,
    save_message,
    save_message_turn,
    set_active_document,
)


class DatabaseRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        self.factory_patch = patch(
            "ai_agent.agent.database.repository.get_session_factory",
            return_value=self.session_factory,
        )
        self.factory_patch.start()

    def tearDown(self) -> None:
        self.factory_patch.stop()
        self.engine.dispose()

    def test_persists_messages_documents_and_image_references(self) -> None:
        session_id = create_session()
        user_message_id = save_message(session_id, "user", "Summarize this PDF")
        document_id = str(uuid4())
        add_document_to_session(
            session_id,
            document_id,
            "report.pdf",
            "data/uploads/report.pdf",
            "vector_store/pdf_indexes/report",
        )
        attach_document_to_message(user_message_id, document_id)
        assistant_message_id = save_message(
            session_id,
            "assistant",
            "Here is the generated image.",
            image_prompt="A blue landscape",
            image_path="generated_images/landscape.png",
        )

        messages = get_session_messages(session_id)
        self.assertEqual(
            [message["role"] for message in messages],
            ["user", "assistant"],
        )
        self.assertEqual(
            messages[0]["documents"],
            [{"id": document_id, "filename": "report.pdf"}],
        )
        self.assertEqual(messages[1]["id"], assistant_message_id)
        self.assertEqual(
            messages[1]["image_path"],
            "generated_images/landscape.png",
        )
        self.assertEqual(list_sessions()[0]["title"], "Summarize this PDF")
        self.assertTrue(list_session_documents(session_id)[0]["is_active"])

    def test_active_pdf_can_be_changed_per_session(self) -> None:
        session_id = create_session()
        first_document_id = str(uuid4())
        second_document_id = str(uuid4())
        for document_id, filename in (
            (first_document_id, "first.pdf"),
            (second_document_id, "second.pdf"),
        ):
            add_document_to_session(
                session_id,
                document_id,
                filename,
                f"data/uploads/{filename}",
                f"vector_store/pdf_indexes/{document_id}",
            )

        set_active_document(session_id, first_document_id)
        documents = {
            document["id"]: document
            for document in list_session_documents(session_id)
        }
        self.assertTrue(documents[first_document_id]["is_active"])
        self.assertFalse(documents[second_document_id]["is_active"])

    def test_saves_complete_turn_atomically_and_is_idempotent(self) -> None:
        session_id = create_session()
        document_id = str(uuid4())
        add_document_to_session(
            session_id,
            document_id,
            "report.pdf",
            "data/uploads/report.pdf",
            "vector_store/pdf_indexes/report",
        )
        turn_id = str(uuid4())

        message_ids = save_message_turn(
            session_id,
            "Summarize the report",
            "It describes the results.",
            document_id=document_id,
            image_prompt="A report illustration",
            image_path="generated_images/report.png",
            turn_id=turn_id,
        )
        retried_ids = save_message_turn(
            session_id,
            "Summarize the report",
            "It describes the results.",
            document_id=document_id,
            image_prompt="A report illustration",
            image_path="generated_images/report.png",
            turn_id=turn_id,
        )

        messages = get_session_messages(session_id)
        self.assertEqual(message_ids, retried_ids)
        self.assertEqual(len(messages), 2)
        self.assertEqual(
            [message["role"] for message in messages],
            ["user", "assistant"],
        )
        self.assertEqual(
            messages[0]["documents"],
            [{"id": document_id, "filename": "report.pdf"}],
        )
        self.assertEqual(
            messages[1]["image_path"],
            "generated_images/report.png",
        )


if __name__ == "__main__":
    unittest.main()
