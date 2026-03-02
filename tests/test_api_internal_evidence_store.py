"""Tests for POST /internal/evidence/store — token auth, request body, stored bundles (M6)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.evidence.repository import get_bundle, list_bundles_by_run
from app.schemas.scout import EvidenceItem
from tests.test_internal import VALID_TOKEN


def _make_item(url: str, snippet: str, source_type: str = "web") -> EvidenceItem:
    return EvidenceItem(
        url=url,
        quoted_snippet=snippet,
        timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
        source_type=source_type,
        confidence_score=0.9,
    )


def _valid_store_body() -> dict:
    return {
        "run_id": "test-run-123",
        "bundles": [
            {
                "candidate_company_name": "Store Test Co",
                "company_website": "https://storetest.example.com",
                "why_now_hypothesis": "Seed round.",
                "evidence": [
                    {
                        "url": "https://storetest.example.com/news",
                        "quoted_snippet": "Seed round closed.",
                        "timestamp_seen": "2026-02-27T12:00:00Z",
                        "source_type": "news",
                        "confidence_score": 0.85,
                    }
                ],
                "missing_information": [],
            }
        ],
        "metadata": {
            "model_version": "gpt-4o-mini",
            "tokens_used": None,
            "latency_ms": None,
            "page_fetch_count": 0,
        },
        "run_context": {"run_id": "test-run-123", "icp_definition": "B2B"},
        "raw_model_output": None,
    }


def test_store_evidence_missing_token_returns_422(client: TestClient) -> None:
    """POST /internal/evidence/store without X-Internal-Token returns 422."""
    response = client.post(
        "/internal/evidence/store",
        json=_valid_store_body(),
    )
    assert response.status_code == 422


def test_store_evidence_wrong_token_returns_403(client: TestClient) -> None:
    """POST /internal/evidence/store with wrong token returns 403."""
    response = client.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": "wrong-token"},
        json=_valid_store_body(),
    )
    assert response.status_code == 403


def test_store_evidence_valid_body_returns_stored_count_and_bundle_ids(
    client_with_db: TestClient,
) -> None:
    """POST /internal/evidence/store with valid body returns status, stored_count, bundle_ids."""
    response = client_with_db.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=_valid_store_body(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["stored_count"] == 1
    assert len(data["bundle_ids"]) == 1
    assert data.get("error") is None


def test_store_evidence_invalid_body_returns_422(client: TestClient) -> None:
    """POST /internal/evidence/store returns 422 for invalid body (missing run_id or metadata)."""
    body = _valid_store_body()
    del body["run_id"]
    r1 = client.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body,
    )
    assert r1.status_code == 422

    body2 = _valid_store_body()
    del body2["metadata"]
    r2 = client.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body2,
    )
    assert r2.status_code == 422


def test_store_evidence_empty_bundles_returns_zero_stored(client_with_db: TestClient) -> None:
    """POST /internal/evidence/store with empty bundles returns stored_count 0."""
    body = _valid_store_body()
    body["bundles"] = []
    response = client_with_db.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["stored_count"] == 0
    assert data["bundle_ids"] == []


def test_store_evidence_stored_bundles_readable_via_repository(
    client_with_db: TestClient,
    db,
) -> None:
    """After POST /internal/evidence/store, get_bundle and list_bundles_by_run return stored data."""
    run_id = "repo-run-456"
    body = {
        "run_id": run_id,
        "bundles": [
            {
                "candidate_company_name": "Repo Store Co",
                "company_website": "https://repostore.example.com",
                "why_now_hypothesis": "",
                "evidence": [
                    {
                        "url": "https://repostore.example.com/about",
                        "quoted_snippet": "We build SaaS.",
                        "timestamp_seen": "2026-02-27T12:00:00Z",
                        "source_type": "web",
                        "confidence_score": 0.8,
                    }
                ],
                "missing_information": [],
            }
        ],
        "metadata": {
            "model_version": "gpt-4o",
            "tokens_used": None,
            "latency_ms": None,
            "page_fetch_count": 0,
        },
        "run_context": {"run_id": run_id, "source": "api"},
        "raw_model_output": None,
    }
    response = client_with_db.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stored_count"] == 1
    bundle_id_str = data["bundle_ids"][0]

    import uuid

    bundle_id = uuid.UUID(bundle_id_str)
    read = get_bundle(db, bundle_id)
    assert read is not None
    assert read.scout_version == "gpt-4o"
    assert read.run_context == {"run_id": run_id, "source": "api"}

    by_run = list_bundles_by_run(db, run_id)
    assert len(by_run) == 1
    assert by_run[0].id == bundle_id


def test_store_evidence_duplicate_same_run_id_creates_multiple_rows(
    client_with_db: TestClient,
    db,
) -> None:
    """POST /internal/evidence/store twice with same run_id creates multiple evidence rows (no overwrite)."""
    run_id = "dup-run-789"
    body = {
        "run_id": run_id,
        "bundles": [
            {
                "candidate_company_name": "First Co",
                "company_website": "https://first.example.com",
                "why_now_hypothesis": "",
                "evidence": [
                    {
                        "url": "https://first.example.com",
                        "quoted_snippet": "Snippet A.",
                        "timestamp_seen": "2026-02-27T12:00:00Z",
                        "source_type": "web",
                        "confidence_score": 0.8,
                    }
                ],
                "missing_information": [],
            }
        ],
        "metadata": {"model_version": "gpt-4o", "tokens_used": None, "latency_ms": None, "page_fetch_count": 0},
        "run_context": {"run_id": run_id},
        "raw_model_output": None,
    }
    r1 = client_with_db.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body,
    )
    assert r1.status_code == 200
    assert r1.json()["stored_count"] == 1
    body["bundles"][0]["candidate_company_name"] = "Second Co"
    body["bundles"][0]["evidence"][0]["quoted_snippet"] = "Snippet B."
    r2 = client_with_db.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body,
    )
    assert r2.status_code == 200
    assert r2.json()["stored_count"] == 1
    from app.evidence.repository import list_bundles_by_run

    bundles = list_bundles_by_run(db, run_id)
    assert len(bundles) == 2


def test_store_evidence_run_id_too_long_returns_422(client: TestClient) -> None:
    """POST /internal/evidence/store with run_id over 64 chars returns 422."""
    body = _valid_store_body()
    body["run_id"] = "x" * 65
    response = client.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body,
    )
    assert response.status_code == 422


def test_list_evidence_bundles_for_workspace_returns_only_for_that_workspace(
    client_with_db: TestClient,
    db,
) -> None:
    """GET /internal/evidence/bundles returns bundles only when run belongs to workspace (no cross-tenant)."""
    import uuid

    from app.models import ScoutRun, Workspace

    ws1 = Workspace(name="Evidence WS One")
    ws2 = Workspace(name="Evidence WS Two")
    db.add(ws1)
    db.add(ws2)
    db.flush()

    run_id_a = "aaaaaaaa-0000-4000-8000-000000000001"
    run_id_b = "bbbbbbbb-0000-4000-8000-000000000002"
    for rid, ws_id in [(run_id_a, ws1.id), (run_id_b, ws2.id)]:
        db.add(
            ScoutRun(
                run_id=uuid.UUID(rid),
                workspace_id=ws_id,
                model_version="test",
                page_fetch_count=0,
                status="completed",
            )
        )
    db.commit()

    # Store evidence for both runs via store endpoint (run_context.run_id = run_id)
    for run_id in (run_id_a, run_id_b):
        body = {
            "run_id": run_id,
            "bundles": [
                {
                    "candidate_company_name": f"Co for {run_id[:8]}",
                    "company_website": "https://example.com",
                    "why_now_hypothesis": "",
                    "evidence": [],
                    "missing_information": [],
                }
            ],
            "metadata": {"model_version": "gpt-4o", "tokens_used": None, "latency_ms": None, "page_fetch_count": 0},
            "run_context": {"run_id": run_id},
            "raw_model_output": None,
        }
        r = client_with_db.post(
            "/internal/evidence/store",
            headers={"X-Internal-Token": VALID_TOKEN},
            json=body,
        )
        assert r.status_code == 200, r.json()
        assert r.json()["stored_count"] == 1

    # List for ws1 with run_id_a -> 1 bundle; with run_id_b (run in ws2) -> 0
    resp_a = client_with_db.get(
        "/internal/evidence/bundles",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"run_id": run_id_a, "workspace_id": str(ws1.id)},
    )
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["count"] == 1
    assert len(data_a["bundles"]) == 1

    resp_b_wrong_ws = client_with_db.get(
        "/internal/evidence/bundles",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"run_id": run_id_b, "workspace_id": str(ws1.id)},
    )
    assert resp_b_wrong_ws.status_code == 200
    assert resp_b_wrong_ws.json()["count"] == 0
    assert resp_b_wrong_ws.json()["bundles"] == []


# ─── M6: Optional verification on POST /internal/evidence/store ─────────────────


def test_store_evidence_with_verification_failing_bundle_quarantined_not_stored(
    client_with_db: TestClient,
    db,
) -> None:
    """POST /internal/evidence/store with run_verification=True: failing bundle quarantined with reason_codes, not stored."""
    run_id = "m6-verify-fail-run"
    body = {
        "run_id": run_id,
        "bundles": [
            {
                "candidate_company_name": "Pass Co",
                "company_website": "https://pass.example.com",
                "why_now_hypothesis": "Seed.",
                "evidence": [
                    {
                        "url": "https://pass.example.com/news",
                        "quoted_snippet": "Seed round.",
                        "timestamp_seen": "2026-02-27T12:00:00Z",
                        "source_type": "web",
                        "confidence_score": 0.9,
                    }
                ],
                "missing_information": [],
            },
            {
                "candidate_company_name": "Fail Co",
                "company_website": "https://fail.example.com",
                "why_now_hypothesis": "Hiring.",
                "evidence": [
                    {
                        "url": "https://fail.example.com/jobs",
                        "quoted_snippet": "CTO role.",
                        "timestamp_seen": "2026-02-27T12:00:00Z",
                        "source_type": "web",
                        "confidence_score": 0.8,
                    }
                ],
                "missing_information": [],
            },
        ],
        "metadata": {"model_version": "gpt-4o", "tokens_used": None, "latency_ms": None, "page_fetch_count": 0},
        "run_context": {"run_id": run_id},
        "raw_model_output": None,
        "run_verification": True,
        "structured_payloads": [
            {"events": [{"event_type": "funding_raised", "confidence": 0.9, "source_refs": [0]}]},
            {"events": [{"event_type": "not_in_taxonomy", "confidence": 0.9}]},
        ],
    }
    response = client_with_db.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["stored_count"] == 1
    assert data["quarantined_count"] == 1
    assert len(data["bundle_ids"]) == 1

    # Failing bundle must not be in evidence_bundles; only passing bundle stored
    from app.evidence.repository import list_bundles_by_run

    bundles = list_bundles_by_run(db, run_id)
    assert len(bundles) == 1
    assert bundles[0].structured_payload == body["structured_payloads"][0]

    # Quarantine must contain one entry with reason_codes
    list_resp = client_with_db.get(
        "/internal/evidence/quarantine",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"limit": 10},
    )
    assert list_resp.status_code == 200
    entries = list_resp.json()["entries"]
    assert len(entries) >= 1
    quarantine_entry = next((e for e in entries if e.get("payload", {}).get("run_id") == run_id), None)
    assert quarantine_entry is not None
    assert quarantine_entry["payload"].get("reason_codes") is not None
    assert "EVENT_TYPE_UNKNOWN" in quarantine_entry["payload"]["reason_codes"]
    assert quarantine_entry["payload"].get("bundle_index") == 1


def test_store_evidence_with_verification_all_pass_all_stored(
    client_with_db: TestClient,
    db,
) -> None:
    """POST /internal/evidence/store with run_verification=True and all passing: all bundles stored, quarantined_count=0."""
    run_id = "m6-verify-pass-run"
    body = {
        "run_id": run_id,
        "bundles": [
            {
                "candidate_company_name": "Co A",
                "company_website": "https://coa.example.com",
                "why_now_hypothesis": "Funding.",
                "evidence": [
                    {
                        "url": "https://coa.example.com/news",
                        "quoted_snippet": "Series A.",
                        "timestamp_seen": "2026-02-27T12:00:00Z",
                        "source_type": "web",
                        "confidence_score": 0.9,
                    }
                ],
                "missing_information": [],
            },
        ],
        "metadata": {"model_version": "gpt-4o", "tokens_used": None, "latency_ms": None, "page_fetch_count": 0},
        "run_context": {"run_id": run_id},
        "raw_model_output": None,
        "run_verification": True,
        "structured_payloads": [
            {"events": [{"event_type": "funding_raised", "confidence": 0.9, "source_refs": [0]}]},
        ],
    }
    response = client_with_db.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["stored_count"] == 1
    assert data["quarantined_count"] == 0
    assert len(data["bundle_ids"]) == 1

    from app.evidence.repository import list_bundles_by_run

    bundles = list_bundles_by_run(db, run_id)
    assert len(bundles) == 1


def test_store_evidence_without_verification_unchanged_behavior(
    client_with_db: TestClient,
) -> None:
    """POST /internal/evidence/store without run_verification (default): no quarantined_count, all bundles stored."""
    body = _valid_store_body()
    assert "run_verification" not in body or body.get("run_verification") is False
    response = client_with_db.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["stored_count"] == 1
    assert "quarantined_count" not in data
    assert len(data["bundle_ids"]) == 1


def test_store_evidence_verification_payload_length_mismatch_returns_422(
    client: TestClient,
) -> None:
    """POST /internal/evidence/store with run_verification=True and structured_payloads length != bundles returns 422."""
    body = _valid_store_body()
    body["run_verification"] = True
    body["structured_payloads"] = [{"events": []}, {"events": []}]  # 2 payloads, 1 bundle
    response = client.post(
        "/internal/evidence/store",
        headers={"X-Internal-Token": VALID_TOKEN},
        json=body,
    )
    assert response.status_code == 422
    detail = response.json().get("detail")
    detail_str = detail if isinstance(detail, str) else str(detail)
    assert "structured_payloads" in detail_str
