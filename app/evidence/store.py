"""Evidence Store write path (M3, Issue #276). Insert-only; versioning; source dedupe; claims; quarantine (M5)."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.orm import Session

from app.core_derivers.loader import get_core_derivers_version
from app.core_taxonomy.loader import get_core_taxonomy_version
from app.models.evidence_bundle import EvidenceBundle as EvidenceBundleORM
from app.models.evidence_bundle_source import EvidenceBundleSource
from app.models.evidence_claim import EvidenceClaim
from app.models.evidence_quarantine import EvidenceQuarantine
from app.models.evidence_source import EvidenceSource
from app.schemas.evidence import EvidenceBundleRecord
from app.schemas.scout import EvidenceBundle as ScoutEvidenceBundle


def _content_hash(snippet: str) -> str:
    """SHA-256 hex digest of snippet for source deduplication."""
    return hashlib.sha256(snippet.encode("utf-8")).hexdigest()


def _get_or_create_source(
    db: Session,
    url: str,
    snippet: str,
    source_type: str,
    retrieved_at,
) -> EvidenceSource:
    """Lookup EvidenceSource by (content_hash, url); create if missing."""
    content_hash = _content_hash(snippet)
    existing = (
        db.query(EvidenceSource)
        .filter(
            EvidenceSource.content_hash == content_hash,
            EvidenceSource.url == url,
        )
        .first()
    )
    if existing is not None:
        return existing
    source = EvidenceSource(
        url=url,
        retrieved_at=retrieved_at,
        snippet=snippet,
        content_hash=content_hash,
        source_type=source_type,
    )
    db.add(source)
    db.flush()
    return source


def _quarantine(db: Session, payload: dict, reason: str) -> None:
    """Insert one row into evidence_quarantine (M5). Caller must flush/commit as needed."""
    row = EvidenceQuarantine(payload=payload, reason=reason)
    db.add(row)
    db.flush()


def store_evidence_bundle(
    db: Session,
    run_id: str,
    scout_version: str,
    bundles: list[ScoutEvidenceBundle],
    run_context: dict | None,
    raw_model_output: dict | None,
    structured_payloads: list[dict | None] | None = None,
    pack_id: uuid.UUID | None = None,
) -> list[EvidenceBundleRecord]:
    """Persist Scout evidence bundles (insert-only). Injects core versions; dedupes sources; optional claims.

    For each bundle: inserts evidence_bundles row; for each EvidenceItem, get-or-create
    EvidenceSource by (content_hash, url) and link via evidence_bundle_sources; if
    structured_payloads[i] has "claims", inserts evidence_claims with source_ids
    resolved from source_refs (0-based indices into bundle.evidence).

    Returns:
        List of EvidenceBundleRecord (one per inserted bundle), in same order as bundles.
    """
    if not bundles:
        return []

    core_taxonomy_version = get_core_taxonomy_version()
    core_derivers_version = get_core_derivers_version()

    if structured_payloads is not None and len(structured_payloads) != len(bundles):
        _quarantine(
            db,
            payload={
                "run_id": run_id,
                "scout_version": scout_version,
                "bundles": [b.model_dump(mode="json") for b in bundles],
                "run_context": run_context,
                "raw_model_output": raw_model_output,
                "structured_payloads": structured_payloads,
            },
            reason="structured_payloads length must match bundles when provided",
        )
        raise ValueError("structured_payloads length must match bundles when provided")

    records: list[EvidenceBundleRecord] = []

    for i, bundle in enumerate(bundles):
        payload = (
            structured_payloads[i]
            if structured_payloads is not None and i < len(structured_payloads)
            else None
        )
        try:
            # Persist sources (dedupe by content_hash + url) and collect source ids in evidence order
            source_ids_in_order: list[uuid.UUID] = []
            for item in bundle.evidence:
                source = _get_or_create_source(
                    db,
                    url=item.url,
                    snippet=item.quoted_snippet,
                    source_type=item.source_type,
                    retrieved_at=item.timestamp_seen,
                )
                source_ids_in_order.append(source.id)

            # Insert bundle (append-only; no updated_at)
            row = EvidenceBundleORM(
                scout_version=scout_version,
                core_taxonomy_version=core_taxonomy_version,
                core_derivers_version=core_derivers_version,
                pack_id=pack_id,
                run_context=run_context,
                raw_model_output=raw_model_output,
                structured_payload=payload,
            )
            db.add(row)
            db.flush()

            # Link bundle to sources
            for sid in source_ids_in_order:
                link = EvidenceBundleSource(bundle_id=row.id, source_id=sid)
                db.add(link)
            db.flush()

            # Optional claims from structured_payload
            if payload and isinstance(payload.get("claims"), list):
                for c in payload["claims"]:
                    if not isinstance(c, dict):
                        continue
                    entity_type = c.get("entity_type") or "entity"
                    field = c.get("field") or ""
                    value = c.get("value")
                    source_refs = c.get("source_refs")
                    confidence = c.get("confidence")
                    if isinstance(source_refs, list):
                        resolved_ids = []
                        for ref in source_refs:
                            if isinstance(ref, int) and 0 <= ref < len(source_ids_in_order):
                                resolved_ids.append(str(source_ids_in_order[ref]))
                        claim = EvidenceClaim(
                            bundle_id=row.id,
                            entity_type=str(entity_type)[:64],
                            field=str(field)[:255],
                            value=str(value) if value is not None else None,
                            source_ids=resolved_ids or None,
                            confidence=float(confidence) if confidence is not None else None,
                        )
                        db.add(claim)
            db.flush()

            records.append(
                EvidenceBundleRecord(
                    id=row.id,
                    created_at=row.created_at,
                    scout_version=row.scout_version,
                    core_taxonomy_version=row.core_taxonomy_version,
                    core_derivers_version=row.core_derivers_version,
                )
            )
        except Exception as e:
            _quarantine(
                db,
                payload={
                    "run_id": run_id,
                    "scout_version": scout_version,
                    "bundle_index": i,
                    "bundle": bundle.model_dump(mode="json"),
                    "run_context": run_context,
                    "raw_model_output": raw_model_output,
                    "structured_payload": payload,
                },
                reason=str(e),
            )
            raise

    return records
