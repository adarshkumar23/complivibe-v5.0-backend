import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment

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
