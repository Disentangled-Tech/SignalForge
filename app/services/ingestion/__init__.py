"""Ingestion job orchestration (Issue #90)."""

from app.services.ingestion.ingest_daily import run_ingest_daily

__all__ = ["run_ingest_daily"]
