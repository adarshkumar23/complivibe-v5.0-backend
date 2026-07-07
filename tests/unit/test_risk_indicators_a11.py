from datetime import UTC, date, datetime, timedelta
import uuid

from app.core.security import get_password_hash
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.risk_indicator import RiskIndicator
from app.models.role import Role
from app.models.task import Task
from app.models.user import User
from app.models.vendor import Vendor
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/risk-indicators"


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


def _create_indicator(
    client,
    headers: dict[str, str],
    *,
    owner_user_id: str,
    name: str,
    metric_type: str,
    warning_threshold: float = 0.4,
    critical_threshold: float = 0.8,
    target_value: float = 0.2,
    linked_risk_id: str | None = None,
) -> dict:
    payload = {
        "name": name,
        "metric_type": metric_type,
        "target_value": target_value,
        "warning_threshold": warning_threshold,
        "critical_threshold": critical_threshold,
        "owner_user_id": owner_user_id,
    }
    if linked_risk_id is not None:
        payload["linked_risk_id"] = linked_risk_id
    response = client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _recalculate(client, headers: dict[str, str], indicator_id: str) -> dict:
    response = client.post(f"{BASE}/{indicator_id}/recalculate", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_a11_permissions_seeded(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-perms")

    keys = {p.key for p in db_session.query(Permission).all()}
    assert "risk_indicators:read" in keys
    assert "risk_indicators:write" in keys

    perms = client.get("/api/v1/auth/permissions", headers=org["org_headers"])
    assert perms.status_code == 200
    codes = set(perms.json()["permission_codes"])
    assert "risk_indicators:read" in codes
    assert "risk_indicators:write" in codes


def test_a11_kri_crud_and_archive(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-crud")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-crud-owner@example.com", "admin")

    created = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Open Alerts KRI",
        metric_type="open_alert_count",
    )
    assert created["status"] == "not_calculated"
    assert created["current_value"] is None

    listed = client.get(BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    detail = client.get(f"{BASE}/{created['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["name"] == "Open Alerts KRI"

    updated = client.patch(
        f"{BASE}/{created['id']}",
        headers=org["org_headers"],
        json={"name": "Open Alerts KRI Updated", "notes": "updated note"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Open Alerts KRI Updated"

    archived = client.post(
        f"{BASE}/{created['id']}/archive",
        headers=org["org_headers"],
        json={"archive_reason": "retired"},
    )
    assert archived.status_code == 200
    assert archived.json()["is_active"] is False
    assert archived.json()["archived_at"] is not None
    assert archived.json()["archive_reason"] == "retired"

    idempotent = client.post(
        f"{BASE}/{created['id']}/archive",
        headers=org["org_headers"],
        json={"archive_reason": "ignored-second-call"},
    )
    assert idempotent.status_code == 200
    assert idempotent.json()["archive_reason"] == "retired"


def test_a11_threshold_and_owner_and_linked_risk_validation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a11-val-a")
    org2 = bootstrap_org_user(client, email_prefix="a11-val-b")
    owner1 = _create_active_user_with_role(db_session, org1["organization_id"], "a11-val-owner1@example.com", "admin")
    owner2 = _create_active_user_with_role(db_session, org2["organization_id"], "a11-val-owner2@example.com", "admin")

    bad_threshold = client.post(
        BASE,
        headers=org1["org_headers"],
        json={
            "name": "Bad Thresholds",
            "metric_type": "open_alert_count",
            "target_value": 1,
            "warning_threshold": 2,
            "critical_threshold": 2,
            "owner_user_id": str(owner1.id),
        },
    )
    assert bad_threshold.status_code in {400, 422}

    bad_owner = client.post(
        BASE,
        headers=org1["org_headers"],
        json={
            "name": "Bad Owner",
            "metric_type": "open_alert_count",
            "target_value": 1,
            "warning_threshold": 2,
            "critical_threshold": 3,
            "owner_user_id": str(owner2.id),
        },
    )
    assert bad_owner.status_code == 400
    assert "owner_user_id" in bad_owner.json()["detail"]

    risk_other_org = client.post(
        "/api/v1/risks",
        headers=org2["org_headers"],
        json={
            "title": "Other Org Risk",
            "category": "security",
            "likelihood": 3,
            "impact": 4,
            "treatment_strategy": "mitigate",
            "owner_user_id": str(owner2.id),
        },
    )
    assert risk_other_org.status_code == 201

    bad_linked_risk = client.post(
        BASE,
        headers=org1["org_headers"],
        json={
            "name": "Bad Linked Risk",
            "metric_type": "open_alert_count",
            "target_value": 1,
            "warning_threshold": 2,
            "critical_threshold": 3,
            "owner_user_id": str(owner1.id),
            "linked_risk_id": risk_other_org.json()["id"],
        },
    )
    assert bad_linked_risk.status_code == 404


def test_a11_archived_indicator_blocks_updates(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-archive-block")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-archive-owner@example.com", "admin")

    created = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Archive Block",
        metric_type="open_alert_count",
    )
    archived = client.post(
        f"{BASE}/{created['id']}/archive",
        headers=org["org_headers"],
        json={"archive_reason": "no updates"},
    )
    assert archived.status_code == 200

    blocked = client.patch(
        f"{BASE}/{created['id']}",
        headers=org["org_headers"],
        json={"name": "Should Fail"},
    )
    assert blocked.status_code == 400


def test_a11_recalculate_control_expiry_rate_formula(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-expiry")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-expiry-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])
    now = datetime.now(UTC)

    c1 = Control(organization_id=org_id, title="C1", status="active", control_type="policy", criticality="high")
    c2 = Control(organization_id=org_id, title="C2", status="active", control_type="policy", criticality="high")
    c3 = Control(organization_id=org_id, title="C3", status="active", control_type="policy", criticality="high")
    db_session.add_all([c1, c2, c3])
    db_session.flush()

    e1 = EvidenceItem(organization_id=org_id, title="E1", status="approved", valid_until=now + timedelta(days=10))
    e2 = EvidenceItem(organization_id=org_id, title="E2", status="approved", valid_until=now + timedelta(days=60))
    db_session.add_all([e1, e2])
    db_session.flush()

    db_session.add_all(
        [
            EvidenceControlLink(organization_id=org_id, evidence_item_id=e1.id, control_id=c1.id, link_status="active"),
            EvidenceControlLink(organization_id=org_id, evidence_item_id=e2.id, control_id=c2.id, link_status="active"),
        ]
    )
    db_session.commit()

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Control Expiry Rate",
        metric_type="control_expiry_rate",
        warning_threshold=0.2,
        critical_threshold=0.5,
    )
    recalculated = _recalculate(client, org["org_headers"], indicator["id"])
    assert abs(recalculated["current_value"] - (1 / 3)) < 0.0002
    assert recalculated["status"] == "amber"


def test_a11_recalculate_evidence_gap_rate_formula(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-gap")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-gap-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    c1 = Control(organization_id=org_id, title="G1", status="active", control_type="policy", criticality="high")
    c2 = Control(organization_id=org_id, title="G2", status="active", control_type="policy", criticality="high")
    c3 = Control(organization_id=org_id, title="G3", status="active", control_type="policy", criticality="high")
    db_session.add_all([c1, c2, c3])
    db_session.flush()

    e1 = EvidenceItem(organization_id=org_id, title="GE1", status="approved")
    e2 = EvidenceItem(organization_id=org_id, title="GE2", status="approved")
    db_session.add_all([e1, e2])
    db_session.flush()

    db_session.add_all(
        [
            EvidenceControlLink(organization_id=org_id, evidence_item_id=e1.id, control_id=c1.id, link_status="active"),
            EvidenceControlLink(organization_id=org_id, evidence_item_id=e2.id, control_id=c2.id, link_status="active"),
        ]
    )
    db_session.commit()

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Evidence Gap Rate",
        metric_type="evidence_gap_rate",
        warning_threshold=0.2,
        critical_threshold=0.5,
    )
    recalculated = _recalculate(client, org["org_headers"], indicator["id"])
    assert abs(recalculated["current_value"] - (1 / 3)) < 0.0002
    assert recalculated["status"] == "amber"


def test_a11_recalculate_overdue_task_rate_formula(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-task")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-task-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])
    now = datetime.now(UTC)

    db_session.add_all(
        [
            Task(organization_id=org_id, title="T1", status="open", due_date=now - timedelta(days=1), task_type="general"),
            Task(organization_id=org_id, title="T2", status="in_progress", due_date=now - timedelta(hours=2), task_type="general"),
            Task(organization_id=org_id, title="T3", status="open", due_date=now + timedelta(days=1), task_type="general"),
            Task(organization_id=org_id, title="T4", status="completed", due_date=now - timedelta(days=2), task_type="general"),
        ]
    )
    db_session.commit()

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Overdue Task Rate",
        metric_type="overdue_task_rate",
        warning_threshold=0.5,
        critical_threshold=0.7,
    )
    recalculated = _recalculate(client, org["org_headers"], indicator["id"])
    assert abs(recalculated["current_value"] - (2 / 3)) < 0.0002
    assert recalculated["status"] == "amber"


def test_a11_recalculate_vendor_high_risk_count_formula(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-vendor-count")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-vendor-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    db_session.add_all(
        [
            Vendor(organization_id=org_id, name="V1", vendor_type="software", owner_user_id=owner.id, risk_tier="high", status="active"),
            Vendor(organization_id=org_id, name="V2", vendor_type="software", owner_user_id=owner.id, risk_tier="critical", status="under_review"),
            Vendor(organization_id=org_id, name="V3", vendor_type="software", owner_user_id=owner.id, risk_tier="low", status="active"),
            Vendor(organization_id=org_id, name="V4", vendor_type="software", owner_user_id=owner.id, risk_tier="high", status="archived"),
        ]
    )
    db_session.commit()

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="High Risk Vendor Count",
        metric_type="vendor_high_risk_count",
        warning_threshold=2,
        critical_threshold=3,
    )
    recalculated = _recalculate(client, org["org_headers"], indicator["id"])
    assert recalculated["current_value"] == 2.0
    assert recalculated["status"] == "amber"


def test_a11_recalculate_open_alert_count_formula(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-alert-count")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-alert-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    db_session.add_all(
        [
            ControlMonitoringAlert(
                organization_id=org_id,
                alert_type="manual",
                severity="high",
                status="open",
                title="A1",
            ),
            ControlMonitoringAlert(
                organization_id=org_id,
                alert_type="manual",
                severity="medium",
                status="open",
                title="A2",
            ),
            ControlMonitoringAlert(
                organization_id=org_id,
                alert_type="manual",
                severity="low",
                status="resolved",
                title="A3",
            ),
        ]
    )
    db_session.commit()

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Open Alert Count",
        metric_type="open_alert_count",
        warning_threshold=2,
        critical_threshold=3,
    )
    recalculated = _recalculate(client, org["org_headers"], indicator["id"])
    assert recalculated["current_value"] == 2.0
    assert recalculated["status"] == "amber"


def test_a11_recalculate_policy_overdue_review_formula(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-policy-review")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-policy-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])
    today = date.today()
    now = datetime.now(UTC)

    db_session.add_all(
        [
            CompliancePolicy(
                organization_id=org_id,
                title="P1",
                policy_type="security",
                status="approved",
                owner_user_id=owner.id,
                review_due_date=today - timedelta(days=1),
            ),
            CompliancePolicy(
                organization_id=org_id,
                title="P2",
                policy_type="security",
                status="approved",
                owner_user_id=owner.id,
                review_due_date=today + timedelta(days=5),
            ),
            CompliancePolicy(
                organization_id=org_id,
                title="P3",
                policy_type="security",
                status="draft",
                owner_user_id=owner.id,
                review_due_date=today - timedelta(days=3),
            ),
            CompliancePolicy(
                organization_id=org_id,
                title="P4",
                policy_type="security",
                status="approved",
                owner_user_id=owner.id,
                review_due_date=today - timedelta(days=2),
                archived_at=now,
            ),
        ]
    )
    db_session.commit()

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Policy Overdue Review",
        metric_type="policy_overdue_review",
        warning_threshold=1,
        critical_threshold=2,
    )
    recalculated = _recalculate(client, org["org_headers"], indicator["id"])
    assert recalculated["current_value"] == 1.0
    assert recalculated["status"] == "amber"


def test_a11_status_derivation_green_amber_red(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-status")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-status-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Open Alerts Status",
        metric_type="open_alert_count",
        warning_threshold=1,
        critical_threshold=2,
    )

    green = _recalculate(client, org["org_headers"], indicator["id"])
    assert green["current_value"] == 0.0
    assert green["status"] == "green"

    db_session.add(ControlMonitoringAlert(organization_id=org_id, alert_type="manual", severity="high", status="open", title="S1"))
    db_session.commit()
    amber = _recalculate(client, org["org_headers"], indicator["id"])
    assert amber["current_value"] == 1.0
    assert amber["status"] == "amber"

    db_session.add(ControlMonitoringAlert(organization_id=org_id, alert_type="manual", severity="high", status="open", title="S2"))
    db_session.commit()
    red = _recalculate(client, org["org_headers"], indicator["id"])
    assert red["current_value"] == 2.0
    assert red["status"] == "red"


def test_a11_breach_detail_explains_which_threshold_and_by_how_much(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-breach")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-breach-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Open Alerts Breach Detail",
        metric_type="open_alert_count",
        warning_threshold=1,
        critical_threshold=2,
    )

    # Green: no breach_detail should be surfaced.
    green = _recalculate(client, org["org_headers"], indicator["id"])
    assert green["breach_detail"] is None

    db_session.add(ControlMonitoringAlert(organization_id=org_id, alert_type="manual", severity="high", status="open", title="S1"))
    db_session.add(ControlMonitoringAlert(organization_id=org_id, alert_type="manual", severity="high", status="open", title="S2"))
    db_session.commit()
    red = _recalculate(client, org["org_headers"], indicator["id"])
    assert red["status"] == "red"
    detail = red["breach_detail"]
    assert detail is not None
    assert detail["metric_type"] == "open_alert_count"
    assert detail["threshold_label"] == "critical_threshold"
    assert detail["threshold_value"] == 2.0
    assert detail["current_value"] == 2.0
    assert detail["margin_over_threshold"] == 0.0
    assert "critical_threshold" in detail["explanation"]

    # Not stale immediately after a fresh recalculate.
    assert red["stale"] is False


def test_a11_indicator_flagged_stale_when_never_calculated_or_old(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-stale")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-stale-owner@example.com", "admin")

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Never Calculated",
        metric_type="open_alert_count",
        warning_threshold=1,
        critical_threshold=2,
    )
    # Freshly created, never recalculated -> stale.
    fetched = client.get(f"{BASE}/{indicator['id']}", headers=org["org_headers"]).json()
    assert fetched["stale"] is True

    recalculated = _recalculate(client, org["org_headers"], indicator["id"])
    assert recalculated["stale"] is False

    # Simulate the value having gone stale by backdating last_calculated_at beyond the
    # 24h staleness window, without anything else about the row changing.
    row = db_session.query(RiskIndicator).filter(RiskIndicator.id == uuid.UUID(indicator["id"])).one()
    row.last_calculated_at = datetime.now(UTC) - timedelta(hours=25)
    db_session.commit()

    fetched_again = client.get(f"{BASE}/{indicator['id']}", headers=org["org_headers"]).json()
    assert fetched_again["stale"] is True


def test_a11_custom_type_recalculate_returns_unchanged(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-custom")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-custom-owner@example.com", "admin")

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Custom KRI",
        metric_type="custom",
        warning_threshold=5,
        critical_threshold=10,
        target_value=1,
    )
    seeded = db_session.query(RiskIndicator).filter(RiskIndicator.id == uuid.UUID(indicator["id"])).one()
    seeded.current_value = 4.2
    seeded.status = "green"
    db_session.commit()

    recalculated = _recalculate(client, org["org_headers"], indicator["id"])
    assert recalculated["current_value"] == 4.2
    assert recalculated["status"] == "green"
    assert recalculated["last_calculated_at"] is None


