import uuid

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.framework_version import FrameworkVersion
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User

REVIEW_CAVEAT_SNIPPET = "internal complivibe content-governance signals"


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _framework_id_by_code(client, token: str, code: str) -> str:
    response = client.get("/api/v1/frameworks", headers=_headers(token))
    assert response.status_code == 200
    for item in response.json():
        if item["code"] == code:
            return item["id"]
    raise AssertionError(f"Framework {code} not found")


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str, password: str = "Pass1234!@") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash(password),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def _persist_coverage_report(client, token: str, org_id: str, framework_id: str) -> str:
    response = client.post(
        f"/api/v1/frameworks/{framework_id}/coverage-report",
        headers=_headers(token, org_id),
        json={"persist": True},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _apply_starter_pack(client, token: str, org_id: str, pack_key: str = "eu_ai_act_starter") -> None:
    response = client.post(
        f"/api/v1/framework-content/packs/{pack_key}/apply",
        headers=_headers(token, org_id),
        json={"dry_run": False, "force_update": False},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def _create_active_framework_version(client, token: str, org_id: str, framework_id: str, coverage_level: str) -> str:
    response = client.post(
        f"/api/v1/frameworks/{framework_id}/versions",
        headers=_headers(token, org_id),
        json={
            "version_label": f"p38-{coverage_level}",
            "status": "active",
            "coverage_level": coverage_level,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _start_and_complete_review(client, token: str, org_id: str, framework_id: str, coverage_report_id: str, review_type: str = "internal_review") -> str:
    started = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews",
        headers=_headers(token, org_id),
        json={
            "review_type": review_type,
            "target_coverage_level": "starter",
            "coverage_report_id": coverage_report_id,
            "checklist_json": {"items": [{"key": "coverage_report_present", "done": True}]},
        },
    )
    assert started.status_code == 201
    review_id = started.json()["id"]

    completed = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/complete",
        headers=_headers(token, org_id),
        json={
            "outcome": "pass",
            "checklist_json": {"items": [{"key": "gate", "done": True}]},
            "findings_json": {"notes": "ok"},
        },
    )
    assert completed.status_code == 200
    return review_id


def test_phase38_permissions_seeded(client):
    owner = _register(client, "p38-owner1@example.com", "Pass1234!@", "P38 Org1")
    org = _org_id(client, owner)

    perms = client.get("/api/v1/auth/permissions", headers=_headers(owner, org))
    assert perms.status_code == 200
    codes = set(perms.json()["permission_codes"])
    assert "framework_content:review" in codes
    assert "framework_content:promote" in codes


def test_phase38_review_start_complete_and_signoff_flow(client, db_session):
    owner = _register(client, "p38-owner2@example.com", "Pass1234!@", "P38 Org2")
    org = _org_id(client, owner)
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)

    started = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews",
        headers=_headers(owner, org),
        json={
            "review_type": "internal_review",
            "target_coverage_level": "starter",
            "coverage_report_id": coverage_report_id,
            "checklist_json": {"items": [{"key": "seed", "done": True}]},
        },
    )
    assert started.status_code == 201
    review_id = started.json()["id"]
    assert started.json()["coverage_snapshot_json"]["framework_id"] == framework_id
    assert REVIEW_CAVEAT_SNIPPET in started.json()["caveat"].lower()

    early_signoff = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/signoffs",
        headers=_headers(owner, org),
        json={"decision": "approved"},
    )
    assert early_signoff.status_code == 400

    completed = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/complete",
        headers=_headers(owner, org),
        json={
            "outcome": "pass",
            "checklist_json": {"items": [{"key": "all", "done": True}]},
            "findings_json": {"notes": "ready"},
        },
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["outcome"] == "pass"

    signoff = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/signoffs",
        headers=_headers(owner, org),
        json={"decision": "approved", "comment": "ship it"},
    )
    assert signoff.status_code == 201
    assert signoff.json()["signoff_checksum_sha256"]
    assert signoff.json()["signoff_signature"]

    dup_signoff = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/signoffs",
        headers=_headers(owner, org),
        json={"decision": "approved"},
    )
    assert dup_signoff.status_code == 400

    detail = client.get(f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}", headers=_headers(owner, org))
    assert detail.status_code == 200
    assert len(detail.json()["signoffs"]) == 1

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_pack_review.started" in actions
    assert "framework_pack_review.completed" in actions
    assert "framework_pack_review.signoff_created" in actions


