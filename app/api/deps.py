"""Shared FastAPI dependencies for API routes."""

from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db  # re-export
from app.models.user import User
from app.services.auth import get_user_from_token

__all__ = [
    "get_db",
    "get_current_user",
    "require_auth",
    "require_ui_auth",
    "validate_uuid_param_or_422",
]


def validate_uuid_param_or_422(value: str | None, param_name: str) -> None:
    """Validate value is a valid UUID; raise HTTPException 422 if not.

    Use when workspace_id or pack_id is provided and must be a valid UUID.
    Empty/None values pass (caller handles omission).
    """
    if not value or not value.strip():
        return
    try:
        from uuid import UUID

        UUID(value.strip())
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {param_name}: must be a valid UUID",
        ) from None


# Cookie name for browser sessions
AUTH_COOKIE = "access_token"


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
    access_token: str | None = Cookie(None),
) -> User | None:
    """Return the authenticated user or None.

    Checks (in order):
    1. Authorization: Bearer <token> header
    2. access_token cookie
    """
    token: str | None = None

    # Check Authorization header
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :]

    # Fall back to cookie
    if token is None and access_token:
        token = access_token

    if token is None:
        return None

    return get_user_from_token(db, token)


def require_auth(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> User:
    """Dependency that requires authentication.

    For API requests (Accept: application/json or /api/ prefix): returns 401.
    For browser requests: returns 401 (UI will handle redirect).
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


def require_ui_auth(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> User:
    """Dependency that requires authentication for browser/UI routes.

    Redirects to /login instead of returning a 401 JSON response.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
    return user
