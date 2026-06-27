import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.engines.remediation_engine import RemediationEngine
from app.models.control import Control
from app.models.issue import Issue
from app.models.issue_control_link import IssueControlLink
from app.models.remediation_suggestion import RemediationSuggestion
from app.models.task import Task
from app.services.audit_service import AuditService


class RemediationService:
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

    def _get_suggestion(self, org_id: uuid.UUID, suggestion_id: uuid.UUID) -> RemediationSuggestion:
        row = self.db.execute(
            select(RemediationSuggestion).where(
                RemediationSuggestion.organization_id == org_id,
                RemediationSuggestion.id == suggestion_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Remediation suggestion not found")
        return row

    def _linked_controls(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> list[Control]:
        rows = self.db.execute(
            select(Control)
            .join(IssueControlLink, IssueControlLink.control_id == Control.id)
            .where(
                IssueControlLink.organization_id == org_id,
                IssueControlLink.issue_id == issue_id,
                IssueControlLink.deleted_at.is_(None),
                Control.organization_id == org_id,
            )
            .order_by(IssueControlLink.linked_at.asc())
        ).scalars().all()
        return rows

    def generate_suggestions(self, org_id: uuid.UUID, issue_id: uuid.UUID, user_id: uuid.UUID) -> list[RemediationSuggestion]:
        issue = self._get_issue(org_id, issue_id)
        controls = self._linked_controls(org_id, issue_id)
        suggestions = RemediationEngine.generate(issue, controls, self.db)
        source_key = RemediationEngine.resolve_source_key(issue, controls)

        for text in suggestions:
            existing = self.db.execute(
                select(RemediationSuggestion).where(
                    RemediationSuggestion.organization_id == org_id,
                    RemediationSuggestion.issue_id == issue_id,
                    RemediationSuggestion.suggestion_text == text,
                )
            ).scalar_one_or_none()
            if existing is None:
                self.db.add(
                    RemediationSuggestion(
                        organization_id=org_id,
                        issue_id=issue_id,
                        suggestion_text=text,
                        suggestion_source="rule_based",
                        source_key=source_key,
                        applied=False,
                        dismissed=False,
                    )
                )

        self.db.flush()
        rows = self.list_suggestions(org_id, issue_id)

        AuditService(self.db).write_audit_log(
            action="remediation.generated",
            entity_type="issue",
            entity_id=issue.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"suggestion_count": len(rows), "source_key": source_key},
            metadata_json={"source": "api"},
        )
        return rows

    def list_suggestions(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> list[RemediationSuggestion]:
        self._get_issue(org_id, issue_id)
        return self.db.execute(
            select(RemediationSuggestion)
            .where(
                RemediationSuggestion.organization_id == org_id,
                RemediationSuggestion.issue_id == issue_id,
            )
            .order_by(RemediationSuggestion.created_at.asc())
        ).scalars().all()

    def apply_suggestion(self, org_id: uuid.UUID, suggestion_id: uuid.UUID, user_id: uuid.UUID) -> RemediationSuggestion:
        row = self._get_suggestion(org_id, suggestion_id)
        issue = self._get_issue(org_id, row.issue_id)

        row.applied = True
        row.dismissed = False

        task = Task(
            organization_id=org_id,
            title=row.suggestion_text[:100],
            description=row.suggestion_text,
            status="open",
            priority="normal",
            task_type="general",
            owner_user_id=issue.owner_id,
            created_by_user_id=user_id,
            linked_entity_type="issue",
            linked_entity_id=issue.id,
            source="automation",
            reminder_status="none",
            metadata_json={"remediation_suggestion_id": str(row.id)},
        )
        self.db.add(task)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="remediation.applied",
            entity_type="remediation_suggestion",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"task_id": str(task.id), "applied": row.applied},
            metadata_json={"source": "api"},
        )
        return row

    def dismiss_suggestion(self, org_id: uuid.UUID, suggestion_id: uuid.UUID, user_id: uuid.UUID) -> RemediationSuggestion:
        row = self._get_suggestion(org_id, suggestion_id)
        row.dismissed = True
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="remediation.dismissed",
            entity_type="remediation_suggestion",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"dismissed": row.dismissed},
            metadata_json={"source": "api"},
        )
        return row
