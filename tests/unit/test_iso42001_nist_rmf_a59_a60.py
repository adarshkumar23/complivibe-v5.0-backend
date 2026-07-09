from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.iso42001_conformity_tracker import ISO42001ConformityTracker
from app.services.seed_service import NIST_AI_RMF_SUBCATEGORIES
from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"
ISO42001_BASE = "/api/v1/ai-governance/iso42001"
NIST_ORG_SUMMARY = "/api/v1/ai-governance/nist-rmf/org-summary"


def _create_system(client, headers: dict[str, str], owner_id: str, name: str) -> str:
    response = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": "limited",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_a59_iso42001_conformity_tracker(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a59-iso42001")

    seeded = client.get(f"{ISO42001_BASE}/conformity-tracker", headers=org["org_headers"])
    assert seeded.status_code == 200
    rows = seeded.json()
    assert len(rows) == 30

    clause_41 = next(row for row in rows if row["clause_ref"] == "4.1")
    update_one = client.post(
        f"{ISO42001_BASE}/conformity-tracker/4.1/update",
        headers=org["org_headers"],
        json={"implementation_status": "implemented", "notes": "Implemented Clause 4.1"},
    )
    assert update_one.status_code == 200
    assert update_one.json()["implementation_status"] == "implemented"

    update_two = client.post(
        f"{ISO42001_BASE}/conformity-tracker/5.1/update",
        headers=org["org_headers"],
        json={"implementation_status": "verified", "notes": "Verified Clause 5.1"},
    )
    assert update_two.status_code == 200
    assert update_two.json()["implementation_status"] == "verified"

    # Upsert behavior: second update on same clause should update existing row, not duplicate.
    update_same_clause = client.post(
        f"{ISO42001_BASE}/conformity-tracker/4.1/update",
        headers=org["org_headers"],
        json={"implementation_status": "verified", "notes": "Promoted to verified"},
    )
    assert update_same_clause.status_code == 200
    assert update_same_clause.json()["id"] == clause_41["id"]
    assert update_same_clause.json()["implementation_status"] == "verified"

    clause_count = db_session.execute(
        select(func.count(ISO42001ConformityTracker.id)).where(
            ISO42001ConformityTracker.organization_id == uuid.UUID(org["organization_id"]),
            ISO42001ConformityTracker.clause_ref == "4.1",
        )
    ).scalar_one()
    assert int(clause_count) == 1

    summary_resp = client.get(f"{ISO42001_BASE}/summary", headers=org["org_headers"])
    assert summary_resp.status_code == 200
    summary = summary_resp.json()

    assert summary["total_clauses"] == 30
    # two completed-equivalent clauses: 4.1 (verified) and 5.1 (verified)
    assert summary["implementation_pct"] == round((2 / 30) * 100, 2)
    assert "Clause 4" in summary["sections"]
    assert "Clause 5" in summary["sections"]
    assert summary["sections"]["Clause 4"]["total"] == 4
    assert summary["sections"]["Clause 5"]["total"] == 3


def test_iso42001_status_only_update_preserves_notes_and_evidence(client):
    org = bootstrap_org_user(client, email_prefix="iso42001-preserve")

    seeded = client.get(f"{ISO42001_BASE}/conformity-tracker", headers=org["org_headers"])
    assert seeded.status_code == 200

    evidence = client.post(
        "/api/v1/evidence",
        headers=org["org_headers"],
        json={"title": "AIMS scope document", "evidence_type": "document"},
    )
    assert evidence.status_code == 201
    evidence_id = evidence.json()["id"]

    with_notes = client.post(
        f"{ISO42001_BASE}/conformity-tracker/4.1/update",
        headers=org["org_headers"],
        json={"implementation_status": "in_progress", "notes": "Scope drafted", "evidence_id": evidence_id},
    )
    assert with_notes.status_code == 200
    assert with_notes.json()["notes"] == "Scope drafted"
    assert with_notes.json()["evidence_id"] == evidence_id

    # Status-only update must not wipe notes/evidence.
    status_only = client.post(
        f"{ISO42001_BASE}/conformity-tracker/4.1/update",
        headers=org["org_headers"],
        json={"implementation_status": "implemented"},
    )
    assert status_only.status_code == 200
    assert status_only.json()["implementation_status"] == "implemented"
    assert status_only.json()["notes"] == "Scope drafted"
    assert status_only.json()["evidence_id"] == evidence_id

    # Explicit null clears notes.
    explicit_clear = client.post(
        f"{ISO42001_BASE}/conformity-tracker/4.1/update",
        headers=org["org_headers"],
        json={"implementation_status": "implemented", "notes": None},
    )
    assert explicit_clear.status_code == 200
    assert explicit_clear.json()["notes"] is None
    assert explicit_clear.json()["evidence_id"] == evidence_id


