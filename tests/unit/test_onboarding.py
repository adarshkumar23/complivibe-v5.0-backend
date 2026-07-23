from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from sqlalchemy import inspect, select

from app.models.audit_log import AuditLog
from app.models.control import Control
from app.models.email_outbox import EmailOutbox
from app.models.framework import Framework
from app.models.organization import Organization
from app.models.organization_framework import OrganizationFramework
from app.models.risk import Risk
from app.models.team_invitation import TeamInvitation
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user


def _start_payload(slug: str = "onboard-org") -> dict:
    return {
        "org_name": "Onboarding Org",
        "org_slug": slug,
        "admin_email": f"{slug}@example.com",
        "admin_full_name": "Onboarding Admin",
        "admin_password": "StrongPass123!",
    }


@pytest.mark.free_registration
def test_onboarding_start_and_slug_checks(client, db_session):
    tables = set(inspect(db_session.bind).get_table_names())
    assert "team_invitations" in tables

    payload = _start_payload("new-onboard")
    start = client.post("/api/v1/onboarding/start", json=payload)
    assert start.status_code == 200, start.text
    body = start.json()
    assert body["access_token"]
    assert body["onboarding_step"] == "org_created"

    org = db_session.get(Organization, UUID(body["org_id"]))
    assert org is not None
    # Stage 1c-1: onboarding lands a new org on the Free plan (active, no trial),
    # not an auto-started trial. Trial is entered only by redeeming a trial code.
    assert org.subscription_status == "active"
    assert org.subscription_plan == "free"
    assert org.trial_ends_at is None

    welcome = db_session.execute(
        select(EmailOutbox).where(
            EmailOutbox.organization_id == org.id,
            EmailOutbox.event_type == "onboarding.welcome",
        )
    ).scalars().first()
    assert welcome is not None

    dup_slug = client.post("/api/v1/onboarding/start", json=_start_payload("new-onboard"))
    assert dup_slug.status_code == 409

    dup_email_payload = _start_payload("another-onboard")
    dup_email_payload["admin_email"] = payload["admin_email"]
    dup_email = client.post("/api/v1/onboarding/start", json=dup_email_payload)
    assert dup_email.status_code == 409

    taken = client.get("/api/v1/onboarding/check-slug", params={"slug": "new-onboard"})
    assert taken.status_code == 200
    assert taken.json()["available"] is False

    available = client.get("/api/v1/onboarding/check-slug", params={"slug": "fresh-slug"})
    assert available.status_code == 200
    assert available.json()["available"] is True


def test_framework_selection_and_team_invites_and_revoke(client, db_session):
    started = client.post("/api/v1/onboarding/start", json=_start_payload("fw-invite"))
    assert started.status_code == 200
    token = started.json()["access_token"]
    org_id = started.json()["org_id"]
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}

    framework = Framework(
        code="FW-TEST",
        name="Framework Test",
        category="security",
        jurisdiction="global",
        status="active",
    )
    db_session.add(framework)
    db_session.flush()

    select_resp = client.post(
        "/api/v1/onboarding/select-frameworks",
        headers=headers,
        json={"framework_ids": [str(framework.id), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]},
    )
    assert select_resp.status_code == 200
    select_body = select_resp.json()
    assert "Framework Test" in select_body["activated"]
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in select_body["skipped"]
    assert select_body["onboarding_step"] == "frameworks_selected"

    invite_resp = client.post(
        "/api/v1/onboarding/invite-team",
        headers=headers,
        json={
            "invites": [
                {"email": "member1@example.com", "role_code": "member"},
                {"email": "member2@example.com", "role_code": "admin"},
            ]
        },
    )
    assert invite_resp.status_code == 200, invite_resp.text
    invite_body = invite_resp.json()
    assert len(invite_body["invited"]) == 2
    assert invite_body["onboarding_step"] == "team_invited"

    queued_invites = db_session.execute(
        select(EmailOutbox).where(
            EmailOutbox.organization_id == UUID(org_id),
            EmailOutbox.event_type == "onboarding.team_invite",
        )
    ).scalars().all()
    assert len(queued_invites) == 2

    duplicate_invite = client.post(
        "/api/v1/onboarding/invite-team",
        headers=headers,
        json={"invites": [{"email": "member1@example.com", "role_code": "member"}]},
    )
    assert duplicate_invite.status_code == 200
    assert duplicate_invite.json()["skipped"][0]["reason"] == "already_invited"

    listing = client.get("/api/v1/onboarding/team-invitations", headers=headers)
    assert listing.status_code == 200
    assert any(item["status"] == "pending" for item in listing.json())

    first_id = listing.json()[0]["id"]
    revoke = client.delete(f"/api/v1/onboarding/team-invitations/{first_id}", headers=headers)
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"


