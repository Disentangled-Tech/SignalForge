"""Unit tests for ORE polisher (Issue #119 M2)."""

from __future__ import annotations

from unittest.mock import patch

from app.services.ore.polisher import polish_ore_draft


def test_polish_ore_draft_returns_empty_on_prompt_failure() -> None:
    """When resolve_prompt_content raises, returns empty subject/message."""
    with patch(
        "app.services.ore.polisher.resolve_prompt_content",
        side_effect=ValueError("Unfilled placeholders"),
    ):
        result = polish_ore_draft(
            "Subject",
            "Message body",
            tone_definition="Gentle.",
            forbidden_phrases=[],
            allowed_framing_labels=[],
            pack=None,
        )
    assert result == {"subject": "", "message": ""}


def test_polish_ore_draft_returns_empty_on_llm_failure() -> None:
    """When LLM complete() raises, returns empty subject/message."""
    with patch(
        "app.services.ore.polisher.resolve_prompt_content",
        return_value="rendered",
    ):
        with patch(
            "app.services.ore.polisher.get_llm_provider",
        ) as mock_llm:
            mock_llm.return_value.complete.side_effect = RuntimeError("API error")
            result = polish_ore_draft(
                "Subject",
                "Message body",
                tone_definition=None,
                forbidden_phrases=[],
                allowed_framing_labels=[],
                pack=None,
            )
    assert result == {"subject": "", "message": ""}


def test_polish_ore_draft_returns_empty_on_invalid_json() -> None:
    """When LLM returns invalid JSON, returns empty subject/message."""
    with patch(
        "app.services.ore.polisher.resolve_prompt_content",
        return_value="rendered",
    ):
        with patch(
            "app.services.ore.polisher.get_llm_provider",
        ) as mock_llm:
            mock_llm.return_value.complete.return_value = "not valid json"
            result = polish_ore_draft(
                "Subject",
                "Message body",
                tone_definition=None,
                forbidden_phrases=[],
                allowed_framing_labels=[],
                pack=None,
            )
    assert result == {"subject": "", "message": ""}


def test_polish_ore_draft_returns_valid_subject_message_when_llm_returns_json() -> None:
    """When LLM returns valid JSON with subject and message, returns them."""
    with patch(
        "app.services.ore.polisher.resolve_prompt_content",
        return_value="rendered",
    ):
        with patch(
            "app.services.ore.polisher.get_llm_provider",
        ) as mock_llm:
            mock_llm.return_value.complete.return_value = (
                '{"subject": "Polished subject", "message": "Polished message body."}'
            )
            result = polish_ore_draft(
                "Original subject",
                "Original message",
                tone_definition="Keep it gentle.",
                sensitivity_level="high",
                forbidden_phrases=[],
                allowed_framing_labels=["Funding Raised"],
                pack=None,
            )
    assert result["subject"] == "Polished subject"
    assert result["message"] == "Polished message body."


def test_polish_ore_draft_passes_tone_forbidden_allowed_to_prompt() -> None:
    """Prompt receives TONE_INSTRUCTION, FORBIDDEN_PHRASES, and ALLOWED_FRAMING."""
    with patch(
        "app.services.ore.polisher.resolve_prompt_content",
        return_value="rendered",
    ) as mock_resolve:
        with patch(
            "app.services.ore.polisher.get_llm_provider",
        ) as mock_llm:
            mock_llm.return_value.complete.return_value = '{"subject":"S","message":"M"}'
            polish_ore_draft(
                "Subj",
                "Msg",
                tone_definition="Use only gentle framing.",
                sensitivity_level="medium",
                forbidden_phrases=["do not say this", "or this"],
                allowed_framing_labels=["Cto Role Posted", "Funding Raised"],
                pack=None,
            )
    mock_resolve.assert_called_once()
    call_kwargs = mock_resolve.call_args[1]
    assert call_kwargs["TONE_INSTRUCTION"] == "Sensitivity: medium. Use only gentle framing."
    assert "do not say this" in call_kwargs["FORBIDDEN_PHRASES"]
    assert "or this" in call_kwargs["FORBIDDEN_PHRASES"]
    assert call_kwargs["ALLOWED_FRAMING"] == "Cto Role Posted, Funding Raised"


def test_polish_ore_draft_prompt_includes_subject_and_message() -> None:
    """Prompt receives SUBJECT and MESSAGE from the draft."""
    with patch(
        "app.services.ore.polisher.resolve_prompt_content",
        return_value="rendered",
    ) as mock_resolve:
        with patch(
            "app.services.ore.polisher.get_llm_provider",
        ) as mock_llm:
            mock_llm.return_value.complete.return_value = '{"subject":"S","message":"M"}'
            polish_ore_draft(
                "Quick question",
                "Hi there,\n\nWhen teams scale...",
                tone_definition=None,
                forbidden_phrases=[],
                allowed_framing_labels=[],
                pack=None,
            )
    call_kwargs = mock_resolve.call_args[1]
    assert call_kwargs["SUBJECT"] == "Quick question"
    assert "When teams scale" in call_kwargs["MESSAGE"]


def test_polish_ore_draft_tone_instruction_empty_when_omitted() -> None:
    """When tone_definition and sensitivity_level omitted, TONE_INSTRUCTION is empty."""
    with patch(
        "app.services.ore.polisher.resolve_prompt_content",
        return_value="rendered",
    ) as mock_resolve:
        with patch(
            "app.services.ore.polisher.get_llm_provider",
        ) as mock_llm:
            mock_llm.return_value.complete.return_value = '{"subject":"S","message":"M"}'
            polish_ore_draft(
                "S",
                "M",
                forbidden_phrases=[],
                allowed_framing_labels=[],
                pack=None,
            )
    assert mock_resolve.call_args[1]["TONE_INSTRUCTION"] == ""


def test_polish_ore_draft_uses_ore_polish_v1_template() -> None:
    """Polisher uses template name ore_polish_v1 (loadable from app/prompts)."""
    with patch(
        "app.services.ore.polisher.resolve_prompt_content",
        return_value="rendered",
    ) as mock_resolve:
        with patch(
            "app.services.ore.polisher.get_llm_provider",
        ) as mock_llm:
            mock_llm.return_value.complete.return_value = '{"subject":"S","message":"M"}'
            polish_ore_draft("S", "M", forbidden_phrases=[], allowed_framing_labels=[], pack=None)
    assert mock_resolve.call_args[0][0] == "ore_polish_v1"


def test_polish_ore_draft_prompt_constraints_no_surveillance_or_forbidden() -> None:
    """Prompt template instructs no surveillance and no forbidden phrases (constraints in prompt)."""
    from app.prompts.loader import load_prompt

    content = load_prompt("ore_polish_v1")
    assert "I noticed you" in content or "surveillance" in content.lower()
    assert "FORBIDDEN_PHRASES" in content
    assert "ALLOWED_FRAMING" in content
    assert "subject" in content and "message" in content
