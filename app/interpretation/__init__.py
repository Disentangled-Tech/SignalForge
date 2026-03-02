"""LLM Event Interpretation (Issue #281).

Schema and contract for classifying raw content into CoreEvent candidates.
M3: interpret_to_core_events(content, evidence). M4 Scout: interpret_bundle_to_core_events(bundle).
"""

from app.interpretation.llm import (
    interpret_bundle_to_core_events,
    interpret_to_core_events,
)
from app.interpretation.schemas import (
    InterpretationInput,
    InterpretationOutput,
    InterpretationOutputItem,
)

__all__ = [
    "InterpretationInput",
    "InterpretationOutput",
    "InterpretationOutputItem",
    "interpret_bundle_to_core_events",
    "interpret_to_core_events",
]
