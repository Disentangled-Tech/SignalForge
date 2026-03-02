"""LLM Event Interpretation (Issue #281).

Schema and contract for classifying raw content into CoreEvent candidates.
No LLM call in this package; see interpretation schemas and (later) llm module.
"""

from app.interpretation.schemas import (
    InterpretationInput,
    InterpretationOutput,
    InterpretationOutputItem,
)

__all__ = [
    "InterpretationInput",
    "InterpretationOutput",
    "InterpretationOutputItem",
]
