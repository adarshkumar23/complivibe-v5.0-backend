import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.policy_risk_mapping import PolicyRiskMapping
from app.models.risk import Risk
from app.schemas.policy_risk_mapping import PolicyRiskMappingUpdate
from app.services.audit_service import AuditService


class PolicyRiskMappingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

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

    def require_risk_in_org(self, org_id: uuid.UUID, risk_id: uuid.UUID) -> Risk:
        row = self.db.execute(
            select(Risk).where(
                Risk.organization_id == org_id,
                Risk.id == risk_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
        return row

    def require_mapping(self, org_id: uuid.UUID, mapping_id: uuid.UUID) -> PolicyRiskMapping:
        row = self.db.execute(
            select(PolicyRiskMapping).where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.id == mapping_id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy-risk mapping not found")
        return row

    def create_mapping(
        self,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        risk_id: uuid.UUID,
        mitigation_strength: str,
        notes: str | None,
        mapped_by: uuid.UUID,
    ) -> PolicyRiskMapping:
        self.require_policy_in_org(org_id, policy_id)
        self.require_risk_in_org(org_id, risk_id)

        duplicate = self.db.execute(
            select(PolicyRiskMapping).where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.policy_id == policy_id,
                PolicyRiskMapping.risk_id == risk_id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Policy-risk mapping already exists")

        row = PolicyRiskMapping(
            organization_id=org_id,
            policy_id=policy_id,
            risk_id=risk_id,
            mitigation_strength=mitigation_strength,
            notes=notes,
            mapped_by=mapped_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_risk_mapping.created",
            entity_type="policy_risk_mapping",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=mapped_by,
            after_json={
                "policy_id": str(row.policy_id),
                "risk_id": str(row.risk_id),
                "mitigation_strength": row.mitigation_strength,
                "notes": row.notes,
            },
            metadata_json={"source": "api"},
        )

        return row

    def list_mappings_for_policy(
        self,
        org_id: uuid.UUID,
        policy_id: uuid.UUID,
        mitigation_strength: str | None = None,
    ) -> list[tuple[PolicyRiskMapping, Risk]]:
        self.require_policy_in_org(org_id, policy_id)
        stmt = (
            select(PolicyRiskMapping, Risk)
            .join(Risk, Risk.id == PolicyRiskMapping.risk_id)
            .where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.policy_id == policy_id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
        )
        if mitigation_strength is not None:
            stmt = stmt.where(PolicyRiskMapping.mitigation_strength == mitigation_strength)

        return self.db.execute(stmt.order_by(PolicyRiskMapping.created_at.desc())).all()

    def list_mappings_for_risk(
        self,
        org_id: uuid.UUID,
        risk_id: uuid.UUID,
        mitigation_strength: str | None = None,
    ) -> list[tuple[PolicyRiskMapping, CompliancePolicy]]:
        self.require_risk_in_org(org_id, risk_id)
        stmt = (
            select(PolicyRiskMapping, CompliancePolicy)
            .join(CompliancePolicy, CompliancePolicy.id == PolicyRiskMapping.policy_id)
            .where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.risk_id == risk_id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
        )
        if mitigation_strength is not None:
            stmt = stmt.where(PolicyRiskMapping.mitigation_strength == mitigation_strength)

        return self.db.execute(stmt.order_by(PolicyRiskMapping.created_at.desc())).all()

    def list_mappings(
        self,
        org_id: uuid.UUID,
        *,
        policy_id: uuid.UUID | None = None,
        risk_id: uuid.UUID | None = None,
        mitigation_strength: str | None = None,
    ) -> list[tuple[PolicyRiskMapping, CompliancePolicy, Risk]]:
        stmt = (
            select(PolicyRiskMapping, CompliancePolicy, Risk)
            .join(CompliancePolicy, CompliancePolicy.id == PolicyRiskMapping.policy_id)
            .join(Risk, Risk.id == PolicyRiskMapping.risk_id)
            .where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
        )
        if policy_id is not None:
            self.require_policy_in_org(org_id, policy_id)
            stmt = stmt.where(PolicyRiskMapping.policy_id == policy_id)
        if risk_id is not None:
            self.require_risk_in_org(org_id, risk_id)
            stmt = stmt.where(PolicyRiskMapping.risk_id == risk_id)
        if mitigation_strength is not None:
            stmt = stmt.where(PolicyRiskMapping.mitigation_strength == mitigation_strength)

        return self.db.execute(stmt.order_by(PolicyRiskMapping.created_at.desc())).all()

    def get_mapping(self, org_id: uuid.UUID, mapping_id: uuid.UUID) -> tuple[PolicyRiskMapping, CompliancePolicy, Risk]:
        row = self.require_mapping(org_id, mapping_id)
        policy = self.require_policy_in_org(org_id, row.policy_id)
        risk = self.require_risk_in_org(org_id, row.risk_id)
        return row, policy, risk

    def update_mapping(
        self,
        org_id: uuid.UUID,
        mapping_id: uuid.UUID,
        payload: PolicyRiskMappingUpdate,
        actor_id: uuid.UUID,
    ) -> PolicyRiskMapping:
        row = self.require_mapping(org_id, mapping_id)
        before = {
            "mitigation_strength": row.mitigation_strength,
            "notes": row.notes,
        }

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_risk_mapping.updated",
            entity_type="policy_risk_mapping",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json=before,
            after_json={
                "mitigation_strength": row.mitigation_strength,
                "notes": row.notes,
            },
            metadata_json={"source": "api"},
        )

        return row

    def delete_mapping(self, org_id: uuid.UUID, mapping_id: uuid.UUID, actor_id: uuid.UUID) -> PolicyRiskMapping:
        row = self.require_mapping(org_id, mapping_id)
        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="policy_risk_mapping.deleted",
            entity_type="policy_risk_mapping",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "policy_id": str(row.policy_id),
                "risk_id": str(row.risk_id),
                "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
            },
            metadata_json={"source": "api"},
        )

        return row

    def get_policy_risk_coverage(self, org_id: uuid.UUID, policy_id: uuid.UUID) -> dict:
        self.require_policy_in_org(org_id, policy_id)

        rows = self.db.execute(
            select(PolicyRiskMapping.mitigation_strength, Risk.severity)
            .join(Risk, Risk.id == PolicyRiskMapping.risk_id)
            .where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.policy_id == policy_id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
        ).all()

        by_strength = {"full": 0, "partial": 0, "indirect": 0}
        severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for strength, severity_value in rows:
            by_strength[str(strength)] = by_strength.get(str(strength), 0) + 1
            severity[str(severity_value)] = severity.get(str(severity_value), 0) + 1

        active_mapping_exists = (
            select(PolicyRiskMapping.id)
            .where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.risk_id == Risk.id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
            .exists()
        )
        unmapped_risk_count = int(
            self.db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == org_id,
                    ~active_mapping_exists,
                )
            ).scalar_one()
        )

        return {
            "policy_id": policy_id,
            "total_risks_mapped": len(rows),
            "by_strength": by_strength,
            "risk_severity_breakdown": severity,
            "unmapped_risk_count": unmapped_risk_count,
        }

    def get_risk_policy_coverage(self, org_id: uuid.UUID, risk_id: uuid.UUID) -> dict:
        self.require_risk_in_org(org_id, risk_id)

        rows = self.db.execute(
            select(PolicyRiskMapping.mitigation_strength, CompliancePolicy.status)
            .join(CompliancePolicy, CompliancePolicy.id == PolicyRiskMapping.policy_id)
            .where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.risk_id == risk_id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
        ).all()

        by_strength = {"full": 0, "partial": 0, "indirect": 0}
        policy_statuses = {"active": 0, "draft": 0, "archived": 0}
        for strength, policy_status in rows:
            by_strength[str(strength)] = by_strength.get(str(strength), 0) + 1
            policy_statuses[str(policy_status)] = policy_statuses.get(str(policy_status), 0) + 1

        return {
            "risk_id": risk_id,
            "total_policies_mapped": len(rows),
            "by_strength": by_strength,
            "has_full_coverage": by_strength.get("full", 0) > 0,
            "policy_statuses": policy_statuses,
        }

    def get_org_mapping_summary(self, org_id: uuid.UUID) -> dict:
        total_mappings = int(
            self.db.execute(
                select(func.count(PolicyRiskMapping.id)).where(
                    PolicyRiskMapping.organization_id == org_id,
                    PolicyRiskMapping.deleted_at.is_(None),
                )
            ).scalar_one()
        )

        policies_with_mappings = int(
            self.db.execute(
                select(func.count(func.distinct(PolicyRiskMapping.policy_id))).where(
                    PolicyRiskMapping.organization_id == org_id,
                    PolicyRiskMapping.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        risks_with_mappings = int(
            self.db.execute(
                select(func.count(func.distinct(PolicyRiskMapping.risk_id))).where(
                    PolicyRiskMapping.organization_id == org_id,
                    PolicyRiskMapping.deleted_at.is_(None),
                )
            ).scalar_one()
        )

        total_policies = int(
            self.db.execute(
                select(func.count(CompliancePolicy.id)).where(CompliancePolicy.organization_id == org_id)
            ).scalar_one()
        )
        total_risks = int(
            self.db.execute(select(func.count(Risk.id)).where(Risk.organization_id == org_id)).scalar_one()
        )

        policies_without_mappings = max(total_policies - policies_with_mappings, 0)
        risks_without_mappings = max(total_risks - risks_with_mappings, 0)
        coverage_rate = 0.0 if total_risks == 0 else (risks_with_mappings / total_risks) * 100.0

        top_rows = self.db.execute(
            select(
                Risk.id,
                Risk.title,
                Risk.severity,
                func.count(PolicyRiskMapping.id).label("policy_count"),
            )
            .join(PolicyRiskMapping, PolicyRiskMapping.risk_id == Risk.id)
            .where(
                Risk.organization_id == org_id,
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
            .group_by(Risk.id, Risk.title, Risk.severity)
            .order_by(func.count(PolicyRiskMapping.id).desc(), Risk.created_at.desc())
            .limit(5)
        ).all()
        top_covered_risks = [
            {
                "risk_id": risk_id,
                "risk_title": risk_title,
                "severity": severity,
                "policy_count": int(policy_count),
            }
            for risk_id, risk_title, severity, policy_count in top_rows
        ]

        mapped_exists = (
            select(PolicyRiskMapping.id)
            .where(
                PolicyRiskMapping.organization_id == org_id,
                PolicyRiskMapping.risk_id == Risk.id,
                PolicyRiskMapping.deleted_at.is_(None),
            )
            .exists()
        )
        uncovered_rows = self.db.execute(
            select(Risk.id, Risk.title, Risk.severity, Risk.status)
            .where(
                Risk.organization_id == org_id,
                ~mapped_exists,
            )
            .order_by(Risk.created_at.desc())
            .limit(10)
        ).all()
        uncovered_risks = [
            {
                "risk_id": risk_id,
                "risk_title": risk_title,
                "severity": severity,
                "status": risk_status,
            }
            for risk_id, risk_title, severity, risk_status in uncovered_rows
        ]

        return {
            "total_mappings": total_mappings,
            "policies_with_mappings": policies_with_mappings,
            "policies_without_mappings": policies_without_mappings,
            "risks_with_mappings": risks_with_mappings,
            "risks_without_mappings": risks_without_mappings,
            "coverage_rate": round(coverage_rate, 2),
            "top_covered_risks": top_covered_risks,
            "uncovered_risks": uncovered_risks,
        }
