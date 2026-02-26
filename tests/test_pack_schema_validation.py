"""Pack schema validation unit tests (Issue #172).

Tests for validate_pack_schema and ValidationError.
These tests FAIL until app/packs/schemas.py is implemented (TDD red phase).
"""

from __future__ import annotations

import pytest


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


class TestValidatePackSchemaHappyPath:
    """Valid pack config passes validation."""

    def test_valid_full_pack_passes(self) -> None:
        """validate_pack_schema with all valid config does not raise."""
        from app.packs.schemas import validate_pack_schema

        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=_valid_esl_policy(),
            derivers=_valid_derivers(),
            playbooks=_valid_playbooks(),
        )
        # No exception

    def test_valid_minimal_pack_passes(self) -> None:
        """validate_pack_schema with minimal required structure passes."""
        from app.packs.schemas import validate_pack_schema

        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy={"signal_ids": ["funding_raised"]},
            scoring={"base_scores": {"momentum": {"funding_raised": 35}}},
            esl_policy={},
            derivers={"derivers": {"passthrough": [{"event_type": "funding_raised", "signal_id": "funding_raised"}]}},
            playbooks={},
        )


class TestValidatePackSchemaManifest:
    """Manifest required fields and format."""

    def test_missing_id_raises(self) -> None:
        """Manifest without 'id' raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        manifest = {"version": "1", "name": "Test", "schema_version": "1"}
        with pytest.raises(ValidationError, match="id|required"):
            validate_pack_schema(
                manifest=manifest,
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_missing_version_raises(self) -> None:
        """Manifest without 'version' raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        manifest = {"id": "test", "name": "Test", "schema_version": "1"}
        with pytest.raises(ValidationError, match="version|required"):
            validate_pack_schema(
                manifest=manifest,
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_missing_name_raises(self) -> None:
        """Manifest without 'name' raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        manifest = {"id": "test", "version": "1", "schema_version": "1"}
        with pytest.raises(ValidationError, match="name|required"):
            validate_pack_schema(
                manifest=manifest,
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_empty_manifest_raises(self) -> None:
        """Empty manifest raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        with pytest.raises(ValidationError):
            validate_pack_schema(
                manifest={},
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_manifest_without_schema_version_passes(self) -> None:
        """Manifest with only id, version, name passes (schema_version optional, default "1")."""
        from app.packs.schemas import get_schema_version, validate_pack_schema

        manifest = {"id": "test_pack", "version": "1", "name": "Test Pack"}
        assert get_schema_version(manifest) == "1"
        validate_pack_schema(
            manifest=manifest,
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=_valid_esl_policy(),
            derivers=_valid_derivers(),
            playbooks={},
        )

    def test_manifest_with_schema_version_2_passes(self) -> None:
        """Manifest with schema_version "2" passes (M1: no validation change)."""
        from app.packs.schemas import get_schema_version, validate_pack_schema

        manifest = {"id": "test_pack", "version": "1", "name": "Test Pack", "schema_version": "2"}
        assert get_schema_version(manifest) == "2"
        validate_pack_schema(
            manifest=manifest,
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=_valid_esl_policy(),
            derivers=_valid_derivers(),
            playbooks={},
        )

    def test_manifest_with_empty_schema_version_raises(self) -> None:
        """Manifest with schema_version present but empty raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        for bad_value in ("", "   "):
            manifest = {
                "id": "test_pack",
                "version": "1",
                "name": "Test Pack",
                "schema_version": bad_value,
            }
            with pytest.raises(ValidationError, match="schema_version|non-empty"):
                validate_pack_schema(
                    manifest=manifest,
                    taxonomy=_valid_taxonomy(),
                    scoring=_valid_scoring(),
                    esl_policy=_valid_esl_policy(),
                    derivers=_valid_derivers(),
                    playbooks={},
                )


class TestValidatePackSchemaTaxonomy:
    """Taxonomy structure and signal_ids."""

    def test_missing_signal_ids_raises(self) -> None:
        """Taxonomy without signal_ids raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        taxonomy = {"dimensions": {"M": ["funding_raised"]}}
        with pytest.raises(ValidationError, match="signal_ids|taxonomy"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=taxonomy,
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_empty_signal_ids_raises(self) -> None:
        """Taxonomy with empty signal_ids raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        taxonomy = {"signal_ids": []}
        with pytest.raises(ValidationError, match="signal_ids|empty"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=taxonomy,
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )


class TestValidatePackSchemaScoringCrossRef:
    """Scoring base_scores must reference taxonomy.signal_ids."""

    def test_scoring_references_unknown_signal_raises(self) -> None:
        """Scoring base_scores with signal not in taxonomy raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        scoring = {
            "base_scores": {
                "momentum": {"funding_raised": 35, "ghost_signal": 10},
                "leadership_gap": {"cto_role_posted": 70},
            },
            "composite_weights": {"M": 0.30, "C": 0.30, "P": 0.25, "G": 0.15},
        }
        with pytest.raises(ValidationError, match="ghost_signal|taxonomy|scoring"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=scoring,
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_scoring_dimension_with_all_invalid_signals_raises(self) -> None:
        """Scoring dimension with no valid taxonomy ref raises."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        scoring = {
            "base_scores": {
                "momentum": {"unknown_signal": 35},
                "leadership_gap": {"cto_role_posted": 70},
            },
            "composite_weights": {"M": 0.30, "C": 0.30, "P": 0.25, "G": 0.15},
        }
        with pytest.raises(ValidationError):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=scoring,
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )


class TestValidatePackSchemaScoringDecayAndSuppressors:
    """Scoring decay and suppressors structure when present (Issue #174)."""

    def test_decay_momentum_non_dict_raises(self) -> None:
        """decay.momentum must be dict when decay present."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        scoring = {
            **_valid_scoring(),
            "decay": {"momentum": "not_a_dict"},
        }
        with pytest.raises(ValidationError, match="decay|momentum|dict"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=scoring,
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_decay_invalid_value_type_raises(self) -> None:
        """decay values must be numeric."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        scoring = {
            **_valid_scoring(),
            "decay": {"momentum": {"0-30": "one"}},
        }
        with pytest.raises(ValidationError, match="numeric"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=scoring,
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_suppressors_negative_value_raises(self) -> None:
        """suppressors values must be non-negative."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        scoring = {
            **_valid_scoring(),
            "suppressors": {"cto_hired_60_days": -1},
        }
        with pytest.raises(ValidationError, match="non-negative"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=scoring,
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_valid_decay_and_suppressors_passes(self) -> None:
        """Valid decay and suppressors pass validation."""
        from app.packs.schemas import validate_pack_schema

        scoring = {
            **_valid_scoring(),
            "decay": {
                "momentum": {"0-30": 1.0, "31-60": 0.7, "91+": 0.0},
            },
            "suppressors": {"cto_hired_60_days": 70, "cto_hired_180_days": 50},
        }
        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=scoring,
            esl_policy=_valid_esl_policy(),
            derivers=_valid_derivers(),
            playbooks={},
        )


class TestValidatePackSchemaDeriversPattern:
    """Pattern derivers: pattern/regex required, signal_id in taxonomy, source_fields whitelist."""

    def test_pattern_missing_pattern_and_regex_raises(self) -> None:
        """Pattern deriver without pattern or regex raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        taxonomy = {**_valid_taxonomy(), "signal_ids": ["funding_raised", "cto_role_posted", "compliance_mentioned"]}
        scoring = {
            "base_scores": {
                "momentum": {"funding_raised": 35},
                "leadership_gap": {"cto_role_posted": 70, "compliance_mentioned": 20},
            },
            "composite_weights": {"M": 0.30, "C": 0.30, "P": 0.25, "G": 0.15},
            "caps": {"dimension_max": 100},
        }
        derivers = {
            "derivers": {
                "passthrough": [{"event_type": "funding_raised", "signal_id": "funding_raised"}],
                "pattern": [
                    {"signal_id": "compliance_mentioned", "source_fields": ["title", "summary"]},
                ],
            }
        }
        with pytest.raises(ValidationError, match="pattern|regex"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=taxonomy,
                scoring=scoring,
                esl_policy=_valid_esl_policy(),
                derivers=derivers,
                playbooks={},
            )

    def test_pattern_signal_id_not_in_taxonomy_raises(self) -> None:
        """Pattern deriver with signal_id not in taxonomy raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        derivers = {
            "derivers": {
                "pattern": [
                    {
                        "signal_id": "ghost_signal",
                        "pattern": r"(?i)compliance",
                        "source_fields": ["title", "summary"],
                    },
                ],
            }
        }
        with pytest.raises(ValidationError, match="ghost_signal|taxonomy"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=derivers,
                playbooks={},
            )

    def test_pattern_source_fields_disallowed_raises(self) -> None:
        """Pattern deriver with disallowed source_fields raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        taxonomy = {**_valid_taxonomy(), "signal_ids": ["funding_raised", "cto_role_posted", "compliance_mentioned"]}
        scoring = {
            "base_scores": {
                "momentum": {"funding_raised": 35},
                "leadership_gap": {"cto_role_posted": 70, "compliance_mentioned": 20},
            },
            "composite_weights": {"M": 0.30, "C": 0.30, "P": 0.25, "G": 0.15},
            "caps": {"dimension_max": 100},
        }
        derivers = {
            "derivers": {
                "pattern": [
                    {
                        "signal_id": "compliance_mentioned",
                        "pattern": r"(?i)compliance",
                        "source_fields": ["title", "raw"],
                    },
                ],
            }
        }
        with pytest.raises(ValidationError, match="raw|not allowed"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=taxonomy,
                scoring=scoring,
                esl_policy=_valid_esl_policy(),
                derivers=derivers,
                playbooks={},
            )

    def test_pattern_source_fields_allowed_passes(self) -> None:
        """Pattern deriver with allowed source_fields passes."""
        from app.packs.schemas import validate_pack_schema

        taxonomy = {**_valid_taxonomy(), "signal_ids": ["funding_raised", "cto_role_posted", "compliance_mentioned"]}
        scoring = {
            "base_scores": {
                "momentum": {"funding_raised": 35},
                "leadership_gap": {"cto_role_posted": 70, "compliance_mentioned": 20},
            },
            "composite_weights": {"M": 0.30, "C": 0.30, "P": 0.25, "G": 0.15},
            "caps": {"dimension_max": 100},
        }
        derivers = {
            "derivers": {
                "passthrough": [{"event_type": "funding_raised", "signal_id": "funding_raised"}],
                "pattern": [
                    {
                        "signal_id": "compliance_mentioned",
                        "pattern": r"(?i)compliance",
                        "source_fields": ["title", "summary", "url", "source"],
                    },
                ],
            }
        }
        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=taxonomy,
            scoring=scoring,
            esl_policy=_valid_esl_policy(),
            derivers=derivers,
            playbooks={},
        )


class TestValidatePackSchemaDeriversCrossRef:
    """Derivers passthrough signal_id must be in taxonomy."""

    def test_deriver_signal_id_not_in_taxonomy_raises(self) -> None:
        """Deriver passthrough with signal_id not in taxonomy raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        derivers = {
            "derivers": {
                "passthrough": [
                    {"event_type": "funding_raised", "signal_id": "funding_raised"},
                    {"event_type": "ghost_event", "signal_id": "ghost_signal"},
                ]
            }
        }
        with pytest.raises(ValidationError, match="ghost_signal|derivers|taxonomy"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=derivers,
                playbooks={},
            )

    def test_deriver_missing_signal_id_raises(self) -> None:
        """Deriver passthrough entry without signal_id raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        derivers = {
            "derivers": {
                "passthrough": [
                    {"event_type": "funding_raised"},
                ]
            }
        }
        with pytest.raises(ValidationError, match="signal_id|derivers"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=derivers,
                playbooks={},
            )


class TestValidatePackSchemaEslPolicy:
    """ESL policy svi_event_types must reference valid signals."""

    def test_svi_event_types_reference_unknown_signal_raises(self) -> None:
        """ESL svi_event_types with signal not in taxonomy raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        esl_policy = {
            "recommendation_boundaries": [[0.0, "Observe Only"]],
            "svi_event_types": ["funding_raised", "unknown_stress_signal"],
        }
        with pytest.raises(ValidationError, match="unknown_stress_signal|svi_event_types|taxonomy"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=esl_policy,
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_empty_svi_event_types_allowed(self) -> None:
        """ESL with empty svi_event_types is allowed (optional)."""
        from app.packs.schemas import validate_pack_schema

        esl_policy = {"recommendation_boundaries": [[0.0, "Observe Only"]], "svi_event_types": []}
        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=esl_policy,
            derivers=_valid_derivers(),
            playbooks={},
        )


class TestValidatePackSchemaEslPolicyIssue175:
    """ESL policy Issue #175: blocked_signals, sensitivity_mapping, prohibited_combinations, downgrade_rules."""

    def test_blocked_signals_unknown_signal_raises(self) -> None:
        """blocked_signals with signal not in taxonomy raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        esl_policy = {
            **_valid_esl_policy(),
            "blocked_signals": ["ghost_signal"],
        }
        with pytest.raises(ValidationError, match="blocked_signals|ghost_signal|taxonomy"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=esl_policy,
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_blocked_signals_valid_passes(self) -> None:
        """blocked_signals with valid taxonomy refs passes."""
        from app.packs.schemas import validate_pack_schema

        esl_policy = {
            **_valid_esl_policy(),
            "blocked_signals": ["funding_raised"],
        }
        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=esl_policy,
            derivers=_valid_derivers(),
            playbooks={},
        )

    def test_sensitivity_mapping_unknown_signal_raises(self) -> None:
        """sensitivity_mapping with key not in taxonomy raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        esl_policy = {
            **_valid_esl_policy(),
            "sensitivity_mapping": {"ghost_signal": "high"},
        }
        with pytest.raises(ValidationError, match="sensitivity_mapping|ghost_signal|taxonomy"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=esl_policy,
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_prohibited_combinations_unknown_signal_raises(self) -> None:
        """prohibited_combinations with signal not in taxonomy raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        esl_policy = {
            **_valid_esl_policy(),
            "prohibited_combinations": [["funding_raised", "ghost_signal"]],
        }
        with pytest.raises(ValidationError, match="prohibited_combinations|ghost_signal|taxonomy"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=esl_policy,
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_prohibited_combinations_valid_passes(self) -> None:
        """prohibited_combinations with valid pairs passes."""
        from app.packs.schemas import validate_pack_schema

        esl_policy = {
            **_valid_esl_policy(),
            "prohibited_combinations": [["funding_raised", "cto_role_posted"]],
        }
        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=esl_policy,
            derivers=_valid_derivers(),
            playbooks={},
        )

    def test_downgrade_rules_unknown_trigger_raises(self) -> None:
        """downgrade_rules with trigger_signal not in taxonomy raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        esl_policy = {
            **_valid_esl_policy(),
            "downgrade_rules": [
                {"trigger_signal": "ghost_signal", "max_recommendation": "Observe Only"},
            ],
        }
        with pytest.raises(ValidationError, match="downgrade_rules|ghost_signal|taxonomy"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=esl_policy,
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_downgrade_rules_invalid_max_recommendation_raises(self) -> None:
        """downgrade_rules with max_recommendation not in boundaries raises ValidationError."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        esl_policy = {
            **_valid_esl_policy(),
            "downgrade_rules": [
                {"trigger_signal": "funding_raised", "max_recommendation": "Invalid Type"},
            ],
        }
        with pytest.raises(ValidationError, match="max_recommendation|recommendation_boundaries"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=esl_policy,
                derivers=_valid_derivers(),
                playbooks={},
            )

    def test_downgrade_rules_valid_passes(self) -> None:
        """downgrade_rules with valid trigger and max_recommendation passes."""
        from app.packs.schemas import validate_pack_schema

        esl_policy = {
            **_valid_esl_policy(),
            "downgrade_rules": [
                {"trigger_signal": "funding_raised", "max_recommendation": "Observe Only"},
            ],
        }
        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=esl_policy,
            derivers=_valid_derivers(),
            playbooks={},
        )

    def test_downgrade_rules_max_recommendation_without_boundaries_raises(self) -> None:
        """downgrade_rules with max_recommendation but no recommendation_boundaries raises."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        for boundaries in ([], None):
            esl_policy = {
                "svi_event_types": [],
                "downgrade_rules": [
                    {"trigger_signal": "funding_raised", "max_recommendation": "Arbitrary Type"},
                ],
            }
            if boundaries is not None:
                esl_policy["recommendation_boundaries"] = boundaries
            with pytest.raises(
                ValidationError,
                match="max_recommendation|recommendation_boundaries",
            ):
                validate_pack_schema(
                    manifest=_valid_manifest(),
                    taxonomy=_valid_taxonomy(),
                    scoring=_valid_scoring(),
                    esl_policy=esl_policy,
                    derivers=_valid_derivers(),
                    playbooks={},
                )

    def test_fractional_cto_v1_with_new_keys_passes(self) -> None:
        """fractional_cto_v1 with blocked_signals and prohibited_combinations passes (Phase 1)."""
        import json
        from pathlib import Path

        import yaml

        from app.packs.schemas import validate_pack_schema

        packs_root = Path(__file__).resolve().parent.parent / "packs"
        pack_dir = packs_root / "fractional_cto_v1"
        with (pack_dir / "pack.json").open() as f:
            manifest = json.load(f)
        with (pack_dir / "taxonomy.yaml").open() as f:
            taxonomy = yaml.safe_load(f) or {}
        with (pack_dir / "scoring.yaml").open() as f:
            scoring = yaml.safe_load(f) or {}
        with (pack_dir / "esl_policy.yaml").open() as f:
            esl_policy = yaml.safe_load(f) or {}
        with (pack_dir / "derivers.yaml").open() as f:
            derivers = yaml.safe_load(f) or {}
        playbooks = {}
        if (pack_dir / "playbooks").is_dir():
            for p in (pack_dir / "playbooks").glob("*.yaml"):
                with p.open() as f:
                    playbooks[p.stem] = yaml.safe_load(f) or {}

        validate_pack_schema(
            manifest=manifest,
            taxonomy=taxonomy,
            scoring=scoring,
            esl_policy=esl_policy,
            derivers=derivers,
            playbooks=playbooks,
        )


class TestValidationErrorType:
    """ValidationError is a proper exception type."""

    def test_validation_error_is_exception(self) -> None:
        """ValidationError subclasses Exception."""
        from app.packs.schemas import ValidationError

        assert issubclass(ValidationError, Exception)

    def test_validation_error_message_preserved(self) -> None:
        """ValidationError preserves message for logging."""
        from app.packs.schemas import ValidationError

        err = ValidationError("signal_id ghost_signal not in taxonomy")
        assert "ghost_signal" in str(err)
        assert "taxonomy" in str(err)


class TestValidatePackSchemaPlaybooks:
    """Playbooks reference valid sensitivity levels when present (Issue #190)."""

    def test_playbook_recommendation_types_invalid_raises(self) -> None:
        """Playbook with recommendation_types not in esl_policy boundaries raises."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        playbooks = {
            "ore_outreach": {
                "pattern_frames": {"momentum": "test"},
                "ctas": ["CTA"],
                "recommendation_types": ["Invalid Type"],
            }
        }
        with pytest.raises(ValidationError, match="Invalid Type|recommendation_boundaries"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks=playbooks,
            )

    def test_playbook_recommendation_types_valid_passes(self) -> None:
        """Playbook with recommendation_types in boundaries passes."""
        from app.packs.schemas import validate_pack_schema

        playbooks = {
            "ore_outreach": {
                "pattern_frames": {"momentum": "test"},
                "ctas": ["CTA"],
                "recommendation_types": ["Observe Only", "Standard Outreach"],
            }
        }
        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=_valid_esl_policy(),
            derivers=_valid_derivers(),
            playbooks=playbooks,
        )

    def test_playbook_without_sensitivity_refs_passes(self) -> None:
        """Playbook without sensitivity_levels or recommendation_types passes."""
        from app.packs.schemas import validate_pack_schema

        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=_valid_esl_policy(),
            derivers=_valid_derivers(),
            playbooks=_valid_playbooks(),
        )


class TestValidatePackSchemaStrictSemver:
    """Version semver validation when strict_semver=True (Issue #190)."""

    def test_strict_semver_invalid_version_raises(self) -> None:
        """strict_semver=True with version '1' raises (not x.y.z)."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        manifest = {**_valid_manifest(), "version": "1"}
        with pytest.raises(ValidationError, match="semver|x.y.z"):
            validate_pack_schema(
                manifest=manifest,
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks=_valid_playbooks(),
                strict_semver=True,
            )

    def test_strict_semver_valid_version_passes(self) -> None:
        """strict_semver=True with version '1.0.0' passes."""
        from app.packs.schemas import validate_pack_schema

        manifest = {**_valid_manifest(), "version": "1.0.0"}
        validate_pack_schema(
            manifest=manifest,
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=_valid_esl_policy(),
            derivers=_valid_derivers(),
            playbooks=_valid_playbooks(),
            strict_semver=True,
        )

    def test_non_strict_semver_accepts_legacy_version(self) -> None:
        """strict_semver=False accepts version '1' (backward compat)."""
        from app.packs.schemas import validate_pack_schema

        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=_valid_taxonomy(),
            scoring=_valid_scoring(),
            esl_policy=_valid_esl_policy(),
            derivers=_valid_derivers(),
            playbooks=_valid_playbooks(),
            strict_semver=False,
        )


class TestValidatePackSchemaStrictExplainability:
    """Explainability validation when strict_explainability=True (Issue #190)."""

    def test_strict_explainability_missing_templates_raises(self) -> None:
        """strict_explainability=True without explainability_templates raises."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        with pytest.raises(ValidationError, match="explainability_templates"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=_valid_taxonomy(),
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks=_valid_playbooks(),
                strict_explainability=True,
            )

    def test_strict_explainability_missing_signal_raises(self) -> None:
        """strict_explainability=True with missing signal_id in templates raises."""
        from app.packs.schemas import ValidationError, validate_pack_schema

        taxonomy = {
            **_valid_taxonomy(),
            "explainability_templates": {"funding_raised": "{label} on {date}"},
        }
        with pytest.raises(ValidationError, match="cto_role_posted|missing"):
            validate_pack_schema(
                manifest=_valid_manifest(),
                taxonomy=taxonomy,
                scoring=_valid_scoring(),
                esl_policy=_valid_esl_policy(),
                derivers=_valid_derivers(),
                playbooks=_valid_playbooks(),
                strict_explainability=True,
            )

    def test_strict_explainability_valid_passes(self) -> None:
        """strict_explainability=True with all templates passes."""
        from app.packs.schemas import validate_pack_schema

        taxonomy = {
            **_valid_taxonomy(),
            "explainability_templates": {
                "funding_raised": "{label} observed on {date}",
                "cto_role_posted": "{label} detected on {date}",
            },
        }
        validate_pack_schema(
            manifest=_valid_manifest(),
            taxonomy=taxonomy,
            scoring=_valid_scoring(),
            esl_policy=_valid_esl_policy(),
            derivers=_valid_derivers(),
            playbooks=_valid_playbooks(),
            strict_explainability=True,
        )

    def test_fractional_cto_v1_passes_when_explainability_enforced(self) -> None:
        """fractional_cto_v1 passes validation with strict_explainability=True (Issue #190)."""
        import json
        from pathlib import Path

        import yaml

        from app.packs.schemas import validate_pack_schema

        packs_root = Path(__file__).resolve().parent.parent / "packs"
        pack_dir = packs_root / "fractional_cto_v1"
        with (pack_dir / "pack.json").open() as f:
            manifest = json.load(f)
        with (pack_dir / "taxonomy.yaml").open() as f:
            taxonomy = yaml.safe_load(f) or {}
        with (pack_dir / "scoring.yaml").open() as f:
            scoring = yaml.safe_load(f) or {}
        with (pack_dir / "esl_policy.yaml").open() as f:
            esl_policy = yaml.safe_load(f) or {}
        with (pack_dir / "derivers.yaml").open() as f:
            derivers = yaml.safe_load(f) or {}
        playbooks = {}
        if (pack_dir / "playbooks").is_dir():
            for p in (pack_dir / "playbooks").glob("*.yaml"):
                with p.open() as f:
                    playbooks[p.stem] = yaml.safe_load(f) or {}

        validate_pack_schema(
            manifest=manifest,
            taxonomy=taxonomy,
            scoring=scoring,
            esl_policy=esl_policy,
            derivers=derivers,
            playbooks=playbooks,
            strict_explainability=True,
        )
