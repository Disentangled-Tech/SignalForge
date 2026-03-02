"""Evidence Extractor (Issue #277): structured entity/event parsing from Evidence Bundles.

This package produces normalized entities (Company, Person) and Core Event candidates
only—no signal derivation. Distinct from app.services.extractor (HTML text extraction).
"""

from __future__ import annotations

from app.extractor.validation import is_valid_core_event_type

__all__ = ["is_valid_core_event_type"]