def test_iso42001_rejects_evidence_outside_org(client):
    org_a = bootstrap_org_user(client, email_prefix="iso42001-eva")
    org_b = bootstrap_org_user(client, email_prefix="iso42001-evb")

    client.get(f"{ISO42001_BASE}/conformity-tracker", headers=org_a["org_headers"])

    foreign_evidence = client.post(
        "/api/v1/evidence",
        headers=org_b["org_headers"],
        json={"title": "Org B evidence", "evidence_type": "document"},
    )
    assert foreign_evidence.status_code == 201
    foreign_id = foreign_evidence.json()["id"]

    cross_org = client.post(
        f"{ISO42001_BASE}/conformity-tracker/4.1/update",
        headers=org_a["org_headers"],
        json={"implementation_status": "implemented", "evidence_id": foreign_id},
    )
    assert cross_org.status_code == 422
    assert "evidence_id" in cross_org.json()["detail"]

    nonexistent = client.post(
        f"{ISO42001_BASE}/conformity-tracker/4.1/update",
        headers=org_a["org_headers"],
        json={"implementation_status": "implemented", "evidence_id": str(uuid.uuid4())},
    )
    assert nonexistent.status_code == 422


def test_nist_rmf_status_only_update_preserves_notes_and_rejects_foreign_evidence(client):
    org = bootstrap_org_user(client, email_prefix="rmf-preserve")
    org_b = bootstrap_org_user(client, email_prefix="rmf-preserve-b")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "RMF-Preserve-System")

    create_impl = client.post(f"{SYSTEMS_BASE}/{system_id}/nist-rmf", headers=org["org_headers"])
    assert create_impl.status_code == 200

    with_notes = client.post(
        f"{SYSTEMS_BASE}/{system_id}/nist-rmf/update-subcategory",
        headers=org["org_headers"],
        json={"subcategory_ref": "GOVERN-1.1", "response_status": "partial", "notes": "Draft policy"},
    )
    assert with_notes.status_code == 200

    status_only = client.post(
        f"{SYSTEMS_BASE}/{system_id}/nist-rmf/update-subcategory",
        headers=org["org_headers"],
        json={"subcategory_ref": "GOVERN-1.1", "response_status": "implemented"},
    )
    assert status_only.status_code == 200
    row = next(item for item in status_only.json()["responses"] if item["subcategory_ref"] == "GOVERN-1.1")
    assert row["response_status"] == "implemented"
    assert row["notes"] == "Draft policy"

    foreign_evidence = client.post(
        "/api/v1/evidence",
        headers=org_b["org_headers"],
        json={"title": "Org B evidence", "evidence_type": "document"},
    )
    assert foreign_evidence.status_code == 201
    cross_org = client.post(
        f"{SYSTEMS_BASE}/{system_id}/nist-rmf/update-subcategory",
        headers=org["org_headers"],
        json={
            "subcategory_ref": "GOVERN-1.1",
            "response_status": "implemented",
            "evidence_id": foreign_evidence.json()["id"],
        },
    )
    assert cross_org.status_code == 422
    assert "evidence_id" in cross_org.json()["detail"]


