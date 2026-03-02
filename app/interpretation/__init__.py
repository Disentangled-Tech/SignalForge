"""LLM Event Interpretation (Issue #281).

Schema and contract for classifying raw content into CoreEvent candidates.
LLM module: interpret_to_core_events (M3).
"""

from app.interpretation.llm import interpret_to_core_events
from app.interpretation.schemas import (
    InterpretationInput,
    InterpretationOutput,
    InterpretationOutputItem,
)

__all__ = [
    "InterpretationInput",
    "InterpretationOutput",
    "InterpretationOutputItem",
    "interpret_to_core_events",
]
