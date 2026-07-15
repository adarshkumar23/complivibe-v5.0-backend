"""Human notification for a surfaced compound insight.

Reuses the EXISTING email/notification-preference mechanism (EmailService ->
EmailOutbox, preference-gated) -- no new channel. This is deliberately SEPARATE
from AuditService.write_audit_log, which only records the trail and does not
notify anyone.

Flush-only: queue_email flushes but does not commit; the caller (the scheduler
job's session) owns the commit.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compound_insight import CompoundInsight
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.services.email_service import EmailService

# Roles whose members should hear about a new org-wide compound exposure.
_GOVERNANCE_ROLE_NAMES = ("owner", "admin", "compliance_manager")
_TEMPLATE_KEY = "compound_insight_surfaced"
_NOTIFICATION_TYPE = "compound_insight_surfaced"


class CompoundInsightNotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _recipients(self, org_id: uuid.UUID) -> list[User]:
        rows = self.db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .join(Role, Role.id == Membership.role_id)
            .where(
                Membership.organization_id == org_id,
                Membership.status == "active",
                Role.name.in_(_GOVERNANCE_ROLE_NAMES),
                User.is_active.is_(True),
                User.status == "active",
            )
        ).scalars().all()
        # de-dupe users who hold more than one qualifying membership/role
        seen: set[uuid.UUID] = set()
        unique: list[User] = []
        for u in rows:
            if u.id not in seen:
                seen.add(u.id)
                unique.append(u)
        return unique

    def notify(self, insight: CompoundInsight) -> int:
        """Queue a preference-gated email to each governance recipient.

        Returns the number of outbox rows queued. Never raises for a routine
        problem (missing template / no recipients) -- surfacing a real detection
        must not be blocked by the notification layer.
        """
        email_service = EmailService(self.db)
        try:
            template = email_service.resolve_template_for_org(
                organization_id=insight.organization_id,
                template_id=None,
                template_key=_TEMPLATE_KEY,
            )
        except Exception:
            # Templates not seeded yet; try to self-heal once, else skip quietly.
            try:
                from app.services.seed_service import SeedService

                SeedService.ensure_global_email_templates(self.db)
                template = email_service.resolve_template_for_org(
                    organization_id=insight.organization_id,
                    template_id=None,
                    template_key=_TEMPLATE_KEY,
                )
            except Exception:
                return 0

        recipients = self._recipients(insight.organization_id)
        narrative = insight.narrative_summary or insight.templated_narrative
        queued = 0
        for user in recipients:
            email_service.queue_email(
                organization_id=insight.organization_id,
                template=template,
                event_type="compound_insight.surfaced",
                recipient_email=user.email,
                recipient_user_id=user.id,
                priority="high",
                scheduled_at=None,
                metadata_json={"source": "compound_insight", "severity": insight.severity},
                created_by_user_id=user.id,  # system-generated; self-attributed to satisfy FK
                variables_json={
                    "user_name": user.full_name or user.email,
                    "insight_title": insight.title,
                    "severity": insight.severity,
                    "narrative": narrative,
                },
                initial_status="pending",
                notification_type=_NOTIFICATION_TYPE,
                severity=insight.severity,
            )
            queued += 1
        return queued
