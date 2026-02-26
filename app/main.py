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
            if "signalforge_test" in get_settings().database_url:
                logger.warning(
                    "App is connected to signalforge_test. "
                    "Use a fresh shell or set DATABASE_URL to signalforge_dev for development."
                )
        except Exception as e:
            logger.critical("Database unreachable: %s", e)
            raise

        # Eagerly validate core YAML files at startup so a bad deployment (syntax error,
        # missing file, or schema violation) surfaces immediately rather than at the first
        # derive job (Issue #285, Milestone 3). Both FileNotFoundError and yaml.YAMLError
        # will propagate as CRITICAL failures, preventing the app from serving requests.
        try:
            from app.core_derivers.loader import load_core_derivers
            from app.core_taxonomy.loader import load_core_taxonomy

            load_core_taxonomy()
            load_core_derivers()
            logger.info("Core taxonomy and derivers validated")
        except Exception as e:
            logger.critical("Core YAML validation failed at startup: %s", e)
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
    from app.api.bias_views import router as bias_views_router
    from app.api.briefing import router as briefing_router
    from app.api.briefing_views import router as briefing_views_router
    from app.api.companies import router as companies_router
    from app.api.outreach import router as outreach_router
    from app.api.settings_views import router as settings_views_router
    from app.api.views import router as views_router
    from app.api.watchlist import router as watchlist_router

    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(briefing_router, prefix="/api/briefing", tags=["briefing"])
    app.include_router(companies_router, prefix="/api/companies", tags=["companies"])
    app.include_router(outreach_router, prefix="/api/outreach", tags=["outreach"])
    app.include_router(watchlist_router, prefix="/api/watchlist", tags=["watchlist"])

    # Mount HTML-serving view routes (no prefix — serves /, /login, /companies, etc.)
    app.include_router(views_router, tags=["views"])
    app.include_router(briefing_views_router, tags=["briefing-views"])
    app.include_router(bias_views_router, tags=["bias-views"])
    app.include_router(settings_views_router, tags=["settings-views"])

    # Internal job endpoints (cron/scripts — token-authenticated)
    from app.api.internal import router as internal_router

    app.include_router(internal_router, tags=["internal"])

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
