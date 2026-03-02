"""Watchlist Seeder request/result schemas (Issue #279, M2)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class SeedFromBundlesRequest(BaseModel):
    """Request to seed companies and core events from evidence bundle(s)."""

    model_config = ConfigDict(extra="forbid")

    bundle_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Evidence bundle UUIDs to seed from",
    )
    workspace_id: uuid.UUID | None = Field(
        None,
        description="When set, only bundles belonging to this workspace are loaded",
    )


class SeedFromBundlesResult(BaseModel):
    """Result of seed_from_bundles: counts and any errors."""

    model_config = ConfigDict(extra="forbid")

    companies_created: int = Field(0, description="Number of new companies created")
    companies_matched: int = Field(0, description="Number of companies resolved to existing")
    events_stored: int = Field(0, description="Number of signal events stored")
    events_skipped_duplicate: int = Field(
        0,
        description="Number of events skipped (duplicate source_event_id)",
    )
    errors: list[str] = Field(default_factory=list, description="Per-bundle or validation errors")
