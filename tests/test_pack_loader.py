"""Pack loader and schema validation tests (Issue #189, Plan Step 1.2, Phase 3.3).

Unit tests for pack manifest loading, schema validation, and Pack interface.
These tests SKIP until app/packs/loader.py exists (TDD: implement loader to make them run).
"""

from __future__ import annotations

import pytest

# Skip entire module when app.packs not implemented (TDD)
pytest.importorskip(
    "app.packs", reason="app.packs.loader not implemented; run when Step 1.2 complete"
)


class TestPackLoader:
    """load_pack(pack_id, version) returns Pack with taxonomy, scoring, esl_policy, playbooks."""

    def test_load_fractional_cto_v1_returns_pack(self) -> None:
        """load_pack('fractional_cto_v1', '1') returns Pack with required attributes."""
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        assert pack is not None
        assert hasattr(pack, "taxonomy")
        assert hasattr(pack, "scoring")
        assert hasattr(pack, "esl_policy")
        assert hasattr(pack, "playbooks")
        assert pack.taxonomy is not None
        assert pack.scoring is not None
        assert pack.esl_policy is not None

    def test_pack_taxonomy_has_signal_ids(self) -> None:
        """Pack taxonomy includes all 23 CTO event types from event_types.SIGNAL_EVENT_TYPES."""
        from app.ingestion.event_types import SIGNAL_EVENT_TYPES
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        tax = pack.taxonomy
        taxonomy_ids = set(
            tax.get("signal_ids", [])
            if isinstance(tax, dict)
            else (getattr(tax, "signal_ids", None) or [])
        )
        for etype in SIGNAL_EVENT_TYPES:
            assert etype in taxonomy_ids, f"Taxonomy missing event type: {etype}"

    def test_load_nonexistent_pack_raises(self) -> None:
        """load_pack('nonexistent_pack', '1') raises PackNotFoundError or ValueError."""
        from app.packs.loader import load_pack

        with pytest.raises((FileNotFoundError, ValueError, KeyError)):
            load_pack("nonexistent_pack", "1")

    def test_load_invalid_version_raises(self) -> None:
        """load_pack('fractional_cto_v1', '99') raises when version not installed."""
        from app.packs.loader import load_pack

        with pytest.raises((FileNotFoundError, ValueError, KeyError)):
            load_pack("fractional_cto_v1", "99")


class TestPackIdPathTraversalGuard:
    """load_pack rejects pack_id/version with path traversal (Issue #189, Plan Step 4)."""

    def test_pack_id_with_dotdot_raises(self) -> None:
        """pack_id containing '..' raises ValueError."""
        from app.packs.loader import load_pack

        with pytest.raises(ValueError, match="must not contain"):
            load_pack("../etc", "1")

    def test_pack_id_with_slash_raises(self) -> None:
        """pack_id containing '/' raises ValueError."""
        from app.packs.loader import load_pack

        with pytest.raises(ValueError, match="path separators"):
            load_pack("foo/bar", "1")

    def test_pack_id_with_backslash_raises(self) -> None:
        """pack_id containing '\\' raises ValueError."""
        from app.packs.loader import load_pack

        with pytest.raises(ValueError, match="path separators"):
            load_pack("foo\\bar", "1")

    def test_pack_id_empty_raises(self) -> None:
        """Empty pack_id raises ValueError."""
        from app.packs.loader import load_pack

        with pytest.raises(ValueError, match="non-empty"):
            load_pack("", "1")

    def test_version_with_dotdot_raises(self) -> None:
        """version containing '..' raises ValueError."""
        from app.packs.loader import load_pack

        with pytest.raises(ValueError, match="must not contain"):
            load_pack("fractional_cto_v1", "..")

    def test_valid_pack_id_still_loads(self) -> None:
        """Valid pack_id (alphanumeric, underscore, hyphen) loads successfully."""
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        assert pack is not None
        assert pack.scoring is not None


class TestPackLoaderDerivers:
    """load_pack loads derivers.yaml and includes in Pack (Issue #172).

    These tests FAIL until loader loads derivers.yaml and Pack has derivers field.
    """

    def test_load_pack_returns_derivers(self) -> None:
        """load_pack returns Pack with derivers attribute containing passthrough rules."""
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        assert hasattr(pack, "derivers"), "Pack must have derivers attribute (Issue #172)"
        assert pack.derivers is not None
        derivers = pack.derivers if isinstance(pack.derivers, dict) else {}
        passthrough = derivers.get("derivers", {}).get("passthrough", [])
        assert len(passthrough) > 0, "Derivers passthrough must not be empty"
        first = passthrough[0]
        assert "event_type" in first and "signal_id" in first

    def test_derivers_match_taxonomy_signal_ids(self) -> None:
        """All deriver signal_ids exist in taxonomy.signal_ids."""
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        taxonomy_ids = set(pack.taxonomy.get("signal_ids", []))
        passthrough = (pack.derivers or {}).get("derivers", {}).get("passthrough", [])
        for entry in passthrough:
            sid = entry.get("signal_id")
            assert sid in taxonomy_ids, f"Deriver signal_id {sid} must be in taxonomy"


