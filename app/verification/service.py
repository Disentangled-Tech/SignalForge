"""Verification Gate service (Issue #278, M1).

Orchestrates verification rules; pack-agnostic; no DB. Entry points: verify_bundle
and verify_bundles. Callers (Scout, internal store) use results to quarantine
failures and store only passing bundles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.verification.rules import run_all_rules
from app.verification.schemas import VerificationResult

if TYPE_CHECKING:
    from app.schemas.scout import EvidenceBundle


def verify_bundle(
    bundle: EvidenceBundle,
    structured_payload: dict | None = None,
) -> VerificationResult:
    """Run all verification rules on a single bundle.

    Args:
        bundle: Scout evidence bundle (candidate company + evidence).
        structured_payload: Optional extractor output (company, events, claims).

    Returns:
        VerificationResult with passed=True and empty reason_codes if all rules
        pass; otherwise passed=False and non-empty reason_codes.
    """
    reason_codes = run_all_rules(bundle, structured_payload)
    return VerificationResult(
        passed=len(reason_codes) == 0,
        reason_codes=reason_codes,
    )


def verify_bundles(
    bundles: list[EvidenceBundle],
    structured_payloads: list[dict | None] | None = None,
) -> list[VerificationResult]:
    """Run verification on each bundle; payloads aligned by index when provided.

    Args:
        bundles: List of Scout evidence bundles.
        structured_payloads: Optional list of extractor payloads; if provided,
            must match len(bundles); bundle i uses structured_payloads[i].

    Returns:
        One VerificationResult per bundle, in same order as bundles.
    """
    if structured_payloads is not None and len(structured_payloads) != len(bundles):
        raise ValueError(
            "structured_payloads length must match bundles when provided; "
            f"got {len(structured_payloads)} vs {len(bundles)}"
        )
    results: list[VerificationResult] = []
    for i, bundle in enumerate(bundles):
        payload = structured_payloads[i] if structured_payloads is not None else None
        results.append(verify_bundle(bundle, payload))
    return results
