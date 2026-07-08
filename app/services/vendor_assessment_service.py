import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.membership import Membership
from app.models.user import User
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_assessment_question import VendorAssessmentQuestion
from app.services.audit_service import AuditService

# Statuses in which an assessment is still "in flight" -- a completed or
# cancelled assessment is never stale regardless of its due_date.
VENDOR_ASSESSMENT_OPEN_STATUSES = {"draft", "in_progress", "under_review"}


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

    @staticmethod
    def is_overdue(assessment: VendorAssessment, *, today: date | None = None) -> bool:
        """Mirrors the DORA ICT-register staleness rule (dora_service._is_register_gap):
        an assessment still in a non-terminal status whose due_date has passed is a
        real compliance gap, not a cosmetic one -- generic vendor assessments deserve
        the exact same signal DORA critical-vendor entries already get.
        """
        if assessment.status not in VENDOR_ASSESSMENT_OPEN_STATUSES:
            return False
        if assessment.due_date is None:
            return False
        reference_date = today if today is not None else datetime.now(UTC).date()
        return assessment.due_date < reference_date

    def overdue_vendor_ids(self, organization_id: uuid.UUID) -> set[uuid.UUID]:
        today = datetime.now(UTC).date()
        rows = self.db.execute(
            select(VendorAssessment.vendor_id).where(
                VendorAssessment.organization_id == organization_id,
                VendorAssessment.status.in_(VENDOR_ASSESSMENT_OPEN_STATUSES),
                VendorAssessment.due_date.is_not(None),
                VendorAssessment.due_date < today,
            )
        ).scalars().all()
        return set(rows)

    def sync_staleness(
        self,
        organization_id: uuid.UUID,
        vendor: Vendor,
        assessment: VendorAssessment,
        *,
        actor_user_id: uuid.UUID | None,
    ) -> None:
        """Cascade an overdue vendor assessment into the same 3 places the DORA
        ICT-register staleness path already lands in (dora_service._sync_risk_register):
        (1) a Risk register entry, (2) a real ControlMonitoringAlert (surfaced via
        /compliance/monitoring/alerts), and (3) an audit log entry linking them.
        Idempotent per assessment (guarded by VendorAssessment.risk_id), so repeated
        syncs on an already-flagged assessment don't spawn duplicate risks/alerts.
        """
        from app.services.risk_service import RiskService

        if not self.is_overdue(assessment) or assessment.risk_id is not None:
            return

        description = (
            f"Vendor assessment '{assessment.title}' for vendor '{vendor.name}' is overdue: "
            f"due date {assessment.due_date.isoformat()} has passed and the assessment is still "
            f"'{assessment.status}'. An overdue vendor assessment means the vendor's risk posture "
            "has not been re-verified on schedule."
        )

        created_by = actor_user_id or assessment.created_by_user_id
        risk = RiskService(self.db).create_risk_from_service(
            organization_id=organization_id,
            title=f"Vendor assessment overdue: {vendor.name}",
            description=description,
            category="third_party",
            likelihood=3,
            impact=3,
            treatment_strategy="mitigate",
            risk_context_external=(
                "Vendor risk assessment past its due date and not completed; vendor risk "
                "posture has not been re-verified on the required cadence."
            ),
            metadata_json={
                "source": "vendor_assessment",
                "vendor_id": str(vendor.id),
                "vendor_assessment_id": str(assessment.id),
                "reason": "assessment_overdue",
            },
            created_by_user_id=created_by,
            audit_source="vendor_assessment",
        )
        assessment.risk_id = risk.id

        alert = ControlMonitoringAlert(
            organization_id=organization_id,
            alert_type="vendor_assessment_overdue",
            severity="medium",
            status="open",
            title=f"Vendor assessment overdue: {vendor.name}",
            description=description,
            alert_context_json={
                "vendor_id": str(vendor.id),
                "vendor_assessment_id": str(assessment.id),
                "due_date": assessment.due_date.isoformat(),
                "risk_id": str(risk.id),
                "event": "vendor_assessment_overdue",
            },
        )
        self.db.add(alert)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_assessment.risk_linked",
            entity_type="vendor_assessment",
            entity_id=assessment.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "risk_id": str(risk.id),
                "alert_id": str(alert.id),
                "reason": "assessment_overdue",
            },
            metadata_json={"source": "vendor_assessment"},
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

    def sweep_overdue_assessments(self, organization_id: uuid.UUID | None = None) -> dict[str, int]:
        """Catches assessments that drift into overdue purely by the clock ticking
        (no create/update call ever touched them again) -- the same gap the DORA
        register cascade has, since it too only fires on create/update. Idempotent
        via VendorAssessment.risk_id, same as sync_staleness.
        """
        today = datetime.now(UTC).date()
        stmt = select(VendorAssessment).where(
            VendorAssessment.status.in_(VENDOR_ASSESSMENT_OPEN_STATUSES),
            VendorAssessment.due_date.is_not(None),
            VendorAssessment.due_date < today,
            VendorAssessment.risk_id.is_(None),
        )
        if organization_id is not None:
            stmt = stmt.where(VendorAssessment.organization_id == organization_id)

        rows = self.db.execute(stmt).scalars().all()
        flagged = 0
        for assessment in rows:
            vendor = self.db.execute(select(Vendor).where(Vendor.id == assessment.vendor_id)).scalar_one_or_none()
            if vendor is None:
                continue
            self.sync_staleness(
                assessment.organization_id,
                vendor,
                assessment,
                actor_user_id=None,
            )
            if assessment.risk_id is not None:
                flagged += 1
        self.db.flush()
        return {"vendor_assessments_flagged_overdue": flagged}


def run_daily_vendor_assessment_staleness_sweep(db: Session) -> dict[str, int]:
    return VendorAssessmentService(db).sweep_overdue_assessments()
