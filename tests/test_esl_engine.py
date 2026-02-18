"""ESL engine unit tests (Issue #124)."""

from __future__ import annotations

import pytest

from app.services.esl.esl_engine import compute_outreach_score


def test_outreach_score_trs_82_sm_05() -> None:
    """TRS=82, SM=0.5 → OutreachScore=41."""
    assert compute_outreach_score(82, 0.5) == 41


def test_outreach_score_trs_100_sm_1() -> None:
    """TRS=100, SM=1.0 → OutreachScore=100."""
    assert compute_outreach_score(100, 1.0) == 100


def test_outreach_score_trs_50_sm_07() -> None:
    """TRS=50, SM=0.7 → OutreachScore=35."""
    assert compute_outreach_score(50, 0.7) == 35


def test_outreach_score_rounds() -> None:
    """Fractional results are rounded."""
    assert compute_outreach_score(33, 0.5) == 16  # 16.5 → 16
    assert compute_outreach_score(33, 0.6) == 20  # 19.8 → 20


def test_outreach_score_zero_sm() -> None:
    """SM=0 → OutreachScore=0."""
    assert compute_outreach_score(82, 0.0) == 0
