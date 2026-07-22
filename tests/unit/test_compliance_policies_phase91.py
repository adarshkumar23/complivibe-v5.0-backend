import uuid

from app.core.security import get_password_hash
from app.models.compliance_policy_version import CompliancePolicyVersion
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

BASE = "/api/v1/compliance/policies"


def _create_user_with_role(
    db_session,
    *,
    org_id: str,
    email: str,
    role_name: str,
    membership_status: str = "active",
    user_status: str = "active",
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status=user_status,
        is_active=is_active,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status=membership_status,
    )
    db_session.add(membership)
    db_session.commit()
    return user


def _create_policy(client, headers: dict[str, str], *, owner_user_id: str, title: str = "P91 Policy") -> dict:
    response = client.post(
        BASE,
        headers=headers,
        json={
            "title": title,
            "policy_type": "acceptable_use",
            "owner_user_id": owner_user_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_version(client, headers: dict[str, str], policy_id: str, *, version_number: str, content: dict) -> dict:
    response = client.post(
        f"{BASE}/{policy_id}/versions",
        headers=headers,
        json={
            "version_number": version_number,
            "content_snapshot_json": content,
            "change_summary": f"changes for {version_number}",
        },
    )
    assert response.status_code == 201
    return response.json()


def _submit_version(client, headers: dict[str, str], policy_id: str, version_id: str) -> dict:
    response = client.post(
        f"{BASE}/{policy_id}/versions/{version_id}/submit-for-approval",
        headers=headers,
        json={"notes": "submit"},
    )
    assert response.status_code == 200
    return response.json()


def _create_approval_request(client, headers: dict[str, str], policy_id: str, version_id: str, approver_user_id: str) -> dict:
    response = client.post(
        f"{BASE}/{policy_id}/approval-requests",
        headers=headers,
        json={
            "version_id": version_id,
            "approver_user_id": approver_user_id,
            "notes": "please review",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_phase91_version_snapshot_immutability_and_deterministic_hash(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p91-immut")
    owner = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-immut-owner@example.com",
        role_name="admin",
    )

    policy = _create_policy(client, org["org_headers"], owner_user_id=str(owner.id), title="Immutable Policy")

    content = {"sections": [{"id": "s1", "text": "alpha"}], "meta": {"k": "v"}}
    version1 = _create_version(client, org["org_headers"], policy["id"], version_number="1.0", content=content)
    version2 = _create_version(client, org["org_headers"], policy["id"], version_number="1.1", content=content)

    assert version1["content_sha256"] == version2["content_sha256"]

    detail_before = client.get(f"{BASE}/{policy['id']}/versions/{version1['id']}", headers=org["org_headers"])
    assert detail_before.status_code == 200

    _submit_version(client, org["org_headers"], policy["id"], version1["id"])

    detail_after = client.get(f"{BASE}/{policy['id']}/versions/{version1['id']}", headers=org["org_headers"])
    assert detail_after.status_code == 200
    assert detail_after.json()["content_snapshot_json"] == detail_before.json()["content_snapshot_json"]
    assert detail_after.json()["content_sha256"] == detail_before.json()["content_sha256"]


def test_phase91_four_eyes_enforced(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p91-eyes")
    owner_headers = org["org_headers"]

    owner_user = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-eyes-owner@example.com",
        role_name="owner",
    )

    policy = _create_policy(client, owner_headers, owner_user_id=str(owner_user.id), title="Four Eyes Policy")
    version = _create_version(
        client,
        owner_headers,
        policy["id"],
        version_number="2.0",
        content={"body": "requires review"},
    )
    _submit_version(client, owner_headers, policy["id"], version["id"])

    approval_request = _create_approval_request(
        client,
        owner_headers,
        policy["id"],
        version["id"],
        approver_user_id=org["user_id"],
    )

    self_approve = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{approval_request['id']}/approve",
        headers=owner_headers,
        json={"notes": "self approve"},
    )
    assert self_approve.status_code == 400
    assert "Requester cannot approve their own request" in self_approve.json()["detail"]


def test_phase91_supersession_behavior_and_policy_approved_state(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p91-super")
    requester_headers = org["org_headers"]

    owner_user = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-super-owner@example.com",
        role_name="owner",
    )
    approver_user = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-super-approver@example.com",
        role_name="admin",
    )
    approver_token = login_user(client, approver_user.email)
    approver_headers = org_headers(approver_token, org["organization_id"])

    policy = _create_policy(client, requester_headers, owner_user_id=str(owner_user.id), title="Supersession Policy")

    v1 = _create_version(client, requester_headers, policy["id"], version_number="1.0", content={"rev": 1})
    _submit_version(client, requester_headers, policy["id"], v1["id"])
    req1 = _create_approval_request(
        client,
        requester_headers,
        policy["id"],
        v1["id"],
        approver_user_id=str(approver_user.id),
    )
    approve1 = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{req1['id']}/approve",
        headers=approver_headers,
        json={"notes": "approved v1"},
    )
    assert approve1.status_code == 200

    v2 = _create_version(client, requester_headers, policy["id"], version_number="2.0", content={"rev": 2})
    _submit_version(client, requester_headers, policy["id"], v2["id"])
    req2 = _create_approval_request(
        client,
        requester_headers,
        policy["id"],
        v2["id"],
        approver_user_id=str(approver_user.id),
    )
    approve2 = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{req2['id']}/approve",
        headers=approver_headers,
        json={"notes": "approved v2"},
    )
    assert approve2.status_code == 200

    v1_row = db_session.query(CompliancePolicyVersion).filter(CompliancePolicyVersion.id == uuid.UUID(v1["id"])).one()
    v2_row = db_session.query(CompliancePolicyVersion).filter(CompliancePolicyVersion.id == uuid.UUID(v2["id"])).one()
    assert v1_row.status == "superseded"
    assert v2_row.status == "approved"

    policy_detail = client.get(f"{BASE}/{policy['id']}", headers=requester_headers)
    assert policy_detail.status_code == 200
    assert policy_detail.json()["status"] == "approved"
    assert policy_detail.json()["version"] == "2.0"
    assert policy_detail.json()["approved_at"] is not None


