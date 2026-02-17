#!/usr/bin/env python3
"""Rectify alembic_version when DB has a revision not in the current migration chain.

Use when the DB's alembic_version points to a revision (e.g. from another branch)
that no longer exists in the repo, causing "Can't locate revision" errors.

Usage:
    python scripts/rectify_alembic_version.py [TARGET_REVISION]

Default TARGET_REVISION is 'head' (resolved from current migration chain).
Only run this if your DB schema already matches the target revision.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.config import get_settings
from app.db.session import engine


def _get_alembic_head() -> str:
    """Return the current head revision from the migration chain."""
    config = Config(str(project_root / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    if head is None:
        raise RuntimeError("No migration head found. Check alembic/versions/.")
    return head


def main() -> None:
    raw_target = sys.argv[1] if len(sys.argv) > 1 else "head"
    if raw_target.lower() == "head":
        target = _get_alembic_head()
    else:
        target = raw_target

    settings = get_settings()
    print(f"Connecting to {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'DB'}...")
    print(f"Setting alembic_version to {target}")

    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE alembic_version SET version_num = :target"),
            {"target": target},
        )
        conn.commit()
        if result.rowcount == 0:
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:target)"), {"target": target})
            conn.commit()
            print("Inserted new alembic_version row.")
        else:
            print(f"Updated alembic_version ({result.rowcount} row(s)).")

    print("Done. Run: alembic current")


if __name__ == "__main__":
    main()
