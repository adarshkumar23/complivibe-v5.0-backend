import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.email_outbox import EmailOutbox
from app.models.issue import Issue
from app.models.issue_sla_policy import IssueSLAPolicy
from app.models.issue_sla_tracking import IssueSLATracking
from app.models.user import User
from app.services.audit_service import AuditService


class SLAService:
    DEFAULT_POLICIES: dict[str, tuple[int, int]] = {
        "critical": (1, 24),
        "high": (4, 72),
        "medium": (24, 168),
        "low": (72, 720),
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _remaining_hours(deadline: datetime, now: datetime) -> float:
        comparable_now = now if deadline.tzinfo is not None else now.replace(tzinfo=None)
        return round((deadline - comparable_now).total_seconds() / 3600.0, 2)

    def _queue_escalation(self, issue: Issue, *, breach_type: str) -> int:
        owner = self.db.execute(select(User).where(User.id == issue.owner_id)).scalar_one_or_none()
        if owner is None or not owner.email:
            return 0

        now = self.utcnow()
        self.db.add(
            EmailOutbox(
                organization_id=issue.organization_id,
                template_id=None,
                event_type=f"issue_sla.{breach_type}",
                recipient_email=owner.email,
                recipient_user_id=owner.id,
                subject=f"Issue SLA breach: {issue.title}",
                body_text=(
                    f"Issue SLA breach detected.\n"
                    f"Issue: {issue.title}\n"
                    f"Severity: {issue.severity}\n"
                    f"Breach type: {breach_type}\n"
                ),
                body_html=None,
                status="pending",
                priority="high",
                scheduled_at=None,
                queued_at=now,
                attempt_count=0,
                max_attempts=3,
                metadata_json={
                    "source": "issue_sla",
                    "issue_id": str(issue.id),
                    "breach_type": breach_type,
                },
                created_by_user_id=issue.created_by,
            )
        )
        return 1

    def _policy_hours(self, org_id: uuid.UUID, severity: str) -> tuple[int, int]:
        policy = self.db.execute(
            select(IssueSLAPolicy).where(
                IssueSLAPolicy.organization_id == org_id,
                IssueSLAPolicy.severity == severity,
            )
        ).scalar_one_or_none()
        if policy is not None:
            return int(policy.response_sla_hours), int(policy.resolution_sla_hours)
        return self.DEFAULT_POLICIES.get(severity, self.DEFAULT_POLICIES["medium"])

    def ensure_default_policies(self, org_id: uuid.UUID) -> list[IssueSLAPolicy]:
        rows: list[IssueSLAPolicy] = []
        for severity, (response_hours, resolution_hours) in self.DEFAULT_POLICIES.items():
            row = self.db.execute(
                select(IssueSLAPolicy).where(
                    IssueSLAPolicy.organization_id == org_id,
                    IssueSLAPolicy.severity == severity,
                )
            ).scalar_one_or_none()
            if row is None:
                row = IssueSLAPolicy(
                    organization_id=org_id,
                    severity=severity,
                    response_sla_hours=response_hours,
                    resolution_sla_hours=resolution_hours,
                )
                self.db.add(row)
                self.db.flush()
            rows.append(row)
        return rows

    def initialize_tracking_for_issue(self, issue: Issue) -> IssueSLATracking:
        existing = self.db.execute(
            select(IssueSLATracking).where(
                IssueSLATracking.organization_id == issue.organization_id,
                IssueSLATracking.issue_id == issue.id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        response_hours, resolution_hours = self._policy_hours(issue.organization_id, issue.severity)
        created_at = issue.created_at
        response_deadline = created_at + timedelta(hours=response_hours)
        resolution_deadline = created_at + timedelta(hours=resolution_hours)

        row = IssueSLATracking(
            organization_id=issue.organization_id,
            issue_id=issue.id,
            response_deadline=response_deadline,
            resolution_deadline=resolution_deadline,
            response_met_at=None,
            resolution_met_at=None,
            response_breached=False,
            resolution_breached=False,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def mark_response_met(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(IssueSLATracking).where(
                IssueSLATracking.organization_id == org_id,
                IssueSLATracking.issue_id == issue_id,
            )
        ).scalar_one_or_none()
        if row is None or row.response_breached or row.response_met_at is not None:
            return
        row.response_met_at = self.utcnow()
        self.db.flush()

    def mark_resolution_met(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(IssueSLATracking).where(
                IssueSLATracking.organization_id == org_id,
                IssueSLATracking.issue_id == issue_id,
            )
        ).scalar_one_or_none()
        if row is None or row.resolution_breached or row.resolution_met_at is not None:
            return
        row.resolution_met_at = self.utcnow()
        self.db.flush()

    def get_sla_status(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> dict:
        issue = self.db.execute(
            select(Issue).where(
                Issue.organization_id == org_id,
                Issue.id == issue_id,
                Issue.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if issue is None:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

        tracking = self.db.execute(
            select(IssueSLATracking).where(
                IssueSLATracking.organization_id == org_id,
                IssueSLATracking.issue_id == issue_id,
            )
        ).scalar_one_or_none()
        if tracking is None:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue SLA tracking not found")

        # The frozen deadlines recorded at issue creation are authoritative.
        # Derive the effective SLA hours from them so the payload is internally
        # consistent even if the organization's live SLA policy is later changed.
        created_at = issue.created_at
        response_hours = int((tracking.response_deadline - created_at).total_seconds() / 3600)
        resolution_hours = int((tracking.resolution_deadline - created_at).total_seconds() / 3600)
        now = self.utcnow()

        response_remaining_hours: float | None
        if tracking.response_met_at is not None or tracking.response_breached:
            response_remaining_hours = None
        else:
            response_remaining_hours = self._remaining_hours(tracking.response_deadline, now)

        resolution_remaining_hours: float | None
        if tracking.resolution_met_at is not None or tracking.resolution_breached:
            resolution_remaining_hours = None
        else:
            resolution_remaining_hours = self._remaining_hours(tracking.resolution_deadline, now)

        return {
            "issue_id": issue.id,
            "severity": issue.severity,
            "response_deadline": tracking.response_deadline,
            "resolution_deadline": tracking.resolution_deadline,
            "response_met_at": tracking.response_met_at,
            "resolution_met_at": tracking.resolution_met_at,
            "response_breached": tracking.response_breached,
            "resolution_breached": tracking.resolution_breached,
            "response_sla_hours": response_hours,
            "resolution_sla_hours": resolution_hours,
            "response_remaining_hours": response_remaining_hours,
            "resolution_remaining_hours": resolution_remaining_hours,
        }

    def get_sla_breaches(self, org_id: uuid.UUID) -> list[dict]:
        rows = self.db.execute(
            select(IssueSLATracking, Issue)
            .join(Issue, Issue.id == IssueSLATracking.issue_id)
            .where(
                IssueSLATracking.organization_id == org_id,
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
                or_(IssueSLATracking.response_breached.is_(True), IssueSLATracking.resolution_breached.is_(True)),
            )
            .order_by(IssueSLATracking.resolution_deadline.asc())
        ).all()

        payload: list[dict] = []
        for tracking, issue in rows:
            payload.append(
                {
                    "issue_id": issue.id,
                    "title": issue.title,
                    "severity": issue.severity,
                    "status": issue.status,
                    "owner_id": issue.owner_id,
                    "response_deadline": tracking.response_deadline,
                    "resolution_deadline": tracking.resolution_deadline,
                    "response_breached": tracking.response_breached,
                    "resolution_breached": tracking.resolution_breached,
                    "response_met_at": tracking.response_met_at,
                    "resolution_met_at": tracking.resolution_met_at,
                }
            )
        return payload

    def check_sla_breaches(self, org_id: uuid.UUID) -> dict[str, int]:
        now = self.utcnow()
        response_breached = 0
        resolution_breached = 0
        notifications_queued = 0

        response_rows = self.db.execute(
            select(IssueSLATracking, Issue)
            .join(Issue, Issue.id == IssueSLATracking.issue_id)
            .where(
                IssueSLATracking.organization_id == org_id,
                Issue.organization_id == org_id,
                IssueSLATracking.response_deadline < now,
                IssueSLATracking.response_breached.is_(False),
                IssueSLATracking.response_met_at.is_(None),
                Issue.status == "open",
                Issue.deleted_at.is_(None),
            )
        ).all()

        for tracking, issue in response_rows:
            tracking.response_breached = True
            notifications_queued += self._queue_escalation(issue, breach_type="response_breached")
            AuditService(self.db).write_audit_log(
                action="sla.response_breached",
                entity_type="issue",
                entity_id=issue.id,
                organization_id=issue.organization_id,
                actor_user_id=None,
                after_json={
                    "response_breached": True,
                    "response_deadline": tracking.response_deadline.isoformat(),
                },
                metadata_json={"source": "scheduler"},
            )
            response_breached += 1

        resolution_rows = self.db.execute(
            select(IssueSLATracking, Issue)
            .join(Issue, Issue.id == IssueSLATracking.issue_id)
            .where(
                IssueSLATracking.organization_id == org_id,
                Issue.organization_id == org_id,
                IssueSLATracking.resolution_deadline < now,
                IssueSLATracking.resolution_breached.is_(False),
                IssueSLATracking.resolution_met_at.is_(None),
                Issue.status.notin_(["resolved", "closed"]),
                Issue.deleted_at.is_(None),
            )
        ).all()

        for tracking, issue in resolution_rows:
            tracking.resolution_breached = True
            notifications_queued += self._queue_escalation(issue, breach_type="resolution_breached")
            AuditService(self.db).write_audit_log(
                action="sla.resolution_breached",
                entity_type="issue",
                entity_id=issue.id,
                organization_id=issue.organization_id,
                actor_user_id=None,
                after_json={
                    "resolution_breached": True,
                    "resolution_deadline": tracking.resolution_deadline.isoformat(),
                },
                metadata_json={"source": "scheduler"},
            )
            resolution_breached += 1

        self.db.flush()
        return {
            "response_breached": response_breached,
            "resolution_breached": resolution_breached,
            "notifications_queued": notifications_queued,
        }

    def get_sla_policies(self, org_id: uuid.UUID) -> list[IssueSLAPolicy]:
        return self.db.execute(
            select(IssueSLAPolicy)
            .where(IssueSLAPolicy.organization_id == org_id)
            .order_by(IssueSLAPolicy.severity.asc())
        ).scalars().all()

    def create_or_update_sla_policy(
        self,
        org_id: uuid.UUID,
        severity: str,
        response_hours: int,
        resolution_hours: int,
        user_id: uuid.UUID,
    ) -> IssueSLAPolicy:
        row = self.db.execute(
            select(IssueSLAPolicy).where(
                IssueSLAPolicy.organization_id == org_id,
                IssueSLAPolicy.severity == severity,
            )
        ).scalar_one_or_none()

        if row is None:
            row = IssueSLAPolicy(
                organization_id=org_id,
                severity=severity,
                response_sla_hours=int(response_hours),
                resolution_sla_hours=int(resolution_hours),
            )
            self.db.add(row)
        else:
            row.response_sla_hours = int(response_hours)
            row.resolution_sla_hours = int(resolution_hours)

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="sla_policy.updated",
            entity_type="issue_sla_policy",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "severity": row.severity,
                "response_sla_hours": int(row.response_sla_hours),
                "resolution_sla_hours": int(row.resolution_sla_hours),
            },
            metadata_json={"source": "api"},
        )
        return row

    def update_issue_dashboard_with_sla(self, org_id: uuid.UUID) -> dict:
        overdue_count = int(
            self.db.execute(
                select(func.count(IssueSLATracking.id))
                .join(Issue, Issue.id == IssueSLATracking.issue_id)
                .where(
                    IssueSLATracking.organization_id == org_id,
                    Issue.organization_id == org_id,
                    Issue.deleted_at.is_(None),
                    IssueSLATracking.resolution_breached.is_(True),
                    Issue.status.notin_(["resolved", "closed"]),
                )
            ).scalar_one()
        )
        return {"overdue_count": overdue_count}


def run_hourly_issue_sla_breach_check(db: Session, org_id: uuid.UUID) -> dict[str, int]:
    return SLAService(db).check_sla_breaches(org_id)
