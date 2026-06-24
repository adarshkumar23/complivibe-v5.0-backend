import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.control_monitoring_definition import ControlMonitoringDefinition
from app.models.control_monitoring_result import ControlMonitoringResult
from app.models.membership import Membership
from app.models.user import User

FREQUENCY_DAYS_MAP: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "annually": 365,
}


class ControlMonitoringService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

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

    def require_definition_in_org(
        self,
        organization_id: uuid.UUID,
        definition_id: uuid.UUID,
    ) -> ControlMonitoringDefinition:
        row = self.db.execute(
            select(ControlMonitoringDefinition).where(
                ControlMonitoringDefinition.id == definition_id,
                ControlMonitoringDefinition.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control monitoring definition not found")
        return row

    def ensure_owner_is_active_member(self, organization_id: uuid.UUID, owner_user_id: uuid.UUID) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == owner_user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )

        user = self.db.execute(select(User).where(User.id == owner_user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )
        return user

    @staticmethod
    def compute_next_check_due_at(check_frequency: str, checked_at: datetime) -> datetime:
        days = FREQUENCY_DAYS_MAP.get(check_frequency)
        if days is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid check_frequency")
        return checked_at + timedelta(days=days)

    def summary(
        self,
        organization_id: uuid.UUID,
        *,
        include_inactive: bool = False,
        include_archived: bool = False,
    ) -> dict[str, int | dict[str, int]]:
        total_definitions = int(
            self.db.execute(
                select(func.count(ControlMonitoringDefinition.id)).where(
                    ControlMonitoringDefinition.organization_id == organization_id
                )
            ).scalar_one()
        )
        active_definitions = int(
            self.db.execute(
                select(func.count(ControlMonitoringDefinition.id)).where(
                    ControlMonitoringDefinition.organization_id == organization_id,
                    ControlMonitoringDefinition.status == "active",
                )
            ).scalar_one()
        )
        inactive_definitions = int(
            self.db.execute(
                select(func.count(ControlMonitoringDefinition.id)).where(
                    ControlMonitoringDefinition.organization_id == organization_id,
                    ControlMonitoringDefinition.status == "inactive",
                )
            ).scalar_one()
        )
        archived_definitions = int(
            self.db.execute(
                select(func.count(ControlMonitoringDefinition.id)).where(
                    ControlMonitoringDefinition.organization_id == organization_id,
                    ControlMonitoringDefinition.status == "archived",
                )
            ).scalar_one()
        )

        definition_scope = [ControlMonitoringDefinition.organization_id == organization_id]
        if not include_inactive:
            definition_scope.append(ControlMonitoringDefinition.status != "inactive")
        if not include_archived:
            definition_scope.append(ControlMonitoringDefinition.status != "archived")

        now = self.utcnow()
        definitions_due_now = int(
            self.db.execute(
                select(func.count(ControlMonitoringDefinition.id)).where(
                    *definition_scope,
                    ControlMonitoringDefinition.next_check_due_at.is_not(None),
                    ControlMonitoringDefinition.next_check_due_at <= now,
                )
            ).scalar_one()
        )

        by_monitoring_type_rows = self.db.execute(
            select(ControlMonitoringDefinition.monitoring_type, func.count(ControlMonitoringDefinition.id))
            .where(*definition_scope)
            .group_by(ControlMonitoringDefinition.monitoring_type)
        ).all()

        joined_results = ControlMonitoringResult.__table__.join(
            ControlMonitoringDefinition.__table__,
            ControlMonitoringResult.definition_id == ControlMonitoringDefinition.id,
        )
        result_scope = [
            ControlMonitoringResult.organization_id == organization_id,
            *definition_scope,
        ]
        total_results = int(
            self.db.execute(
                select(func.count(ControlMonitoringResult.id)).select_from(joined_results).where(*result_scope)
            ).scalar_one()
        )

        by_check_status_rows = self.db.execute(
            select(ControlMonitoringResult.check_status, func.count(ControlMonitoringResult.id))
            .select_from(joined_results)
            .where(*result_scope)
            .group_by(ControlMonitoringResult.check_status)
        ).all()

        return {
            "total_definitions": total_definitions,
            "active_definitions": active_definitions,
            "inactive_definitions": inactive_definitions,
            "archived_definitions": archived_definitions,
            "definitions_due_now": definitions_due_now,
            "total_results": total_results,
            "by_monitoring_type": {str(key): int(value) for key, value in by_monitoring_type_rows},
            "by_check_status": {str(key): int(value) for key, value in by_check_status_rows},
        }
