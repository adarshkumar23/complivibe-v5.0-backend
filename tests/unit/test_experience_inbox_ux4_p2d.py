from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.audit_engagement import AuditEngagement
from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_policy_approval_request import CompliancePolicyApprovalRequest
from app.models.compliance_policy_version import CompliancePolicyVersion
from app.models.control import Control
from app.models.control_exception import ControlException
from app.models.control_exception_approval import ControlExceptionApproval
from app.models.pbc_item import PbcItem
from app.models.policy_attestation_campaign import PolicyAttestationCampaign
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user


def _seed_inbox_records(db_session, org_id: uuid.UUID, user_id: uuid.UUID, prefix: str) -> None:
    now = datetime.now(UTC)

    overdue_task = Task(
        organization_id=org_id,
        title=f"{prefix} Overdue Task",
        status="open",
        priority="high",
        task_type="general",
        owner_user_id=user_id,
        created_by_user_id=user_id,
        due_date=now - timedelta(days=2),
        source="manual",
        reminder_status="none",
    )
    db_session.add(overdue_task)

    policy = CompliancePolicy(
        organization_id=org_id,
        title=f"{prefix} Security Policy",
        policy_type="security",
        status="active",
        owner_user_id=user_id,
        version="1.0",
    )
    db_session.add(policy)
    db_session.flush()

    policy_version = CompliancePolicyVersion(
        organization_id=org_id,
        policy_id=policy.id,
        version_number="1.0",
        content_snapshot_json={"title": policy.title},
        status="submitted",
        content_sha256="a" * 64,
        submitted_by_user_id=user_id,
    )
    db_session.add(policy_version)
    db_session.flush()

    approval_request = CompliancePolicyApprovalRequest(
        organization_id=org_id,
        policy_id=policy.id,
        version_id=policy_version.id,
        requested_by_user_id=user_id,
        approver_user_id=user_id,
        status="pending",
    )
    db_session.add(approval_request)

    campaign = PolicyAttestationCampaign(
        organization_id=org_id,
        policy_id=policy.id,
        policy_version_id=policy_version.id,
        policy_version="1.0",
        name=f"{prefix} Attestation Campaign",
        title=f"{prefix} Attestation Campaign",
        due_date=date.today() + timedelta(days=1),
        status="active",
        created_by=user_id,
    )
    db_session.add(campaign)
    db_session.flush()

    attestation = PolicyAttestationRecord(
        organization_id=org_id,
        campaign_id=campaign.id,
        user_id=user_id,
        status="pending",
    )
    db_session.add(attestation)

    engagement = AuditEngagement(
        organization_id=org_id,
        title=f"{prefix} External Audit",
        audit_type="external_certification",
        scope_framework_ids=[],
        assigned_auditor_ids=[],
        status="planning",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=30),
        created_by=user_id,
    )
    db_session.add(engagement)
    db_session.flush()

    pbc_item = PbcItem(
        organization_id=org_id,
        audit_engagement_id=engagement.id,
        title=f"{prefix} Upload evidence package",
        requester_id=user_id,
        assignee_id=user_id,
        status="pending",
        due_date=date.today() + timedelta(days=2),
    )
    db_session.add(pbc_item)

    control = Control(
        organization_id=org_id,
        title=f"{prefix} Access Control",
        created_by_user_id=user_id,
    )
    db_session.add(control)
    db_session.flush()

    control_exception = ControlException(
        organization_id=org_id,
        control_id=control.id,
        title=f"{prefix} Temporary Exception",
        description="Exception requires approval",
        exception_type="temporary",
        risk_acceptance_reason="Operational need",
        requested_by_user_id=user_id,
        owner_user_id=user_id,
        status="pending_approval",
        effective_date=date.today(),
        expiry_date=date.today() + timedelta(days=15),
    )
    db_session.add(control_exception)
    db_session.flush()

    control_approval = ControlExceptionApproval(
        organization_id=org_id,
        exception_id=control_exception.id,
        approver_user_id=user_id,
        status="pending",
        sequence=1,
    )
    db_session.add(control_approval)
    db_session.commit()


def test_ux4_compliance_inbox_aggregates_modules(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="ux4-main")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    _seed_inbox_records(db_session, org_id, user_id, "OrgA")

    resp = client.get("/api/v1/inbox", headers=ctx["org_headers"])
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["total_items"] >= 5

    item_types = {row["item_type"] for row in payload["items"]}
    assert "overdue_task" in item_types
    assert "attestation_pending" in item_types
    assert "evidence_request" in item_types
    assert "approval_request" in item_types


def test_ux4_compliance_inbox_isolation_and_adversarial_limit(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="ux4-org-a")
    org_b = bootstrap_org_user(client, email_prefix="ux4-org-b")

    _seed_inbox_records(
        db_session,
        uuid.UUID(org_a["organization_id"]),
        uuid.UUID(org_a["user_id"]),
        "OrgA",
    )
    _seed_inbox_records(
        db_session,
        uuid.UUID(org_b["organization_id"]),
        uuid.UUID(org_b["user_id"]),
        "OrgB",
    )

    inbox_a = client.get("/api/v1/inbox", headers=org_a["org_headers"])
    assert inbox_a.status_code == 200, inbox_a.text
    titles_a = [item["title"] for item in inbox_a.json()["items"]]
    assert any("OrgA" in title for title in titles_a)
    assert all("OrgB" not in title for title in titles_a)

    invalid = client.get("/api/v1/inbox?limit=0", headers=org_a["org_headers"])
    assert invalid.status_code == 422
