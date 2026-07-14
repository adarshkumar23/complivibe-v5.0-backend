import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.control import Control
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_risk_score import VendorRiskScore
from app.services.audit_service import AuditService
from app.services.vendor_concentration_risk_service import VendorConcentrationRiskService

LIKELIHOOD_MAP: dict[str, int] = {
    "very_low": 1,
    "low": 2,
    "medium": 3,
    "high": 4,
    "very_high": 5,
}
IMPACT_MAP: dict[str, int] = {
    "very_low": 1,
    "low": 2,
    "medium": 3,
    "high": 4,
    "very_high": 5,
}


class VendorRiskService:
    """Manual vendor likelihood x impact scoring.

    ``VendorRiskScore`` is the point-in-time manual risk score history and the
    latest manual score updates ``Vendor.risk_tier`` as the cached vendor-list
    tier. Questionnaire scoring is a separate answer-rule subsystem with its
    own 0-100 scale; it may also update the cached tier, but it does not create
    synthetic ``VendorRiskScore`` rows because no real likelihood/impact axes
    exist for those questionnaire totals.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def require_vendor_in_org(self, organization_id: uuid.UUID, vendor_id: uuid.UUID) -> Vendor:
        row = self.db.execute(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
        return row

    def require_control_in_org(self, organization_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        row = self.db.execute(
            select(Control).where(
                Control.id == control_id,
                Control.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return row

    def require_assessment_in_org(self, organization_id: uuid.UUID, vendor_id: uuid.UUID, assessment_id: uuid.UUID) -> VendorAssessment:
        row = self.db.execute(
            select(VendorAssessment).where(
                VendorAssessment.id == assessment_id,
                VendorAssessment.organization_id == organization_id,
                VendorAssessment.vendor_id == vendor_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor assessment not found")
        return row

    def create_risk_score(
        self,
        *,
        organization_id: uuid.UUID,
        vendor_id: uuid.UUID,
        assessment_id: uuid.UUID | None,
        likelihood: str,
        impact: str,
        notes: str | None,
        scored_by_user_id: uuid.UUID,
        triggered_by: str = "user_action",
        confirm_override: bool = False,
    ) -> tuple[VendorRiskScore, int | None]:
        vendor = self.require_vendor_in_org(organization_id, vendor_id)
        if assessment_id is not None:
            self.require_assessment_in_org(organization_id, vendor_id, assessment_id)

        previous_score_row = self.db.execute(
            select(VendorRiskScore)
            .where(
                VendorRiskScore.organization_id == organization_id,
                VendorRiskScore.vendor_id == vendor_id,
            )
            .order_by(VendorRiskScore.created_at.desc(), VendorRiskScore.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        previous_score = previous_score_row.inherent_risk_score if previous_score_row is not None else None

        inherent_risk_score, risk_level, explanation = self.compute_score_payload(
            likelihood=likelihood,
            impact=impact,
        )

        row = VendorRiskScore(
            organization_id=organization_id,
            vendor_id=vendor_id,
            assessment_id=assessment_id,
            likelihood=likelihood,
            impact=impact,
            inherent_risk_score=inherent_risk_score,
            risk_level=risk_level,
            score_explanation_json=explanation,
            scored_by_user_id=scored_by_user_id,
            notes=notes,
            created_at=datetime.now(UTC),
        )
        self.db.add(row)
        self.db.flush()

        previous_tier = vendor.risk_tier
        previous_tier_source = vendor.risk_tier_source
        if previous_tier != row.risk_level:
            # A manually-set tier (see Vendor.risk_tier_source) represents a human's
            # explicit judgment call -- e.g. a compliance officer who knows context
            # this likelihood x impact scoring doesn't capture. A routine recompute
            # must not silently clobber that; it needs an explicit confirm_override.
            if vendor.risk_tier_source == "manual" and not confirm_override:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Vendor risk_tier was manually set to '{previous_tier}'. This score "
                        f"would overwrite it with '{row.risk_level}'. Pass confirm_override=true "
                        "to proceed."
                    ),
                )
            vendor.risk_tier = row.risk_level
            vendor.risk_tier_source = "computed"
            self.db.flush()
            AuditService(self.db).write_audit_log(
                action="vendor.risk_tier.updated",
                entity_type="vendor",
                entity_id=vendor.id,
                organization_id=organization_id,
                actor_user_id=scored_by_user_id,
                before_json={"risk_tier": previous_tier, "risk_tier_source": previous_tier_source},
                after_json={
                    "risk_tier": vendor.risk_tier,
                    "risk_tier_source": vendor.risk_tier_source,
                    "vendor_risk_score_id": str(row.id),
                    "inherent_risk_score": row.inherent_risk_score,
                    "manual_override_confirmed": confirm_override,
                },
                metadata_json={"source": "vendor_risk_score"},
            )
            # risk_tier is a direct input to T1-6's concentration HHI calculation
            # (see sanctions_screening.py for the same pattern). Without this, a
            # manual likelihood x impact score that escalates/de-escalates a vendor's
            # tier would leave an already-tracked org's concentration detection stale
            # until an unrelated vendor update or supply-chain change happened to
            # trigger a recompute.
            self._refresh_concentration_risk(
                organization_id=organization_id,
                actor_user_id=scored_by_user_id,
                trigger="vendor_risk_score.created",
            )

        EventBus.get_instance().emit(
            EventType.VENDOR_SCORE_UPDATED,
            EventPayload(
                org_id=organization_id,
                entity_type="vendor",
                entity_id=vendor_id,
                event_type=EventType.VENDOR_SCORE_UPDATED,
                previous_value=previous_score,
                new_value=row.inherent_risk_score,
                triggered_by=triggered_by,
                db=self.db,
                triggered_by_user_id=scored_by_user_id,
            ),
        )

        return row, previous_score

    def _refresh_concentration_risk(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        trigger: str,
    ) -> None:
        outcome = VendorConcentrationRiskService(self.db).recompute_if_tracked(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        if outcome is None:
            return
        detection, risk_created, state_changed = outcome
        if not state_changed:
            return
        AuditService(self.db).write_audit_log(
            action="vendor_concentration_risk.recomputed",
            entity_type="vendor_concentration_risk_detection",
            entity_id=detection.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "status": detection.status,
                "hhi_score": detection.hhi_score,
                "risk_id": str(detection.risk_id) if detection.risk_id else None,
            },
            metadata_json={"source": trigger, "risk_created": risk_created},
        )

    @staticmethod
    def risk_level_from_score(score: int) -> str:
        if score <= 4:
            return "low"
        if score <= 9:
            return "medium"
        if score <= 16:
            return "high"
        return "critical"

    @classmethod
    def compute_score_payload(cls, *, likelihood: str, impact: str) -> tuple[int, str, dict]:
        likelihood_value = LIKELIHOOD_MAP.get(likelihood)
        impact_value = IMPACT_MAP.get(impact)
        if likelihood_value is None or impact_value is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid likelihood or impact value")

        inherent_risk_score = likelihood_value * impact_value
        risk_level = cls.risk_level_from_score(inherent_risk_score)
        explanation = {
            "likelihood_value": likelihood_value,
            "impact_value": impact_value,
            "formula": "likelihood_value * impact_value",
            "thresholds": {
                "low": [1, 4],
                "medium": [5, 9],
                "high": [10, 16],
                "critical": [17, 25],
            },
            "provenance": "manual_vendor_risk_scoring_v1",
        }
        return inherent_risk_score, risk_level, explanation
