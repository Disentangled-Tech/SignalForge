"""
Prompt template loader.

Loads .md prompt templates from app/prompts/ and renders them
by substituting {{VARIABLE_NAME}} placeholders.

M4 (Pack v2): resolve_prompt_content() can load from pack prompts dir
(packs/{pack_id}/prompts/*.md) when pack has schema_version "2".
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# Directory where prompt template .md files live
_PROMPTS_DIR = Path(__file__).parent

# Pattern to match {{VARIABLE_NAME}} placeholders
_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")

# Template name: safe for path (no path separators, alphanumeric/underscore/hyphen/dot only)
_TEMPLATE_NAME_SAFE = re.compile(r"^[a-zA-Z0-9_.-]+$")

if TYPE_CHECKING:
    from app.packs.loader import Pack


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
        available = sorted(p.stem for p in _PROMPTS_DIR.glob("*.md"))
        raise FileNotFoundError(
            f"Prompt template '{template_name}' not found at {path}. "
            f"Available templates: {available}"
        )
    return path.read_text(encoding="utf-8")


def load_prompt_from_pack(pack_dir: Path, template_name: str) -> str | None:
    """Load a prompt template from pack_dir/prompts/{template_name}.md (M4).

    Args:
        pack_dir: Pack root path (e.g. packs/fractional_cto_v1).
        template_name: Template file name without .md. Must be safe (no path separators).

    Returns:
        Template content if file exists, else None.
    """
    if not _TEMPLATE_NAME_SAFE.match(template_name):
        return None
    path = pack_dir / "prompts" / f"{template_name}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _render_template_content(template_content: str, template_name: str, **variables: str) -> str:
    """Fill {{VARIABLE}} placeholders in template string. Shared by render_prompt and resolve_prompt_content."""
    template_placeholders = set(_PLACEHOLDER_RE.findall(template_content))
    for var_name in variables:
        if var_name not in template_placeholders:
            logger.warning(
                "Variable '%s' provided but not found in template '%s'",
                var_name,
                template_name,
            )
    rendered = template_content
    for var_name, var_value in variables.items():
        rendered = rendered.replace(f"{{{{{var_name}}}}}", str(var_value))
    remaining = _PLACEHOLDER_RE.findall(rendered)
    if remaining:
        raise ValueError(
            f"Unfilled placeholders in template '{template_name}': "
            f"{sorted(set(remaining))}. "
            f"Provide these as keyword arguments."
        )
    return rendered


def resolve_prompt_content(
    template_name: str,
    pack: Pack | None,
    **variables: str,
) -> str:
    """Load template from pack prompts (v2) or app/prompts, then render (M4).

    When pack is provided and has schema_version \"2\", tries pack_dir/prompts/{template_name}.md
    first; if missing, falls back to app/prompts. When pack is None or v1, uses app/prompts only.
    """
    template_content: str | None = None
    if pack is not None and isinstance(pack.manifest, dict):
        if pack.manifest.get("schema_version") == "2":
            pack_id = pack.manifest.get("id")
            if pack_id:
                from app.packs.loader import get_pack_dir

                pack_dir = get_pack_dir(pack_id)
                template_content = load_prompt_from_pack(pack_dir, template_name)
    if template_content is None:
        template_content = load_prompt(template_name)
    return _render_template_content(template_content, template_name, **variables)


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
    return _render_template_content(template, template_name, **variables)