def test_phase38_promotion_preflight_and_skip_rules(client):
    owner = _register(client, "p38-owner3@example.com", "Pass1234!@", "P38 Org3")
    org = _org_id(client, owner)
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)

    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)

    preflight_fail = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions/preflight",
        headers=_headers(owner, org),
        json={"review_run_id": review_id, "to_coverage_level": "partial"},
    )
    assert preflight_fail.status_code == 200
    assert preflight_fail.json()["passed"] is True

    skip_request = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions",
        headers=_headers(owner, org),
        json={"review_run_id": review_id, "to_coverage_level": "full_verified"},
    )
    assert skip_request.status_code == 400


def test_phase38_full_verified_gates_require_final_verification_and_two_signoffs(client, db_session):
    owner = _register(client, "p38-owner4@example.com", "Pass1234!@", "P38 Org4")
    org = _org_id(client, owner)
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    reviewed_version_id = _create_active_framework_version(client, owner, org, framework_id, "reviewed")
    rows = db_session.query(FrameworkVersion).filter(FrameworkVersion.framework_id == uuid.UUID(framework_id)).all()
    for row in rows:
        if str(row.id) != reviewed_version_id and row.status == "active":
            row.status = "superseded"
    db_session.commit()
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)

    admin1 = _create_active_user_with_role(db_session, org, "p38-admin1@example.com", "admin")
    admin2 = _create_active_user_with_role(db_session, org, "p38-admin2@example.com", "admin")
    admin1_token = _login(client, admin1.email, "Pass1234!@")
    admin2_token = _login(client, admin2.email, "Pass1234!@")

    review_id = _start_and_complete_review(
        client,
        owner,
        org,
        framework_id,
        coverage_report_id,
        review_type="final_verification",
    )

    client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/signoffs",
        headers=_headers(admin1_token, org),
        json={"decision": "approved", "comment": "one"},
    )

    one_signoff = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions/preflight",
        headers=_headers(owner, org),
        json={"review_run_id": review_id, "to_coverage_level": "full_verified"},
    )
    assert one_signoff.status_code == 200
    assert one_signoff.json()["passed"] is False
    assert any("two approved signoffs" in msg for msg in one_signoff.json()["gate_failures"])

    client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/signoffs",
        headers=_headers(admin2_token, org),
        json={"decision": "approved", "comment": "two"},
    )
    two_signoff = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions/preflight",
        headers=_headers(owner, org),
        json={"review_run_id": review_id, "to_coverage_level": "full_verified"},
    )
    assert two_signoff.status_code == 200
    assert two_signoff.json()["approved_signoffs"] >= 2
    assert all("two approved signoffs" not in msg for msg in two_signoff.json()["gate_failures"])


