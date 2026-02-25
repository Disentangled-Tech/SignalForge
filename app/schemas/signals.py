"""Canonical Company Signal schemas (Phase 2, Plan Step 1; Phase 4, Plan Step 4).

Defines CompanySignalEventRead, CompanySignalScoreRead for providers/services.
Event types are pack-defined (taxonomy.yaml); use str with pack validation at runtime.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.models.signal_event import SignalEvent


class CompanySignalEventRead(BaseModel):
    """Canonical event schema for providers/services.

    Maps from SignalEvent ORM. event_type is pack-defined (taxonomy signal_ids);
    validated against pack at runtime, not hardcoded enum.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int | None
    source: str
    source_event_id: str | None
    event_type: str = Field(..., description="Pack-defined; e.g. funding_raised, launch_major")
    event_time: datetime
    ingested_at: datetime
    title: str | None = None
    summary: str | None = None
    url: str | None = None
    confidence: float | None = None
    pack_id: UUID | None = None


class CompanySignalScoreRead(BaseModel):
    """Canonical score schema for composite + dimensions.

    Aligns with ReadinessSnapshot + EngagementSnapshot.
    """

    model_config = ConfigDict(from_attributes=True)

    company_id: int
    as_of: date
    composite: int
    momentum: int
    complexity: int
    pressure: int
    leadership_gap: int
    explain: dict | None = None
    pack_id: UUID | None = None
    computed_at: datetime

    # Optional EngagementSnapshot fields
    esl_score: float | None = None
    esl_decision: str | None = None
    sensitivity_level: str | None = None


def to_company_signal_event_read(event: SignalEvent) -> CompanySignalEventRead:
    """Convert SignalEvent ORM to CompanySignalEventRead schema.

    Used at ingestion boundary when canonical schema is needed (Phase 4, Plan Step 4).
    """
    return CompanySignalEventRead.model_validate(event)
