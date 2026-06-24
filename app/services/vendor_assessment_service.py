import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.user import User
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_assessment_question import VendorAssessmentQuestion


class VendorAssessmentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

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

    def require_assessment_in_org(
        self,
        organization_id: uuid.UUID,
        vendor_id: uuid.UUID,
        assessment_id: uuid.UUID,
    ) -> VendorAssessment:
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

    def require_question_in_org(
        self,
        organization_id: uuid.UUID,
        assessment_id: uuid.UUID,
        question_id: uuid.UUID,
    ) -> VendorAssessmentQuestion:
        row = self.db.execute(
            select(VendorAssessmentQuestion).where(
                VendorAssessmentQuestion.id == question_id,
                VendorAssessmentQuestion.organization_id == organization_id,
                VendorAssessmentQuestion.assessment_id == assessment_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor assessment question not found")
        return row

    def ensure_active_member(self, organization_id: uuid.UUID, user_id: uuid.UUID, *, field_name: str) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} must be an active member of the organization",
            )

        user = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} must be an active member of the organization",
            )
        return user

    @staticmethod
    def ensure_assessment_mutable(assessment: VendorAssessment) -> None:
        if assessment.status in {"completed", "cancelled"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Completed or cancelled assessments cannot update questions",
            )

    def summary(self, organization_id: uuid.UUID, vendor_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        total_assessments = int(
            self.db.execute(
                select(func.count(VendorAssessment.id)).where(
                    VendorAssessment.organization_id == organization_id,
                    VendorAssessment.vendor_id == vendor_id,
                )
            ).scalar_one()
        )

        completed_assessments = int(
            self.db.execute(
                select(func.count(VendorAssessment.id)).where(
                    VendorAssessment.organization_id == organization_id,
                    VendorAssessment.vendor_id == vendor_id,
                    VendorAssessment.status == "completed",
                )
            ).scalar_one()
        )
        cancelled_assessments = int(
            self.db.execute(
                select(func.count(VendorAssessment.id)).where(
                    VendorAssessment.organization_id == organization_id,
                    VendorAssessment.vendor_id == vendor_id,
                    VendorAssessment.status == "cancelled",
                )
            ).scalar_one()
        )

        by_status_rows = self.db.execute(
            select(VendorAssessment.status, func.count(VendorAssessment.id))
            .where(
                VendorAssessment.organization_id == organization_id,
                VendorAssessment.vendor_id == vendor_id,
            )
            .group_by(VendorAssessment.status)
        ).all()
        by_assessment_type_rows = self.db.execute(
            select(VendorAssessment.assessment_type, func.count(VendorAssessment.id))
            .where(
                VendorAssessment.organization_id == organization_id,
                VendorAssessment.vendor_id == vendor_id,
            )
            .group_by(VendorAssessment.assessment_type)
        ).all()
        by_overall_rating_rows = self.db.execute(
            select(VendorAssessment.overall_rating, func.count(VendorAssessment.id))
            .where(
                VendorAssessment.organization_id == organization_id,
                VendorAssessment.vendor_id == vendor_id,
            )
            .group_by(VendorAssessment.overall_rating)
        ).all()

        return {
            "total_assessments": total_assessments,
            "active_assessments": max(0, total_assessments - completed_assessments - cancelled_assessments),
            "completed_assessments": completed_assessments,
            "cancelled_assessments": cancelled_assessments,
            "by_status": {str(key): int(value) for key, value in by_status_rows},
            "by_assessment_type": {str(key): int(value) for key, value in by_assessment_type_rows},
            "by_overall_rating": {str(key): int(value) for key, value in by_overall_rating_rows},
        }
