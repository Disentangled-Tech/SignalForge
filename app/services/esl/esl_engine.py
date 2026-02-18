"""ESL engine — OutreachScore and recommendation type caps (Issue #124).

OutreachScore = round(trs * esl) when ESL (stability modifier) is 0–1.
"""

from __future__ import annotations


def compute_outreach_score(trs: int, stability_modifier: float) -> int:
    """Compute OutreachScore from TRS and stability modifier (ESL).

    Args:
        trs: Total Readiness Score (0–100).
        stability_modifier: ESL factor 0–1 (e.g. 0.5 for high pressure).

    Returns:
        round(trs * stability_modifier), e.g. TRS=82, SM=0.5 → 41.
    """
    return round(trs * stability_modifier)