def test_phase91_version_list_flags_live_version_and_stale_active_campaign(client, db_session):
    """Intelligence: the version list must flag which version is currently live/effective, and
    must flag when an active attestation campaign is still referencing a version that has since
    been superseded -- so nobody mistakes a stale campaign for proof of current compliance."""
    org = bootstrap_org_user(client, email_prefix="p91-liveflag")
    requester_headers = org["org_headers"]

    owner_user = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-liveflag-owner@example.com",
        role_name="owner",
    )
    approver_user = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-liveflag-approver@example.com",
        role_name="admin",
    )
    approver_token = login_user(client, approver_user.email)
    approver_headers = org_headers(approver_token, org["organization_id"])

    policy = _create_policy(client, requester_headers, owner_user_id=str(owner_user.id), title="Live Flag Policy")

    v1 = _create_version(client, requester_headers, policy["id"], version_number="1.0", content={"rev": 1})
    _submit_version(client, requester_headers, policy["id"], v1["id"])
    req1 = _create_approval_request(client, requester_headers, policy["id"], v1["id"], approver_user_id=str(approver_user.id))
    approve1 = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{req1['id']}/approve",
        headers=approver_headers,
        json={"notes": "approved v1"},
    )
    assert approve1.status_code == 200

    # Before any second version exists, v1 is the live version and no campaign references it yet.
    versions_before = client.get(f"{BASE}/{policy['id']}/versions", headers=requester_headers)
    assert versions_before.status_code == 200
    v1_before = next(v for v in versions_before.json() if v["id"] == v1["id"])
    assert v1_before["is_live"] is True
    assert v1_before["referenced_by_active_campaign"] is False
    assert v1_before["stale_active_campaign_reference"] is False

    # Launch an attestation campaign explicitly pinned to v1.
    campaign = client.post(
        "/api/v1/compliance/attestation-campaigns",
        headers=requester_headers,
        json={
            "policy_id": policy["id"],
            "title": "Live Flag Campaign",
            "due_date": "2030-01-01",
            "policy_version_id": v1["id"],
        },
    )
    assert campaign.status_code == 201

    # Now supersede v1 with an approved v2.
    v2 = _create_version(client, requester_headers, policy["id"], version_number="2.0", content={"rev": 2})
    _submit_version(client, requester_headers, policy["id"], v2["id"])
    req2 = _create_approval_request(client, requester_headers, policy["id"], v2["id"], approver_user_id=str(approver_user.id))
    approve2 = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{req2['id']}/approve",
        headers=approver_headers,
        json={"notes": "approved v2"},
    )
    assert approve2.status_code == 200

    versions_after = client.get(f"{BASE}/{policy['id']}/versions", headers=requester_headers)
    assert versions_after.status_code == 200
    by_id = {v["id"]: v for v in versions_after.json()}

    assert by_id[v1["id"]]["is_live"] is False
    assert by_id[v1["id"]]["referenced_by_active_campaign"] is True
    assert by_id[v1["id"]]["stale_active_campaign_reference"] is True

    assert by_id[v2["id"]]["is_live"] is True
    assert by_id[v2["id"]]["referenced_by_active_campaign"] is False
    assert by_id[v2["id"]]["stale_active_campaign_reference"] is False

    single = client.get(f"{BASE}/{policy['id']}/versions/{v1['id']}", headers=requester_headers)
    assert single.status_code == 200
    assert single.json()["stale_active_campaign_reference"] is True


