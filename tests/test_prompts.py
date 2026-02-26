"""Tests for prompt template loader."""

from unittest.mock import patch

import pytest

from app.prompts.loader import (
    _PLACEHOLDER_RE,
    load_prompt,
    load_prompt_from_pack,
    render_prompt,
    resolve_prompt_content,
)

# ---------------------------------------------------------------------------
# Expected placeholders for each template
# ---------------------------------------------------------------------------

TEMPLATE_PLACEHOLDERS = {
    "stage_classification_v1": {
        "OPERATOR_PROFILE_MARKDOWN",
        "COMPANY_NAME",
        "WEBSITE_URL",
        "FOUNDER_NAME",
        "COMPANY_NOTES",
        "SIGNALS_TEXT",
    },
    "pain_signals_v1": {
        "COMPANY_NAME",
        "WEBSITE_URL",
        "FOUNDER_NAME",
        "COMPANY_NOTES",
        "SIGNALS_TEXT",
    },
    "outreach_v1": {
        "OFFER_TYPE",
        "OPERATOR_PROFILE_MARKDOWN",
        "COMPANY_NAME",
        "FOUNDER_NAME",
        "WEBSITE_URL",
        "COMPANY_NOTES",
        "STAGE",
        "TOP_RISKS",
        "MOST_LIKELY_NEXT_PROBLEM",
        "RECOMMENDED_CONVERSATION_ANGLE",
        "EVIDENCE_BULLETS",
    },
    "briefing_entry_v1": {
        "COMPANY_NAME",
        "FOUNDER_NAME",
        "WEBSITE_URL",
        "STAGE",
        "STAGE_CONFIDENCE",
        "PAIN_SIGNALS_JSON",
        "EVIDENCE_BULLETS",
    },
    "explanation_v1": {
        "COMPANY_NAME",
        "STAGE",
        "EVIDENCE_BULLETS",
        "PAIN_SIGNALS_SUMMARY",
        "TOP_RISKS",
        "MOST_LIKELY_NEXT_PROBLEM",
    },
}

ALL_TEMPLATES = list(TEMPLATE_PLACEHOLDERS.keys())


# ---------------------------------------------------------------------------
# load_prompt tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_name", ALL_TEMPLATES)
def test_load_prompt_success(template_name: str) -> None:
    """Each known template should load without error."""
    content = load_prompt(template_name)
    assert isinstance(content, str)
    assert len(content) > 0


def test_load_prompt_missing_template() -> None:
    """Loading a non-existent template should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="not_a_real_template"):
        load_prompt("not_a_real_template")


def test_load_prompt_error_lists_available() -> None:
    """The FileNotFoundError message should list available templates."""
    with pytest.raises(FileNotFoundError, match="Available templates"):
        load_prompt("nonexistent_xyz")


# ---------------------------------------------------------------------------
# Template placeholder verification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("template_name", ALL_TEMPLATES)
def test_template_has_expected_placeholders(template_name: str) -> None:
    """Each template should contain exactly the expected placeholder variables."""
    content = load_prompt(template_name)
    found = set(_PLACEHOLDER_RE.findall(content))
    expected = TEMPLATE_PLACEHOLDERS[template_name]
    assert found == expected, (
        f"Template '{template_name}' placeholder mismatch.\n"
        f"  Expected: {sorted(expected)}\n"
        f"  Found:    {sorted(found)}"
    )


# ---------------------------------------------------------------------------
# render_prompt tests
# ---------------------------------------------------------------------------


def test_render_prompt_fills_all_variables() -> None:
    """render_prompt should replace all placeholders with provided values."""
    variables = {name: f"<{name}>" for name in TEMPLATE_PLACEHOLDERS["pain_signals_v1"]}
    result = render_prompt("pain_signals_v1", **variables)
    # No remaining placeholders
    assert "{{" not in result
    # Each value should appear in the output
    for _name, value in variables.items():
        assert value in result


def test_render_prompt_missing_variable_raises() -> None:
    """render_prompt should raise ValueError when placeholders are left unfilled."""
    with pytest.raises(ValueError, match="Unfilled placeholders"):
        render_prompt("pain_signals_v1", COMPANY_NAME="Acme")


def test_render_prompt_extra_variable_warns(caplog: pytest.LogCaptureFixture) -> None:
    """render_prompt should log a warning for variables not in the template."""
    variables = dict.fromkeys(TEMPLATE_PLACEHOLDERS["pain_signals_v1"], "x")
    variables["NOT_IN_TEMPLATE"] = "extra"
    with caplog.at_level("WARNING", logger="app.prompts.loader"):
        render_prompt("pain_signals_v1", **variables)
    assert "NOT_IN_TEMPLATE" in caplog.text


# ---------------------------------------------------------------------------
# Caching tests
# ---------------------------------------------------------------------------


def test_load_prompt_caches_results() -> None:
    """load_prompt should cache file reads — loading twice should use cache."""
    # Clear any existing cache
    load_prompt.cache_clear()

    load_prompt("pain_signals_v1")
    load_prompt("pain_signals_v1")

    info = load_prompt.cache_info()
    assert info.hits >= 1, "Expected at least 1 cache hit on second load"


# ---------------------------------------------------------------------------
# Import test
# ---------------------------------------------------------------------------


def test_outreach_v1_includes_issue_19_acceptance_criteria() -> None:
    """outreach_v1.md contains conversational, no marketing, company context per Issue #19."""
    content = load_prompt("outreach_v1")
    assert "conversational" in content.lower()
    assert "marketing" in content.lower() or "promotional" in content.lower()
    assert "company" in content.lower() or "context" in content.lower()


