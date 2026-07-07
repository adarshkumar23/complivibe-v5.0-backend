import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.control_exception import ControlException
from app.models.control_exception_approval import ControlExceptionApproval
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.membership import Membership
from app.models.user import User
from app.schemas.control_exception import ControlExceptionCreate
from app.services.audit_service import AuditService
from app.services.rbac_service import RBACService


class ControlExceptionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> date:
        return datetime.now(UTC).date()

    def require_exception_in_org(self, org_id: uuid.UUID, exception_id: uuid.UUID) -> ControlException:
        row = self.db.execute(
            select(ControlException).where(
                ControlException.id == exception_id,
                ControlException.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control exception not found")
        return row

    def require_control_in_org(self, org_id: uuid.UUID, control_id: uuid.UUID, *, field_name: str = "control_id") -> Control:
        row = self.db.execute(
            select(Control).where(
                Control.id == control_id,
                Control.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{field_name} not found")
        return row

    def ensure_active_member(self, org_id: uuid.UUID, user_id: uuid.UUID, *, field_name: str) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=422,
                detail=f"{field_name} must be an active member of the organization",
            )

        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(
                status_code=422,
                detail=f"{field_name} must be an active member of the organization",
            )
        return user

    @staticmethod
    def _validate_expiry_rules(payload: ControlExceptionCreate) -> None:
        if payload.exception_type == "permanent" and payload.expiry_date is not None:
            raise HTTPException(
                status_code=422,
                detail="permanent exceptions must not include expiry_date",
            )
        if payload.exception_type in {"temporary", "conditional"} and payload.expiry_date is None:
            raise HTTPException(
                status_code=422,
                detail=f"{payload.exception_type} exceptions require expiry_date",
            )
        if payload.expiry_date is not None and payload.expiry_date <= payload.effective_date:
            raise HTTPException(
                status_code=422,
                detail="expiry_date must be greater than effective_date",
            )

    @staticmethod
    def _read_exception(row: ControlException) -> dict:
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "control_id": row.control_id,
            "title": row.title,
            "description": row.description,
            "exception_type": row.exception_type,
            "risk_acceptance_reason": row.risk_acceptance_reason,
            "compensating_control_id": row.compensating_control_id,
            "compensating_description": row.compensating_description,
            "requested_by_user_id": row.requested_by_user_id,
            "owner_user_id": row.owner_user_id,
            "status": row.status,
            "approved_by_user_id": row.approved_by_user_id,
            "approved_at": row.approved_at,
            "rejected_by_user_id": row.rejected_by_user_id,
            "rejected_at": row.rejected_at,
            "rejection_reason": row.rejection_reason,
            "revoked_by_user_id": row.revoked_by_user_id,
            "revoked_at": row.revoked_at,
            "revocation_reason": row.revocation_reason,
            "effective_date": row.effective_date,
            "expiry_date": row.expiry_date,
            "review_date": row.review_date,
            "auto_expired_at": row.auto_expired_at,
            "tags_json": row.tags_json,
            "notes": row.notes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def create_exception(
        self,
        data: ControlExceptionCreate,
        org_id: uuid.UUID,
        requested_by_user_id: uuid.UUID,
    ) -> ControlException:
        self._validate_expiry_rules(data)
        self.require_control_in_org(org_id, data.control_id, field_name="control_id")
        self.ensure_active_member(org_id, data.owner_user_id, field_name="owner_user_id")
        self.ensure_active_member(org_id, requested_by_user_id, field_name="requested_by_user_id")

        if data.compensating_control_id is not None:
            self.require_control_in_org(org_id, data.compensating_control_id, field_name="compensating_control_id")

        if data.approvers:
            seen_sequences: set[int] = set()
            for step in data.approvers:
                if step.sequence in seen_sequences:
                    raise HTTPException(
                        status_code=422,
                        detail="approvers must have unique sequence values",
                    )
                seen_sequences.add(step.sequence)
                self.ensure_active_member(org_id, step.user_id, field_name="approver user_id")

        row = ControlException(
            organization_id=org_id,
            control_id=data.control_id,
            title=data.title,
            description=data.description,
            exception_type=data.exception_type,
            risk_acceptance_reason=data.risk_acceptance_reason,
            compensating_control_id=data.compensating_control_id,
            compensating_description=data.compensating_description,
            requested_by_user_id=requested_by_user_id,
            owner_user_id=data.owner_user_id,
            status="pending_approval",
            effective_date=data.effective_date,
            expiry_date=data.expiry_date,
            review_date=data.review_date,
            tags_json=data.tags_json,
            notes=data.notes,
        )
        self.db.add(row)
        self.db.flush()

        if data.approvers:
            for step in sorted(data.approvers, key=lambda item: item.sequence):
                self.db.add(
                    ControlExceptionApproval(
                        organization_id=org_id,
                        exception_id=row.id,
                        approver_user_id=step.user_id,
                        sequence=step.sequence,
                        status="pending",
                    )
                )
            self.db.flush()

        AuditService(self.db).write_audit_log(
            action="control_exception.created",
            entity_type="control_exception",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=requested_by_user_id,
            after_json={
                "control_id": str(row.control_id),
                "exception_type": row.exception_type,
                "status": row.status,
                "effective_date": str(row.effective_date),
                "expiry_date": str(row.expiry_date) if row.expiry_date else None,
            },
            metadata_json={"source": "api"},
        )
        return row

    def approve(
        self,
        exception_id: uuid.UUID,
        approver_user_id: uuid.UUID,
        decision_notes: str | None,
        org_id: uuid.UUID,
    ) -> ControlException:
        row = self.require_exception_in_org(org_id, exception_id)
        if row.status != "pending_approval":
            raise HTTPException(
                status_code=422,
                detail="Only pending_approval exceptions can be approved",
            )
        if approver_user_id == row.requested_by_user_id:
            raise HTTPException(
                status_code=422,
                detail="Requester cannot approve own exception",
            )

        chain = self.db.execute(
            select(ControlExceptionApproval)
            .where(
                ControlExceptionApproval.organization_id == org_id,
                ControlExceptionApproval.exception_id == exception_id,
            )
            .order_by(ControlExceptionApproval.sequence.asc(), ControlExceptionApproval.created_at.asc())
        ).scalars().all()

        has_override_permission = RBACService.user_has_permission(
            self.db,
            approver_user_id,
            org_id,
            "exceptions:approve",
        )
        is_in_chain = any(step.approver_user_id == approver_user_id for step in chain)
        if chain and not (is_in_chain or has_override_permission):
            raise HTTPException(
                status_code=422,
                detail="Approver is not authorized for this approval chain",
            )

        if chain:
            current_step = next((step for step in chain if step.status == "pending"), None)
            if current_step is None:
                raise HTTPException(
                    status_code=422,
                    detail="No pending approval step remains",
                )
            if not has_override_permission and current_step.approver_user_id != approver_user_id:
                raise HTTPException(
                    status_code=422,
                    detail="Approver is not authorized for the current approval step",
                )

            current_step.status = "approved"
            current_step.decision_notes = decision_notes
            current_step.decided_at = self.utcnow()
            self.db.flush()

            AuditService(self.db).write_audit_log(
                action="control_exception.approval_step_completed",
                entity_type="control_exception_approval",
                entity_id=current_step.id,
                organization_id=org_id,
                actor_user_id=approver_user_id,
                after_json={
                    "exception_id": str(exception_id),
                    "sequence": current_step.sequence,
                    "status": current_step.status,
                },
                metadata_json={"source": "api"},
            )

            if any(step.status == "pending" for step in chain):
                AuditService(self.db).write_audit_log(
                    action="control_exception.approved",
                    entity_type="control_exception",
                    entity_id=row.id,
                    organization_id=org_id,
                    actor_user_id=approver_user_id,
                    after_json={"status": row.status, "partial_approval": True},
                    metadata_json={"source": "api"},
                )
                return row

        now = self.utcnow()
        row.status = "active"
        row.approved_by_user_id = approver_user_id
        row.approved_at = now
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="control_exception.approved",
            entity_type="control_exception",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=approver_user_id,
            after_json={"status": row.status, "approved_at": now.isoformat()},
            metadata_json={"source": "api"},
        )
        return row

    def reject(
        self,
        exception_id: uuid.UUID,
        rejector_user_id: uuid.UUID,
        rejection_reason: str,
        org_id: uuid.UUID,
    ) -> ControlException:
        row = self.require_exception_in_org(org_id, exception_id)
        if row.status != "pending_approval":
            raise HTTPException(
                status_code=422,
                detail="Only pending_approval exceptions can be rejected",
            )
        if not rejection_reason.strip():
            raise HTTPException(
                status_code=422,
                detail="rejection_reason is required",
            )

        now = self.utcnow()
        row.status = "rejected"
        row.rejected_by_user_id = rejector_user_id
        row.rejected_at = now
        row.rejection_reason = rejection_reason.strip()

        pending_steps = self.db.execute(
            select(ControlExceptionApproval).where(
                ControlExceptionApproval.organization_id == org_id,
                ControlExceptionApproval.exception_id == exception_id,
                ControlExceptionApproval.status == "pending",
            )
        ).scalars().all()
        for step in pending_steps:
            step.status = "skipped"
            step.decision_notes = "Skipped due to rejection"
            step.decided_at = now

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="control_exception.rejected",
            entity_type="control_exception",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=rejector_user_id,
            after_json={"status": row.status, "rejection_reason": row.rejection_reason},
            metadata_json={"source": "api"},
        )
        return row

    def revoke(
        self,
        exception_id: uuid.UUID,
        revoker_user_id: uuid.UUID,
        revocation_reason: str,
        org_id: uuid.UUID,
    ) -> ControlException:
        row = self.require_exception_in_org(org_id, exception_id)
        if row.status != "active":
            raise HTTPException(
                status_code=422,
                detail="Only active exceptions can be revoked",
            )
        if not revocation_reason.strip():
            raise HTTPException(
                status_code=422,
                detail="revocation_reason is required",
            )

        now = self.utcnow()
        row.status = "revoked"
        row.revoked_by_user_id = revoker_user_id
        row.revoked_at = now
        row.revocation_reason = revocation_reason.strip()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="control_exception.revoked",
            entity_type="control_exception",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=revoker_user_id,
            after_json={"status": row.status, "revocation_reason": row.revocation_reason},
            metadata_json={"source": "api"},
        )
        return row

    def check_and_expire(self, org_id: uuid.UUID | None = None) -> int:
        today = self.utcdate()
        now = self.utcnow()
        filters = [
            ControlException.status == "active",
            ControlException.expiry_date.is_not(None),
            ControlException.expiry_date < today,
            ControlException.auto_expired_at.is_(None),
        ]
        if org_id is not None:
            filters.append(ControlException.organization_id == org_id)

        rows = self.db.execute(select(ControlException).where(*filters)).scalars().all()

        for row in rows:
            row.status = "expired"
            row.auto_expired_at = now

            alert = ControlMonitoringAlert(
                organization_id=row.organization_id,
                rule_id=None,
                definition_id=None,
                control_id=row.control_id,
                alert_type="manual",
                severity="high",
                status="open",
                title=f"Control exception expired: {row.title}",
                description=(
                    f"Control exception expired. control_id={row.control_id} "
                    f"exception_id={row.id} expiry_date={row.expiry_date}"
                ),
                alert_context_json={
                    "control_id": str(row.control_id),
                    "exception_id": str(row.id),
                    "expiry_date": str(row.expiry_date) if row.expiry_date else None,
                    "event": "control_exception_expired",
                },
            )
            self.db.add(alert)
            self.db.flush()

            AuditService(self.db).write_audit_log(
                action="control_exception.expired",
                entity_type="control_exception",
                entity_id=row.id,
                organization_id=row.organization_id,
                actor_user_id=None,
                after_json={"status": row.status, "auto_expired_at": row.auto_expired_at.isoformat()},
                metadata_json={"source": "system"},
            )

        return len(rows)

    def get_control_exception_status(
        self,
        control_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> ControlException | None:
        return self.db.execute(
            select(ControlException)
            .where(
                ControlException.organization_id == org_id,
                ControlException.control_id == control_id,
                ControlException.status == "active",
            )
            .order_by(ControlException.created_at.desc())
        ).scalar_one_or_none()

    def summary(self, org_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        today = self.utcdate()
        window_end = today + timedelta(days=30)

        total = int(
            self.db.execute(
                select(func.count(ControlException.id)).where(ControlException.organization_id == org_id)
            ).scalar_one()
        )

        by_status_rows = self.db.execute(
            select(ControlException.status, func.count(ControlException.id))
            .where(ControlException.organization_id == org_id)
            .group_by(ControlException.status)
        ).all()
        by_type_rows = self.db.execute(
            select(ControlException.exception_type, func.count(ControlException.id))
            .where(ControlException.organization_id == org_id)
            .group_by(ControlException.exception_type)
        ).all()

        expiring_soon = int(
            self.db.execute(
                select(func.count(ControlException.id)).where(
                    ControlException.organization_id == org_id,
                    ControlException.status == "active",
                    ControlException.expiry_date.is_not(None),
                    ControlException.expiry_date >= today,
                    ControlException.expiry_date <= window_end,
                )
            ).scalar_one()
        )

        expired_unreviewed = int(
            self.db.execute(
                select(func.count(ControlException.id)).where(
                    ControlException.organization_id == org_id,
                    ControlException.status == "expired",
                    ControlException.revoked_at.is_(None),
                )
            ).scalar_one()
        )

        controls_with_active_exception = int(
            self.db.execute(
                select(func.count(distinct(ControlException.control_id))).where(
                    ControlException.organization_id == org_id,
                    ControlException.status == "active",
                )
            ).scalar_one()
        )

        review_overdue = int(
            self.db.execute(
                select(func.count(ControlException.id)).where(
                    ControlException.organization_id == org_id,
                    ControlException.status == "active",
                    ControlException.review_date.is_not(None),
                    ControlException.review_date < today,
                )
            ).scalar_one()
        )

        return {
            "total": total,
            "by_status": {str(key): int(value) for key, value in by_status_rows},
            "by_type": {str(key): int(value) for key, value in by_type_rows},
            "expiring_soon": expiring_soon,
            "expired_unreviewed": expired_unreviewed,
            "controls_with_active_exception": controls_with_active_exception,
            "review_overdue": review_overdue,
        }

    def list_exceptions(
        self,
        *,
        org_id: uuid.UUID,
        status_filter: str | None = None,
        control_id: uuid.UUID | None = None,
        owner_user_id: uuid.UUID | None = None,
        exception_type: str | None = None,
        include_expired: bool = False,
        expiring_within_days: int | None = None,
    ) -> list[ControlException]:
        today = self.utcdate()
        stmt = select(ControlException).where(ControlException.organization_id == org_id)

        if status_filter is not None:
            stmt = stmt.where(ControlException.status == status_filter)
        if control_id is not None:
            stmt = stmt.where(ControlException.control_id == control_id)
        if owner_user_id is not None:
            stmt = stmt.where(ControlException.owner_user_id == owner_user_id)
        if exception_type is not None:
            stmt = stmt.where(ControlException.exception_type == exception_type)
        if not include_expired:
            stmt = stmt.where(ControlException.status != "expired")
        if expiring_within_days is not None:
            end_date = today + timedelta(days=max(0, expiring_within_days))
            stmt = stmt.where(
                ControlException.expiry_date.is_not(None),
                ControlException.expiry_date >= today,
                ControlException.expiry_date <= end_date,
            )

        return self.db.execute(stmt.order_by(ControlException.created_at.desc())).scalars().all()

    def approval_steps(self, org_id: uuid.UUID, exception_id: uuid.UUID) -> list[ControlExceptionApproval]:
        return self.db.execute(
            select(ControlExceptionApproval)
            .where(
                ControlExceptionApproval.organization_id == org_id,
                ControlExceptionApproval.exception_id == exception_id,
            )
            .order_by(ControlExceptionApproval.sequence.asc(), ControlExceptionApproval.created_at.asc())
        ).scalars().all()


def run_daily_control_exception_expiry_sweep(db: Session) -> dict:
    expired_count = ControlExceptionService(db).check_and_expire(org_id=None)
    return {"expired_count": expired_count, "records_processed": expired_count}