def test_phase91_tenant_scoping_for_versions_and_approval_requests(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p91-tenant-a")
    org2 = bootstrap_org_user(client, email_prefix="p91-tenant-b")

    owner1 = _create_user_with_role(
        db_session,
        org_id=org1["organization_id"],
        email="p91-tenant-owner1@example.com",
        role_name="admin",
    )
    owner2 = _create_user_with_role(
        db_session,
        org_id=org2["organization_id"],
        email="p91-tenant-owner2@example.com",
        role_name="admin",
    )

    policy1 = _create_policy(client, org1["org_headers"], owner_user_id=str(owner1.id), title="Org1")
    version1 = _create_version(client, org1["org_headers"], policy1["id"], version_number="1.0", content={"a": 1})
    _submit_version(client, org1["org_headers"], policy1["id"], version1["id"])

    req = _create_approval_request(
        client,
        org1["org_headers"],
        policy1["id"],
        version1["id"],
        approver_user_id=str(owner1.id),
    )

    cross_version = client.get(
        f"{BASE}/{policy1['id']}/versions/{version1['id']}",
        headers=org2["org_headers"],
    )
    assert cross_version.status_code == 404

    cross_requests = client.get(
        f"{BASE}/{policy1['id']}/approval-requests",
        headers=org2["org_headers"],
    )
    assert cross_requests.status_code == 404

    cross_reject = client.post(
        f"{BASE}/{policy1['id']}/approval-requests/{req['id']}/reject",
        headers=org2["org_headers"],
        json={"notes": "cross tenant"},
    )
    assert cross_reject.status_code == 404

    _ = _create_policy(client, org2["org_headers"], owner_user_id=str(owner2.id), title="Org2")


def test_phase91_audit_coverage_and_cancel_requires_reason(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p91-audit")
    requester_headers = org["org_headers"]

    owner_user = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-audit-owner@example.com",
        role_name="owner",
    )
    approver_user = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-audit-approver@example.com",
        role_name="admin",
    )
    approver_token = login_user(client, approver_user.email)
    approver_headers = org_headers(approver_token, org["organization_id"])

    policy = _create_policy(client, requester_headers, owner_user_id=str(owner_user.id), title="Audit Flow")

    v1 = _create_version(client, requester_headers, policy["id"], version_number="1.0", content={"n": 1})
    _submit_version(client, requester_headers, policy["id"], v1["id"])
    req1 = _create_approval_request(client, requester_headers, policy["id"], v1["id"], str(approver_user.id))
    approved = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{req1['id']}/approve",
        headers=approver_headers,
        json={"notes": "approve", "review_notes": "ok"},
    )
    assert approved.status_code == 200

    v2 = _create_version(client, requester_headers, policy["id"], version_number="2.0", content={"n": 2})
    _submit_version(client, requester_headers, policy["id"], v2["id"])
    req2 = _create_approval_request(client, requester_headers, policy["id"], v2["id"], str(approver_user.id))
    rejected = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{req2['id']}/reject",
        headers=approver_headers,
        json={"notes": "reject", "review_notes": "needs changes"},
    )
    assert rejected.status_code == 200

    v3 = _create_version(client, requester_headers, policy["id"], version_number="3.0", content={"n": 3})
    _submit_version(client, requester_headers, policy["id"], v3["id"])
    req3 = _create_approval_request(client, requester_headers, policy["id"], v3["id"], str(approver_user.id))

    cancel_missing_reason = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{req3['id']}/cancel",
        headers=requester_headers,
        json={},
    )
    assert cancel_missing_reason.status_code == 422

    cancelled = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{req3['id']}/cancel",
        headers=requester_headers,
        json={"reason": "no longer needed"},
    )
    assert cancelled.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=requester_headers)
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "compliance_policy_version.created" in actions
    assert "compliance_policy_version.submitted" in actions
    assert "compliance_policy_approval.requested" in actions
    assert "compliance_policy_approval.approved" in actions
    assert "compliance_policy_approval.rejected" in actions
    assert "compliance_policy_approval.cancelled" in actions


