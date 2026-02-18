"""Test adapter returning hardcoded RawEvents (Issue #89)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.signal import RawEvent
from app.ingestion.base import SourceAdapter


class TestAdapter(SourceAdapter):
    """Adapter that returns hardcoded RawEvents for testing and verification."""

    @property
    def source_name(self) -> str:
        return "test"

    def fetch_events(self, since: datetime) -> list[RawEvent]:
        """Return fixed list of RawEvents regardless of since."""
        return [
            RawEvent(
                company_name="Test Company A",
                domain="testa.example.com",
                website_url="https://testa.example.com",
                event_type_candidate="funding_raised",
                event_time=datetime(2026, 2, 18, 10, 0, 0, tzinfo=timezone.utc),
                title="Series A",
                summary="Raised $5M",
                url="https://example.com/funding/testa",
                source_event_id="test-adapter-001",
                raw_payload={"amount": 5000000},
            ),
            RawEvent(
                company_name="Test Company B",
                domain="testb.example.com",
                website_url="https://testb.example.com",
                event_type_candidate="job_posted_engineering",
                event_time=datetime(2026, 2, 18, 11, 0, 0, tzinfo=timezone.utc),
                title="Senior Engineer",
                summary="Hiring for growth",
                url="https://example.com/jobs/testb",
                source_event_id="test-adapter-002",
                raw_payload={"roles": ["engineer"]},
            ),
            RawEvent(
                company_name="Test Company C",
                domain="testc.example.com",
                event_type_candidate="cto_role_posted",
                event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=timezone.utc),
                title="CTO",
                source_event_id="test-adapter-003",
            ),
        ]
