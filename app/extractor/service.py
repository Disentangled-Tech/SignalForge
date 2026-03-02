"""Evidence Extractor service (M2, Issue #277): in-memory extraction only.

Converts Evidence Bundles into normalized entity fields (Company, Person) and
Core Event candidates. No signal derivation; no DB writes. Pack-agnostic.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from app.extractor.schemas import ExtractionResult
from app.schemas.core_events import (
    CoreEventCandidate,
    ExtractionEntityCompany,
    ExtractionEntityPerson,
)
from app.schemas.scout import EvidenceBundle

# Cap on core_event_candidates from raw_extraction (align with EvidenceBundle.evidence max_length)
MAX_CORE_EVENT_CANDIDATES = 50


def _domain_from_website_url(url: str) -> str | None:
    """Extract hostname (domain) from website URL for company domain field."""
    if not url or not url.strip():
        return None
    try:
        parsed = urlparse(url)
        netloc = (parsed.netloc or "").strip()
        if not netloc:
            return None
        # Remove port if present
        if ":" in netloc:
            netloc = netloc.split(":")[0]
        return netloc if netloc else None
    except (ValueError, TypeError):
        # urlparse can raise ValueError for invalid port; TypeError on non-string input
        return None


def _company_from_bundle(bundle: EvidenceBundle) -> ExtractionEntityCompany:
    """Build normalized company from bundle fields (source-backed by bundle)."""
    domain = _domain_from_website_url(bundle.company_website)
    return ExtractionEntityCompany(
        name=bundle.candidate_company_name,
        domain=domain,
        website_url=bundle.company_website,
    )


def _parse_raw_core_event_candidates(
    raw_list: list[dict[str, Any]],
    evidence_len: int,
) -> list[CoreEventCandidate]:
    """Parse and validate core_event_candidates from raw extraction; drop invalid."""
    candidates: list[CoreEventCandidate] = []
    for item in raw_list[:MAX_CORE_EVENT_CANDIDATES]:
        if not isinstance(item, dict):
            continue
        source_refs = item.get("source_refs")
        if isinstance(source_refs, list):
            valid_refs = [r for r in source_refs if isinstance(r, int) and 0 <= r < evidence_len]
            # Drop candidate if refs were provided but none valid (source-backed contract)
            if source_refs and not valid_refs:
                continue
            item = {**item, "source_refs": valid_refs}
        try:
            candidates.append(CoreEventCandidate.model_validate(item))
        except ValidationError:
            # Unknown event_type or validation error: drop this candidate
            continue
    return candidates


def extract(
    bundle: EvidenceBundle,
    raw_extraction: dict[str, Any] | None = None,
) -> ExtractionResult:
    """Extract normalized entities and core event candidates from an Evidence Bundle.

    In-memory only; no signal derivation; no DB writes. Pack-agnostic.

    Args:
        bundle: Scout Evidence Bundle (in-memory).
        raw_extraction: Optional LLM/API extraction dict with keys company, person,
            core_event_candidates. Validated against core taxonomy; unknown event
            types and invalid source_refs are dropped.

    Returns:
        ExtractionResult with company (from bundle or raw), person (from raw),
        and core_event_candidates (validated; invalid entries dropped).
    """
    evidence_len = len(bundle.evidence)

    company: ExtractionEntityCompany | None = None
    person: ExtractionEntityPerson | None = None
    core_event_candidates: list[CoreEventCandidate] = []

    if raw_extraction:
        raw_company = raw_extraction.get("company")
        if isinstance(raw_company, dict) and raw_company.get("name"):
            try:
                company = ExtractionEntityCompany.model_validate(raw_company)
            except ValidationError:
                pass
        if company is None:
            company = _company_from_bundle(bundle)

        raw_person = raw_extraction.get("person")
        if isinstance(raw_person, dict) and raw_person.get("name"):
            try:
                person = ExtractionEntityPerson.model_validate(raw_person)
            except ValidationError:
                pass

        raw_events = raw_extraction.get("core_event_candidates")
        if isinstance(raw_events, list):
            core_event_candidates = _parse_raw_core_event_candidates(
                raw_events[:MAX_CORE_EVENT_CANDIDATES],
                evidence_len,
            )
    else:
        company = _company_from_bundle(bundle)

    return ExtractionResult(
        company=company,
        person=person,
        core_event_candidates=core_event_candidates,
    )
