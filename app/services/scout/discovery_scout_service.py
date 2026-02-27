"""Discovery Scout Service — orchestrate query planning, LLM, validation, persistence.

Evidence-Only: does NOT call resolve_or_create_company, store_signal_event, or deriver.
Per plan Step 5 / M4. Citation requirement enforced via EvidenceBundle schema (Step 7).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core_taxonomy.loader import load_core_taxonomy
from app.llm.router import ModelRole, get_llm_provider
from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from app.prompts.loader import render_prompt
from app.schemas.scout import EvidenceBundle

logger = logging.getLogger(__name__)


class DiscoveryScoutService:
    """Orchestrates query planning, LLM, validation, persistence. Evidence-Only; no company/event writes."""

    @staticmethod
    def run(
        db: Session,
        icp_definition: str,
        exclusion_rules: str | None = None,
        pack_id: str | None = None,
        page_fetch_limit: int = 10,
    ) -> dict:
        """Delegate to module-level run()."""
        return run(db, icp_definition, exclusion_rules, pack_id, page_fetch_limit)


def run(
    db: Session,
    icp_definition: str,
    exclusion_rules: str | None = None,
    pack_id: str | None = None,
    page_fetch_limit: int = 10,
) -> dict:
    """Run discovery scout: plan queries, call LLM, validate bundles, persist to scout tables only.

    Does not write to companies, signal_events, or signal_instances.

    Returns:
        dict with run_id (str), bundles_count (int), status (str), error (str | None).
    """
    run_uuid = uuid4()
    started_at = datetime.now(UTC)
    settings = get_settings()
    allowlist = list(settings.scout_source_allowlist)
    denylist = list(settings.scout_source_denylist)

    # 1) Query planning (read-only)
    from app.scout.query_planner import plan as plan_queries

    core_rubric = load_core_taxonomy()
    queries = plan_queries(icp_definition.strip(), core_rubric, pack_id)
    query_context = "; ".join(queries[:5])

    # 2) Page fetch count: no URL list in this minimal path; use 0 (LLM gets query context only)
    page_fetch_count = 0

    # 3) Build prompt and call LLM
    try:
        prompt = render_prompt(
            "scout_evidence_bundle_v1",
            ICP_DEFINITION=icp_definition.strip(),
            EXCLUSION_RULES=exclusion_rules or "",
            QUERY_CONTEXT=query_context,
        )
    except FileNotFoundError as e:
        logger.error("Scout prompt not found: %s", e)
        _persist_run(
            db,
            run_uuid,
            started_at,
            model_version="",
            tokens_used=None,
            latency_ms=None,
            page_fetch_count=0,
            config_snapshot={
                "icp": icp_definition[:500],
                "query_count": len(queries),
                "allowlist_ref": "config",
                "denylist_ref": "config",
            },
            status="failed",
            error_message=str(e),
            bundles=[],
        )
        logger.info(
            "Scout run completed run_id=%s status=failed bundles_count=0",
            run_uuid,
        )
        return {
            "run_id": str(run_uuid),
            "bundles_count": 0,
            "status": "failed",
            "error": str(e),
        }

    llm = get_llm_provider(role=ModelRole.REASONING)
    model_version = getattr(llm, "model", "unknown") or "unknown"
    t0 = time.monotonic()
    raw_response = llm.complete(
        prompt,
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    # LLM provider returns str; usage may be on a different attribute in some providers
    tokens_used = getattr(llm, "last_usage", None) or getattr(raw_response, "usage", None)
    if tokens_used is not None and hasattr(tokens_used, "total_tokens"):
        tokens_used = tokens_used.total_tokens
    else:
        tokens_used = None

    # 4) Parse and validate (citation enforced by EvidenceBundle model_validator)
    bundles: list[EvidenceBundle] = []
    parsed: dict | None = None
    try:
        parsed = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
        raw_bundles = parsed.get("bundles") or []
        if not isinstance(raw_bundles, list):
            raise ValueError("bundles must be an array")
        for item in raw_bundles:
            if not isinstance(item, dict):
                continue
            try:
                b = EvidenceBundle.model_validate(item)
                bundles.append(b)
            except Exception as e:
                logger.warning("Scout bundle validation failed (skipping): %s", e)
    except (json.JSONDecodeError, ValueError) as e:
        logger.exception("Scout LLM output parse failed: %s", e)
        _persist_run(
            db,
            run_uuid,
            started_at,
            model_version=model_version,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            page_fetch_count=page_fetch_count,
            config_snapshot={
                "icp": icp_definition[:500],
                "query_count": len(queries),
                "allowlist_ref": "config",
                "denylist_ref": "config",
            },
            status="failed",
            error_message=str(e),
            bundles=[],
            raw_llm_output={"raw_preview": str(raw_response)[:2000] if raw_response else None},
        )
        logger.info(
            "Scout run completed run_id=%s status=failed bundles_count=0",
            run_uuid,
        )
        return {
            "run_id": str(run_uuid),
            "bundles_count": 0,
            "status": "failed",
            "error": str(e),
        }

    # 5) Persist (scout tables only)
    _persist_run(
        db,
        run_uuid,
        started_at,
        model_version=model_version,
        tokens_used=tokens_used,
        latency_ms=latency_ms,
        page_fetch_count=page_fetch_count,
        config_snapshot={
            "icp": icp_definition[:500],
            "query_count": len(queries),
            "allowlist_ref": "config",
            "denylist_ref": "config",
        },
        status="completed",
        error_message=None,
        bundles=bundles,
        raw_llm_output=parsed if (bundles and parsed is not None) else None,
    )

    logger.info(
        "Scout run completed run_id=%s status=completed bundles_count=%s",
        run_uuid,
        len(bundles),
    )
    return {
        "run_id": str(run_uuid),
        "bundles_count": len(bundles),
        "status": "completed",
        "error": None,
    }


def _persist_run(
    db: Session,
    run_uuid: UUID,
    started_at: datetime,
    model_version: str,
    tokens_used: int | None,
    latency_ms: int | None,
    page_fetch_count: int,
    config_snapshot: dict | None,
    status: str,
    error_message: str | None,
    bundles: list[EvidenceBundle],
    raw_llm_output: dict | None = None,
) -> None:
    """Persist ScoutRun and ScoutEvidenceBundle rows. No companies/signal_events."""
    finished_at = datetime.now(UTC)
    run_row = ScoutRun(
        run_id=run_uuid,
        started_at=started_at,
        finished_at=finished_at,
        model_version=model_version or "unknown",
        tokens_used=tokens_used,
        latency_ms=latency_ms,
        page_fetch_count=page_fetch_count,
        config_snapshot=config_snapshot,
        status=status,
        error_message=error_message,
    )
    db.add(run_row)
    db.flush()

    for idx, b in enumerate(bundles):
        # Evidence: list of dicts for JSONB (Pydantic model_dump)
        evidence_data = [e.model_dump(mode="json") for e in b.evidence]
        missing_data = list(b.missing_information)
        bundle_row = ScoutEvidenceBundle(
            scout_run_id=run_row.id,
            candidate_company_name=b.candidate_company_name,
            company_website=b.company_website,
            why_now_hypothesis=b.why_now_hypothesis or "",
            evidence=evidence_data,
            missing_information=missing_data,
            raw_llm_output=raw_llm_output if (raw_llm_output and idx == 0) else None,
        )
        db.add(bundle_row)

    db.commit()