def test_accept_invitation_public_and_error_cases(client, db_session):
    started = client.post("/api/v1/onboarding/start", json=_start_payload("accept-org"))
    assert started.status_code == 200
    token = started.json()["access_token"]
    org_id = started.json()["org_id"]
    owner_headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}

    invite = client.post(
        "/api/v1/onboarding/invite-team",
        headers=owner_headers,
        json={"invites": [{"email": "invitee@example.com", "role_code": "member"}]},
    )
    assert invite.status_code == 200

    pending_invite = db_session.execute(
        select(TeamInvitation).where(
            TeamInvitation.organization_id == UUID(org_id),
            TeamInvitation.email == "invitee@example.com",
            TeamInvitation.status == "pending",
        )
    ).scalar_one()

    accepted = client.post(
        "/api/v1/onboarding/accept-invite",
        json={
            "token": pending_invite.token,
            "full_name": "Invited User",
            "password": "ValidPass123!",
        },
    )
    assert accepted.status_code == 200, accepted.text
    accept_body = accepted.json()
    assert accept_body["access_token"]
    assert accept_body["org_id"] == org_id

    accepted_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org_id),
            AuditLog.action == "onboarding.invitation_accepted",
        )
    ).scalars().first()
    assert accepted_audit is not None

    used_again = client.post(
        "/api/v1/onboarding/accept-invite",
        json={
            "token": pending_invite.token,
            "full_name": "Invited User",
            "password": "ValidPass123!",
        },
    )
    assert used_again.status_code == 404

    invalid = client.post(
        "/api/v1/onboarding/accept-invite",
        json={"token": "bad-token", "full_name": "Name", "password": "ValidPass123!"},
    )
    assert invalid.status_code == 404

    exp_invite = TeamInvitation(
        organization_id=UUID(org_id),
        email="expired@example.com",
        role_code="member",
        invited_by=UUID(started.json()["user_id"]),
        token="expired-token",
        status="pending",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
        created_at=datetime.now(UTC),
    )
    db_session.add(exp_invite)
    db_session.flush()

    expired = client.post(
        "/api/v1/onboarding/accept-invite",
        json={"token": "expired-token", "full_name": "Expired", "password": "ValidPass123!"},
    )
    assert expired.status_code == 410


def test_checklist_complete_audit_and_org_isolation(client, db_session):
    started = client.post("/api/v1/onboarding/start", json=_start_payload("check-org"))
    assert started.status_code == 200
    token = started.json()["access_token"]
    org_id = started.json()["org_id"]
    user_id = started.json()["user_id"]
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}

    framework = Framework(code="FW-CHECK", name="Framework Check", category="security", jurisdiction="global", status="active")
    db_session.add(framework)
    db_session.flush()

    client.post(
        "/api/v1/onboarding/select-frameworks",
        headers=headers,
        json={"framework_ids": [str(framework.id)]},
    )
    client.post(
        "/api/v1/onboarding/invite-team",
        headers=headers,
        json={"invites": [{"email": "member-check@example.com"}]},
    )

    extra_user = User(
        email="already-member@example.com",
        full_name="Already Member",
        hashed_password="hash",
        is_active=True,
        status="active",
        is_superuser=False,
    )
    db_session.add(extra_user)
    db_session.flush()

    owner_membership = db_session.execute(
        select(OrganizationFramework).where(OrganizationFramework.organization_id == UUID(org_id))
    ).scalars().first()
    assert owner_membership is not None

    from app.models.membership import Membership

    owner_row = db_session.execute(
        select(Membership).where(
            Membership.organization_id == UUID(org_id),
            Membership.user_id == UUID(user_id),
        )
    ).scalar_one()

    db_session.add(
        Membership(
            organization_id=UUID(org_id),
            user_id=extra_user.id,
            role_id=owner_row.role_id,
            status="active",
            invited_by=UUID(user_id),
        )
    )
    db_session.add(
        Control(
            organization_id=UUID(org_id),
            title="Control 1",
            control_type="process",
            status="implemented",
            criticality="medium",
            source="custom",
        )
    )
    db_session.add(
        Risk(
            organization_id=UUID(org_id),
            title="Risk 1",
            category="security",
            severity="high",
            likelihood=3,
            impact=3,
            inherent_score=9,
            status="identified",
            treatment_strategy="mitigate",
            composite_score_method="standard",
        )
    )
    db_session.flush()

    checklist = client.get("/api/v1/onboarding/checklist", headers=headers)
    assert checklist.status_code == 200
    checklist_body = checklist.json()
    assert checklist_body["completion_percentage"] == 100

    # Every completed signal must carry a real completed_at timestamp, not a hardcoded None,
    # so the checklist accurately reflects when each milestone was actually reached.
    items_by_id = {item["id"]: item for item in checklist_body["checklist_items"]}
    for item_id in ("frameworks_selected", "team_invited_or_has_members", "has_controls", "has_risks"):
        item = items_by_id[item_id]
        assert item["completed"] is True
        assert item["completed_at"] is not None, f"{item_id} should have a real completed_at timestamp"

    complete = client.post("/api/v1/onboarding/complete", headers=headers)
    assert complete.status_code == 200
    assert complete.json()["onboarding_completed"] is True

    org_row = db_session.get(Organization, UUID(org_id))
    assert org_row is not None
    assert org_row.onboarding_completed is True

    actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == UUID(org_id),
                AuditLog.action.in_(
                    [
                        "onboarding.org_created",
                        "onboarding.frameworks_selected",
                        "onboarding.team_invited",
                        "onboarding.completed",
                    ]
                ),
            )
        ).all()
    }
    assert "onboarding.org_created" in actions
    assert "onboarding.frameworks_selected" in actions
    assert "onboarding.team_invited" in actions
    assert "onboarding.completed" in actions

    second_org = bootstrap_org_user(client, email_prefix="onboard-iso")
    bad_headers = {
        "Authorization": f"Bearer {second_org['access_token']}",
        "X-Organization-ID": org_id,
    }
    forbidden = client.get("/api/v1/onboarding/checklist", headers=bad_headers)
    assert forbidden.status_code == 403
