"""Unit tests for Discovery Scout Service (Evidence-Only, plan Step 5 / M4)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.evidence.repository import list_bundles_by_run
from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from app.services.scout.discovery_scout_service import run


def _mock_db_session() -> MagicMock:
    """Return a mock Session that accepts add/flush/commit without requiring real tables."""
    session = MagicMock(spec=Session)
    session.add = MagicMock()
    session.flush = MagicMock()
    session.commit = MagicMock()
    return session


def _valid_llm_bundles_json() -> str:
    """Return LLM response JSON that validates as EvidenceBundle list."""
    return json.dumps(
        {
            "bundles": [
                {
                    "candidate_company_name": "Acme Inc",
                    "company_website": "https://acme.com",
                    "why_now_hypothesis": "Recently hiring engineers.",
                    "evidence": [
                        {
                            "url": "https://acme.com/careers",
                            "quoted_snippet": "We are hiring senior engineers.",
                            "timestamp_seen": "2025-02-27T12:00:00Z",
                            "source_type": "careers",
                            "confidence_score": 0.9,
                        }
                    ],
                    "missing_information": [],
                }
            ]
        }
    )


async def _run_with_mocks(
    db: Session,
    *,
    seed_urls: list[str] | None = None,
    llm_response: str | None = None,
    fetch_returns: str | None = "<p>Some content</p>",
    denylist: list[str] | None = None,
    allowlist: list[str] | None = None,
    page_fetch_limit: int = 10,
    run_extractor: bool | None = None,
):
    """Run scout with mocked fetch and LLM."""
    if llm_response is None:
        llm_response = _valid_llm_bundles_json()
    if seed_urls is None:
        seed_urls = ["https://example.com/page1"]

    async def fake_fetch(url: str) -> str | None:
        return fetch_returns

    mock_llm = MagicMock()
    mock_llm.complete = MagicMock(return_value=llm_response)
    mock_llm.model = "gpt-4o"

    with patch(
        "app.services.scout.discovery_scout_service.get_llm_provider", return_value=mock_llm
    ):
        return await run(
            db,
            "B2B SaaS with technical hiring needs",
            seed_urls=seed_urls,
            allowlist=allowlist,
            denylist=denylist or [],
            fetch_page=fake_fetch,
            llm_provider=mock_llm,
            page_fetch_limit=page_fetch_limit,
            run_extractor=run_extractor,
        )


@pytest.mark.asyncio
async def test_run_returns_valid_bundles_and_persists(db: Session) -> None:
    """run() returns validated EvidenceBundles and persists ScoutRun + ScoutEvidenceBundle rows."""
    run_id, bundles, metadata = await _run_with_mocks(db, seed_urls=["https://allowed.com/a"])
    assert isinstance(run_id, str)
    assert len(run_id) > 0
    assert len(bundles) == 1
    assert bundles[0].candidate_company_name == "Acme Inc"
    assert bundles[0].company_website == "https://acme.com"
    assert len(bundles[0].evidence) == 1
    assert metadata.page_fetch_count == 1

    row = db.query(ScoutRun).filter(ScoutRun.run_id == uuid.UUID(run_id)).first()
    assert row is not None
    assert row.status == "completed"
    assert row.page_fetch_count == 1
    bundle_rows = (
        db.query(ScoutEvidenceBundle).filter(ScoutEvidenceBundle.scout_run_id == row.run_id).all()
    )
    assert len(bundle_rows) == 1
    assert bundle_rows[0].candidate_company_name == "Acme Inc"


@pytest.mark.asyncio
async def test_run_does_not_call_company_resolver_or_event_storage() -> None:
    """DiscoveryScoutService.run() must not call resolve_or_create_company or store_signal_event."""
    mock_db = _mock_db_session()
    with patch(
        "app.ingestion.event_storage.store_signal_event",
        MagicMock(),
    ) as mock_store:
        with patch(
            "app.services.company_resolver.resolve_or_create_company",
            MagicMock(),
        ) as mock_resolve:
            with patch(
                "app.services.scout.discovery_scout_service.store_evidence_bundle",
                return_value=[],
            ):
                await _run_with_mocks(mock_db, seed_urls=["https://example.com"])
            mock_store.assert_not_called()
            mock_resolve.assert_not_called()


@pytest.mark.asyncio
async def test_denylist_blocks_urls() -> None:
    """URLs on denylist are not fetched; page_fetch_count should be 0 for only-denylisted seeds."""
    mock_db = _mock_db_session()
    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        return_value=[],
    ):
        run_id, bundles, metadata = await _run_with_mocks(
            mock_db,
            seed_urls=["https://blocked.evil/path"],
            allowlist=[],  # empty allowlist = all allowed except denylist
            denylist=["blocked.evil"],
        )
    assert metadata.page_fetch_count == 0


@pytest.mark.asyncio
async def test_page_fetch_limit_enforced() -> None:
    """Only page_fetch_limit URLs are fetched."""
    mock_db = _mock_db_session()
    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        return_value=[],
    ):
        run_id, _, metadata = await _run_with_mocks(
            mock_db,
            seed_urls=[
                "https://a.com/1",
                "https://a.com/2",
                "https://a.com/3",
                "https://a.com/4",
                "https://a.com/5",
            ],
            allowlist=[],
            denylist=[],
            page_fetch_limit=2,
        )
    assert metadata.page_fetch_count == 2


@pytest.mark.asyncio
async def test_bundle_with_empty_evidence_and_non_empty_why_now_rejected() -> None:
    """LLM output with why_now_hypothesis but empty evidence fails validation (citation requirement)."""
    mock_db = _mock_db_session()
    bad_json = json.dumps(
        {
            "bundles": [
                {
                    "candidate_company_name": "NoCite Inc",
                    "company_website": "https://nocite.com",
                    "why_now_hypothesis": "They are scaling.",
                    "evidence": [],
                    "missing_information": [],
                }
            ]
        }
    )
    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        return_value=[],
    ):
        run_id, bundles, metadata = await _run_with_mocks(mock_db, llm_response=bad_json)
    assert len(bundles) == 0


@pytest.mark.asyncio
async def test_bundle_with_evidence_and_why_now_accepted() -> None:
    """Valid bundle with evidence and why_now_hypothesis is accepted."""
    mock_db = _mock_db_session()
    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        return_value=[],
    ):
        run_id, bundles, _ = await _run_with_mocks(mock_db, llm_response=_valid_llm_bundles_json())
    assert len(bundles) == 1
    assert bundles[0].why_now_hypothesis
    assert len(bundles[0].evidence) >= 1


@pytest.mark.asyncio
async def test_empty_seed_urls_yields_zero_fetches() -> None:
    """When seed_urls is None or empty, no pages are fetched."""
    mock_db = _mock_db_session()
    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        return_value=[],
    ):
        run_id, bundles, metadata = await _run_with_mocks(mock_db, seed_urls=[])
    assert metadata.page_fetch_count == 0


@pytest.mark.asyncio
async def test_output_schema_has_no_pack_specific_fields() -> None:
    """Validated EvidenceBundle has no signal_id, event_type, or pack-specific fields."""
    mock_db = _mock_db_session()
    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        return_value=[],
    ):
        run_id, bundles, _ = await _run_with_mocks(mock_db)
    assert len(bundles) == 1
    b = bundles[0]
    assert hasattr(b, "candidate_company_name")
    assert hasattr(b, "company_website")
    assert hasattr(b, "why_now_hypothesis")
    assert hasattr(b, "evidence")
    assert hasattr(b, "missing_information")
    assert not hasattr(b, "signal_id")
    assert not hasattr(b, "event_type")
    assert not hasattr(b, "pack_id")


# --- M4: Optional Scout integration (Extractor) ---


@pytest.mark.asyncio
async def test_scout_run_with_extractor_disabled_calls_store_with_structured_payloads_none() -> None:
    """With run_extractor=False (explicit), store_evidence_bundle receives structured_payloads=None.

    Passing run_extractor=False makes the test independent of SCOUT_RUN_EXTRACTOR env.
    """
    mock_db = _mock_db_session()
    store_kwargs: list[dict] = []

    def capture_store(*args: object, **kwargs: object) -> list:
        store_kwargs.append(dict(kwargs))
        return []

    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        side_effect=capture_store,
    ):
        await _run_with_mocks(
            mock_db,
            seed_urls=["https://example.com/one"],
            run_extractor=False,
        )
    assert len(store_kwargs) == 1
    assert store_kwargs[0].get("structured_payloads") is None


@pytest.mark.asyncio
async def test_scout_run_with_extractor_enabled_calls_store_with_structured_payloads() -> None:
    """With run_extractor=True, store_evidence_bundle receives structured_payloads list (ExtractionResult shape)."""
    mock_db = _mock_db_session()
    store_kwargs: list[dict] = []

    def capture_store(*args: object, **kwargs: object) -> list:
        store_kwargs.append(dict(kwargs))
        return []

    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        side_effect=capture_store,
    ):
        run_id, bundles, _ = await _run_with_mocks(
            mock_db,
            seed_urls=["https://example.com"],
            run_extractor=True,
        )
    assert len(bundles) == 1, "expected one validated bundle"
    assert len(store_kwargs) == 1, "store_evidence_bundle should be called once"
    payloads = store_kwargs[0].get("structured_payloads")
    assert payloads is not None
    assert len(payloads) == 1
    one = payloads[0]
    assert "company" in one
    assert "core_event_candidates" in one
    assert "version" in one
    assert one["company"] is not None
    assert isinstance(one["core_event_candidates"], list)
    assert one["company"].get("name") == "Acme Inc"
    assert one["company"].get("website_url") == "https://acme.com"


@pytest.mark.asyncio
async def test_scout_run_with_extractor_enabled_empty_bundles_calls_store_with_none_payloads() -> None:
    """When run_extractor=True but no bundles validated, store_evidence_bundle receives structured_payloads=None."""
    mock_db = _mock_db_session()
    bad_json = json.dumps({"bundles": []})
    store_kwargs: list[dict] = []

    def capture_store(*args: object, **kwargs: object) -> list:
        store_kwargs.append(dict(kwargs))
        return []

    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        side_effect=capture_store,
    ):
        await _run_with_mocks(
            mock_db,
            llm_response=bad_json,
            seed_urls=[],
            run_extractor=True,
        )
    assert len(store_kwargs) == 1
    assert store_kwargs[0].get("structured_payloads") is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scout_run_with_extractor_on_stores_and_read_back_structured_payload(
    db: Session,
) -> None:
    """Integration: run with run_extractor=True persists ExtractionResult to store; read back matches."""
    run_id, bundles, _ = await _run_with_mocks(
        db,
        seed_urls=["https://example.com"],
        run_extractor=True,
    )
    assert len(bundles) == 1

    stored = list_bundles_by_run(db, run_id)
    assert len(stored) == 1
    payload = stored[0].structured_payload
    assert payload is not None
    assert "company" in payload
    assert payload["company"] is not None
    assert payload["company"].get("name") == "Acme Inc"
    assert payload["company"].get("website_url") == "https://acme.com"
    assert "core_event_candidates" in payload
    assert isinstance(payload["core_event_candidates"], list)
    assert "version" in payload
