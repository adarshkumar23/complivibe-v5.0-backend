from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect, select

from app.models.ai_system import AISystem
from app.models.audit_log import AuditLog
from app.models.business_unit import BusinessUnit
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.risk import Risk
from app.models.vendor import Vendor
from tests.helpers.auth_org import bootstrap_org_user


def test_business_units_schema_and_crud_tagging(client, db_session):
    inspector = inspect(db_session.bind)
    tables = set(inspector.get_table_names())
    assert "business_units" in tables

    for table_name in ["risks", "controls", "compliance_policies", "vendors", "ai_systems"]:
        columns = {c["name"] for c in inspector.get_columns(table_name)}
        assert "business_unit_id" in columns

    owner = bootstrap_org_user(client, email_prefix="bu-owner")
    headers = owner["org_headers"]
    org_id = UUID(owner["organization_id"])
    user_id = UUID(owner["user_id"])

    create_parent = client.post(
        "/api/v1/compliance/business-units",
        headers=headers,
        json={"name": "EMEA", "code": "EMEA", "description": "Region"},
    )
    assert create_parent.status_code == 201, create_parent.text
    parent = create_parent.json()
    parent_id = UUID(parent["id"])

    create_child_1 = client.post(
        "/api/v1/compliance/business-units",
        headers=headers,
        json={"name": "UK", "code": "UK", "parent_bu_id": str(parent_id)},
    )
    assert create_child_1.status_code == 201, create_child_1.text
    child_1_id = UUID(create_child_1.json()["id"])

    create_child_2 = client.post(
        "/api/v1/compliance/business-units",
        headers=headers,
        json={"name": "Germany", "code": "DE", "parent_bu_id": str(parent_id)},
    )
    assert create_child_2.status_code == 201, create_child_2.text

    dup = client.post(
        "/api/v1/compliance/business-units",
        headers=headers,
        json={"name": "EMEA Duplicate", "code": "EMEA"},
    )
    assert dup.status_code == 409

    other_org = bootstrap_org_user(client, email_prefix="bu-other")
    other_headers = other_org["org_headers"]

    cross_parent = client.post(
        "/api/v1/compliance/business-units",
        headers=other_headers,
        json={"name": "Bad Child", "code": "BAD", "parent_bu_id": str(parent_id)},
    )
    assert cross_parent.status_code == 404

    tree = client.get("/api/v1/compliance/business-units/tree", headers=headers)
    assert tree.status_code == 200
    payload = tree.json()
    assert len(payload) == 1
    assert payload[0]["code"] == "EMEA"
    assert len(payload[0]["children"]) == 2
    child_codes = sorted([item["code"] for item in payload[0]["children"]])
    assert child_codes == ["DE", "UK"]

    risk_1 = Risk(organization_id=org_id, title="Risk One", created_by_user_id=user_id)
    risk_2 = Risk(organization_id=org_id, title="Risk Two", created_by_user_id=user_id)
    control_1 = Control(organization_id=org_id, title="Control One", created_by_user_id=user_id)
    db_session.add_all([risk_1, risk_2, control_1])
    db_session.flush()

    tag_risk = client.post(
        "/api/v1/compliance/business-units/tag",
        headers=headers,
        json={
            "entity_type": "risk",
            "entity_id": str(risk_1.id),
            "business_unit_id": str(child_1_id),
        },
    )
    assert tag_risk.status_code == 200
    assert tag_risk.json()["business_unit_id"] == str(child_1_id)

    invalid_type = client.post(
        "/api/v1/compliance/business-units/tag",
        headers=headers,
        json={"entity_type": "bad_type", "entity_id": str(risk_1.id), "business_unit_id": str(child_1_id)},
    )
    assert invalid_type.status_code == 400

    other_bu_resp = client.post(
        "/api/v1/compliance/business-units",
        headers=other_headers,
        json={"name": "Other BU", "code": "OTH"},
    )
    assert other_bu_resp.status_code == 201
    other_bu_id = other_bu_resp.json()["id"]

    cross_org_tag = client.post(
        "/api/v1/compliance/business-units/tag",
        headers=headers,
        json={
            "entity_type": "risk",
            "entity_id": str(risk_1.id),
            "business_unit_id": other_bu_id,
        },
    )
    assert cross_org_tag.status_code == 404

    tag_risk_2 = client.post(
        "/api/v1/compliance/business-units/tag",
        headers=headers,
        json={
            "entity_type": "risk",
            "entity_id": str(risk_2.id),
            "business_unit_id": str(child_1_id),
        },
    )
    assert tag_risk_2.status_code == 200

    tag_control = client.post(
        "/api/v1/compliance/business-units/tag",
        headers=headers,
        json={
            "entity_type": "control",
            "entity_id": str(control_1.id),
            "business_unit_id": str(child_1_id),
        },
    )
    assert tag_control.status_code == 200

    summary = client.get(f"/api/v1/compliance/business-units/{child_1_id}/summary", headers=headers)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["entity_counts"]["risks"] == 2
    assert summary_body["entity_counts"]["controls"] == 1
    assert summary_body["total_tagged"] == 3

    risks_filtered = client.get(f"/api/v1/risks?business_unit_id={child_1_id}", headers=headers)
    assert risks_filtered.status_code == 200
    risk_ids = {UUID(item["id"]) for item in risks_filtered.json()}
    assert risk_ids == {risk_1.id, risk_2.id}

    untag = client.post(
        "/api/v1/compliance/business-units/tag",
        headers=headers,
        json={
            "entity_type": "risk",
            "entity_id": str(risk_1.id),
            "business_unit_id": None,
        },
    )
    assert untag.status_code == 200
    db_session.refresh(risk_1)
    assert risk_1.business_unit_id is None

    deactivate = client.post(f"/api/v1/compliance/business-units/{child_1_id}/deactivate", headers=headers)
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False
    deactivated_bu = db_session.get(BusinessUnit, child_1_id)
    assert deactivated_bu is not None
    assert deactivated_bu.deleted_at is None

    db_session.refresh(risk_2)
    assert risk_2.business_unit_id == child_1_id
    db_session.refresh(control_1)
    assert control_1.business_unit_id == child_1_id

    from_other_org = client.get("/api/v1/compliance/business-units", headers=other_headers)
    assert from_other_org.status_code == 200
    ids_from_other = {item["id"] for item in from_other_org.json()}
    assert str(parent_id) not in ids_from_other
    assert str(child_1_id) not in ids_from_other

    created_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "business_unit.created",
        )
    ).scalars().first()
    assert created_audit is not None

    tagged_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "business_unit.entity_tagged",
        )
    ).scalars().first()
    assert tagged_audit is not None


