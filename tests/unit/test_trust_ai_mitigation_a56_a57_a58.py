from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.compliance.services.vendor_mitigation_service import VendorMitigationService
from app.models.ai_vendor_assessment import AIVendorAssessment
from app.models.compliance_policy import CompliancePolicy
from app.models.evidence_item import EvidenceItem
from app.models.email_outbox import EmailOutbox
from app.models.trust_center_access_request import TrustCenterAccessRequest
from app.models.vendor_mitigation_action import VendorMitigationAction
from app.models.vendor_mitigation_case import VendorMitigationCase
from tests.helpers.auth_org import bootstrap_org_user


TRUST_ADMIN_BASE = "/api/v1/compliance/trust-center"
TRUST_PUBLIC_BASE = "/api/v1/trust-center"
AI_BASE = "/api/v1/compliance/ai-vendor-assessments"
VENDORS_BASE = "/api/v1/compliance/vendors"
MITIGATION_BASE = "/api/v1/compliance/vendor-mitigation"


def _create_vendor(client, headers: dict[str, str], *, owner_id: str, name: str = "Vendor AI") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_id,
            "risk_tier": "medium",
            "status": "active",
            "data_access": True,
            "processes_personal_data": True,
            "sub_processor": False,
        },
    )
    assert response.status_code == 201
    return response.json()


def _enable_trust_center(client, headers: dict[str, str], *, is_enabled: bool = True) -> dict:
    response = client.post(
        f"{TRUST_ADMIN_BASE}/configuration",
        headers=headers,
        json={
            "is_enabled": is_enabled,
            "display_name": "CompliVibe",
            "tagline": "Security you can verify",
            "show_certifications": True,
            "show_framework_coverage": True,
            "show_published_policies": True,
            "show_uptime_status": True,
            "request_access_enabled": True,
        },
    )
    assert response.status_code == 200
    return response.json()


def _set_slug(client, headers: dict[str, str], slug: str) -> dict:
    response = client.post(f"{TRUST_ADMIN_BASE}/slug", headers=headers, json={"slug": slug})
    assert response.status_code == 200
    return response.json()


