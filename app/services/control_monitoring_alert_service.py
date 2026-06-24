import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.control_monitoring_definition import ControlMonitoringDefinition
from app.models.control_monitoring_rule import ControlMonitoringRule
from app.models.membership import Membership
from app.models.user import User


class ControlMonitoringAlertService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def require_alert_in_org(self, organization_id: uuid.UUID, alert_id: uuid.UUID) -> ControlMonitoringAlert:
        row = self.db.execute(
            select(ControlMonitoringAlert).where(
                ControlMonitoringAlert.id == alert_id,
                ControlMonitoringAlert.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control monitoring alert not found")
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

    def require_rule_in_org(self, organization_id: uuid.UUID, rule_id: uuid.UUID) -> ControlMonitoringRule:
        row = self.db.execute(
            select(ControlMonitoringRule).where(
                ControlMonitoringRule.id == rule_id,
                ControlMonitoringRule.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control monitoring rule not found")
        return row

    def require_definition_in_org(self, organization_id: uuid.UUID, definition_id: uuid.UUID) -> ControlMonitoringDefinition:
        row = self.db.execute(
            select(ControlMonitoringDefinition).where(
                ControlMonitoringDefinition.id == definition_id,
                ControlMonitoringDefinition.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control monitoring definition not found")
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

    @staticmethod
    def ensure_not_terminal(alert: ControlMonitoringAlert) -> None:
        if alert.status in {"resolved", "dismissed"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Resolved or dismissed alerts are terminal and cannot transition",
            )

    def summary(self, organization_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        total_alerts = int(
            self.db.execute(
                select(func.count(ControlMonitoringAlert.id)).where(ControlMonitoringAlert.organization_id == organization_id)
            ).scalar_one()
        )
        open_alerts = int(
            self.db.execute(
                select(func.count(ControlMonitoringAlert.id)).where(
                    ControlMonitoringAlert.organization_id == organization_id,
                    ControlMonitoringAlert.status == "open",
                )
            ).scalar_one()
        )
        acknowledged_alerts = int(
            self.db.execute(
                select(func.count(ControlMonitoringAlert.id)).where(
                    ControlMonitoringAlert.organization_id == organization_id,
                    ControlMonitoringAlert.status == "acknowledged",
                )
            ).scalar_one()
        )
        resolved_alerts = int(
            self.db.execute(
                select(func.count(ControlMonitoringAlert.id)).where(
                    ControlMonitoringAlert.organization_id == organization_id,
                    ControlMonitoringAlert.status == "resolved",
                )
            ).scalar_one()
        )
        dismissed_alerts = int(
            self.db.execute(
                select(func.count(ControlMonitoringAlert.id)).where(
                    ControlMonitoringAlert.organization_id == organization_id,
                    ControlMonitoringAlert.status == "dismissed",
                )
            ).scalar_one()
        )

        by_severity_rows = self.db.execute(
            select(ControlMonitoringAlert.severity, func.count(ControlMonitoringAlert.id))
            .where(ControlMonitoringAlert.organization_id == organization_id)
            .group_by(ControlMonitoringAlert.severity)
        ).all()
        by_status_rows = self.db.execute(
            select(ControlMonitoringAlert.status, func.count(ControlMonitoringAlert.id))
            .where(ControlMonitoringAlert.organization_id == organization_id)
            .group_by(ControlMonitoringAlert.status)
        ).all()
        by_alert_type_rows = self.db.execute(
            select(ControlMonitoringAlert.alert_type, func.count(ControlMonitoringAlert.id))
            .where(ControlMonitoringAlert.organization_id == organization_id)
            .group_by(ControlMonitoringAlert.alert_type)
        ).all()

        return {
            "total_alerts": total_alerts,
            "open_alerts": open_alerts,
            "acknowledged_alerts": acknowledged_alerts,
            "resolved_alerts": resolved_alerts,
            "dismissed_alerts": dismissed_alerts,
            "by_severity": {str(key): int(value) for key, value in by_severity_rows},
            "by_status": {str(key): int(value) for key, value in by_status_rows},
            "by_alert_type": {str(key): int(value) for key, value in by_alert_type_rows},
        }