def test_policy_vendor_ai_system_tagging_and_soft_delete_behavior(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="bu-softdel")
    headers = owner["org_headers"]
    org_id = UUID(owner["organization_id"])
    user_id = UUID(owner["user_id"])

    create_bu = client.post(
        "/api/v1/compliance/business-units",
        headers=headers,
        json={"name": "North America", "code": "NA"},
    )
    assert create_bu.status_code == 201, create_bu.text
    bu_id = UUID(create_bu.json()["id"])

    risk = Risk(organization_id=org_id, title="SoftDelete Risk", created_by_user_id=user_id)
    control = Control(organization_id=org_id, title="SoftDelete Control", created_by_user_id=user_id)
    policy = CompliancePolicy(
        organization_id=org_id,
        title="SoftDelete Policy",
        policy_type="security",
        owner_user_id=user_id,
    )
    vendor = Vendor(
        organization_id=org_id,
        name="SoftDelete Vendor",
        vendor_type="processor",
        owner_user_id=user_id,
    )
    ai_system = AISystem(
        organization_id=org_id,
        name="SoftDelete AISystem",
        system_type="model",
    )
    db_session.add_all([risk, control, policy, vendor, ai_system])
    db_session.flush()

    for entity_type, entity_id in [
        ("risk", risk.id),
        ("control", control.id),
        ("policy", policy.id),
        ("vendor", vendor.id),
        ("ai_system", ai_system.id),
    ]:
        tag_resp = client.post(
            "/api/v1/compliance/business-units/tag",
            headers=headers,
            json={
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "business_unit_id": str(bu_id),
            },
        )
        assert tag_resp.status_code == 200, tag_resp.text
        assert tag_resp.json()["business_unit_id"] == str(bu_id)

    db_session.refresh(policy)
    db_session.refresh(vendor)
    db_session.refresh(ai_system)
    assert policy.business_unit_id == bu_id
    assert vendor.business_unit_id == bu_id
    assert ai_system.business_unit_id == bu_id

    delete_resp = client.delete(f"/api/v1/compliance/business-units/{bu_id}", headers=headers)
    assert delete_resp.status_code == 200, delete_resp.text

    deleted_bu = db_session.get(BusinessUnit, bu_id)
    assert deleted_bu is not None
    assert deleted_bu.deleted_at is not None

    default_list = client.get("/api/v1/compliance/business-units", headers=headers)
    assert default_list.status_code == 200
    listed_ids = {row["id"] for row in default_list.json()}
    assert str(bu_id) not in listed_ids

    tree = client.get("/api/v1/compliance/business-units/tree", headers=headers)
    assert tree.status_code == 200

    def _flatten(nodes):
        result = []
        for node in nodes:
            result.append(node["id"])
            result.extend(_flatten(node.get("children", [])))
        return result

    assert str(bu_id) not in set(_flatten(tree.json()))

    db_session.refresh(risk)
    db_session.refresh(control)
    db_session.refresh(policy)
    db_session.refresh(vendor)
    db_session.refresh(ai_system)
    assert risk.business_unit_id == bu_id
    assert control.business_unit_id == bu_id
    assert policy.business_unit_id == bu_id
    assert vendor.business_unit_id == bu_id
    assert ai_system.business_unit_id == bu_id
