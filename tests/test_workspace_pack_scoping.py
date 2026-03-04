"""Issue #193: Workspace and pack scoping integration tests (M4).

Cross-tenant: API/service calls with workspace_id=A must never return B's data.
Cross-pack: Queries with pack_id=B must not return pack A's signals/snapshots/leads.
Scoping removal: Tests assert that result sets do not contain other workspace/pack
data; removing the workspace_id or pack_id filter would cause these tests to fail.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.api.briefing_views import get_briefing_data
from app.evidence.repository import get_bundle_for_workspace
from app.evidence.store import store_evidence_bundle
from app.models import (
    AnalysisRecord,
    BriefingItem,
    Company,
    ScoutRun,
    Workspace,
)
from app.schemas.scout import EvidenceBundle, EvidenceItem
from app.services.lead_feed import get_leads_from_feed, upsert_lead_feed_row


def _make_evidence_item(url: str, snippet: str) -> EvidenceItem:
    return EvidenceItem(
        url=url,
        quoted_snippet=snippet,
        timestamp_seen=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        source_type="web",
        confidence_score=0.9,
    )


# ── Cross-tenant: LeadFeed ───────────────────────────────────────────────────


@pytest.mark.integration
def test_cross_tenant_lead_feed_returns_only_workspace_data(
    db: Session,
    fractional_cto_pack_id: UUID,
) -> None:
    """get_leads_from_feed(workspace_id=A) must not return rows belonging to workspace B."""
    ws_a = Workspace(name="Workspace A")
    ws_b = Workspace(name="Workspace B")
    db.add_all([ws_a, ws_b])
    db.commit()
    db.refresh(ws_a)
    db.refresh(ws_b)

    company_a = Company(name="Co A", website_url="https://coa.example.com")
    company_b = Company(name="Co B", website_url="https://cob.example.com")
    db.add_all([company_a, company_b])
    db.commit()
    db.refresh(company_a)
    db.refresh(company_b)

    as_of = date(2099, 3, 1)
    upsert_lead_feed_row(
        db,
        str(ws_a.id),
        fractional_cto_pack_id,
        company_a.id,
        composite_score=80,
        as_of=as_of,
    )
    upsert_lead_feed_row(
        db,
        str(ws_b.id),
        fractional_cto_pack_id,
        company_b.id,
        composite_score=70,
        as_of=as_of,
    )
    db.commit()

    leads_a = get_leads_from_feed(
        db,
        workspace_id=ws_a.id,
        pack_id=fractional_cto_pack_id,
        as_of=as_of,
        limit=50,
    )
    entity_ids_a = {lead["entity_id"] for lead in leads_a}

    assert company_a.id in entity_ids_a
    assert company_b.id not in entity_ids_a, (
        "Workspace B's lead must not appear when querying for workspace A"
    )


# ── Cross-tenant: BriefingItem ────────────────────────────────────────────────


@pytest.mark.integration
def test_cross_tenant_briefing_items_scoped_by_workspace(
    db: Session,
    fractional_cto_pack_id: UUID,
) -> None:
    """get_briefing_data(workspace_id=A) must only return BriefingItems for workspace A."""
    ws_a = Workspace(name="Briefing WS A")
    ws_b = Workspace(name="Briefing WS B")
    db.add_all([ws_a, ws_b])
    db.commit()
    db.refresh(ws_a)
    db.refresh(ws_b)

    company_a = Company(name="Brief Co A", website_url="https://briefa.example.com")
    company_b = Company(name="Brief Co B", website_url="https://briefb.example.com")
    db.add_all([company_a, company_b])
    db.commit()
    db.refresh(company_a)
    db.refresh(company_b)

    analysis_a = AnalysisRecord(
        company_id=company_a.id,
        source_type="manual",
        stage="seed",
        pack_id=fractional_cto_pack_id,
    )
    analysis_b = AnalysisRecord(
        company_id=company_b.id,
        source_type="manual",
        stage="seed",
        pack_id=fractional_cto_pack_id,
    )
    db.add_all([analysis_a, analysis_b])
    db.commit()
    db.refresh(analysis_a)
    db.refresh(analysis_b)

    briefing_date = date(2099, 3, 2)
    item_a = BriefingItem(
        company_id=company_a.id,
        analysis_id=analysis_a.id,
        workspace_id=ws_a.id,
        briefing_date=briefing_date,
    )
    item_b = BriefingItem(
        company_id=company_b.id,
        analysis_id=analysis_b.id,
        workspace_id=ws_b.id,
        briefing_date=briefing_date,
    )
    db.add_all([item_a, item_b])
    db.commit()

    data_a = get_briefing_data(db, briefing_date, workspace_id=str(ws_a.id))
    items_a = data_a["items"]

    assert len(items_a) >= 1
    for item in items_a:
        assert item.workspace_id == ws_a.id, (
            "Briefing data for workspace A must not include workspace B items"
        )
    company_ids_a = {item.company_id for item in items_a}
    assert company_b.id not in company_ids_a


# ── Cross-tenant: Evidence bundle ──────────────────────────────────────────────


@pytest.mark.integration
def test_cross_tenant_evidence_bundle_for_workspace_returns_none_for_other_workspace(
    db: Session,
) -> None:
    """get_bundle_for_workspace(bundle_id, workspace_id=B) returns None when run belongs to A."""
    ws_a = Workspace(name="Evidence WS A")
    ws_b = Workspace(name="Evidence WS B")
    db.add_all([ws_a, ws_b])
    db.commit()
    db.refresh(ws_a)
    db.refresh(ws_b)

    run_a = ScoutRun(
        run_id=uuid4(),
        workspace_id=ws_a.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        status="completed",
    )
    db.add(run_a)
    db.commit()
    db.refresh(run_a)

    bundle_schema = EvidenceBundle(
        candidate_company_name="Evidence Co",
        company_website="https://evidence.example.com",
        why_now_hypothesis="Test",
        evidence=[_make_evidence_item("https://ev.example.com", "snippet")],
    )
    run_context = {"run_id": str(run_a.run_id)}
    records = store_evidence_bundle(
        db,
        run_id=str(run_a.run_id),
        scout_version="scout-v1",
        bundles=[bundle_schema],
        run_context=run_context,
        raw_model_output=None,
    )
    db.commit()
    assert len(records) == 1
    bundle_id = records[0].id

    result_b = get_bundle_for_workspace(db, bundle_id, ws_b.id)
    assert result_b is None, (
        "Bundle whose run belongs to workspace A must not be returned for workspace B"
    )

    result_a = get_bundle_for_workspace(db, bundle_id, ws_a.id)
    assert result_a is not None
    assert result_a.id == bundle_id


# ── Cross-pack: LeadFeed ──────────────────────────────────────────────────────


@pytest.mark.integration
def test_cross_pack_lead_feed_returns_only_pack_data(
    db: Session,
    fractional_cto_pack_id: UUID,
    second_pack_id: UUID,
) -> None:
    """get_leads_from_feed(..., pack_id=A) must not return pack B's lead rows."""
    ws = Workspace(name="Pack Scope WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    company_cto = Company(name="CTO Co", website_url="https://ctopack.example.com")
    company_other = Company(name="Other Pack Co", website_url="https://otherpack.example.com")
    db.add_all([company_cto, company_other])
    db.commit()
    db.refresh(company_cto)
    db.refresh(company_other)

    as_of = date(2099, 3, 3)
    upsert_lead_feed_row(
        db,
        str(ws.id),
        fractional_cto_pack_id,
        company_cto.id,
        composite_score=85,
        as_of=as_of,
    )
    upsert_lead_feed_row(
        db,
        str(ws.id),
        second_pack_id,
        company_other.id,
        composite_score=75,
        as_of=as_of,
    )
    db.commit()

    leads_cto = get_leads_from_feed(
        db,
        workspace_id=ws.id,
        pack_id=fractional_cto_pack_id,
        as_of=as_of,
        limit=50,
    )
    entity_ids_cto = {lead["entity_id"] for lead in leads_cto}

    assert company_cto.id in entity_ids_cto
    assert company_other.id not in entity_ids_cto, (
        "Pack B's lead must not appear when querying for pack A"
    )


# ── Scoping removal regression ─────────────────────────────────────────────────


@pytest.mark.integration
def test_scoping_removal_would_fail_cross_tenant(
    db: Session,
    fractional_cto_pack_id: UUID,
) -> None:
    """Assert result set does not contain rows from other workspace.

    This test would fail if the workspace_id filter were removed from the
    lead_feed query: we explicitly assert that no entity from workspace B
    appears when querying for workspace A.
    """
    ws_a = Workspace(name="Scoping Regress A")
    ws_b = Workspace(name="Scoping Regress B")
    db.add_all([ws_a, ws_b])
    db.commit()
    db.refresh(ws_a)
    db.refresh(ws_b)

    company_b = Company(name="Only In B", website_url="https://onlyb.example.com")
    db.add(company_b)
    db.commit()
    db.refresh(company_b)

    as_of = date(2099, 3, 4)
    upsert_lead_feed_row(
        db,
        str(ws_b.id),
        fractional_cto_pack_id,
        company_b.id,
        composite_score=90,
        as_of=as_of,
    )
    db.commit()

    leads_a = get_leads_from_feed(
        db,
        workspace_id=ws_a.id,
        pack_id=fractional_cto_pack_id,
        as_of=as_of,
        limit=50,
    )
    entity_ids_returned = {lead["entity_id"] for lead in leads_a}

    assert company_b.id not in entity_ids_returned, (
        "Removing workspace_id filter would leak workspace B data into workspace A query; "
        "this assertion enforces tenant isolation (Issue #193)."
    )
