"""Tests for composite readiness + explain payload (Issue #87)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Company, SignalEvent
from app.services.readiness.readiness_engine import (
    apply_global_suppressors,
    build_explain_payload,
    compute_composite,
    compute_event_contributions,
    compute_readiness,
)
from app.services.readiness.scoring_constants import COMPOSITE_WEIGHTS
from app.services.readiness.snapshot_writer import write_readiness_snapshot


@dataclass
class MockEvent:
    """Event-like object with source/url for top_events."""

    event_type: str
    event_time: datetime
    confidence: float | None = 0.7
    source: str = "test"
    url: str | None = None


def _days_ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _event(
    etype: str,
    days_ago: int,
    confidence: float | None = 0.7,
    source: str = "test",
    url: str | None = None,
) -> MockEvent:
    return MockEvent(
        event_type=etype,
        event_time=_days_ago(days_ago),
        confidence=confidence,
        source=source,
        url=url,
    )


# ── compute_composite ────────────────────────────────────────────────────


class TestComputeComposite:
    """Composite formula R = 0.30M + 0.30C + 0.25P + 0.15G."""

    def test_formula_exact(self) -> None:
        """M=100, C=0, P=0, G=0 → R=30."""
        assert compute_composite(100, 0, 0, 0) == 30

    def test_formula_all_equal(self) -> None:
        """M=C=P=G=50 → R=50."""
        assert compute_composite(50, 50, 50, 50) == 50

    def test_formula_mixed(self) -> None:
        """M=70, C=60, P=55, G=40 → R=59 (0.30*70+0.30*60+0.25*55+0.15*40=58.75)."""
        assert compute_composite(70, 60, 55, 40) == 59

    def test_clamp_upper(self) -> None:
        """Values above 100 clamp to 100."""
        assert compute_composite(100, 100, 100, 100) == 100

    def test_clamp_lower(self) -> None:
        """Negative dimensions clamp to 0 (formula can't produce negative)."""
        assert compute_composite(0, 0, 0, 0) == 0

    def test_rounding_half_up(self) -> None:
        """0.30*33+0.30*33+0.25*33+0.15*33 = 33 exactly."""
        assert compute_composite(33, 33, 33, 33) == 33

    def test_weights_sum_to_one(self) -> None:
        """Composite weights sum to 1.0 (Issue #95)."""
        total = COMPOSITE_WEIGHTS["M"] + COMPOSITE_WEIGHTS["C"] + COMPOSITE_WEIGHTS["P"] + COMPOSITE_WEIGHTS["G"]
        assert abs(total - 1.0) < 1e-9

    def test_single_dimension_dominance(self) -> None:
        """M=100, C=P=G=0 → R=30 (Issue #95)."""
        assert compute_composite(100, 0, 0, 0) == 30
        assert compute_composite(0, 100, 0, 0) == 30
        assert compute_composite(0, 0, 100, 0) == 25
        assert compute_composite(0, 0, 0, 100) == 15


# ── apply_global_suppressors ──────────────────────────────────────────────


class TestApplyGlobalSuppressors:
    """Company status acquired/dead zeros dimensions."""

    def test_acquired_suppresses(self) -> None:
        """company_status=acquired → (0,0,0,0, ['company_status_suppressed'])."""
        m, c, p, g, supp = apply_global_suppressors(70, 60, 55, 40, "acquired")
        assert (m, c, p, g) == (0, 0, 0, 0)
        assert "company_status_suppressed" in supp

    def test_dead_suppresses(self) -> None:
        """company_status=dead → zeros."""
        m, c, p, g, supp = apply_global_suppressors(50, 50, 50, 50, "dead")
        assert (m, c, p, g) == (0, 0, 0, 0)
        assert "company_status_suppressed" in supp

    def test_active_passthrough(self) -> None:
        """company_status=active or None → no change."""
        m, c, p, g, supp = apply_global_suppressors(70, 60, 55, 40, None)
        assert (m, c, p, g) == (70, 60, 55, 40)
        assert supp == []

        m, c, p, g, supp = apply_global_suppressors(70, 60, 55, 40, "active")
        assert (m, c, p, g) == (70, 60, 55, 40)
        assert supp == []


# ── build_explain_payload ───────────────────────────────────────────────


class TestBuildExplainPayload:
    """Explain payload structure per v2-spec §4.5."""

    def test_structure(self) -> None:
        """Has weights, dimensions, top_events, suppressors_applied."""
        top = [
            {
                "event_type": "funding_raised",
                "event_time": "2026-02-01T00:00:00Z",
                "source": "crunchbase",
                "url": "https://example.com",
                "contribution_points": 35.0,
                "confidence": 0.9,
            }
        ]
        payload = build_explain_payload(70, 60, 55, 40, 59, top, [])
        assert "weights" in payload
        assert payload["weights"]["M"] == 0.30
        assert payload["weights"]["C"] == 0.30
        assert payload["weights"]["P"] == 0.25
        assert payload["weights"]["G"] == 0.15
        assert "dimensions" in payload
        assert payload["dimensions"] == {"M": 70, "C": 60, "P": 55, "G": 40, "R": 59}
        assert payload["top_events"] == top
        assert payload["suppressors_applied"] == []

    def test_suppressors_included(self) -> None:
        """suppressors_applied appears in payload."""
        payload = build_explain_payload(0, 0, 0, 0, 0, [], ["company_status_suppressed"])
        assert payload["suppressors_applied"] == ["company_status_suppressed"]

    def test_minimum_threshold_included_when_pack_defines_nonzero(self) -> None:
        """minimum_threshold in explain when pack defines it (Issue #174)."""
        payload = build_explain_payload(
            70, 60, 55, 40, 59, [], [], _cfg={"minimum_threshold": 60}
        )
        assert payload["minimum_threshold"] == 60

    def test_minimum_threshold_omitted_when_zero_or_default(self) -> None:
        """minimum_threshold not in payload when 0 (default)."""
        payload = build_explain_payload(
            70, 60, 55, 40, 59, [], [], _cfg={"minimum_threshold": 0}
        )
        assert "minimum_threshold" not in payload
        payload_none = build_explain_payload(70, 60, 55, 40, 59, [], [])
        assert "minimum_threshold" not in payload_none


class TestComputeReadiness:
    """Full flow: events → dimensions + composite + explain."""

    def test_full_flow(self) -> None:
        """Mock events produce valid result dict."""
        as_of = date.today()
        events = [
            _event("funding_raised", 5),
            _event("api_launched", 30),
            _event("enterprise_customer", 10),
        ]
        result = compute_readiness(events, as_of)
        assert "momentum" in result
        assert "complexity" in result
        assert "pressure" in result
        assert "leadership_gap" in result
        assert "composite" in result
        assert "explain" in result
        assert result["composite"] == compute_composite(
            result["momentum"],
            result["complexity"],
            result["pressure"],
            result["leadership_gap"],
        )
        assert result["explain"]["dimensions"]["R"] == result["composite"]
        assert len(result["explain"]["top_events"]) <= 8

    def test_company_status_suppressed(self) -> None:
        """company_status=acquired zeros composite and explain dimensions."""
        events = [_event("funding_raised", 5), _event("cto_role_posted", 10)]
        result = compute_readiness(events, date.today(), company_status="acquired")
        assert result["momentum"] == 0
        assert result["complexity"] == 0
        assert result["pressure"] == 0
        assert result["leadership_gap"] == 0
        assert result["composite"] == 0
        assert "company_status_suppressed" in result["explain"]["suppressors_applied"]

    def test_explain_includes_quiet_signal_amplification_applied(self) -> None:
        """When quiet signals amplified (no funding), explain has the key (Issue #113)."""
        events = [
            _event("api_launched", 30),
            _event("compliance_mentioned", 60),
        ]
        result = compute_readiness(events, date.today())
        assert "quiet_signal_amplification_applied" in result["explain"]
        amplified = result["explain"]["quiet_signal_amplification_applied"]
        assert "api_launched" in amplified
        assert "compliance_mentioned" in amplified

    def test_explain_no_quiet_amplification_when_funding_present(self) -> None:
        """With funding, quiet_signal_amplification_applied is absent (empty list not added)."""
        events = [
            _event("api_launched", 30),
            _event("funding_raised", 5),
        ]
        result = compute_readiness(events, date.today())
        # When has_funding, quiet_amplified is [] so key is not added to payload
        assert "quiet_signal_amplification_applied" not in result["explain"]

    def test_top_events_contribution_points_reflect_amplification(self) -> None:
        """contribution_points for quiet signals higher when no funding (Issue #113)."""
        events_no_funding = [_event("api_launched", 30)]
        events_with_funding = [
            _event("api_launched", 30),
            _event("funding_raised", 5),
        ]
        top_no_funding = compute_event_contributions(events_no_funding, date.today(), limit=8)
        top_with_funding = compute_event_contributions(events_with_funding, date.today(), limit=8)
        api_no = next((e for e in top_no_funding if e["event_type"] == "api_launched"), None)
        api_with = next((e for e in top_with_funding if e["event_type"] == "api_launched"), None)
        assert api_no is not None and api_with is not None
        # Amplified: 35*1.0*0.7=24.5; normal: 25*1.0*0.7=17.5 (C only)
        assert api_no["contribution_points"] > api_with["contribution_points"]


# ── compute_event_contributions ───────────────────────────────────────────


class TestComputeEventContributions:
    """Top events by contribution."""

    def test_returns_sorted_by_contribution(self) -> None:
        """Higher contribution events come first."""
        events = [
            _event("funding_raised", 5),  # high contrib
            _event("compliance_mentioned", 200),  # lower
        ]
        top = compute_event_contributions(events, date.today(), limit=8)
        assert len(top) >= 1
        assert top[0]["event_type"] == "funding_raised"
        assert "contribution_points" in top[0]
        assert "event_time" in top[0]
        assert "source" in top[0]

    def test_limit_respected(self) -> None:
        """Only up to limit events returned."""
        events = [_event("funding_raised", i) for i in range(15)]
        top = compute_event_contributions(events, date.today(), limit=5)
        assert len(top) <= 5

    def test_events_with_no_contribution_return_empty_or_partial(self) -> None:
        """Events with no contribution (unknown types, out of window) → partial result (Issue #95)."""
        # Only unknown/irrelevant events
        events = [
            MockEvent(event_type="unknown_type", event_time=_days_ago(5), confidence=1.0, source="test", url=None),
        ]
        top = compute_event_contributions(events, date.today(), limit=8)
        assert top == []


# ── write_readiness_snapshot (integration) ─────────────────────────────────


class TestWriteReadinessSnapshotPersists:
    """Snapshot written to DB."""

    def test_persists_snapshot(self, db: Session) -> None:
        """write_readiness_snapshot creates ReadinessSnapshot row."""
        company = Company(name="CompositeTestCo", website_url="https://composite.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        # Seed SignalEvents
        as_of = date.today()
        for i, etype in enumerate(["funding_raised", "api_launched", "enterprise_customer"]):
            ev = SignalEvent(
                company_id=company.id,
                source="test",
                event_type=etype,
                event_time=datetime.now(UTC) - timedelta(days=i * 10),
                confidence=0.8,
            )
            db.add(ev)
        db.commit()

        snapshot = write_readiness_snapshot(db, company.id, as_of)
        assert snapshot is not None
        assert snapshot.company_id == company.id
        assert snapshot.as_of == as_of
        assert snapshot.momentum >= 0
        assert snapshot.complexity >= 0
        assert snapshot.pressure >= 0
        assert snapshot.leadership_gap >= 0
        assert 0 <= snapshot.composite <= 100
        assert snapshot.explain is not None
        assert "weights" in snapshot.explain
        assert "dimensions" in snapshot.explain
        assert "top_events" in snapshot.explain
        assert "suppressors_applied" in snapshot.explain
        assert "delta_1d" in snapshot.explain
        assert snapshot.explain["delta_1d"] == 0  # no prev snapshot

    def test_no_events_returns_none(self, db: Session) -> None:
        """Company with no SignalEvents returns None."""
        company = Company(name="NoEventsCo", website_url="https://noevents.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        snapshot = write_readiness_snapshot(db, company.id, date.today())
        assert snapshot is None

    def test_explain_includes_delta_1d_when_prev_exists(self, db: Session) -> None:
        """Second snapshot includes delta_1d when previous day snapshot exists."""
        company = Company(name="DeltaTestCo", website_url="https://delta.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        # Seed SignalEvents
        for i, etype in enumerate(["funding_raised", "api_launched", "enterprise_customer"]):
            ev = SignalEvent(
                company_id=company.id,
                source="test",
                event_type=etype,
                event_time=datetime.now(UTC) - timedelta(days=i * 10),
                confidence=0.8,
            )
            db.add(ev)
        db.commit()

        # Day 1 snapshot (composite will be some value)
        as_of_1 = date.today() - timedelta(days=1)
        snap1 = write_readiness_snapshot(db, company.id, as_of_1)
        assert snap1 is not None
        composite_1 = snap1.composite

        # Day 2 snapshot - should have delta_1d = composite_2 - composite_1
        as_of_2 = date.today()
        snap2 = write_readiness_snapshot(db, company.id, as_of_2)
        assert snap2 is not None
        assert "delta_1d" in snap2.explain
        expected_delta = snap2.composite - composite_1
        assert snap2.explain["delta_1d"] == expected_delta
