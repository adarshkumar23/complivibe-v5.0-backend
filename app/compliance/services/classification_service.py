import uuid
from collections import Counter
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.engines.classification_engine import ClassificationEngine
from app.models.email_outbox import EmailOutbox
from app.models.incident_classification import IncidentClassification
from app.models.issue import Issue
from app.models.user import User
from app.services.audit_service import AuditService


class ClassificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _get_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> Issue:
        issue = self.db.execute(
            select(Issue).where(
                Issue.organization_id == org_id,
                Issue.id == issue_id,
                Issue.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if issue is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
        return issue

    def get_classification(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> IncidentClassification | None:
        return self.db.execute(
            select(IncidentClassification).where(
                IncidentClassification.organization_id == org_id,
                IncidentClassification.issue_id == issue_id,
            )
        ).scalar_one_or_none()

    def _queue_breach_feed_reminder(self, issue: Issue, implications: list[str]) -> bool:
        if not ({"gdpr_72hr", "dpdp_72hr"} & set(implications)):
            return False
        if issue.issue_type not in {"data_loss", "unauthorized_access", "security_incident"}:
            return False

        owner = self.db.execute(select(User).where(User.id == issue.owner_id)).scalar_one_or_none()
        if owner is None or not owner.email:
            return False

        now = self.utcnow()
        self.db.add(
            EmailOutbox(
                organization_id=issue.organization_id,
                template_id=None,
                event_type="classification.breach_notification_feed",
                recipient_email=owner.email,
                recipient_user_id=owner.id,
                subject=f"Breach notification review suggested for issue: {issue.title}",
                body_text=(
                    f"Issue '{issue.title}' has regulatory implications: {', '.join(implications)}. "
                    "Review and consider creating a breach notification at "
                    f"POST /api/v1/compliance/issues/{issue.id}/breach-notification."
                ),
                body_html=None,
                status="pending",
                priority="high",
                scheduled_at=None,
                queued_at=now,
                attempt_count=0,
                max_attempts=3,
                metadata_json={"issue_id": str(issue.id), "source": "classification_feed"},
                created_by_user_id=None,
            )
        )
        return True

    def auto_classify(self, org_id: uuid.UUID, issue_id: uuid.UUID, user_id: uuid.UUID) -> IncidentClassification:
        issue = self._get_issue(org_id, issue_id)
        payload = ClassificationEngine.classify(issue.issue_type, issue.severity)
        implications = [str(x) for x in payload.get("regulatory_implications", [])]
        notification_required = len(implications) > 0
        now = self.utcnow()

        row = self.get_classification(org_id, issue_id)
        if row is None:
            row = IncidentClassification(
                organization_id=org_id,
                issue_id=issue_id,
                classified_issue_type=issue.issue_type,
                classified_severity=issue.severity,
                category=str(payload["category"]),
                sub_category=str(payload.get("sub_category") or "") or None,
                regulatory_implications=implications,
                notification_required=notification_required,
                auto_classified=True,
                classification_by=user_id,
                classified_at=now,
                last_updated_at=now,
            )
            self.db.add(row)
        else:
            row.classified_issue_type = issue.issue_type
            row.classified_severity = issue.severity
            row.category = str(payload["category"])
            row.sub_category = str(payload.get("sub_category") or "") or None
            row.regulatory_implications = implications
            row.notification_required = notification_required
            row.auto_classified = True
            row.classification_by = user_id
            row.last_updated_at = now

        queued = self._queue_breach_feed_reminder(issue, implications)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="classification.auto_classified",
            entity_type="incident_classification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "issue_id": str(issue_id),
                "category": row.category,
                "notification_required": row.notification_required,
                "outbox_queued": queued,
            },
            metadata_json={"source": "api"},
        )
        return row

    def override_classification(self, org_id: uuid.UUID, issue_id: uuid.UUID, data, user_id: uuid.UUID) -> IncidentClassification:
        issue = self._get_issue(org_id, issue_id)
        row = self.get_classification(org_id, issue_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident classification not found")

        row.classified_issue_type = issue.issue_type
        row.classified_severity = issue.severity
        row.category = data.category
        row.sub_category = data.sub_category
        row.regulatory_implications = list(data.regulatory_implications or [])
        row.notification_required = len(row.regulatory_implications) > 0
        row.auto_classified = False
        row.classification_by = user_id
        row.last_updated_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="classification.overridden",
            entity_type="incident_classification",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={
                "issue_id": str(issue_id),
                "category": row.category,
                "notification_required": row.notification_required,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_incidents_by_category(self, org_id: uuid.UUID, category: str | None = None) -> dict:
        stmt = select(IncidentClassification).where(IncidentClassification.organization_id == org_id)
        if category is not None:
            stmt = stmt.where(IncidentClassification.category == category)
        rows = self.db.execute(stmt).scalars().all()

        by_category = Counter(row.category for row in rows)
        notification_required_count = sum(1 for row in rows if row.notification_required)

        reg_counter: Counter[str] = Counter()
        for row in rows:
            for implication in row.regulatory_implications or []:
                reg_counter[str(implication)] += 1

        return {
            "total_classified": len(rows),
            "by_category": {k: int(v) for k, v in by_category.items()},
            "notification_required_count": int(notification_required_count),
            "regulatory_breakdown": {k: int(v) for k, v in reg_counter.items()},
        }
