"""Authentication API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import AUTH_COOKIE, get_db, require_auth
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserRead
from app.services.auth import authenticate_user, create_access_token

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate user and return JWT token.

    Also sets an httponly cookie for browser sessions.
    """
    user = authenticate_user(db, body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(data={"sub": user.username})

    # Set httponly cookie for browser sessions
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24,  # 24 hours
        path="/",
    )

    return TokenResponse(access_token=token)


@router.post("/logout")
def logout(response: Response) -> dict:
    """Clear the authentication cookie."""
    response.delete_cookie(key=AUTH_COOKIE, path="/")
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(require_auth)) -> UserRead:
    """Return the currently authenticated user's information."""
    return UserRead.model_validate(current_user)

