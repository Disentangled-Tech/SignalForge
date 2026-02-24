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
from sqlalchemy import and_, delete
from sqlalchemy.orm import Session

from app.models import Company, EngagementSnapshot, ReadinessSnapshot, SignalEvent, SignalInstance
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

# Fixed as_of for determinism (TDD_rules)
_PARITY_AS_OF = date(2099, 6, 15)


@pytest.fixture(autouse=True)
def _clean_parity_test_data(db: Session) -> None:
    """Remove parity harness snapshots to avoid collision with other tests."""
    db.execute(
        delete(EngagementSnapshot).where(EngagementSnapshot.as_of == _PARITY_AS_OF)
    )
    db.execute(
        delete(ReadinessSnapshot).where(ReadinessSnapshot.as_of == _PARITY_AS_OF)
    )
    db.commit()
    yield
    db.execute(
        delete(EngagementSnapshot).where(EngagementSnapshot.as_of == _PARITY_AS_OF)
    )
    db.execute(
        delete(ReadinessSnapshot).where(ReadinessSnapshot.as_of == _PARITY_AS_OF)
    )
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
        """Base scores from pack match BASE_SCORES_* constants."""
        cfg = from_pack(_load_fractional_cto_scoring())
        assert cfg["base_scores_momentum"] == BASE_SCORES_MOMENTUM
        assert cfg["base_scores_complexity"] == BASE_SCORES_COMPLEXITY
        assert cfg["base_scores_pressure"] == BASE_SCORES_PRESSURE
        assert cfg["base_scores_leadership_gap"] == BASE_SCORES_LEADERSHIP_GAP

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


class TestEmergingCompaniesParityPackVsLegacy:
    """Same fixture data: pack snapshots vs legacy (pack_id=NULL) → same entity set."""

    @pytest.mark.integration
    def test_same_fixture_pack_vs_legacy_snapshots_same_entity_set(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Fixed fixture: pack_id=cto vs pack_id=NULL snapshots → same surfaced entities."""
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

        # Legacy snapshots (pack_id=NULL)
        for i, c in enumerate(companies):
            rs = ReadinessSnapshot(
                company_id=c.id,
                as_of=_PARITY_AS_OF,
                momentum=70,
                complexity=60,
                pressure=55,
                leadership_gap=40,
                composite=composites[i],
                pack_id=None,
            )
            db.add(rs)
            es = EngagementSnapshot(
                company_id=c.id,
                as_of=_PARITY_AS_OF,
                esl_score=esl_scores[i],
                engagement_type="Standard Outreach",
                cadence_blocked=False,
                pack_id=None,
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

        # Legacy path: get_emerging_companies with pack_id=None uses default pack,
        # which matches both cto and NULL. To isolate legacy-only, we'd need a
        # separate pack. For parity: both paths should surface the same 5 companies.
        # When pack_filter includes NULL, we get legacy rows. Assert entity set.
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
        """Fixed fixture: pack-only vs legacy-only → same ordering (OutreachScore desc)."""
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
        pack_scores = [
            round(rs.composite * es.esl_score) for rs, es, _ in result_pack
        ]

        # Remove pack snapshots, add legacy-only (pack_id=NULL)
        db.execute(
            delete(ReadinessSnapshot).where(
                and_(
                    ReadinessSnapshot.as_of == _PARITY_AS_OF,
                    ReadinessSnapshot.pack_id == fractional_cto_pack_id,
                )
            )
        )
        db.execute(
            delete(EngagementSnapshot).where(
                and_(
                    EngagementSnapshot.as_of == _PARITY_AS_OF,
                    EngagementSnapshot.pack_id == fractional_cto_pack_id,
                )
            )
        )
        db.commit()

        for i, c in enumerate(companies):
            rs = ReadinessSnapshot(
                company_id=c.id,
                as_of=_PARITY_AS_OF,
                momentum=70,
                complexity=60,
                pressure=55,
                leadership_gap=40,
                composite=composites[i],
                pack_id=None,
            )
            db.add(rs)
            es = EngagementSnapshot(
                company_id=c.id,
                as_of=_PARITY_AS_OF,
                esl_score=esl_scores[i],
                engagement_type="Standard Outreach",
                cadence_blocked=False,
                pack_id=None,
            )
            db.add(es)
        db.commit()

        result_legacy = get_emerging_companies(
            db,
            _PARITY_AS_OF,
            limit=5,
            outreach_score_threshold=30,
            pack_id=None,
        )
        legacy_scores = [
            round(rs.composite * es.esl_score) for rs, es, _ in result_legacy
        ]

        # Same score bands (ordering by OutreachScore desc)
        assert pack_scores == [64, 60, 58, 54, 35]
        assert legacy_scores == [64, 60, 58, 54, 35]

        # ESL decision (engagement_type) present for all results
        assert all(es.engagement_type for _, es, _ in result_pack)
        assert all(es.engagement_type for _, es, _ in result_legacy)


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
            db.query(SignalInstance).filter(
                SignalInstance.entity_id.in_(company_ids)
            ).delete(synchronize_session="fetch")
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
            db.query(SignalInstance).filter(
                SignalInstance.entity_id.in_(company_ids)
            ).delete(synchronize_session="fetch")
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
    ) -> None:
        """Ingest → derive → score produces expected entities, signal_ids, scores."""
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
                    SignalInstance.pack_id == fractional_cto_pack_id,
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
