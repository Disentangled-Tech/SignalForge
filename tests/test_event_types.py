"""Tests for canonical event types (Issue #244, Phase 1)."""

from __future__ import annotations

from app.ingestion.event_types import is_valid_event_type


class TestRepoActivityIsValidEventType:
    """repo_activity is a core event type."""

    def test_repo_activity_is_valid_event_type(self) -> None:
        """is_valid_event_type('repo_activity') returns True."""
        assert is_valid_event_type("repo_activity") is True


class TestIncorporationIsValidEventType:
    """incorporation is a core event type (Issue #250)."""

    def test_incorporation_is_valid_event_type(self) -> None:
        """is_valid_event_type('incorporation') returns True."""
        assert is_valid_event_type("incorporation") is True