def test_a11_summary_counts_by_status_and_metric_type(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-summary")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-summary-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])
    old = datetime.now(UTC) - timedelta(days=2)
    new = datetime.now(UTC) - timedelta(hours=1)

    db_session.add_all(
        [
            RiskIndicator(
                organization_id=org_id,
                name="R1",
                metric_type="open_alert_count",
                target_value=1,
                warning_threshold=2,
                critical_threshold=3,
                current_value=0.0,
                status="green",
                owner_user_id=owner.id,
                is_active=True,
                last_calculated_at=old,
            ),
            RiskIndicator(
                organization_id=org_id,
                name="R2",
                metric_type="vendor_high_risk_count",
                target_value=1,
                warning_threshold=2,
                critical_threshold=3,
                current_value=2.0,
                status="amber",
                owner_user_id=owner.id,
                is_active=True,
                last_calculated_at=new,
            ),
            RiskIndicator(
                organization_id=org_id,
                name="R3",
                metric_type="custom",
                target_value=1,
                warning_threshold=2,
                critical_threshold=3,
                current_value=None,
                status="not_calculated",
                owner_user_id=owner.id,
                is_active=True,
            ),
            RiskIndicator(
                organization_id=org_id,
                name="R4",
                metric_type="open_alert_count",
                target_value=1,
                warning_threshold=2,
                critical_threshold=3,
                current_value=4.0,
                status="red",
                owner_user_id=owner.id,
                is_active=False,
            ),
        ]
    )
    db_session.commit()

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_indicators"] == 3
    assert body["critical_count"] == 0
    assert body["warning_count"] == 1
    assert body["by_status"]["green"] == 1
    assert body["by_status"]["amber"] == 1
    assert body["by_status"]["not_calculated"] == 1
    assert body["by_metric_type"]["open_alert_count"] == 1
    assert body["by_metric_type"]["vendor_high_risk_count"] == 1
    assert body["by_metric_type"]["custom"] == 1
    assert body["last_calculated_at"] is not None


def test_a11_tenant_isolation_all_endpoints(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a11-tenant-a")
    org2 = bootstrap_org_user(client, email_prefix="a11-tenant-b")
    owner1 = _create_active_user_with_role(db_session, org1["organization_id"], "a11-tenant-owner1@example.com", "admin")
    _create_active_user_with_role(db_session, org2["organization_id"], "a11-tenant-owner2@example.com", "admin")

    created = _create_indicator(
        client,
        org1["org_headers"],
        owner_user_id=str(owner1.id),
        name="Tenant Scoped KRI",
        metric_type="open_alert_count",
    )

    list_org2 = client.get(BASE, headers=org2["org_headers"])
    assert list_org2.status_code == 200
    assert list_org2.json() == []

    summary_org2 = client.get(f"{BASE}/summary", headers=org2["org_headers"])
    assert summary_org2.status_code == 200
    assert summary_org2.json()["total_indicators"] == 0

    get_cross = client.get(f"{BASE}/{created['id']}", headers=org2["org_headers"])
    assert get_cross.status_code == 404

    patch_cross = client.patch(f"{BASE}/{created['id']}", headers=org2["org_headers"], json={"name": "cross"})
    assert patch_cross.status_code == 404

    recalc_cross = client.post(f"{BASE}/{created['id']}/recalculate", headers=org2["org_headers"])
    assert recalc_cross.status_code == 404

    archive_cross = client.post(
        f"{BASE}/{created['id']}/archive",
        headers=org2["org_headers"],
        json={"archive_reason": "cross"},
    )
    assert archive_cross.status_code == 404


def test_a11_recalculate_audit_event_contains_delta(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-audit")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-audit-owner@example.com", "admin")
    org_id = uuid.UUID(org["organization_id"])

    indicator = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Audit Delta",
        metric_type="open_alert_count",
        warning_threshold=1,
        critical_threshold=2,
    )
    _ = _recalculate(client, org["org_headers"], indicator["id"])

    db_session.add(ControlMonitoringAlert(organization_id=org_id, alert_type="manual", severity="high", status="open", title="AD1"))
    db_session.commit()
    _ = _recalculate(client, org["org_headers"], indicator["id"])

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    recalculated_logs = [row for row in logs.json() if row["action"] == "risk_indicator.recalculated"]
    assert len(recalculated_logs) >= 2
    last = recalculated_logs[0]
    context = last.get("metadata_json", {}).get("context_json")
    assert context is not None
    assert "previous_value" in context
    assert "new_value" in context
    assert "previous_status" in context
    assert "new_status" in context


def test_a11_include_archived_filter_behavior(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a11-filter")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a11-filter-owner@example.com", "admin")

    active = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Active KRI",
        metric_type="open_alert_count",
    )
    archived = _create_indicator(
        client,
        org["org_headers"],
        owner_user_id=str(owner.id),
        name="Archived KRI",
        metric_type="custom",
    )
    resp = client.post(
        f"{BASE}/{archived['id']}/archive",
        headers=org["org_headers"],
        json={"archive_reason": "retired"},
    )
    assert resp.status_code == 200

    default_list = client.get(BASE, headers=org["org_headers"])
    assert default_list.status_code == 200
    ids_default = {row["id"] for row in default_list.json()}
    assert active["id"] in ids_default
    assert archived["id"] not in ids_default

    include_archived = client.get(f"{BASE}?include_archived=true&is_active=false", headers=org["org_headers"])
    assert include_archived.status_code == 200
    ids_archived = {row["id"] for row in include_archived.json()}
    assert archived["id"] in ids_archived
