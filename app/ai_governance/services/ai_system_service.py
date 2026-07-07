import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.signal_service import SignalService
from app.models.ai_system import AISystem
from app.models.membership import Membership
from app.models.user import User
from app.services.audit_service import AuditService


class AISystemService:
    ALLOWED_SYSTEM_TYPES = {"model", "use_case", "agent", "application", "data_pipeline"}
    ALLOWED_DEPLOYMENT_STATUSES = {
        "development",
        "staging",
        "limited_production",
        "production",
        "decommissioned",
    }
    ALLOWED_RISK_TIERS = {"prohibited", "high", "limited", "minimal", "unassessed"}

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _validate_owner(self, org_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        owner = self.db.execute(
            select(User.id)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == owner_id,
                Membership.organization_id == org_id,
                Membership.status == "active",
                User.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if owner is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="owner_id must be an active member of the organization",
            )

    def _validate_system_type(self, system_type: str) -> None:
        if system_type not in self.ALLOWED_SYSTEM_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid system_type")

    def _validate_status(self, deployment_status: str) -> None:
        if deployment_status not in self.ALLOWED_DEPLOYMENT_STATUSES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid deployment_status")

    def _validate_risk_tier(self, risk_tier: str | None) -> None:
        if risk_tier is None:
            return
        if risk_tier not in self.ALLOWED_RISK_TIERS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid risk_tier")

    def create_system(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> AISystem:
        self._validate_system_type(data.system_type)
        self._validate_status(data.deployment_status)
        self._validate_risk_tier(data.risk_tier)
        self._validate_owner(org_id, data.owner_id)

        row = AISystem(
            organization_id=org_id,
            name=data.name,
            system_type=data.system_type,
            description=data.description,
            owner_id=data.owner_id,
            business_owner_user_id=data.owner_id,
            vendor_id=data.vendor_id,
            deployment_status=data.deployment_status,
            lifecycle_status=data.deployment_status,
            risk_tier=data.risk_tier,
            data_sources_description=data.data_sources_description,
            purpose=data.purpose,
            intended_purpose=data.purpose,
            affected_population=data.affected_population,
            geographic_scope=data.geographic_scope,
            geography_json=data.geographic_scope,
            model_version=data.model_version,
            created_by=created_by,
            created_by_user_id=created_by,
            updated_by_user_id=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "system.registered",
            actor_id=created_by,
            actor_type="user",
            ai_system_id=row.id,
            event_data={
                "name": row.name,
                "system_type": row.system_type,
                "deployment_status": row.deployment_status,
            },
        )

        AuditService(self.db).write_audit_log(
            action="ai_system.created",
            entity_type="ai_system",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "name": row.name,
                "system_type": row.system_type,
                "deployment_status": row.deployment_status,
                "risk_tier": row.risk_tier,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    def list_systems(
        self,
        org_id: uuid.UUID,
        *,
        system_type: str | None = None,
        deployment_status: str | None = None,
        risk_tier: str | None = None,
        business_unit_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AISystem]:
        stmt = select(AISystem).where(
            AISystem.organization_id == org_id,
            AISystem.deleted_at.is_(None),
        )
        if system_type is not None:
            stmt = stmt.where(AISystem.system_type == system_type)
        if deployment_status is not None:
            stmt = stmt.where(AISystem.deployment_status == deployment_status)
        if risk_tier is not None:
            stmt = stmt.where(AISystem.risk_tier == risk_tier)
        if business_unit_id is not None:
            stmt = stmt.where(AISystem.business_unit_id == business_unit_id)

        return (
            self.db.execute(stmt.order_by(AISystem.created_at.desc()).offset(skip).limit(limit))
            .scalars()
            .all()
        )

    def update_system(self, org_id: uuid.UUID, system_id: uuid.UUID, data, actor_id: uuid.UUID) -> AISystem:
        row = self.get_system(org_id, system_id)
        before = {
            "name": row.name,
            "system_type": row.system_type,
            "deployment_status": row.deployment_status,
            "risk_tier": row.risk_tier,
        }

        payload = data.model_dump(exclude_unset=True)
        if "system_type" in payload:
            self._validate_system_type(payload["system_type"])
        if "deployment_status" in payload:
            self._validate_status(payload["deployment_status"])
        if "risk_tier" in payload:
            self._validate_risk_tier(payload["risk_tier"])
        if payload.get("owner_id") is not None:
            self._validate_owner(org_id, payload["owner_id"])

        for key, value in payload.items():
            setattr(row, key, value)

        if "owner_id" in payload:
            row.business_owner_user_id = row.owner_id
        if "deployment_status" in payload:
            row.lifecycle_status = row.deployment_status
        if "purpose" in payload:
            row.intended_purpose = row.purpose
        if "geographic_scope" in payload:
            row.geography_json = row.geographic_scope

        row.updated_by_user_id = actor_id
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ai_system.updated",
            entity_type="ai_system",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={
                "name": row.name,
                "system_type": row.system_type,
                "deployment_status": row.deployment_status,
                "risk_tier": row.risk_tier,
            },
            metadata_json={"source": "api"},
        )
        return row

    def update_deployment_status(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        new_status: str,
        actor_id: uuid.UUID,
    ) -> AISystem:
        self._validate_status(new_status)
        row = self.get_system(org_id, system_id)
        before_status = row.deployment_status
        if before_status == "decommissioned" and new_status != "decommissioned":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot transition from decommissioned to an active status",
            )

        row.deployment_status = new_status
        row.lifecycle_status = new_status
        row.updated_by_user_id = actor_id
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "system.status_changed",
            actor_id=actor_id,
            actor_type="user",
            ai_system_id=row.id,
            event_data={"from_status": before_status, "to_status": new_status},
        )

        AuditService(self.db).write_audit_log(
            action="ai_system.status_changed",
            entity_type="ai_system",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json={"deployment_status": before_status},
            after_json={"deployment_status": new_status},
            metadata_json={"source": "api"},
        )

        SignalService(self.db).emit_signal(
            org_id,
            row.id,
            signal_type="deployment_scope_expansion",
            description=f"System deployment status changed from {before_status} to {new_status}",
            actor_id=actor_id,
        )
        return row

    def get_summary(self, org_id: uuid.UUID) -> dict:
        # Aggregate in SQL rather than loading every AISystem row into memory --
        # with thousands of registered systems, a Python-side Counter over the
        # full result set is an unnecessary full materialization on every call.
        base_filter = (AISystem.organization_id == org_id, AISystem.deleted_at.is_(None))

        total = self.db.execute(select(func.count()).select_from(AISystem).where(*base_filter)).scalar_one()

        def _group_counts(column) -> dict[str, int]:
            rows = self.db.execute(
                select(column, func.count()).where(*base_filter).group_by(column)
            ).all()
            return {str(key) if key is not None else "unknown": int(count) for key, count in rows}

        by_type = _group_counts(AISystem.system_type)
        by_status = _group_counts(AISystem.deployment_status)
        by_tier_raw = _group_counts(AISystem.risk_tier)
        # Preserve the existing contract: unclassified systems are bucketed
        # under "unassessed" (not "unknown") in by_risk_tier.
        by_tier = {("unassessed" if key == "unknown" else key): count for key, count in by_tier_raw.items()}

        unclassified = self.db.execute(
            select(func.count()).select_from(AISystem).where(*base_filter, AISystem.risk_tier.is_(None))
        ).scalar_one()

        return {
            "total": int(total),
            "by_system_type": by_type,
            "by_deployment_status": by_status,
            "by_risk_tier": by_tier,
            "unclassified_count": int(unclassified),
        }

    def soft_delete_system(self, org_id: uuid.UUID, system_id: uuid.UUID, user_id: uuid.UUID) -> AISystem:
        row = self.get_system(org_id, system_id)
        if row.deployment_status != "decommissioned":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only decommissioned systems can be deleted",
            )

        row.deleted_at = self.utcnow()
        row.updated_by_user_id = user_id
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ai_system.deleted",
            entity_type="ai_system",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat()},
            metadata_json={"source": "api"},
        )
        return row
