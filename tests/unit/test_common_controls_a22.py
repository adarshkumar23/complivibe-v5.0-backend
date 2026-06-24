from datetime import date, datetime, timedelta, UTC
import uuid

from app.core.security import get_password_hash
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/common-controls"


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str = "admin") -> User:
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
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def _create_control(client, headers: dict[str, str], *, title: str) -> dict:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "policy", "criticality": "medium"},
    )
    assert response.status_code == 201
    return response.json()


def _create_evidence(client, headers: dict[str, str], *, title: str, valid_until_days: int = 30) -> dict:
    response = client.post(
        "/api/v1/evidence",
        headers=headers,
        json={
            "title": title,
            "evidence_type": "policy_document",
            "source": "manual",
            "valid_until": (datetime.now(UTC) + timedelta(days=valid_until_days)).isoformat(),
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_framework_obligation(db_session, *, code: str, name: str, reference_code: str) -> tuple[Framework, Obligation]:
    framework = Framework(
        code=code,
        name=name,
        description=f"{name} desc",
        category="Security",
        jurisdiction="United States",
        authority="Test Authority",
        version="1.0",
        status="active",
        coverage_level="starter",
        source_url=None,
        effective_date=date.today(),
    )
    db_session.add(framework)
    db_session.flush()

    obligation = Obligation(
        framework_id=framework.id,
        framework_section_id=None,
        reference_code=reference_code,
        title=f"{reference_code} obligation",
        description="obligation",
        plain_language_summary="summary",
        obligation_type="control",
        jurisdiction="United States",
        source_url=None,
        version="1.0",
        status="active",
        effective_date=date.today(),
        parent_obligation_id=None,
    )
    db_session.add(obligation)
    db_session.flush()
    db_session.commit()
    return framework, obligation


def _activate_framework_for_org(db_session, org_id: str, framework_id: uuid.UUID, actor_user_id: str | None = None) -> None:
    row = OrganizationFramework(
        organization_id=uuid.UUID(org_id),
        framework_id=framework_id,
        status="active",
        activated_by_user_id=uuid.UUID(actor_user_id) if actor_user_id else None,
        activated_at=datetime.now(UTC),
        deactivated_by_user_id=None,
        deactivated_at=None,
        notes="test",
    )
    db_session.add(row)
    db_session.commit()


def test_a22_mapping_create_duplicate_and_validation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a22-map-a")
    org2 = bootstrap_org_user(client, email_prefix="a22-map-b")

    control1 = _create_control(client, org1["org_headers"], title="A22 Control 1")
    control2 = _create_control(client, org2["org_headers"], title="A22 Control 2")

    fw1, ob1 = _create_framework_obligation(db_session, code="A22-FW1", name="A22 Framework 1", reference_code="CC6.1")
    fw2, ob2 = _create_framework_obligation(db_session, code="A22-FW2", name="A22 Framework 2", reference_code="A.9.4.2")
    _activate_framework_for_org(db_session, org1["organization_id"], fw1.id, org1["user_id"])

    created = client.post(
        f"{BASE}/mappings",
        headers=org1["org_headers"],
        json={
            "control_id": control1["id"],
            "framework_id": str(fw1.id),
            "obligation_id": str(ob1.id),
            "section_reference": "CC6.1",
            "mapping_rationale": "single control covers requirement",
            "mapping_strength": "full",
        },
    )
    assert created.status_code == 201

    duplicate = client.post(
        f"{BASE}/mappings",
        headers=org1["org_headers"],
        json={
            "control_id": control1["id"],
            "framework_id": str(fw1.id),
            "obligation_id": str(ob1.id),
            "mapping_strength": "full",
        },
    )
    assert duplicate.status_code == 422

    control_not_in_org = client.post(
        f"{BASE}/mappings",
        headers=org1["org_headers"],
        json={
            "control_id": control2["id"],
            "framework_id": str(fw1.id),
            "obligation_id": str(ob1.id),
            "mapping_strength": "full",
        },
    )
    assert control_not_in_org.status_code == 404

    framework_not_active = client.post(
        f"{BASE}/mappings",
        headers=org1["org_headers"],
        json={
            "control_id": control1["id"],
            "framework_id": str(fw2.id),
            "obligation_id": str(ob2.id),
            "mapping_strength": "full",
        },
    )
    assert framework_not_active.status_code == 422

    obligation_not_found = client.post(
        f"{BASE}/mappings",
        headers=org1["org_headers"],
        json={
            "control_id": control1["id"],
            "framework_id": str(fw1.id),
            "obligation_id": str(uuid.uuid4()),
            "mapping_strength": "full",
        },
    )
    assert obligation_not_found.status_code == 404


def test_a22_patch_deactivate_coverage_and_reports(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a22-reports")
    control = _create_control(client, org["org_headers"], title="A22 Coverage Control")

    fw1, ob1 = _create_framework_obligation(db_session, code="A22-COV1", name="Coverage FW 1", reference_code="CC6.1")
    fw2, ob2 = _create_framework_obligation(db_session, code="A22-COV2", name="Coverage FW 2", reference_code="IA-2")
    _activate_framework_for_org(db_session, org["organization_id"], fw1.id, org["user_id"])
    _activate_framework_for_org(db_session, org["organization_id"], fw2.id, org["user_id"])

    m1 = client.post(
        f"{BASE}/mappings",
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "framework_id": str(fw1.id),
            "obligation_id": str(ob1.id),
            "section_reference": "CC6.1",
            "mapping_strength": "full",
            "mapping_rationale": "initial",
        },
    )
    assert m1.status_code == 201
    mapping1 = m1.json()

    patch = client.patch(
        f"{BASE}/mappings/{mapping1['id']}",
        headers=org["org_headers"],
        json={"mapping_rationale": "updated rationale", "mapping_strength": "partial"},
    )
    assert patch.status_code == 200
    assert patch.json()["mapping_rationale"] == "updated rationale"
    assert patch.json()["mapping_strength"] == "partial"

    ev1 = _create_evidence(client, org["org_headers"], title="A22 Evidence 1", valid_until_days=90)
    ev2 = _create_evidence(client, org["org_headers"], title="A22 Evidence 2", valid_until_days=90)
    ev3 = _create_evidence(client, org["org_headers"], title="A22 Evidence 3", valid_until_days=90)

    c1 = client.post(
        f"{BASE}/evidence-coverage",
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "evidence_id": ev1["id"],
            "mapping_id": mapping1["id"],
            "coverage_status": "covers",
            "coverage_notes": "good",
        },
    )
    assert c1.status_code == 201

    c2 = client.post(
        f"{BASE}/evidence-coverage",
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "evidence_id": ev2["id"],
            "mapping_id": mapping1["id"],
            "coverage_status": "partial",
        },
    )
    assert c2.status_code == 201

    c3 = client.post(
        f"{BASE}/evidence-coverage",
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "evidence_id": ev3["id"],
            "mapping_id": mapping1["id"],
            "coverage_status": "insufficient",
        },
    )
    assert c3.status_code == 201

    duplicate_cov = client.post(
        f"{BASE}/evidence-coverage",
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "evidence_id": ev1["id"],
            "mapping_id": mapping1["id"],
            "coverage_status": "covers",
        },
    )
    assert duplicate_cov.status_code == 422

    m2 = client.post(
        f"{BASE}/mappings",
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "framework_id": str(fw2.id),
            "obligation_id": str(ob2.id),
            "section_reference": "IA-2",
            "mapping_strength": "full",
        },
    )
    assert m2.status_code == 201
    mapping2 = m2.json()

    reuse_link = client.post(
        f"{BASE}/evidence-coverage",
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "evidence_id": ev1["id"],
            "mapping_id": mapping2["id"],
            "coverage_status": "covers",
        },
    )
    assert reuse_link.status_code == 201

    coverage = client.get(f"{BASE}/coverage/{control['id']}", headers=org["org_headers"])
    assert coverage.status_code == 200
    report = coverage.json()
    assert report["control"]["id"] == control["id"]
    assert report["total_frameworks"] == 2
    assert report["total_obligations"] == 2
    assert len(report["frameworks_covered"]) == 2

    fw1_report = next(item for item in report["frameworks_covered"] if item["framework_id"] == str(fw1.id))
    ob_report = fw1_report["obligations"][0]
    assert ob_report["section_reference"] == "CC6.1"
    assert ob_report["coverage_summary"]["total_evidence"] == 3
    assert ob_report["coverage_summary"]["covering"] == 1
    assert ob_report["coverage_summary"]["partial"] == 1
    assert ob_report["coverage_summary"]["insufficient"] == 1
    assert ob_report["coverage_summary"]["coverage_pct"] == 33.33

    reuse = client.get(f"{BASE}/evidence-reuse", headers=org["org_headers"])
    assert reuse.status_code == 200
    reuse_body = reuse.json()
    assert reuse_body["total_evidence_items"] == 3
    assert reuse_body["reused_count"] == 1
    assert reuse_body["reuse_rate"] == 0.3333
    reused_item = reuse_body["reused_evidence"][0]
    assert reused_item["evidence_id"] == ev1["id"]
    assert reused_item["reuse_count"] == 2
    assert "Coverage FW 1" in reused_item["frameworks_covered"]
    assert "Coverage FW 2" in reused_item["frameworks_covered"]

    control_b = _create_control(client, org["org_headers"], title="A22 Single Framework Control")
    single = client.post(
        f"{BASE}/mappings",
        headers=org["org_headers"],
        json={
            "control_id": control_b["id"],
            "framework_id": str(fw1.id),
            "obligation_id": str(ob1.id),
            "mapping_strength": "compensating",
        },
    )
    assert single.status_code == 201

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["total_common_controls"] == 1
    assert summary_body["total_mappings"] == 3
    assert summary_body["by_mapping_strength"]["partial"] >= 1
    assert summary_body["frameworks_with_common_controls"] == 2
    assert summary_body["top_common_controls"][0]["control_id"] == control["id"]
    assert summary_body["top_common_controls"][0]["framework_count"] == 2

    deactivate = client.delete(f"{BASE}/mappings/{mapping2['id']}", headers=org["org_headers"])
    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == "inactive"


