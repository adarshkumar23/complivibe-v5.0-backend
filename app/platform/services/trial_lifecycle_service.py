"""Trial lifecycle sweep: pre-expiry warnings + expired-trial downgrade to Free.

Belt-and-braces to the lazy per-request downgrade in app/core/billing_deps.py:
the lazy path handles orgs that make a request after expiry; this daily sweep
handles dormant orgs that don't. Both share
BillingService.downgrade_trial_if_expired (atomic, audited, data-preserving).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_outbox import EmailOutbox
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.platform.services.billing_service import BillingService

WARNING_T3_EVENT = "trial.expiry.warning.t3"
WARNING_T1_EVENT = "trial.expiry.warning.t1"


class TrialLifecycleService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    def _owner_admin_recipients(self, org_id: uuid.UUID) -> list[User]:
        return list(
            self.db.execute(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .join(Role, Role.id == Membership.role_id)
                .where(
                    Membership.organization_id == org_id,
                    Membership.status == "active",
                    Role.name.in_(("owner", "admin")),
                    User.is_active.is_(True),
                    User.email.is_not(None),
                )
            )
            .scalars()
            .unique()
            .all()
        )

    def send_expiry_warnings(self, now: datetime, *, days: int, event_type: str) -> int:
        """Queue a pre-expiry warning for trial orgs entering the ``days``-left window.

        Idempotent: dedups on (organization_id, event_type) against email_outbox,
        so a given org is warned at most once per stage across all sweep runs
        (one trial per org lifetime -> one t3 + one t1 ever)."""
        window_end = now + timedelta(days=days)
        orgs = (
            self.db.execute(
                select(Organization).where(
                    Organization.subscription_plan == "trial",
                    Organization.trial_ends_at.is_not(None),
                    Organization.trial_ends_at > now,
                    Organization.trial_ends_at <= window_end,
                )
            )
            .scalars()
            .all()
        )
        queued = 0
        for org in orgs:
            already = self.db.execute(
                select(EmailOutbox.id).where(
                    EmailOutbox.organization_id == org.id,
                    EmailOutbox.event_type == event_type,
                )
            ).first()
            if already:
                continue
            recipients = self._owner_admin_recipients(org.id)
            if not recipients:
                continue
            subject = f"Your CompliVibe trial ends in {days} day{'s' if days != 1 else ''}"
            body = (
                f"Your 14-day CompliVibe trial ends in {days} day{'s' if days != 1 else ''} "
                f"(on {self._as_utc(org.trial_ends_at).date().isoformat()}).\n\n"
                "When it ends, your organization moves to the Free plan -- your data is kept, "
                "but premium features re-lock and core creation is capped at 5 records each.\n\n"
                "Upgrade any time to keep full access: /billing/upgrade\n"
            )
            for user in recipients:
                self.db.add(
                    EmailOutbox(
                        organization_id=org.id,
                        template_id=None,
                        event_type=event_type,
                        recipient_email=user.email,
                        recipient_user_id=user.id,
                        subject=subject,
                        body_text=body,
                        body_html=None,
                        status="pending",
                        priority="normal",
                        scheduled_at=None,
                        queued_at=now,
                        attempt_count=0,
                        max_attempts=3,
                        metadata_json={
                            "source": "trial_lifecycle_sweep",
                            "stage": event_type,
                            "trial_ends_at": self._as_utc(org.trial_ends_at).isoformat(),
                        },
                    )
                )
            queued += 1
        return queued

    def downgrade_expired(self, now: datetime) -> int:
        """Downgrade every expired trial org to Free (idempotent, audited)."""
        expired = (
            self.db.execute(
                select(Organization).where(
                    Organization.subscription_plan == "trial",
                    Organization.trial_ends_at.is_not(None),
                    Organization.trial_ends_at < now,
                )
            )
            .scalars()
            .all()
        )
        billing = BillingService(self.db)
        return sum(1 for org in expired if billing.downgrade_trial_if_expired(org))


def run_daily_trial_lifecycle_sweep(db: Session) -> dict:
    svc = TrialLifecycleService(db)
    now = svc.utcnow()
    warned_t3 = svc.send_expiry_warnings(now, days=3, event_type=WARNING_T3_EVENT)
    warned_t1 = svc.send_expiry_warnings(now, days=1, event_type=WARNING_T1_EVENT)
    downgraded = svc.downgrade_expired(now)
    return {
        "warned_t3": warned_t3,
        "warned_t1": warned_t1,
        "downgraded": downgraded,
        "records_processed": warned_t3 + warned_t1 + downgraded,
    }
