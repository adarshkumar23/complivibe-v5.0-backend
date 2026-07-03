import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_engagement import AuditEngagement
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.user import User
from app.schemas.audit_engagement import AuditEngagementCreate, AuditEngagementUpdate
from app.services.audit_service import AuditService


class AuditEngagementService:
    ALLOWED_TRANSITIONS: dict[str, set[str]] = {
        "planning": {"fieldwork", "cancelled"},
        "fieldwork": {"review", "cancelled"},
        "review": {"report_issuance", "fieldwork"},
        "report_issuance": {"closed"},
        "closed": set(),
        "cancelled": set(),
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def require_engagement(self, org_id: uuid.UUID, engagement_id: uuid.UUID) -> AuditEngagement:
        row = self.db.execute(
            select(AuditEngagement).where(
                AuditEngagement.organization_id == org_id,
                AuditEngagement.id == engagement_id,
                AuditEngagement.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit engagement not found")
        return row

    def _validate_framework_ids(self, framework_ids: list[uuid.UUID]) -> None:
        if not framework_ids:
            return
        found = {
            row[0]
            for row in self.db.execute(select(Framework.id).where(Framework.id.in_(framework_ids))).all()
        }
        missing = [str(item) for item in framework_ids if item not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown framework ids: {', '.join(missing)}",
            )

    def _validate_assigned_auditors(self, org_id: uuid.UUID, auditor_ids: list[uuid.UUID]) -> None:
        if not auditor_ids:
            return

        active_member_ids = {
            row[0]
            for row in self.db.execute(
                select(Membership.user_id)
                .join(User, User.id == Membership.user_id)
                .where(
                    Membership.organization_id == org_id,
                    Membership.status == "active",
                    User.is_active.is_(True),
                    User.status == "active",
                    Membership.user_id.in_(auditor_ids),
                )
            ).all()
        }
        missing = [str(item) for item in auditor_ids if item not in active_member_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"assigned_auditor_ids must be active org members: {', '.join(missing)}",
            )

    @staticmethod
    def _ensure_date_range(start_date: date, end_date: date) -> None:
        if end_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="end_date must be on or after start_date",
            )

    def create_engagement(
        self,
        org_id: uuid.UUID,
        data: AuditEngagementCreate,
        created_by: uuid.UUID,
        *,
        source_schedule_id: uuid.UUID | None = None,
    ) -> AuditEngagement:
        self._ensure_date_range(data.start_date, data.end_date)
        self._validate_framework_ids(data.scope_framework_ids)
        self._validate_assigned_auditors(org_id, data.assigned_auditor_ids)

        row = AuditEngagement(
            organization_id=org_id,
            title=data.title,
            audit_type=data.audit_type,
            scope_framework_ids=[str(item) for item in data.scope_framework_ids],
            assigned_auditor_ids=[str(item) for item in data.assigned_auditor_ids],
            status="planning",
            start_date=data.start_date,
            end_date=data.end_date,
            report_issued_at=None,
            lead_auditor_name=data.lead_auditor_name,
            audit_firm=data.audit_firm,
            notes=data.notes,
            created_by=created_by,
            source_schedule_id=source_schedule_id,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_engagement.created",
            entity_type="audit_engagement",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "title": row.title,
                "audit_type": row.audit_type,
                "status": row.status,
                "start_date": str(row.start_date),
                "end_date": str(row.end_date),
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_engagement(self, org_id: uuid.UUID, engagement_id: uuid.UUID) -> AuditEngagement:
        return self.require_engagement(org_id, engagement_id)

    def list_engagements(
        self,
        org_id: uuid.UUID,
        *,
        status_value: str | None = None,
        audit_type: str | None = None,
        framework_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AuditEngagement]:
        stmt = select(AuditEngagement).where(
            AuditEngagement.organization_id == org_id,
            AuditEngagement.deleted_at.is_(None),
        )
        if status_value is not None:
            stmt = stmt.where(AuditEngagement.status == status_value)
        if audit_type is not None:
            stmt = stmt.where(AuditEngagement.audit_type == audit_type)

        rows = self.db.execute(stmt.order_by(AuditEngagement.start_date.desc(), AuditEngagement.created_at.desc())).scalars().all()
        if framework_id is not None:
            framework_str = str(framework_id)
            rows = [row for row in rows if framework_str in (row.scope_framework_ids or [])]

        return rows[skip : skip + limit]

    def update_engagement(self, org_id: uuid.UUID, engagement_id: uuid.UUID, data: AuditEngagementUpdate) -> AuditEngagement:
        row = self.require_engagement(org_id, engagement_id)

        incoming = data.model_dump(exclude_unset=True)
        start_date = incoming.get("start_date", row.start_date)
        end_date = incoming.get("end_date", row.end_date)
        self._ensure_date_range(start_date, end_date)

        if "scope_framework_ids" in incoming and incoming["scope_framework_ids"] is not None:
            self._validate_framework_ids(incoming["scope_framework_ids"])
            incoming["scope_framework_ids"] = [str(item) for item in incoming["scope_framework_ids"]]

        if "assigned_auditor_ids" in incoming and incoming["assigned_auditor_ids"] is not None:
            self._validate_assigned_auditors(org_id, incoming["assigned_auditor_ids"])
            incoming["assigned_auditor_ids"] = [str(item) for item in incoming["assigned_auditor_ids"]]

        before = {
            "title": row.title,
            "audit_type": row.audit_type,
            "scope_framework_ids": row.scope_framework_ids,
            "assigned_auditor_ids": row.assigned_auditor_ids,
            "start_date": str(row.start_date),
            "end_date": str(row.end_date),
            "lead_auditor_name": row.lead_auditor_name,
            "audit_firm": row.audit_firm,
            "notes": row.notes,
        }

        for key, value in incoming.items():
            setattr(row, key, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_engagement.updated",
            entity_type="audit_engagement",
            entity_id=row.id,
            organization_id=org_id,
            before_json=before,
            after_json={
                "title": row.title,
                "audit_type": row.audit_type,
                "scope_framework_ids": row.scope_framework_ids,
                "assigned_auditor_ids": row.assigned_auditor_ids,
                "start_date": str(row.start_date),
                "end_date": str(row.end_date),
                "lead_auditor_name": row.lead_auditor_name,
                "audit_firm": row.audit_firm,
                "notes": row.notes,
            },
            metadata_json={"source": "api"},
        )
        return row

    def transition_status(
        self,
        org_id: uuid.UUID,
        engagement_id: uuid.UUID,
        new_status: str,
        current_user_id: uuid.UUID,
    ) -> AuditEngagement:
        row = self.require_engagement(org_id, engagement_id)
        allowed = self.ALLOWED_TRANSITIONS.get(row.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {row.status} to {new_status}",
            )

        before_status = row.status
        row.status = new_status
        if new_status == "report_issuance":
            row.report_issued_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_engagement.status_transitioned",
            entity_type="audit_engagement",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=current_user_id,
            before_json={"status": before_status},
            after_json={
                "status": row.status,
                "report_issued_at": row.report_issued_at.isoformat() if row.report_issued_at else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def soft_delete_engagement(self, org_id: uuid.UUID, engagement_id: uuid.UUID, user_id: uuid.UUID) -> AuditEngagement:
        row = self.require_engagement(org_id, engagement_id)
        if row.status not in {"planning", "cancelled"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only planning or cancelled engagements can be deleted",
            )

        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="audit_engagement.deleted",
            entity_type="audit_engagement",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat() if row.deleted_at else None, "status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def get_engagement_dashboard(self, org_id: uuid.UUID) -> dict:
        today = self.utcdate()
        in_30_days = today + timedelta(days=30)

        base_where = [AuditEngagement.organization_id == org_id, AuditEngagement.deleted_at.is_(None)]

        total_engagements = int(
            self.db.execute(select(func.count(AuditEngagement.id)).where(*base_where)).scalar_one()
        )

        by_status_rows = self.db.execute(
            select(AuditEngagement.status, func.count(AuditEngagement.id))
            .where(*base_where)
            .group_by(AuditEngagement.status)
        ).all()
        by_type_rows = self.db.execute(
            select(AuditEngagement.audit_type, func.count(AuditEngagement.id))
            .where(*base_where)
            .group_by(AuditEngagement.audit_type)
        ).all()

        upcoming = int(
            self.db.execute(
                select(func.count(AuditEngagement.id)).where(
                    *base_where,
                    AuditEngagement.start_date >= today,
                    AuditEngagement.start_date <= in_30_days,
                )
            ).scalar_one()
        )
        overdue = int(
            self.db.execute(
                select(func.count(AuditEngagement.id)).where(
                    *base_where,
                    AuditEngagement.end_date < today,
                    AuditEngagement.status.notin_(["closed", "cancelled"]),
                )
            ).scalar_one()
        )

        return {
            "total_engagements": total_engagements,
            "by_status": {str(key): int(val) for key, val in by_status_rows},
            "by_type": {str(key): int(val) for key, val in by_type_rows},
            "upcoming": upcoming,
            "overdue": overdue,
        }
