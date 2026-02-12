"""
Prompt template loader.

Loads .md prompt templates from app/prompts/ and renders them
by substituting {{VARIABLE_NAME}} placeholders.
"""

import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Directory where prompt template .md files live
_PROMPTS_DIR = Path(__file__).parent

# Pattern to match {{VARIABLE_NAME}} placeholders
_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")


@lru_cache(maxsize=64)
def load_prompt(template_name: str) -> str:
    """Load a prompt template by name.

    Args:
        template_name: Name of the template file (without .md extension).
            Example: "stage_classification_v1"

    Returns:
        The raw template string with {{PLACEHOLDER}} markers intact.

    Raises:
        FileNotFoundError: If the template file does not exist.
    """
    path = _PROMPTS_DIR / f"{template_name}.md"
    if not path.is_file():
        available = sorted(
            p.stem for p in _PROMPTS_DIR.glob("*.md")
        )
        raise FileNotFoundError(
            f"Prompt template '{template_name}' not found at {path}. "
            f"Available templates: {available}"
        )
    return path.read_text(encoding="utf-8")


def render_prompt(template_name: str, **variables: str) -> str:
    """Load a template and fill in {{VARIABLE}} placeholders.

    Uses simple string replacement (not str.format or f-strings)
    to avoid conflicts with JSON in templates.

    Args:
        template_name: Name of the template file (without .md extension).
        **variables: Keyword arguments mapping placeholder names to values.
            Example: render_prompt("outreach_v1", COMPANY_NAME="Acme")

    Returns:
        The rendered prompt string with all placeholders filled.

    Raises:
        FileNotFoundError: If the template file does not exist.
        ValueError: If required placeholders remain unfilled after rendering.
    """
    template = load_prompt(template_name)

    # Find all placeholders defined in the template
    template_placeholders = set(_PLACEHOLDER_RE.findall(template))

    # Warn about variables provided but not present in template
    for var_name in variables:
        if var_name not in template_placeholders:
            logger.warning(
                "Variable '%s' provided but not found in template '%s'",
                var_name,
                template_name,
            )

    # Substitute each provided variable
    rendered = template
    for var_name, var_value in variables.items():
        rendered = rendered.replace(f"{{{{{var_name}}}}}", str(var_value))

    # Check for unfilled placeholders
    remaining = _PLACEHOLDER_RE.findall(rendered)
    if remaining:
        raise ValueError(
            f"Unfilled placeholders in template '{template_name}': "
            f"{sorted(set(remaining))}. "
            f"Provide these as keyword arguments to render_prompt()."
        )

    return rendered

