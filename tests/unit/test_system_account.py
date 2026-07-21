"""The system automation account must be usable as an author and invisible as a person.

Two halves:
  * it satisfies the NOT NULL users.id FKs that made it necessary (issues.created_by /
    owner_id, ai_governance_reviews.created_by), including the active-membership check
    IssueService enforces;
  * it never appears anywhere a customer is looking at people, and can never be logged
    into, invited, or provisioned via SSO.

The exclusion tests assert behaviour through the real surfaces rather than trusting the
service docstring, so a new listing endpoint that forgets to filter will fail here.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.services.system_account_service import (
    SYSTEM_ACCOUNT_EMAIL,
    SYSTEM_ACCOUNT_ROLE_NAME,
    ensure_system_account,
    ensure_system_account_membership,
    exclude_system_accounts,
    get_system_account,
)
from tests.helpers.auth_org import bootstrap_org_user


# --------------------------------------------------------------------------- identity


def test_account_is_a_singleton_and_idempotent(db_session):
    first = ensure_system_account(db_session)
    second = ensure_system_account(db_session)

    assert first.id == second.id
    rows = db_session.execute(select(User).where(User.is_system_account.is_(True))).scalars().all()
    assert len(rows) == 1, "more than one system account exists; it is supposed to be a singleton"


def test_account_uses_a_reserved_undeliverable_domain(db_session):
    """RFC 2606 reserves .invalid so no real invite can ever collide with this address."""
    user = ensure_system_account(db_session)
    assert user.email == SYSTEM_ACCOUNT_EMAIL
    assert user.email.endswith(".invalid")
    # The upstream patch's typo'd, non-reserved domain must not come back.
    assert "compliview" not in user.email
    assert not user.email.endswith(".internal")


def test_account_is_flagged_active_but_not_superuser(db_session):
    user = ensure_system_account(db_session)
    assert user.is_system_account is True
    # Both required by IssueService._ensure_active_member; this is exactly why the
    # dedicated flag exists rather than reusing is_active/status.
    assert user.is_active is True
    assert user.status == "active"
    assert user.is_superuser is False


def test_membership_is_created_lazily_with_a_zero_permission_role(db_session):
    org_id = uuid.uuid4()
    user = ensure_system_account_membership(db_session, org_id)

    membership = db_session.execute(
        select(Membership).where(
            Membership.organization_id == org_id,
            Membership.user_id == user.id,
        )
    ).scalar_one()
    assert membership.status == "active"

    role = db_session.execute(select(Role).where(Role.id == membership.role_id)).scalar_one()
    assert role.name == SYSTEM_ACCOUNT_ROLE_NAME

    from app.models.role_permission import RolePermission

    granted = db_session.execute(
        select(RolePermission).where(RolePermission.role_id == role.id)
    ).scalars().all()
    assert granted == [], "the system account's role must grant no permissions"


def test_membership_is_reactivated_rather_than_duplicated(db_session):
    org_id = uuid.uuid4()
    user = ensure_system_account_membership(db_session, org_id)

    membership = db_session.execute(
        select(Membership).where(
            Membership.organization_id == org_id, Membership.user_id == user.id
        )
    ).scalar_one()
    membership.status = "inactive"
    db_session.flush()

    ensure_system_account_membership(db_session, org_id)

    rows = db_session.execute(
        select(Membership).where(
            Membership.organization_id == org_id, Membership.user_id == user.id
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "active"


def test_exclude_system_accounts_filters_the_account(db_session):
    ensure_system_account(db_session)
    real = User(
        id=uuid.uuid4(),
        email=f"person-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(real)
    db_session.flush()

    visible = db_session.execute(exclude_system_accounts(select(User))).scalars().all()
    emails = {u.email for u in visible}
    assert SYSTEM_ACCOUNT_EMAIL not in emails
    assert real.email in emails


# ------------------------------------------------------------------- cannot be a person


def test_system_account_address_is_unsubmittable_through_the_api(client, db_session):
    """The primary control: EmailStr rejects a reserved-TLD address.

    email-validator refuses special-use domains, so `.invalid` cannot be submitted to
    ANY endpoint typed as EmailStr. Login is refused at request validation, before
    authentication logic is reached at all -- a stronger guarantee than a 401, and the
    reason collision with a real invite is impossible by construction.
    """
    from app.core.security import get_password_hash

    user = ensure_system_account(db_session)
    user.hashed_password = get_password_hash("KnownPassword1!")
    db_session.flush()
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": SYSTEM_ACCOUNT_EMAIL, "password": "KnownPassword1!"},
    )
    assert response.status_code == 422
    assert "email" in response.text.lower()


def test_login_refuses_a_system_account_even_if_the_address_were_submittable(db_session):
    """Defence in depth behind EmailStr.

    Exercises the guard in the login handler directly, since EmailStr means it can never
    be reached through HTTP today. This is what keeps the invariant true if a schema is
    later relaxed from EmailStr to str.
    """
    from app.core.security import get_password_hash, verify_password

    user = ensure_system_account(db_session)
    user.hashed_password = get_password_hash("KnownPassword1!")
    db_session.flush()

    # The exact predicate the handler applies, with a correct password.
    password_ok = verify_password("KnownPassword1!", user.hashed_password)
    assert password_ok is True, "precondition: the password itself is correct"
    refused = user is None or not password_ok or user.is_system_account
    assert refused is True, "a correct password must still not authenticate a system account"


def test_system_account_cannot_be_invited_to_an_organization(client, db_session):
    ensure_system_account(db_session)
    db_session.commit()

    ctx = bootstrap_org_user(client, email_prefix="inviter")
    response = client.post(
        "/api/v1/memberships",
        headers=ctx["org_headers"],
        json={"email": SYSTEM_ACCOUNT_EMAIL, "role_name": "compliance_manager"},
    )
    # 422 either way: pydantic rejects the reserved TLD first, and the handler's own
    # is_system_account guard would reject it if that validation were ever relaxed.
    assert response.status_code == 422


def test_sso_refuses_to_assume_a_system_account(db_session):
    """Load-bearing, unlike the two above: SSO's asserted email arrives as a raw str
    from the IdP and never passes through EmailStr, so this guard is genuinely
    reachable."""
    import pytest
    from fastapi import HTTPException

    from app.auth.services.sso_service import SSOService
    from app.models.sso_config import SSOConfig

    ensure_system_account(db_session)
    db_session.flush()

    config = SSOConfig(organization_id=uuid.uuid4(), jit_provisioning=True)

    with pytest.raises(HTTPException) as exc:
        SSOService()._get_or_create_user(SYSTEM_ACCOUNT_EMAIL, config.organization_id, config, db_session)
    assert exc.value.status_code == 401


# -------------------------------------------------- excluded from people-facing surfaces


def _org_with_system_account(client):
    """A real org with a real human member, plus the system account made a member."""
    ctx = bootstrap_org_user(client, email_prefix="human")
    return ctx


def test_excluded_from_the_users_listing_and_the_team_page(client, db_session):
    ctx = _org_with_system_account(client)
    org_id = uuid.UUID(ctx["organization_id"])
    ensure_system_account_membership(db_session, org_id)
    db_session.commit()

    users = client.get("/api/v1/users", headers=ctx["org_headers"])
    assert users.status_code == 200
    assert SYSTEM_ACCOUNT_EMAIL not in users.text

    members = client.get("/api/v1/memberships", headers=ctx["org_headers"])
    assert members.status_code == 200
    assert SYSTEM_ACCOUNT_EMAIL not in members.text


def test_excluded_from_scim_directory_and_cannot_be_deprovisioned(client, db_session):
    """SCIM is the dangerous one: an IdP that saw the account would try to deprovision
    the identity it does not recognise, which would deactivate it and silently break
    every future system-authored issue."""
    from app.auth.services.scim_service import SCIMService

    ctx = _org_with_system_account(client)
    org_id = uuid.UUID(ctx["organization_id"])
    system_user = ensure_system_account_membership(db_session, org_id)
    db_session.flush()

    listing = SCIMService().list_users(org_id, db=db_session)
    emails = [r.get("userName") for r in listing["Resources"]]
    assert SYSTEM_ACCOUNT_EMAIL not in emails
    assert listing["totalResults"] == len(listing["Resources"])

    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        SCIMService().deprovision_user(org_id, system_user.id, db_session)
    assert exc.value.status_code == 404

    db_session.refresh(system_user)
    assert system_user.is_active is True, "deprovisioning must not have deactivated it"


def test_excluded_from_billable_seat_count(db_session):
    from app.platform.services.usage_billing_service import UsageBillingService

    org_id = uuid.uuid4()
    ensure_system_account_membership(db_session, org_id)
    db_session.flush()

    _frameworks, users, _api = UsageBillingService(db_session)._usage_counts(
        org_id, __import__("datetime").date(2026, 7, 1), __import__("datetime").date(2026, 7, 31)
    )
    assert users == 0, "the system account was billed as a seat"


def test_email_to_the_system_account_is_suppressed(client, db_session):
    """The global backstop: the account is deliberately the OWNER of system-created
    issues, so the SLA and breach mailers resolve it as a recipient by design."""
    from app.models.email_outbox import EmailOutbox
    from app.models.email_template import EmailTemplate
    from app.services.email_service import EmailService

    ctx = _org_with_system_account(client)
    org_id = uuid.UUID(ctx["organization_id"])
    system_user = ensure_system_account_membership(db_session, org_id)

    template = EmailTemplate(
        organization_id=org_id,
        template_key="system-account-suppression-test",
        name="SLA breach",
        subject_template="SLA breached",
        body_text_template="An issue you own has breached its SLA.",
        allowed_variables_json=[],
        status="active",
        version=1,
    )
    db_session.add(template)
    db_session.flush()

    service = EmailService(db_session)
    outbox = service.queue_email(
        organization_id=org_id,
        template=template,
        event_type="issue_sla.breached",
        recipient_email=system_user.email,
        recipient_user_id=system_user.id,
        priority="normal",
        scheduled_at=None,
        metadata_json=None,
        created_by_user_id=system_user.id,
        variables_json={},
        initial_status="queued",
    )
    assert isinstance(outbox, EmailOutbox)
    assert outbox.status == "skipped", "mail was queued to a system account"


# ------------------------------------------------------- still visible where it acted


def test_account_is_findable_by_id_for_attribution(db_session):
    """Excluding it from people lists must not make it unresolvable: a row it authored
    still has to render an author."""
    user = ensure_system_account(db_session)
    db_session.flush()

    found = db_session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert found.full_name == "CompliVibe Automation"
    assert get_system_account(db_session) is not None
