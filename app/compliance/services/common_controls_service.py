import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.common_control_evidence_coverage import CommonControlEvidenceCoverage
from app.models.common_control_mapping import CommonControlMapping
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.user import User
from app.schemas.common_controls import CommonControlMappingCreate, CommonControlMappingUpdate
from app.services.audit_service import AuditService


class CommonControlsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def require_control_in_org(self, org_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        row = self.db.execute(
            select(Control).where(
                Control.organization_id == org_id,
                Control.id == control_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return row

    def require_framework(self, framework_id: uuid.UUID) -> Framework:
        row = self.db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
        return row

    def require_obligation(self, obligation_id: uuid.UUID) -> Obligation:
        row = self.db.execute(select(Obligation).where(Obligation.id == obligation_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obligation not found")
        return row

    def require_active_framework_for_org(self, org_id: uuid.UUID, framework_id: uuid.UUID) -> OrganizationFramework:
        row = self.db.execute(
            select(OrganizationFramework).where(
                OrganizationFramework.organization_id == org_id,
                OrganizationFramework.framework_id == framework_id,
                OrganizationFramework.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=422,
                detail="Framework is not active for this organization",
            )
        return row

    def require_mapping_in_org(self, org_id: uuid.UUID, mapping_id: uuid.UUID) -> CommonControlMapping:
        row = self.db.execute(
            select(CommonControlMapping).where(
                CommonControlMapping.organization_id == org_id,
                CommonControlMapping.id == mapping_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Common control mapping not found")
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

    def create_mapping(
        self,
        control_id: uuid.UUID,
        framework_id: uuid.UUID,
        obligation_id: uuid.UUID,
        data: CommonControlMappingCreate,
        org_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
    ) -> CommonControlMapping:
        control = self.require_control_in_org(org_id, control_id)
        framework = self.require_framework(framework_id)
        obligation = self.require_obligation(obligation_id)
        self.require_active_framework_for_org(org_id, framework_id)

        if obligation.framework_id != framework.id:
            raise HTTPException(
                status_code=422,
                detail="obligation_id must belong to framework_id",
            )

        existing = self.db.execute(
            select(CommonControlMapping.id).where(
                CommonControlMapping.organization_id == org_id,
                CommonControlMapping.control_id == control_id,
                CommonControlMapping.framework_id == framework_id,
                CommonControlMapping.obligation_id == obligation_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=422,
                detail="Duplicate common control mapping",
            )

        if data.verified_by_user_id is not None:
            self.ensure_active_member(org_id, data.verified_by_user_id, field_name="verified_by_user_id")

        now = self.utcnow()
        row = CommonControlMapping(
            organization_id=org_id,
            control_id=control_id,
            framework_id=framework_id,
            obligation_id=obligation_id,
            section_reference=data.section_reference,
            mapping_rationale=data.mapping_rationale,
            mapping_strength=data.mapping_strength,
            verified_by_user_id=data.verified_by_user_id,
            verified_at=now if data.verified_by_user_id else None,
            status="active",
            created_by_user_id=created_by_user_id,
        )
        self.db.add(row)
        self.db.flush()

        # Keep denormalized common-control fields aligned for fast filtering/listing.
        control.is_common_control = True
        if not control.common_control_tag:
            control.common_control_tag = framework.code.lower()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="common_control.mapping_created",
            entity_type="common_control_mapping",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by_user_id,
            after_json={
                "control_id": str(row.control_id),
                "framework_id": str(row.framework_id),
                "obligation_id": str(row.obligation_id),
                "mapping_strength": row.mapping_strength,
                "status": row.status,
            },
            metadata_json={"source": "api"},
        )
        return row

    def update_mapping(
        self,
        mapping_id: uuid.UUID,
        data: CommonControlMappingUpdate,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> CommonControlMapping:
        row = self.require_mapping_in_org(org_id, mapping_id)
        before = {
            "section_reference": row.section_reference,
            "mapping_rationale": row.mapping_rationale,
            "mapping_strength": row.mapping_strength,
            "status": row.status,
            "verified_by_user_id": str(row.verified_by_user_id) if row.verified_by_user_id else None,
        }

        changes = data.model_dump(exclude_unset=True)
        if "verified_by_user_id" in changes and changes["verified_by_user_id"] is not None:
            self.ensure_active_member(org_id, changes["verified_by_user_id"], field_name="verified_by_user_id")
            row.verified_at = self.utcnow()
        for field, value in changes.items():
            setattr(row, field, value)
        self.db.flush()

        after = {
            "section_reference": row.section_reference,
            "mapping_rationale": row.mapping_rationale,
            "mapping_strength": row.mapping_strength,
            "status": row.status,
            "verified_by_user_id": str(row.verified_by_user_id) if row.verified_by_user_id else None,
        }
        AuditService(self.db).write_audit_log(
            action="common_control.mapping_updated",
            entity_type="common_control_mapping",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=after,
            metadata_json={"source": "api"},
        )
        return row

    def deactivate_mapping(self, mapping_id: uuid.UUID, org_id: uuid.UUID, actor_user_id: uuid.UUID) -> CommonControlMapping:
        row = self.require_mapping_in_org(org_id, mapping_id)
        before_status = row.status
        row.status = "inactive"
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="common_control.mapping_deactivated",
            entity_type="common_control_mapping",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json={"status": before_status},
            after_json={"status": row.status},
            metadata_json={"source": "api"},
        )
        return row

    def add_evidence_coverage(
        self,
        org_id: uuid.UUID,
        control_id: uuid.UUID,
        evidence_id: uuid.UUID,
        mapping_id: uuid.UUID,
        coverage_status: str,
        coverage_notes: str | None,
        actor_user_id: uuid.UUID,
    ) -> CommonControlEvidenceCoverage:
        self.require_control_in_org(org_id, control_id)
        mapping = self.require_mapping_in_org(org_id, mapping_id)

        evidence = self.db.execute(
            select(EvidenceItem).where(
                EvidenceItem.organization_id == org_id,
                EvidenceItem.id == evidence_id,
            )
        ).scalar_one_or_none()
        if evidence is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

        if mapping.control_id != control_id:
            raise HTTPException(
                status_code=422,
                detail="mapping_id does not belong to control_id",
            )

        existing = self.db.execute(
            select(CommonControlEvidenceCoverage.id).where(
                CommonControlEvidenceCoverage.organization_id == org_id,
                CommonControlEvidenceCoverage.control_id == control_id,
                CommonControlEvidenceCoverage.evidence_id == evidence_id,
                CommonControlEvidenceCoverage.mapping_id == mapping_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=422,
                detail="Duplicate evidence coverage mapping",
            )

        now = self.utcnow()
        row = CommonControlEvidenceCoverage(
            organization_id=org_id,
            control_id=control_id,
            evidence_id=evidence_id,
            mapping_id=mapping_id,
            coverage_status=coverage_status,
            coverage_notes=coverage_notes,
            assessed_by_user_id=actor_user_id,
            assessed_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="common_control.evidence_coverage_added",
            entity_type="common_control_evidence_coverage",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "control_id": str(control_id),
                "evidence_id": str(evidence_id),
                "mapping_id": str(mapping_id),
                "coverage_status": coverage_status,
            },
            metadata_json={"source": "api"},
        )
        return row

    def list_mappings(
        self,
        org_id: uuid.UUID,
        *,
        control_id: uuid.UUID | None = None,
        framework_id: uuid.UUID | None = None,
        mapping_strength: str | None = None,
        status_value: str | None = None,
    ) -> list[CommonControlMapping]:
        stmt = select(CommonControlMapping).where(CommonControlMapping.organization_id == org_id)
        if control_id is not None:
            stmt = stmt.where(CommonControlMapping.control_id == control_id)
        if framework_id is not None:
            stmt = stmt.where(CommonControlMapping.framework_id == framework_id)
        if mapping_strength is not None:
            stmt = stmt.where(CommonControlMapping.mapping_strength == mapping_strength)
        if status_value is not None:
            stmt = stmt.where(CommonControlMapping.status == status_value)
        return self.db.execute(stmt.order_by(CommonControlMapping.created_at.desc())).scalars().all()

    def get_coverage_report(self, control_id: uuid.UUID, org_id: uuid.UUID) -> dict:
        control = self.require_control_in_org(org_id, control_id)

        mappings = self.db.execute(
            select(CommonControlMapping, Framework, Obligation)
            .join(Framework, Framework.id == CommonControlMapping.framework_id)
            .join(Obligation, Obligation.id == CommonControlMapping.obligation_id)
            .where(
                CommonControlMapping.organization_id == org_id,
                CommonControlMapping.control_id == control_id,
                CommonControlMapping.status != "inactive",
            )
            .order_by(Framework.name.asc(), Obligation.reference_code.asc())
        ).all()

        framework_map: dict[uuid.UUID, dict] = {}
        obligation_coverages: list[float] = []

        for mapping, framework, obligation in mappings:
            fw_entry = framework_map.setdefault(
                framework.id,
                {
                    "framework_id": framework.id,
                    "framework_name": framework.name,
                    "obligations": [],
                },
            )

            coverage_rows = self.db.execute(
                select(CommonControlEvidenceCoverage, EvidenceItem)
                .join(EvidenceItem, EvidenceItem.id == CommonControlEvidenceCoverage.evidence_id)
                .where(
                    CommonControlEvidenceCoverage.organization_id == org_id,
                    CommonControlEvidenceCoverage.mapping_id == mapping.id,
                    CommonControlEvidenceCoverage.control_id == control_id,
                )
                .order_by(EvidenceItem.created_at.desc())
            ).all()

            evidence_coverage = [
                {
                    "evidence_id": evidence.id,
                    "evidence_title": evidence.title,
                    "coverage_status": coverage.coverage_status,
                    "expiry_date": evidence.valid_until.date() if evidence.valid_until else None,
                }
                for coverage, evidence in coverage_rows
            ]

            total_evidence = len(evidence_coverage)
            covering = sum(1 for item in evidence_coverage if item["coverage_status"] == "covers")
            partial = sum(1 for item in evidence_coverage if item["coverage_status"] == "partial")
            insufficient = sum(1 for item in evidence_coverage if item["coverage_status"] == "insufficient")
            coverage_pct = float((covering / total_evidence) * 100.0) if total_evidence > 0 else 0.0
            obligation_coverages.append(coverage_pct)

            fw_entry["obligations"].append(
                {
                    "obligation_id": obligation.id,
                    "section_reference": mapping.section_reference,
                    "mapping_strength": mapping.mapping_strength,
                    "evidence_coverage": evidence_coverage,
                    "coverage_summary": {
                        "total_evidence": total_evidence,
                        "covering": covering,
                        "partial": partial,
                        "insufficient": insufficient,
                        "coverage_pct": round(coverage_pct, 2),
                    },
                }
            )

        frameworks_covered: list[dict] = []
        for fw in framework_map.values():
            obligations = fw["obligations"]
            fw_pct = float(sum(o["coverage_summary"]["coverage_pct"] for o in obligations) / len(obligations)) if obligations else 0.0
            frameworks_covered.append(
                {
                    "framework_id": fw["framework_id"],
                    "framework_name": fw["framework_name"],
                    "obligations": obligations,
                    "framework_coverage_pct": round(fw_pct, 2),
                }
            )

        total_obligations = sum(len(fw["obligations"]) for fw in frameworks_covered)
        overall_coverage_pct = float(sum(obligation_coverages) / len(obligation_coverages)) if obligation_coverages else 0.0

        return {
            "control": {"id": control.id, "name": control.title, "status": control.status},
            "frameworks_covered": frameworks_covered,
            "total_frameworks": len(frameworks_covered),
            "total_obligations": total_obligations,
            "overall_coverage_pct": round(overall_coverage_pct, 2),
        }

    def get_evidence_reuse_report(self, org_id: uuid.UUID) -> dict:
        rows = self.db.execute(
            select(
                CommonControlEvidenceCoverage.evidence_id,
                EvidenceItem.title,
                func.count(distinct(CommonControlEvidenceCoverage.mapping_id)).label("reuse_count"),
            )
            .join(EvidenceItem, EvidenceItem.id == CommonControlEvidenceCoverage.evidence_id)
            .where(CommonControlEvidenceCoverage.organization_id == org_id)
            .group_by(CommonControlEvidenceCoverage.evidence_id, EvidenceItem.title)
            .order_by(func.count(distinct(CommonControlEvidenceCoverage.mapping_id)).desc(), EvidenceItem.title.asc())
        ).all()

        total_evidence_items = int(
            self.db.execute(
                select(func.count(distinct(CommonControlEvidenceCoverage.evidence_id))).where(
                    CommonControlEvidenceCoverage.organization_id == org_id,
                )
            ).scalar_one()
        )

        reused_evidence: list[dict] = []
        for evidence_id, evidence_title, reuse_count in rows:
            if int(reuse_count) <= 1:
                continue
            details = self.db.execute(
                select(Framework.name, Obligation.reference_code)
                .join(CommonControlMapping, CommonControlMapping.framework_id == Framework.id)
                .join(Obligation, Obligation.id == CommonControlMapping.obligation_id)
                .join(CommonControlEvidenceCoverage, CommonControlEvidenceCoverage.mapping_id == CommonControlMapping.id)
                .where(
                    CommonControlEvidenceCoverage.organization_id == org_id,
                    CommonControlEvidenceCoverage.evidence_id == evidence_id,
                )
            ).all()

            frameworks_covered = sorted({name for name, _ in details})
            obligations_covered = sorted({ref for _, ref in details if ref})
            reused_evidence.append(
                {
                    "evidence_id": evidence_id,
                    "evidence_title": evidence_title,
                    "reuse_count": int(reuse_count),
                    "frameworks_covered": frameworks_covered,
                    "obligations_covered": obligations_covered,
                }
            )

        reused_count = len(reused_evidence)
        reuse_rate = float(reused_count / total_evidence_items) if total_evidence_items > 0 else 0.0

        return {
            "reused_evidence": reused_evidence,
            "total_evidence_items": total_evidence_items,
            "reused_count": reused_count,
            "reuse_rate": round(reuse_rate, 4),
        }

    def get_common_controls_summary(self, org_id: uuid.UUID) -> dict:
        active_mappings = self.db.execute(
            select(CommonControlMapping).where(
                CommonControlMapping.organization_id == org_id,
                CommonControlMapping.status == "active",
            )
        ).scalars().all()

        total_mappings = len(active_mappings)
        by_mapping_strength = {"full": 0, "partial": 0, "compensating": 0}
        for row in active_mappings:
            by_mapping_strength[row.mapping_strength] = by_mapping_strength.get(row.mapping_strength, 0) + 1

        per_control = self.db.execute(
            select(
                CommonControlMapping.control_id,
                func.count(distinct(CommonControlMapping.framework_id)).label("framework_count"),
                func.count(distinct(CommonControlMapping.obligation_id)).label("obligation_count"),
            )
            .where(
                CommonControlMapping.organization_id == org_id,
                CommonControlMapping.status == "active",
            )
            .group_by(CommonControlMapping.control_id)
            .order_by(func.count(distinct(CommonControlMapping.framework_id)).desc())
        ).all()

        common_controls = [row for row in per_control if int(row.framework_count) >= 2]
        total_common_controls = len(common_controls)

        if common_controls:
            control_ids = [row.control_id for row in common_controls]
            frameworks_with_common_controls = int(
                self.db.execute(
                    select(func.count(distinct(CommonControlMapping.framework_id))).where(
                        CommonControlMapping.organization_id == org_id,
                        CommonControlMapping.status == "active",
                        CommonControlMapping.control_id.in_(control_ids),
                    )
                ).scalar_one()
            )
        else:
            frameworks_with_common_controls = 0

        top_common_controls: list[dict] = []
        for row in common_controls[:5]:
            control = self.db.execute(
                select(Control).where(
                    Control.organization_id == org_id,
                    Control.id == row.control_id,
                )
            ).scalar_one_or_none()
            if control is None:
                continue
            top_common_controls.append(
                {
                    "control_id": control.id,
                    "control_name": control.title,
                    "framework_count": int(row.framework_count),
                    "obligation_count": int(row.obligation_count),
                }
            )

        return {
            "total_common_controls": total_common_controls,
            "total_mappings": total_mappings,
            "by_mapping_strength": by_mapping_strength,
            "frameworks_with_common_controls": frameworks_with_common_controls,
            "top_common_controls": top_common_controls,
        }