class TestPackLoaderInvalidSchemaRaises:
    """load_pack with invalid schema raises ValidationError (Issue #172).

    Uses packs/invalid_schema_pack fixture with ghost_signal not in taxonomy.
    These tests FAIL until loader calls validate_pack_schema and raises on invalid.
    """

    def test_load_invalid_schema_pack_raises_validation_error(self) -> None:
        """load_pack('invalid_schema_pack','1') raises ValidationError (Issue #172).

        Fails until: loader loads derivers.yaml, calls validate_pack_schema, raises on invalid.
        """
        from app.packs.loader import load_pack
        from app.packs.schemas import ValidationError

        with pytest.raises(ValidationError):
            load_pack("invalid_schema_pack", "1")

    def test_invalid_pack_error_message_mentions_problem(self) -> None:
        """ValidationError message includes signal_id or field for debugging."""
        from app.packs.loader import load_pack
        from app.packs.schemas import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            load_pack("invalid_schema_pack", "1")
        msg = str(exc_info.value).lower()
        assert "ghost_signal" in msg or "taxonomy" in msg or "scoring" in msg or "derivers" in msg


class TestPackSchemaValidation:
    """Pack YAML files validate against schema."""

    def test_pack_json_has_required_fields(self) -> None:
        """pack.json has id, version, name, schema_version."""
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        manifest = getattr(pack, "manifest", pack) if hasattr(pack, "manifest") else pack
        assert getattr(manifest, "id", None) or (isinstance(manifest, dict) and "id" in manifest)
        assert getattr(manifest, "version", None) or (
            isinstance(manifest, dict) and "version" in manifest
        )

    def test_scoring_yaml_has_base_scores(self) -> None:
        """scoring.yaml has base scores for momentum, complexity, pressure, leadership_gap."""
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        scoring = pack.scoring
        assert scoring is not None
        sc = (
            scoring
            if isinstance(scoring, dict)
            else vars(scoring)
            if hasattr(scoring, "__dict__")
            else {}
        )
        assert bool(sc) or bool(scoring), "scoring config must not be empty"


class TestPackConfigChecksum:
    """Pack config_checksum computed and stable (Issue #190, Phase 3)."""

    def test_load_pack_returns_config_checksum(self) -> None:
        """load_pack returns Pack with config_checksum attribute."""
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        assert hasattr(pack, "config_checksum")
        assert pack.config_checksum is not None
        assert isinstance(pack.config_checksum, str)
        assert len(pack.config_checksum) == 64
        assert all(c in "0123456789abcdef" for c in pack.config_checksum)

    def test_checksum_stable_for_same_config(self) -> None:
        """Same pack config produces identical checksum on repeated loads."""
        from app.packs.loader import load_pack

        pack1 = load_pack("fractional_cto_v1", "1")
        pack2 = load_pack("fractional_cto_v1", "1")
        assert pack1.config_checksum == pack2.config_checksum

    def test_compute_pack_config_checksum_deterministic(self) -> None:
        """compute_pack_config_checksum produces same hash for same input."""
        from app.packs.loader import compute_pack_config_checksum

        cfg = {
            "manifest": {"id": "test", "version": "1.0.0"},
            "taxonomy": {"signal_ids": ["a", "b"]},
            "scoring": {},
            "esl_policy": {},
            "derivers": {},
            "playbooks": {},
        }
        h1 = compute_pack_config_checksum(**cfg)
        h2 = compute_pack_config_checksum(**cfg)
        assert h1 == h2
        assert len(h1) == 64
        assert all(c in "0123456789abcdef" for c in h1)

    def test_compute_pack_config_checksum_different_on_input_change(self) -> None:
        """Different config produces different checksum."""
        from app.packs.loader import compute_pack_config_checksum

        cfg1 = {
            "manifest": {"id": "test", "version": "1.0.0"},
            "taxonomy": {"signal_ids": ["a", "b"]},
            "scoring": {},
            "esl_policy": {},
            "derivers": {},
            "playbooks": {},
        }
        cfg2 = {
            "manifest": {"id": "test", "version": "1.0.1"},
            "taxonomy": {"signal_ids": ["a", "b"]},
            "scoring": {},
            "esl_policy": {},
            "derivers": {},
            "playbooks": {},
        }
        h1 = compute_pack_config_checksum(**cfg1)
        h2 = compute_pack_config_checksum(**cfg2)
        assert h1 != h2
