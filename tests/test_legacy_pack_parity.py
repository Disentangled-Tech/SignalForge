"""Legacy-vs-Pack Parity Harness (TDD_rules, Phase 4 Cleanup).

Regression harness that compares outputs from:
- Legacy pipeline (pre-pack behavior, pack_id=NULL snapshots)
- Pack pipeline (fractional_cto_v1)

Uses a fixed, deterministic fixture. Asserts same entity set, same ordering
within tolerance, same score bands. See rules/TDD_rules.md.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest
import yaml
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import (
    Company,
    EngagementSnapshot,
    OutreachRecommendation,
    ReadinessSnapshot,
    SignalEvent,
    SignalInstance,
)
from app.services.briefing import get_emerging_companies
from app.services.readiness.readiness_engine import compute_readiness
from app.services.readiness.scoring_constants import (
    BASE_SCORES_COMPLEXITY,
    BASE_SCORES_LEADERSHIP_GAP,
    BASE_SCORES_MOMENTUM,
    BASE_SCORES_PRESSURE,
    CAP_DIMENSION_MAX,
    CAP_FOUNDER_URGENCY,
    CAP_JOBS_COMPLEXITY,
    CAP_JOBS_MOMENTUM,
    COMPOSITE_WEIGHTS,
    DEFAULT_DECAY_COMPLEXITY,
    DEFAULT_DECAY_MOMENTUM,
    DEFAULT_DECAY_PRESSURE,
    QUIET_SIGNAL_AMPLIFIED_BASE,
    QUIET_SIGNAL_LOOKBACK_DAYS,
    SUPPRESS_CTO_HIRED_60_DAYS,
    SUPPRESS_CTO_HIRED_180_DAYS,
    from_pack,
)
from app.services.readiness.snapshot_writer import write_readiness_snapshot

# Fixed as_of for determinism (TDD_rules)
_PARITY_AS_OF = date(2099, 6, 15)


@pytest.fixture(autouse=True)
def _clean_parity_test_data(db: Session) -> None:
    """Remove parity harness snapshots to avoid collision with other tests."""
    db.execute(delete(EngagementSnapshot).where(EngagementSnapshot.as_of == _PARITY_AS_OF))
    db.execute(delete(ReadinessSnapshot).where(ReadinessSnapshot.as_of == _PARITY_AS_OF))
    db.commit()
    yield
    db.execute(delete(EngagementSnapshot).where(EngagementSnapshot.as_of == _PARITY_AS_OF))
    db.execute(delete(ReadinessSnapshot).where(ReadinessSnapshot.as_of == _PARITY_AS_OF))
    db.commit()


def _event(event_type: str, days_ago: int, *, confidence: float = 0.8):
    """Create mock event for compute_readiness (no DB)."""
    from datetime import timedelta
    from types import SimpleNamespace

    base = datetime(2099, 6, 15, 12, 0, 0, tzinfo=UTC)
    event_time = base - timedelta(days=days_ago)
    return SimpleNamespace(
        event_type=event_type,
        event_time=event_time,
        confidence=confidence,
    )


def _load_fractional_cto_scoring() -> dict:
    """Load fractional_cto_v1 scoring.yaml for parity tests."""
    import os

    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "packs",
        "fractional_cto_v1",
        "scoring.yaml",
    )
    with open(path) as f:
        return yaml.safe_load(f)


class TestFromPackFractionalCtoMatchesDefaults:
    """from_pack(fractional_cto_v1) produces same values as module constants."""

    def test_from_pack_base_scores_match_module_defaults(self) -> None:
        """Base scores from pack contain module defaults; pack may add keys (e.g. repo_activity)."""
        cfg = from_pack(_load_fractional_cto_scoring())
        for k, v in BASE_SCORES_MOMENTUM.items():
            assert cfg["base_scores_momentum"].get(k) == v, f"momentum mismatch for {k}"
        for k, v in BASE_SCORES_COMPLEXITY.items():
            assert cfg["base_scores_complexity"].get(k) == v, f"complexity mismatch for {k}"
        for k, v in BASE_SCORES_PRESSURE.items():
            assert cfg["base_scores_pressure"].get(k) == v, f"pressure mismatch for {k}"
        for k, v in BASE_SCORES_LEADERSHIP_GAP.items():
            assert cfg["base_scores_leadership_gap"].get(k) == v, f"leadership_gap mismatch for {k}"

    def test_from_pack_caps_match_module_defaults(self) -> None:
        """Caps from pack match CAP_* constants."""
        import os

        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "packs",
            "fractional_cto_v1",
            "scoring.yaml",
        )
        with open(path) as f:
            scoring = yaml.safe_load(f)
        cfg = from_pack(scoring)
        assert cfg["cap_jobs_momentum"] == CAP_JOBS_MOMENTUM
        assert cfg["cap_jobs_complexity"] == CAP_JOBS_COMPLEXITY
        assert cfg["cap_founder_urgency"] == CAP_FOUNDER_URGENCY
        assert cfg["cap_dimension_max"] == CAP_DIMENSION_MAX

    def test_from_pack_composite_weights_match_module_defaults(self) -> None:
        """Composite weights from pack match COMPOSITE_WEIGHTS."""
        cfg = from_pack(_load_fractional_cto_scoring())
        assert cfg["composite_weights"] == COMPOSITE_WEIGHTS

    def test_from_pack_quiet_signal_matches_module_defaults(self) -> None:
        """Quiet signal config from pack matches module defaults."""
        cfg = from_pack(_load_fractional_cto_scoring())
        assert cfg["quiet_signal_lookback_days"] == QUIET_SIGNAL_LOOKBACK_DAYS
        assert cfg["quiet_signal_amplified_base"] == QUIET_SIGNAL_AMPLIFIED_BASE

    def test_from_pack_decay_matches_module_defaults(self) -> None:
        """Decay breakpoints from pack match DEFAULT_DECAY_* (Issue #174)."""
        cfg = from_pack(_load_fractional_cto_scoring())
        assert cfg["decay_momentum"] == DEFAULT_DECAY_MOMENTUM
        assert cfg["decay_pressure"] == DEFAULT_DECAY_PRESSURE
        assert cfg["decay_complexity"] == DEFAULT_DECAY_COMPLEXITY

    def test_from_pack_suppressors_match_module_defaults(self) -> None:
        """Suppressors from pack match SUPPRESS_CTO_HIRED_* (Issue #174)."""
        cfg = from_pack(_load_fractional_cto_scoring())
        assert cfg["suppress_cto_hired_60_days"] == SUPPRESS_CTO_HIRED_60_DAYS
        assert cfg["suppress_cto_hired_180_days"] == SUPPRESS_CTO_HIRED_180_DAYS

    def test_from_pack_minimum_threshold_defaults_to_zero(self) -> None:
        """minimum_threshold defaults to 0 when pack omits it (Issue #174)."""
        cfg = from_pack(_load_fractional_cto_scoring())
        assert cfg["minimum_threshold"] == 0

    def test_from_pack_disqualifier_signals_empty_for_cto(self) -> None:
        """Fractional CTO pack has empty disqualifier_signals for parity (Phase 2)."""
        cfg = from_pack(_load_fractional_cto_scoring())
        assert cfg["disqualifier_signals"] == {}


class TestReadinessParitySameEventsPackNoneVsCto:
    """compute_readiness(events, pack=None) == compute_readiness(events, pack=cto)."""

    def test_same_events_pack_none_vs_cto_produces_same_composite(self) -> None:
        """Fixed fixture: same events, pack=None vs pack=cto → same composite."""
        events = [
            _event("funding_raised", 5),
            _event("job_posted_engineering", 10),
            _event("cto_role_posted", 30),
        ]
        result_none = compute_readiness(events, _PARITY_AS_OF, pack=None)
        from app.packs.loader import load_pack

        cto_pack = load_pack("fractional_cto_v1", "1")
        result_pack = compute_readiness(events, _PARITY_AS_OF, pack=cto_pack)
        assert result_pack["composite"] == result_none["composite"]
        assert result_pack["momentum"] == result_none["momentum"]
        assert result_pack["complexity"] == result_none["complexity"]
        assert result_pack["pressure"] == result_none["pressure"]
        assert result_pack["leadership_gap"] == result_none["leadership_gap"]


class TestRecommendationBandParity:
    """When pack has bands, resolve_band matches expected for fixture scores (Issue #242)."""

    def test_fixture_scores_produce_expected_bands(self) -> None:
        """Fixed composites 34, 35, 69, 70 produce IGNORE, WATCH, WATCH, HIGH_PRIORITY."""
        from app.packs.loader import load_pack
        from app.services.signal_scorer import resolve_band

        cto_pack = load_pack("fractional_cto_v1", "1")
        assert resolve_band(34, cto_pack) == "IGNORE"
        assert resolve_band(35, cto_pack) == "WATCH"
        assert resolve_band(69, cto_pack) == "WATCH"
        assert resolve_band(70, cto_pack) == "HIGH_PRIORITY"


class TestEmergingCompaniesParityPackVsLegacy:
    """Same fixture data: pack snapshots vs legacy path → same entity set.

    After Issue #193, \"legacy\" means pack_id=None → default pack resolution,
    not rows with pack_id=NULL (NOT NULL enforced on snapshot/event tables).
    """

    @pytest.mark.integration
    def test_same_fixture_pack_vs_legacy_snapshots_same_entity_set(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Fixed fixture: pack path vs legacy (pack_id=None → default pack) → same surfaced entities."""
        companies = [
            Company(
                name=f"Parity Co {i}",
                website_url=f"https://parity{i}.parity.example.com",
            )
            for i in range(5)
        ]
        db.add_all(companies)
        db.commit()
        for c in companies:
            db.refresh(c)

        # Same composite/esl for both pack and legacy (simulating parity)
        composites = [70, 80, 90, 60, 65]
        esl_scores = [0.5, 0.8, 0.6, 1.0, 0.9]

        # Pack snapshots (pack_id=cto)
        for i, c in enumerate(companies):
            rs = ReadinessSnapshot(
                company_id=c.id,
                as_of=_PARITY_AS_OF,
                momentum=70,
                complexity=60,
                pressure=55,
                leadership_gap=40,
                composite=composites[i],
                pack_id=fractional_cto_pack_id,
            )
            db.add(rs)
            es = EngagementSnapshot(
                company_id=c.id,
                as_of=_PARITY_AS_OF,
                esl_score=esl_scores[i],
                engagement_type="Standard Outreach",
                cadence_blocked=False,
                pack_id=fractional_cto_pack_id,
            )
            db.add(es)

        db.commit()

        # Pack path: get_emerging_companies with pack_id=cto
        result_pack = get_emerging_companies(
            db,
            _PARITY_AS_OF,
            limit=10,
            outreach_score_threshold=30,
            pack_id=fractional_cto_pack_id,
        )
        pack_entity_ids = {c.id for _, _, c in result_pack}

        # Legacy path: pack_id=None → default pack (same as cto). Issue #193: no pack_id=NULL rows.
        result_legacy = get_emerging_companies(
            db,
            _PARITY_AS_OF,
            limit=10,
            outreach_score_threshold=30,
            pack_id=None,
        )
        legacy_entity_ids = {c.id for _, _, c in result_legacy}

        # Same entity set (both have same 5 companies)
        expected_ids = {c.id for c in companies}
        assert pack_entity_ids == expected_ids
        assert legacy_entity_ids == expected_ids

        # ESL decision (engagement_type) present and consistent for matching entities
        pack_by_id = {c.id: es.engagement_type for _, es, c in result_pack}
        legacy_by_id = {c.id: es.engagement_type for _, es, c in result_legacy}
        for eid in expected_ids:
            assert pack_by_id[eid], f"Pack result missing engagement_type for company {eid}"
            assert legacy_by_id[eid], f"Legacy result missing engagement_type for company {eid}"
            assert pack_by_id[eid] == legacy_by_id[eid], (
                f"ESL decision mismatch for company {eid}: pack={pack_by_id[eid]!r} vs legacy={legacy_by_id[eid]!r}"
            )

    @pytest.mark.integration
    def test_same_fixture_pack_vs_legacy_same_ordering_within_tolerance(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Fixed fixture: pack path vs legacy (pack_id=None → default pack) → same ordering (OutreachScore desc)."""
        companies = [
            Company(
                name=f"Order Co {i}",
                website_url=f"https://order{i}.parity.example.com",
            )
            for i in range(5)
        ]
        db.add_all(companies)
        db.commit()
        for c in companies:
            db.refresh(c)

        composites = [70, 80, 90, 60, 65]
        esl_scores = [0.5, 0.8, 0.6, 1.0, 0.9]
        # OutreachScores: 35, 64, 54, 60, 58 → order: 64, 60, 58, 54, 35

        # Pack-only snapshots
        for i, c in enumerate(companies):
            rs = ReadinessSnapshot(
                company_id=c.id,
                as_of=_PARITY_AS_OF,
                momentum=70,
                complexity=60,
                pressure=55,
                leadership_gap=40,
                composite=composites[i],
                pack_id=fractional_cto_pack_id,
            )
            db.add(rs)
            es = EngagementSnapshot(
                company_id=c.id,
                as_of=_PARITY_AS_OF,
                esl_score=esl_scores[i],
                engagement_type="Standard Outreach",
                cadence_blocked=False,
                pack_id=fractional_cto_pack_id,
            )
            db.add(es)
        db.commit()

        result_pack = get_emerging_companies(
            db,
            _PARITY_AS_OF,
            limit=5,
            outreach_score_threshold=30,
            pack_id=fractional_cto_pack_id,
        )
        pack_scores = [round(rs.composite * es.esl_score) for rs, es, _ in result_pack]

        # Legacy path: pack_id=None → default pack (same data). Issue #193: no pack_id=NULL rows.
        result_legacy = get_emerging_companies(
            db,
            _PARITY_AS_OF,
            limit=5,
            outreach_score_threshold=30,
            pack_id=None,
        )
        legacy_scores = [round(rs.composite * es.esl_score) for rs, es, _ in result_legacy]

        # Same score bands (ordering by OutreachScore desc)
        assert pack_scores == [64, 60, 58, 54, 35]
        assert legacy_scores == [64, 60, 58, 54, 35]

        # ESL decision (engagement_type) present for all results
        assert all(es.engagement_type for _, es, _ in result_pack)
        assert all(es.engagement_type for _, es, _ in result_legacy)

    @pytest.mark.integration
    def test_get_emerging_companies_pack_returns_companies_with_snapshots(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """get_emerging_companies (pack) returns companies when ReadinessSnapshot + EngagementSnapshot exist.

        Follow-up from docs/ISSUE_LEGACY_PACK_PARITY_HARNESS.md: pack path surfaces companies
        from snapshots. select_top_companies uses different data (AnalysisRecord); full comparison
        deferred until both paths share aligned fixture (see ISSUE_LEGACY_PACK_PARITY_HARNESS.md).
        """
        companies = [
            Company(
                name=f"Emerging Co {i}",
                website_url=f"https://emerging{i}.parity.example.com",
            )
            for i in range(3)
        ]
        db.add_all(companies)
        db.commit()
        for c in companies:
            db.refresh(c)

        composites = [70, 65, 60]
        esl_scores = [0.9] * 3
        for i, c in enumerate(companies):
            rs = ReadinessSnapshot(
                company_id=c.id,
                as_of=_PARITY_AS_OF,
                momentum=70,
                complexity=60,
                pressure=55,
                leadership_gap=40,
                composite=composites[i],
                pack_id=fractional_cto_pack_id,
            )
            db.add(rs)
            es = EngagementSnapshot(
                company_id=c.id,
                as_of=_PARITY_AS_OF,
                esl_score=esl_scores[i],
                engagement_type="Standard Outreach",
                cadence_blocked=False,
                pack_id=fractional_cto_pack_id,
            )
            db.add(es)
        db.commit()

        emerging = get_emerging_companies(
            db,
            _PARITY_AS_OF,
            limit=5,
            outreach_score_threshold=30,
            pack_id=fractional_cto_pack_id,
        )
        emerging_ids = {c.id for _, _, c in emerging}
        expected_ids = {c.id for c in companies}

        assert emerging_ids == expected_ids, (
            f"get_emerging_companies(pack) should return all companies with snapshots; "
            f"got {emerging_ids}, expected {expected_ids}"
        )


# TestAdapter domains for ingest→derive→score harness
_PARITY_TEST_DOMAINS = ("testa.example.com", "testb.example.com", "testc.example.com")
_PARITY_INGEST_AS_OF = date(2026, 2, 18)


class TestIngestDeriveScoreParity:
    """Pack pipeline (fractional_cto_v1) produces expected entities, signal_ids, scores.

    Fixture: TestAdapter returns 3 events (funding_raised, job_posted_engineering,
    cto_role_posted) for testa/testb/testc.example.com.
    """

    @pytest.fixture(autouse=True)
    def _cleanup_ingest_parity_data(self, db: Session) -> None:
        """Remove test adapter data before and after each test."""
        company_ids = [
            row[0]
            for row in db.query(Company.id).filter(Company.domain.in_(_PARITY_TEST_DOMAINS)).all()
        ]
        if company_ids:
            db.query(SignalInstance).filter(SignalInstance.entity_id.in_(company_ids)).delete(
                synchronize_session="fetch"
            )
            db.query(ReadinessSnapshot).filter(
                ReadinessSnapshot.company_id.in_(company_ids)
            ).delete(synchronize_session="fetch")
        db.query(SignalEvent).filter(SignalEvent.source == "test").delete(
            synchronize_session="fetch"
        )
        db.query(Company).filter(Company.domain.in_(_PARITY_TEST_DOMAINS)).delete(
            synchronize_session="fetch"
        )
        db.commit()
        yield
        company_ids = [
            row[0]
            for row in db.query(Company.id).filter(Company.domain.in_(_PARITY_TEST_DOMAINS)).all()
        ]
        if company_ids:
            db.query(SignalInstance).filter(SignalInstance.entity_id.in_(company_ids)).delete(
                synchronize_session="fetch"
            )
            db.query(ReadinessSnapshot).filter(
                ReadinessSnapshot.company_id.in_(company_ids)
            ).delete(synchronize_session="fetch")
        db.query(SignalEvent).filter(SignalEvent.source == "test").delete(
            synchronize_session="fetch"
        )
        db.query(Company).filter(Company.domain.in_(_PARITY_TEST_DOMAINS)).delete(
            synchronize_session="fetch"
        )
        db.commit()

    @pytest.mark.integration
    def test_parity_harness_same_entities_signal_ids_scores(
        self,
        db: Session,
        fractional_cto_pack_id,
        core_pack_id,
    ) -> None:
        """Ingest → derive → score produces expected entities, signal_ids, scores (Issue #287 M2: derive writes to core)."""
        from app.pipeline.deriver_engine import run_deriver
        from app.services.ingestion.ingest_daily import run_ingest_daily
        from app.services.readiness.score_nightly import run_score_nightly

        with patch("app.services.readiness.score_nightly.date") as mock_date:
            mock_date.today.return_value = _PARITY_INGEST_AS_OF

            ingest_result = run_ingest_daily(db)
            assert ingest_result["status"] == "completed"
            assert ingest_result["inserted"] == 3

            companies = (
                db.query(Company)
                .filter(Company.domain.in_(_PARITY_TEST_DOMAINS))
                .order_by(Company.domain)
                .all()
            )
            assert len(companies) == 3
            entities = {c.domain for c in companies}
            assert entities == {"testa.example.com", "testb.example.com", "testc.example.com"}

            derive_result = run_deriver(
                db,
                pack_id=fractional_cto_pack_id,
                company_ids=[c.id for c in companies],
            )
            assert derive_result["status"] == "completed"
            assert derive_result["instances_upserted"] == 3
            assert derive_result["events_processed"] == 3

            instances = (
                db.query(SignalInstance)
                .filter(
                    SignalInstance.entity_id.in_(c.id for c in companies),
                    SignalInstance.pack_id == core_pack_id,
                )
                .all()
            )
            signal_ids = {i.signal_id for i in instances}
            assert signal_ids == {"funding_raised", "job_posted_engineering", "cto_role_posted"}

            score_result = run_score_nightly(db, pack_id=fractional_cto_pack_id)
            assert score_result["status"] == "completed"
            assert score_result["companies_scored"] >= 1

            snapshots = (
                db.query(ReadinessSnapshot)
                .filter(
                    ReadinessSnapshot.company_id.in_(c.id for c in companies),
                    ReadinessSnapshot.as_of == _PARITY_INGEST_AS_OF,
                    ReadinessSnapshot.pack_id == fractional_cto_pack_id,
                )
                .all()
            )
            assert len(snapshots) >= 1
            for snap in snapshots:
                assert 0 <= snap.composite <= 100
                assert snap.explain is not None

            # Issue #175 Phase 2: ESL decision=allow for fractional CTO pack
            eng_snapshots = (
                db.query(EngagementSnapshot)
                .filter(
                    EngagementSnapshot.company_id.in_(c.id for c in companies),
                    EngagementSnapshot.as_of == _PARITY_INGEST_AS_OF,
                    EngagementSnapshot.pack_id == fractional_cto_pack_id,
                )
                .all()
            )
            for es in eng_snapshots:
                assert es.explain is not None
                assert es.explain.get("esl_decision") == "allow", (
                    f"Fractional CTO pack must produce esl_decision=allow; "
                    f"got {es.explain.get('esl_decision')!r} for company {es.company_id}"
                )
                # Phase 4: dedicated columns must match explain (Issue #175)
                assert es.esl_decision == "allow", (
                    f"EngagementSnapshot.esl_decision must be 'allow' for fractional CTO; "
                    f"got {es.esl_decision!r} for company {es.company_id}"
                )
                # sensitivity_level may be None for allow; when set, must be non-empty
                if es.sensitivity_level is not None:
                    assert len(es.sensitivity_level) > 0, (
                        f"sensitivity_level must be non-empty when set; company {es.company_id}"
                    )

    @pytest.mark.integration
    def test_parity_harness_derived_signal_ids_match_core_passthrough(
        self,
        db: Session,
        fractional_cto_pack_id,
        core_pack_id,
    ) -> None:
        """Ingest → derive → score: derived signal_ids match core derivers (Issue #285/#287 M2).

        Derive uses core derivers only and writes to core pack. Derived signal_ids
        must match core passthrough for TestAdapter event types.
        """
        from app.core_derivers.loader import get_core_passthrough_map
        from app.pipeline.deriver_engine import run_deriver
        from app.services.ingestion.ingest_daily import run_ingest_daily

        core_passthrough = get_core_passthrough_map()
        assert "funding_raised" in core_passthrough
        assert "job_posted_engineering" in core_passthrough
        assert "cto_role_posted" in core_passthrough

        with patch("app.services.readiness.score_nightly.date") as mock_date:
            mock_date.today.return_value = _PARITY_INGEST_AS_OF

            run_ingest_daily(db)
            companies = (
                db.query(Company)
                .filter(Company.domain.in_(_PARITY_TEST_DOMAINS))
                .order_by(Company.domain)
                .all()
            )
            assert len(companies) >= 1

            derive_result = run_deriver(
                db,
                pack_id=fractional_cto_pack_id,
                company_ids=[c.id for c in companies],
            )
            assert derive_result["status"] == "completed"

            instances = (
                db.query(SignalInstance)
                .filter(
                    SignalInstance.entity_id.in_(c.id for c in companies),
                    SignalInstance.pack_id == core_pack_id,
                )
                .all()
            )
            derived_signal_ids = {i.signal_id for i in instances}
            # Every derived signal_id must be in core passthrough (derive uses core only)
            core_signal_ids = set(core_passthrough.values())
            for sid in derived_signal_ids:
                assert sid in core_signal_ids, (
                    f"Derived signal_id {sid!r} must be in core derivers; "
                    f"core signal_ids: {core_signal_ids}"
                )
            # TestAdapter emits funding_raised, job_posted_engineering, cto_role_posted
            assert derived_signal_ids == {
                "funding_raised",
                "job_posted_engineering",
                "cto_role_posted",
            }

    @pytest.mark.integration
    def test_parity_derive_core_score_composite_matches_legacy(
        self,
        db: Session,
        fractional_cto_pack_id,
        core_pack_id,
    ) -> None:
        """Same events: legacy (pack-scoped events) vs derive→core (core instances) yield same composite (Issue #287).

        Two companies with identical SignalEvents. One scored via legacy path (core_pack_id=None),
        one via derive then core-instance path. Composites must match within tolerance.
        """
        from datetime import timedelta

        from app.pipeline.deriver_engine import run_deriver

        # Use fixed as_of and event times so both paths see same window
        as_of = _PARITY_AS_OF
        base_dt = datetime(2099, 6, 15, 12, 0, 0, tzinfo=UTC)
        ev1_time = base_dt - timedelta(days=5)
        ev2_time = base_dt - timedelta(days=50)

        company_legacy = Company(
            name="ParityLegacyCo",
            domain="parity-legacy.example.com",
            website_url="https://parity-legacy.example.com",
        )
        company_core = Company(
            name="ParityCoreCo",
            domain="parity-core.example.com",
            website_url="https://parity-core.example.com",
        )
        db.add_all([company_legacy, company_core])
        db.commit()
        db.refresh(company_legacy)
        db.refresh(company_core)

        for company in (company_legacy, company_core):
            db.add_all(
                [
                    SignalEvent(
                        company_id=company.id,
                        source="test",
                        event_type="funding_raised",
                        event_time=ev1_time,
                        confidence=0.9,
                        pack_id=fractional_cto_pack_id,
                    ),
                    SignalEvent(
                        company_id=company.id,
                        source="test",
                        event_type="cto_role_posted",
                        event_time=ev2_time,
                        confidence=0.7,
                        pack_id=fractional_cto_pack_id,
                    ),
                ]
            )
        db.commit()

        # Legacy path: no core_pack_id → event list from pack-scoped SignalEvents
        snap_legacy = write_readiness_snapshot(
            db,
            company_legacy.id,
            as_of,
            pack_id=fractional_cto_pack_id,
            core_pack_id=None,
        )
        assert snap_legacy is not None, "Legacy path must produce snapshot"
        composite_legacy = snap_legacy.composite

        # Core path: derive then score from core instances
        run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company_core.id])
        snap_core = write_readiness_snapshot(
            db,
            company_core.id,
            as_of,
            pack_id=fractional_cto_pack_id,
            core_pack_id=core_pack_id,
        )
        assert snap_core is not None, "Core path must produce snapshot"
        composite_core = snap_core.composite

        assert abs(composite_legacy - composite_core) <= 1, (
            f"Derive→core score composite should match legacy within 1 point: "
            f"legacy={composite_legacy} core={composite_core}"
        )

    @pytest.mark.integration
    def test_parity_run_derive_no_pack_then_score_with_pack_produces_composite(
        self,
        db: Session,
        fractional_cto_pack_id,
        core_pack_id,
    ) -> None:
        """run_derive(pack_id=None) → run_score(pack_id=workspace_pack) produces valid composite (Issue #287 M6).

        Backward compatibility: derive without pack (writes to core) then score with
        workspace pack yields same snapshot shape and composite as derive-with-pack path.
        """
        from app.pipeline.deriver_engine import run_deriver
        from app.services.ingestion.ingest_daily import run_ingest_daily
        from app.services.readiness.score_nightly import run_score_nightly

        with patch("app.services.readiness.score_nightly.date") as mock_date:
            mock_date.today.return_value = _PARITY_INGEST_AS_OF

            run_ingest_daily(db)
            companies = (
                db.query(Company)
                .filter(Company.domain.in_(_PARITY_TEST_DOMAINS))
                .order_by(Company.domain)
                .all()
            )
            assert len(companies) >= 1

            derive_result = run_deriver(db, pack_id=None, company_ids=[c.id for c in companies])
            assert derive_result["status"] == "completed", (
                f"run_deriver(pack_id=None) must complete when core pack exists: {derive_result}"
            )
            assert derive_result["instances_upserted"] >= 1

            instances = (
                db.query(SignalInstance)
                .filter(
                    SignalInstance.entity_id.in_(c.id for c in companies),
                    SignalInstance.pack_id == core_pack_id,
                )
                .all()
            )
            assert len(instances) >= 1, "Derive (no pack) must write to core SignalInstances"

            score_result = run_score_nightly(db, pack_id=fractional_cto_pack_id)
            assert score_result["status"] == "completed"
            assert score_result["companies_scored"] >= 1

            snapshots = (
                db.query(ReadinessSnapshot)
                .filter(
                    ReadinessSnapshot.company_id.in_(c.id for c in companies),
                    ReadinessSnapshot.as_of == _PARITY_INGEST_AS_OF,
                    ReadinessSnapshot.pack_id == fractional_cto_pack_id,
                )
                .all()
            )
            assert len(snapshots) >= 1, (
                "run_score(with pack) must produce pack-scoped ReadinessSnapshots from core instances"
            )
            for snap in snapshots:
                assert 0 <= snap.composite <= 100
                assert snap.explain is not None


# Draft constraints for parity harness (TDD_rules, docs/ISSUE_LEGACY_PACK_PARITY_HARNESS.md)
_ALLOWED_RECOMMENDATION_TYPES = frozenset(
    {
        "Observe Only",
        "Soft Value Share",
        "Low-Pressure Intro",
        "Standard Outreach",
        "Direct Strategic Outreach",
    }
)
_SURVEILLANCE_PHRASES = (
    "I noticed you",
    "I saw that you",
    "After your recent funding",
    "You're hiring",
)
_CTA_PATTERNS = ("Want me to send", "Open to a", "If helpful", "would it help")


class TestOutreachDraftConstraintsParity:
    """Parity harness: when ORE path is exercised, assert draft constraints (tone, required elements, no forbidden phrases).

    See docs/ISSUE_LEGACY_PACK_PARITY_HARNESS.md and rules/TDD_rules.md § Legacy-vs-Pack Parity Harness.
    """

    @pytest.mark.integration
    def test_ore_parity_playbook_id_and_draft_constraints(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """ORE (fractional_cto_v1) sets playbook_id and stored drafts satisfy tone, required elements, no forbidden phrases."""
        from unittest.mock import patch

        from app.services.ore.ore_pipeline import generate_ore_recommendation
        from app.services.ore.playbook_loader import DEFAULT_PLAYBOOK_NAME, get_ore_playbook
        from app.services.pack_resolver import resolve_pack

        # Deterministic critic-compliant draft (no surveillance, single CTA, opt-out)
        draft = {
            "subject": "Quick question about ParityCo",
            "message": (
                "Hi Parity Founder,\n\n"
                "When products add integrations and enterprise asks, systems often need a stabilization pass.\n\n"
                "I have a 2-page Tech Inflection Checklist that might help. Want me to send that checklist? "
                "No worries if now isn't the time."
            ),
        }

        company = Company(
            name="ParityCo",
            website_url="https://parity-ore.example.com",
            founder_name="Parity Founder",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        as_of = _PARITY_AS_OF
        rs = ReadinessSnapshot(
            company_id=company.id,
            as_of=as_of,
            momentum=70,
            complexity=65,
            pressure=50,
            leadership_gap=55,
            composite=62,
            pack_id=fractional_cto_pack_id,
        )
        db.add(rs)
        es = EngagementSnapshot(
            company_id=company.id,
            as_of=as_of,
            esl_score=0.85,
            engagement_type="Standard Outreach",
            esl_decision="allow",
            cadence_blocked=False,
            pack_id=fractional_cto_pack_id,
        )
        db.add(es)
        db.commit()

        try:
            with patch(
                "app.services.ore.ore_pipeline.generate_ore_draft",
                return_value=draft,
            ):
                rec = generate_ore_recommendation(db, company_id=company.id, as_of=as_of)

            assert rec is not None, "ORE must return OutreachRecommendation when snapshot exists"
            # Same playbook chosen (parity harness assertion)
            assert rec.playbook_id == DEFAULT_PLAYBOOK_NAME, (
                f"ORE must set playbook_id to playbook name; got {rec.playbook_id!r}"
            )
            assert rec.pack_id == fractional_cto_pack_id

            # Correct tone class: recommendation_type must be one of the allowed set
            assert rec.recommendation_type in _ALLOWED_RECOMMENDATION_TYPES, (
                f"recommendation_type must be allowed; got {rec.recommendation_type!r}"
            )

            variants = rec.draft_variants or []
            if not variants:
                # Observe Only or no draft generated — no draft constraints to check
                return

            pack = resolve_pack(db, fractional_cto_pack_id)
            playbook = get_ore_playbook(pack, DEFAULT_PLAYBOOK_NAME)
            forbidden_phrases = playbook.get("forbidden_phrases") or []

            for i, v in enumerate(variants):
                subject = v.get("subject", "")
                message = v.get("message", "")
                combined = f"{subject} {message}".lower()

                # (3) Do not contain any pack forbidden phrases
                for phrase in forbidden_phrases:
                    if phrase and isinstance(phrase, str):
                        assert phrase.lower() not in combined, (
                            f"Draft variant {i} contains pack forbidden phrase {phrase!r}"
                        )

                # (4) Reference only allowed facts — no surveillance / raw observation text
                for phrase in _SURVEILLANCE_PHRASES:
                    assert phrase.lower() not in combined, (
                        f"Draft variant {i} contains surveillance phrase {phrase!r}"
                    )

                # (2) Contain required elements: value and CTA (consent-based)
                has_cta = any(cta.lower() in message.lower() for cta in _CTA_PATTERNS)
                assert has_cta, (
                    f"Draft variant {i} must contain at least one consent-based CTA pattern"
                )
                # Value: draft should offer something (pattern + value asset or similar)
                assert len(message.strip()) >= 20, (
                    f"Draft variant {i} must have substantive message (value/pattern)"
                )
        finally:
            db.query(OutreachRecommendation).filter(
                OutreachRecommendation.company_id == company.id,
                OutreachRecommendation.as_of == as_of,
                OutreachRecommendation.pack_id == fractional_cto_pack_id,
            ).delete(synchronize_session="fetch")
            db.execute(
                delete(EngagementSnapshot).where(EngagementSnapshot.company_id == company.id)
            )
            db.execute(delete(ReadinessSnapshot).where(ReadinessSnapshot.company_id == company.id))
            db.delete(company)
            db.commit()

    def test_ore_parity_critic_rejects_pack_forbidden_phrases(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """M5 (Issue #120): Parity — critic must reject any draft containing a pack forbidden_phrase."""
        from app.services.ore.critic import check_critic
        from app.services.ore.playbook_loader import DEFAULT_PLAYBOOK_NAME, get_ore_playbook
        from app.services.pack_resolver import resolve_pack

        pack = resolve_pack(db, fractional_cto_pack_id)
        playbook = get_ore_playbook(pack, DEFAULT_PLAYBOOK_NAME)
        forbidden_phrases = playbook.get("forbidden_phrases") or []
        if not forbidden_phrases:
            # Fixture so parity assertion always runs (fractional_cto_v1 may have empty list)
            forbidden_phrases = ["limited time offer"]

        base_subject = "Quick question about TestCo"
        base_message = (
            "Hi Jane, teams often hit a complexity step-change. "
            "Want me to send a checklist? No worries if now isn't the time."
        )
        for phrase in forbidden_phrases:
            if not phrase or not isinstance(phrase, str):
                continue
            message_with_phrase = base_message + " " + phrase
            result = check_critic(
                base_subject,
                message_with_phrase,
                forbidden_phrases=[phrase],
            )
            assert not result.passed, (
                f"Critic must reject draft containing pack forbidden phrase {phrase!r} (parity)"
            )
            assert any(phrase.lower() in v.lower() for v in result.violations)