def test_imports_from_package() -> None:
    """load_prompt and render_prompt should be importable from app.prompts."""
    from app.prompts import load_prompt as lp
    from app.prompts import render_prompt as rp

    assert callable(lp)
    assert callable(rp)


# ---------------------------------------------------------------------------
# Pack prompt bundle (M4: resolve_prompt_content)
# ---------------------------------------------------------------------------


def test_resolve_prompt_content_without_pack_uses_app_prompts() -> None:
    """resolve_prompt_content with pack=None uses app/prompts (same as render_prompt)."""
    variables = {name: f"<{name}>" for name in TEMPLATE_PLACEHOLDERS["pain_signals_v1"]}
    result = resolve_prompt_content("pain_signals_v1", None, **variables)
    assert "{{" not in result
    for _name, value in variables.items():
        assert value in result


def test_resolve_prompt_content_with_v1_pack_uses_app_prompts() -> None:
    """resolve_prompt_content with schema_version '1' pack uses app/prompts (no pack prompts)."""
    from app.packs.loader import Pack

    pack = Pack(
        manifest={"id": "fractional_cto_v1", "version": "1", "name": "CTO", "schema_version": "1"},
        taxonomy={},
        scoring={},
        esl_policy={},
        playbooks={},
        derivers={},
        config_checksum="",
    )
    variables = {name: f"<{name}>" for name in TEMPLATE_PLACEHOLDERS["pain_signals_v1"]}
    result = resolve_prompt_content("pain_signals_v1", pack, **variables)
    assert "{{" not in result
    assert "<COMPANY_NAME>" in result


def test_resolve_prompt_content_with_v2_pack_no_prompts_dir_uses_app_prompts() -> None:
    """resolve_prompt_content with v2 pack but no prompts dir falls back to app/prompts."""
    from app.packs.loader import Pack

    # v2 pack whose pack dir has no prompts/ (e.g. fractional_cto_v1 not yet migrated)
    pack = Pack(
        manifest={"id": "fractional_cto_v1", "version": "1", "name": "CTO", "schema_version": "2"},
        taxonomy={},
        scoring={},
        esl_policy={},
        playbooks={},
        derivers={},
        config_checksum="",
    )
    variables = {name: f"<{name}>" for name in TEMPLATE_PLACEHOLDERS["pain_signals_v1"]}
    result = resolve_prompt_content("pain_signals_v1", pack, **variables)
    assert "{{" not in result
    assert "<COMPANY_NAME>" in result


def test_load_prompt_from_pack_returns_none_when_file_missing() -> None:
    """load_prompt_from_pack returns None when pack prompts dir has no such template."""
    from pathlib import Path

    # Use a dir that exists but has no prompts subdir or template
    pack_dir = Path(__file__).resolve().parent.parent / "app" / "prompts"
    result = load_prompt_from_pack(pack_dir, "nonexistent_template_xyz")
    assert result is None


def test_load_prompt_from_pack_returns_content_when_file_exists() -> None:
    """load_prompt_from_pack returns file content when pack_dir/prompts/<name>.md exists."""
    # app/prompts/ has .md files; use it as fake "pack" root so prompts/ would be app/prompts/prompts
    # which doesn't exist. So use a temp dir with prompts/subdir.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        pack_dir = Path(tmp)
        prompts_dir = pack_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "custom_v1.md").write_text("Hello {{NAME}}", encoding="utf-8")
        content = load_prompt_from_pack(pack_dir, "custom_v1")
        assert content == "Hello {{NAME}}"


def test_resolve_prompt_content_with_v2_pack_uses_pack_file_when_present() -> None:
    """resolve_prompt_content with v2 pack and pack prompts dir containing template uses pack file."""
    import tempfile
    from pathlib import Path

    from app.packs import loader as pack_loader
    from app.packs.loader import Pack

    with tempfile.TemporaryDirectory() as tmp:
        pack_dir = Path(tmp)
        prompts_dir = pack_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "pain_signals_v1.md").write_text(
            "Pack override: {{COMPANY_NAME}} and {{SIGNALS_TEXT}}",
            encoding="utf-8",
        )
        pack = Pack(
            manifest={"id": "custom_v2", "version": "1", "name": "Custom", "schema_version": "2"},
            taxonomy={},
            scoring={},
            esl_policy={},
            playbooks={},
            derivers={},
            config_checksum="",
        )
        with patch.object(pack_loader, "get_pack_dir", return_value=pack_dir):
            result = resolve_prompt_content(
                "pain_signals_v1",
                pack,
                COMPANY_NAME="Acme",
                WEBSITE_URL="https://acme.com",
                FOUNDER_NAME="Jane",
                COMPANY_NOTES="",
                SIGNALS_TEXT="some signals",
            )
        assert "Pack override" in result
        assert "Acme" in result
        assert "some signals" in result
