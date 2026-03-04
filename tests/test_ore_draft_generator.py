"""Unit tests for ORE draft generator (Issue #176 M4: explainability + top signals)."""

from __future__ import annotations

from unittest.mock import patch

from app.models.company import Company
from app.services.ore.draft_generator import generate_ore_draft


def test_generate_ore_draft_passes_explainability_and_top_signals_to_prompt() -> None:
    """M4: When explainability_snippet and top_signal_labels are provided, they are passed to the prompt."""
    company = Company(name="TestCo", founder_name="Jane", website_url="https://test.co")
    with patch(
        "app.services.ore.draft_generator.resolve_prompt_content",
        return_value="rendered",
    ) as mock_resolve:
        with patch(
            "app.services.ore.draft_generator.get_llm_provider",
        ) as mock_llm:
            mock_llm.return_value.complete.return_value = '{"subject":"Hi","message":"Hello"}'
            generate_ore_draft(
                company=company,
                recommendation_type="Standard Outreach",
                pattern_frame="When teams scale...",
                value_asset="Checklist",
                cta="Want me to send it?",
                pack=None,
                explainability_snippet="Top factors: complexity, momentum.",
                top_signal_labels=["Cto Role Posted", "Funding Raised"],
            )
    mock_resolve.assert_called_once()
    call_kwargs = mock_resolve.call_args[1]
    assert call_kwargs.get("EXPLAINABILITY_SNIPPET") == "Top factors: complexity, momentum."
    assert call_kwargs.get("TOP_SIGNALS") == "Cto Role Posted, Funding Raised"


def test_generate_ore_draft_defaults_explainability_empty_when_not_provided() -> None:
    """M4: When explainability_snippet and top_signal_labels are omitted, empty values are passed (backward compat)."""
    company = Company(name="TestCo", founder_name="Jane", website_url="https://test.co")
    with patch(
        "app.services.ore.draft_generator.resolve_prompt_content",
        return_value="rendered",
    ) as mock_resolve:
        with patch(
            "app.services.ore.draft_generator.get_llm_provider",
        ) as mock_llm:
            mock_llm.return_value.complete.return_value = '{"subject":"Hi","message":"Hello"}'
            generate_ore_draft(
                company=company,
                recommendation_type="Standard Outreach",
                pattern_frame="When teams scale...",
                value_asset="Checklist",
                cta="Want me to send it?",
                pack=None,
            )
    call_kwargs = mock_resolve.call_args[1]
    assert call_kwargs.get("EXPLAINABILITY_SNIPPET") == ""
    assert call_kwargs.get("TOP_SIGNALS") == ""


def test_generate_ore_draft_returns_empty_on_invalid_json() -> None:
    """When LLM returns invalid JSON, returns subject/message empty dict (no crash)."""
    company = Company(name="TestCo", founder_name="Jane", website_url="https://test.co")
    with patch(
        "app.services.ore.draft_generator.resolve_prompt_content",
        return_value="rendered",
    ):
        with patch(
            "app.services.ore.draft_generator.get_llm_provider",
        ) as mock_llm:
            mock_llm.return_value.complete.return_value = "not valid json"
            result = generate_ore_draft(
                company=company,
                recommendation_type="Standard Outreach",
                pattern_frame="When teams scale...",
                value_asset="Checklist",
                cta="Want me to send it?",
                pack=None,
            )
    assert result == {"subject": "", "message": ""}
