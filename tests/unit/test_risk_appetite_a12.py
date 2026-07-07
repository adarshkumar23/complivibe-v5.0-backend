import uuid

from app.compliance.services.risk_appetite_service import RiskAppetiteService
from app.core.security import get_password_hash
from app.models.business_unit import BusinessUnit
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.risk import Risk
from app.models.risk_appetite_threshold import RiskAppetiteThreshold
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/risk-appetite"


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
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


def _create_threshold(
    client,
    headers: dict[str, str],
    *,
    scope_type: str,
    risk_category: str,
    max_acceptable_score: int,
    escalation_owner_id: str,
    scope_id: str | None = None,
    notes: str | None = None,
):
    payload = {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "risk_category": risk_category,
        "max_acceptable_score": max_acceptable_score,
        "escalation_owner_id": escalation_owner_id,
        "notes": notes,
    }
    response = client.post(BASE, headers=headers, json=payload)
    return response


def _create_risk(
    client,
    headers: dict[str, str],
    *,
    title: str,
    category: str,
    likelihood: int,
    impact: int,
    owner_user_id: str,
    metadata_json: dict | None = None,
):
    payload = {
        "title": title,
        "category": category,
        "likelihood": likelihood,
        "impact": impact,
        "treatment_strategy": "mitigate",
        "owner_user_id": owner_user_id,
        "metadata_json": metadata_json,
    }
    return client.post("/api/v1/risks", headers=headers, json=payload)


