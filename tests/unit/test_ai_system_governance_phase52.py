import uuid

from app.models.ai_system_governance_attestation import AISystemGovernanceAttestation
from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], *, name: str = "Governed AI") -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={"name": name, "system_type": "agent"},
    )
    assert response.status_code == 201
    return response.json()


def test_create_governance_review_assignee_validation_and_archived_rule(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p52-review-owner")
    other_org = bootstrap_org_user(client, email_prefix="p52-review-other")
    headers = owner["org_headers"]
    ai_system = _create_ai_system(client, headers)

    cross_org_assignee = other_org["user_id"]
    bad_assignee = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews",
        headers=headers,
        json={
            "review_type": "initial_review",
            "title": "Initial Gate",
            "assigned_to_user_id": cross_org_assignee,
        },
    )
    assert bad_assignee.status_code == 400
    assert "assigned_to_user_id" in bad_assignee.json()["detail"]

    archive = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/archive",
        headers=headers,
        json={"reason": "retired"},
    )
    assert archive.status_code == 200

    archived_wrong_type = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews",
        headers=headers,
        json={"review_type": "periodic_review", "title": "Periodic"},
    )
    assert archived_wrong_type.status_code == 400

    archived_retirement = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews",
        headers=headers,
        json={"review_type": "retirement_review", "title": "Retirement"},
    )
    assert archived_retirement.status_code == 201
    assert archived_retirement.json()["status"] == "pending"


def test_governance_review_list_detail_tenant_scoped(client):
    org1 = bootstrap_org_user(client, email_prefix="p52-scope-org1")
    org2 = bootstrap_org_user(client, email_prefix="p52-scope-org2")
    ai1 = _create_ai_system(client, org1["org_headers"], name="Org1 AI")
    ai2 = _create_ai_system(client, org2["org_headers"], name="Org2 AI")

    review1 = client.post(
        f"/api/v1/ai-systems/{ai1['id']}/governance-reviews",
        headers=org1["org_headers"],
        json={"review_type": "initial_review", "title": "Org1 review"},
    )
    assert review1.status_code == 201

    list_org1 = client.get(
        f"/api/v1/ai-systems/{ai1['id']}/governance-reviews",
        headers=org1["org_headers"],
    )
    assert list_org1.status_code == 200
    assert len(list_org1.json()) == 1

    list_cross = client.get(
        f"/api/v1/ai-systems/{ai2['id']}/governance-reviews",
        headers=org1["org_headers"],
    )
    assert list_cross.status_code == 404

    detail_cross = client.get(
        f"/api/v1/ai-systems/{ai1['id']}/governance-reviews/{review1.json()['id']}",
        headers=org2["org_headers"],
    )
    assert detail_cross.status_code == 404


def test_start_complete_cancel_review_flow(client):
    owner = bootstrap_org_user(client, email_prefix="p52-flow-owner")
    headers = owner["org_headers"]
    ai_system = _create_ai_system(client, headers)

    review = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews",
        headers=headers,
        json={"review_type": "pre_production_review", "title": "Pre-prod"},
    )
    assert review.status_code == 201
    review_id = review.json()["id"]

    started = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{review_id}/start",
        headers=headers,
        json={},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"
    assert started.json()["started_at"] is not None

    completed = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{review_id}/complete",
        headers=headers,
        json={
            "outcome": "approved_with_conditions",
            "findings_json": [{"key": "f1"}],
            "conditions_json": [{"key": "c1"}],
        },
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["outcome"] == "approved_with_conditions"

    cannot_cancel_completed = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{review_id}/cancel",
        headers=headers,
        json={"cancellation_reason": "too late"},
    )
    assert cannot_cancel_completed.status_code == 400

    review2 = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews",
        headers=headers,
        json={"review_type": "change_review", "title": "Change"},
    )
    assert review2.status_code == 201
    review2_id = review2.json()["id"]

    cancel_missing_reason = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{review2_id}/cancel",
        headers=headers,
        json={},
    )
    assert cancel_missing_reason.status_code == 422


