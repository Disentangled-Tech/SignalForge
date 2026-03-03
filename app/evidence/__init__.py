"""Evidence Store and Repository (Issue #276). Immutable evidence bundle persistence from Scout.

Read APIs: Any future endpoint that lists or returns evidence bundles MUST enforce workspace
scoping (e.g. via scout_runs.workspace_id when bundles are tied to scout runs) so that
no cross-tenant data is exposed. See app.evidence.store module docstring.
"""

from app.evidence.repository import (
    get_bundle,
    get_bundle_for_workspace,
    list_bundles_by_run,
    list_bundles_by_run_for_workspace,
    list_claims_for_bundle,
    list_sources_for_bundle,
)
from app.evidence.store import list_scout_bundle_ids_for_workspace, store_evidence_bundle

__all__ = [
    "get_bundle",
    "get_bundle_for_workspace",
    "list_bundles_by_run",
    "list_bundles_by_run_for_workspace",
    "list_claims_for_bundle",
    "list_sources_for_bundle",
    "list_scout_bundle_ids_for_workspace",
    "store_evidence_bundle",
]