def test_a12_permissions_seeded(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-perms")

    keys = {p.key for p in db_session.query(Permission).all()}
    assert "risk_appetite:read" in keys
    assert "risk_appetite:write" in keys

    perms = client.get("/api/v1/auth/permissions", headers=org["org_headers"])
    assert perms.status_code == 200
    codes = set(perms.json()["permission_codes"])
    assert "risk_appetite:read" in codes
    assert "risk_appetite:write" in codes


def test_a12_threshold_crud_patch_deactivate_and_idempotent(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-crud")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-crud-owner@example.com", "admin")

    created = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="operational",
        max_acceptable_score=12,
        escalation_owner_id=str(escalation_owner.id),
        notes="initial",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["is_active"] is True

    listed = client.get(BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detail = client.get(f"{BASE}/{body['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["risk_category"] == "operational"

    updated = client.patch(
        f"{BASE}/{body['id']}",
        headers=org["org_headers"],
        json={"max_acceptable_score": 14, "notes": "updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["max_acceptable_score"] == 14
    assert updated.json()["notes"] == "updated"

    deactivated = client.post(
        f"{BASE}/{body['id']}/deactivate",
        headers=org["org_headers"],
        json={"reason": "superseded"},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert "Deactivated: superseded" in (deactivated.json()["notes"] or "")

    idempotent = client.post(
        f"{BASE}/{body['id']}/deactivate",
        headers=org["org_headers"],
        json={"reason": "ignored-second-call"},
    )
    assert idempotent.status_code == 200
    assert idempotent.json()["is_active"] is False
    assert "ignored-second-call" not in (idempotent.json()["notes"] or "")


def test_a12_max_acceptable_score_validation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-score-val")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-score-owner@example.com", "admin")

    low = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="financial",
        max_acceptable_score=0,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert low.status_code == 422

    high = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="financial",
        max_acceptable_score=26,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert high.status_code == 422


def test_a12_escalation_owner_must_be_active_org_member(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a12-owner-a")
    org2 = bootstrap_org_user(client, email_prefix="a12-owner-b")

    cross_owner = _create_active_user_with_role(db_session, org2["organization_id"], "a12-cross-owner@example.com", "admin")
    response = _create_threshold(
        client,
        org1["org_headers"],
        scope_type="org",
        risk_category="technology",
        max_acceptable_score=10,
        escalation_owner_id=str(cross_owner.id),
    )
    assert response.status_code == 400
    assert "escalation_owner_id" in response.json()["detail"]


def test_a12_business_unit_scope_must_belong_to_org(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a12-scope-a")
    org2 = bootstrap_org_user(client, email_prefix="a12-scope-b")
    escalation_owner = _create_active_user_with_role(db_session, org1["organization_id"], "a12-scope-owner@example.com", "admin")

    foreign_bu = BusinessUnit(
        organization_id=uuid.UUID(org2["organization_id"]),
        name="Foreign BU",
        code="FBU",
        is_active=True,
        created_by=uuid.UUID(org2["user_id"]),
        deleted_at=None,
    )
    db_session.add(foreign_bu)
    db_session.commit()

    response = _create_threshold(
        client,
        org1["org_headers"],
        scope_type="business_unit",
        scope_id=str(foreign_bu.id),
        risk_category="technology",
        max_acceptable_score=10,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert response.status_code == 400
    assert "scope_id" in response.json()["detail"]

    poisoned = (
        db_session.query(RiskAppetiteThreshold)
        .filter(
            RiskAppetiteThreshold.organization_id == uuid.UUID(org1["organization_id"]),
            RiskAppetiteThreshold.scope_id == foreign_bu.id,
        )
        .count()
    )
    assert poisoned == 0


def test_a12_duplicate_active_threshold_same_scope_category_returns_422(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-dup")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-dup-owner@example.com", "admin")

    first = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="compliance",
        max_acceptable_score=9,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert first.status_code == 201

    duplicate = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="compliance",
        max_acceptable_score=11,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert duplicate.status_code == 422
    assert duplicate.json()["detail"] == (
        "Active threshold already exists for this scope and category. "
        "Deactivate existing threshold before creating a new one."
    )


def test_a12_scope_and_category_not_patchable(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-no-patch")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-no-patch-owner@example.com", "admin")

    created = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="vendor",
        max_acceptable_score=7,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert created.status_code == 201

    patch_scope = client.patch(
        f"{BASE}/{created.json()['id']}",
        headers=org["org_headers"],
        json={"scope_type": "business_unit"},
    )
    assert patch_scope.status_code == 422

    patch_category = client.patch(
        f"{BASE}/{created.json()['id']}",
        headers=org["org_headers"],
        json={"risk_category": "financial"},
    )
    assert patch_category.status_code == 422


def test_a12_summary_categories_without_threshold_and_breach_count(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-summary")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-summary-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    c1 = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="operational",
        max_acceptable_score=10,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert c1.status_code == 201

    bu = BusinessUnit(
        organization_id=org_id,
        name="Summary BU",
        code="SUM",
        is_active=True,
        created_by=uuid.UUID(org["user_id"]),
        deleted_at=None,
    )
    db_session.add(bu)
    db_session.commit()
    bu_scope = str(bu.id)
    c2 = _create_threshold(
        client,
        org["org_headers"],
        scope_type="business_unit",
        scope_id=bu_scope,
        risk_category="financial",
        max_acceptable_score=8,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert c2.status_code == 201

    db_session.add(
        ControlMonitoringAlert(
            organization_id=org_id,
            alert_type="risk_threshold_breach",
            severity="high",
            status="open",
            title="Breach",
        )
    )
    db_session.commit()

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_thresholds"] == 2
    assert body["active_thresholds"] == 2
    assert body["by_category"]["operational"] == 1
    assert body["by_category"]["financial"] == 1
    assert body["breach_count"] == 1
    assert "operational" not in body["categories_without_threshold"]
    assert "financial" in body["categories_without_threshold"]


def test_a12_breaches_endpoint_returns_enriched_rows(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-breaches")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-breach-owner@example.com", "admin")

    threshold = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="operational",
        max_acceptable_score=10,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert threshold.status_code == 201

    risk_resp = _create_risk(
        client,
        org["org_headers"],
        title="Operational Risk",
        category="operational",
        likelihood=4,
        impact=4,
        owner_user_id=str(escalation_owner.id),
    )
    assert risk_resp.status_code == 201

    breaches = client.get(f"{BASE}/breaches", headers=org["org_headers"])
    assert breaches.status_code == 200
    rows = breaches.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["threshold_id"] == threshold.json()["id"]
    assert row["risk"]["id"] == risk_resp.json()["id"]
    assert row["risk"]["name"] == "Operational Risk"
    assert row["risk"]["score"] == 16
    assert row["risk"]["category"] == "operational"


def test_a12_check_appetite_breach_no_threshold_and_within_threshold(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-no-breach")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-no-breach-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    risk = Risk(
        organization_id=org_id,
        title="No threshold risk",
        category="operational",
        severity="medium",
        likelihood=2,
        impact=2,
        inherent_score=4,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=escalation_owner.id,
    )
    db_session.add(risk)
    db_session.commit()

    service = RiskAppetiteService(db_session)
    assert service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=12, risk_category="operational") is None

    threshold = RiskAppetiteThreshold(
        organization_id=org_id,
        scope_type="org",
        scope_id=None,
        risk_category="operational",
        max_acceptable_score=12,
        escalation_owner_id=escalation_owner.id,
        is_active=True,
        created_by_user_id=escalation_owner.id,
    )
    db_session.add(threshold)
    db_session.commit()

    assert service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=12, risk_category="operational") is None


def test_a12_check_appetite_breach_creates_alert_with_severity_context_and_assignment(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-breach-create")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-breach-create-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    risk = Risk(
        organization_id=org_id,
        title="Breach Risk",
        category="technology",
        severity="high",
        likelihood=4,
        impact=4,
        inherent_score=16,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=escalation_owner.id,
    )
    threshold = RiskAppetiteThreshold(
        organization_id=org_id,
        scope_type="org",
        scope_id=None,
        risk_category="technology",
        max_acceptable_score=10,
        escalation_owner_id=escalation_owner.id,
        is_active=True,
        created_by_user_id=escalation_owner.id,
    )
    db_session.add_all([risk, threshold])
    db_session.commit()

    service = RiskAppetiteService(db_session)
    alert = service.check_appetite_breach(
        org_id=org_id,
        risk_id=risk.id,
        new_score=16,
        risk_category="technology",
        actor_user_id=escalation_owner.id,
    )
    db_session.commit()

    assert alert is not None
    assert alert.alert_type == "risk_threshold_breach"
    assert alert.status == "open"
    assert alert.severity == "critical"
    assert alert.assigned_to_user_id == escalation_owner.id
    assert alert.alert_context_json is not None
    assert alert.alert_context_json["risk_id"] == str(risk.id)
    assert alert.alert_context_json["threshold_id"] == str(threshold.id)


def test_a12_check_appetite_breach_idempotent_second_call_no_duplicate(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-idem")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-idem-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    risk = Risk(
        organization_id=org_id,
        title="Idempotent Risk",
        category="compliance",
        severity="high",
        likelihood=5,
        impact=3,
        inherent_score=15,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=escalation_owner.id,
    )
    threshold = RiskAppetiteThreshold(
        organization_id=org_id,
        scope_type="org",
        scope_id=None,
        risk_category="compliance",
        max_acceptable_score=8,
        escalation_owner_id=escalation_owner.id,
        is_active=True,
        created_by_user_id=escalation_owner.id,
    )
    db_session.add_all([risk, threshold])
    db_session.commit()

    service = RiskAppetiteService(db_session)
    first = service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=15, risk_category="compliance")
    second = service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=15, risk_category="compliance")
    db_session.commit()

    assert first is not None
    # Second call with an unchanged score doesn't create a duplicate alert -- it now returns the
    # same still-open alert (rather than None) so callers get a reference to it, but the alert
    # count below is the real "no duplicate" invariant this test is about.
    assert second is not None
    assert second.id == first.id
    count = (
        db_session.query(ControlMonitoringAlert)
        .filter(
            ControlMonitoringAlert.organization_id == org_id,
            ControlMonitoringAlert.alert_type == "risk_threshold_breach",
            ControlMonitoringAlert.status == "open",
        )
        .count()
    )
    assert count == 1


def test_a12_breach_alert_auto_resolves_when_score_drops_back_under_threshold(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-autoresolve-score")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-ar-score-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    risk = Risk(
        organization_id=org_id,
        title="Recovering Risk",
        category="compliance",
        severity="high",
        likelihood=5,
        impact=3,
        inherent_score=15,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=escalation_owner.id,
    )
    threshold = RiskAppetiteThreshold(
        organization_id=org_id,
        scope_type="org",
        scope_id=None,
        risk_category="compliance",
        max_acceptable_score=8,
        escalation_owner_id=escalation_owner.id,
        is_active=True,
        created_by_user_id=escalation_owner.id,
    )
    db_session.add_all([risk, threshold])
    db_session.commit()

    service = RiskAppetiteService(db_session)
    breach_alert = service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=15, risk_category="compliance")
    db_session.commit()
    assert breach_alert is not None
    assert breach_alert.status == "open"

    # Score drops back under the threshold (e.g. after mitigation) -- the prior alert must not
    # keep reporting a "live" breach.
    resolved = service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=6, risk_category="compliance")
    db_session.commit()
    assert resolved is None

    db_session.refresh(breach_alert)
    assert breach_alert.status == "resolved"
    assert breach_alert.resolved_at is not None
    assert "no longer applies" in (breach_alert.resolution_notes or "")

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"]).json()
    actions = [item["action"] for item in logs]
    assert "risk_appetite.breach_auto_resolved" in actions

    # A subsequent re-breach creates a fresh alert rather than trying to reopen the resolved one.
    rebreach = service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=15, risk_category="compliance")
    db_session.commit()
    assert rebreach is not None
    assert rebreach.id != breach_alert.id
    assert rebreach.status == "open"


def test_a12_breach_alert_context_score_refreshed_on_repeat_breach(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-refresh-score")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-refresh-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    risk = Risk(
        organization_id=org_id,
        title="Worsening Risk",
        category="compliance",
        severity="high",
        likelihood=5,
        impact=3,
        inherent_score=15,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=escalation_owner.id,
    )
    threshold = RiskAppetiteThreshold(
        organization_id=org_id,
        scope_type="org",
        scope_id=None,
        risk_category="compliance",
        max_acceptable_score=8,
        escalation_owner_id=escalation_owner.id,
        is_active=True,
        created_by_user_id=escalation_owner.id,
    )
    db_session.add_all([risk, threshold])
    db_session.commit()

    service = RiskAppetiteService(db_session)
    first = service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=15, risk_category="compliance")
    db_session.commit()
    assert first.alert_context_json["new_score"] == 15

    # Risk gets worse while the alert is still open -- the existing alert's snapshot should track
    # the new value instead of continuing to show the original (now stale) score.
    worse = service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=20, risk_category="compliance")
    db_session.commit()
    assert worse.id == first.id
    db_session.refresh(first)
    assert first.alert_context_json["new_score"] == 20
    assert "20" in first.title


def test_a12_raising_threshold_auto_resolves_no_longer_breaching_alerts(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-autoresolve-raise")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-ar-raise-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    risk = Risk(
        organization_id=org_id,
        title="Threshold Raised Risk",
        category="compliance",
        severity="high",
        likelihood=5,
        impact=3,
        inherent_score=15,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=escalation_owner.id,
    )
    threshold = RiskAppetiteThreshold(
        organization_id=org_id,
        scope_type="org",
        scope_id=None,
        risk_category="compliance",
        max_acceptable_score=8,
        escalation_owner_id=escalation_owner.id,
        is_active=True,
        created_by_user_id=escalation_owner.id,
    )
    db_session.add_all([risk, threshold])
    db_session.commit()

    service = RiskAppetiteService(db_session)
    breach_alert = service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=15, risk_category="compliance")
    db_session.commit()
    assert breach_alert.status == "open"

    raise_threshold = client.patch(
        f"{BASE}/{threshold.id}",
        headers=org["org_headers"],
        json={"max_acceptable_score": 20},
    )
    assert raise_threshold.status_code == 200

    db_session.refresh(breach_alert)
    assert breach_alert.status == "resolved"
    assert "raised" in (breach_alert.resolution_notes or "")