def test_g6_assigned_non_owner_approver_can_decide_own_request(client, db_session):
    """Regression test for the G6 bug: approve/reject required the blanket
    compliance_policies:approve permission via require_permission(), which only
    "owner" (and "admin") roles carry. An "auditor" explicitly assigned as
    approver_user_id on a specific request got a bare 403 ("Missing required
    permission: compliance_policies:approve") even though they were the named,
    correct decision-maker for that exact request.

    Being the assigned approver on a request must be sufficient authorization
    for THAT request regardless of the assignee's role's blanket grant. A
    different user who is neither the assignee nor an owner/admin must still
    be rejected.

    Uses "auditor" (not "reviewer") for both users: reviewer was given a real
    compliance_policies:approve grant as part of the G7 fix that made the
    "reviewer" role name actually able to review things, so it no longer
    demonstrates the assignee-specific bypass this test targets. "auditor"
    still legitimately lacks that blanket permission.
    """
    org = bootstrap_org_user(client, email_prefix="p91-g6-assignee")
    owner_headers = org["org_headers"]

    reviewer = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-g6-reviewer@example.com",
        role_name="auditor",
    )
    other_reviewer = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-g6-other-reviewer@example.com",
        role_name="auditor",
    )
    reviewer_token = login_user(client, reviewer.email)
    reviewer_headers = org_headers(reviewer_token, org["organization_id"])
    other_reviewer_token = login_user(client, other_reviewer.email)
    other_reviewer_headers = org_headers(other_reviewer_token, org["organization_id"])

    policy = _create_policy(client, owner_headers, owner_user_id=org["user_id"], title="G6 Assignee Policy")
    version = _create_version(
        client, owner_headers, policy["id"], version_number="2.0", content={"body": "needs reviewer sign-off"}
    )
    _submit_version(client, owner_headers, policy["id"], version["id"])

    approval_request = _create_approval_request(
        client, owner_headers, policy["id"], version["id"], approver_user_id=str(reviewer.id)
    )

    # A different reviewer-role user, not assigned to this request and without
    # the blanket compliance_policies:approve permission, must still be blocked.
    wrong_person = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{approval_request['id']}/approve",
        headers=other_reviewer_headers,
        json={"notes": "not my request"},
    )
    assert wrong_person.status_code == 403

    # The assigned reviewer -- whose ROLE lacks compliance_policies:approve -- can
    # act on THIS request because they are the named approver.
    approved = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{approval_request['id']}/approve",
        headers=reviewer_headers,
        json={"notes": "reviewer sign-off as assignee"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    # Same story for reject: assign a second request to the reviewer and confirm
    # they can reject it, while the wrong person still cannot.
    version2 = _create_version(
        client, owner_headers, policy["id"], version_number="3.0", content={"body": "needs rejection"}
    )
    _submit_version(client, owner_headers, policy["id"], version2["id"])
    approval_request2 = _create_approval_request(
        client, owner_headers, policy["id"], version2["id"], approver_user_id=str(reviewer.id)
    )

    wrong_person_reject = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{approval_request2['id']}/reject",
        headers=other_reviewer_headers,
        json={"notes": "not my request"},
    )
    assert wrong_person_reject.status_code == 403

    rejected = client.post(
        f"{BASE}/{policy['id']}/approval-requests/{approval_request2['id']}/reject",
        headers=reviewer_headers,
        json={"notes": "reviewer rejecting as assignee"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"


def test_g6_version_diff_endpoint_real_line_and_field_diff(client, db_session):
    """G6 item 6: there was no way to diff two policy versions -- a client had
    to fetch both raw content_snapshot_json blobs and diff them itself. This
    exercises the new GET .../versions/{a}/diff/{b} endpoint end to end and
    asserts it returns a REAL diff (unified diff text, structured line hunks,
    and a field-level diff of non-text metadata), not just both snapshots.
    """
    org = bootstrap_org_user(client, email_prefix="p91-g6-diff")
    headers = org["org_headers"]

    policy = _create_policy(client, headers, owner_user_id=org["user_id"], title="Diff Policy")
    v1 = _create_version(
        client,
        headers,
        policy["id"],
        version_number="1.0",
        content={
            "content": "Line one.\nLine two.\nLine three unchanged.\nOld line four.\n",
            "source": "manual",
        },
    )
    v2 = _create_version(
        client,
        headers,
        policy["id"],
        version_number="2.0",
        content={
            "content": "Line one.\nLine two updated.\nLine three unchanged.\nNew line four.\nBrand new line five.\n",
            "source": "manual_revision",
        },
    )

    diff = client.get(f"{BASE}/{policy['id']}/versions/{v1['id']}/diff/{v2['id']}", headers=headers)
    assert diff.status_code == 200, diff.text
    body = diff.json()

    assert body["older"]["version_number"] == "1.0"
    assert body["newer"]["version_number"] == "2.0"
    assert body["identical"] is False
    assert body["word_count_delta"] > 0
    assert body["line_count_delta"] == 1

    # Real unified-diff text, not raw snapshots.
    assert "-Line two.\n" in body["unified_diff"] or "-Line two." in body["unified_diff"]
    assert "+Line two updated." in body["unified_diff"]

    # Structured hunks: line 1 and 3 unchanged, line 2 replaced, line 4 replaced
    # with two new lines.
    ops = [hunk["op"] for hunk in body["line_hunks"]]
    assert "equal" in ops
    assert "replace" in ops
    replace_hunks = [h for h in body["line_hunks"] if h["op"] == "replace"]
    assert any(h["older_lines"] == ["Line two."] and h["newer_lines"] == ["Line two updated."] for h in replace_hunks)
    assert any(
        h["older_lines"] == ["Old line four."] and h["newer_lines"] == ["New line four.", "Brand new line five."]
        for h in replace_hunks
    )

    # Field-level diff of non-text metadata (source changed), content itself is
    # NOT duplicated here since it's already covered by unified_diff/line_hunks.
    field_diffs = {d["field"]: d for d in body["json_field_diffs"]}
    assert "content" not in field_diffs
    assert field_diffs["source"]["change"] == "changed"
    assert field_diffs["source"]["older_value"] == "manual"
    assert field_diffs["source"]["newer_value"] == "manual_revision"

    # Order-independence: requesting the newer version first still labels
    # older/newer correctly by created_at, not URL order.
    reversed_diff = client.get(f"{BASE}/{policy['id']}/versions/{v2['id']}/diff/{v1['id']}", headers=headers)
    assert reversed_diff.status_code == 200
    assert reversed_diff.json()["older"]["version_number"] == "1.0"
    assert reversed_diff.json()["newer"]["version_number"] == "2.0"

    # Diffing a version against itself is rejected.
    same_version = client.get(f"{BASE}/{policy['id']}/versions/{v1['id']}/diff/{v1['id']}", headers=headers)
    assert same_version.status_code == 400

    # Identical content across two versions is reported as identical=True with
    # an empty unified diff.
    v3 = _create_version(
        client,
        headers,
        policy["id"],
        version_number="3.0",
        content={"content": v2["content_snapshot_json"]["content"], "source": "manual_revision"},
    )
    identical_diff = client.get(f"{BASE}/{policy['id']}/versions/{v2['id']}/diff/{v3['id']}", headers=headers)
    assert identical_diff.status_code == 200
    assert identical_diff.json()["identical"] is True
    assert identical_diff.json()["unified_diff"] == ""

    # Nonexistent version -> 404, not a silent empty diff.
    missing = client.get(f"{BASE}/{policy['id']}/versions/{v1['id']}/diff/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404


def test_phase91_patch_status_self_approval_blocked(client, db_session):
    """Four-eyes on the PATCH-status approval shortcut: the policy owner must not be
    able to approve their own policy by driving draft -> under_review -> approved via
    PATCH, even though they hold compliance_policies:approve. This mirrors the guard
    the formal approval-requests flow already enforces (Requester cannot approve their
    own request) and the control-exception 0316 fix (Requester cannot approve own
    exception)."""
    from app.models.audit_log import AuditLog

    org = bootstrap_org_user(client, email_prefix="p91-selfapprove")
    owner_headers = org["org_headers"]

    # Policy owned by the same user who will attempt to approve it. The bootstrap user
    # is org owner, so they hold compliance_policies:approve -- only four-eyes should
    # stop the self-approval.
    policy = _create_policy(
        client, owner_headers, owner_user_id=org["user_id"], title="Self Approve Policy"
    )

    to_review = client.patch(
        f"{BASE}/{policy['id']}", headers=owner_headers, json={"status": "under_review"}
    )
    assert to_review.status_code == 200

    self_approve = client.patch(
        f"{BASE}/{policy['id']}", headers=owner_headers, json={"status": "approved"}
    )
    assert self_approve.status_code == 400, (
        f"owner self-approval via PATCH must be rejected, got {self_approve.status_code}: "
        f"{self_approve.json()}"
    )

    # The policy must NOT have flipped to approved and must carry no approver.
    detail = client.get(f"{BASE}/{policy['id']}", headers=owner_headers).json()
    assert detail["status"] == "under_review"
    assert detail["approved_by_user_id"] is None

    # The blocked attempt is itself audited (governance-relevant event).
    blocked = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.entity_id == uuid.UUID(policy["id"]),
            AuditLog.action == "compliance_policy.self_approval_blocked",
        )
        .all()
    )
    assert len(blocked) == 1, "self-approval rejection must be audited"
    assert str(blocked[0].actor_user_id) == org["user_id"]


def test_phase91_patch_status_approval_by_different_user_allowed(client, db_session):
    """The legitimate PATCH-status approval path still works: a DIFFERENT user with
    compliance_policies:approve can approve a policy owned by someone else."""
    org = bootstrap_org_user(client, email_prefix="p91-diffapprove")

    owner_user = _create_user_with_role(
        db_session,
        org_id=org["organization_id"],
        email="p91-diffapprove-owner@example.com",
        role_name="compliance_manager",
    )
    approver_token = login_user(client, "p91-diffapprove-owner@example.com")  # noqa: F841 (placeholder)

    # Policy owned by owner_user; the bootstrap org owner (a DIFFERENT identity, holding
    # approve) drives the transition and approves it.
    policy = _create_policy(
        client, org["org_headers"], owner_user_id=str(owner_user.id), title="Diff Approver Policy"
    )
    r1 = client.patch(
        f"{BASE}/{policy['id']}", headers=org["org_headers"], json={"status": "under_review"}
    )
    assert r1.status_code == 200
    r2 = client.patch(
        f"{BASE}/{policy['id']}", headers=org["org_headers"], json={"status": "approved"}
    )
    assert r2.status_code == 200, f"different-user approval must succeed: {r2.json()}"
    body = r2.json()
    assert body["status"] == "approved"
    assert body["approved_by_user_id"] == org["user_id"]
    assert body["approved_by_user_id"] != str(owner_user.id)
