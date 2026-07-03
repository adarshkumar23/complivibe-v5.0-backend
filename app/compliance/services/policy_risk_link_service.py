import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.policy_risk_link import PolicyRiskLink
from app.models.policy_risk_mapping import PolicyRiskMapping
from app.models.risk import Risk
from app.services.audit_service import AuditService


class PolicyRiskLinkService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_policy(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> CompliancePolicy:
        row = self.db.execute(
            select(CompliancePolicy).where(
                CompliancePolicy.organization_id == org_id,
                CompliancePolicy.id == policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance policy not found")
        return row

    def _require_risk(self, org_id: uuid.UUID, risk_id: uuid.UUID) -> Risk:
        row = self.db.execute(
            select(Risk).where(
                Risk.organization_id == org_id,
                Risk.id == risk_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
        return row

    def _sync_mapping_for_link(
        self,
        *,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        risk_id: uuid.UUID,
        mapped_by: uuid.UUID,
    ) -> None:
        mapping = self.db.execute(
            select(PolicyRiskMapping).where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.policy_id == policy_id,
                PolicyRiskMapping.risk_id == risk_id,
            )
        ).scalar_one_or_none()
        if mapping is None:
            mapping = PolicyRiskMapping(
                organization_id=org_id,
                policy_id=policy_id,
                risk_id=risk_id,
                mitigation_strength="partial",
                mapped_by=mapped_by,
            )
            self.db.add(mapping)
        elif mapping.deleted_at is not None:
            mapping.deleted_at = None
            mapping.mapped_by = mapped_by
        self.db.flush()

    def link_risk(
        self,
        *,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        risk_id: uuid.UUID,
        created_by: uuid.UUID,
        link_reason: str | None = None,
    ) -> PolicyRiskLink:
        self._require_policy(org_id, policy_id)
        self._require_risk(org_id, risk_id)
        existing = self.db.execute(
            select(PolicyRiskLink).where(
                PolicyRiskLink.organization_id == org_id,
                PolicyRiskLink.policy_id == policy_id,
                PolicyRiskLink.risk_id == risk_id,
            )
        ).scalar_one_or_none()
        if existing is not None and existing.status == "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Policy-risk link already exists")

        if existing is None:
            row = PolicyRiskLink(
                organization_id=org_id,
                policy_id=policy_id,
                risk_id=risk_id,
                link_reason=link_reason,
                status="active",
                created_by=created_by,
            )
            self.db.add(row)
        else:
            existing.status = "active"
            existing.link_reason = link_reason
            existing.unlinked_at = None
            existing.unlinked_by = None
            existing.unlink_reason = None
            row = existing
        self.db.flush()

        self._sync_mapping_for_link(
            org_id=org_id,
            policy_id=policy_id,
            risk_id=risk_id,
            mapped_by=created_by,
        )

        AuditService(self.db).write_audit_log(
            action="policy.risk_linked",
            entity_type="policy_risk_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            metadata_json={"policy_id": str(policy_id), "risk_id": str(risk_id)},
        )
        return row

    def unlink_risk(
        self,
        *,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        risk_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> None:
        row = self.db.execute(
            select(PolicyRiskLink).where(
                PolicyRiskLink.organization_id == org_id,
                PolicyRiskLink.policy_id == policy_id,
                PolicyRiskLink.risk_id == risk_id,
                PolicyRiskLink.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy-risk link not found")
        row.status = "inactive"
        row.unlinked_at = self.utcnow()
        row.unlinked_by = actor_user_id
        self.db.flush()

        mapping = self.db.execute(
            select(PolicyRiskMapping).where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.policy_id == policy_id,
                PolicyRiskMapping.risk_id == risk_id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if mapping is not None:
            mapping.deleted_at = self.utcnow()
            self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy.risk_unlinked",
            entity_type="policy_risk_link",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            metadata_json={"policy_id": str(policy_id), "risk_id": str(risk_id)},
        )

    def list_risks_for_policy(self, *, org_id: uuid.UUID, policy_id: uuid.UUID) -> list[Risk]:
        self._require_policy(org_id, policy_id)
        rows = self.db.execute(
            select(Risk)
            .join(PolicyRiskLink, PolicyRiskLink.risk_id == Risk.id)
            .where(
                PolicyRiskLink.organization_id == org_id,
                PolicyRiskLink.policy_id == policy_id,
                PolicyRiskLink.status == "active",
                Risk.organization_id == org_id,
            )
            .order_by(Risk.title.asc())
        ).scalars().all()
        return rows

    def list_policies_for_risk(self, *, org_id: uuid.UUID, risk_id: uuid.UUID) -> list[CompliancePolicy]:
        self._require_risk(org_id, risk_id)
        rows = self.db.execute(
            select(CompliancePolicy)
            .join(PolicyRiskLink, PolicyRiskLink.policy_id == CompliancePolicy.id)
            .where(
                PolicyRiskLink.organization_id == org_id,
                PolicyRiskLink.risk_id == risk_id,
                PolicyRiskLink.status == "active",
                CompliancePolicy.organization_id == org_id,
            )
            .order_by(CompliancePolicy.title.asc())
        ).scalars().all()
        return rows
