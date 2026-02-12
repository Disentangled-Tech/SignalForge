"""
SignalForge FastAPI application entry point.

Pipeline: companies → signals → analysis → scoring → briefing → outreach draft
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.config import get_settings
from app.db.session import check_db_connection, engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info("SignalForge starting")
    try:
        try:
            check_db_connection()
            logger.info("Database connection verified")
        except Exception as e:
            logger.critical("Database unreachable: %s", e)
            raise
        yield
    finally:
        logger.info("SignalForge shutting down")
        engine.dispose()
        logger.info("Database connection pool closed")


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

    # Mount API routes
    from app.api.auth import router as auth_router
    from app.api.companies import router as companies_router
    from app.api.views import router as views_router

    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(companies_router, prefix="/api/companies", tags=["companies"])
    # app.include_router(briefing.router, prefix="/api/briefing", tags=["briefing"])

    # Mount HTML-serving view routes (no prefix — serves /, /login, /companies, etc.)
    app.include_router(views_router, tags=["views"])

    @app.get("/health")
    def health() -> dict:
        """Health check endpoint. Confirms DB connectivity."""
        from sqlalchemy import text

        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {
                "status": "ok",
                "version": __version__,
                "database": "connected",
            }
        except Exception:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "version": __version__,
                    "database": "disconnected",
                },
            )

    return app


app = create_app()
