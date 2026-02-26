"""
Prompt templates. All prompts live here per PRD.

Rules:
- Never hardcode prompts in Python
- Prompts must be versioned by filename
- Prompts must be editable without code changes
"""

from app.prompts.loader import (
    load_prompt,
    load_prompt_from_pack,
    render_prompt,
    resolve_prompt_content,
)

__all__ = ["load_prompt", "load_prompt_from_pack", "render_prompt", "resolve_prompt_content"]
