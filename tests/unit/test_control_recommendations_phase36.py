import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.membership import Membership
from app.models.obligation_control_recommendation import ObligationControlRecommendation
from app.models.role import Role
from app.models.task import Task
from app.models.user import User


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


def _framework_with_obligation(client, token: str) -> tuple[dict, dict]:
    frameworks = client.get("/api/v1/frameworks", headers=_headers(token))
    assert frameworks.status_code == 200
    for framework in frameworks.json():
        obligations = client.get(f"/api/v1/frameworks/{framework['id']}/obligations", headers=_headers(token))
        assert obligations.status_code == 200
        if obligations.json():
            return framework, obligations.json()[0]
    raise AssertionError("No framework with obligations found")


def _activate_framework(client, token: str, org_id: str, framework_id: str) -> None:
    response = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(token, org_id),
        json={},
    )
    assert response.status_code == 200


def _set_obligation_state(client, token: str, org_id: str, obligation_id: str, applicability: str) -> None:
    response = client.patch(
        f"/api/v1/obligations/{obligation_id}/state",
        headers=_headers(token, org_id),
        json={
            "applicability_status": applicability,
            "implementation_status": "not_started",
            "justification": "phase36 test" if applicability == "not_applicable" else None,
        },
    )
    assert response.status_code == 200


