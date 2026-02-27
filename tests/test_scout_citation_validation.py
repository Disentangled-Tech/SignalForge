"""Citation validation: evidence required when why_now_hypothesis is non-empty (Step 7)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.schemas.scout import EvidenceBundle, EvidenceItem


def test_bundle_with_empty_evidence_and_non_empty_why_now_rejected() -> None:
    """Bundle with non-empty why_now_hypothesis and empty evidence is rejected."""
    with pytest.raises(ValueError, match="evidence must be non-empty when why_now_hypothesis"):
        EvidenceBundle(
            candidate_company_name="Acme",
            company_website="https://acme.example.com",
            why_now_hypothesis="They are scaling and need a CTO.",
            evidence=[],
            missing_information=[],
        )


def test_bundle_with_evidence_and_why_now_accepted() -> None:
    """Bundle with both evidence and why_now_hypothesis is accepted."""
    bundle = EvidenceBundle(
        candidate_company_name="Acme",
        company_website="https://acme.example.com",
        why_now_hypothesis="They are scaling.",
        evidence=[
            EvidenceItem(
                url="https://acme.example.com/jobs",
                quoted_snippet="We are hiring a CTO.",
                timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
                source_type="careers",
                confidence_score=0.85,
            ),
        ],
        missing_information=[],
    )
    assert len(bundle.evidence) == 1
    assert bundle.why_now_hypothesis == "They are scaling."