def test_attestation_requirements_integrity_verify_and_no_mutation(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p52-attest-owner")
    headers = owner["org_headers"]
    org_id = uuid.UUID(owner["organization_id"])
    ai_system = _create_ai_system(client, headers)

    review = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews",
        headers=headers,
        json={"review_type": "initial_review", "title": "Attestation Review"},
    )
    assert review.status_code == 201
    review_id = review.json()["id"]

    early_attestation = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{review_id}/attestations",
        headers=headers,
        json={"decision": "attest", "statement": "premature"},
    )
    assert early_attestation.status_code == 400

    done = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{review_id}/complete",
        headers=headers,
        json={"outcome": "approved"},
    )
    assert done.status_code == 200

    attestation = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{review_id}/attestations",
        headers=headers,
        json={"decision": "attest", "statement": "Approved with documented checks."},
    )
    assert attestation.status_code == 201
    att_body = attestation.json()
    assert att_body["content_sha256"]
    assert att_body["internal_signature"]
    assert att_body["signature_algorithm"] == "HMAC-SHA256"
    assert "internal CompliVibe integrity signature" in att_body["caveat"]

    dup = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{review_id}/attestations",
        headers=headers,
        json={"decision": "attest", "statement": "second attempt"},
    )
    assert dup.status_code == 400

    row = (
        db_session.query(AISystemGovernanceAttestation)
        .filter(
            AISystemGovernanceAttestation.id == uuid.UUID(att_body["id"]),
            AISystemGovernanceAttestation.organization_id == org_id,
        )
        .one()
    )
    before_signature = row.internal_signature
    before_hash = row.content_sha256
    before_created_at = row.created_at

    verify = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{review_id}/attestations/{att_body['id']}/verify",
        headers=headers,
        json={},
    )
    assert verify.status_code == 200
    verify_body = verify.json()
    assert verify_body["valid_hash"] is True
    assert verify_body["valid_signature"] is True
    assert verify_body["content_sha256"] == before_hash

    db_session.refresh(row)
    assert row.internal_signature == before_signature
    assert row.content_sha256 == before_hash
    assert row.created_at == before_created_at


def test_governance_summary_and_audit_logs(client):
    owner = bootstrap_org_user(client, email_prefix="p52-summary-owner")
    headers = owner["org_headers"]
    ai_system = _create_ai_system(client, headers)

    r1 = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews",
        headers=headers,
        json={"review_type": "initial_review", "title": "R1"},
    )
    r2 = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews",
        headers=headers,
        json={"review_type": "periodic_review", "title": "R2"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201

    start_r1 = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{r1.json()['id']}/start",
        headers=headers,
        json={},
    )
    assert start_r1.status_code == 200
    complete_r1 = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{r1.json()['id']}/complete",
        headers=headers,
        json={"outcome": "approved"},
    )
    assert complete_r1.status_code == 200
    cancel_r2 = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{r2.json()['id']}/cancel",
        headers=headers,
        json={"cancellation_reason": "obsolete"},
    )
    assert cancel_r2.status_code == 200

    attest = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-reviews/{r1.json()['id']}/attestations",
        headers=headers,
        json={"decision": "acknowledge", "statement": "Recorded."},
    )
    assert attest.status_code == 201

    summary = client.get(
        f"/api/v1/ai-systems/{ai_system['id']}/governance-summary",
        headers=headers,
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_reviews"] == 2
    assert body["pending_reviews"] == 0
    assert body["in_progress_reviews"] == 0
    assert body["completed_reviews"] == 1
    assert body["cancelled_reviews"] == 1
    assert body["by_review_type"]["initial_review"] == 1
    assert body["by_review_type"]["periodic_review"] == 1
    assert body["by_outcome"]["approved"] == 1
    assert body["total_attestations"] == 1
    assert body["latest_review_at"] is not None
    assert body["latest_attestation_at"] is not None

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = [item["action"] for item in logs.json()]
    assert "ai_system_governance_review.created" in actions
    assert "ai_system_governance_review.started" in actions
    assert "ai_system_governance_review.completed" in actions
    assert "ai_system_governance_review.cancelled" in actions
    assert "ai_system_governance_attestation.created" in actions
