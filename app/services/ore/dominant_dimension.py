"""Dominant TRS dimension for ORE strategy selection (Issue #117).

Pure helper: given M, C, P, G scores, returns the dominant dimension name.
Tie-break order (ORE design): momentum > complexity > pressure > leadership_gap.

Callers (ore_pipeline) pass snapshot dimension scores (0–100). Out-of-range values
are not validated here; behavior is defined by max(scores) and tie-break order.
"""

from __future__ import annotations

# Tie-break order when scores are equal (M > C > P > G per plan).
_DIMENSION_ORDER = ("momentum", "complexity", "pressure", "leadership_gap")


def get_dominant_trs_dimension(
    momentum: int,
    complexity: int,
    pressure: int,
    leadership_gap: int,
) -> str:
    """Return the TRS dimension with the highest score.

    Args:
        momentum: Momentum dimension score (0–100).
        complexity: Complexity dimension score (0–100).
        pressure: Pressure dimension score (0–100).
        leadership_gap: Leadership gap dimension score (0–100).

    Returns:
        One of "momentum", "complexity", "pressure", "leadership_gap".
        Tie-break order: momentum > complexity > pressure > leadership_gap.
    """
    scores = {
        "momentum": momentum,
        "complexity": complexity,
        "pressure": pressure,
        "leadership_gap": leadership_gap,
    }
    max_score = max(scores.values())
    for dim in _DIMENSION_ORDER:
        if scores[dim] == max_score:
            return dim
    return _DIMENSION_ORDER[0]  # fallback (all equal)