def test_phase38_promotion_approve_reject_execute_and_history(client, db_session):
    owner = _register(client, "p38-owner5@example.com", "Pass1234!@", "P38 Org5")
    org = _org_id(client, owner)
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)

    requester = _create_active_user_with_role(db_session, org, "p38-cm@example.com", "compliance_manager")
    approver = _create_active_user_with_role(db_session, org, "p38-admin3@example.com", "admin")
    requester_token = _login(client, requester.email, "Pass1234!@")
    approver_token = _login(client, approver.email, "Pass1234!@")

    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    signoff = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/signoffs",
        headers=_headers(approver_token, org),
        json={"decision": "approved", "comment": "ok"},
    )
    assert signoff.status_code == 201

    promotion = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions",
        headers=_headers(requester_token, org),
        json={"review_run_id": review_id, "to_coverage_level": "partial"},
    )
    assert promotion.status_code == 201
    promotion_id = promotion.json()["id"]

    self_approve = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions/{promotion_id}/approve",
        headers=_headers(requester_token, org),
    )
    assert self_approve.status_code == 403

    approved = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions/{promotion_id}/approve",
        headers=_headers(approver_token, org),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    executed = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions/{promotion_id}/execute",
        headers=_headers(owner, org),
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "executed"

    version = (
        db_session.query(FrameworkVersion)
        .filter(FrameworkVersion.framework_id == uuid.UUID(framework_id), FrameworkVersion.status == "active")
        .order_by(FrameworkVersion.created_at.desc())
        .first()
    )
    assert version is not None
    assert version.coverage_level == "partial"

    history = client.get(f"/api/v1/frameworks/{framework_id}/pack-promotions", headers=_headers(owner, org))
    assert history.status_code == 200
    assert len(history.json()) >= 1
    assert REVIEW_CAVEAT_SNIPPET in history.json()[0]["caveat"].lower()

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_pack_promotion.requested" in actions
    assert "framework_pack_promotion.approved" in actions
    assert "framework_pack_promotion.executed" in actions


def test_phase38_promotion_reject_requires_reason(client, db_session):
    owner = _register(client, "p38-owner6@example.com", "Pass1234!@", "P38 Org6")
    org = _org_id(client, owner)
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)

    admin = _create_active_user_with_role(db_session, org, "p38-admin4@example.com", "admin")
    admin_token = _login(client, admin.email, "Pass1234!@")

    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)
    client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/signoffs",
        headers=_headers(admin_token, org),
        json={"decision": "approved", "comment": "ok"},
    )
    created = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions",
        headers=_headers(owner, org),
        json={"review_run_id": review_id, "to_coverage_level": "partial"},
    )
    assert created.status_code == 201
    pid = created.json()["id"]

    no_reason = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions/{pid}/reject",
        headers=_headers(owner, org),
        json={"rejection_reason": ""},
    )
    assert no_reason.status_code == 400

    rejected = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-promotions/{pid}/reject",
        headers=_headers(owner, org),
        json={"rejection_reason": "needs updates"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


def test_phase38_review_summary_and_tenant_scoping(client, db_session):
    owner1 = _register(client, "p38-owner7@example.com", "Pass1234!@", "P38 Org7A")
    org1 = _org_id(client, owner1)
    owner2 = _register(client, "p38-owner8@example.com", "Pass1234!@", "P38 Org7B")
    org2 = _org_id(client, owner2)

    framework1 = _framework_id_by_code(client, owner1, "EU_AI_ACT")
    framework2 = _framework_id_by_code(client, owner2, "EU_AI_ACT")
    _apply_starter_pack(client, owner1, org1)
    _apply_starter_pack(client, owner2, org2)

    cov1 = _persist_coverage_report(client, owner1, org1, framework1)
    review1 = _start_and_complete_review(client, owner1, org1, framework1, cov1)

    # Org2 creates separate review record.
    cov2 = _persist_coverage_report(client, owner2, org2, framework2)
    _start_and_complete_review(client, owner2, org2, framework2, cov2)

    list1 = client.get(f"/api/v1/frameworks/{framework1}/pack-reviews", headers=_headers(owner1, org1))
    assert list1.status_code == 200
    assert any(item["id"] == review1 for item in list1.json())

    cross = client.get(f"/api/v1/frameworks/{framework2}/pack-reviews", headers=_headers(owner1, org1))
    assert cross.status_code == 200
    assert all(item["organization_id"] == org1 for item in cross.json())

    summary = client.get(f"/api/v1/frameworks/{framework1}/review-summary", headers=_headers(owner1, org1))
    assert summary.status_code == 200
    assert "promotion_readiness" in summary.json()
    assert REVIEW_CAVEAT_SNIPPET in summary.json()["caveat"].lower()
