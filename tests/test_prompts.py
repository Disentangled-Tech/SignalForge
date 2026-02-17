"""Tests for prompt template loader."""

from unittest.mock import patch

import pytest

from app.prompts.loader import load_prompt, render_prompt, _PLACEHOLDER_RE


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
    for name, value in variables.items():
        assert value in result


def test_render_prompt_missing_variable_raises() -> None:
    """render_prompt should raise ValueError when placeholders are left unfilled."""
    with pytest.raises(ValueError, match="Unfilled placeholders"):
        render_prompt("pain_signals_v1", COMPANY_NAME="Acme")


def test_render_prompt_extra_variable_warns(caplog: pytest.LogCaptureFixture) -> None:
    """render_prompt should log a warning for variables not in the template."""
    variables = {name: "x" for name in TEMPLATE_PLACEHOLDERS["pain_signals_v1"]}
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
    from app.prompts import load_prompt as lp, render_prompt as rp

    assert callable(lp)
    assert callable(rp)