def test_a12_deactivating_threshold_auto_resolves_its_open_alerts(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-autoresolve-deactivate")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-ar-deact-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    risk = Risk(
        organization_id=org_id,
        title="Threshold Deactivated Risk",
        category="compliance",
        severity="high",
        likelihood=5,
        impact=3,
        inherent_score=15,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=escalation_owner.id,
    )
    threshold = RiskAppetiteThreshold(
        organization_id=org_id,
        scope_type="org",
        scope_id=None,
        risk_category="compliance",
        max_acceptable_score=8,
        escalation_owner_id=escalation_owner.id,
        is_active=True,
        created_by_user_id=escalation_owner.id,
    )
    db_session.add_all([risk, threshold])
    db_session.commit()

    service = RiskAppetiteService(db_session)
    breach_alert = service.check_appetite_breach(org_id=org_id, risk_id=risk.id, new_score=15, risk_category="compliance")
    db_session.commit()
    assert breach_alert.status == "open"

    deactivate = client.post(
        f"{BASE}/{threshold.id}/deactivate",
        headers=org["org_headers"],
        json={"reason": "No longer relevant"},
    )
    assert deactivate.status_code == 200

    db_session.refresh(breach_alert)
    assert breach_alert.status == "resolved"
    assert "deactivated" in (breach_alert.resolution_notes or "")


