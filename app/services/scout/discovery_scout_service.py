"""Discovery Scout Service — Evidence-Only orchestration (plan Step 5).

Orchestrates: Query Planner → filter sources → fetch pages → LLM → validate Evidence Bundles
→ persist to ScoutRun + ScoutEvidenceBundle. Does NOT call company resolver, event storage,
or any deriver.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.config import get_settings
from app.evidence.store import store_evidence_bundle
from app.llm.router import ModelRole, get_llm_provider
from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from app.prompts.loader import render_prompt
from app.schemas.scout import EvidenceBundle, ScoutRunMetadata
from app.scout.query_planner import plan_queries
from app.scout.sources import filter_allowed_sources

if TYPE_CHECKING:
    from app.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# Default page fetch limit when not specified
DEFAULT_PAGE_FETCH_LIMIT = 10


def _parse_llm_bundles(raw: str) -> list[dict]:
    """Parse LLM response JSON and return list of bundle dicts. Returns [] on parse failure."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Scout LLM response was not valid JSON")
        return []
    if not isinstance(data, dict):
        return []
    bundles = data.get("bundles")
    if not isinstance(bundles, list):
        return []
    return bundles


async def run(
    db: Session,
    icp_definition: str,
    *,
    exclusion_rules: str | None = None,
    pack_id: str | None = None,
    page_fetch_limit: int = DEFAULT_PAGE_FETCH_LIMIT,
    seed_urls: list[str] | None = None,
    allowlist: list[str] | None = None,
    denylist: list[str] | None = None,
    fetch_page: Callable[[str], Awaitable[str | None]] | None = None,
    llm_provider: LLMProvider | None = None,
    workspace_id: uuid.UUID | None = None,
) -> tuple[str, list[EvidenceBundle], ScoutRunMetadata]:
    """Run discovery scout: plan queries, filter URLs, fetch, LLM, validate, persist.

    Does NOT call resolve_or_create_company, store_signal_event, or any deriver.
    Writes only to scout_runs and scout_evidence_bundles.

    Args:
        db: Database session for persisting ScoutRun and ScoutEvidenceBundle.
        icp_definition: Ideal Customer Profile description.
        exclusion_rules: Optional exclusion rules text (for config snapshot only).
        pack_id: Optional pack id for query emphasis (passed to query planner).
        page_fetch_limit: Max URLs to fetch (default 10).
        seed_urls: URLs to fetch. If None, no pages are fetched (empty content).
        allowlist: Source allowlist. If None, uses settings.scout_source_allowlist.
        denylist: Source denylist. If None, uses settings.scout_source_denylist.
        fetch_page: Async callable(url) -> str | None. If None, uses app.services.fetcher.fetch_page.
        llm_provider: LLM provider. If None, uses get_llm_provider(role=ModelRole.SCOUT).

    Returns:
        (run_id, list of validated EvidenceBundles, metadata).
    """
    settings = get_settings()
    if allowlist is None:
        allowlist = list(settings.scout_source_allowlist)
    if denylist is None:
        denylist = list(settings.scout_source_denylist)

    run_id = str(uuid.uuid4())
    queries = plan_queries(icp_definition, core_rubric=None, pack_id=pack_id)

    urls_to_fetch: list[str] = []
    if seed_urls:
        urls_to_fetch = filter_allowed_sources(seed_urls, allowlist, denylist)[:page_fetch_limit]

    page_content_parts: list[str] = []
    if urls_to_fetch:
        from app.services.fetcher import fetch_page as _fetch_page

        fetcher = fetch_page if fetch_page is not None else _fetch_page
        for url in urls_to_fetch:
            html = await fetcher(url)
            if html:
                from app.services.extractor import extract_text

                page_content_parts.append(f"--- URL: {url} ---\n{extract_text(html)}")
    page_content = "\n\n".join(page_content_parts) if page_content_parts else "(no content)"

    prompt = render_prompt(
        "scout_evidence_bundle_v1",
        ICP_DEFINITION=icp_definition,
        PAGE_CONTENT=page_content,
    )
    provider = llm_provider or get_llm_provider(role=ModelRole.SCOUT, settings=settings)
    model_version = getattr(provider, "model", "unknown")
    raw_response = provider.complete(
        prompt,
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    bundle_dicts = _parse_llm_bundles(raw_response)
    validated: list[EvidenceBundle] = []
    for i, b in enumerate(bundle_dicts):
        if not isinstance(b, dict):
            continue
        try:
            validated.append(EvidenceBundle.model_validate(b))
        except Exception as e:
            logger.warning("Scout bundle %d failed validation: %s", i, e)

    config_snapshot = {
        "icp_definition": icp_definition[:500],
        "exclusion_rules": exclusion_rules,
        "pack_id": pack_id,
        "query_count": len(queries),
        "page_fetch_count": len(urls_to_fetch),
    }
    scout_run = ScoutRun(
        run_id=uuid.UUID(run_id),
        workspace_id=workspace_id,
        finished_at=datetime.now(UTC),
        model_version=model_version,
        tokens_used=None,
        latency_ms=None,
        page_fetch_count=len(urls_to_fetch),
        config_snapshot=config_snapshot,
        status="completed",
        error_message=None,
    )
    db.add(scout_run)
    db.flush()

    for vb in validated:
        evidence_json = [e.model_dump(mode="json") for e in vb.evidence]
        missing_json = list(vb.missing_information)
        row = ScoutEvidenceBundle(
            scout_run_id=scout_run.run_id,
            candidate_company_name=vb.candidate_company_name,
            company_website=vb.company_website,
            why_now_hypothesis=vb.why_now_hypothesis,
            evidence=evidence_json,
            missing_information=missing_json,
            raw_llm_output=vb.model_dump(mode="json"),
        )
        db.add(row)
    db.flush()

    # Persist to Evidence Store (M6): immutable bundles with core versioning; same transaction.
    run_context = {"run_id": run_id, **config_snapshot}
    raw_model_output = {"raw_response": raw_response, "parsed_bundles": bundle_dicts}
    store_evidence_bundle(
        db,
        run_id=run_id,
        scout_version=model_version,
        bundles=validated,
        run_context=run_context,
        raw_model_output=raw_model_output,
        structured_payloads=None,
        pack_id=None,
    )
    db.commit()

    metadata = ScoutRunMetadata(
        model_version=model_version,
        tokens_used=None,
        latency_ms=None,
        page_fetch_count=len(urls_to_fetch),
    )
    return run_id, validated, metadata


class DiscoveryScoutService:
    """Orchestrates discovery scout run: query plan, fetch, LLM, validate, persist (Evidence-Only)."""

    @staticmethod
    async def run(
        db: Session,
        icp_definition: str,
        *,
        exclusion_rules: str | None = None,
        pack_id: str | None = None,
        page_fetch_limit: int = DEFAULT_PAGE_FETCH_LIMIT,
        seed_urls: list[str] | None = None,
        allowlist: list[str] | None = None,
        denylist: list[str] | None = None,
        fetch_page: Callable[[str], Awaitable[str | None]] | None = None,
        llm_provider: LLMProvider | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> tuple[str, list[EvidenceBundle], ScoutRunMetadata]:
        """Run discovery scout. See module-level run() for full doc."""
        return await run(
            db,
            icp_definition,
            exclusion_rules=exclusion_rules,
            pack_id=pack_id,
        page_fetch_limit=page_fetch_limit,
        seed_urls=seed_urls,
        allowlist=allowlist,
        denylist=denylist,
        fetch_page=fetch_page,
        llm_provider=llm_provider,
        workspace_id=workspace_id,
    )
