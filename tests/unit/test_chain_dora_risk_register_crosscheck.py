import uuid
from datetime import UTC, datetime, timedelta

from app.models.dora_ict_register import DORAICTRegister
from app.models.issue import Issue
from app.models.vendor import Vendor
from tests.helpers import bootstrap_admin_org


def test_dora_critical_missing_exit_strategy_creates_risk_register_entry(client, db_session):
    admin = bootstrap_admin_org(client, email_prefix="dorachain")
    headers = admin["org_headers"]

    create_resp = client.post(
        "/api/v1/compliance/dora/ict-register",
        headers=headers,
        json={
            "counterparty_name": "CloudCore Hosting Ltd",
            "service_description": "Primary core banking hosting provider",
            "is_critical_function": True,
            "sub_outsourcing_used": False,
            "exit_strategy_documented": False,
            "owner_id": admin["user_id"],
            "status": "active",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    entry = create_resp.json()
    print("DORA ENTRY:", entry)
    assert entry["risk_id"] is not None

    # The linked risk must be a real row in the risk register, visible via the risks API.
    risk_resp = client.get(f"/api/v1/risks/{entry['risk_id']}", headers=headers)
    assert risk_resp.status_code == 200, risk_resp.text
    risk = risk_resp.json()
    print("LINKED RISK:", risk)
    assert "CloudCore Hosting Ltd" in risk["title"]
    assert risk["category"] == "third_party"

    issues = db_session.query(Issue).filter(
        Issue.organization_id == uuid.UUID(admin["organization_id"]),
        Issue.source_type == "risk_assessment",
        Issue.source_id == uuid.UUID(entry["id"]),
    ).all()
    assert len(issues) == 1
    assert issues[0].issue_type == "vendor_failure"
    assert issues[0].owner_id == uuid.UUID(admin["user_id"])

    # Idempotency: updating the same entry again (still a gap) must not create a second risk.
    update_resp = client.patch(
        f"/api/v1/compliance/dora/ict-register/{entry['id']}",
        headers=headers,
        json={"service_description": "Primary core banking hosting provider (updated)"},
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["risk_id"] == entry["risk_id"]
    issue_count = db_session.query(Issue).filter(
        Issue.organization_id == uuid.UUID(admin["organization_id"]),
        Issue.source_type == "risk_assessment",
        Issue.source_id == uuid.UUID(entry["id"]),
    ).count()
    assert issue_count == 1

    # Audit trail: creation, and the risk link, and the underlying risk.created row.
    from app.models.audit_log import AuditLog

    rows = db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(admin["organization_id"])).all()
    actions = [(r.action, r.entity_type) for r in rows]
    print("AUDIT ACTIONS:", actions)
    assert ("dora.ict_entry_created", "dora_ict_register") in actions
    assert ("dora.ict_entry_risk_linked", "dora_ict_register") in actions
    assert ("risk.created", "risk") in actions
    assert ("issue.created", "issue") in actions


def test_dora_non_critical_provider_does_not_create_risk(client, db_session):
    admin = bootstrap_admin_org(client, email_prefix="dorachain2")
    headers = admin["org_headers"]

    create_resp = client.post(
        "/api/v1/compliance/dora/ict-register",
        headers=headers,
        json={
            "counterparty_name": "Minor Utility Vendor",
            "service_description": "Non-critical support tool",
            "is_critical_function": False,
            "sub_outsourcing_used": False,
            "exit_strategy_documented": False,
            "owner_id": admin["user_id"],
            "status": "active",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    assert create_resp.json()["risk_id"] is None


def test_dora_ict_register_rejects_cross_tenant_owner_and_vendor(client, db_session):
    org_a = bootstrap_admin_org(client, email_prefix="doracrossa")
    org_b = bootstrap_admin_org(client, email_prefix="doracrossb")

    vendor_b = Vendor(
        organization_id=uuid.UUID(org_b["organization_id"]),
        name="Other Org ICT Provider",
        vendor_type="technology",
        owner_user_id=uuid.UUID(org_b["user_id"]),
    )
    db_session.add(vendor_b)
    db_session.commit()
    db_session.refresh(vendor_b)

    base_payload = {
        "counterparty_name": "Cross Tenant Provider",
        "service_description": "Critical service",
        "is_critical_function": True,
        "sub_outsourcing_used": False,
        "exit_strategy_documented": True,
        "owner_id": org_a["user_id"],
        "status": "active",
    }

    bad_owner = client.post(
        "/api/v1/compliance/dora/ict-register",
        headers=org_a["org_headers"],
        json={**base_payload, "owner_id": org_b["user_id"]},
    )
    assert bad_owner.status_code == 422

    bad_vendor = client.post(
        "/api/v1/compliance/dora/ict-register",
        headers=org_a["org_headers"],
        json={**base_payload, "vendor_id": str(vendor_b.id)},
    )
    assert bad_vendor.status_code == 404
    assert (
        db_session.query(DORAICTRegister)
        .filter(DORAICTRegister.organization_id == uuid.UUID(org_a["organization_id"]))
        .filter(DORAICTRegister.counterparty_name == "Cross Tenant Provider")
        .count()
        == 0
    )
