import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.issue import Issue
from app.models.issue_policy_link import IssuePolicyLink
from app.models.policy_issue_link import PolicyIssueLink
from app.models.task import Task
from app.schemas.policy_issue_link import PolicyIssueLinkUpdate
from app.services.audit_service import AuditService


class PolicyIssueLinkService:
    OPEN_ISSUE_STATUSES = {"open", "in_progress", "blocked"}
    RESOLVED_ISSUE_STATUSES = {"completed", "cancelled", "archived"}
    VIOLATION_TYPES = ("violation", "near_miss", "observation", "procedural_gap")
    SEVERITY_IMPACTS = ("low", "medium", "high", "critical")

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def issue_severity(issue: Task) -> str:
        mapping = {
            "low": "low",
            "normal": "medium",
            "high": "high",
            "urgent": "critical",
        }
        return mapping.get(str(issue.priority), "medium")

    def require_policy_in_org(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> CompliancePolicy:
        row = self.db.execute(
            select(CompliancePolicy).where(
                CompliancePolicy.organization_id == org_id,
                CompliancePolicy.id == policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance policy not found")
        return row

    def require_issue_in_org(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> Task:
        row = self.db.execute(
            select(Task).where(
                Task.organization_id == org_id,
                Task.id == issue_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
        return row

    def require_link(self, org_id: uuid.UUID, link_id: uuid.UUID) -> PolicyIssueLink:
        row = self.db.execute(
            select(PolicyIssueLink).where(
                PolicyIssueLink.organization_id == org_id,
                PolicyIssueLink.id == link_id,
                PolicyIssueLink.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy-issue link not found")
        return row

    def create_link(
        self,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        issue_id: uuid.UUID,
        violation_type: str,
        severity_impact: str,
        notes: str | None,
        linked_by: uuid.UUID,
    ) -> PolicyIssueLink:
        self.require_policy_in_org(org_id, policy_id)
        self.require_issue_in_org(org_id, issue_id)

        duplicate = self.db.execute(
            select(PolicyIssueLink).where(
                PolicyIssueLink.organization_id == org_id,
                PolicyIssueLink.policy_id == policy_id,
                PolicyIssueLink.issue_id == issue_id,
                PolicyIssueLink.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Policy-issue link already exists")

        row = PolicyIssueLink(
            organization_id=org_id,
            policy_id=policy_id,
            issue_id=issue_id,
            violation_type=violation_type,
            severity_impact=severity_impact,
            notes=notes,
            linked_by=linked_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_issue_link.created",
            entity_type="policy_issue_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=linked_by,
            after_json={
                "policy_id": str(row.policy_id),
                "issue_id": str(row.issue_id),
                "violation_type": row.violation_type,
                "severity_impact": row.severity_impact,
                "notes": row.notes,
            },
            metadata_json={"source": "api"},
        )

        return row

    def list_links_for_policy(
        self,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        violation_type: str | None = None,
        severity_impact: str | None = None,
    ) -> list[tuple[PolicyIssueLink, Task]]:
        self.require_policy_in_org(org_id, policy_id)
        stmt = (
            select(PolicyIssueLink, Task)
            .join(Task, Task.id == PolicyIssueLink.issue_id)
            .where(
                PolicyIssueLink.organization_id == org_id,
                PolicyIssueLink.policy_id == policy_id,
                PolicyIssueLink.deleted_at.is_(None),
            )
        )
        if violation_type is not None:
            stmt = stmt.where(PolicyIssueLink.violation_type == violation_type)
        if severity_impact is not None:
            stmt = stmt.where(PolicyIssueLink.severity_impact == severity_impact)

        return self.db.execute(stmt.order_by(PolicyIssueLink.created_at.desc())).all()

    def list_links_for_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> list[tuple[PolicyIssueLink, CompliancePolicy]]:
        self.require_issue_in_org(org_id, issue_id)
        stmt = (
            select(PolicyIssueLink, CompliancePolicy)
            .join(CompliancePolicy, CompliancePolicy.id == PolicyIssueLink.policy_id)
            .where(
                PolicyIssueLink.organization_id == org_id,
                PolicyIssueLink.issue_id == issue_id,
                PolicyIssueLink.deleted_at.is_(None),
            )
        )
        return self.db.execute(stmt.order_by(PolicyIssueLink.created_at.desc())).all()

    def list_links(
        self,
        org_id: uuid.UUID,
        *,
        policy_id: uuid.UUID | None = None,
        issue_id: uuid.UUID | None = None,
        violation_type: str | None = None,
        severity_impact: str | None = None,
    ) -> list[tuple[PolicyIssueLink, CompliancePolicy, Task]]:
        stmt = (
            select(PolicyIssueLink, CompliancePolicy, Task)
            .join(CompliancePolicy, CompliancePolicy.id == PolicyIssueLink.policy_id)
            .join(Task, Task.id == PolicyIssueLink.issue_id)
            .where(
                PolicyIssueLink.organization_id == org_id,
                PolicyIssueLink.deleted_at.is_(None),
            )
        )
        if policy_id is not None:
            self.require_policy_in_org(org_id, policy_id)
            stmt = stmt.where(PolicyIssueLink.policy_id == policy_id)
        if issue_id is not None:
            self.require_issue_in_org(org_id, issue_id)
            stmt = stmt.where(PolicyIssueLink.issue_id == issue_id)
        if violation_type is not None:
            stmt = stmt.where(PolicyIssueLink.violation_type == violation_type)
        if severity_impact is not None:
            stmt = stmt.where(PolicyIssueLink.severity_impact == severity_impact)

        return self.db.execute(stmt.order_by(PolicyIssueLink.created_at.desc())).all()

    def get_link(self, org_id: uuid.UUID, link_id: uuid.UUID) -> tuple[PolicyIssueLink, CompliancePolicy, Task]:
        row = self.require_link(org_id, link_id)
        policy = self.require_policy_in_org(org_id, row.policy_id)
        issue = self.require_issue_in_org(org_id, row.issue_id)
        return row, policy, issue

    def update_link(
        self,
        org_id: uuid.UUID,
        link_id: uuid.UUID,
        payload: PolicyIssueLinkUpdate,
        actor_id: uuid.UUID,
    ) -> PolicyIssueLink:
        row = self.require_link(org_id, link_id)
        before = {
            "violation_type": row.violation_type,
            "severity_impact": row.severity_impact,
            "notes": row.notes,
        }

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_issue_link.updated",
            entity_type="policy_issue_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={
                "violation_type": row.violation_type,
                "severity_impact": row.severity_impact,
                "notes": row.notes,
            },
            metadata_json={"source": "api"},
        )

        return row

    def delete_link(self, org_id: uuid.UUID, link_id: uuid.UUID, actor_id: uuid.UUID) -> PolicyIssueLink:
        row = self.require_link(org_id, link_id)
        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_issue_link.deleted",
            entity_type="policy_issue_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "policy_id": str(row.policy_id),
                "issue_id": str(row.issue_id),
                "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
            },
            metadata_json={"source": "api"},
        )

        return row

    def get_policy_effectiveness(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> dict:
        self.require_policy_in_org(org_id, policy_id)

        rows = self.db.execute(
            select(PolicyIssueLink.violation_type, PolicyIssueLink.severity_impact, Task.status)
            .join(Task, Task.id == PolicyIssueLink.issue_id)
            .where(
                PolicyIssueLink.organization_id == org_id,
                PolicyIssueLink.policy_id == policy_id,
                PolicyIssueLink.deleted_at.is_(None),
            )
        ).all()

        by_violation_type = {k: 0 for k in self.VIOLATION_TYPES}
        by_severity_impact = {k: 0 for k in self.SEVERITY_IMPACTS}
        open_issues = 0
        resolved_issues = 0

        for violation_type, severity_impact, issue_status in rows:
            by_violation_type[str(violation_type)] = by_violation_type.get(str(violation_type), 0) + 1
            by_severity_impact[str(severity_impact)] = by_severity_impact.get(str(severity_impact), 0) + 1

            issue_status_value = str(issue_status)
            if issue_status_value in self.OPEN_ISSUE_STATUSES:
                open_issues += 1
            elif issue_status_value in self.RESOLVED_ISSUE_STATUSES:
                resolved_issues += 1

        # ``Issue.created_at`` can be persisted as naive timestamps in SQLite
        # test runs; use naive UTC here to avoid aware/naive comparison errors.
        now = datetime.utcnow()
        last_30d = now - timedelta(days=30)
        last_90d = now - timedelta(days=90)

        trend_last_30d = int(
            self.db.execute(
                select(func.count(PolicyIssueLink.id)).where(
                    PolicyIssueLink.organization_id == org_id,
                    PolicyIssueLink.policy_id == policy_id,
                    PolicyIssueLink.deleted_at.is_(None),
                    PolicyIssueLink.created_at >= last_30d,
                )
            ).scalar_one()
        )
        trend_last_90d = int(
            self.db.execute(
                select(func.count(PolicyIssueLink.id)).where(
                    PolicyIssueLink.organization_id == org_id,
                    PolicyIssueLink.policy_id == policy_id,
                    PolicyIssueLink.deleted_at.is_(None),
                    PolicyIssueLink.created_at >= last_90d,
                )
            ).scalar_one()
        )

        total_issues_linked = len(rows)
        effectiveness_score = 100.0 - (open_issues / max(total_issues_linked, 1) * 100.0)
        effectiveness_score = max(0.0, min(100.0, effectiveness_score))

        return {
            "policy_id": policy_id,
            "total_issues_linked": total_issues_linked,
            "open_issues": open_issues,
            "resolved_issues": resolved_issues,
            "by_violation_type": by_violation_type,
            "by_severity_impact": by_severity_impact,
            "trend_last_30d": trend_last_30d,
            "trend_last_90d": trend_last_90d,
            "effectiveness_score": effectiveness_score,
        }

    def get_issue_policy_context(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> dict:
        issue = self.require_issue_in_org(org_id, issue_id)

        rows = self.db.execute(
            select(PolicyIssueLink, CompliancePolicy)
            .join(CompliancePolicy, CompliancePolicy.id == PolicyIssueLink.policy_id)
            .where(
                PolicyIssueLink.organization_id == org_id,
                PolicyIssueLink.issue_id == issue_id,
                PolicyIssueLink.deleted_at.is_(None),
            )
        ).all()

        severity_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        most_severe_impact = None
        most_severe_rank = 0

        policies: list[dict] = []
        for link, policy in rows:
            policies.append(
                {
                    "policy_id": policy.id,
                    "policy_name": policy.title,
                    "policy_status": policy.status,
                    "violation_type": link.violation_type,
                    "severity_impact": link.severity_impact,
                    "linked_at": link.created_at,
                }
            )
            current_rank = severity_rank.get(str(link.severity_impact), 0)
            if current_rank > most_severe_rank:
                most_severe_rank = current_rank
                most_severe_impact = str(link.severity_impact)

        _ = issue
        return {
            "issue_id": issue_id,
            "total_policies_linked": len(rows),
            "policies": policies,
            "most_severe_impact": most_severe_impact,
        }

    def get_org_policy_effectiveness_summary(self, org_id: uuid.UUID) -> dict:
        total_links = int(
            self.db.execute(
                select(func.count(PolicyIssueLink.id)).where(
                    PolicyIssueLink.organization_id == org_id,
                    PolicyIssueLink.deleted_at.is_(None),
                )
            ).scalar_one()
        )

        policies_with_issues = int(
            self.db.execute(
                select(func.count(func.distinct(PolicyIssueLink.policy_id))).where(
                    PolicyIssueLink.organization_id == org_id,
                    PolicyIssueLink.deleted_at.is_(None),
                )
            ).scalar_one()
        )

        total_policies = int(
            self.db.execute(
                select(func.count(CompliancePolicy.id)).where(CompliancePolicy.organization_id == org_id)
            ).scalar_one()
        )
        policies_without_issues = max(total_policies - policies_with_issues, 0)

        violation_type_breakdown = {k: 0 for k in self.VIOLATION_TYPES}
        for violation_type, count in self.db.execute(
            select(PolicyIssueLink.violation_type, func.count(PolicyIssueLink.id))
            .where(
                PolicyIssueLink.organization_id == org_id,
                PolicyIssueLink.deleted_at.is_(None),
            )
            .group_by(PolicyIssueLink.violation_type)
        ).all():
            violation_type_breakdown[str(violation_type)] = int(count)

        most_violated_policies = [
            {
                "policy_id": policy_id,
                "policy_name": policy_title,
                "issue_count": int(issue_count),
            }
            for policy_id, policy_title, issue_count in self.db.execute(
                select(
                    CompliancePolicy.id,
                    CompliancePolicy.title,
                    func.count(PolicyIssueLink.id).label("issue_count"),
                )
                .join(PolicyIssueLink, PolicyIssueLink.policy_id == CompliancePolicy.id)
                .where(
                    CompliancePolicy.organization_id == org_id,
                    PolicyIssueLink.organization_id == org_id,
                    PolicyIssueLink.deleted_at.is_(None),
                )
                .group_by(CompliancePolicy.id, CompliancePolicy.title)
                .order_by(func.count(PolicyIssueLink.id).desc(), CompliancePolicy.title.asc())
                .limit(5)
            ).all()
        ]

        open_issues_by_policy = [
            {
                "policy_id": policy_id,
                "policy_name": policy_title,
                "open_issue_count": int(open_issue_count),
            }
            for policy_id, policy_title, open_issue_count in self.db.execute(
                select(
                    CompliancePolicy.id,
                    CompliancePolicy.title,
                    func.count(PolicyIssueLink.id).label("open_issue_count"),
                )
                .join(PolicyIssueLink, PolicyIssueLink.policy_id == CompliancePolicy.id)
                .join(Task, Task.id == PolicyIssueLink.issue_id)
                .where(
                    CompliancePolicy.organization_id == org_id,
                    PolicyIssueLink.organization_id == org_id,
                    PolicyIssueLink.deleted_at.is_(None),
                    Task.status.in_(self.OPEN_ISSUE_STATUSES),
                )
                .group_by(CompliancePolicy.id, CompliancePolicy.title)
                .having(func.count(PolicyIssueLink.id) > 0)
                .order_by(func.count(PolicyIssueLink.id).desc(), CompliancePolicy.title.asc())
                .limit(10)
            ).all()
        ]

        return {
            "total_links": total_links,
            "policies_with_issues": policies_with_issues,
            "policies_without_issues": policies_without_issues,
            "most_violated_policies": most_violated_policies,
            "violation_type_breakdown": violation_type_breakdown,
            "open_issues_by_policy": open_issues_by_policy,
        }

    # Sprint 3 P3 v2 methods on issue_policy_links (Issue model-backed).
    def _require_issue_record(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> Issue:
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

    def link_issue(
        self,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        issue_id: uuid.UUID,
        created_by: uuid.UUID,
        link_reason: str | None = None,
    ) -> IssuePolicyLink:
        self.require_policy_in_org(org_id, policy_id)
        self._require_issue_record(org_id, issue_id)
        existing = self.db.execute(
            select(IssuePolicyLink).where(
                IssuePolicyLink.organization_id == org_id,
                IssuePolicyLink.policy_id == policy_id,
                IssuePolicyLink.issue_id == issue_id,
                IssuePolicyLink.unlinked_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Issue-policy link already exists")

        now = self.utcnow()
        row = IssuePolicyLink(
            organization_id=org_id,
            issue_id=issue_id,
            policy_id=policy_id,
            link_type="violated",
            link_reason=link_reason,
            status="active",
            linked_by=created_by,
            linked_at=now,
            created_by=created_by,
            created_at=now,
        )
        self.db.add(row)
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="policy.issue_linked",
            entity_type="issue_policy_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            metadata_json={"policy_id": str(policy_id), "issue_id": str(issue_id), "link_reason": link_reason},
        )
        return row

    def unlink_issue(
        self,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        issue_id: uuid.UUID,
        unlinked_by: uuid.UUID,
    ) -> IssuePolicyLink:
        row = self.db.execute(
            select(IssuePolicyLink).where(
                IssuePolicyLink.organization_id == org_id,
                IssuePolicyLink.policy_id == policy_id,
                IssuePolicyLink.issue_id == issue_id,
                IssuePolicyLink.unlinked_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue-policy link not found")
        row.status = "inactive"
        row.unlinked_at = self.utcnow()
        row.unlinked_by = unlinked_by
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="policy.issue_unlinked",
            entity_type="issue_policy_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=unlinked_by,
            metadata_json={"policy_id": str(policy_id), "issue_id": str(issue_id)},
        )
        return row

    def list_issues_for_policy(
        self,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        include_resolved: bool = False,
    ) -> list[Issue]:
        self.require_policy_in_org(org_id, policy_id)
        stmt = (
            select(Issue)
            .join(IssuePolicyLink, IssuePolicyLink.issue_id == Issue.id)
            .where(
                Issue.organization_id == org_id,
                IssuePolicyLink.organization_id == org_id,
                IssuePolicyLink.policy_id == policy_id,
                IssuePolicyLink.unlinked_at.is_(None),
                Issue.deleted_at.is_(None),
            )
        )
        if not include_resolved:
            stmt = stmt.where(Issue.status.not_in(["resolved", "closed"]))
        return self.db.execute(stmt.order_by(Issue.created_at.desc())).scalars().all()

    def list_policies_for_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> list[CompliancePolicy]:
        self._require_issue_record(org_id, issue_id)
        stmt = (
            select(CompliancePolicy)
            .join(IssuePolicyLink, IssuePolicyLink.policy_id == CompliancePolicy.id)
            .where(
                CompliancePolicy.organization_id == org_id,
                IssuePolicyLink.organization_id == org_id,
                IssuePolicyLink.issue_id == issue_id,
                IssuePolicyLink.unlinked_at.is_(None),
            )
        )
        return self.db.execute(stmt.order_by(CompliancePolicy.title.asc())).scalars().all()

    def get_policy_violation_rate(self, org_id: uuid.UUID, policy_id: uuid.UUID, lookback_days: int = 365) -> dict:
        policy = self.require_policy_in_org(org_id, policy_id)
        lookback_days = max(1, int(lookback_days))
        # ``Issue.created_at`` may be persisted as naive in SQLite test runs.
        # Normalize comparisons to naive UTC for deterministic filtering.
        now = datetime.utcnow()
        window_start = now - timedelta(days=lookback_days)
        midpoint = window_start + timedelta(days=lookback_days / 2)

        linked_issue_rows = self.db.execute(
            select(Issue, IssuePolicyLink.link_type)
            .join(IssuePolicyLink, IssuePolicyLink.issue_id == Issue.id)
            .where(
                Issue.organization_id == org_id,
                IssuePolicyLink.organization_id == org_id,
                IssuePolicyLink.policy_id == policy_id,
                IssuePolicyLink.unlinked_at.is_(None),
                Issue.deleted_at.is_(None),
            )
        ).all()

        linked_issues_rows = [row[0] for row in linked_issue_rows]

        total_linked_issues = len({row.id for row in linked_issues_rows})
        open_issues = len([row for row in linked_issues_rows if row.status not in {"resolved", "closed"}])
        resolved_issues = len([row for row in linked_issues_rows if row.status in {"resolved", "closed"}])

        def _naive_utc(dt: datetime) -> datetime:
            return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

        issues_in_window = [row for row in linked_issues_rows if _naive_utc(row.created_at) >= window_start]
        first_half = len([row for row in issues_in_window if _naive_utc(row.created_at) < midpoint])
        second_half = len([row for row in issues_in_window if _naive_utc(row.created_at) >= midpoint])

        trend: str | None
        if len(issues_in_window) < 3:
            trend = None
        else:
            if second_half > (first_half * 1.2):
                trend = "increasing"
            elif first_half > (second_half * 1.2):
                trend = "decreasing"
            else:
                trend = "stable"

        issue_type_counts: dict[str, int] = {}
        for row in linked_issues_rows:
            key = str(getattr(row, "issue_type", "") or "")
            if not key:
                continue
            issue_type_counts[key] = issue_type_counts.get(key, 0) + 1
        most_common_issue_type = max(issue_type_counts, key=issue_type_counts.get) if issue_type_counts else None

        violation_rate_per_month = round(total_linked_issues / (lookback_days / 30), 2)

        # Legacy keys preserved for compatibility with existing endpoint schema.
        violations_past_12m = len(
            {
                issue.id
                for issue, link_type in linked_issue_rows
                if _naive_utc(issue.created_at) >= window_start and str(link_type or "").lower() == "violated"
            }
        )
        total_issues_past_12m = int(
            self.db.execute(
                select(func.count(Issue.id)).where(
                    Issue.organization_id == org_id,
                    Issue.deleted_at.is_(None),
                    Issue.created_at >= window_start,
                )
            ).scalar_one()
        )
        violation_rate = round((violations_past_12m / total_issues_past_12m) * 100.0, 2) if total_issues_past_12m else 0.0

        return {
            "policy_id": policy.id,
            "lookback_days": lookback_days,
            "total_linked_issues": total_linked_issues,
            "open_issues": open_issues,
            "resolved_issues": resolved_issues,
            "violation_rate_per_month": violation_rate_per_month,
            "most_common_issue_type": most_common_issue_type,
            "trend": trend,
            "policy_name": policy.title,
            "total_issues_past_12m": total_issues_past_12m,
            "violations_past_12m": violations_past_12m,
            "violation_rate": violation_rate,
        }
