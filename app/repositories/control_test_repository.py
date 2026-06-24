import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.control_test_definition import ControlTestDefinition
from app.models.control_test_run import ControlTestRun


class ControlTestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_definition_by_id(self, test_id: uuid.UUID) -> ControlTestDefinition | None:
        return self.db.execute(select(ControlTestDefinition).where(ControlTestDefinition.id == test_id)).scalar_one_or_none()

    def list_definitions_for_control(self, organization_id: uuid.UUID, control_id: uuid.UUID) -> list[ControlTestDefinition]:
        stmt = (
            select(ControlTestDefinition)
            .where(
                ControlTestDefinition.organization_id == organization_id,
                ControlTestDefinition.control_id == control_id,
                ControlTestDefinition.status != "archived",
            )
            .order_by(ControlTestDefinition.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_runs_for_control(self, organization_id: uuid.UUID, control_id: uuid.UUID, limit: int = 100) -> list[ControlTestRun]:
        stmt = (
            select(ControlTestRun)
            .where(
                ControlTestRun.organization_id == organization_id,
                ControlTestRun.control_id == control_id,
            )
            .order_by(ControlTestRun.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())
