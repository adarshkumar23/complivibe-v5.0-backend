import uuid
from datetime import UTC, datetime, timedelta

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

    # Idempotency: updating the same entry again (still a gap) must not create a second risk.
    update_resp = client.patch(
        f"/api/v1/compliance/dora/ict-register/{entry['id']}",
        headers=headers,
        json={"service_description": "Primary core banking hosting provider (updated)"},
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["risk_id"] == entry["risk_id"]

    # Audit trail: creation, and the risk link, and the underlying risk.created row.
    from app.models.audit_log import AuditLog

    rows = db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(admin["organization_id"])).all()
    actions = [(r.action, r.entity_type) for r in rows]
    print("AUDIT ACTIONS:", actions)
    assert ("dora.ict_entry_created", "dora_ict_register") in actions
    assert ("dora.ict_entry_risk_linked", "dora_ict_register") in actions
    assert ("risk.created", "risk") in actions


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
