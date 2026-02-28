"""Evidence store DTOs (Issue #276). Read/return schemas for Evidence Store and Repository."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scout import EvidenceBundle, ScoutRunMetadata


class StoreEvidenceRequest(BaseModel):
    """Request body for POST /internal/evidence/store (ScoutRunResult + run_context)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., min_length=1, max_length=64)
    bundles: list[EvidenceBundle] = Field(default_factory=list)
    metadata: ScoutRunMetadata
    run_context: dict[str, Any] | None = Field(None)
    raw_model_output: dict[str, Any] | None = Field(None)


class EvidenceBundleRecord(BaseModel):
    """Return type for store_evidence_bundle: one persisted evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(..., description="Evidence bundle primary key")
    created_at: datetime = Field(..., description="Insert timestamp (append-only)")
    scout_version: str = Field(..., min_length=1, max_length=128)
    core_taxonomy_version: str = Field(..., min_length=1, max_length=64)
    core_derivers_version: str = Field(..., min_length=1, max_length=64)


class EvidenceSourceRead(BaseModel):
    """Read DTO for one evidence source (repository)."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(..., description="Evidence source primary key")
    url: str = Field(..., max_length=2048)
    retrieved_at: datetime | None = Field(None)
    snippet: str | None = Field(None)
    content_hash: str = Field(..., min_length=1, max_length=64)
    source_type: str | None = Field(None, max_length=64)


class EvidenceClaimRead(BaseModel):
    """Read DTO for one evidence claim (repository)."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., description="Evidence claim primary key")
    bundle_id: uuid.UUID = Field(..., description="Parent evidence bundle id")
    entity_type: str = Field(..., max_length=64)
    field: str = Field(..., max_length=255)
    value: str | None = Field(None)
    source_ids: list[str] | None = Field(None, description="References to evidence_sources.id")
    confidence: float | None = Field(None)


class EvidenceBundleRead(BaseModel):
    """Read DTO for one evidence bundle (repository). Full row; no pack logic."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(..., description="Evidence bundle primary key")
    created_at: datetime = Field(..., description="Insert timestamp (append-only)")
    scout_version: str = Field(..., min_length=1, max_length=128)
    core_taxonomy_version: str = Field(..., min_length=1, max_length=64)
    core_derivers_version: str = Field(..., min_length=1, max_length=64)
    pack_id: uuid.UUID | None = Field(None)
    run_context: dict | None = Field(None)
    raw_model_output: dict | None = Field(None)
    structured_payload: dict | None = Field(None)
