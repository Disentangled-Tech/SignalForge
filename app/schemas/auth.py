"""Authentication schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Schema for login credentials."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Schema for JWT token response."""

    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    """Schema for reading user info (response)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str

