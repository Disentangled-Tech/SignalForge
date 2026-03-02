"""Diff-based monitor engine: snapshots, diff detection, change events (pack-agnostic)."""

from app.monitor.snapshot_store import get_latest_snapshot, save_snapshot

__all__ = ["get_latest_snapshot", "save_snapshot"]
