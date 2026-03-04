"""Watchlist Seeder: seed companies and signal events from evidence bundle structured_payload (Issue #279 M2)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.evidence.repository import get_bundle, get_bundle_for_workspace
from app.ingestion.event_storage import store_signal_event
from app.schemas.company import CompanyCreate, CompanySource
from app.schemas.core_events import (
    CoreEventCandidate,
    ExtractionEntityCompany,
    StructuredExtractionPayload,
    get_events_from_payload,
)
from app.schemas.seeder import SeedFromBundlesResult
from app.services.company_resolver import resolve_or_create_company

logger = logging.getLogger(__name__)

SOURCE_WATCHLIST_SEEDER = "watchlist_seeder"


def _company_from_extraction(entity: ExtractionEntityCompany) -> CompanyCreate:
    """Map ExtractionEntityCompany to CompanyCreate for resolve_or_create_company."""
    website_url = entity.website_url
    if not website_url and entity.domain:
        website_url = (
            f"https://{entity.domain}" if not entity.domain.startswith("http") else entity.domain
        )
    return CompanyCreate(
        company_name=entity.name,
        website_url=website_url or None,
        founder_name=None,
        founder_linkedin_url=None,
        company_linkedin_url=None,
        notes=None,
        source=CompanySource.research,
        target_profile_match=None,
    )


def _event_time_for_candidate(
    candidate: CoreEventCandidate,
    bundle_created_at: datetime | None,
) -> datetime:
    """Return event_time: from candidate, else bundle created_at, else now UTC."""
    if candidate.event_time is not None:
        return candidate.event_time
    if bundle_created_at is not None:
        return bundle_created_at
    return datetime.now(UTC)


def seed_from_bundles(
    db: Session,
    bundle_ids: list[UUID],
    workspace_id: UUID | None = None,
) -> SeedFromBundlesResult:
    """Seed companies and core events from evidence bundle(s).

    For each bundle: load bundle (workspace-scoped if workspace_id set), parse
    structured_payload, resolve or create company from payload.company, then
    store one SignalEvent per payload.events with source=watchlist_seeder and
    source_event_id={bundle_id}:{index} for idempotent dedupe.

    Pack-agnostic: no pack dependency for event processing.

    Workspace / tenant: When exposing bundle-by-id to users or per-tenant APIs,
    call with workspace_id so bundles are loaded via get_bundle_for_workspace and
    tenant boundaries are enforced. When workspace_id is omitted, get_bundle() is
    used and does not filter by workspace; the caller is responsible for not
    passing other tenants' bundle IDs.
    """
    result = SeedFromBundlesResult()

    for bundle_id in bundle_ids:
        if workspace_id is not None:
            bundle_read = get_bundle_for_workspace(db, bundle_id, workspace_id)
        else:
            bundle_read = get_bundle(db, bundle_id)

        if bundle_read is None:
            result.errors.append(f"Bundle not found or not in workspace: {bundle_id}")
            continue

        raw = bundle_read.structured_payload
        if not raw:
            result.errors.append(f"Bundle {bundle_id} has no structured_payload")
            continue

        # M2: Accept both StructuredExtractionPayload (events) and ExtractionResult
        # (core_event_candidates) shapes. Build normalized dict with only allowed keys
        # so model_validate does not fail on extra keys (e.g. core_event_candidates).
        if ("events" in raw and not isinstance(raw.get("events"), list)) or (
            "core_event_candidates" in raw
            and not isinstance(raw.get("core_event_candidates"), list)
        ):
            result.errors.append(
                f"Bundle {bundle_id} invalid structured_payload: events/core_event_candidates must be a list"
            )
            continue
        events_list = get_events_from_payload(raw)
        persons_list = raw.get("persons")
        if not isinstance(persons_list, list) and isinstance(raw.get("person"), dict):
            persons_list = [raw["person"]]
        elif not isinstance(persons_list, list):
            persons_list = []
        claims_list = raw.get("claims")
        if not isinstance(claims_list, list):
            claims_list = []
        normalized = {
            "version": raw.get("version", "1.0"),
            "events": events_list,
            "company": raw.get("company"),
            "persons": persons_list,
            "claims": claims_list,
        }
        try:
            payload = StructuredExtractionPayload.model_validate(normalized)
        except Exception as e:
            result.errors.append(f"Bundle {bundle_id} invalid structured_payload: {e!s}")
            continue

        if payload.company is None:
            result.errors.append(f"Bundle {bundle_id} has no company in structured_payload")
            continue

        if not payload.events:
            result.errors.append(f"Bundle {bundle_id} has no events in structured_payload")
            continue

        company_create = _company_from_extraction(payload.company)
        company, created = resolve_or_create_company(db, company_create)
        if created:
            result.companies_created += 1
            logger.info(
                "Seeder created company company_id=%s bundle_id=%s name=%s",
                company.id,
                bundle_id,
                company.name,
            )
        else:
            result.companies_matched += 1
            logger.info(
                "Seeder matched company company_id=%s bundle_id=%s name=%s",
                company.id,
                bundle_id,
                company.name,
            )

        for i, candidate in enumerate(payload.events):
            event_time = _event_time_for_candidate(candidate, bundle_read.created_at)
            source_event_id = f"{bundle_id}:{i}"
            stored = store_signal_event(
                db,
                company_id=company.id,
                source=SOURCE_WATCHLIST_SEEDER,
                source_event_id=source_event_id,
                event_type=candidate.event_type,
                event_time=event_time,
                title=candidate.title,
                summary=candidate.summary,
                url=candidate.url,
                raw=None,
                confidence=candidate.confidence,
                pack_id=None,
                evidence_bundle_id=bundle_id,
            )
            if stored is not None:
                result.events_stored += 1
                logger.debug(
                    "Seeder stored event bundle_id=%s company_id=%s event_type=%s source_event_id=%s",
                    bundle_id,
                    company.id,
                    candidate.event_type,
                    source_event_id,
                )
            else:
                result.events_skipped_duplicate += 1

    return result
