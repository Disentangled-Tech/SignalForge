"""Diff-based monitor (pack-agnostic): snapshots, diff detection, change events.

M3: Diff detection — compute_diff, ChangeEvent schema, detector.
"""

from app.monitor.detector import detect_change
from app.monitor.diff import compute_diff

__all__ = ["compute_diff", "detect_change"]