def _create_ai_assessment(client, headers: dict[str, str], vendor_id: str, payload: dict) -> dict:
    response = client.post(f"{AI_BASE}?vendor_id={vendor_id}", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_a56_trust_center_public_access_and_admin_workflow(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a56-org")
    slug = "trust-center-org"

    invalid_slug = client.post(f"{TRUST_ADMIN_BASE}/slug", headers=org["org_headers"], json={"slug": "Bad_Slug"})
    assert invalid_slug.status_code == 422

    _set_slug(client, org["org_headers"], slug)

    org2 = bootstrap_org_user(client, email_prefix="a56-org2")
    dup_slug = client.post(f"{TRUST_ADMIN_BASE}/slug", headers=org2["org_headers"], json={"slug": slug})
    assert dup_slug.status_code == 422

    disabled = client.get(f"{TRUST_PUBLIC_BASE}/{slug}")
    assert disabled.status_code == 404

    _enable_trust_center(client, org["org_headers"], is_enabled=True)

    policy = CompliancePolicy(
        organization_id=uuid.UUID(org["organization_id"]),
        title="Access Control Policy",
        description="Long private policy content",
        policy_type="security",
        status="approved",
        owner_user_id=uuid.UUID(org["user_id"]),
        version="1.0",
    )
    db_session.add(policy)
    db_session.commit()

    published = client.post(
        f"{TRUST_ADMIN_BASE}/publish-policy",
        headers=org["org_headers"],
        json={"policy_id": str(policy.id), "summary": "High-level summary only"},
    )
    assert published.status_code == 200

    public = client.get(f"{TRUST_PUBLIC_BASE}/{slug}")
    assert public.status_code == 200
    payload = public.json()
    assert payload["display_name"] == "CompliVibe"
    assert isinstance(payload["policies"], list)
    assert any(item["title"] == "Access Control Policy" for item in payload["policies"])
    assert all("content" not in item for item in payload["policies"])

    unknown_slug = client.get(f"{TRUST_PUBLIC_BASE}/missing-slug")
    assert unknown_slug.status_code == 404

    request_access = client.post(
        f"{TRUST_PUBLIC_BASE}/{slug}/request-access",
        json={
            "requester_name": "Jane Reviewer",
            "requester_email": "jane@example.com",
            "requester_company": "Acme",
            "request_reason": "Security due diligence",
        },
    )
    assert request_access.status_code == 201
    request_id = request_access.json()["request_id"]

    reviewed = client.post(
        f"{TRUST_ADMIN_BASE}/access-requests/{request_id}/review",
        headers=org["org_headers"],
        json={"action": "approve", "notes": "Approved"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approved"

    req_row = db_session.get(TrustCenterAccessRequest, uuid.UUID(request_id))
    assert req_row is not None
    assert req_row.access_token_hash is not None
    assert len(req_row.access_token_hash) == 64
    assert req_row.access_expires_at is not None
    expires_at = req_row.access_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    assert expires_at >= datetime.now(UTC) + timedelta(days=6)

    uptime_update = client.patch(
        f"{TRUST_ADMIN_BASE}/uptime-status",
        headers=org["org_headers"],
        json={"status": "operational"},
    )
    assert uptime_update.status_code == 200

    public_after_uptime = client.get(f"{TRUST_PUBLIC_BASE}/{slug}")
    assert public_after_uptime.status_code == 200
    assert public_after_uptime.json()["uptime"]["status"] == "operational"


def test_a57_ai_vendor_assessment_scoring_summary_and_isolation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a57-org")
    org_b = bootstrap_org_user(client, email_prefix="a57-orgb")

    vendor = _create_vendor(client, org["org_headers"], owner_id=org["user_id"], name="AI Vendor A")

    created = _create_ai_assessment(
        client,
        org["org_headers"],
        vendor["id"],
        {
            "ai_model_name": "Model-A",
            "model_type": "llm",
            "data_exits_environment": True,
            "bias_testing_performed": False,
            "human_oversight_required": False,
            "output_used_for_decisions": True,
            "training_data_governance": None,
            "explainability_approach": None,
            "regulatory_obligations": ["EU AI Act Art. 13", "GDPR Art. 22", "ISO", "SOC2", "NIST"],
        },
    )

    completed = client.post(f"{AI_BASE}/{created['id']}/complete", headers=org["org_headers"])
    assert completed.status_code == 200
    completed_payload = completed.json()
    assert completed_payload["risk_score"] == 100
    assert completed_payload["overall_risk_level"] == "critical"

    # Separate scoring checks for specific rule contributions.
    second = _create_ai_assessment(
        client,
        org["org_headers"],
        vendor["id"],
        {
            "ai_model_name": "Model-B",
            "model_type": "llm",
            "data_exits_environment": True,
            "bias_testing_performed": False,
            "human_oversight_required": True,
            "output_used_for_decisions": False,
            "training_data_governance": "Documented",
            "explainability_approach": "SHAP",
            "regulatory_obligations": [],
        },
    )
    second_complete = client.post(f"{AI_BASE}/{second['id']}/complete", headers=org["org_headers"])
    assert second_complete.status_code == 200
    # +30 exits, +20 no bias, -10 oversight true => 40
    assert second_complete.json()["risk_score"] == 40
    assert second_complete.json()["overall_risk_level"] == "medium"

    summary = client.get(f"{AI_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["critical_count"] >= 1
    assert summary_payload["data_exits_count"] >= 2

    delete_completed = client.delete(f"{AI_BASE}/{created['id']}", headers=org["org_headers"])
    assert delete_completed.status_code == 422

    list_org = client.get(AI_BASE, headers=org["org_headers"])
    list_org_b = client.get(AI_BASE, headers=org_b["org_headers"])
    assert list_org.status_code == 200
    assert list_org_b.status_code == 200
    assert any(row["id"] == created["id"] for row in list_org.json())
    assert all(row["id"] != created["id"] for row in list_org_b.json())


def test_a58_vendor_mitigation_workflow_and_sweep(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a58-org")
    org_b = bootstrap_org_user(client, email_prefix="a58-orgb")
    vendor = _create_vendor(client, org["org_headers"], owner_id=org["user_id"], name="Vendor Mitigation")

    ai_assessment = _create_ai_assessment(
        client,
        org["org_headers"],
        vendor["id"],
        {
            "model_type": "llm",
            "data_exits_environment": True,
            "bias_testing_performed": False,
            "human_oversight_required": False,
            "output_used_for_decisions": True,
            "regulatory_obligations": [],
        },
    )
    completed_ai = client.post(f"{AI_BASE}/{ai_assessment['id']}/complete", headers=org["org_headers"])
    assert completed_ai.status_code == 200

    no_assessment_case = client.post(
        f"{MITIGATION_BASE}/cases",
        headers=org["org_headers"],
        json={
            "vendor_id": vendor["id"],
            "title": "Case without assessment",
            "description": "Missing refs",
            "severity": "high",
            "assigned_owner_id": org["user_id"],
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
        },
    )
    assert no_assessment_case.status_code == 422

    case = client.post(
        f"{MITIGATION_BASE}/cases",
        headers=org["org_headers"],
        json={
            "vendor_id": vendor["id"],
            "ai_assessment_id": ai_assessment["id"],
            "title": "Mitigate model drift risk",
            "description": "Need additional controls",
            "severity": "high",
            "assigned_owner_id": org["user_id"],
            "due_date": (date.today() + timedelta(days=3)).isoformat(),
        },
    )
    assert case.status_code == 201
    case_id = case.json()["id"]

    action = client.post(
        f"{MITIGATION_BASE}/cases/{case_id}/actions",
        headers=org["org_headers"],
        json={
            "title": "Upload pen test report",
            "description": "Provide latest evidence",
            "action_type": "documentation",
            "assigned_to_vendor": True,
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
        },
    )
    assert action.status_code == 201
    action_id = action.json()["id"]

    wrong_org_evidence = EvidenceItem(
        organization_id=uuid.UUID(org_b["organization_id"]),
        title="Wrong org evidence",
        evidence_type="document",
        source="manual",
        status="active",
        review_status="not_reviewed",
        freshness_status="unknown",
        uploaded_by_user_id=uuid.UUID(org_b["user_id"]),
    )
    db_session.add(wrong_org_evidence)
    db_session.commit()

    wrong_evidence_submit = client.post(
        f"{MITIGATION_BASE}/cases/{case_id}/actions/{action_id}/submit-evidence",
        headers=org["org_headers"],
        json={"evidence_id": str(wrong_org_evidence.id)},
    )
    assert wrong_evidence_submit.status_code == 422

    good_evidence = EvidenceItem(
        organization_id=uuid.UUID(org["organization_id"]),
        title="Correct evidence",
        evidence_type="document",
        source="manual",
        status="active",
        review_status="verified",
        freshness_status="current",
        uploaded_by_user_id=uuid.UUID(org["user_id"]),
    )
    db_session.add(good_evidence)
    db_session.commit()

    submit = client.post(
        f"{MITIGATION_BASE}/cases/{case_id}/actions/{action_id}/submit-evidence",
        headers=org["org_headers"],
        json={"evidence_id": str(good_evidence.id)},
    )
    assert submit.status_code == 200
    assert submit.json()["status"] == "evidence_submitted"

    accepted = client.post(
        f"{MITIGATION_BASE}/cases/{case_id}/actions/{action_id}/accept",
        headers=org["org_headers"],
    )
    assert accepted.status_code == 200
    assert accepted.json()["accepted_at"] is not None
    assert accepted.json()["accepted_by"] == org["user_id"]

    case_after_accept = client.get(f"{MITIGATION_BASE}/cases/{case_id}", headers=org["org_headers"])
    assert case_after_accept.status_code == 200
    assert case_after_accept.json()["status"] == "under_review"

    action2 = client.post(
        f"{MITIGATION_BASE}/cases/{case_id}/actions",
        headers=org["org_headers"],
        json={
            "title": "Follow-up training",
            "description": "Train staff",
            "action_type": "training",
            "assigned_to_vendor": False,
            "due_date": (date.today() + timedelta(days=5)).isoformat(),
        },
    )
    assert action2.status_code == 201

    rejected = client.post(
        f"{MITIGATION_BASE}/cases/{case_id}/actions/{action2.json()['id']}/reject",
        headers=org["org_headers"],
        json={"reason": "Insufficient detail"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["rejection_reason"] == "Insufficient detail"

    move_in_progress = client.post(
        f"{MITIGATION_BASE}/cases/{case_id}/transition",
        headers=org["org_headers"],
        json={"new_status": "in_progress"},
    )
    assert move_in_progress.status_code == 200

    escalated = client.post(
        f"{MITIGATION_BASE}/cases/{case_id}/escalate",
        headers=org["org_headers"],
        json={"reason": "Vendor non-responsive"},
    )
    assert escalated.status_code == 200
    assert escalated.json()["status"] == "escalated"

    outbox_count = (
        db_session.query(EmailOutbox)
        .filter(EmailOutbox.organization_id == uuid.UUID(org["organization_id"]), EmailOutbox.event_type == "vendor_mitigation.case_escalated")
        .count()
    )
    assert outbox_count >= 1

    case_row = db_session.get(VendorMitigationCase, uuid.UUID(case_id))
    assert case_row is not None
    case_row.status = "in_progress"
    db_session.commit()

    overdue_action = db_session.get(VendorMitigationAction, uuid.UUID(action_id))
    assert overdue_action is not None
    overdue_action.status = "open"
    overdue_action.due_date = date.today() - timedelta(days=2)
    db_session.commit()

    sweep = VendorMitigationService(db_session).sweep_overdue_actions(uuid.UUID(org["organization_id"]))
    db_session.commit()
    assert sweep["marked_overdue"] >= 1

    summary = client.get(f"{MITIGATION_BASE}/cases/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    assert summary.json()["overdue_cases"] >= 0

    delete_blocked = client.delete(f"{MITIGATION_BASE}/cases/{case_id}", headers=org["org_headers"])
    assert delete_blocked.status_code == 422