def test_a60_nist_rmf_workflow(client):
    org = bootstrap_org_user(client, email_prefix="a60-nist-rmf")
    system_one = _create_system(client, org["org_headers"], org["user_id"], "A60-RMF-System-1")

    create_impl = client.post(f"{SYSTEMS_BASE}/{system_one}/nist-rmf", headers=org["org_headers"])
    assert create_impl.status_code == 200
    implementation_id = create_impl.json()["id"]

    detail = client.get(f"{SYSTEMS_BASE}/{system_one}/nist-rmf", headers=org["org_headers"])
    assert detail.status_code == 200
    body = detail.json()
    responses = body["responses"]

    expected_count = sum(len(rows) for rows in NIST_AI_RMF_SUBCATEGORIES.values())
    assert expected_count >= 40
    assert len(responses) == expected_count

    # Update one subcategory to implemented.
    one_update = client.post(
        f"{SYSTEMS_BASE}/{system_one}/nist-rmf/update-subcategory",
        headers=org["org_headers"],
        json={
            "subcategory_ref": "GOVERN-1.1",
            "response_status": "implemented",
            "notes": "Policy implemented",
        },
    )
    assert one_update.status_code == 200
    updated = next(item for item in one_update.json()["responses"] if item["subcategory_ref"] == "GOVERN-1.1")
    assert updated["response_status"] == "implemented"

    # All GOVERN subcategories implemented => 100% for govern.
    for ref, _ in NIST_AI_RMF_SUBCATEGORIES["GOVERN"]:
        res = client.post(
            f"{SYSTEMS_BASE}/{system_one}/nist-rmf/update-subcategory",
            headers=org["org_headers"],
            json={"subcategory_ref": ref, "response_status": "implemented"},
        )
        assert res.status_code == 200

    maturity = client.get(f"{SYSTEMS_BASE}/{system_one}/nist-rmf/maturity", headers=org["org_headers"])
    assert maturity.status_code == 200
    maturity_body = maturity.json()
    assert maturity_body["govern"]["pct"] == 100.0

    # Mixed MAP responses => partial percentage and function status in_progress.
    map_refs = [ref for ref, _ in NIST_AI_RMF_SUBCATEGORIES["MAP"]]
    for ref in map_refs[: len(map_refs) // 2]:
        res = client.post(
            f"{SYSTEMS_BASE}/{system_one}/nist-rmf/update-subcategory",
            headers=org["org_headers"],
            json={"subcategory_ref": ref, "response_status": "implemented"},
        )
        assert res.status_code == 200

    maturity_mixed = client.get(f"{SYSTEMS_BASE}/{system_one}/nist-rmf/maturity", headers=org["org_headers"])
    assert maturity_mixed.status_code == 200
    mixed_body = maturity_mixed.json()
    expected_map_pct = round((len(map_refs) // 2) / len(map_refs) * 100, 2)
    assert mixed_body["map"]["pct"] == expected_map_pct

    impl_after = client.get(f"{SYSTEMS_BASE}/{system_one}/nist-rmf", headers=org["org_headers"])
    assert impl_after.status_code == 200
    assert impl_after.json()["implementation"]["govern_status"] == "implemented"
    assert impl_after.json()["implementation"]["map_status"] == "in_progress"
    assert impl_after.json()["implementation"]["id"] == implementation_id

    # Create second system and set full GOVERN implementation to validate org summary aggregation.
    system_two = _create_system(client, org["org_headers"], org["user_id"], "A60-RMF-System-2")
    create_impl_two = client.post(f"{SYSTEMS_BASE}/{system_two}/nist-rmf", headers=org["org_headers"])
    assert create_impl_two.status_code == 200
    for ref, _ in NIST_AI_RMF_SUBCATEGORIES["GOVERN"]:
        res = client.post(
            f"{SYSTEMS_BASE}/{system_two}/nist-rmf/update-subcategory",
            headers=org["org_headers"],
            json={"subcategory_ref": ref, "response_status": "implemented"},
        )
        assert res.status_code == 200

    org_summary = client.get(NIST_ORG_SUMMARY, headers=org["org_headers"])
    assert org_summary.status_code == 200
    summary = org_summary.json()
    assert summary["systems_count"] == 2
    assert summary["govern"]["pct"] == 100.0
    assert summary["map"]["pct"] > 0

    # Tenant isolation: second org should not see first org summary data.
    org_b = bootstrap_org_user(client, email_prefix="a60-nist-rmf-b")
    org_b_summary = client.get(NIST_ORG_SUMMARY, headers=org_b["org_headers"])
    assert org_b_summary.status_code == 200
    assert org_b_summary.json()["systems_count"] == 0

    # Ensure response rows are scoped and not leaked across orgs.
    org_one_response_count = client.get(f"{SYSTEMS_BASE}/{system_one}/nist-rmf", headers=org["org_headers"])
    assert org_one_response_count.status_code == 200
    assert len(org_one_response_count.json()["responses"]) == expected_count

    leaked_count = client.get(f"{SYSTEMS_BASE}/{system_one}/nist-rmf", headers=org_b["org_headers"])
    assert leaked_count.status_code == 404

    # Sanity check DB row count per implementation uniqueness.
    response_count_db = client.get(f"{SYSTEMS_BASE}/{system_one}/nist-rmf", headers=org["org_headers"]).json()["responses"]
    assert len(response_count_db) == expected_count
    assert (
        len(
            {
                f"{item['subcategory_ref']}::{item['function']}"
                for item in response_count_db
            }
        )
        == expected_count
    )
