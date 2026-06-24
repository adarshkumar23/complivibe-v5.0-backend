import hashlib
import json
import uuid

from sqlalchemy import func, select

from app.models.ai_system import AISystem
from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.ai_system_risk_assessment_snapshot import AISystemRiskAssessmentSnapshot
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/ai-governance/ai-risk/assessments"


def _create_ai_system(client, headers: dict[str, str], *, name: str = "Risk AI") -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={"name": name, "system_type": "agent"},
    )
    assert response.status_code == 201
    return response.json()


def _create_assessment(client, headers: dict[str, str], ai_system_id: str, **overrides) -> dict:
    payload = {
        "ai_system_id": ai_system_id,
        "title": "Initial Risk Review",
        "assessment_type": "initial",
        "risk_level": "medium",
        "likelihood": "medium",
        "impact": "high",
        "methodology_version": "v1",
    }
    payload.update(overrides)
    response = client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase61_create_assessment_validation_and_scoring(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p61-create")
    other = bootstrap_org_user(client, email_prefix="p61-create-other")
    ai_system = _create_ai_system(client, owner["org_headers"])

    bad_system = client.post(
        BASE,
        headers=owner["org_headers"],
        json={
            "ai_system_id": other["organization_id"],  # invalid UUID for ai_system scope on purpose
            "title": "Bad",
            "assessment_type": "initial",
            "risk_level": "medium",
            "likelihood": "medium",
            "impact": "high",
            "methodology_version": "v1",
        },
    )
    assert bad_system.status_code in (400, 404, 422)

    # Valid create with deterministic score from manual likelihood/impact.
    created = _create_assessment(client, owner["org_headers"], ai_system["id"])
    assert created["assessment_type"] == "initial"
    assert created["status"] == "draft"
    assert created["inherent_risk_score"] == 6
    assert created["residual_risk_score"] == 6
    assert "manual governance records" in created["caveat"]

    # owner_user_id must be active same-org member.
    cross_org_user_id = other["user_id"]
    bad_owner = client.post(
        BASE,
        headers=owner["org_headers"],
        json={
            "ai_system_id": ai_system["id"],
            "title": "Owner check",
            "assessment_type": "initial",
            "risk_level": "low",
            "likelihood": "low",
            "impact": "low",
            "owner_user_id": cross_org_user_id,
            "methodology_version": "v1",
        },
    )
    assert bad_owner.status_code == 400
    assert "owner_user_id" in bad_owner.json()["detail"]


def test_phase61_reject_archived_ai_system_and_enum_validation(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p61-enums")
    ai_system = _create_ai_system(client, owner["org_headers"])

    archived = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/archive",
        headers=owner["org_headers"],
        json={"reason": "retired"},
    )
    assert archived.status_code == 200

    archived_reject = client.post(
        BASE,
        headers=owner["org_headers"],
        json={
            "ai_system_id": ai_system["id"],
            "title": "Nope",
            "assessment_type": "initial",
            "risk_level": "low",
            "likelihood": "low",
            "impact": "low",
            "methodology_version": "v1",
        },
    )
    assert archived_reject.status_code == 400

    invalid_type = client.post(
        BASE,
        headers=owner["org_headers"],
        json={
            "ai_system_id": ai_system["id"],
            "title": "Invalid",
            "assessment_type": "auto_magic",
            "risk_level": "low",
            "likelihood": "low",
            "impact": "low",
            "methodology_version": "v1",
        },
    )
    assert invalid_type.status_code == 422

    invalid_risk_level = client.post(
        BASE,
        headers=owner["org_headers"],
        json={
            "ai_system_id": ai_system["id"],
            "title": "Invalid level",
            "assessment_type": "initial",
            "risk_level": "extreme",
            "likelihood": "low",
            "impact": "low",
            "methodology_version": "v1",
        },
    )
    assert invalid_risk_level.status_code == 422

    invalid_likelihood = client.post(
        BASE,
        headers=owner["org_headers"],
        json={
            "ai_system_id": ai_system["id"],
            "title": "Invalid likelihood",
            "assessment_type": "initial",
            "risk_level": "low",
            "likelihood": "maybe",
            "impact": "low",
            "methodology_version": "v1",
        },
    )
    assert invalid_likelihood.status_code == 422


def test_phase61_list_filters_detail_tenant_scope_and_update(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p61-list-org1")
    org2 = bootstrap_org_user(client, email_prefix="p61-list-org2")
    ai1 = _create_ai_system(client, org1["org_headers"], name="AI-1")
    ai2 = _create_ai_system(client, org1["org_headers"], name="AI-2")

    a1 = _create_assessment(
        client,
        org1["org_headers"],
        ai1["id"],
        title="A1",
        assessment_type="initial",
        risk_level="high",
        likelihood="high",
        impact="high",
    )
    _create_assessment(
        client,
        org1["org_headers"],
        ai2["id"],
        title="A2",
        assessment_type="periodic",
        risk_level="low",
        likelihood="low",
        impact="low",
    )

    list_all = client.get(BASE, headers=org1["org_headers"])
    assert list_all.status_code == 200
    assert len(list_all.json()) == 2

    by_ai_system = client.get(f"{BASE}?ai_system_id={ai1['id']}", headers=org1["org_headers"])
    assert by_ai_system.status_code == 200
    assert len(by_ai_system.json()) == 1
    assert by_ai_system.json()[0]["id"] == a1["id"]

    by_type = client.get(f"{BASE}?assessment_type=periodic", headers=org1["org_headers"])
    assert by_type.status_code == 200
    assert len(by_type.json()) == 1

    by_level = client.get(f"{BASE}?risk_level=high", headers=org1["org_headers"])
    assert by_level.status_code == 200
    assert len(by_level.json()) == 1

    detail_cross_tenant = client.get(f"{BASE}/{a1['id']}", headers=org2["org_headers"])
    assert detail_cross_tenant.status_code == 404

    updated = client.patch(
        f"{BASE}/{a1['id']}",
        headers=org1["org_headers"],
        json={"risk_level": "critical", "impact": "critical", "likelihood": "high"},
    )
    assert updated.status_code == 200
    assert updated.json()["risk_level"] == "critical"
    assert updated.json()["inherent_risk_score"] == 12

    logs = client.get("/api/v1/audit-logs", headers=org1["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "ai_system_risk_assessment.updated" in actions


def test_phase61_lifecycle_and_snapshot_immutability(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p61-lifecycle")
    ai = _create_ai_system(client, org["org_headers"])
    created = _create_assessment(client, org["org_headers"], ai["id"])

    submit = client.post(f"{BASE}/{created['id']}/submit-for-review", headers=org["org_headers"], json={})
    assert submit.status_code == 200
    assert submit.json()["status"] == "in_review"

    completed = client.post(f"{BASE}/{created['id']}/complete", headers=org["org_headers"], json={})
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None

    snapshots_after_complete = client.get(
        f"{BASE}/{created['id']}/snapshots",
        headers=org["org_headers"],
    )
    assert snapshots_after_complete.status_code == 200
    comp_snaps = snapshots_after_complete.json()
    assert any(row["snapshot_type"] == "completion_snapshot" for row in comp_snaps)

    manual = client.post(
        f"{BASE}/{created['id']}/snapshots",
        headers=org["org_headers"],
        json={"note": "checkpoint"},
    )
    assert manual.status_code == 201
    manual_body = manual.json()
    assert manual_body["snapshot_type"] == "manual_snapshot"

    canonical = json.dumps(manual_body["snapshot_json"], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    expected_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert manual_body["snapshot_sha256"] == expected_sha

    # No update endpoint for snapshots; snapshots remain immutable.
    patch_snapshot = client.patch(
        f"/api/v1/ai-governance/ai-risk/assessment-snapshots/{manual_body['id']}",
        headers=org["org_headers"],
        json={"snapshot_sha256": "bad"},
    )
    assert patch_snapshot.status_code in (404, 405)

    before_sha = manual_body["snapshot_sha256"]
    detail = client.get(
        f"/api/v1/ai-governance/ai-risk/assessment-snapshots/{manual_body['id']}",
        headers=org["org_headers"],
    )
    assert detail.status_code == 200
    assert detail.json()["snapshot_sha256"] == before_sha

    missing_reason = client.post(
        f"{BASE}/{created['id']}/archive",
        headers=org["org_headers"],
        json={},
    )
    assert missing_reason.status_code == 422

    archived = client.post(
        f"{BASE}/{created['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "superseded"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["archived_at"] is not None

    snapshots_after_archive = client.get(
        f"{BASE}/{created['id']}/snapshots",
        headers=org["org_headers"],
    )
    assert snapshots_after_archive.status_code == 200
    assert any(row["snapshot_type"] == "archive_snapshot" for row in snapshots_after_archive.json())

    blocked_update = client.patch(
        f"{BASE}/{created['id']}",
        headers=org["org_headers"],
        json={"title": "should fail"},
    )
    assert blocked_update.status_code == 400

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "ai_system_risk_assessment.submitted_for_review" in actions
    assert "ai_system_risk_assessment.completed" in actions
    assert "ai_system_risk_assessment.archived" in actions
    assert "ai_system_risk_assessment_snapshot.created" in actions


def test_phase61_snapshot_tenant_scope_and_summary(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p61-summary-org1")
    org2 = bootstrap_org_user(client, email_prefix="p61-summary-org2")

    ai1 = _create_ai_system(client, org1["org_headers"], name="Summary-1")
    ai2 = _create_ai_system(client, org1["org_headers"], name="Summary-2")
    a1 = _create_assessment(client, org1["org_headers"], ai1["id"], risk_level="high", assessment_type="initial")
    a2 = _create_assessment(client, org1["org_headers"], ai2["id"], risk_level="low", assessment_type="periodic")

    client.post(f"{BASE}/{a1['id']}/complete", headers=org1["org_headers"], json={})
    client.post(f"{BASE}/{a2['id']}/submit-for-review", headers=org1["org_headers"], json={})

    snap = client.post(f"{BASE}/{a2['id']}/snapshots", headers=org1["org_headers"], json={})
    assert snap.status_code == 201

    cross_list = client.get(f"{BASE}/{a2['id']}/snapshots", headers=org2["org_headers"])
    assert cross_list.status_code == 404

    cross_get = client.get(
        f"/api/v1/ai-governance/ai-risk/assessment-snapshots/{snap.json()['id']}",
        headers=org2["org_headers"],
    )
    assert cross_get.status_code == 404

    summary = client.get("/api/v1/ai-governance/ai-risk/assessments/summary", headers=org1["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_assessments"] == 2
    assert body["draft_assessments"] == 0
    assert body["in_review_assessments"] == 1
    assert body["completed_assessments"] == 1
    assert body["archived_assessments"] == 0
    assert body["by_risk_level"]["high"] == 1
    assert body["by_risk_level"]["low"] == 1
    assert body["by_assessment_type"]["initial"] == 1
    assert body["by_assessment_type"]["periodic"] == 1
    assert body["by_ai_system"][ai1["id"]] == 1
    assert body["by_ai_system"][ai2["id"]] == 1
    assert body["total_snapshots"] >= 2
    assert body["latest_completed_at"] is not None
    assert "manual governance records" in body["caveat"]


def test_phase61_contract_phase6_endpoint_and_read_only_audit_behavior(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p61-contracts")
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    before_assessments = db_session.execute(select(func.count(AISystemRiskAssessment.id))).scalar_one()
    before_snapshots = db_session.execute(select(func.count(AISystemRiskAssessmentSnapshot.id))).scalar_one()

    response = client.get("/api/v1/ai-governance/contracts/phase6", headers=org["org_headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == "phase6"
    assert body["status"] == "foundation"
    assert body["group_count"] >= 1
    keys = {group["group_key"] for group in body["groups"]}
    assert "ai_risk_assessments" in keys

    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    after_assessments = db_session.execute(select(func.count(AISystemRiskAssessment.id))).scalar_one()
    after_snapshots = db_session.execute(select(func.count(AISystemRiskAssessmentSnapshot.id))).scalar_one()
    assert after_audit == before_audit
    assert after_assessments == before_assessments
    assert after_snapshots == before_snapshots


def test_phase61_source_ai_system_validation_is_same_org(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p61-orgval-1")
    org2 = bootstrap_org_user(client, email_prefix="p61-orgval-2")
    ai2 = _create_ai_system(client, org2["org_headers"], name="Org2 AI")

    create_cross = client.post(
        BASE,
        headers=org1["org_headers"],
        json={
            "ai_system_id": ai2["id"],
            "title": "cross-org",
            "assessment_type": "initial",
            "risk_level": "medium",
            "likelihood": "medium",
            "impact": "medium",
            "methodology_version": "v1",
        },
    )
    assert create_cross.status_code == 404

    # Ensure we did not mutate AI systems while assessing.
    persisted = db_session.query(AISystem).filter(AISystem.id == uuid.UUID(ai2["id"])).one()
    assert persisted.lifecycle_status == "proposed"
