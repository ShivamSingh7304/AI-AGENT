import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "ai_agent.db"
load_dotenv(PROJECT_ROOT / ".env")


def get_database_url() -> URL:
    """Use local SQLite by default; opt in to PostgreSQL with a backend setting."""
    backend = os.getenv("AI_AGENT_DATABASE_BACKEND", "sqlite").strip().casefold()
    if backend == "sqlite":
        raw_url = os.getenv("DATABASE_URL", "").strip()
        if raw_url.startswith("sqlite:"):
            return make_url(raw_url)

        DEFAULT_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        return URL.create(
            "sqlite",
            database=str(DEFAULT_DATABASE_PATH),
        )
    if backend not in {"postgres", "postgresql"}:
        raise ValueError(
            "AI_AGENT_DATABASE_BACKEND must be 'sqlite' or 'postgresql'."
        )

    raw_url = os.getenv("DATABASE_URL", "").strip()
    if not raw_url:
        logger.error("DATABASE_URL is not configured for PostgreSQL")
        raise RuntimeError(
            "DATABASE_URL is required when AI_AGENT_DATABASE_BACKEND is "
            "'postgresql'."
        )
    try:
        url = make_url(raw_url)
    except Exception:
        logger.exception("DATABASE_URL could not be parsed")
        raise

    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    elif url.drivername != "postgresql+psycopg":
        logger.error(
            "Unsupported database URL driver configured: %s",
            url.drivername,
        )
        raise ValueError(
            "DATABASE_URL must use SQLite or PostgreSQL with the psycopg driver."
        )

    query = dict(url.query)
    query.setdefault("sslmode", "require")
    return url.set(query=query)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = get_database_url()
    if url.get_backend_name() == "sqlite":
        database = url.database
        if database not in (None, "", ":memory:"):
            Path(database).expanduser().resolve().parent.mkdir(
                parents=True,
                exist_ok=True,
            )
        logger.info("Creating SQLite engine for database %s", database)
        connect_args = {"check_same_thread": False, "timeout": 30}
    else:
        logger.info(
            "Creating PostgreSQL engine for database %s on host %s",
            url.database,
            url.host,
        )
        connect_args = {"connect_timeout": 10}

    try:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    except Exception:
        logger.exception("Could not create database engine")
        raise

    if url.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def configure_sqlite_connection(connection, _) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    logger.info("%s engine created", url.get_backend_name().capitalize())
    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    logger.debug("Created database session factory")
    return factory
