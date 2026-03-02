"""Verification Gate schemas (Issue #278, M1).

VerificationResult and reason code constants for pack-agnostic fact and event
validation before evidence enters the store. No DB; used by verification service.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class VerificationReasonCode(StrEnum):
    """Structured reason codes for verification failures (quarantine payload)."""

    # Event rules (M2)
    EVENT_TYPE_UNKNOWN = "EVENT_TYPE_UNKNOWN"
    EVENT_MISSING_TIMESTAMPED_CITATION = "EVENT_MISSING_TIMESTAMPED_CITATION"
    EVENT_MISSING_REQUIRED_FIELDS = "EVENT_MISSING_REQUIRED_FIELDS"

    # Fact rules (M5)
    FACT_DOMAIN_MISMATCH = "FACT_DOMAIN_MISMATCH"
    FACT_FOUNDER_MISSING_PRIMARY_SOURCE = "FACT_FOUNDER_MISSING_PRIMARY_SOURCE"
    FACT_HIRING_MISSING_JOBS_OR_ATS = "FACT_HIRING_MISSING_JOBS_OR_ATS"


class VerificationResult(BaseModel):
    """Per-bundle verification outcome: pass/fail and optional reason codes."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(..., description="True if bundle passed all verification rules.")
    reason_codes: list[str] = Field(
        default_factory=list,
        description="Structured reason codes when passed=False; empty when passed=True.",
    )
