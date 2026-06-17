"""FastAPI application entrypoint.

Phase 0: minimal app proving the server boots — logging is configured at
startup and a `/health` route reports liveness. Routers for the real features
are mounted in later phases.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import news, style, trends
from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hook. Scheduler registration (Phase 11) plugs in here."""

    setup_logging()
    settings = get_settings()
    logger.info("Starting %s (env=%s)", settings.app_name, settings.environment)
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Application factory — keeps construction testable and explicit."""

    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Liveness probe. Extended with db/scheduler/ollama checks in Phase 11."""
        return {"status": "ok"}

    app.include_router(news.router)
    app.include_router(trends.router)
    app.include_router(style.router)
    return app


app = create_app()
