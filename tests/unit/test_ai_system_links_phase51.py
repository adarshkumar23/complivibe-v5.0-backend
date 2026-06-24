import uuid

from app.models.ai_system_control_link import AISystemControlLink
from app.models.ai_system_evidence_link import AISystemEvidenceLink
from app.models.ai_system_risk_link import AISystemRiskLink
from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], name: str = "AI Links System") -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={
            "name": name,
            "system_type": "agent",
            "lifecycle_status": "proposed",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_control(client, headers: dict[str, str], title: str = "AI Control") -> dict:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={
            "title": title,
            "control_type": "ai_governance",
            "criticality": "high",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_evidence(client, headers: dict[str, str], title: str = "AI Evidence") -> dict:
    response = client.post(
        "/api/v1/evidence",
        headers=headers,
        json={
            "title": title,
            "evidence_type": "document",
            "source": "manual",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_risk(client, headers: dict[str, str], title: str = "AI Risk") -> dict:
    response = client.post(
        "/api/v1/risks",
        headers=headers,
        json={
            "title": title,
            "likelihood": 4,
            "impact": 4,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_ai_system_manual_link_create_and_duplicate_blocks(client):
    owner = bootstrap_org_user(client, email_prefix="p51-link-owner")
    headers = owner["org_headers"]
    ai_system = _create_ai_system(client, headers)
    control = _create_control(client, headers)
    evidence = _create_evidence(client, headers)
    risk = _create_risk(client, headers)

    control_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls",
        headers=headers,
        json={"control_id": control["id"], "link_reason": "Manual mapping"},
    )
    assert control_link.status_code == 201
    assert control_link.json()["status"] == "active"

    evidence_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/evidence",
        headers=headers,
        json={"evidence_id": evidence["id"], "link_reason": "Supports control"},
    )
    assert evidence_link.status_code == 201
    assert evidence_link.json()["status"] == "active"

    risk_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/risks",
        headers=headers,
        json={"risk_id": risk["id"], "link_reason": "Impacted by model behavior"},
    )
    assert risk_link.status_code == 201
    assert risk_link.json()["status"] == "active"

    dup_control = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls",
        headers=headers,
        json={"control_id": control["id"]},
    )
    assert dup_control.status_code == 400

    dup_evidence = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/evidence",
        headers=headers,
        json={"evidence_id": evidence["id"]},
    )
    assert dup_evidence.status_code == 400

    dup_risk = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/risks",
        headers=headers,
        json={"risk_id": risk["id"]},
    )
    assert dup_risk.status_code == 400


def test_ai_system_link_tenant_scoped_and_archived_block(client):
    org1 = bootstrap_org_user(client, email_prefix="p51-link-org1")
    org2 = bootstrap_org_user(client, email_prefix="p51-link-org2")
    ai_system = _create_ai_system(client, org1["org_headers"], name="Org1 AI")
    control_org2 = _create_control(client, org2["org_headers"], title="Org2 Control")

    cross_tenant = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls",
        headers=org1["org_headers"],
        json={"control_id": control_org2["id"]},
    )
    assert cross_tenant.status_code == 404

    archive = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/archive",
        headers=org1["org_headers"],
        json={"reason": "No longer used"},
    )
    assert archive.status_code == 200

    own_control = _create_control(client, org1["org_headers"], title="Org1 Control")
    archived_block = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls",
        headers=org1["org_headers"],
        json={"control_id": own_control["id"]},
    )
    assert archived_block.status_code == 400


def test_ai_system_unlink_requires_reason_and_is_non_destructive(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p51-unlink-owner")
    headers = owner["org_headers"]
    org_id = uuid.UUID(owner["organization_id"])
    ai_system = _create_ai_system(client, headers)
    control = _create_control(client, headers)

    linked = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls",
        headers=headers,
        json={"control_id": control["id"]},
    )
    assert linked.status_code == 201
    link_id = linked.json()["id"]

    missing_reason = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls/{link_id}/unlink",
        headers=headers,
        json={},
    )
    assert missing_reason.status_code == 422

    unlinked = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls/{link_id}/unlink",
        headers=headers,
        json={"unlink_reason": "No longer relevant"},
    )
    assert unlinked.status_code == 200
    assert unlinked.json()["status"] == "unlinked"
    assert unlinked.json()["unlink_reason"] == "No longer relevant"

    list_default = client.get(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls",
        headers=headers,
    )
    assert list_default.status_code == 200
    assert list_default.json() == []

    list_with_unlinked = client.get(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls?include_unlinked=true",
        headers=headers,
    )
    assert list_with_unlinked.status_code == 200
    assert len(list_with_unlinked.json()) == 1
    assert list_with_unlinked.json()[0]["status"] == "unlinked"

    persisted = (
        db_session.query(AISystemControlLink)
        .filter(
            AISystemControlLink.id == uuid.UUID(link_id),
            AISystemControlLink.organization_id == org_id,
        )
        .one_or_none()
    )
    assert persisted is not None
    assert persisted.status == "unlinked"


