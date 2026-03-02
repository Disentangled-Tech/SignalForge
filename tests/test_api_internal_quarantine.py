"""Tests for GET /internal/evidence/quarantine and GET /internal/evidence/quarantine/{id} (M4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.models.evidence_quarantine import EvidenceQuarantine
from tests.test_internal import VALID_TOKEN


def test_list_quarantine_missing_token_returns_422(client: TestClient) -> None:
    """GET /internal/evidence/quarantine without X-Internal-Token returns 422."""
    response = client.get("/internal/evidence/quarantine")
    assert response.status_code == 422


def test_list_quarantine_wrong_token_returns_403(client: TestClient) -> None:
    """GET /internal/evidence/quarantine with wrong token returns 403."""
    response = client.get(
        "/internal/evidence/quarantine",
        headers={"X-Internal-Token": "wrong-token"},
    )
    assert response.status_code == 403


def test_list_quarantine_valid_token_returns_entries(client_with_db: TestClient) -> None:
    """GET /internal/evidence/quarantine with valid token returns entries and count."""
    response = client_with_db.get(
        "/internal/evidence/quarantine",
        headers={"X-Internal-Token": VALID_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert "entries" in data
    assert "count" in data
    assert isinstance(data["entries"], list)
    assert data["count"] == len(data["entries"])


def test_list_quarantine_returns_reason_codes_when_in_payload(
    client_with_db: TestClient,
    db,
) -> None:
    """List response includes reason_codes when payload contains reason_codes."""
    payload = {
        "run_id": "r1",
        "bundle_index": 0,
        "reason_codes": ["EVENT_TYPE_UNKNOWN", "EVENT_MISSING_TIMESTAMPED_CITATION"],
    }
    row = EvidenceQuarantine(payload=payload, reason="Event type unknown; missing citation")
    db.add(row)
    db.commit()

    response = client_with_db.get(
        "/internal/evidence/quarantine",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"limit": 10},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    found = next((e for e in data["entries"] if e.get("reason_codes")), None)
    assert found is not None
    assert found["reason_codes"] == ["EVENT_TYPE_UNKNOWN", "EVENT_MISSING_TIMESTAMPED_CITATION"]


def test_list_quarantine_filter_by_reason_substring(
    client_with_db: TestClient,
    db,
) -> None:
    """List with reason_substring filters by reason (case-insensitive)."""
    unique = "UniqueFilterReasonM4XYZ"
    row1 = EvidenceQuarantine(payload={"run_id": "r1"}, reason=f"Domain {unique} mismatch")
    row2 = EvidenceQuarantine(payload={"run_id": "r2"}, reason="Length mismatch")
    db.add(row1)
    db.add(row2)
    db.commit()

    response = client_with_db.get(
        "/internal/evidence/quarantine",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"limit": 10, "reason_substring": unique},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    assert all(unique in (e.get("reason") or "") for e in data["entries"])


def test_list_quarantine_filter_by_since_returns_only_entries_on_or_after_since(
    client_with_db: TestClient,
    db,
) -> None:
    """List with since= returns only entries with created_at >= since (ISO 8601)."""
    from sqlalchemy import text

    t_old = datetime(2026, 2, 1, 10, 0, 0, tzinfo=UTC)
    t_new = datetime(2026, 2, 2, 12, 0, 0, tzinfo=UTC)
    row_old = EvidenceQuarantine(payload={"run_id": "since_test_old"}, reason="Old entry")
    row_new = EvidenceQuarantine(payload={"run_id": "since_test_new"}, reason="New entry")
    db.add(row_old)
    db.add(row_new)
    db.flush()
    db.execute(
        text("UPDATE evidence_quarantine SET created_at = :t WHERE id = :id"),
        {"t": t_old, "id": row_old.id},
    )
    db.execute(
        text("UPDATE evidence_quarantine SET created_at = :t WHERE id = :id"),
        {"t": t_new, "id": row_new.id},
    )
    db.commit()

    since_param = "2026-02-01T10:00:01Z"
    response = client_with_db.get(
        "/internal/evidence/quarantine",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"limit": 50, "since": since_param},
    )
    assert response.status_code == 200
    data = response.json()
    run_ids = [e["payload"].get("run_id") for e in data["entries"]]
    assert "since_test_new" in run_ids
    assert "since_test_old" not in run_ids
    for e in data["entries"]:
        created = e.get("created_at")
        if created:
            assert created >= "2026-02-01T10:00:01", (
                f"Entry {e.get('id')} has created_at {created} before since"
            )


def test_get_quarantine_missing_token_returns_422(client: TestClient) -> None:
    """GET /internal/evidence/quarantine/{id} without X-Internal-Token returns 422."""
    response = client.get(f"/internal/evidence/quarantine/{uuid.uuid4()}")
    assert response.status_code == 422


def test_get_quarantine_wrong_token_returns_403(client: TestClient) -> None:
    """GET /internal/evidence/quarantine/{id} with wrong token returns 403."""
    response = client.get(
        f"/internal/evidence/quarantine/{uuid.uuid4()}",
        headers={"X-Internal-Token": "wrong-token"},
    )
    assert response.status_code == 403


def test_get_quarantine_not_found_returns_404(client_with_db: TestClient) -> None:
    """GET /internal/evidence/quarantine/{id} with unknown id returns 404."""
    response = client_with_db.get(
        f"/internal/evidence/quarantine/{uuid.uuid4()}",
        headers={"X-Internal-Token": VALID_TOKEN},
    )
    assert response.status_code == 404
    assert response.json().get("detail") == "Quarantine entry not found"


def test_get_quarantine_success_returns_entry_with_reason_codes(
    client_with_db: TestClient,
    db,
) -> None:
    """Get by id returns entry with reason_codes when present in payload."""
    payload = {
        "run_id": "r2",
        "reason_codes": ["FACT_DOMAIN_MISMATCH"],
    }
    row = EvidenceQuarantine(payload=payload, reason="Domain mismatch")
    db.add(row)
    db.commit()
    db.refresh(row)
    qid = str(row.id)

    response = client_with_db.get(
        f"/internal/evidence/quarantine/{qid}",
        headers={"X-Internal-Token": VALID_TOKEN},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == qid
    assert data["reason"] == "Domain mismatch"
    assert data["reason_codes"] == ["FACT_DOMAIN_MISMATCH"]
    assert data["payload"] == payload
