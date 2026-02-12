"""
SignalForge FastAPI application entry point.

Pipeline: companies → signals → analysis → scoring → briefing → outreach draft
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app import __version__
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info("SignalForge starting")
    yield
    logger.info("SignalForge shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Mount API routes (to be added)
    # from app.api import auth, companies, briefing
    # app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    # app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
    # app.include_router(briefing.router, prefix="/api/briefing", tags=["briefing"])

    @app.get("/health")
    def health() -> dict:
        """Health check endpoint."""
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
