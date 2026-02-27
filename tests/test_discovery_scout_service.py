"""Tests for Discovery Scout Service — Evidence-Only; no company/event writes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from app.models.signal_event import SignalEvent
from app.services.scout.discovery_scout_service import run as run_scout


# ── Valid LLM JSON (citation-compliant) ────────────────────────────────────


def _valid_bundles_json() -> str:
    return """{
  "bundles": [
    {
      "candidate_company_name": "Acme Inc",
      "company_website": "https://acme.example.com",
      "why_now_hypothesis": "Recently raised Series A; hiring CTO.",
      "evidence": [
        {
          "url": "https://acme.example.com/news",
          "quoted_snippet": "Series A announced.",
          "timestamp_seen": "2026-02-27T12:00:00Z",
          "source_type": "news",
          "confidence_score": 0.9
        }
      ],
      "missing_information": ["Exact funding amount"]
    }
  ]
}"""


def _valid_bundles_json_empty_hypothesis() -> str:
    return """{
  "bundles": [
    {
      "candidate_company_name": "Beta LLC",
      "company_website": "https://beta.example.com",
      "why_now_hypothesis": "",
      "evidence": [],
      "missing_information": []
    }
  ]
}"""


@patch("app.services.scout.discovery_scout_service.get_llm_provider")
def test_run_returns_run_id_and_bundles_count(
    mock_get_llm: MagicMock,
    db: Session,
) -> None:
    """run() returns run_id, bundles_count, status completed when LLM returns valid bundles."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = _valid_bundles_json()
    mock_llm.model = "gpt-4o"
    mock_get_llm.return_value = mock_llm

    result = run_scout(
        db,
        icp_definition="Seed-stage B2B SaaS",
        exclusion_rules=None,
        pack_id=None,
        page_fetch_limit=10,
    )

    assert result["status"] == "completed"
    assert result["bundles_count"] == 1
    assert result["error"] is None
    assert len(result["run_id"]) > 0


@patch("app.services.scout.discovery_scout_service.get_llm_provider")
def test_run_persists_scout_run_and_bundles_not_companies_or_events(
    mock_get_llm: MagicMock,
    db: Session,
) -> None:
    """run() persists to scout_runs and scout_evidence_bundles only; no companies/signal_events."""
    companies_before = db.query(Company).count()
    events_before = db.query(SignalEvent).count()

    mock_llm = MagicMock()
    mock_llm.complete.return_value = _valid_bundles_json()
    mock_llm.model = "gpt-4o"
    mock_get_llm.return_value = mock_llm

    result = run_scout(
        db,
        icp_definition="Fintech startup",
        exclusion_rules=None,
        pack_id=None,
        page_fetch_limit=10,
    )

    assert result["status"] == "completed"
    assert result["bundles_count"] == 1

    # Scout tables updated
    runs = db.query(ScoutRun).filter(ScoutRun.run_id.isnot(None)).all()
    assert len(runs) >= 1
    bundles = db.query(ScoutEvidenceBundle).all()
    assert len(bundles) >= 1

    # Domain tables unchanged
    assert db.query(Company).count() == companies_before
    assert db.query(SignalEvent).count() == events_before


@patch("app.services.scout.discovery_scout_service.get_llm_provider")
def test_run_rejects_bundle_with_non_empty_hypothesis_and_empty_evidence(
    mock_get_llm: MagicMock,
    db: Session,
) -> None:
    """LLM output with why_now set but empty evidence is rejected (citation requirement)."""
    invalid_json = """{
  "bundles": [
    {
      "candidate_company_name": "Acme",
      "company_website": "https://acme.example.com",
      "why_now_hypothesis": "They are scaling.",
      "evidence": [],
      "missing_information": []
    }
  ]
}"""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = invalid_json
    mock_llm.model = "gpt-4o"
    mock_get_llm.return_value = mock_llm

    result = run_scout(
        db,
        icp_definition="B2B SaaS",
        exclusion_rules=None,
        pack_id=None,
        page_fetch_limit=10,
    )

    # That bundle fails validation so we get 0 accepted bundles (status still completed with 0)
    assert result["bundles_count"] == 0
    assert result["status"] == "completed"


@patch("app.services.scout.discovery_scout_service.get_llm_provider")
def test_run_accepts_bundle_with_evidence_and_hypothesis(
    mock_get_llm: MagicMock,
    db: Session,
) -> None:
    """Bundle with both evidence and why_now_hypothesis is accepted."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = _valid_bundles_json()
    mock_llm.model = "gpt-4o"
    mock_get_llm.return_value = mock_llm

    result = run_scout(
        db,
        icp_definition="Seed-stage",
        exclusion_rules="Exclude regulated",
        pack_id=None,
        page_fetch_limit=5,
    )

    assert result["status"] == "completed"
    assert result["bundles_count"] == 1
    run_row = db.query(ScoutRun).order_by(ScoutRun.id.desc()).first()
    assert run_row is not None
    assert run_row.status == "completed"
    bundle_row = db.query(ScoutEvidenceBundle).filter(
        ScoutEvidenceBundle.scout_run_id == run_row.id
    ).first()
    assert bundle_row is not None
    assert "Acme" in bundle_row.candidate_company_name
    assert bundle_row.evidence and len(bundle_row.evidence) >= 1


@patch("app.services.scout.discovery_scout_service.get_llm_provider")
def test_run_accepts_empty_hypothesis_empty_evidence_bundle(
    mock_get_llm: MagicMock,
    db: Session,
) -> None:
    """run() accepts bundle with empty why_now and empty evidence (no citation required)."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = _valid_bundles_json_empty_hypothesis()
    mock_llm.model = "gpt-4o"
    mock_get_llm.return_value = mock_llm

    result = run_scout(
        db,
        icp_definition="Any startup",
        exclusion_rules=None,
        pack_id=None,
        page_fetch_limit=10,
    )

    assert result["status"] == "completed"
    assert result["bundles_count"] == 1


@patch("app.services.scout.discovery_scout_service.get_llm_provider")
def test_run_invalid_json_returns_failed(
    mock_get_llm: MagicMock,
    db: Session,
) -> None:
    """run() returns status failed when LLM output is not valid JSON."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "not json at all"
    mock_llm.model = "gpt-4o"
    mock_get_llm.return_value = mock_llm

    result = run_scout(
        db,
        icp_definition="B2B",
        exclusion_rules=None,
        pack_id=None,
        page_fetch_limit=10,
    )

    assert result["status"] == "failed"
    assert result["bundles_count"] == 0
    assert result["error"] is not None
