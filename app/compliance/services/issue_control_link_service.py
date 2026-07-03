import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.issue import Issue
from app.models.issue_control_link import IssueControlLink
from app.services.audit_service import AuditService


class IssueControlLinkService:
    FAILURE_TYPES = ("control_failed", "control_bypassed", "control_ineffective", "control_absent")

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> Issue:
        row = self.db.execute(
            select(Issue).where(
                Issue.organization_id == org_id,
                Issue.id == issue_id,
                Issue.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
        return row

    def _require_control(self, org_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        row = self.db.execute(
            select(Control).where(
                Control.organization_id == org_id,
                Control.id == control_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return row

    def link_issue_to_control(
        self,
        org_id: uuid.UUID,
        issue_id: uuid.UUID,
        control_id: uuid.UUID,
        failure_type: str,
        linked_by: uuid.UUID,
    ) -> IssueControlLink:
        self._require_issue(org_id, issue_id)
        self._require_control(org_id, control_id)

        duplicate = self.db.execute(
            select(IssueControlLink).where(
                IssueControlLink.organization_id == org_id,
                IssueControlLink.issue_id == issue_id,
                IssueControlLink.control_id == control_id,
                IssueControlLink.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Issue-control link already exists")

        row = IssueControlLink(
            organization_id=org_id,
            issue_id=issue_id,
            control_id=control_id,
            failure_type=failure_type,
            linked_by=linked_by,
            linked_at=self.utcnow(),
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="issue_control_link.created",
            entity_type="issue_control_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=linked_by,
            after_json={
                "issue_id": str(row.issue_id),
                "control_id": str(row.control_id),
                "failure_type": row.failure_type,
            },
            metadata_json={"source": "api"},
        )
        return row

    def unlink_issue_from_control(
        self,
        org_id: uuid.UUID,
        issue_id: uuid.UUID,
        control_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        row = self.db.execute(
            select(IssueControlLink).where(
                IssueControlLink.organization_id == org_id,
                IssueControlLink.issue_id == issue_id,
                IssueControlLink.control_id == control_id,
                IssueControlLink.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue-control link not found")

        entity_id = row.id
        self.db.delete(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="issue_control_link.removed",
            entity_type="issue_control_link",
            entity_id=entity_id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"issue_id": str(issue_id), "control_id": str(control_id)},
            metadata_json={"source": "api"},
        )

    def get_issue_control_links(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> list[IssueControlLink]:
        self._require_issue(org_id, issue_id)
        return self.db.execute(
            select(IssueControlLink)
            .where(
                IssueControlLink.organization_id == org_id,
                IssueControlLink.issue_id == issue_id,
                IssueControlLink.deleted_at.is_(None),
            )
            .order_by(IssueControlLink.linked_at.desc())
        ).scalars().all()

    def get_control_associated_issues(
        self,
        org_id: uuid.UUID,
        control_id: uuid.UUID,
        failure_type: str | None = None,
        status_value: str | None = None,
    ) -> dict:
        self._require_control(org_id, control_id)

        stmt = (
            select(IssueControlLink, Issue)
            .join(Issue, Issue.id == IssueControlLink.issue_id)
            .where(
                IssueControlLink.organization_id == org_id,
                IssueControlLink.control_id == control_id,
                IssueControlLink.deleted_at.is_(None),
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
            )
            .order_by(IssueControlLink.linked_at.desc())
        )
        if failure_type is not None:
            stmt = stmt.where(IssueControlLink.failure_type == failure_type)
        if status_value is not None:
            stmt = stmt.where(Issue.status == status_value)

        grouped: dict[str, list[dict]] = {k: [] for k in self.FAILURE_TYPES}
        for link, issue in self.db.execute(stmt).all():
            grouped.setdefault(link.failure_type, []).append(
                {
                    "issue_id": issue.id,
                    "title": issue.title,
                    "severity": issue.severity,
                    "status": issue.status,
                    "failure_type": link.failure_type,
                    "linked_at": link.linked_at,
                }
            )
        return {"control_id": control_id, "grouped": grouped}

    def get_control_failure_rate(self, org_id: uuid.UUID, control_id: uuid.UUID) -> dict:
        control = self._require_control(org_id, control_id)

        earliest_issue_created_at = self.db.execute(
            select(func.min(Issue.created_at)).where(
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

        now = self.utcnow()
        if earliest_issue_created_at is None:
            active_months = 1
        else:
            # Keep failure-rate windows stable in tests/runs by using a rolling 30-day month bucket.
            delta_days = max(0, int((now.date() - earliest_issue_created_at.date()).days))
            active_months = max(1, int(delta_days // 30) + 1)

        by_type_rows = self.db.execute(
            select(IssueControlLink.failure_type, func.count(IssueControlLink.id))
            .join(Issue, Issue.id == IssueControlLink.issue_id)
            .where(
                IssueControlLink.organization_id == org_id,
                IssueControlLink.control_id == control_id,
                IssueControlLink.deleted_at.is_(None),
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
            )
            .group_by(IssueControlLink.failure_type)
        ).all()
        by_failure_type = {k: 0 for k in self.FAILURE_TYPES}
        for failure_type, count in by_type_rows:
            by_failure_type[str(failure_type)] = int(count)

        total_failures = int(
            self.db.execute(
                select(func.count(IssueControlLink.id))
                .join(Issue, Issue.id == IssueControlLink.issue_id)
                .where(
                    IssueControlLink.organization_id == org_id,
                    IssueControlLink.control_id == control_id,
                    IssueControlLink.deleted_at.is_(None),
                    IssueControlLink.failure_type != "control_absent",
                    Issue.organization_id == org_id,
                    Issue.deleted_at.is_(None),
                )
            ).scalar_one()
        )

        open_high_critical_count = int(
            self.db.execute(
                select(func.count(func.distinct(Issue.id)))
                .join(IssueControlLink, IssueControlLink.issue_id == Issue.id)
                .where(
                    IssueControlLink.organization_id == org_id,
                    IssueControlLink.control_id == control_id,
                    IssueControlLink.deleted_at.is_(None),
                    Issue.organization_id == org_id,
                    Issue.deleted_at.is_(None),
                    Issue.severity.in_(["high", "critical"]),
                    Issue.status.not_in(["resolved", "closed"]),
                )
            ).scalar_one()
        )

        failure_rate = round((total_failures / active_months), 2) if active_months else 0.0
        return {
            "control_id": control.id,
            "control_name": control.title,
            "active_months": active_months,
            "total_failures": total_failures,
            "failure_rate": failure_rate,
            "by_failure_type": by_failure_type,
            "open_high_critical_count": open_high_critical_count,
        }
