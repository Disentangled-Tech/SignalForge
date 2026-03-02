"""Unit and integration tests for monitor runner (M4, Issue #280). M6: run_monitor_full + persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.signal_event import SignalEvent
from app.monitor.runner import (
    MONITOR_PATHS,
    PAGE_MONITOR_SOURCE,
    _normalize_base_url,
    _urls_to_monitor,
    run_monitor,
    run_monitor_full,
)
from app.schemas.core_events import CoreEventCandidate


class TestNormalizeBaseUrl:
    def test_adds_https_if_no_scheme(self):
        assert _normalize_base_url("example.com") == "https://example.com"

    def test_strips_trailing_slash(self):
        assert _normalize_base_url("https://example.com/") == "https://example.com"

    def test_preserves_http(self):
        assert _normalize_base_url("http://example.com") == "http://example.com"


class TestUrlsToMonitor:
    def test_includes_homepage_and_paths(self):
        pairs = _urls_to_monitor("https://example.com")
        urls = [u for u, _ in pairs]
        assert "https://example.com" in urls
        for path in MONITOR_PATHS:
            assert any(path in u for u in urls)

    def test_source_types(self):
        pairs = _urls_to_monitor("https://example.com")
        assert pairs[0][1] == "homepage"
        assert len(pairs) == 1 + len(MONITOR_PATHS)


class TestRunMonitorUnit:
    """Unit tests with mocked fetch."""

    @pytest.mark.asyncio
    async def test_run_monitor_returns_empty_when_no_companies(self, db: Session):
        events = await run_monitor(db, company_ids=[])
        assert events == []

    @pytest.mark.asyncio
    async def test_run_monitor_skips_company_without_website_url(self, db: Session):
        c = Company(name="No URL", website_url=None)
        db.add(c)
        db.commit()
        events = await run_monitor(db, company_ids=[c.id])
        assert events == []


@pytest.mark.integration
class TestRunMonitorIntegration:
    """Integration: two snapshots with different content → runner produces one ChangeEvent."""

    @pytest.mark.asyncio
    async def test_two_snapshots_different_content_produces_one_change_event(
        self, db: Session
    ) -> None:
        company = Company(
            name="Monitor Integration Co",
            website_url="https://monitor-int.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        base_url = "https://monitor-int.example.com"
        # First run: fetch returns "Version A" for homepage only; others None
        html_a = "<html><body><p>" + "A" * 150 + "</p></body></html>"
        html_b = "<html><body><p>" + "B" * 150 + "</p></body></html>"

        call_count = [0]

        async def mock_fetch(url: str, check_robots: bool = False):
            if url != base_url:
                return None
            call_count[0] += 1
            return html_a if call_count[0] == 1 else html_b

        with patch("app.monitor.runner.fetch_page", new_callable=AsyncMock, side_effect=mock_fetch):
            events_first = await run_monitor(db, company_ids=[company.id])
            events_second = await run_monitor(db, company_ids=[company.id])

        assert len(events_first) == 0
        assert len(events_second) == 1
        ev = events_second[0]
        assert ev.page_url == base_url
        assert ev.company_id == company.id
        assert ev.before_hash != ev.after_hash

    @pytest.mark.asyncio
    async def test_run_monitor_with_company_ids_excludes_other_companies(self, db: Session) -> None:
        """Passing company_ids=[id_a] must not produce events for company id_b."""
        company_a = Company(
            name="Company A",
            website_url="https://company-a.example.com",
        )
        company_b = Company(
            name="Company B",
            website_url="https://company-b.example.com",
        )
        db.add_all([company_a, company_b])
        db.commit()
        db.refresh(company_a)
        db.refresh(company_b)
        id_a, id_b = company_a.id, company_b.id
        base_a = "https://company-a.example.com"
        base_b = "https://company-b.example.com"

        html_a1 = "<html><body><p>" + "A1" * 80 + "</p></body></html>"
        html_a2 = "<html><body><p>" + "A2" * 80 + "</p></body></html>"
        html_b = "<html><body><p>" + "B" * 80 + "</p></body></html>"

        call_count_a = [0]

        async def mock_fetch(url: str, check_robots: bool = False):
            if url == base_a:
                call_count_a[0] += 1
                return html_a1 if call_count_a[0] == 1 else html_a2
            if url == base_b:
                return html_b
            return None

        with patch("app.monitor.runner.fetch_page", new_callable=AsyncMock, side_effect=mock_fetch):
            events_first = await run_monitor(db, company_ids=[id_a])
            events_second = await run_monitor(db, company_ids=[id_a])

        assert len(events_first) == 0
        assert len(events_second) == 1
        assert all(ev.company_id == id_a for ev in events_second)
        assert not any(ev.company_id == id_b for ev in events_second)
        assert events_second[0].company_id == id_a


@pytest.mark.integration
class TestRunMonitorFullIntegration:
    """M6: Full monitor run → interpret → persist SignalEvent with source=page_monitor."""

    @pytest.mark.asyncio
    async def test_run_monitor_full_persists_signal_events_with_page_monitor_source(
        self, db: Session
    ) -> None:
        """Two page versions → one ChangeEvent → mocked LLM → at least one SignalEvent with source=page_monitor."""
        company = Company(
            name="M6 Persist Co",
            website_url="https://m6-persist.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        base_url = "https://m6-persist.example.com"
        html_a = "<html><body><p>" + "A" * 150 + "</p></body></html>"
        html_b = "<html><body><p>" + "B" * 150 + "</p></body></html>"
        call_count = [0]

        async def mock_fetch(url: str, check_robots: bool = False):
            if url != base_url:
                return None
            call_count[0] += 1
            return html_a if call_count[0] == 1 else html_b

        def mock_interpret(change_ev, *, llm_provider=None):
            return [
                CoreEventCandidate(
                    event_type="cto_role_posted",
                    event_time=change_ev.timestamp,
                    title=None,
                    summary="CTO role posted (monitor).",
                    url=change_ev.page_url,
                    confidence=0.85,
                    source_refs=[0],
                )
            ]

        with (
            patch("app.monitor.runner.fetch_page", new_callable=AsyncMock, side_effect=mock_fetch),
            patch("app.monitor.runner.interpret_change_event", side_effect=mock_interpret),
        ):
            await run_monitor(db, company_ids=[company.id])
            result = await run_monitor_full(db, company_ids=[company.id])

        assert result["status"] == "completed"
        assert result["change_events_count"] == 1
        assert result["events_stored"] >= 1

        rows = (
            db.query(SignalEvent)
            .filter(
                SignalEvent.source == PAGE_MONITOR_SOURCE,
                SignalEvent.company_id == company.id,
            )
            .all()
        )
        assert len(rows) >= 1
        ev = rows[0]
        assert ev.event_type == "cto_role_posted"
        assert ev.source == PAGE_MONITOR_SOURCE
        assert ev.company_id == company.id
        assert ev.summary is not None
