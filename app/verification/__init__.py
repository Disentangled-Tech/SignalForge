"""Verification & Grounding Gate (Issue #278).

Pack-agnostic validation of entity facts and core event candidates before evidence
enters the store. No DB; orchestrated by verification service; callers quarantine
failures and store only passing bundles.
"""

from app.verification.schemas import VerificationReasonCode, VerificationResult
from app.verification.service import verify_bundle, verify_bundles

__all__ = [
    "VerificationReasonCode",
    "VerificationResult",
    "verify_bundle",
    "verify_bundles",
]
