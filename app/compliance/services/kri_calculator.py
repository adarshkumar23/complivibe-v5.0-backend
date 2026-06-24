import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.risk_indicator import RiskIndicator
from app.models.task import Task
from app.models.vendor import Vendor
from app.services.audit_service import AuditService


class KRICalculator:
    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def utcdate() -> datetime.date:
        return datetime.now(UTC).date()

    @staticmethod
    def _to_float(value: float | int) -> float:
        return round(float(value), 4)

    @staticmethod
    def require_indicator_in_org(org_id: uuid.UUID, indicator_id: uuid.UUID, db: Session) -> RiskIndicator:
        indicator = db.execute(
            select(RiskIndicator).where(
                RiskIndicator.id == indicator_id,
                RiskIndicator.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if indicator is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk indicator not found")
        return indicator

    @staticmethod
    def calculate_control_expiry_rate(org_id: uuid.UUID, db: Session) -> float:
        now = KRICalculator.utcnow()
        horizon = now + timedelta(days=30)

        numerator = int(
            db.execute(
                select(func.count(func.distinct(Control.id)))
                .join(EvidenceControlLink, EvidenceControlLink.control_id == Control.id)
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    Control.organization_id == org_id,
                    Control.status == "active",
                    EvidenceControlLink.organization_id == org_id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == org_id,
                    EvidenceItem.status == "approved",
                    EvidenceItem.valid_until.is_not(None),
                    EvidenceItem.valid_until >= now,
                    EvidenceItem.valid_until <= horizon,
                )
            ).scalar_one()
        )
        denominator = int(
            db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == org_id,
                    Control.status == "active",
                )
            ).scalar_one()
        )
        return KRICalculator._to_float((numerator / denominator) if denominator else 0.0)

    @staticmethod
    def calculate_evidence_gap_rate(org_id: uuid.UUID, db: Session) -> float:
        approved_controls_subquery = (
            select(EvidenceControlLink.control_id)
            .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
            .where(
                EvidenceControlLink.organization_id == org_id,
                EvidenceControlLink.link_status == "active",
                EvidenceItem.organization_id == org_id,
                EvidenceItem.status == "approved",
            )
            .distinct()
        )
        numerator = int(
            db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == org_id,
                    Control.status == "active",
                    Control.id.not_in(approved_controls_subquery),
                )
            ).scalar_one()
        )
        denominator = int(
            db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == org_id,
                    Control.status == "active",
                )
            ).scalar_one()
        )
        return KRICalculator._to_float((numerator / denominator) if denominator else 0.0)

    @staticmethod
    def calculate_overdue_task_rate(org_id: uuid.UUID, db: Session) -> float:
        now = KRICalculator.utcnow()
        numerator = int(
            db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == org_id,
                    Task.status.in_(["open", "in_progress"]),
                    Task.due_date.is_not(None),
                    Task.due_date < now,
                )
            ).scalar_one()
        )
        denominator = int(
            db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == org_id,
                    Task.status.in_(["open", "in_progress"]),
                )
            ).scalar_one()
        )
        return KRICalculator._to_float((numerator / denominator) if denominator else 0.0)

    @staticmethod
    def calculate_vendor_high_risk_count(org_id: uuid.UUID, db: Session) -> float:
        count = int(
            db.execute(
                select(func.count(Vendor.id)).where(
                    Vendor.organization_id == org_id,
                    Vendor.risk_tier.in_(["critical", "high"]),
                    Vendor.status != "archived",
                )
            ).scalar_one()
        )
        return KRICalculator._to_float(count)

    @staticmethod
    def calculate_open_alert_count(org_id: uuid.UUID, db: Session) -> float:
        count = int(
            db.execute(
                select(func.count(ControlMonitoringAlert.id)).where(
                    ControlMonitoringAlert.organization_id == org_id,
                    ControlMonitoringAlert.status == "open",
                )
            ).scalar_one()
        )
        return KRICalculator._to_float(count)

    @staticmethod
    def calculate_policy_overdue_review(org_id: uuid.UUID, db: Session) -> float:
        today = KRICalculator.utcdate()
        count = int(
            db.execute(
                select(func.count(CompliancePolicy.id)).where(
                    CompliancePolicy.organization_id == org_id,
                    CompliancePolicy.status == "approved",
                    CompliancePolicy.review_due_date.is_not(None),
                    CompliancePolicy.review_due_date < today,
                    CompliancePolicy.archived_at.is_(None),
                )
            ).scalar_one()
        )
        return KRICalculator._to_float(count)

    @staticmethod
    def compute(indicator: RiskIndicator, db: Session) -> tuple[float | None, str]:
        if indicator.metric_type == "custom":
            return (float(indicator.current_value) if indicator.current_value is not None else None, indicator.status)

        dispatch = {
            "control_expiry_rate": KRICalculator.calculate_control_expiry_rate,
            "evidence_gap_rate": KRICalculator.calculate_evidence_gap_rate,
            "overdue_task_rate": KRICalculator.calculate_overdue_task_rate,
            "vendor_high_risk_count": KRICalculator.calculate_vendor_high_risk_count,
            "open_alert_count": KRICalculator.calculate_open_alert_count,
            "policy_overdue_review": KRICalculator.calculate_policy_overdue_review,
        }

        calculator = dispatch.get(indicator.metric_type)
        if calculator is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported metric_type")

        current_value = calculator(indicator.organization_id, db)
        if current_value >= float(indicator.critical_threshold):
            status_value = "red"
        elif current_value >= float(indicator.warning_threshold):
            status_value = "amber"
        else:
            status_value = "green"
        return current_value, status_value

    @staticmethod
    def recalculate_and_persist(
        indicator_id: uuid.UUID,
        org_id: uuid.UUID,
        db: Session,
        *,
        actor_user_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RiskIndicator:
        indicator = KRICalculator.require_indicator_in_org(org_id, indicator_id, db)

        previous_value = float(indicator.current_value) if indicator.current_value is not None else None
        previous_status = indicator.status

        if indicator.metric_type == "custom":
            AuditService(db).write_audit_log(
                action="risk_indicator.recalculated",
                entity_type="risk_indicator",
                entity_id=indicator.id,
                organization_id=org_id,
                actor_user_id=actor_user_id,
                before_json={"previous_value": previous_value, "previous_status": previous_status},
                after_json={"new_value": previous_value, "new_status": previous_status},
                metadata_json={
                    "source": "api",
                    "context_json": {
                        "previous_value": previous_value,
                        "new_value": previous_value,
                        "previous_status": previous_status,
                        "new_status": previous_status,
                        "custom_noop": True,
                    },
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
            db.commit()
            db.refresh(indicator)
            return indicator

        computed_value, derived_status = KRICalculator.compute(indicator, db)
        indicator.current_value = computed_value
        indicator.status = derived_status
        indicator.last_calculated_at = KRICalculator.utcnow()
        db.flush()

        AuditService(db).write_audit_log(
            action="risk_indicator.recalculated",
            entity_type="risk_indicator",
            entity_id=indicator.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json={"previous_value": previous_value, "previous_status": previous_status},
            after_json={"new_value": computed_value, "new_status": derived_status},
            metadata_json={
                "source": "api",
                "context_json": {
                    "previous_value": previous_value,
                    "new_value": computed_value,
                    "previous_status": previous_status,
                    "new_status": derived_status,
                },
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

        db.commit()
        db.refresh(indicator)
        return indicator
