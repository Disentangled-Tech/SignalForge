"""Settings and operator profile schemas."""

from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field


class SettingsUpdate(BaseModel):
    """Schema for updating application settings (issue #29)."""

    briefing_time: time | None = Field(
        None, description="Time of day to generate briefings (HH:MM)"
    )
    briefing_email: str | None = Field(
        None,
        max_length=255,
        description="Email address for briefing delivery",
    )
    briefing_email_enabled: bool | None = Field(None, description="Enable briefing email delivery")
    briefing_frequency: str | None = Field(None, description="daily or weekly")
    briefing_day_of_week: int | None = Field(
        None, ge=0, le=6, description="0=Monday .. 6=Sunday for weekly briefings"
    )
    scoring_weights: dict[str, float] | None = Field(
        None, description="Custom scoring weights as key-value pairs"
    )


class SettingsRead(BaseModel):
    """Schema for reading application settings (response)."""

    model_config = ConfigDict(from_attributes=True)

    briefing_time: time | None = None
    briefing_email: str | None = None
    briefing_email_enabled: bool | None = None
    briefing_frequency: str | None = None
    briefing_day_of_week: int | None = None
    scoring_weights: dict[str, float] | None = None


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

    content: str | None = None
    updated_at: datetime | None = None
