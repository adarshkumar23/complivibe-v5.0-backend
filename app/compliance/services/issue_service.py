import uuid
from collections import Counter
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_finding import AuditFinding
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.issue import Issue
from app.models.issue_transition import IssueTransition
from app.models.membership import Membership
from app.models.org_issue_settings import OrgIssueSettings
from app.models.user import User
from app.schemas.issue import IssueCreate, IssuePromoteCreate, IssueUpdate
from app.services.audit_service import AuditService


class IssueService:
    ALLOWED_TRANSITIONS: dict[str, str] = {
        "open": "investigating",
        "investigating": "mitigating",
        "mitigating": "resolved",
        "resolved": "closed",
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _ensure_active_member(self, org_id: uuid.UUID, user_id: uuid.UUID, field_name: str) -> None:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name} must be an active organization member",
            )

        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name} must be an active organization member",
            )

    def create_issue(self, org_id: uuid.UUID, data: IssueCreate, created_by: uuid.UUID) -> Issue:
        self._ensure_active_member(org_id, data.owner_id, "owner_id")
        if data.assigned_to is not None:
            self._ensure_active_member(org_id, data.assigned_to, "assigned_to")

        row = Issue(
            organization_id=org_id,
            title=data.title,
            description=data.description,
            issue_type=data.issue_type,
            severity=data.severity,
            source_type=data.source_type,
            source_id=data.source_id,
            status="open",
            owner_id=data.owner_id,
            assigned_to=data.assigned_to,
            created_by=created_by,
            resolution_note=None,
            resolved_at=None,
            closed_at=None,
        )
        self.db.add(row)
        self.db.flush()
        if row.created_at is None:
            row.created_at = self.utcnow()
            self.db.flush()

        # SLA tracking must be initialized in the same transaction as issue creation.
        from app.compliance.services.sla_service import SLAService

        SLAService(self.db).initialize_tracking_for_issue(row)

        AuditService(self.db).write_audit_log(
            action="issue.created",
            entity_type="issue",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "status": row.status,
                "severity": row.severity,
                "issue_type": row.issue_type,
                "source_type": row.source_type,
                "source_id": str(row.source_id) if row.source_id else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> Issue:
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

    def list_issues(
        self,
        org_id: uuid.UUID,
        *,
        status_value: str | None = None,
        severity: str | None = None,
        issue_type: str | None = None,
        source_type: str | None = None,
        owner_id: uuid.UUID | None = None,
        assigned_to: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Issue]:
        stmt = select(Issue).where(
            Issue.organization_id == org_id,
            Issue.deleted_at.is_(None),
        )
        if status_value is not None:
            stmt = stmt.where(Issue.status == status_value)
        if severity is not None:
            stmt = stmt.where(Issue.severity == severity)
        if issue_type is not None:
            stmt = stmt.where(Issue.issue_type == issue_type)
        if source_type is not None:
            stmt = stmt.where(Issue.source_type == source_type)
        if owner_id is not None:
            stmt = stmt.where(Issue.owner_id == owner_id)
        if assigned_to is not None:
            stmt = stmt.where(Issue.assigned_to == assigned_to)

        stmt = stmt.order_by(Issue.created_at.desc()).offset(skip).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def update_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID, data: IssueUpdate, actor_id: uuid.UUID | None = None) -> Issue:
        row = self.get_issue(org_id, issue_id)
        updates = data.model_dump(exclude_unset=True)

        if "owner_id" in updates and updates["owner_id"] is not None:
            self._ensure_active_member(org_id, updates["owner_id"], "owner_id")
        if "assigned_to" in updates and updates["assigned_to"] is not None:
            self._ensure_active_member(org_id, updates["assigned_to"], "assigned_to")

        before = {
            "title": row.title,
            "description": row.description,
            "owner_id": str(row.owner_id),
            "assigned_to": str(row.assigned_to) if row.assigned_to else None,
        }

        for key, value in updates.items():
            setattr(row, key, value)

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="issue.updated",
            entity_type="issue",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={
                "title": row.title,
                "description": row.description,
                "owner_id": str(row.owner_id),
                "assigned_to": str(row.assigned_to) if row.assigned_to else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def assign_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID, assigned_to: uuid.UUID, actor_id: uuid.UUID) -> Issue:
        row = self.get_issue(org_id, issue_id)
        self._ensure_active_member(org_id, assigned_to, "assigned_to")

        before = {"assigned_to": str(row.assigned_to) if row.assigned_to else None}
        row.assigned_to = assigned_to
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="issue.assigned",
            entity_type="issue",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={"assigned_to": str(row.assigned_to)},
            metadata_json={"source": "api"},
        )
        return row

    def transition_issue(
        self,
        org_id: uuid.UUID,
        issue_id: uuid.UUID,
        new_status: str,
        actor_id: uuid.UUID,
        *,
        notes: str | None = None,
        resolution_note: str | None = None,
    ) -> Issue:
        row = self.get_issue(org_id, issue_id)
        expected_next = self.ALLOWED_TRANSITIONS.get(row.status)
        if expected_next is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {row.status} to {new_status}",
            )
        if new_status != expected_next:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {row.status} to {new_status}",
            )

        from_status = row.status
        if from_status == "resolved" and new_status == "closed":
            if resolution_note is None or not resolution_note.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="resolution_note is required when closing a resolved issue",
                )
            settings = self.get_org_settings(org_id)
            if settings.require_rca_before_close:
                from app.compliance.services.rca_service import RCAService

                if not RCAService(self.db).has_rca(org_id, row.id):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="RCA required before closing this issue.",
                    )
            row.resolution_note = resolution_note.strip()

        row.status = new_status
        if new_status == "resolved":
            row.resolved_at = self.utcnow()
        if new_status == "closed":
            row.closed_at = self.utcnow()

        transition = IssueTransition(
            organization_id=org_id,
            issue_id=row.id,
            from_status=from_status,
            to_status=new_status,
            actor_id=actor_id,
            notes=notes,
            transitioned_at=self.utcnow(),
        )
        self.db.add(transition)
        self.db.flush()

        from app.compliance.services.sla_service import SLAService

        if from_status == "open" and new_status == "investigating":
            SLAService(self.db).mark_response_met(org_id, row.id)
        if new_status == "resolved":
            SLAService(self.db).mark_resolution_met(org_id, row.id)

        AuditService(self.db).write_audit_log(
            action="issue.transitioned",
            entity_type="issue",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json={"status": from_status},
            after_json={
                "status": row.status,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                "closed_at": row.closed_at.isoformat() if row.closed_at else None,
                "resolution_note": row.resolution_note,
            },
            metadata_json={"source": "api", "notes": notes},
        )
        return row

    def get_transitions(self, org_id: uuid.UUID, issue_id: uuid.UUID) -> list[IssueTransition]:
        self.get_issue(org_id, issue_id)
        return self.db.execute(
            select(IssueTransition)
            .where(
                IssueTransition.organization_id == org_id,
                IssueTransition.issue_id == issue_id,
            )
            .order_by(IssueTransition.transitioned_at.asc(), IssueTransition.id.asc())
        ).scalars().all()

    def get_issue_dashboard(self, org_id: uuid.UUID) -> dict:
        rows = self.db.execute(
            select(Issue).where(
                Issue.organization_id == org_id,
                Issue.deleted_at.is_(None),
            )
        ).scalars().all()

        by_status = Counter(row.status for row in rows)
        by_severity = Counter(row.severity for row in rows)
        by_type = Counter(row.issue_type for row in rows)

        open_critical_count = sum(1 for row in rows if row.severity == "critical" and row.status != "closed")
        unassigned_count = sum(1 for row in rows if row.assigned_to is None)

        resolved_rows = [row for row in rows if row.status in {"resolved", "closed"} and row.resolved_at is not None]
        if resolved_rows:
            avg_seconds = sum((row.resolved_at - row.created_at).total_seconds() for row in resolved_rows) / len(resolved_rows)
            avg_time_to_resolve_hours = round(avg_seconds / 3600.0, 2)
        else:
            avg_time_to_resolve_hours = 0.0

        from app.compliance.services.sla_service import SLAService

        overdue_payload = SLAService(self.db).update_issue_dashboard_with_sla(org_id)
        return {
            "total": len(rows),
            "by_status": {k: int(v) for k, v in by_status.items()},
            "by_severity": {k: int(v) for k, v in by_severity.items()},
            "by_type": {k: int(v) for k, v in by_type.items()},
            "open_critical_count": int(open_critical_count),
            "avg_time_to_resolve_hours": float(avg_time_to_resolve_hours),
            "unassigned_count": int(unassigned_count),
            "overdue_count": int(overdue_payload["overdue_count"]),
        }

    def soft_delete_issue(self, org_id: uuid.UUID, issue_id: uuid.UUID, user_id: uuid.UUID) -> Issue:
        row = self.get_issue(org_id, issue_id)
        if row.status != "open":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only open issues can be deleted")

        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="issue.deleted",
            entity_type="issue",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"status": row.status, "deleted_at": row.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row

    def promote_from_alert(self, org_id: uuid.UUID, alert_id: uuid.UUID, data: IssuePromoteCreate, created_by: uuid.UUID) -> Issue:
        alert = self.db.execute(
            select(ControlMonitoringAlert).where(
                ControlMonitoringAlert.organization_id == org_id,
                ControlMonitoringAlert.id == alert_id,
            )
        ).scalar_one_or_none()
        if alert is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control monitoring alert not found")

        payload = IssueCreate(
            title=data.title,
            description=data.description,
            issue_type=data.issue_type,
            severity=data.severity,
            source_type="monitoring_alert",
            source_id=alert_id,
            owner_id=data.owner_id,
            assigned_to=data.assigned_to,
        )
        row = self.create_issue(org_id, payload, created_by)
        AuditService(self.db).write_audit_log(
            action="issue.promoted_from_alert",
            entity_type="issue",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"source_id": str(alert_id), "source_type": "monitoring_alert"},
            metadata_json={"source": "api"},
        )
        return row

    def promote_from_finding(self, org_id: uuid.UUID, finding_id: uuid.UUID, data: IssuePromoteCreate, created_by: uuid.UUID) -> Issue:
        finding = self.db.execute(
            select(AuditFinding).where(
                AuditFinding.organization_id == org_id,
                AuditFinding.id == finding_id,
                AuditFinding.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if finding is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit finding not found")

        payload = IssueCreate(
            title=data.title,
            description=data.description,
            issue_type=data.issue_type,
            severity=data.severity,
            source_type="audit_finding",
            source_id=finding_id,
            owner_id=data.owner_id,
            assigned_to=data.assigned_to,
        )
        row = self.create_issue(org_id, payload, created_by)
        AuditService(self.db).write_audit_log(
            action="issue.promoted_from_finding",
            entity_type="issue",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"source_id": str(finding_id), "source_type": "audit_finding"},
            metadata_json={"source": "api"},
        )
        return row

    def get_org_settings(self, org_id: uuid.UUID) -> OrgIssueSettings:
        row = self.db.execute(
            select(OrgIssueSettings).where(OrgIssueSettings.organization_id == org_id)
        ).scalar_one_or_none()
        if row is not None:
            return row

        row = OrgIssueSettings(
            organization_id=org_id,
            require_rca_before_close=True,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def update_org_settings(self, org_id: uuid.UUID, require_rca_before_close: bool, user_id: uuid.UUID) -> OrgIssueSettings:
        row = self.get_org_settings(org_id)
        before = {"require_rca_before_close": bool(row.require_rca_before_close)}
        row.require_rca_before_close = require_rca_before_close
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="issue_settings.updated",
            entity_type="org_issue_settings",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={"require_rca_before_close": bool(row.require_rca_before_close)},
            metadata_json={"source": "api"},
        )
        return row
