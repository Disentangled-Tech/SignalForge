"""Workspace access control (Phase 3).

Validates user has access to workspace before allowing data operations.
Uses user_workspaces for membership; default workspace allowed for all users.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_workspace import UserWorkspace


def user_has_access_to_workspace(
    db: Session,
    user: User,
    workspace_id: str | UUID | None,
) -> bool:
    """Return True if user has access to workspace.

    Default workspace: always allowed (all users backfilled on migration).
    Other workspaces: requires (user_id, workspace_id) in user_workspaces.
    None workspace_id: returns False (no workspace context).
    """
    from app.pipeline.stages import DEFAULT_WORKSPACE_ID

    if workspace_id is None:
        return False
    ws_uuid = UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
    default_uuid = UUID(DEFAULT_WORKSPACE_ID)
    if ws_uuid == default_uuid:
        return True
    return (
        db.query(UserWorkspace)
        .filter(
            UserWorkspace.user_id == user.id,
            UserWorkspace.workspace_id == ws_uuid,
        )
        .first()
        is not None
    )
