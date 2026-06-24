import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.policy_exception import PolicyException
from app.models.policy_exception_approval import PolicyExceptionApproval
from app.schemas.policy_exception import PolicyExceptionCreate, PolicyExceptionUpdate
from app.services.audit_service import AuditService
from app.services.rbac_service import RBACService


class PolicyExceptionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def require_policy_in_org(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> CompliancePolicy:
        policy = self.db.execute(
            select(CompliancePolicy).where(
                CompliancePolicy.organization_id == org_id,
                CompliancePolicy.id == policy_id,
            )
        ).scalar_one_or_none()
        if policy is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance policy not found")
        return policy

    def require_exception(self, org_id: uuid.UUID, exception_id: uuid.UUID, *, include_deleted: bool = False) -> PolicyException:
        stmt = select(PolicyException).where(
            PolicyException.organization_id == org_id,
            PolicyException.id == exception_id,
        )
        if not include_deleted:
            stmt = stmt.where(PolicyException.deleted_at.is_(None))
        row = self.db.execute(stmt).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy exception not found")
        return row

    def get_approval(self, org_id: uuid.UUID, exception_id: uuid.UUID) -> PolicyExceptionApproval | None:
        return self.db.execute(
            select(PolicyExceptionApproval).where(
                PolicyExceptionApproval.organization_id == org_id,
                PolicyExceptionApproval.exception_id == exception_id,
            )
        ).scalar_one_or_none()

    def _has_manage(self, actor_id: uuid.UUID, org_id: uuid.UUID) -> bool:
        return RBACService.user_has_permission(self.db, actor_id, org_id, "policy_exceptions:manage")

    def create_exception(self, org_id: uuid.UUID, payload: PolicyExceptionCreate, requested_by: uuid.UUID) -> PolicyException:
        self.require_policy_in_org(org_id, payload.policy_id)

        row = PolicyException(
            organization_id=org_id,
            policy_id=payload.policy_id,
            policy_version=payload.policy_version,
            title=payload.title,
            description=payload.description,
            justification=payload.justification,
            compensating_measure=payload.compensating_measure,
            requested_by=requested_by,
            requestor_scope=payload.requestor_scope,
            requested_expiry_date=payload.requested_expiry_date,
            status="pending",
            approved_expiry_date=None,
            risk_level=payload.risk_level,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_exception.created",
            entity_type="policy_exception",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=requested_by,
            after_json={
                "policy_id": str(row.policy_id),
                "status": row.status,
                "risk_level": row.risk_level,
                "requested_expiry_date": str(row.requested_expiry_date),
            },
            metadata_json={"source": "api"},
        )
        return row

    def list_exceptions(
        self,
        org_id: uuid.UUID,
        *,
        policy_id: uuid.UUID | None = None,
        status_value: str | None = None,
        requested_by: uuid.UUID | None = None,
        risk_level: str | None = None,
    ) -> list[PolicyException]:
        stmt = select(PolicyException).where(
            PolicyException.organization_id == org_id,
            PolicyException.deleted_at.is_(None),
        )
        if policy_id is not None:
            stmt = stmt.where(PolicyException.policy_id == policy_id)
        if status_value is not None:
            stmt = stmt.where(PolicyException.status == status_value)
        if requested_by is not None:
            stmt = stmt.where(PolicyException.requested_by == requested_by)
        if risk_level is not None:
            stmt = stmt.where(PolicyException.risk_level == risk_level)

        return self.db.execute(stmt.order_by(PolicyException.created_at.desc())).scalars().all()

    def get_exception(self, org_id: uuid.UUID, exception_id: uuid.UUID) -> tuple[PolicyException, PolicyExceptionApproval | None]:
        row = self.require_exception(org_id, exception_id)
        return row, self.get_approval(org_id, row.id)

    def update_exception(
        self,
        org_id: uuid.UUID,
        exception_id: uuid.UUID,
        payload: PolicyExceptionUpdate,
        actor_id: uuid.UUID,
    ) -> PolicyException:
        row = self.require_exception(org_id, exception_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending exceptions can be updated")

        if actor_id != row.requested_by and not self._has_manage(actor_id, org_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this exception")

        before = {
            "title": row.title,
            "description": row.description,
            "justification": row.justification,
            "compensating_measure": row.compensating_measure,
            "requestor_scope": row.requestor_scope,
            "requested_expiry_date": str(row.requested_expiry_date),
            "risk_level": row.risk_level,
        }

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_exception.updated",
            entity_type="policy_exception",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={
                "title": row.title,
                "description": row.description,
                "justification": row.justification,
                "compensating_measure": row.compensating_measure,
                "requestor_scope": row.requestor_scope,
                "requested_expiry_date": str(row.requested_expiry_date),
                "risk_level": row.risk_level,
            },
            metadata_json={"source": "api"},
        )
        return row

    def withdraw_exception(self, org_id: uuid.UUID, exception_id: uuid.UUID, actor_id: uuid.UUID) -> PolicyException:
        row = self.require_exception(org_id, exception_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending exceptions can be withdrawn")
        if actor_id != row.requested_by and not self._has_manage(actor_id, org_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to withdraw this exception")

        row.status = "withdrawn"
        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_exception.withdrawn",
            entity_type="policy_exception",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={"status": row.status, "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None},
            metadata_json={"source": "api"},
        )
        return row

    def approve_exception(
        self,
        org_id: uuid.UUID,
        exception_id: uuid.UUID,
        *,
        decision_reason: str,
        approved_expiry_date: date,
        conditions: str | None,
        actor_id: uuid.UUID,
    ) -> PolicyException:
        row = self.require_exception(org_id, exception_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending exceptions can be approved")

        existing = self.get_approval(org_id, row.id)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approval decision already recorded for this exception")

        approval = PolicyExceptionApproval(
            organization_id=org_id,
            exception_id=row.id,
            reviewed_by=actor_id,
            decision="approved",
            decision_reason=decision_reason,
            approved_expiry_date=approved_expiry_date,
            conditions=conditions,
        )
        self.db.add(approval)

        row.status = "approved"
        row.approved_expiry_date = approved_expiry_date
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_exception.approved",
            entity_type="policy_exception",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "status": row.status,
                "approved_expiry_date": str(row.approved_expiry_date) if row.approved_expiry_date else None,
                "decision_reason": decision_reason,
                "conditions": conditions,
            },
            metadata_json={"source": "api"},
        )
        return row

    def reject_exception(
        self,
        org_id: uuid.UUID,
        exception_id: uuid.UUID,
        *,
        decision_reason: str,
        actor_id: uuid.UUID,
    ) -> PolicyException:
        row = self.require_exception(org_id, exception_id)
        if row.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending exceptions can be rejected")

        existing = self.get_approval(org_id, row.id)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approval decision already recorded for this exception")

        approval = PolicyExceptionApproval(
            organization_id=org_id,
            exception_id=row.id,
            reviewed_by=actor_id,
            decision="rejected",
            decision_reason=decision_reason,
            approved_expiry_date=None,
            conditions=None,
        )
        self.db.add(approval)

        row.status = "rejected"
        row.approved_expiry_date = None
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_exception.rejected",
            entity_type="policy_exception",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "status": row.status,
                "decision_reason": decision_reason,
            },
            metadata_json={"source": "api"},
        )
        return row

    def expire_exceptions(self, org_id: uuid.UUID | None = None) -> int:
        today = self.utcdate()
        stmt = select(PolicyException).where(
            PolicyException.status == "approved",
            PolicyException.approved_expiry_date.is_not(None),
            PolicyException.approved_expiry_date < today,
        )
        if org_id is not None:
            stmt = stmt.where(PolicyException.organization_id == org_id)

        rows = self.db.execute(stmt).scalars().all()
        for row in rows:
            row.status = "expired"
            self.db.flush()
            AuditService(self.db).write_audit_log(
                action="policy_exception.expired",
                entity_type="policy_exception",
                entity_id=row.id,
                organization_id=row.organization_id,
                actor_user_id=None,
                after_json={
                    "status": row.status,
                    "approved_expiry_date": str(row.approved_expiry_date) if row.approved_expiry_date else None,
                },
                metadata_json={"source": "sweep"},
            )
        return len(rows)

    def get_policy_exception_summary(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> dict:
        self.require_policy_in_org(org_id, policy_id)
        today = self.utcdate()

        base_filters = [
            PolicyException.organization_id == org_id,
            PolicyException.policy_id == policy_id,
        ]

        active_exceptions = int(
            self.db.execute(
                select(func.count(PolicyException.id)).where(
                    *base_filters,
                    PolicyException.deleted_at.is_(None),
                    PolicyException.status == "approved",
                    PolicyException.approved_expiry_date.is_not(None),
                    PolicyException.approved_expiry_date >= today,
                )
            ).scalar_one()
        )
        pending_count = int(
            self.db.execute(
                select(func.count(PolicyException.id)).where(
                    *base_filters,
                    PolicyException.deleted_at.is_(None),
                    PolicyException.status == "pending",
                )
            ).scalar_one()
        )
        historical_count = int(
            self.db.execute(
                select(func.count(PolicyException.id)).where(
                    *base_filters,
                    PolicyException.status.in_(["rejected", "expired", "withdrawn"]),
                )
            ).scalar_one()
        )

        approved_rows = self.db.execute(
            select(PolicyException.created_at, PolicyException.approved_expiry_date).where(
                *base_filters,
                PolicyException.status.in_(["approved", "expired"]),
                PolicyException.approved_expiry_date.is_not(None),
            )
        ).all()
        avg_duration: float | None = None
        if approved_rows:
            durations = [(expiry_date - created_at.date()).days for created_at, expiry_date in approved_rows]
            if durations:
                avg_duration = round(sum(durations) / len(durations), 2)

        risk_counts = self.db.execute(
            select(PolicyException.risk_level, func.count(PolicyException.id))
            .where(*base_filters)
            .group_by(PolicyException.risk_level)
        ).all()
        most_common: str | None = None
        if risk_counts:
            risk_counts_sorted = sorted(risk_counts, key=lambda row: (-int(row[1]), str(row[0])))
            most_common = str(risk_counts_sorted[0][0])

        return {
            "policy_id": policy_id,
            "active_exceptions": active_exceptions,
            "pending_count": pending_count,
            "historical_count": historical_count,
            "avg_exception_duration_days": avg_duration,
            "most_common_risk_level": most_common,
        }

    def get_org_exception_dashboard(self, org_id: uuid.UUID) -> dict:
        today = self.utcdate()
        soon_end = today + timedelta(days=14)

        total_pending = int(
            self.db.execute(
                select(func.count(PolicyException.id)).where(
                    PolicyException.organization_id == org_id,
                    PolicyException.deleted_at.is_(None),
                    PolicyException.status == "pending",
                )
            ).scalar_one()
        )
        total_active = int(
            self.db.execute(
                select(func.count(PolicyException.id)).where(
                    PolicyException.organization_id == org_id,
                    PolicyException.deleted_at.is_(None),
                    PolicyException.status == "approved",
                    PolicyException.approved_expiry_date.is_not(None),
                    PolicyException.approved_expiry_date >= today,
                )
            ).scalar_one()
        )

        expiring_soon = self.db.execute(
            select(PolicyException)
            .where(
                PolicyException.organization_id == org_id,
                PolicyException.deleted_at.is_(None),
                PolicyException.status == "approved",
                PolicyException.approved_expiry_date.is_not(None),
                PolicyException.approved_expiry_date >= today,
                PolicyException.approved_expiry_date <= soon_end,
            )
            .order_by(PolicyException.approved_expiry_date.asc(), PolicyException.created_at.desc())
        ).scalars().all()

        high_risk_active = self.db.execute(
            select(PolicyException)
            .where(
                PolicyException.organization_id == org_id,
                PolicyException.deleted_at.is_(None),
                PolicyException.status == "approved",
                PolicyException.approved_expiry_date.is_not(None),
                PolicyException.approved_expiry_date >= today,
                PolicyException.risk_level.in_(["high", "critical"]),
            )
            .order_by(PolicyException.risk_level.desc(), PolicyException.created_at.desc())
        ).scalars().all()

        overdue_pending = self.db.execute(
            select(PolicyException)
            .where(
                PolicyException.organization_id == org_id,
                PolicyException.deleted_at.is_(None),
                PolicyException.status == "pending",
                PolicyException.requested_expiry_date < today,
            )
            .order_by(PolicyException.requested_expiry_date.asc(), PolicyException.created_at.desc())
        ).scalars().all()

        return {
            "total_pending": total_pending,
            "total_active": total_active,
            "expiring_soon": expiring_soon,
            "high_risk_active": high_risk_active,
            "overdue_pending": overdue_pending,
        }
