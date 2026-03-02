"""Diff-based monitor (pack-agnostic): snapshots, diff detection, change events.

M2: snapshot_store (get_latest_snapshot, save_snapshot).
M3: Diff detection — compute_diff, detector (detect_change).
"""

from app.monitor.detector import detect_change
from app.monitor.diff import compute_diff
from app.monitor.snapshot_store import get_latest_snapshot, save_snapshot

__all__ = [
    "compute_diff",
    "detect_change",
    "get_latest_snapshot",
    "save_snapshot",
]
