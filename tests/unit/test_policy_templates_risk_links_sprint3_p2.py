import uuid

from app.models.audit_log import AuditLog
from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_policy_version import CompliancePolicyVersion
from app.models.policy_template import PolicyTemplate
from app.models.risk import Risk
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user


BASE_TEMPLATES = "/api/v1/compliance/policy-templates"


def _create_policy(client, headers: dict[str, str], owner_user_id: str, title: str) -> dict:
    response = client.post(
        "/api/v1/compliance/policies",
        headers=headers,
        json={
            "title": title,
            "description": "Policy text",
            "policy_type": "access_control",
            "status": "draft",
            "owner_user_id": owner_user_id,
            "version": "1.0",
            "content_url": "https://example.com/policy.txt",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_risk(db_session, org_id: str, title: str) -> Risk:
    row = Risk(
        organization_id=uuid.UUID(org_id),
        title=title,
        description="Risk desc",
        category="other",
        severity="medium",
        likelihood=3,
        impact=3,
        inherent_score=9,
        status="identified",
        treatment_strategy="mitigate",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_s3_p2_templates_seed_list_custom_apply_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s3p2-templates-a")
    other_org = bootstrap_org_user(client, email_prefix="s3p2-templates-b")

    # (a) + (l): seeded system templates are present and idempotent at exactly 15
    SeedService.ensure_policy_templates(db_session)
    SeedService.ensure_policy_templates(db_session)
    db_session.commit()
    system_count = (
        db_session.query(PolicyTemplate)
        .filter(PolicyTemplate.is_system.is_(True), PolicyTemplate.organization_id.is_(None))
        .count()
    )
    assert system_count == 15

    listed = client.get(BASE_TEMPLATES, headers=org["org_headers"])
    assert listed.status_code == 200
    templates = listed.json()
    system_templates = [t for t in templates if t["is_system"] is True]
    assert len(system_templates) == 15

    # (b): org-custom template appears only for creator org
    created_custom = client.post(
        BASE_TEMPLATES,
        headers=org["org_headers"],
        json={
            "title": "Org A Custom Access Policy",
            "description": "Org-specific template",
            "policy_type": "access_control",
            "content": "This is a custom template content body for Org A.",
        },
    )
    assert created_custom.status_code == 201
    custom_id = created_custom.json()["id"]

    listed_org = client.get(BASE_TEMPLATES, headers=org["org_headers"])
    assert listed_org.status_code == 200
    assert any(t["id"] == custom_id for t in listed_org.json())

    listed_other = client.get(BASE_TEMPLATES, headers=other_org["org_headers"])
    assert listed_other.status_code == 200
    assert all(t["id"] != custom_id for t in listed_other.json())

    # (c): applying system template creates draft policy with copied content
    system_id = system_templates[0]["id"]
    apply_system = client.post(
        f"{BASE_TEMPLATES}/{system_id}/apply",
        headers=org["org_headers"],
        json={},
    )
    assert apply_system.status_code == 200
    created_policy_id = apply_system.json()["policy_id"]
    policy_row = db_session.query(CompliancePolicy).filter(CompliancePolicy.id == uuid.UUID(created_policy_id)).one()
    template_row = db_session.query(PolicyTemplate).filter(PolicyTemplate.id == uuid.UUID(system_id)).one()
    assert policy_row.status == "draft"
    assert policy_row.notes == "Created from policy template"
    applied_version = (
        db_session.query(CompliancePolicyVersion)
        .filter(CompliancePolicyVersion.policy_id == uuid.UUID(created_policy_id))
        .one()
    )
    assert applied_version.content_snapshot_json["source"] == "policy_template"
    assert applied_version.content_snapshot_json["content"] == template_row.content

    # (d): applying org-custom template works and writes audit
    apply_custom = client.post(
        f"{BASE_TEMPLATES}/{custom_id}/apply",
        headers=org["org_headers"],
        json={"override_title": "Custom Template Applied"},
    )
    assert apply_custom.status_code == 200
    applied_custom_policy = db_session.query(CompliancePolicy).filter(
        CompliancePolicy.id == uuid.UUID(apply_custom.json()["policy_id"])
    ).one()
    assert applied_custom_policy.status == "draft"
    assert applied_custom_policy.title == "Custom Template Applied"

    # (e): applying another org's custom template blocked
    forbidden_apply = client.post(
        f"{BASE_TEMPLATES}/{custom_id}/apply",
        headers=other_org["org_headers"],
        json={},
    )
    assert forbidden_apply.status_code == 404

    actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    }
    # (k) audit for template created + applied
    assert "policy_template.created" in actions
    assert "policy_template.applied" in actions


def test_s3_p2_policy_risk_links_endpoints(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s3p2-links-a")
    other_org = bootstrap_org_user(client, email_prefix="s3p2-links-b")

    policy = _create_policy(client, org["org_headers"], org["user_id"], "Risk Link Policy")
    risk = _create_risk(db_session, org["organization_id"], "Shared Risk")
    risk_2 = _create_risk(db_session, org["organization_id"], "Second Risk")
    other_risk = _create_risk(db_session, other_org["organization_id"], "Other Org Risk")

    # (f): link risk to policy and list by policy
    linked = client.post(
        f"/api/v1/compliance/policies/{policy['id']}/risks",
        headers=org["org_headers"],
        json={"risk_id": str(risk.id), "link_reason": "Mitigates via policy controls"},
    )
    assert linked.status_code == 201

    linked_list = client.get(f"/api/v1/compliance/policies/{policy['id']}/risks", headers=org["org_headers"])
    assert linked_list.status_code == 200
    assert any(row["id"] == str(risk.id) for row in linked_list.json())

    # (g): duplicate link returns 409
    dup = client.post(
        f"/api/v1/compliance/policies/{policy['id']}/risks",
        headers=org["org_headers"],
        json={"risk_id": str(risk.id)},
    )
    assert dup.status_code == 409

    # link second risk and verify reverse listing (i)
    linked_second = client.post(
        f"/api/v1/compliance/policies/{policy['id']}/risks",
        headers=org["org_headers"],
        json={"risk_id": str(risk_2.id)},
    )
    assert linked_second.status_code == 201

    reverse = client.get(f"/api/v1/compliance/risks/{risk_2.id}/policies", headers=org["org_headers"])
    assert reverse.status_code == 200
    assert any(row["id"] == policy["id"] for row in reverse.json())

    # (h): unlink and verify removed from list
    unlinked = client.delete(
        f"/api/v1/compliance/policies/{policy['id']}/risks/{risk.id}",
        headers=org["org_headers"],
    )
    assert unlinked.status_code == 204
    linked_list_after = client.get(f"/api/v1/compliance/policies/{policy['id']}/risks", headers=org["org_headers"])
    assert linked_list_after.status_code == 200
    assert all(row["id"] != str(risk.id) for row in linked_list_after.json())

    # (j): cross-org get template blocked + cross-org risk linking blocked
    # template check handled in template test; here validate cross-org risk link path
    cross_org_link = client.post(
        f"/api/v1/compliance/policies/{policy['id']}/risks",
        headers=org["org_headers"],
        json={"risk_id": str(other_risk.id)},
    )
    assert cross_org_link.status_code == 404

    actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    }
    # (k) audit for risk linked + unlinked
    assert "policy.risk_linked" in actions
    assert "policy.risk_unlinked" in actions


def test_s3_p2_cross_org_template_get_404(client):
    org_a = bootstrap_org_user(client, email_prefix="s3p2-template-get-a")
    org_b = bootstrap_org_user(client, email_prefix="s3p2-template-get-b")

    created_custom = client.post(
        BASE_TEMPLATES,
        headers=org_a["org_headers"],
        json={
            "title": "Org A Private Template",
            "description": "Org-specific",
            "policy_type": "data_privacy",
            "content": "Org A custom policy template content",
        },
    )
    assert created_custom.status_code == 201

    forbidden = client.get(f"{BASE_TEMPLATES}/{created_custom.json()['id']}", headers=org_b["org_headers"])
    assert forbidden.status_code == 404
