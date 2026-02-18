"""Tests for the create_company CLI script."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.company import CompanyRead


# ── Helpers ──────────────────────────────────────────────────────────


def _make_company_read(**overrides) -> CompanyRead:
    """Create a CompanyRead for script output assertions."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1,
        company_name="Acme Corp",
        website_url="https://acme.example.com",
        founder_name="Jane Doe",
        founder_linkedin_url=None,
        company_linkedin_url=None,
        notes=None,
        source="manual",
        target_profile_match=None,
        cto_need_score=None,
        current_stage=None,
        created_at=now,
        updated_at=now,
        last_scan_at=None,
    )
    defaults.update(overrides)
    return CompanyRead(**defaults)


# ── Tests ────────────────────────────────────────────────────────────


class TestCreateCompanyScript:
    """Tests for app.scripts.create_company main()."""

    @patch("app.scripts.create_company._model_to_read")
    @patch("app.scripts.create_company.resolve_or_create_company")
    @patch("app.scripts.create_company.SessionLocal")
    def test_creates_company_with_valid_args(
        self, mock_session_local, mock_resolve, mock_model_to_read, capsys
    ) -> None:
        """Script creates company when given valid args."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_company = MagicMock()
        mock_resolve.return_value = (mock_company, True)
        mock_model_to_read.return_value = _make_company_read(
            id=42, company_name="Test Co"
        )

        from app.scripts.create_company import main

        old_argv = sys.argv
        try:
            sys.argv = ["create_company", "--company-name", "Test Co"]
            main()
            out, err = capsys.readouterr()
            assert "Test Co" in out
            assert "42" in out or "created successfully" in out.lower()
            mock_resolve.assert_called_once()
            call_args = mock_resolve.call_args[0]
            assert call_args[1].company_name == "Test Co"
        finally:
            sys.argv = old_argv

    @patch("app.scripts.create_company.resolve_or_create_company")
    @patch("app.scripts.create_company.SessionLocal")
    def test_exits_1_when_duplicate(
        self, mock_session_local, mock_resolve, capsys
    ) -> None:
        """Script exits 1 when company name already exists."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        existing = MagicMock()
        existing.id = 10
        existing.name = "Existing Co"
        mock_resolve.return_value = (existing, False)

        from app.scripts.create_company import main

        old_argv = sys.argv
        try:
            sys.argv = ["create_company", "--company-name", "Existing Co"]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
            out, err = capsys.readouterr()
            assert "already exists" in (out + err).lower()
            mock_resolve.assert_called_once()
        finally:
            sys.argv = old_argv

    @patch("app.scripts.create_company.SessionLocal")
    def test_exits_1_when_company_name_missing(self, mock_session_local, capsys) -> None:
        """Script validates required company_name."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        from app.scripts.create_company import main

        old_argv = sys.argv
        try:
            sys.argv = ["create_company"]  # Missing --company-name
            with pytest.raises(SystemExit):
                main()
            # argparse exits 2 on missing required arg, or we could catch
            # and print a friendly message and exit 1
            out, err = capsys.readouterr()
            assert "company-name" in (out + err).lower() or "required" in (out + err).lower()
        finally:
            sys.argv = old_argv

    @patch("app.scripts.create_company._model_to_read")
    @patch("app.scripts.create_company.resolve_or_create_company")
    @patch("app.scripts.create_company.SessionLocal")
    def test_passes_optional_fields(
        self, mock_session_local, mock_resolve, mock_model_to_read, capsys
    ) -> None:
        """Script passes optional fields through correctly."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_company = MagicMock()
        mock_resolve.return_value = (mock_company, True)
        mock_model_to_read.return_value = _make_company_read(
            id=1, company_name="Full Co"
        )

        from app.scripts.create_company import main

        old_argv = sys.argv
        try:
            sys.argv = [
                "create_company",
                "--company-name", "Full Co",
                "--website-url", "https://full.example.com",
                "--founder-name", "Alice",
                "--notes", "Test notes",
            ]
            main()
            mock_resolve.assert_called_once()
            data = mock_resolve.call_args[0][1]
            assert data.company_name == "Full Co"
            assert data.website_url == "https://full.example.com"
            assert data.founder_name == "Alice"
            assert data.notes == "Test notes"
        finally:
            sys.argv = old_argv
