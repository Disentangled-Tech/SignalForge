"""Integration tests for Verification Gate (Issue #278, M2).

Tests the contract: verify_bundles → quarantine failures (with reason_codes) →
store only passing bundles. Failing bundle must appear in evidence_quarantine with
reason_codes in payload and must not appear in evidence_bundles.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.evidence.repository import list_bundles_by_run
from app.evidence.store import store_evidence_bundle
from app.models.evidence_bundle import EvidenceBundle as EvidenceBundleORM
from app.models.evidence_quarantine import EvidenceQuarantine
from app.schemas.scout import EvidenceBundle, EvidenceItem
from app.verification import verify_bundles


def _make_item(url: str, snippet: str, source_type: str = "web") -> EvidenceItem:
    return EvidenceItem(
        url=url,
        quoted_snippet=snippet,
        timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
        source_type=source_type,
        confidence_score=0.9,
    )


def _passing_bundle() -> EvidenceBundle:
    return EvidenceBundle(
        candidate_company_name="Pass Co",
        company_website="https://pass.example.com",
        why_now_hypothesis="Seed.",
        evidence=[_make_item("https://pass.example.com/news", "Seed round.")],
        missing_information=[],
    )


def _failing_bundle() -> EvidenceBundle:
    return EvidenceBundle(
        candidate_company_name="Fail Co",
        company_website="https://fail.example.com",
        why_now_hypothesis="Hiring.",
        evidence=[_make_item("https://fail.example.com/jobs", "CTO role.")],
        missing_information=[],
    )


@pytest.mark.integration
def test_verify_quarantine_failures_store_passing_bundle_not_stored(
    db: Session,
) -> None:
    """Flow: verify_bundles → quarantine failures with reason_codes → store only passing.

    Failing bundle (invalid event_type) is quarantined with reason_codes in payload
    and is not in evidence_bundles. Passing bundle is stored.
    """
    run_id = "verify-integration-run-1"
    passing_bundle = _passing_bundle()
    failing_bundle = _failing_bundle()
    passing_payload: dict = {
        "events": [{"event_type": "funding_raised", "confidence": 0.9, "source_refs": [0]}]
    }
    failing_payload: dict = {"events": [{"event_type": "not_in_taxonomy", "confidence": 0.9}]}

    results = verify_bundles(
        [passing_bundle, failing_bundle],
        structured_payloads=[passing_payload, failing_payload],
    )
    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is False
    assert "EVENT_TYPE_UNKNOWN" in results[1].reason_codes

    # Quarantine the failing bundle (contract M3 will do this; we use ORM directly)
    quarantine_payload = {
        "run_id": run_id,
        "bundle_index": 1,
        "bundle": failing_bundle.model_dump(mode="json"),
        "structured_payload": failing_payload,
        "reason_codes": results[1].reason_codes,
    }
    quarantine_row = EvidenceQuarantine(
        payload=quarantine_payload,
        reason="; ".join(results[1].reason_codes),
    )
    db.add(quarantine_row)
    db.flush()

    # Store only the passing bundle
    stored = store_evidence_bundle(
        db,
        run_id=run_id,
        scout_version="test",
        bundles=[passing_bundle],
        run_context={"run_id": run_id},
        raw_model_output=None,
        structured_payloads=[passing_payload],
    )
    assert len(stored) == 1

    # Assert: one quarantine row with reason_codes; failing bundle not in evidence_bundles
    quarantine_rows = db.query(EvidenceQuarantine).all()
    assert len(quarantine_rows) == 1
    assert quarantine_rows[0].payload.get("reason_codes") == results[1].reason_codes
    assert quarantine_rows[0].payload.get("bundle_index") == 1

    bundles_in_run = list_bundles_by_run(db, run_id)
    assert len(bundles_in_run) == 1
    # Stored bundle has our passing payload (structured_payload contains events)
    assert bundles_in_run[0].structured_payload == passing_payload

    # Failing bundle must not appear in evidence_bundles at all
    all_bundle_rows = (
        db.query(EvidenceBundleORM)
        .filter(EvidenceBundleORM.run_context["run_id"].astext == run_id)
        .all()
    )
    assert len(all_bundle_rows) == 1
