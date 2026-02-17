"""Settings and operator profile schemas."""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SettingsUpdate(BaseModel):
    """Schema for updating application settings (issue #29)."""

    briefing_time: Optional[time] = Field(
        None, description="Time of day to generate briefings (HH:MM)"
    )
    briefing_email: Optional[str] = Field(
        None,
        max_length=255,
        description="Email address for briefing delivery",
    )
    briefing_email_enabled: Optional[bool] = Field(
        None, description="Enable briefing email delivery"
    )
    briefing_frequency: Optional[str] = Field(
        None, description="daily or weekly"
    )
    briefing_day_of_week: Optional[int] = Field(
        None, ge=0, le=6, description="0=Monday .. 6=Sunday for weekly briefings"
    )
    scoring_weights: Optional[dict[str, float]] = Field(
        None, description="Custom scoring weights as key-value pairs"
    )


class SettingsRead(BaseModel):
    """Schema for reading application settings (response)."""

    model_config = ConfigDict(from_attributes=True)

    briefing_time: Optional[time] = None
    briefing_email: Optional[str] = None
    briefing_email_enabled: Optional[bool] = None
    briefing_frequency: Optional[str] = None
    briefing_day_of_week: Optional[int] = None
    scoring_weights: Optional[dict[str, float]] = None


class OperatorProfileUpdate(BaseModel):
    """Schema for updating the operator profile."""

    content: str = Field(
        ...,
        min_length=1,
        description="Operator profile content in markdown format",
    )


class OperatorProfileRead(BaseModel):
    """Schema for reading the operator profile (response)."""

    model_config = ConfigDict(from_attributes=True)

    content: Optional[str] = None
    updated_at: Optional[datetime] = None

