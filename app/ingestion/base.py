"""Abstract adapter interface for signal sources (Issue #89)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.schemas.signal import RawEvent


class SourceAdapter(ABC):
    """Pluggable adapter for signal sources.

    Adapters return a list of RawEvent instances. The ingestion pipeline
    handles normalization, company resolution, and storage. Caller is
    responsible for deduplication via (source, source_event_id).
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifier for this adapter (e.g. 'crunchbase', 'producthunt')."""
        ...

    @abstractmethod
    def fetch_events(self, since: datetime) -> list[RawEvent]:
        """Fetch raw events from source since given datetime."""
        ...
