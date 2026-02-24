"""Tests for validate_all_packs CLI (Issue #190, Phase 4)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("app.packs", reason="app.packs not implemented")


class TestValidateAllPacksCLI:
    """validate_all_packs() returns 0 when all packs validate."""

    def test_validate_all_packs_returns_zero_when_valid(self) -> None:
        """validate_all_packs returns 0 when fractional_cto_v1 validates (invalid_schema_pack excluded)."""
        from app.packs.validate_all_packs import validate_all_packs

        exit_code = validate_all_packs()
        assert exit_code == 0

    def test_exclude_pack_ids_contains_invalid_schema_pack(self) -> None:
        """invalid_schema_pack is excluded from CI validation (test fixture)."""
        from app.packs.validate_all_packs import EXCLUDE_PACK_IDS

        assert "invalid_schema_pack" in EXCLUDE_PACK_IDS

    def test_validate_all_packs_returns_one_when_packs_dir_missing(self) -> None:
        """validate_all_packs returns 1 when packs directory does not exist."""
        from app.packs import validate_all_packs as validate_module

        with patch.object(validate_module, "_packs_root", return_value=Path("/nonexistent/packs")):
            exit_code = validate_module.validate_all_packs()
        assert exit_code == 1

    def test_validate_all_packs_returns_one_when_pack_fails_validation(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """validate_all_packs returns 1 when a pack fails ValidationError (exclude list bypassed)."""
        from app.packs import validate_all_packs as validate_module

        with patch.object(
            validate_module, "EXCLUDE_PACK_IDS", frozenset()
        ), patch.object(
            validate_module, "_packs_root", return_value=Path(__file__).parent.parent / "packs"
        ):
            exit_code = validate_module.validate_all_packs()
        assert exit_code == 1
        err = capsys.readouterr().err
        assert "FAIL:" in err or "failed" in err.lower()

    def test_validate_all_packs_returns_one_when_pack_json_missing_id(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """validate_all_packs returns 1 when pack.json has no id."""
        from app.packs import validate_all_packs as validate_module

        bad_pack_dir = tmp_path / "bad_pack"
        bad_pack_dir.mkdir()
        (bad_pack_dir / "pack.json").write_text(json.dumps({"version": "1", "name": "Bad"}))
        with patch.object(validate_module, "_packs_root", return_value=tmp_path):
            exit_code = validate_module.validate_all_packs()
        assert exit_code == 1
        assert "missing id or version" in capsys.readouterr().err

    def test_main_exits_with_validate_all_packs_return_code(self) -> None:
        """main() calls sys.exit with validate_all_packs return value."""
        from app.packs.validate_all_packs import main, validate_all_packs

        with patch("app.packs.validate_all_packs.validate_all_packs", return_value=0):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        with patch("app.packs.validate_all_packs.validate_all_packs", return_value=1):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
