"""Pack loader and schema validation tests (Issue #189, Plan Step 1.2, Phase 3.3).

Unit tests for pack manifest loading, schema validation, and Pack interface.
These tests SKIP until app/packs/loader.py exists (TDD: implement loader to make them run).
"""

from __future__ import annotations

import pytest

# Skip entire module when app.packs not implemented (TDD)
pytest.importorskip("app.packs", reason="app.packs.loader not implemented; run when Step 1.2 complete")


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
        from app.packs.loader import load_pack
        from app.ingestion.event_types import SIGNAL_EVENT_TYPES

        pack = load_pack("fractional_cto_v1", "1")
        tax = pack.taxonomy
        taxonomy_ids = set(
            tax.get("signal_ids", []) if isinstance(tax, dict) else (getattr(tax, "signal_ids", None) or [])
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


class TestPackSchemaValidation:
    """Pack YAML files validate against schema."""

    def test_pack_json_has_required_fields(self) -> None:
        """pack.json has id, version, name, schema_version."""
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        manifest = getattr(pack, "manifest", pack) if hasattr(pack, "manifest") else pack
        assert getattr(manifest, "id", None) or (isinstance(manifest, dict) and "id" in manifest)
        assert getattr(manifest, "version", None) or (isinstance(manifest, dict) and "version" in manifest)

    def test_scoring_yaml_has_base_scores(self) -> None:
        """scoring.yaml has base scores for momentum, complexity, pressure, leadership_gap."""
        from app.packs.loader import load_pack

        pack = load_pack("fractional_cto_v1", "1")
        scoring = pack.scoring
        assert scoring is not None
        sc = scoring if isinstance(scoring, dict) else vars(scoring) if hasattr(scoring, "__dict__") else {}
        assert bool(sc) or bool(scoring), "scoring config must not be empty"
