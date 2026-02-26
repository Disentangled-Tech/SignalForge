"""Ranked companies service for GET /api/companies/top (Issue #247, Phase 1).

Thin wrapper over get_emerging_companies_for_briefing. Maps (RS, ES, Company)
to RankedCompanyTop DTOs for the API.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.config import get_settings
from app.pipeline.stages import DEFAULT_WORKSPACE_ID
from app.schemas.ranked_companies import RankedCompanyTop
from app.services.briefing import get_emerging_companies_for_briefing
from app.services.pack_resolver import get_pack_for_workspace, resolve_pack
from app.services.readiness.human_labels import event_type_to_label


def get_ranked_companies_for_api(
    db: Session,
    as_of: date,
    *,
    limit: int = 10,
    outreach_score_threshold: int | None = None,
    workspace_id: str | None = None,
) -> list[RankedCompanyTop]:
    """Get ranked companies for API (Issue #247).

    Reuses get_emerging_companies_for_briefing. Returns list of RankedCompanyTop
    with company_id, company_name, website_url, composite_score, recommendation_band,
    top_signals, and optional dimension breakdown (momentum, complexity, pressure,
    leadership_gap).

    When no companies qualify: returns []. No exception.
    """
    settings = get_settings()
    threshold = (
        outreach_score_threshold
        if outreach_score_threshold is not None
        else settings.outreach_score_threshold
    )
    triples = get_emerging_companies_for_briefing(
        db,
        as_of,
        limit=limit,
        outreach_score_threshold=threshold,
        workspace_id=workspace_id,
    )
    ws_id = workspace_id or DEFAULT_WORKSPACE_ID
    pack_id = get_pack_for_workspace(db, ws_id)
    pack = resolve_pack(db, pack_id) if pack_id else None

    result: list[RankedCompanyTop] = []
    for rs, _es, company in triples:
        top_events = (getattr(rs, "explain", None) or {}).get("top_events") or []
        top_signals = [
            event_type_to_label(
                ev.get("event_type", "") if isinstance(ev, dict) else "",
                pack=pack,
            )
            for ev in top_events[:3]
        ]
        recommendation_band = None
        explain = getattr(rs, "explain", None) or {}
        band_val = explain.get("recommendation_band")
        if band_val in ("IGNORE", "WATCH", "HIGH_PRIORITY"):
            recommendation_band = band_val

        momentum = getattr(rs, "momentum", None)
        complexity = getattr(rs, "complexity", None)
        pressure = getattr(rs, "pressure", None)
        leadership_gap = getattr(rs, "leadership_gap", None)

        result.append(
            RankedCompanyTop(
                company_id=company.id,
                company_name=company.name or "Unknown",
                website_url=company.website_url,
                composite_score=getattr(rs, "composite", 0),
                recommendation_band=recommendation_band,
                top_signals=top_signals,
                momentum=momentum,
                complexity=complexity,
                pressure=pressure,
                leadership_gap=leadership_gap,
            )
        )
    return result
