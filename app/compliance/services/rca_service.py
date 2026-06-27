import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.models.root_cause_analysis import RootCauseAnalysis
from app.services.audit_service import AuditService


class RCAService:
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

    def has_rca(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> bool:
        row = self.db.execute(
            select(RootCauseAnalysis.id).where(
                RootCauseAnalysis.organization_id == org_id,
                RootCauseAnalysis.issue_id == issue_id,
            )
        ).scalar_one_or_none()
        return row is not None

    def create_rca(self, org_id: uuid.UUID, issue_id: uuid.UUID, data, authored_by: uuid.UUID) -> RootCauseAnalysis:
        issue = self._get_issue(org_id, issue_id)
        if issue.status not in {"resolved", "closed"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="RCA can only be created for resolved or closed issues.",
            )

        existing = self.db.execute(
            select(RootCauseAnalysis).where(
                RootCauseAnalysis.organization_id == org_id,
                RootCauseAnalysis.issue_id == issue_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RCA already exists for this issue")

        row = RootCauseAnalysis(
            organization_id=org_id,
            issue_id=issue_id,
            summary=data.summary,
            timeline_description=data.timeline_description,
            root_cause=data.root_cause,
            contributing_factors=list(data.contributing_factors or []),
            corrective_actions=list(data.corrective_actions or []),
            preventive_measures=list(data.preventive_measures or []),
            authored_by=authored_by,
            reviewed_by=None,
            reviewed_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="rca.created",
            entity_type="root_cause_analysis",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=authored_by,
            after_json={"issue_id": str(issue_id)},
            metadata_json={"source": "api"},
        )
        return row

    def get_rca(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> RootCauseAnalysis:
        _ = self._get_issue(org_id, issue_id)
        row = self.db.execute(
            select(RootCauseAnalysis).where(
                RootCauseAnalysis.organization_id == org_id,
                RootCauseAnalysis.issue_id == issue_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RCA not found")
        return row

    def update_rca(self, org_id: uuid.UUID, issue_id: uuid.UUID, data, actor_user_id: uuid.UUID | None = None) -> RootCauseAnalysis:
        row = self.get_rca(org_id, issue_id)
        if row.reviewed_by is not None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Reviewed RCA cannot be edited")

        before = {
            "summary": row.summary,
            "timeline_description": row.timeline_description,
            "root_cause": row.root_cause,
        }

        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(row, field, value)

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="rca.updated",
            entity_type="root_cause_analysis",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={
                "summary": row.summary,
                "timeline_description": row.timeline_description,
                "root_cause": row.root_cause,
            },
            metadata_json={"source": "api"},
        )
        return row

    def review_rca(self, org_id: uuid.UUID, issue_id: uuid.UUID, reviewer_id: uuid.UUID) -> RootCauseAnalysis:
        row = self.get_rca(org_id, issue_id)
        if row.reviewed_by is not None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="RCA is already reviewed")
        if row.authored_by == reviewer_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="RCA author cannot self-review")

        row.reviewed_by = reviewer_id
        row.reviewed_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="rca.reviewed",
            entity_type="root_cause_analysis",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=reviewer_id,
            after_json={"reviewed_by": str(row.reviewed_by), "reviewed_at": row.reviewed_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row
