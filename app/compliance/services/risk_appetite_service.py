import uuid

from fastapi import HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.membership import Membership
from app.models.risk import Risk
from app.models.risk_appetite_threshold import RiskAppetiteThreshold
from app.models.user import User
from app.services.audit_service import AuditService


class RiskAppetiteService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def derive_severity(new_score: int, max_acceptable_score: int) -> str:
        breach_ratio = new_score / max_acceptable_score
        if breach_ratio >= 1.5:
            return "critical"
        if breach_ratio >= 1.2:
            return "high"
        if breach_ratio >= 1.0:
            return "medium"
        return "low"

    def ensure_active_member(self, organization_id: uuid.UUID, user_id: uuid.UUID, *, field_name: str) -> None:
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

    def require_threshold_in_org(self, organization_id: uuid.UUID, threshold_id: uuid.UUID) -> RiskAppetiteThreshold:
        threshold = self.db.execute(
            select(RiskAppetiteThreshold).where(
                RiskAppetiteThreshold.id == threshold_id,
                RiskAppetiteThreshold.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if threshold is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk appetite threshold not found")
        return threshold

    def ensure_no_active_duplicate(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        risk_category: str,
        exclude_threshold_id: uuid.UUID | None = None,
    ) -> None:
        stmt = select(RiskAppetiteThreshold).where(
            RiskAppetiteThreshold.organization_id == organization_id,
            RiskAppetiteThreshold.scope_type == scope_type,
            RiskAppetiteThreshold.risk_category == risk_category,
            RiskAppetiteThreshold.is_active.is_(True),
        )
        if scope_id is None:
            stmt = stmt.where(RiskAppetiteThreshold.scope_id.is_(None))
        else:
            stmt = stmt.where(RiskAppetiteThreshold.scope_id == scope_id)
        if exclude_threshold_id is not None:
            stmt = stmt.where(RiskAppetiteThreshold.id != exclude_threshold_id)

        existing = self.db.execute(stmt).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "Active threshold already exists for this scope and category. "
                    "Deactivate existing threshold before creating a new one."
                ),
            )

    def ensure_scope_in_org(self, organization_id: uuid.UUID, scope_type: str, scope_id: uuid.UUID | None) -> None:
        if scope_type != "business_unit":
            return
        business_unit = self.db.execute(
            select(BusinessUnit.id).where(
                BusinessUnit.id == scope_id,
                BusinessUnit.organization_id == organization_id,
                BusinessUnit.is_active.is_(True),
                BusinessUnit.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if business_unit is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scope_id must reference an active business unit in the organization",
            )

    def _resolve_most_specific_threshold(
        self,
        *,
        organization_id: uuid.UUID,
        risk_category: str,
        scope_id: uuid.UUID | None,
    ) -> RiskAppetiteThreshold | None:
        stmt = (
            select(RiskAppetiteThreshold)
            .where(
                RiskAppetiteThreshold.organization_id == organization_id,
                RiskAppetiteThreshold.risk_category == risk_category,
                RiskAppetiteThreshold.is_active.is_(True),
                RiskAppetiteThreshold.scope_type.in_(["org", "business_unit"]),
            )
            .order_by(
                case((RiskAppetiteThreshold.scope_type == "business_unit", 0), else_=1),
                RiskAppetiteThreshold.created_at.desc(),
            )
        )
        rows = self.db.execute(stmt).scalars().all()
        if not rows:
            return None

        if scope_id is not None:
            for row in rows:
                if row.scope_type == "business_unit" and row.scope_id == scope_id:
                    return row

        for row in rows:
            if row.scope_type == "org" and row.scope_id is None:
                return row

        return None

    def check_appetite_breach(
        self,
        *,
        org_id: uuid.UUID,
        risk_id: uuid.UUID,
        new_score: int,
        risk_category: str,
        actor_user_id: uuid.UUID | None = None,
    ) -> ControlMonitoringAlert | None:
        risk = self.db.execute(
            select(Risk).where(
                Risk.id == risk_id,
                Risk.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if risk is None:
            return None

        scope_id = None
        if isinstance(risk.metadata_json, dict):
            raw_scope_id = risk.metadata_json.get("business_unit_id")
            if isinstance(raw_scope_id, str):
                try:
                    scope_id = uuid.UUID(raw_scope_id)
                except ValueError:
                    scope_id = None

        threshold = self._resolve_most_specific_threshold(
            organization_id=org_id,
            risk_category=risk_category,
            scope_id=scope_id,
        )
        if threshold is None:
            return None

        if new_score <= threshold.max_acceptable_score:
            return None

        open_alerts = self.db.execute(
            select(ControlMonitoringAlert).where(
                ControlMonitoringAlert.organization_id == org_id,
                ControlMonitoringAlert.alert_type == "risk_threshold_breach",
                ControlMonitoringAlert.status == "open",
            )
        ).scalars().all()
        for row in open_alerts:
            if not isinstance(row.alert_context_json, dict):
                continue
            if str(row.alert_context_json.get("risk_id")) == str(risk_id):
                return None

        severity = self.derive_severity(new_score, threshold.max_acceptable_score)
        title = (
            f"Risk appetite breach: {risk_category} score "
            f"{new_score} exceeds threshold {threshold.max_acceptable_score}"
        )
        description = (
            f"Risk {risk_id} exceeded threshold {threshold.id}. "
            f"Scope={threshold.scope_type}:{threshold.scope_id}."
        )

        alert = ControlMonitoringAlert(
            organization_id=org_id,
            alert_type="risk_threshold_breach",
            severity=severity,
            status="open",
            title=title,
            description=description,
            alert_context_json={
                "risk_id": str(risk_id),
                "threshold_id": str(threshold.id),
                "risk_category": risk_category,
                "new_score": new_score,
                "max_acceptable_score": threshold.max_acceptable_score,
                "scope_type": threshold.scope_type,
                "scope_id": str(threshold.scope_id) if threshold.scope_id else None,
            },
            assigned_to_user_id=threshold.escalation_owner_id,
        )
        self.db.add(alert)
        self.db.flush()

        score_delta = new_score - threshold.max_acceptable_score
        AuditService(self.db).write_audit_log(
            action="risk_appetite.breach_detected",
            entity_type="risk_appetite_threshold",
            entity_id=threshold.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "risk_id": str(risk_id),
                "threshold_id": str(threshold.id),
                "score": new_score,
                "max_score": threshold.max_acceptable_score,
            },
            metadata_json={
                "source": "service",
                "context_json": {
                    "risk_id": str(risk_id),
                    "threshold_id": str(threshold.id),
                    "score": new_score,
                    "max_score": threshold.max_acceptable_score,
                    "score_delta": score_delta,
                },
            },
        )
        return alert
