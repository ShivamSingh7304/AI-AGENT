import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_agent.api.routes.documents import router as documents_router
from ai_agent.api.routes.messages import router as messages_router
from ai_agent.api.routes.sessions import router as sessions_router
from ai_agent.core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    from ai_agent.agent.agent import app_agent

    logger.info(
        "Shared AI agent initialized and ready: %s",
        type(app_agent).__name__,
    )
    yield


app = FastAPI(
    title="AI Agent API",
    description="Session, chat, and PDF endpoints for the AI Agent.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(sessions_router)
app.include_router(messages_router)
app.include_router(documents_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    logger.debug("API health check")
    return {"status": "ok"}
