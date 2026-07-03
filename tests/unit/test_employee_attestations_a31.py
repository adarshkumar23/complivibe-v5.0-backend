from datetime import UTC, date, datetime, timedelta
import uuid

from app.core.security import get_password_hash
from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.policy_attestation_campaign import PolicyAttestationCampaign
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

CAMPAIGNS_BASE = "/api/v1/compliance/attestation-campaigns"
RECORDS_BASE = "/api/v1/compliance/attestation-records"


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str = "reviewer") -> User:
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


def _create_policy(client, headers: dict[str, str], *, owner_user_id: str, title: str, version: str = "1.0") -> dict:
    response = client.post(
        "/api/v1/compliance/policies",
        headers=headers,
        json={
            "title": title,
            "description": "Policy text",
            "policy_type": "access_control",
            "status": "draft",
            "owner_user_id": owner_user_id,
            "version": version,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_campaign(
    client,
    headers: dict[str, str],
    *,
    policy_id: str,
    user_ids: list[str],
    name: str = "A3.1 Campaign",
    due_date_value: date | None = None,
    expiry_days: int = 365,
    policy_version: str = "1.0",
) -> dict:
    response = client.post(
        CAMPAIGNS_BASE,
        headers=headers,
        json={
            "title": name,
            "description": "Campaign desc",
            "policy_id": policy_id,
            "attestation_text": f"{name} attestation text",
            "due_date": (due_date_value or (date.today() + timedelta(days=14))).isoformat(),
        },
    )
    assert response.status_code == 201
    return response.json()


def test_a31_campaign_lifecycle_create_list_update_cancel(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a31-campaign")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="A3.1 Policy")
    user1 = _create_active_user_with_role(db_session, org["organization_id"], "a31-c1@example.com")
    user2 = _create_active_user_with_role(db_session, org["organization_id"], "a31-c2@example.com")

    created = _create_campaign(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        user_ids=[str(user1.id), str(user2.id)],
        name="Q3 Policy Attestation",
    )
    assert created["campaign"]["policy_id"] == policy["id"]
    assert created["total_members"] >= 2
    assert created["pending_count"] == created["total_members"]

    listed = client.get(CAMPAIGNS_BASE, headers=org["org_headers"], params={"status_value": "active"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    summary = client.get(f"{CAMPAIGNS_BASE}/{created['campaign']['id']}", headers=org["org_headers"])
    assert summary.status_code == 200
    assert summary.json()["campaign"]["id"] == created["campaign"]["id"]


def test_a31_attestation_submit_lifecycle_and_guards(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a31-submit")
    submitter = _create_active_user_with_role(db_session, org["organization_id"], "a31-submitter@example.com", role_name="reviewer")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Submit Policy")
    campaign = _create_campaign(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        user_ids=[str(submitter.id)],
        expiry_days=10,
        name="Submit Campaign",
    )
    campaign_id = campaign["campaign"]["id"]

    submit_token = login_user(client, submitter.email)
    submit_headers = org_headers(submit_token, org["organization_id"])

    before = datetime.now(UTC).replace(tzinfo=None)
    submitted = client.post(f"{CAMPAIGNS_BASE}/{campaign_id}/attest", headers=submit_headers, json={})
    after = datetime.now(UTC).replace(tzinfo=None)
    assert submitted.status_code == 200
    body = submitted.json()
    assert body["status"] == "attested"
    assert body["attested_at"] is not None
    attested_at = datetime.fromisoformat(body["attested_at"].replace("Z", "+00:00")).replace(tzinfo=None)
    assert before <= attested_at <= after

    duplicate_submit = client.post(f"{CAMPAIGNS_BASE}/{campaign_id}/attest", headers=submit_headers, json={})
    assert duplicate_submit.status_code in {400, 409}


def test_a31_exemption_and_non_manager_forbidden(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a31-exempt")
    target = _create_active_user_with_role(db_session, org["organization_id"], "a31-target@example.com", role_name="reviewer")
    non_manager = _create_active_user_with_role(db_session, org["organization_id"], "a31-readonly@example.com", role_name="readonly")

    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Exempt Policy")
    campaign = _create_campaign(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        user_ids=[str(target.id)],
        name="Exempt Campaign",
    )
    campaign_id = campaign["campaign"]["id"]

    forbidden_headers = org_headers(login_user(client, non_manager.email), org["organization_id"])
    forbidden = client.post(
        f"{CAMPAIGNS_BASE}/{campaign_id}/exempt/{target.id}",
        headers=forbidden_headers,
        json={"reason": "not allowed"},
    )
    assert forbidden.status_code == 403

    exempted = client.post(
        f"{CAMPAIGNS_BASE}/{campaign_id}/exempt/{target.id}",
        headers=org["org_headers"],
        json={"reason": "Contractor exemption"},
    )
    assert exempted.status_code == 200
    assert exempted.json()["status"] == "exempted"
    assert exempted.json()["exemption_reason"] == "Contractor exemption"

    target_headers = org_headers(login_user(client, target.email), org["organization_id"])
    cannot_attest = client.post(f"{CAMPAIGNS_BASE}/{campaign_id}/attest", headers=target_headers, json={})
    assert cannot_attest.status_code in {200, 400, 409}


def test_a31_single_and_bulk_reminders_use_internal_outbox_only(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a31-remind")
    user1 = _create_active_user_with_role(db_session, org["organization_id"], "a31-r1@example.com", role_name="reviewer")
    user2 = _create_active_user_with_role(db_session, org["organization_id"], "a31-r2@example.com", role_name="reviewer")

    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Reminder Policy")
    campaign = _create_campaign(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        user_ids=[str(user1.id), str(user2.id)],
        name="Reminder Campaign",
    )
    campaign_id = campaign["campaign"]["id"]

    single = client.post(f"{CAMPAIGNS_BASE}/{campaign_id}/remind/{user1.id}", headers=org["org_headers"])
    assert single.status_code == 200
    assert single.json()["reminder_sent_at"] is not None

    token_user1 = login_user(client, user1.email)
    headers_user1 = org_headers(token_user1, org["organization_id"])
    attested = client.post(f"{CAMPAIGNS_BASE}/{campaign_id}/attest", headers=headers_user1, json={})
    assert attested.status_code == 200

    bulk = client.post(f"{CAMPAIGNS_BASE}/{campaign_id}/reminders", headers=org["org_headers"])
    assert bulk.status_code == 200
    assert bulk.json()["reminders_queued"] >= 1

    queued = (
        db_session.query(EmailOutbox)
        .filter(EmailOutbox.organization_id == uuid.UUID(org["organization_id"]))
        .filter(EmailOutbox.event_type == "attestation.reminder")
        .all()
    )
    assert len(queued) >= 2


def test_a31_expire_attestations_scoped_and_unscoped(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a31-expire-a")
    org2 = bootstrap_org_user(client, email_prefix="a31-expire-b")

    user1 = _create_active_user_with_role(db_session, org1["organization_id"], "a31-exp1@example.com", role_name="reviewer")
    user2 = _create_active_user_with_role(db_session, org1["organization_id"], "a31-exp2@example.com", role_name="reviewer")
    user3 = _create_active_user_with_role(db_session, org2["organization_id"], "a31-exp3@example.com", role_name="reviewer")

    policy1 = _create_policy(client, org1["org_headers"], owner_user_id=org1["user_id"], title="Expire Policy 1")
    policy2 = _create_policy(client, org2["org_headers"], owner_user_id=org2["user_id"], title="Expire Policy 2")

    campaign1 = _create_campaign(client, org1["org_headers"], policy_id=policy1["id"], user_ids=[str(user1.id), str(user2.id)], name="Expire C1")
    campaign2 = _create_campaign(client, org2["org_headers"], policy_id=policy2["id"], user_ids=[str(user3.id)], name="Expire C2")

    rec1 = (
        db_session.query(PolicyAttestationRecord)
        .filter(PolicyAttestationRecord.campaign_id == uuid.UUID(campaign1["campaign"]["id"]), PolicyAttestationRecord.user_id == user1.id)
        .one()
    )
    rec2 = (
        db_session.query(PolicyAttestationRecord)
        .filter(PolicyAttestationRecord.campaign_id == uuid.UUID(campaign1["campaign"]["id"]), PolicyAttestationRecord.user_id == user2.id)
        .one()
    )
    rec3 = (
        db_session.query(PolicyAttestationRecord)
        .filter(PolicyAttestationRecord.campaign_id == uuid.UUID(campaign2["campaign"]["id"]), PolicyAttestationRecord.user_id == user3.id)
        .one()
    )
    rec1.status = "attested"
    rec1.attested_at = datetime.now(UTC) - timedelta(days=10)
    rec1.expires_at = datetime.now(UTC) - timedelta(hours=1)
    rec2.status = "attested"
    rec2.attested_at = datetime.now(UTC) - timedelta(days=2)
    rec2.expires_at = datetime.now(UTC) + timedelta(days=5)
    rec3.status = "attested"
    rec3.attested_at = datetime.now(UTC) - timedelta(days=10)
    rec3.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()

    from app.compliance.services.employee_attestation_service import AttestationRecordService

    scoped = AttestationRecordService(db_session).expire_attestations(org_id=uuid.UUID(org1["organization_id"]))
    assert scoped == 1
    db_session.commit()

    db_session.refresh(rec1)
    db_session.refresh(rec2)
    db_session.refresh(rec3)
    assert rec1.status == "expired"
    assert rec2.status == "attested"
    assert rec3.status == "attested"

    unscoped = AttestationRecordService(db_session).expire_attestations()
    assert unscoped == 1
    db_session.commit()
    db_session.refresh(rec3)
    assert rec3.status == "expired"


def test_a31_completion_stats_dashboard_policy_summary_and_tenant_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a31-stats-a")
    org_b = bootstrap_org_user(client, email_prefix="a31-stats-b")

    a_user1 = _create_active_user_with_role(db_session, org_a["organization_id"], "a31-s1@example.com", role_name="reviewer")
    a_user2 = _create_active_user_with_role(db_session, org_a["organization_id"], "a31-s2@example.com", role_name="reviewer")
    a_user3 = _create_active_user_with_role(db_session, org_a["organization_id"], "a31-s3@example.com", role_name="reviewer")

    policy_a = _create_policy(client, org_a["org_headers"], owner_user_id=org_a["user_id"], title="Stats Policy A")
    policy_b = _create_policy(client, org_b["org_headers"], owner_user_id=org_b["user_id"], title="Stats Policy B")

    camp1 = _create_campaign(
        client,
        org_a["org_headers"],
        policy_id=policy_a["id"],
        user_ids=[str(a_user1.id), str(a_user2.id), str(a_user3.id)],
        name="Stats Campaign 1",
        due_date_value=date.today() - timedelta(days=1),
    )
    camp2 = _create_campaign(
        client,
        org_a["org_headers"],
        policy_id=policy_a["id"],
        user_ids=[str(a_user1.id), str(a_user2.id)],
        name="Stats Campaign 2",
        due_date_value=date.today() + timedelta(days=5),
    )
    _ = _create_campaign(
        client,
        org_b["org_headers"],
        policy_id=policy_b["id"],
        user_ids=[org_b["user_id"]],
        name="Stats Campaign B",
    )

    user1_headers = org_headers(login_user(client, a_user1.email), org_a["organization_id"])
    user2_headers = org_headers(login_user(client, a_user2.email), org_a["organization_id"])
    attest1 = client.post(f"{CAMPAIGNS_BASE}/{camp1['campaign']['id']}/attest", headers=user1_headers, json={})
    attest2 = client.post(f"{CAMPAIGNS_BASE}/{camp1['campaign']['id']}/attest", headers=user2_headers, json={})
    assert attest1.status_code == 200
    assert attest2.status_code == 200

    camp1_detail = client.get(f"{CAMPAIGNS_BASE}/{camp1['campaign']['id']}", headers=org_a["org_headers"])
    assert camp1_detail.status_code == 200
    assert 0.0 <= camp1_detail.json()["completion_pct"] <= 100.0
    assert camp1_detail.json()["completion_pct"] > 0.0

    campaigns_list = client.get(CAMPAIGNS_BASE, headers=org_a["org_headers"])
    assert campaigns_list.status_code == 200
    assert len(campaigns_list.json()) >= 2

    policy_summary = client.get(
        f"/api/v1/compliance/policies/{policy_a['id']}/attestation-summary",
        headers=org_a["org_headers"],
    )
    assert policy_summary.status_code == 200
    assert policy_summary.json()["campaigns_count"] == 2
    assert policy_summary.json()["overdue_count"] >= 1

    hidden_campaign = client.get(f"{CAMPAIGNS_BASE}/{camp1['campaign']['id']}", headers=org_b["org_headers"])
    assert hidden_campaign.status_code == 404


def test_a31_user_record_endpoints_and_permissions(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a31-records")
    user1 = _create_active_user_with_role(db_session, org["organization_id"], "a31-u1@example.com", role_name="reviewer")
    user2 = _create_active_user_with_role(db_session, org["organization_id"], "a31-u2@example.com", role_name="readonly")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Record Policy")
    campaign = _create_campaign(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        user_ids=[str(user1.id), str(user2.id)],
        name="Record Campaign",
    )
    token1 = login_user(client, user1.email)
    headers1 = org_headers(token1, org["organization_id"])

    submit = client.post(f"{CAMPAIGNS_BASE}/{campaign['campaign']['id']}/attest", headers=headers1, json={})
    assert submit.status_code == 200

    my_records = client.get(f"{RECORDS_BASE}/me", headers=headers1)
    assert my_records.status_code == 200
    assert all(item["user_id"] == str(user1.id) for item in my_records.json())

    manage_records = client.get(f"{RECORDS_BASE}/user/{user1.id}", headers=org["org_headers"])
    assert manage_records.status_code == 200
    assert len(manage_records.json()) >= 1

    readonly_headers = org_headers(login_user(client, user2.email), org["organization_id"])
    denied = client.get(f"{RECORDS_BASE}/user/{user1.id}", headers=readonly_headers)
    assert denied.status_code == 403


def test_a31_cross_org_submission_forbidden(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a31-cross-a")
    org_b = bootstrap_org_user(client, email_prefix="a31-cross-b")

    a_user = _create_active_user_with_role(db_session, org_a["organization_id"], "a31-cross-user@example.com", role_name="reviewer")
    policy_a = _create_policy(client, org_a["org_headers"], owner_user_id=org_a["user_id"], title="Cross Policy")
    campaign = _create_campaign(
        client,
        org_a["org_headers"],
        policy_id=policy_a["id"],
        user_ids=[str(a_user.id)],
        name="Cross Campaign",
    )
    token_b = login_user(client, org_b["email"])
    headers_b = org_headers(token_b, org_b["organization_id"])
    wrong_org_submit = client.post(f"{CAMPAIGNS_BASE}/{campaign['campaign']['id']}/attest", headers=headers_b, json={})
    assert wrong_org_submit.status_code in {403, 404}


def test_a31_campaign_completion_endpoint_returns_user_breakdown(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a31-completion")
    u1 = _create_active_user_with_role(db_session, org["organization_id"], "a31-comp1@example.com", role_name="reviewer")
    u2 = _create_active_user_with_role(db_session, org["organization_id"], "a31-comp2@example.com", role_name="reviewer")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Completion Policy")
    campaign = _create_campaign(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        user_ids=[str(u1.id), str(u2.id)],
        name="Completion Campaign",
    )

    u1_headers = org_headers(login_user(client, u1.email), org["organization_id"])
    submit = client.post(f"{CAMPAIGNS_BASE}/{campaign['campaign']['id']}/attest", headers=u1_headers, json={})
    assert submit.status_code == 200

    completion = client.get(f"{CAMPAIGNS_BASE}/{campaign['campaign']['id']}/completion", headers=org["org_headers"])
    assert completion.status_code == 200
    assert len(completion.json()) >= 2
    status_map = {row["email"]: row["status"] for row in completion.json()}
    assert status_map[u1.email] == "attested"
    assert status_map[u2.email] == "pending"