def test_a12_derive_severity_bands():
    service = RiskAppetiteService(db=None)  # type: ignore[arg-type]
    assert service.derive_severity(15, 10) == "critical"
    assert service.derive_severity(12, 10) == "high"
    assert service.derive_severity(10, 10) == "medium"
    assert service.derive_severity(9, 10) == "low"


def test_a12_most_specific_business_unit_threshold_precedence(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-specific")
    owner_a = _create_active_user_with_role(db_session, org["organization_id"], "a12-specific-a@example.com", "admin")
    owner_b = _create_active_user_with_role(db_session, org["organization_id"], "a12-specific-b@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])
    bu_id = uuid.uuid4()

    risk = Risk(
        organization_id=org_id,
        title="BU Risk",
        category="vendor",
        severity="high",
        likelihood=4,
        impact=2,
        inherent_score=8,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=owner_a.id,
        metadata_json={"business_unit_id": str(bu_id)},
    )
    org_threshold = RiskAppetiteThreshold(
        organization_id=org_id,
        scope_type="org",
        scope_id=None,
        risk_category="vendor",
        max_acceptable_score=10,
        escalation_owner_id=owner_a.id,
        is_active=True,
        created_by_user_id=owner_a.id,
    )
    bu_threshold = RiskAppetiteThreshold(
        organization_id=org_id,
        scope_type="business_unit",
        scope_id=bu_id,
        risk_category="vendor",
        max_acceptable_score=5,
        escalation_owner_id=owner_b.id,
        is_active=True,
        created_by_user_id=owner_b.id,
    )
    db_session.add_all([risk, org_threshold, bu_threshold])
    db_session.commit()

    alert = RiskAppetiteService(db_session).check_appetite_breach(
        org_id=org_id,
        risk_id=risk.id,
        new_score=8,
        risk_category="vendor",
        actor_user_id=owner_a.id,
    )
    db_session.commit()

    assert alert is not None
    assert alert.assigned_to_user_id == owner_b.id
    assert alert.alert_context_json is not None
    assert alert.alert_context_json["threshold_id"] == str(bu_threshold.id)
    assert alert.alert_context_json["scope_type"] == "business_unit"
    assert alert.alert_context_json["scope_id"] == str(bu_id)


def test_a12_breach_detected_audit_context_and_integration_hook_on_risk_update(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-audit")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-audit-owner@example.com", "admin")

    threshold = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="operational",
        max_acceptable_score=10,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert threshold.status_code == 201

    risk = _create_risk(
        client,
        org["org_headers"],
        title="Hook Risk",
        category="operational",
        likelihood=2,
        impact=2,
        owner_user_id=str(escalation_owner.id),
    )
    assert risk.status_code == 201

    no_breaches = client.get(f"{BASE}/breaches", headers=org["org_headers"])
    assert no_breaches.status_code == 200
    assert no_breaches.json() == []

    updated = client.patch(
        f"/api/v1/risks/{risk.json()['id']}",
        headers=org["org_headers"],
        json={"likelihood": 5, "impact": 5},
    )
    assert updated.status_code == 200
    assert updated.json()["inherent_score"] == 25

    breaches = client.get(f"{BASE}/breaches", headers=org["org_headers"])
    assert breaches.status_code == 200
    assert len(breaches.json()) == 1

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    breach_logs = [row for row in logs.json() if row["action"] == "risk_appetite.breach_detected"]
    assert len(breach_logs) >= 1
    context = breach_logs[0].get("metadata_json", {}).get("context_json")
    assert context is not None
    assert context["risk_id"] == risk.json()["id"]
    assert context["threshold_id"] == threshold.json()["id"]
    assert context["score"] == 25
    assert context["max_score"] == 10


def test_a12_include_inactive_filter_behavior(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a12-filter")
    escalation_owner = _create_active_user_with_role(db_session, org["organization_id"], "a12-filter-owner@example.com", "admin")

    active = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="operational",
        max_acceptable_score=12,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert active.status_code == 201

    inactive = _create_threshold(
        client,
        org["org_headers"],
        scope_type="org",
        risk_category="technology",
        max_acceptable_score=12,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert inactive.status_code == 201
    deact = client.post(
        f"{BASE}/{inactive.json()['id']}/deactivate",
        headers=org["org_headers"],
        json={"reason": "retired"},
    )
    assert deact.status_code == 200

    default_rows = client.get(BASE, headers=org["org_headers"])
    assert default_rows.status_code == 200
    ids_default = {row["id"] for row in default_rows.json()}
    assert active.json()["id"] in ids_default
    assert inactive.json()["id"] not in ids_default

    include_rows = client.get(f"{BASE}?include_inactive=true", headers=org["org_headers"])
    assert include_rows.status_code == 200
    ids_include = {row["id"] for row in include_rows.json()}
    assert active.json()["id"] in ids_include
    assert inactive.json()["id"] in ids_include


def test_a12_tenant_isolation_all_endpoints(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a12-tenant-a")
    org2 = bootstrap_org_user(client, email_prefix="a12-tenant-b")

    escalation_owner = _create_active_user_with_role(db_session, org1["organization_id"], "a12-tenant-owner@example.com", "admin")

    created = _create_threshold(
        client,
        org1["org_headers"],
        scope_type="org",
        risk_category="reputational",
        max_acceptable_score=10,
        escalation_owner_id=str(escalation_owner.id),
    )
    assert created.status_code == 201

    list_org2 = client.get(BASE, headers=org2["org_headers"])
    assert list_org2.status_code == 200
    assert list_org2.json() == []

    summary_org2 = client.get(f"{BASE}/summary", headers=org2["org_headers"])
    assert summary_org2.status_code == 200
    assert summary_org2.json()["total_thresholds"] == 0

    breaches_org2 = client.get(f"{BASE}/breaches", headers=org2["org_headers"])
    assert breaches_org2.status_code == 200
    assert breaches_org2.json() == []

    get_cross = client.get(f"{BASE}/{created.json()['id']}", headers=org2["org_headers"])
    assert get_cross.status_code == 404

    patch_cross = client.patch(
        f"{BASE}/{created.json()['id']}",
        headers=org2["org_headers"],
        json={"max_acceptable_score": 11},
    )
    assert patch_cross.status_code == 404

    deactivate_cross = client.post(
        f"{BASE}/{created.json()['id']}/deactivate",
        headers=org2["org_headers"],
        json={"reason": "cross"},
    )
    assert deactivate_cross.status_code == 404
