"""ORE (Outreach Recommendation Engine) — policy gate, critic, pipeline."""

from app.services.ore.ore_pipeline import (
    generate_ore_recommendation,
    get_or_create_ore_recommendation,
)

__all__ = ["generate_ore_recommendation", "get_or_create_ore_recommendation"]
