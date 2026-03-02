"""Evidence Extractor (Issue #277): structured entity/event parsing from Evidence Bundles.

This package produces normalized entities (Company, Person) and Core Event candidates
only—no signal derivation. Distinct from app.services.extractor (HTML text extraction).
"""

from __future__ import annotations

from app.extractor.schemas import ExtractionResult, extraction_result_json_schema
from app.extractor.service import extract
from app.extractor.validation import is_valid_core_event_type

__all__ = [
    "ExtractionResult",
    "extract",
    "extraction_result_json_schema",
    "is_valid_core_event_type",
]
