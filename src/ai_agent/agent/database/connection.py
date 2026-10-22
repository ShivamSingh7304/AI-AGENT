import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")


def get_database_url() -> URL:
    """Read and normalize the Neon PostgreSQL connection URL."""
    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        logger.error("DATABASE_URL is not configured")
        raise RuntimeError(
            "DATABASE_URL is not set. Add your Neon PostgreSQL connection "
            "string to the project's .env file."
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
            "Unsupported database driver configured: %s",
            url.drivername,
        )
        raise ValueError(
            "DATABASE_URL must use PostgreSQL with the psycopg driver."
        )

    query = dict(url.query)
    query.setdefault("sslmode", "require")
    return url.set(query=query)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = get_database_url()
    logger.info(
        "Creating PostgreSQL engine for database %s on host %s",
        url.database,
        url.host,
    )
    try:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )
    except Exception:
        logger.exception("Could not create PostgreSQL engine")
        raise
    logger.info("PostgreSQL engine created")
    return engine


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    logger.debug("Created database session factory")
    return factory