def test_a22_tenant_isolation_and_audit_events(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a22-tenant-a")
    org2 = bootstrap_org_user(client, email_prefix="a22-tenant-b")

    control1 = _create_control(client, org1["org_headers"], title="A22 T1")

    fw, ob = _create_framework_obligation(db_session, code="A22-TEN", name="Tenant FW", reference_code="T-1")
    _activate_framework_for_org(db_session, org1["organization_id"], fw.id, org1["user_id"])

    created = client.post(
        f"{BASE}/mappings",
        headers=org1["org_headers"],
        json={
            "control_id": control1["id"],
            "framework_id": str(fw.id),
            "obligation_id": str(ob.id),
            "mapping_strength": "full",
            "mapping_rationale": "tenant test",
        },
    )
    assert created.status_code == 201
    mapping = created.json()

    updated = client.patch(
        f"{BASE}/mappings/{mapping['id']}",
        headers=org1["org_headers"],
        json={"mapping_rationale": "tenant test updated", "mapping_strength": "partial"},
    )
    assert updated.status_code == 200

    list_org2 = client.get(f"{BASE}/mappings", headers=org2["org_headers"])
    assert list_org2.status_code == 200
    assert all(item["organization_id"] == org2["organization_id"] for item in list_org2.json())

    patch_cross = client.patch(
        f"{BASE}/mappings/{mapping['id']}",
        headers=org2["org_headers"],
        json={"mapping_rationale": "cross"},
    )
    assert patch_cross.status_code == 404

    delete_cross = client.delete(f"{BASE}/mappings/{mapping['id']}", headers=org2["org_headers"])
    assert delete_cross.status_code == 404

    coverage_cross = client.get(f"{BASE}/coverage/{control1['id']}", headers=org2["org_headers"])
    assert coverage_cross.status_code == 404

    deactivate = client.delete(f"{BASE}/mappings/{mapping['id']}", headers=org1["org_headers"])
    assert deactivate.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=org1["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "common_control.mapping_created" in actions
    assert "common_control.mapping_updated" in actions
    assert "common_control.mapping_deactivated" in actions
