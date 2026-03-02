"""Validation for Evidence Extractor (Issue #277): core event types only."""

from __future__ import annotations


def is_valid_core_event_type(candidate: str) -> bool:
    """Return True if candidate is a valid core event type (core taxonomy signal_id).

    Event types in the Extractor context are the same as core signal_ids (current design).
    Rejects unknown types; used by CoreEventCandidate schema validation.

    Args:
        candidate: The event_type string to check.

    Returns:
        True if candidate is a known core signal_id; False otherwise.
    """
    from app.core_taxonomy.loader import is_valid_signal_id

    return bool(candidate) and is_valid_signal_id(candidate)