def _create_control(client, token: str, org_id: str, title: str) -> str:
    response = client.post(
        "/api/v1/controls",
        headers=_headers(token, org_id),
        json={"title": title, "control_type": "process", "criticality": "high"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _map_control(client, token: str, org_id: str, control_id: str, obligation_id: str) -> None:
    response = client.post(
        f"/api/v1/controls/{control_id}/obligations",
        headers=_headers(token, org_id),
        json={"obligation_id": obligation_id, "mapping_type": "supports", "confidence": "manual_confirmed"},
    )
    assert response.status_code == 200


def _create_expired_verified_evidence(client, token: str, org_id: str, control_id: str, title: str) -> str:
    evidence = client.post(
        "/api/v1/evidence",
        headers=_headers(token, org_id),
        json={
            "title": title,
            "evidence_type": "policy_document",
            "valid_until": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
    )
    assert evidence.status_code == 201
    evidence_id = evidence.json()["id"]

    reviewed = client.post(
        f"/api/v1/evidence/{evidence_id}/review",
        headers=_headers(token, org_id),
        json={"review_status": "verified"},
    )
    assert reviewed.status_code == 200

    linked = client.post(
        f"/api/v1/evidence/{evidence_id}/controls",
        headers=_headers(token, org_id),
        json={"control_id": control_id, "confidence": "manual_confirmed"},
    )
    assert linked.status_code == 200
    return evidence_id


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


def test_recommendation_generation_dry_run_live_and_duplicate_skip(client):
    owner = _register(client, "p36-owner1@example.com", "Pass1234!@", "P36 Org1")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    _set_obligation_state(client, owner, org, obligation["id"], "applicable")

    dry = client.post(
        f"/api/v1/frameworks/{framework['id']}/control-recommendations/generate",
        headers=_headers(owner, org),
        json={"dry_run": True},
    )
    assert dry.status_code == 200
    assert dry.json()["dry_run"] is True
    assert any(item["recommendation_type"] == "create_control" for item in dry.json()["recommendations"])

    listed_after_dry = client.get("/api/v1/control-recommendations", headers=_headers(owner, org))
    assert listed_after_dry.status_code == 200
    assert listed_after_dry.json() == []

    live = client.post(
        f"/api/v1/frameworks/{framework['id']}/control-recommendations/generate",
        headers=_headers(owner, org),
        json={"dry_run": False},
    )
    assert live.status_code == 200
    assert live.json()["dry_run"] is False
    assert live.json()["run_id"] is not None

    listed_after_live = client.get(
        "/api/v1/control-recommendations?recommendation_type=create_control&limit=200",
        headers=_headers(owner, org),
    )
    assert listed_after_live.status_code == 200
    assert any(item["recommendation_type"] == "create_control" for item in listed_after_live.json())

    rerun = client.post(
        f"/api/v1/frameworks/{framework['id']}/control-recommendations/generate",
        headers=_headers(owner, org),
        json={"dry_run": False},
    )
    assert rerun.status_code == 200
    assert rerun.json()["summary"]["recommendations_skipped_duplicate_count"] >= 1


def test_non_applicable_and_needs_review_paths(client):
    owner = _register(client, "p36-owner2@example.com", "Pass1234!@", "P36 Org2")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])

    _set_obligation_state(client, owner, org, obligation["id"], "not_applicable")
    run_non_applicable = client.post(
        f"/api/v1/frameworks/{framework['id']}/control-recommendations/generate",
        headers=_headers(owner, org),
        json={"dry_run": False},
    )
    assert run_non_applicable.status_code == 200
    assert all(item["recommendation_type"] != "create_control" for item in run_non_applicable.json()["recommendations"])

    _set_obligation_state(client, owner, org, obligation["id"], "needs_review")
    run_needs_review = client.post(
        f"/api/v1/frameworks/{framework['id']}/control-recommendations/generate",
        headers=_headers(owner, org),
        json={"dry_run": False},
    )
    assert run_needs_review.status_code == 200
    assert any(item["recommendation_type"] == "review_applicability" for item in run_needs_review.json()["recommendations"])


def test_expired_evidence_generates_refresh_recommendation_and_apply_creates_task(client, db_session):
    owner = _register(client, "p36-owner3@example.com", "Pass1234!@", "P36 Org3")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    _set_obligation_state(client, owner, org, obligation["id"], "applicable")

    control_id = _create_control(client, owner, org, "P36 Evidence Control")
    _map_control(client, owner, org, control_id, obligation["id"])
    _create_expired_verified_evidence(client, owner, org, control_id, "P36 Expired Evidence")

    generated = client.post(
        f"/api/v1/frameworks/{framework['id']}/control-recommendations/generate",
        headers=_headers(owner, org),
        json={"dry_run": False},
    )
    assert generated.status_code == 200
    refresh = next((item for item in generated.json()["recommendations"] if item["recommendation_type"] == "refresh_evidence"), None)
    assert refresh is not None

    applied = client.post(
        f"/api/v1/control-recommendations/{refresh['id']}/apply",
        headers=_headers(owner, org),
        json={"notes": "Request fresh evidence"},
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"

    tasks = db_session.query(Task).filter(Task.organization_id == uuid.UUID(org)).all()
    assert any(task.task_type == "evidence_request" for task in tasks)


def test_apply_create_control_and_map_existing_control_validation(client, db_session):
    owner = _register(client, "p36-owner4@example.com", "Pass1234!@", "P36 Org4")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    _set_obligation_state(client, owner, org, obligation["id"], "applicable")

    generated = client.post(
        f"/api/v1/frameworks/{framework['id']}/control-recommendations/generate",
        headers=_headers(owner, org),
        json={"dry_run": False},
    )
    assert generated.status_code == 200
    create_rec = next((item for item in generated.json()["recommendations"] if item["recommendation_type"] == "create_control"), None)
    assert create_rec is not None

    apply_create = client.post(
        f"/api/v1/control-recommendations/{create_rec['id']}/apply",
        headers=_headers(owner, org),
        json={"create_control": True},
    )
    assert apply_create.status_code == 200
    assert apply_create.json()["status"] == "applied"
    assert apply_create.json()["created_control_id"] is not None

    org_controls = client.get(f"/api/v1/obligations/{obligation['id']}/controls", headers=_headers(owner, org))
    assert org_controls.status_code == 200
    assert any(c["id"] == apply_create.json()["created_control_id"] for c in org_controls.json())

    # Create map_existing_control recommendation manually and validate control ownership checks.
    manual = ObligationControlRecommendation(
        organization_id=uuid.UUID(org),
        framework_id=uuid.UUID(framework["id"]),
        obligation_id=uuid.UUID(obligation["id"]),
        recommendation_type="map_existing_control",
        priority="normal",
        status="open",
        title="Map existing control",
        rationale="Manual test recommendation",
        confidence_level="deterministic_partial",
        source="coverage_gap",
        generated_by_user_id=uuid.UUID(client.get("/api/v1/auth/me", headers=_headers(owner)).json()["id"]),
        generated_at=datetime.now(UTC),
    )
    db_session.add(manual)
    db_session.commit()

    owner2 = _register(client, "p36-owner4b@example.com", "Pass1234!@", "P36 Org4b")
    org2 = _org_id(client, owner2)
    control_other_org = _create_control(client, owner2, org2, "Other Org Control")

    bad_apply = client.post(
        f"/api/v1/control-recommendations/{manual.id}/apply",
        headers=_headers(owner, org),
        json={"existing_control_id": control_other_org, "create_control": False},
    )
    assert bad_apply.status_code == 404

    local_control = _create_control(client, owner, org, "Local Org Control")
    good_apply = client.post(
        f"/api/v1/control-recommendations/{manual.id}/apply",
        headers=_headers(owner, org),
        json={"existing_control_id": local_control, "create_control": False},
    )
    assert good_apply.status_code == 200
    assert good_apply.json()["status"] == "applied"

    mapping = (
        db_session.query(ControlObligationMapping)
        .filter(
            ControlObligationMapping.organization_id == uuid.UUID(org),
            ControlObligationMapping.obligation_id == uuid.UUID(obligation["id"]),
            ControlObligationMapping.control_id == uuid.UUID(local_control),
            ControlObligationMapping.status == "active",
        )
        .one_or_none()
    )
    assert mapping is not None


def test_dismiss_requires_reason_and_lists_are_tenant_scoped(client, db_session):
    owner1 = _register(client, "p36-owner5@example.com", "Pass1234!@", "P36 Org5")
    org1 = _org_id(client, owner1)
    owner2 = _register(client, "p36-owner6@example.com", "Pass1234!@", "P36 Org6")
    org2 = _org_id(client, owner2)

    framework, obligation = _framework_with_obligation(client, owner1)
    _activate_framework(client, owner1, org1, framework["id"])
    _activate_framework(client, owner2, org2, framework["id"])
    _set_obligation_state(client, owner1, org1, obligation["id"], "applicable")

    generated = client.post(
        f"/api/v1/frameworks/{framework['id']}/control-recommendations/generate",
        headers=_headers(owner1, org1),
        json={"dry_run": False},
    )
    assert generated.status_code == 200
    rec = next((item for item in generated.json()["recommendations"] if item["status"] == "open"), None)
    assert rec is not None

    bad_dismiss = client.post(
        f"/api/v1/control-recommendations/{rec['id']}/dismiss",
        headers=_headers(owner1, org1),
        json={"dismissal_reason": ""},
    )
    assert bad_dismiss.status_code == 422

    dismissed = client.post(
        f"/api/v1/control-recommendations/{rec['id']}/dismiss",
        headers=_headers(owner1, org1),
        json={"dismissal_reason": "No longer needed"},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    scoped_other = client.get("/api/v1/control-recommendations", headers=_headers(owner2, org2))
    assert scoped_other.status_code == 200
    assert scoped_other.json() == []

    summary = client.get("/api/v1/control-recommendations/summary", headers=_headers(owner1, org1))
    assert summary.status_code == 200
    body = summary.json()
    assert body["dismissed_recommendations"] >= 1

    runs = client.get("/api/v1/control-recommendations/runs", headers=_headers(owner1, org1))
    assert runs.status_code == 200

    logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org1))
        .all()
    )
    actions = {log.action for log in logs}
    assert "control_recommendations.generated" in actions
    assert "control_recommendation.dismissed" in actions


def test_readonly_cannot_run_live_generation_without_controls_write(client, db_session):
    owner = _register(client, "p36-owner7@example.com", "Pass1234!@", "P36 Org7")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    _set_obligation_state(client, owner, org, obligation["id"], "applicable")

    readonly = _create_active_user_with_role(db_session, org, "p36-readonly@example.com", "readonly")
    readonly_token = _login(client, readonly.email, "Pass1234!@")

    dry_ok = client.post(
        f"/api/v1/frameworks/{framework['id']}/control-recommendations/generate",
        headers=_headers(readonly_token, org),
        json={"dry_run": True},
    )
    assert dry_ok.status_code == 200

    live_forbidden = client.post(
        f"/api/v1/frameworks/{framework['id']}/control-recommendations/generate",
        headers=_headers(readonly_token, org),
        json={"dry_run": False},
    )
    assert live_forbidden.status_code == 403
