import unittest
from unittest.mock import patch

from ai_agent.agent.database.connection import (
    DEFAULT_DATABASE_PATH,
    get_database_url,
)


class DatabaseConnectionTests(unittest.TestCase):
    def test_uses_local_sqlite_when_database_url_is_empty(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AI_AGENT_DATABASE_BACKEND": "sqlite",
                "DATABASE_URL": "",
            },
            clear=False,
        ):
            url = get_database_url()

        self.assertEqual(url.drivername, "sqlite")
        self.assertEqual(url.database, str(DEFAULT_DATABASE_PATH))

    def test_sqlite_backend_ignores_configured_postgres_url(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AI_AGENT_DATABASE_BACKEND": "sqlite",
                "DATABASE_URL": "postgresql://user:secret@db.example/app",
            },
            clear=False,
        ):
            url = get_database_url()

        self.assertEqual(url.drivername, "sqlite")
        self.assertEqual(url.database, str(DEFAULT_DATABASE_PATH))

    def test_preserves_explicit_sqlite_database_url(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AI_AGENT_DATABASE_BACKEND": "sqlite",
                "DATABASE_URL": "sqlite:///./data/test.db",
            },
            clear=False,
        ):
            url = get_database_url()

        self.assertEqual(url.drivername, "sqlite")
        self.assertEqual(url.database, "./data/test.db")

    def test_normalizes_neon_postgres_url_and_requires_ssl(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AI_AGENT_DATABASE_BACKEND": "postgresql",
                "DATABASE_URL": (
                    "postgresql://agent:secret@ep-example.neon.tech/agentdb"
                )
            },
            clear=False,
        ):
            url = get_database_url()

        self.assertEqual(url.drivername, "postgresql+psycopg")
        self.assertEqual(url.host, "ep-example.neon.tech")
        self.assertEqual(url.query["sslmode"], "require")

    def test_preserves_stronger_ssl_mode(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AI_AGENT_DATABASE_BACKEND": "postgresql",
                "DATABASE_URL": (
                    "postgresql://agent:secret@ep-example.neon.tech/"
                    "agentdb?sslmode=verify-full"
                )
            },
            clear=False,
        ):
            url = get_database_url()

        self.assertEqual(url.query["sslmode"], "verify-full")


if __name__ == "__main__":
    unittest.main()
