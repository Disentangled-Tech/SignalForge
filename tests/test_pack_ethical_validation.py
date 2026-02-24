"""Pack ethical validation tests (Issue #190, ADR-006).

Core hard bans cannot be overridden by pack esl_policy.
"""

from __future__ import annotations

import pytest

from app.packs.ethical_constants import (
    CORE_HARD_BAN_KEYS,
    PROTECTED_ATTRIBUTE_CATEGORIES,
    validate_esl_policy_against_core_bans,
)
from app.packs.schemas import ValidationError, validate_pack_schema


def _valid_manifest() -> dict:
    return {"id": "test_pack", "version": "1", "name": "Test Pack", "schema_version": "1"}


def _valid_taxonomy() -> dict:
    return {
        "signal_ids": ["funding_raised", "cto_role_posted"],
        "dimensions": {"M": ["funding_raised"], "G": ["cto_role_posted"]},
        "labels": {"funding_raised": "New funding", "cto_role_posted": "CTO search"},
    }


def _valid_scoring() -> dict:
    return {
        "base_scores": {
            "momentum": {"funding_raised": 35},
            "leadership_gap": {"cto_role_posted": 70},
        },
        "composite_weights": {"M": 0.30, "C": 0.30, "P": 0.25, "G": 0.15},
        "caps": {"dimension_max": 100},
    }


def _valid_esl_policy() -> dict:
    return {
        "recommendation_boundaries": [[0.0, "Observe Only"], [0.7, "Standard Outreach"]],
        "svi_event_types": ["funding_raised"],
    }


def _valid_derivers() -> dict:
    return {
        "derivers": {
            "passthrough": [
                {"event_type": "funding_raised", "signal_id": "funding_raised"},
                {"event_type": "cto_role_posted", "signal_id": "cto_role_posted"},
            ]
        }
    }


def _valid_playbooks() -> dict:
    return {"ore_outreach": {"pattern_frames": {"momentum": "test"}, "ctas": ["CTA"]}}


class TestCoreHardBansCannotBeOverridden:
    """Pack esl_policy cannot set core ban override keys to true."""

    def test_allow_protected_attribute_targeting_raises(self) -> None:
        """esl_policy with allow_protected_attribute_targeting=true fails."""
        esl_policy = {**_valid_esl_policy(), "allow_protected_attribute_targeting": True}
        with pytest.raises(ValidationError, match="core ban|allow_protected_attribute_targeting"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=esl_policy,
                derivers=_valid_derivers(),
                playbooks=_valid_playbooks(),
            )

    def test_allow_bankruptcy_exploitation_raises(self) -> None:
        """esl_policy with allow_bankruptcy_exploitation=true fails."""
        esl_policy = {**_valid_esl_policy(), "allow_bankruptcy_exploitation": True}
        with pytest.raises(ValidationError, match="core ban|allow_bankruptcy_exploitation"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=esl_policy,
                derivers=_valid_derivers(),
                playbooks=_valid_playbooks(),
            )

    def test_allow_vulnerability_targeting_raises(self) -> None:
        """esl_policy with allow_vulnerability_targeting=true fails."""
        esl_policy = {**_valid_esl_policy(), "allow_vulnerability_targeting": True}
        with pytest.raises(ValidationError, match="core ban|allow_vulnerability_targeting"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=esl_policy,
                derivers=_valid_derivers(),
                playbooks=_valid_playbooks(),
            )

    def test_allow_distress_surfacing_raises(self) -> None:
        """esl_policy with allow_distress_surfacing=true fails."""
        esl_policy = {**_valid_esl_policy(), "allow_distress_surfacing": True}
        with pytest.raises(ValidationError, match="core ban|allow_distress_surfacing"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=esl_policy,
                derivers=_valid_derivers(),
                playbooks=_valid_playbooks(),
            )

    def test_ban_key_false_allowed(self) -> None:
        """esl_policy with override key=false is allowed (explicit opt-out)."""
        esl_policy = {**_valid_esl_policy(), "allow_protected_attribute_targeting": False}
        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=esl_policy,
            derivers=_valid_derivers(),
            playbooks=_valid_playbooks(),
        )

    def test_ban_key_absent_allowed(self) -> None:
        """esl_policy without override keys passes (default restrictive)."""
        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=_valid_esl_policy(),
            derivers=_valid_derivers(),
            playbooks=_valid_playbooks(),
        )


class TestValidateEslPolicyAgainstCoreBansDirect:
    """Direct validation of validate_esl_policy_against_core_bans."""

    def test_empty_esl_policy_passes(self) -> None:
        """Empty esl_policy passes."""
        validate_esl_policy_against_core_bans({})

    def test_non_dict_passes(self) -> None:
        """Non-dict esl_policy is ignored (no-op)."""
        validate_esl_policy_against_core_bans(None)  # type: ignore[arg-type]
        validate_esl_policy_against_core_bans([])  # type: ignore[arg-type]

    def test_integer_one_rejected(self) -> None:
        """esl_policy with allow_*=1 (YAML integer) is rejected (no bypass)."""
        with pytest.raises(ValidationError, match="core ban|allow_protected_attribute_targeting"):
            validate_esl_policy_against_core_bans(
                {"allow_protected_attribute_targeting": 1}
            )


class TestEthicalConstantsExports:
    """Constants are exported for reference."""

    def test_core_hard_ban_keys_non_empty(self) -> None:
        """CORE_HARD_BAN_KEYS contains expected ban keys."""
        assert "allow_protected_attribute_targeting" in CORE_HARD_BAN_KEYS
        assert "allow_bankruptcy_exploitation" in CORE_HARD_BAN_KEYS
        assert len(CORE_HARD_BAN_KEYS) >= 4

    def test_protected_attribute_categories_non_empty(self) -> None:
        """PROTECTED_ATTRIBUTE_CATEGORIES contains expected categories."""
        assert "race" in PROTECTED_ATTRIBUTE_CATEGORIES
        assert "gender" in PROTECTED_ATTRIBUTE_CATEGORIES
