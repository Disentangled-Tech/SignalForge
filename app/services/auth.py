"""Authentication service — user management and JWT tokens."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User

# JWT configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def create_user(db: Session, username: str, password: str) -> User:
    """Create a new user with hashed password."""
    user = User(username=username)
    user.set_password(password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Validate credentials and return user, or None if invalid."""
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return None
    if not user.verify_password(password):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def get_user_from_token(db: Session, token: str) -> Optional[User]:
    """Extract user from a JWT token. Returns None if token invalid or user not found."""
    payload = decode_access_token(token)
    if payload is None:
        return None
    username: Optional[str] = payload.get("sub")
    if username is None:
        return None
    return db.query(User).filter(User.username == username).first()

