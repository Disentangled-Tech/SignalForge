"""Watchlist Seeder: register entities from evidence bundles and persist Core Events (Issue #279)."""

from __future__ import annotations

from app.services.watchlist_seeder.seeder import seed_from_bundles

__all__ = ["seed_from_bundles"]
