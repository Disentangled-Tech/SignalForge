"""Unit tests for Discovery Scout Service (Evidence-Only, plan Step 5 / M4)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.evidence.repository import list_bundles_by_run
from app.models.evidence_quarantine import EvidenceQuarantine
from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from app.services.scout.discovery_scout_service import run
from app.verification.schemas import VerificationResult
from tests.test_constants import TEST_WORKSPACE_ID


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
    workspace_id: uuid.UUID,
    seed_urls: list[str] | None = None,
    llm_response: str | None = None,
    fetch_returns: str | None = "<p>Some content</p>",
    denylist: list[str] | None = None,
    allowlist: list[str] | None = None,
    page_fetch_limit: int = 10,
    run_extractor: bool | None = None,
    run_interpretation: bool | None = None,
):
    """Run scout with mocked fetch and LLM. workspace_id is required for tenant scoping."""
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
            workspace_id=workspace_id,
            run_extractor=run_extractor,
            run_interpretation=run_interpretation,
        )


@pytest.mark.asyncio
async def test_run_returns_valid_bundles_and_persists(db: Session) -> None:
    """run() returns validated EvidenceBundles and persists ScoutRun + ScoutEvidenceBundle rows."""
    from app.models.workspace import Workspace

    ws = Workspace(name="Scout Test WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    run_id, bundles, metadata = await _run_with_mocks(
        db, workspace_id=ws.id, seed_urls=["https://allowed.com/a"]
    )
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
async def test_config_snapshot_contains_queries_families_and_bundles_count(db: Session) -> None:
    """M3: config_snapshot after run contains queries, query_families, and run-level bundles_count."""
    from app.models.workspace import Workspace

    ws = Workspace(name="Scout Config Snapshot WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    run_id, bundles, _ = await _run_with_mocks(
        db, workspace_id=ws.id, seed_urls=["https://allowed.com/a"]
    )
    row = db.query(ScoutRun).filter(ScoutRun.run_id == uuid.UUID(run_id)).first()
    assert row is not None
    snap = row.config_snapshot
    assert snap is not None
    assert "queries" in snap
    assert "query_families" in snap
    assert "bundles_count" in snap
    assert "query_count" in snap
    assert isinstance(snap["queries"], list)
    assert isinstance(snap["query_families"], list)
    assert len(snap["queries"]) == snap["query_count"]
    assert len(snap["query_families"]) == len(snap["queries"])
    assert snap["bundles_count"] == len(bundles)


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
                await _run_with_mocks(
                    mock_db, workspace_id=TEST_WORKSPACE_ID, seed_urls=["https://example.com"]
                )
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
            workspace_id=TEST_WORKSPACE_ID,
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
            workspace_id=TEST_WORKSPACE_ID,
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
        run_id, bundles, metadata = await _run_with_mocks(
            mock_db, workspace_id=TEST_WORKSPACE_ID, llm_response=bad_json
        )
    assert len(bundles) == 0


@pytest.mark.asyncio
async def test_bundle_with_evidence_and_why_now_accepted() -> None:
    """Valid bundle with evidence and why_now_hypothesis is accepted."""
    mock_db = _mock_db_session()
    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        return_value=[],
    ):
        run_id, bundles, _ = await _run_with_mocks(
            mock_db, workspace_id=TEST_WORKSPACE_ID, llm_response=_valid_llm_bundles_json()
        )
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
        run_id, bundles, metadata = await _run_with_mocks(
            mock_db, workspace_id=TEST_WORKSPACE_ID, seed_urls=[]
        )
    assert metadata.page_fetch_count == 0


@pytest.mark.asyncio
async def test_output_schema_has_no_pack_specific_fields() -> None:
    """Validated EvidenceBundle has no signal_id, event_type, or pack-specific fields."""
    mock_db = _mock_db_session()
    with patch(
        "app.services.scout.discovery_scout_service.store_evidence_bundle",
        return_value=[],
    ):
        run_id, bundles, _ = await _run_with_mocks(mock_db, workspace_id=TEST_WORKSPACE_ID)
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
async def test_scout_run_with_extractor_disabled_calls_store_with_structured_payloads_none() -> (
    None
):
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
            workspace_id=TEST_WORKSPACE_ID,
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
            workspace_id=TEST_WORKSPACE_ID,
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
async def test_scout_run_with_extractor_enabled_empty_bundles_calls_store_with_none_payloads() -> (
    None
):
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
            workspace_id=TEST_WORKSPACE_ID,
            llm_response=bad_json,
            seed_urls=[],
            run_extractor=True,
        )
    assert len(store_kwargs) == 1
    assert store_kwargs[0].get("structured_payloads") is None


# --- M4: Optional Scout interpretation (LLM Event Interpretation) ---


@pytest.mark.asyncio
async def test_scout_run_with_interpretation_enabled_structured_payload_has_core_event_candidates() -> (
    None
):
    """With run_extractor=True and run_interpretation=True, structured_payload contains non-empty core_event_candidates when LLM returns valid events."""
    from app.schemas.core_events import CoreEventCandidate

    core_signal_ids = __import__(
        "app.core_taxonomy.loader", fromlist=["get_core_signal_ids"]
    ).get_core_signal_ids()
    valid_event_type = next(iter(core_signal_ids))
    mock_candidates = [
        CoreEventCandidate(
            event_type=valid_event_type,
            confidence=0.9,
            source_refs=[0],
            summary="Hiring engineers.",
        )
    ]

    mock_db = _mock_db_session()
    store_kwargs: list[dict] = []

    def capture_store(*args: object, **kwargs: object) -> list:
        store_kwargs.append(dict(kwargs))
        return []

    with (
        patch(
            "app.services.scout.discovery_scout_service.store_evidence_bundle",
            side_effect=capture_store,
        ),
        patch(
            "app.services.scout.discovery_scout_service.interpret_bundle_to_core_events",
            return_value=mock_candidates,
        ),
    ):
        await _run_with_mocks(
            mock_db,
            workspace_id=TEST_WORKSPACE_ID,
            seed_urls=["https://example.com"],
            run_extractor=True,
            run_interpretation=True,
        )
    assert len(store_kwargs) == 1
    payloads = store_kwargs[0].get("structured_payloads")
    assert payloads is not None
    assert len(payloads) == 1
    assert payloads[0]["core_event_candidates"]
    assert len(payloads[0]["core_event_candidates"]) == 1
    assert payloads[0]["core_event_candidates"][0]["event_type"] == valid_event_type


@pytest.mark.asyncio
async def test_scout_run_interpretation_pack_id_does_not_alter_result() -> None:
    """Interpretation is not given pack_id; pack selection does not alter interpretation result."""
    from app.schemas.core_events import CoreEventCandidate

    core_signal_ids = __import__(
        "app.core_taxonomy.loader", fromlist=["get_core_signal_ids"]
    ).get_core_signal_ids()
    valid_event_type = next(iter(core_signal_ids))
    mock_candidates = [
        CoreEventCandidate(
            event_type=valid_event_type,
            confidence=0.85,
            source_refs=[0],
            summary="Funding round.",
        )
    ]

    mock_db = _mock_db_session()
    store_kwargs: list[dict] = []

    def capture_store(*args: object, **kwargs: object) -> list:
        store_kwargs.append(dict(kwargs))
        return []

    interpret_mock = MagicMock(return_value=mock_candidates)

    with (
        patch(
            "app.services.scout.discovery_scout_service.store_evidence_bundle",
            side_effect=capture_store,
        ),
        patch(
            "app.services.scout.discovery_scout_service.interpret_bundle_to_core_events",
            side_effect=interpret_mock,
        ),
    ):
        await _run_with_mocks(
            mock_db,
            workspace_id=TEST_WORKSPACE_ID,
            seed_urls=["https://example.com"],
            run_extractor=True,
            run_interpretation=True,
        )
    # interpret_bundle_to_core_events is called with (bundle, llm_provider=...); no pack_id
    assert interpret_mock.call_count == 1
    call_args = interpret_mock.call_args
    assert len(call_args[0]) == 1  # single positional arg (bundle)
    assert call_args[1].get("llm_provider") is not None
    assert "pack_id" not in call_args[1]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scout_run_with_extractor_on_stores_and_read_back_structured_payload(
    db: Session,
) -> None:
    """Integration: run with run_extractor=True persists ExtractionResult to store; read back matches."""
    from app.models.workspace import Workspace

    ws = Workspace(name="Scout Extractor WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    run_id, bundles, _ = await _run_with_mocks(
        db,
        workspace_id=ws.id,
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


def _two_bundles_llm_json() -> str:
    """Return LLM response JSON with two valid EvidenceBundles (for M3 verification gate test)."""
    return json.dumps(
        {
            "bundles": [
                {
                    "candidate_company_name": "Pass Co",
                    "company_website": "https://pass.example.com",
                    "why_now_hypothesis": "Seed round.",
                    "evidence": [
                        {
                            "url": "https://pass.example.com/news",
                            "quoted_snippet": "Seed round.",
                            "timestamp_seen": "2025-02-27T12:00:00Z",
                            "source_type": "news",
                            "confidence_score": 0.9,
                        }
                    ],
                    "missing_information": [],
                },
                {
                    "candidate_company_name": "Fail Co",
                    "company_website": "https://fail.example.com",
                    "why_now_hypothesis": "Hiring.",
                    "evidence": [
                        {
                            "url": "https://fail.example.com/jobs",
                            "quoted_snippet": "CTO role.",
                            "timestamp_seen": "2025-02-27T12:00:00Z",
                            "source_type": "careers",
                            "confidence_score": 0.9,
                        }
                    ],
                    "missing_information": [],
                },
            ]
        }
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scout_run_with_verification_enabled_quarantines_failures_stores_passing(
    db: Session,
) -> None:
    """M3: With verification gate enabled, failing bundle is quarantined with reason_codes; only passing stored."""
    from app.models.workspace import Workspace

    ws = Workspace(name="Scout Verification WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    # When verify_bundles returns one pass and one fail, Scout must quarantine the failed and store only the passing.
    def mock_verify_bundles(bundles, structured_payloads=None):
        from app.verification.service import verify_bundles as real_verify_bundles

        results = real_verify_bundles(bundles, structured_payloads)
        # Force second bundle to fail so we assert quarantine + single stored bundle
        if len(results) >= 2:
            results = [
                results[0],
                VerificationResult(passed=False, reason_codes=["EVENT_TYPE_UNKNOWN"]),
            ]
        return results

    settings = MagicMock()
    settings.scout_source_allowlist = []
    settings.scout_source_denylist = []
    settings.scout_run_extractor = False
    settings.scout_verification_gate_enabled = True

    with (
        patch(
            "app.services.scout.discovery_scout_service.get_settings",
            return_value=settings,
        ),
        patch(
            "app.services.scout.discovery_scout_service.verify_bundles",
            side_effect=mock_verify_bundles,
        ),
    ):
        run_id, bundles, _ = await _run_with_mocks(
            db,
            workspace_id=ws.id,
            seed_urls=["https://example.com"],
            llm_response=_two_bundles_llm_json(),
            run_extractor=False,
        )

    # Scout returns both validated bundles to caller; store path only persists passing
    assert len(bundles) == 2

    # Evidence store: only the first (passing) bundle was stored
    stored = list_bundles_by_run(db, run_id)
    assert len(stored) == 1
    assert stored[0].structured_payload is None  # run_extractor=False

    # One quarantine row with reason_codes
    quarantine_rows = db.query(EvidenceQuarantine).all()
    assert len(quarantine_rows) == 1
    assert quarantine_rows[0].payload.get("reason_codes") == ["EVENT_TYPE_UNKNOWN"]
    assert quarantine_rows[0].payload.get("bundle_index") == 1
    assert "Fail Co" in str(
        quarantine_rows[0].payload.get("bundle", {}).get("candidate_company_name", "")
    )
