"""API routes."""

from app.api.companies import router as companies_router

__all__ = ["companies_router"]

from app.api.auth import router as auth_router

__all__ = ["auth_router"]
