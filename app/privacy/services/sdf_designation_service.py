import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.services.audit_schedule_service import AuditScheduleService
from app.models.audit_schedule import AuditSchedule
from app.models.data_asset import DataAsset
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization import Organization
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.sdf_designation_suggestion import SDFDesignationSuggestion
from app.services.audit_service import AuditService

# DPDP Rules 2025 (Rule 13) does not publish a fixed numeric volume/sensitivity threshold
# for Significant Data Fiduciary designation — that is left to a separate Central
# Government notification of specific fiduciaries/classes. This count is therefore a
# heuristic starting point for human review, not a legal determination.
SENSITIVE_ASSET_SUGGESTION_THRESHOLD = 5

SENSITIVE_CLASSIFICATION_TYPES = {"sensitive_personal_data", "health_data", "financial_data"}

INDIA_DPDP_FRAMEWORK_CODE = "INDIA_DPDP"
SDF_OBLIGATION_REFERENCE_CODES = ("DPDP-SDF-1", "DPDP-SDF-2", "DPDP-SDF-3")
SDF_AUDIT_OBLIGATION_REFERENCE_CODE = "DPDP-SDF-2"
SDF_AI_IMPACT_OBLIGATION_REFERENCE_CODE = "DPDP-SDF-3"


class SDFDesignationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def suggest_sdf_designation(self, org_id: uuid.UUID) -> SDFDesignationSuggestion:
        total_asset_count = int(
            self.db.execute(select(func.count(DataAsset.id)).where(DataAsset.organization_id == org_id)).scalar_one() or 0
        )
        sensitive_asset_count = int(
            self.db.execute(
                select(func.count(DataAsset.id)).where(
                    DataAsset.organization_id == org_id,
                    DataAsset.classification_type.in_(SENSITIVE_CLASSIFICATION_TYPES),
                    DataAsset.classification_confirmed.is_(True),
                )
            ).scalar_one()
            or 0
        )

        suggested = sensitive_asset_count >= SENSITIVE_ASSET_SUGGESTION_THRESHOLD
        rationale = (
            f"{sensitive_asset_count} of {total_asset_count} data assets are confirmed as "
            f"sensitive_personal_data/health_data/financial_data, "
            f"{'meeting' if suggested else 'below'} the internal review threshold of "
            f"{SENSITIVE_ASSET_SUGGESTION_THRESHOLD}. DPDP Rules 2025 (Rule 13) does not publish a "
            "fixed numeric SDF threshold — this is a heuristic signal for human review, not a "
            "legal determination of Significant Data Fiduciary status."
        )
        now = self.utcnow()
        row = SDFDesignationSuggestion(
            organization_id=org_id,
            suggested_sdf=suggested,
            sensitive_asset_count=sensitive_asset_count,
            total_asset_count=total_asset_count,
            rationale=rationale,
            provenance_json={
                "threshold": SENSITIVE_ASSET_SUGGESTION_THRESHOLD,
                "classification_types_considered": sorted(SENSITIVE_CLASSIFICATION_TYPES),
            },
            created_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="sdf_designation.suggested",
            entity_type="sdf_designation_suggestion",
            entity_id=row.id,
            organization_id=org_id,
            after_json={"suggested_sdf": suggested, "sensitive_asset_count": sensitive_asset_count},
            metadata_json={"source": "system"},
        )
        return row

    def _require_dpdp_obligation(self, reference_code: str) -> Obligation | None:
        framework = self.db.execute(select(Framework).where(Framework.code == INDIA_DPDP_FRAMEWORK_CODE)).scalar_one_or_none()
        if framework is None:
            return None
        return self.db.execute(
            select(Obligation).where(
                Obligation.framework_id == framework.id,
                Obligation.reference_code == reference_code,
            )
        ).scalar_one_or_none()

    def _set_obligation_applicability(
        self, org_id: uuid.UUID, obligation: Obligation, applicability_status: str, justification: str | None = None
    ) -> OrganizationObligationState:
        state = self.db.execute(
            select(OrganizationObligationState).where(
                OrganizationObligationState.organization_id == org_id,
                OrganizationObligationState.obligation_id == obligation.id,
            )
        ).scalar_one_or_none()
        if state is None:
            state = OrganizationObligationState(
                organization_id=org_id,
                obligation_id=obligation.id,
                applicability_status=applicability_status,
                implementation_status="not_started",
                justification=justification,
            )
            self.db.add(state)
        else:
            state.applicability_status = applicability_status
            if justification is not None:
                state.justification = justification
        self.db.flush()
        return state

    def confirm_sdf_designation(
        self,
        org_id: uuid.UUID,
        confirmed_value: bool,
        sdf_category: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> dict:
        org = self.db.get(Organization, org_id)
        if org is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

        latest_suggestion = self.db.execute(
            select(SDFDesignationSuggestion)
            .where(SDFDesignationSuggestion.organization_id == org_id)
            .order_by(SDFDesignationSuggestion.created_at.desc())
        ).scalars().first()

        now = self.utcnow()
        if latest_suggestion is not None and not latest_suggestion.confirmed:
            latest_suggestion.confirmed = True
            latest_suggestion.confirmed_value = confirmed_value
            latest_suggestion.confirmed_at = now
            latest_suggestion.confirmed_by_user_id = actor_user_id

        org.is_significant_data_fiduciary = confirmed_value
        org.sdf_category = sdf_category if confirmed_value else None
        self.db.flush()

        obligation_state_ids: list[uuid.UUID] = []
        audit_schedule_id: uuid.UUID | None = None

        for ref_code in SDF_OBLIGATION_REFERENCE_CODES:
            obligation = self._require_dpdp_obligation(ref_code)
            if obligation is None:
                continue
            justification = None
            if confirmed_value and ref_code == SDF_AI_IMPACT_OBLIGATION_REFERENCE_CODE:
                justification = (
                    "Algorithmic impact assessment should be evidenced via the AI Governance "
                    "domain's AIRiskAssessment/ISO42001ConformityTracker records for this org's "
                    "AI systems (DPDP Rules 2025, Rule 13)."
                )
            state = self._set_obligation_applicability(
                org_id,
                obligation,
                "applicable" if confirmed_value else "not_applicable",
                justification=justification,
            )
            obligation_state_ids.append(state.id)

        if confirmed_value:
            audit_obligation = self._require_dpdp_obligation(SDF_AUDIT_OBLIGATION_REFERENCE_CODE)
            framework = self.db.execute(select(Framework).where(Framework.code == INDIA_DPDP_FRAMEWORK_CODE)).scalar_one_or_none()
            if framework is not None:
                existing_schedule = self.db.execute(
                    select(AuditSchedule).where(
                        AuditSchedule.organization_id == org_id,
                        AuditSchedule.framework_id == framework.id,
                        AuditSchedule.is_active.is_(True),
                    )
                ).scalar_one_or_none()
                if existing_schedule is None and actor_user_id is not None:
                    schedule = AuditScheduleService(self.db).create_schedule(
                        org_id,
                        title="DPDP Significant Data Fiduciary — Annual Independent Data Audit",
                        recurrence="annual",
                        lead_time_days=30,
                        audit_type="internal_readiness",
                        framework_id=framework.id,
                        created_by=actor_user_id,
                    )
                    audit_schedule_id = schedule.id
                elif existing_schedule is not None:
                    audit_schedule_id = existing_schedule.id
            _ = audit_obligation  # already covered by the applicability loop above

        AuditService(self.db).write_audit_log(
            action="sdf_designation.confirmed",
            entity_type="organization",
            entity_id=org_id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "is_significant_data_fiduciary": confirmed_value,
                "sdf_category": org.sdf_category,
                "obligation_state_ids": [str(i) for i in obligation_state_ids],
                "audit_schedule_id": str(audit_schedule_id) if audit_schedule_id else None,
            },
            metadata_json={"source": "api"},
        )

        return {
            "organization_id": org_id,
            "is_significant_data_fiduciary": org.is_significant_data_fiduciary,
            "sdf_category": org.sdf_category,
            "obligation_state_ids": obligation_state_ids,
            "audit_schedule_id": audit_schedule_id,
        }
