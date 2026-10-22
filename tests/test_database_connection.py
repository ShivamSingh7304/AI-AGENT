import unittest
from unittest.mock import patch

from ai_agent.agent.database.connection import get_database_url


class DatabaseConnectionTests(unittest.TestCase):
    def test_normalizes_neon_postgres_url_and_requires_ssl(self) -> None:
        with patch.dict(
            "os.environ",
            {
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