def test_ai_system_link_summary_counts(client):
    owner = bootstrap_org_user(client, email_prefix="p51-summary-owner")
    headers = owner["org_headers"]
    ai_system = _create_ai_system(client, headers)

    control = _create_control(client, headers, title="Summary Control")
    evidence = _create_evidence(client, headers, title="Summary Evidence")
    risk = _create_risk(client, headers, title="Summary Risk")

    control_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls",
        headers=headers,
        json={"control_id": control["id"]},
    )
    evidence_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/evidence",
        headers=headers,
        json={"evidence_id": evidence["id"]},
    )
    risk_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/risks",
        headers=headers,
        json={"risk_id": risk["id"]},
    )
    assert control_link.status_code == 201
    assert evidence_link.status_code == 201
    assert risk_link.status_code == 201

    unlink_control = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls/{control_link.json()['id']}/unlink",
        headers=headers,
        json={"unlink_reason": "Test unlinked control"},
    )
    assert unlink_control.status_code == 200

    summary = client.get(
        f"/api/v1/ai-systems/{ai_system['id']}/links/summary",
        headers=headers,
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["active_control_links"] == 0
    assert body["active_evidence_links"] == 1
    assert body["active_risk_links"] == 1
    assert body["unlinked_control_links"] == 1
    assert body["unlinked_evidence_links"] == 0
    assert body["unlinked_risk_links"] == 0
    assert body["total_active_links"] == 2
    assert body["total_unlinked_links"] == 1


def test_ai_system_link_audit_logs_written(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p51-audit-owner")
    headers = owner["org_headers"]
    org_id = uuid.UUID(owner["organization_id"])
    ai_system = _create_ai_system(client, headers)
    control = _create_control(client, headers, title="Audit Control")
    evidence = _create_evidence(client, headers, title="Audit Evidence")
    risk = _create_risk(client, headers, title="Audit Risk")

    control_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls",
        headers=headers,
        json={"control_id": control["id"]},
    )
    evidence_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/evidence",
        headers=headers,
        json={"evidence_id": evidence["id"]},
    )
    risk_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/risks",
        headers=headers,
        json={"risk_id": risk["id"]},
    )
    assert control_link.status_code == 201
    assert evidence_link.status_code == 201
    assert risk_link.status_code == 201

    control_unlink = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/controls/{control_link.json()['id']}/unlink",
        headers=headers,
        json={"unlink_reason": "cleanup"},
    )
    evidence_unlink = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/evidence/{evidence_link.json()['id']}/unlink",
        headers=headers,
        json={"unlink_reason": "cleanup"},
    )
    risk_unlink = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/risks/{risk_link.json()['id']}/unlink",
        headers=headers,
        json={"unlink_reason": "cleanup"},
    )
    assert control_unlink.status_code == 200
    assert evidence_unlink.status_code == 200
    assert risk_unlink.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    logged_actions = [item["action"] for item in logs.json() if item["organization_id"] == str(org_id)]
    assert "ai_system.control_linked" in logged_actions
    assert "ai_system.control_unlinked" in logged_actions
    assert "ai_system.evidence_linked" in logged_actions
    assert "ai_system.evidence_unlinked" in logged_actions
    assert "ai_system.risk_linked" in logged_actions
    assert "ai_system.risk_unlinked" in logged_actions


def test_ai_system_evidence_and_risk_unlink_non_destructive(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p51-nondestruct-owner")
    headers = owner["org_headers"]
    org_id = uuid.UUID(owner["organization_id"])
    ai_system = _create_ai_system(client, headers)
    evidence = _create_evidence(client, headers, title="NonDestructive Evidence")
    risk = _create_risk(client, headers, title="NonDestructive Risk")

    evidence_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/evidence",
        headers=headers,
        json={"evidence_id": evidence["id"]},
    )
    risk_link = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/risks",
        headers=headers,
        json={"risk_id": risk["id"]},
    )
    assert evidence_link.status_code == 201
    assert risk_link.status_code == 201

    evidence_unlink = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/evidence/{evidence_link.json()['id']}/unlink",
        headers=headers,
        json={"unlink_reason": "obsolete evidence"},
    )
    risk_unlink = client.post(
        f"/api/v1/ai-systems/{ai_system['id']}/links/risks/{risk_link.json()['id']}/unlink",
        headers=headers,
        json={"unlink_reason": "obsolete risk"},
    )
    assert evidence_unlink.status_code == 200
    assert risk_unlink.status_code == 200

    evidence_row = (
        db_session.query(AISystemEvidenceLink)
        .filter(
            AISystemEvidenceLink.id == uuid.UUID(evidence_link.json()["id"]),
            AISystemEvidenceLink.organization_id == org_id,
        )
        .one_or_none()
    )
    risk_row = (
        db_session.query(AISystemRiskLink)
        .filter(
            AISystemRiskLink.id == uuid.UUID(risk_link.json()["id"]),
            AISystemRiskLink.organization_id == org_id,
        )
        .one_or_none()
    )
    assert evidence_row is not None
    assert evidence_row.status == "unlinked"
    assert risk_row is not None
    assert risk_row.status == "unlinked"
