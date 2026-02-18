"""Ingestion adapter framework for signal sources (Issue #89)."""

from app.ingestion.base import SourceAdapter
from app.ingestion.event_types import SIGNAL_EVENT_TYPES
from app.ingestion.ingest import run_ingest

__all__ = ["SourceAdapter", "SIGNAL_EVENT_TYPES", "run_ingest"]
