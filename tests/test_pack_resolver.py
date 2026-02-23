"""Pack resolver tests (Issue #189, Plan Step 3).

Tests for resolve_pack and get_default_pack_id.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.pack_resolver import get_default_pack_id, resolve_pack


class TestResolvePack:
    """resolve_pack(db, pack_id) loads Pack from DB + filesystem."""

    def test_resolve_pack_returns_pack_when_pack_exists(self, db, fractional_cto_pack_id) -> None:
        """resolve_pack returns Pack when pack is in DB and files exist."""
        pack = resolve_pack(db, fractional_cto_pack_id)
        assert pack is not None
        assert hasattr(pack, "scoring")
        assert hasattr(pack, "esl_policy")
        assert pack.scoring is not None
        assert pack.esl_policy is not None

    def test_resolve_pack_returns_none_when_pack_not_in_db(self, db) -> None:
        """resolve_pack returns None when pack UUID not in signal_packs."""
        unknown_uuid = uuid.uuid4()
        pack = resolve_pack(db, unknown_uuid)
        assert pack is None


class TestGetDefaultPackId:
    """get_default_pack_id returns fractional_cto_v1 UUID."""

    def test_get_default_pack_id_returns_uuid_when_installed(self, db) -> None:
        """get_default_pack_id returns UUID when fractional_cto_v1 is installed."""
        pack_id = get_default_pack_id(db)
        if pack_id is None:
            pytest.skip("fractional_cto_v1 pack not installed (run migration)")
        assert pack_id is not None
        assert isinstance(pack_id, uuid.UUID)
