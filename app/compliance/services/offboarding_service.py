from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.audit_engagement import AuditEngagement
from app.models.compliance_deadline import ComplianceDeadline
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.membership import Membership
from app.models.offboarding_configuration import OffboardingConfiguration
from app.models.offboarding_record import OffboardingRecord
from app.models.risk import Risk
from app.models.task import Task
from app.models.user import User
from app.models.user_session import UserSession
from app.models.vendor import Vendor
from app.services.activation_token_service import ActivationTokenService
from app.services.audit_service import AuditService
from app.services.rbac_service import RBACService


class OffboardingService:
    TASK_TERMINAL_STATUSES: tuple[str, ...] = ("completed", "cancelled", "archived")

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _ensure_user_in_org(self, org_id: uuid.UUID, user_id: uuid.UUID, *, field_name: str, require_active: bool = False) -> None:
        stmt = select(Membership).where(
            Membership.organization_id == org_id,
            Membership.user_id == user_id,
        )
        if require_active:
            stmt = stmt.where(Membership.status == "active")
        membership = self.db.execute(stmt).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name} must belong to the organization",
            )

        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} must belong to the organization")
        if require_active and (not user.is_active or user.status != "active"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name} must belong to the organization",
            )

    def get_or_create_config(self, org_id: uuid.UUID) -> OffboardingConfiguration:
        row = self.db.execute(
            select(OffboardingConfiguration).where(OffboardingConfiguration.organization_id == org_id)
        ).scalar_one_or_none()
        if row is not None:
            return row

        row = OffboardingConfiguration(
            organization_id=org_id,
            default_successor_id=None,
            require_successor_on_deactivate=False,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def update_config(self, org_id: uuid.UUID, data, user_id: uuid.UUID) -> OffboardingConfiguration:
        row = self.get_or_create_config(org_id)
        updates = data.model_dump(exclude_unset=True)

        if "default_successor_id" in updates and updates["default_successor_id"] is not None:
            self._ensure_user_in_org(org_id, updates["default_successor_id"], field_name="default_successor_id", require_active=True)

        before = {
            "default_successor_id": str(row.default_successor_id) if row.default_successor_id else None,
            "require_successor_on_deactivate": bool(row.require_successor_on_deactivate),
        }
        for field, value in updates.items():
            setattr(row, field, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="offboarding.config_updated",
            entity_type="offboarding_configuration",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={
                "default_successor_id": str(row.default_successor_id) if row.default_successor_id else None,
                "require_successor_on_deactivate": bool(row.require_successor_on_deactivate),
            },
            metadata_json={"source": "api"},
        )
        return row

    def _count_stmt(self, stmt):
        return self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    def validate_offboarding(self, org_id: uuid.UUID, deactivated_user_id: uuid.UUID) -> dict:
        self._ensure_user_in_org(org_id, deactivated_user_id, field_name="deactivated_user_id", require_active=False)

        risks_to_reassign = int(self.db.execute(select(func.count(Risk.id)).where(
            Risk.organization_id == org_id,
            Risk.owner_user_id == deactivated_user_id,
        )).scalar_one())
        controls_to_reassign = int(self.db.execute(select(func.count(Control.id)).where(
            Control.organization_id == org_id,
            Control.owner_user_id == deactivated_user_id,
        )).scalar_one())
        tasks_to_reassign = int(self.db.execute(select(func.count(Task.id)).where(
            Task.organization_id == org_id,
            Task.owner_user_id == deactivated_user_id,
            Task.status.notin_(self.TASK_TERMINAL_STATUSES),
        )).scalar_one())
        policies_to_reassign = int(self.db.execute(select(func.count(CompliancePolicy.id)).where(
            CompliancePolicy.organization_id == org_id,
            CompliancePolicy.owner_user_id == deactivated_user_id,
        )).scalar_one())
        vendors_to_reassign = int(self.db.execute(select(func.count(Vendor.id)).where(
            Vendor.organization_id == org_id,
            Vendor.owner_user_id == deactivated_user_id,
        )).scalar_one())

        audit_engagements = self.db.execute(
            select(AuditEngagement).where(AuditEngagement.organization_id == org_id)
        ).scalars().all()
        audit_engagements_to_reassign = 0
        deactivated_user_str = str(deactivated_user_id)
        for row in audit_engagements:
            assigned = [str(item) for item in (row.assigned_auditor_ids or [])]
            if deactivated_user_str in assigned:
                audit_engagements_to_reassign += 1

        payload = {
            "risks_to_reassign": risks_to_reassign,
            "controls_to_reassign": controls_to_reassign,
            "tasks_to_reassign": tasks_to_reassign,
            "policies_to_reassign": policies_to_reassign,
            "vendors_to_reassign": vendors_to_reassign,
            "audit_engagements_to_reassign": audit_engagements_to_reassign,
            "total": risks_to_reassign
            + controls_to_reassign
            + tasks_to_reassign
            + policies_to_reassign
            + vendors_to_reassign
            + audit_engagements_to_reassign,
        }
        return payload

    def run_offboarding(
        self,
        org_id: uuid.UUID,
        deactivated_user_id: uuid.UUID,
        successor_id: uuid.UUID | None,
        executed_by: uuid.UUID,
    ) -> OffboardingRecord:
        config = self.get_or_create_config(org_id)
        chosen_successor = successor_id or config.default_successor_id

        if config.require_successor_on_deactivate and chosen_successor is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="successor_id is required when offboarding policy requires successor")

        self._ensure_user_in_org(org_id, deactivated_user_id, field_name="deactivated_user_id", require_active=False)

        if chosen_successor is not None:
            self._ensure_user_in_org(org_id, chosen_successor, field_name="successor_id", require_active=True)
            if deactivated_user_id == chosen_successor:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="deactivated_user_id and successor_id cannot be the same")

        deactivated_membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == deactivated_user_id,
            )
        ).scalar_one_or_none()
        if deactivated_membership is not None and deactivated_membership.status == "active":
            RBACService.assert_not_last_owner_change(
                self.db,
                target_membership=deactivated_membership,
                organization_id=org_id,
                deactivating=True,
            )

        counts: dict[str, int] = {
            "risks": 0,
            "controls": 0,
            "tasks": 0,
            "policies": 0,
            "vendors": 0,
            "audit_engagements": 0,
        }

        with self.db.begin_nested():
            # Revoke login/session access for the deactivated user before touching
            # ownership records. Reassigning data without also cutting off login
            # access is a security bug on its own -- an "offboarded" teammate who
            # can still authenticate still has full standing access to everything
            # their role permits, regardless of who now owns their old records.
            membership_status_before = deactivated_membership.status if deactivated_membership is not None else None
            activation_tokens_revoked = 0
            if deactivated_membership is not None and deactivated_membership.status != "inactive":
                deactivated_membership.status = "inactive"
                activation_tokens_revoked = ActivationTokenService(self.db).revoke_active_tokens_for_membership(
                    deactivated_membership.id
                )

            now = self.utcnow()
            active_sessions = self.db.execute(
                select(UserSession).where(
                    UserSession.organization_id == org_id,
                    UserSession.user_id == deactivated_user_id,
                    UserSession.status == "active",
                )
            ).scalars().all()
            for session_row in active_sessions:
                session_row.status = "revoked"
                session_row.revoked_at = now
                session_row.revoked_by = executed_by
            sessions_revoked = len(active_sessions)

            # If this was the user's only active membership across the whole platform,
            # fully deactivate their account too -- otherwise `POST /auth/login` still
            # lets them authenticate (it only checks User.is_active/status, not
            # membership status) and, having no active membership anywhere, would even
            # issue them a legacy session-less token via the "no active membership"
            # fallback path.
            deactivated_user_row = self.db.execute(select(User).where(User.id == deactivated_user_id)).scalar_one_or_none()
            remaining_active_membership_elsewhere = self.db.execute(
                select(Membership.id).where(
                    Membership.user_id == deactivated_user_id,
                    Membership.status == "active",
                    Membership.organization_id != org_id,
                )
            ).scalar_one_or_none()
            user_account_deactivated = False
            if (
                deactivated_user_row is not None
                and remaining_active_membership_elsewhere is None
                and (deactivated_user_row.is_active or deactivated_user_row.status == "active")
            ):
                deactivated_user_row.is_active = False
                deactivated_user_row.status = "deactivated"
                user_account_deactivated = True

            self.db.flush()

            if chosen_successor is not None:
                result = self.db.execute(
                    update(Risk)
                    .where(Risk.organization_id == org_id, Risk.owner_user_id == deactivated_user_id)
                    .values(owner_user_id=chosen_successor)
                )
                counts["risks"] = int(result.rowcount or 0)

                result = self.db.execute(
                    update(Control)
                    .where(Control.organization_id == org_id, Control.owner_user_id == deactivated_user_id)
                    .values(owner_user_id=chosen_successor)
                )
                counts["controls"] = int(result.rowcount or 0)

                result = self.db.execute(
                    update(CompliancePolicy)
                    .where(CompliancePolicy.organization_id == org_id, CompliancePolicy.owner_user_id == deactivated_user_id)
                    .values(owner_user_id=chosen_successor)
                )
                counts["policies"] = int(result.rowcount or 0)

                result = self.db.execute(
                    update(Vendor)
                    .where(Vendor.organization_id == org_id, Vendor.owner_user_id == deactivated_user_id)
                    .values(owner_user_id=chosen_successor)
                )
                counts["vendors"] = int(result.rowcount or 0)

                # Also reassign compliance deadlines when owner field exists in schema.
                self.db.execute(
                    update(ComplianceDeadline)
                    .where(ComplianceDeadline.organization_id == org_id, ComplianceDeadline.owner_user_id == deactivated_user_id)
                    .values(owner_user_id=chosen_successor)
                )

            # Tasks are always handled.  When a successor is provided they get reassigned;
            # otherwise they are intentionally orphaned so dashboards can surface them.
            result = self.db.execute(
                update(Task)
                .where(
                    Task.organization_id == org_id,
                    Task.owner_user_id == deactivated_user_id,
                    Task.status.notin_(self.TASK_TERMINAL_STATUSES),
                )
                .values(owner_user_id=chosen_successor)
            )
            counts["tasks"] = int(result.rowcount or 0)

            # Audit engagements use assigned_auditor_ids JSON list; replace user id in-array.
            if chosen_successor is not None:
                deactivated_user_str = str(deactivated_user_id)
                successor_str = str(chosen_successor)
                engagement_rows = self.db.execute(
                    select(AuditEngagement).where(AuditEngagement.organization_id == org_id)
                ).scalars().all()
                for engagement in engagement_rows:
                    current = [str(item) for item in (engagement.assigned_auditor_ids or [])]
                    if deactivated_user_str not in current:
                        continue
                    engagement.assigned_auditor_ids = [successor_str if item == deactivated_user_str else item for item in current]
                    counts["audit_engagements"] += 1

            total_reassigned = int(sum(counts.values()))
            record = OffboardingRecord(
                organization_id=org_id,
                deactivated_user_id=deactivated_user_id,
                successor_id=chosen_successor,
                records_reassigned=dict(counts),
                total_reassigned=total_reassigned,
                executed_by=executed_by,
            )
            self.db.add(record)
            self.db.flush()

            metadata = {
                "source": "api",
                "reason": f"offboarding_user_{deactivated_user_id}",
                "successor_id": str(chosen_successor),
            }
            AuditService(self.db).write_audit_log(
                action="offboarding.login_access_revoked",
                entity_type="membership",
                entity_id=deactivated_membership.id if deactivated_membership is not None else None,
                organization_id=org_id,
                actor_user_id=executed_by,
                before_json={"membership_status": membership_status_before},
                after_json={
                    "membership_status": "inactive" if deactivated_membership is not None else None,
                    "sessions_revoked": sessions_revoked,
                    "activation_tokens_revoked": activation_tokens_revoked,
                    "user_account_deactivated": user_account_deactivated,
                },
                metadata_json=metadata,
            )
            AuditService(self.db).write_audit_log(
                action="offboarding.risks_reassigned",
                entity_type="risk",
                organization_id=org_id,
                actor_user_id=executed_by,
                after_json={"count": counts["risks"]},
                metadata_json=metadata,
            )
            AuditService(self.db).write_audit_log(
                action="offboarding.controls_reassigned",
                entity_type="control",
                organization_id=org_id,
                actor_user_id=executed_by,
                after_json={"count": counts["controls"]},
                metadata_json=metadata,
            )
            AuditService(self.db).write_audit_log(
                action="offboarding.tasks_reassigned",
                entity_type="task",
                organization_id=org_id,
                actor_user_id=executed_by,
                after_json={"count": counts["tasks"]},
                metadata_json=metadata,
            )
            AuditService(self.db).write_audit_log(
                action="offboarding.policies_reassigned",
                entity_type="compliance_policy",
                organization_id=org_id,
                actor_user_id=executed_by,
                after_json={"count": counts["policies"]},
                metadata_json=metadata,
            )
            AuditService(self.db).write_audit_log(
                action="offboarding.vendors_reassigned",
                entity_type="vendor",
                organization_id=org_id,
                actor_user_id=executed_by,
                after_json={"count": counts["vendors"]},
                metadata_json=metadata,
            )
            AuditService(self.db).write_audit_log(
                action="offboarding.audit_engagements_reassigned",
                entity_type="audit_engagement",
                organization_id=org_id,
                actor_user_id=executed_by,
                after_json={"count": counts["audit_engagements"]},
                metadata_json=metadata,
            )
            AuditService(self.db).write_audit_log(
                action="offboarding.executed",
                entity_type="offboarding_record",
                entity_id=record.id,
                organization_id=org_id,
                actor_user_id=executed_by,
                after_json={"records_reassigned": dict(counts), "total_reassigned": total_reassigned},
                metadata_json=metadata,
            )

        return record

    def get_offboarding_records(self, org_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> list[OffboardingRecord]:
        stmt = select(OffboardingRecord).where(OffboardingRecord.organization_id == org_id)
        if user_id is not None:
            stmt = stmt.where(OffboardingRecord.deactivated_user_id == user_id)
        return self.db.execute(stmt.order_by(OffboardingRecord.executed_at.desc())).scalars().all()

    def get_offboarding_record(self, org_id: uuid.UUID, record_id: uuid.UUID) -> OffboardingRecord:
        row = self.db.execute(
            select(OffboardingRecord).where(
                OffboardingRecord.organization_id == org_id,
                OffboardingRecord.id == record_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offboarding record not found")
        return row
