"""
Prompt templates. All prompts live here per PRD.

Rules:
- Never hardcode prompts in Python
- Prompts must be versioned by filename
- Prompts must be editable without code changes
"""

from app.prompts.loader import load_prompt, render_prompt

__all__ = ["load_prompt", "render_prompt"]
