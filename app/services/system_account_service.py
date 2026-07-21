"""The system automation account: the standard pattern for "needs a real user FK but is not a person".

WHEN TO USE THIS
================
Reach for this when core itself originates a record that a core table insists was
authored by a user. Today that means:

  * issues.created_by / issues.owner_id  -- NOT NULL FK users.id ON DELETE RESTRICT
  * ai_governance_reviews.created_by      -- NOT NULL FK users.id ON DELETE RESTRICT

There is no nullable path on either, and adding one would mean altering a live core
table's constraint to accommodate automation -- a much larger change than the problem
warrants, and one that weakens an invariant every human-authored row still relies on.

Do NOT reach for this to authenticate a machine caller. Inbound machine ingest has its
own mechanism -- `subsystem_ingest_keys`, one key per (organization, key_type) -- and
that is the right tool when the question is "may this caller push data?". This account
answers a different question: "whose name goes on a row core wrote itself?".

THE DESIGN, AND WHY
===================
ONE account, not one per organization. A per-org account (which is what the upstream
patent-P4 patch proposed) multiplies a fake user by the tenant count, gives every
tenant a distinct fake identity to be confused by, and makes "how many system accounts
exist?" unanswerable without a scan. One row is easier to reason about, easier to
exclude, and easier to audit. Tenancy is carried by the per-org Membership rows, which
are required anyway because IssueService._ensure_active_member checks membership, not
identity.

The address is `automation@complivibe.invalid`. `.invalid` is reserved by RFC 2606
precisely so it can never be delegated or resolved. (The upstream patch used
`compliview.internal` -- a typo of the product name, on a TLD that is not reserved and
is in fact used privately by real deployments.)

That choice does more work than being merely undeliverable. `email-validator`, which
backs pydantic's EmailStr, REJECTS reserved/special-use domains outright:

    value is not a valid email address: The part after the @-sign is a special-use or
    reserved name that cannot be used with email.

Every inbound surface that takes an address -- LoginRequest, MembershipCreate,
invitations -- types it as EmailStr, so this address is structurally unsubmittable.
Collision with a real organisation invite is therefore not merely unlikely, it is
impossible by construction rather than by a check somebody has to remember to write.

The consequence to know: the explicit `is_system_account` refusals in the login and
invite paths are DEFENCE IN DEPTH, not the primary control -- EmailStr rejects the
address before they are reached. They exist so the invariant survives someone later
relaxing a schema from EmailStr to str. The refusal in SSOService._get_or_create_user
IS load-bearing: the asserted email there arrives as a raw `str` from the IdP and never
passes through EmailStr.

A second consequence: `MembershipUserRead.email` is EmailStr, so if this account ever
did leak into a membership listing the response would 500 rather than quietly show a
robot. That is a fail-loud, which is the direction to prefer, but the real defence is
that every such listing filters it out -- see `exclude_system_accounts`.

It is `is_active=True` and `status='active'` because membership checks demand it. That
is exactly why `is_system_account` had to be a new column: nothing else on the row can
tell it apart from a person.

Its role grants ZERO permissions, deliberately. Dispatch from the compliance event
bridge calls core services directly, service-to-service; it never traverses an
authenticated route, so no permission is ever consulted. The role exists solely to
satisfy Membership.role_id NOT NULL. If a future code path ever does route a system
action through require_permission, it will fail closed rather than silently acting with
someone's authority.

Login is impossible twice over: the password hash is of a freshly generated secret that
is never stored or returned, and `authenticate_user` refuses `is_system_account` rows
outright.

EXCLUDING IT
============
Every people-facing surface must exclude it. Use `exclude_system_accounts()` below on
any query that lists, counts or searches users or memberships. The surfaces that
currently apply this are listed in tests/unit/test_system_account.py, which asserts the
exclusion end-to-end rather than trusting this docstring to stay true.

It must still appear where it genuinely acted: audit log actors, and the
created_by/owner of a row it authored. Hiding it there would misattribute a machine
decision to a person, which is worse than showing a robot's name.

KNOWN RESIDUAL, recorded rather than quietly left
=================================================
Roughly fifty per-domain assignment validators (IssueService._ensure_active_member and
its equivalents in task, control, risk, vendor, DPIA, DSAR, ROPA, offboarding, access
certification and others) all share the shape

    Membership.user_id == <id> AND Membership.status == 'active'
      AND User.is_active AND User.status == 'active'

and therefore still ACCEPT this account if a caller supplies its id explicitly. They are
not patched here, for two reasons: the account is already absent from every picker that
would offer it, so reaching one requires knowing and typing the UUID; and editing fifty
validators in one change carries more regression risk than the exposure justifies.

The exposure if it happens is bounded -- the account holds no permissions, and the email
backstop in EmailService.queue_email means an assignment produces no bounced mail -- but
it is not zero: the assignee would render as "CompliVibe Automation" in that domain's
lists. The clean fix is a shared `require_assignable_member` helper those validators call
instead of each re-implementing the query. That is worth doing on its own, with its own
tests, rather than as a rider on this change.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User

#: RFC 2606 reserved TLD -- can never be delegated, resolved, or invited.
SYSTEM_ACCOUNT_EMAIL = "automation@complivibe.invalid"
SYSTEM_ACCOUNT_FULL_NAME = "CompliVibe Automation"

#: Per-org role that grants nothing. Named distinctly from the seeded product roles so
#: it can never be confused with one, and so ROLE_PERMISSION_MAP never picks it up.
SYSTEM_ACCOUNT_ROLE_NAME = "system_automation"
SYSTEM_ACCOUNT_ROLE_DESCRIPTION = (
    "CompliVibe Automation system account. Grants no permissions; exists only to "
    "satisfy Membership.role_id. Never assign a person to this role."
)


def exclude_system_accounts(stmt: Select[Any], user_model: type[User] = User) -> Select[Any]:
    """Filter system accounts out of a users query.

    `.is_(False)` rather than `== False` or a truthiness test, so the predicate stays
    correct in SQL and reads the same way as the other NULL-safe filters in this
    codebase.
    """
    return stmt.where(user_model.is_system_account.is_(False))


def get_system_account(db: Session) -> User | None:
    """The system account if it exists, else None. Never creates."""
    return db.execute(select(User).where(User.email == SYSTEM_ACCOUNT_EMAIL)).scalar_one_or_none()


def ensure_system_account(db: Session) -> User:
    """The singleton system account, created on first use.

    Idempotent: selects by natural key (email), creates if missing, flushes, returns --
    the same shape as SeedService's other `ensure_*` helpers.
    """
    existing = get_system_account(db)
    if existing is not None:
        # Repair the flag if an older row predates the column's introduction.
        if not existing.is_system_account:
            existing.is_system_account = True
            db.flush()
        return existing

    user = User(
        id=uuid.uuid4(),
        email=SYSTEM_ACCOUNT_EMAIL,
        full_name=SYSTEM_ACCOUNT_FULL_NAME,
        # Hash of a secret generated here and immediately discarded. Nobody -- including
        # whoever runs this -- can know the plaintext. authenticate_user also refuses
        # system accounts outright, so this is defence in depth, not the only lock.
        hashed_password=get_password_hash(secrets.token_urlsafe(64)),
        status="active",
        is_active=True,
        is_superuser=False,
        is_system_account=True,
    )
    db.add(user)
    db.flush()
    return user


def ensure_system_account_role(db: Session, organization_id: uuid.UUID) -> Role:
    """The org's zero-permission role for the system account."""
    existing = db.execute(
        select(Role).where(
            Role.organization_id == organization_id,
            Role.name == SYSTEM_ACCOUNT_ROLE_NAME,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    role = Role(
        organization_id=organization_id,
        name=SYSTEM_ACCOUNT_ROLE_NAME,
        description=SYSTEM_ACCOUNT_ROLE_DESCRIPTION,
        is_system=True,
        is_system_role=True,
        is_active=True,
    )
    db.add(role)
    db.flush()
    # Deliberately no RolePermission rows. See the module docstring.
    return role


def ensure_system_account_membership(db: Session, organization_id: uuid.UUID) -> User:
    """The system account, guaranteed to be an active member of `organization_id`.

    Called lazily at the point of use -- the first time an org's compliance event bridge
    needs to author an issue or a review. Idempotent and cheap, so there is no need for
    a bulk backfill across existing organisations.
    """
    user = ensure_system_account(db)

    membership = db.execute(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user.id,
        )
    ).scalar_one_or_none()

    if membership is None:
        role = ensure_system_account_role(db, organization_id)
        db.add(
            Membership(
                organization_id=organization_id,
                user_id=user.id,
                role_id=role.id,
                status="active",
            )
        )
        db.flush()
    elif membership.status != "active":
        # A membership that was deactivated (e.g. by a bulk operation) would make every
        # subsequent system-authored issue 422. Reactivate rather than fail.
        membership.status = "active"
        db.flush()

    return user
