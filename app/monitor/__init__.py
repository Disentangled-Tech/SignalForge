"""Diff-based monitor (M2–M7): snapshot store, diff detection, change events, LLM interpretation.

Pack-agnostic; Core-owned. Emits Core Event candidates only.

M6 integration (when adding monitor runner and store_signal_event):
- Set workspace_id and pack_id from run context on every persisted SignalEvent
  (source="page_monitor"); do not rely on request or global state.
- Add integration test: one company, two page versions → at least one SignalEvent
  with source="page_monitor" and valid event_type.
"""

from app.monitor.interpretation import interpret_change_event
from app.monitor.schemas import ChangeEvent

__all__ = ["ChangeEvent", "interpret_change_event"]
