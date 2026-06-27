import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.issue import Issue
from app.models.issue_policy_link import IssuePolicyLink
from app.services.audit_service import AuditService


class IssuePolicyLinkService:
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

    def _require_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> CompliancePolicy:
        row = self.db.execute(
            select(CompliancePolicy).where(
                CompliancePolicy.organization_id == org_id,
                CompliancePolicy.id == policy_id,
                CompliancePolicy.status != "archived",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance policy not found")
        return row

    def link_issue_to_policy(
        self,
        org_id: uuid.UUID,
        issue_id: uuid.UUID,
        policy_id: uuid.UUID,
        link_type: str,
        linked_by: uuid.UUID,
    ) -> IssuePolicyLink:
        self._require_issue(org_id, issue_id)
        self._require_policy(org_id, policy_id)

        duplicate = self.db.execute(
            select(IssuePolicyLink).where(
                IssuePolicyLink.organization_id == org_id,
                IssuePolicyLink.issue_id == issue_id,
                IssuePolicyLink.policy_id == policy_id,
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Issue-policy link already exists")

        row = IssuePolicyLink(
            organization_id=org_id,
            issue_id=issue_id,
            policy_id=policy_id,
            link_type=link_type,
            linked_by=linked_by,
            linked_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="issue_policy_link.created",
            entity_type="issue_policy_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=linked_by,
            after_json={
                "issue_id": str(row.issue_id),
                "policy_id": str(row.policy_id),
                "link_type": row.link_type,
            },
            metadata_json={"source": "api"},
        )
        return row

    def unlink_issue_from_policy(
        self,
        org_id: uuid.UUID,
        issue_id: uuid.UUID,
        policy_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        row = self.db.execute(
            select(IssuePolicyLink).where(
                IssuePolicyLink.organization_id == org_id,
                IssuePolicyLink.issue_id == issue_id,
                IssuePolicyLink.policy_id == policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue-policy link not found")

        entity_id = row.id
        self.db.delete(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="issue_policy_link.removed",
            entity_type="issue_policy_link",
            entity_id=entity_id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"issue_id": str(issue_id), "policy_id": str(policy_id)},
            metadata_json={"source": "api"},
        )

    def get_issue_policy_links(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> list[IssuePolicyLink]:
        self._require_issue(org_id, issue_id)
        return self.db.execute(
            select(IssuePolicyLink)
            .where(
                IssuePolicyLink.organization_id == org_id,
                IssuePolicyLink.issue_id == issue_id,
            )
            .order_by(IssuePolicyLink.linked_at.desc())
        ).scalars().all()

    def get_policy_associated_issues(
        self,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        link_type: str | None = None,
    ) -> list[dict]:
        policy = self._require_policy(org_id, policy_id)
        _ = policy
        stmt = (
            select(IssuePolicyLink, Issue)
            .join(Issue, Issue.id == IssuePolicyLink.issue_id)
            .where(
                IssuePolicyLink.organization_id == org_id,
                IssuePolicyLink.policy_id == policy_id,
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
            )
            .order_by(IssuePolicyLink.linked_at.desc())
        )
        if link_type is not None:
            stmt = stmt.where(IssuePolicyLink.link_type == link_type)

        rows = self.db.execute(stmt).all()
        return [
            {
                "issue_id": issue.id,
                "title": issue.title,
                "severity": issue.severity,
                "status": issue.status,
                "link_type": link.link_type,
                "linked_at": link.linked_at,
            }
            for link, issue in rows
        ]

    def get_policy_violation_rate(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> dict:
        policy = self._require_policy(org_id, policy_id)
        since = self.utcnow() - timedelta(days=365)

        total_issues = int(
            self.db.execute(
                select(func.count(Issue.id)).where(
                    Issue.organization_id == org_id,
                    Issue.deleted_at.is_(None),
                    Issue.created_at >= since,
                )
            ).scalar_one()
        )

        violations = int(
            self.db.execute(
                select(func.count(func.distinct(IssuePolicyLink.issue_id)))
                .join(Issue, Issue.id == IssuePolicyLink.issue_id)
                .where(
                    IssuePolicyLink.organization_id == org_id,
                    IssuePolicyLink.policy_id == policy_id,
                    IssuePolicyLink.link_type == "violated",
                    Issue.organization_id == org_id,
                    Issue.deleted_at.is_(None),
                    Issue.created_at >= since,
                )
            ).scalar_one()
        )

        rate = round((violations / total_issues) * 100.0, 2) if total_issues else 0.0
        return {
            "policy_id": policy.id,
            "policy_name": policy.title,
            "total_issues_past_12m": total_issues,
            "violations_past_12m": violations,
            "violation_rate": rate,
        }

    def get_policy_violation_counts(self, org_id: uuid.UUID, policy_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not policy_ids:
            return {}
        since = self.utcnow() - timedelta(days=365)
        rows = self.db.execute(
            select(IssuePolicyLink.policy_id, func.count(func.distinct(IssuePolicyLink.issue_id)))
            .join(Issue, Issue.id == IssuePolicyLink.issue_id)
            .where(
                IssuePolicyLink.organization_id == org_id,
                IssuePolicyLink.policy_id.in_(policy_ids),
                IssuePolicyLink.link_type == "violated",
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
                Issue.created_at >= since,
            )
            .group_by(IssuePolicyLink.policy_id)
        ).all()
        return {policy_id: int(count) for policy_id, count in rows}
