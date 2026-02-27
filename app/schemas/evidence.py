"""Evidence store DTOs (Issue #276). Read/return schemas for Evidence Store and Repository."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvidenceBundleRecord(BaseModel):
    """Return type for store_evidence_bundle: one persisted evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(..., description="Evidence bundle primary key")
    created_at: datetime = Field(..., description="Insert timestamp (append-only)")
    scout_version: str = Field(..., min_length=1, max_length=128)
    core_taxonomy_version: str = Field(..., min_length=1, max_length=64)
    core_derivers_version: str = Field(..., min_length=1, max_length=64)
