import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_governance_event import AIGovernanceEvent
from app.models.ai_system import AISystem


class AIGovernanceEventService:
    @staticmethod
    def log(
        db: Session,
        org_id: uuid.UUID,
        event_type: str,
        actor_id: uuid.UUID | None = None,
        actor_type: str = "user",
        ai_system_id: uuid.UUID | None = None,
        event_data: dict | None = None,
    ) -> None:
        event = AIGovernanceEvent(
            organization_id=org_id,
            ai_system_id=ai_system_id,
            event_type=event_type,
            actor_id=actor_id,
            actor_type=actor_type,
            event_data=event_data or {},
        )
        db.add(event)
        db.flush()

    @staticmethod
    def get_system_events(
        db: Session,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        event_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AIGovernanceEvent]:
        stmt = select(AIGovernanceEvent).where(
            AIGovernanceEvent.organization_id == org_id,
            AIGovernanceEvent.ai_system_id == system_id,
        )
        if event_type:
            stmt = stmt.where(AIGovernanceEvent.event_type == event_type)
        return db.execute(
            stmt.order_by(AIGovernanceEvent.created_at.asc()).offset(max(0, int(skip))).limit(max(1, min(int(limit), 500)))
        ).scalars().all()

    @staticmethod
    def get_org_events(
        db: Session,
        org_id: uuid.UUID,
        event_type: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[AIGovernanceEvent]:
        stmt = select(AIGovernanceEvent).where(AIGovernanceEvent.organization_id == org_id)
        if event_type:
            stmt = stmt.where(AIGovernanceEvent.event_type == event_type)
        if from_date is not None:
            stmt = stmt.where(AIGovernanceEvent.created_at >= from_date)
        if to_date is not None:
            stmt = stmt.where(AIGovernanceEvent.created_at <= to_date)
        return db.execute(
            stmt.order_by(AIGovernanceEvent.created_at.asc()).offset(max(0, int(skip))).limit(max(1, min(int(limit), 500)))
        ).scalars().all()

    @staticmethod
    def get_event_summary(db: Session, org_id: uuid.UUID) -> dict:
        since = datetime.now(UTC) - timedelta(days=30)

        total_30d = int(
            db.execute(
                select(func.count(AIGovernanceEvent.id)).where(
                    AIGovernanceEvent.organization_id == org_id,
                    AIGovernanceEvent.created_at >= since,
                )
            ).scalar_one()
            or 0
        )

        by_type_rows = db.execute(
            select(AIGovernanceEvent.event_type, func.count(AIGovernanceEvent.id))
            .where(
                AIGovernanceEvent.organization_id == org_id,
                AIGovernanceEvent.created_at >= since,
            )
            .group_by(AIGovernanceEvent.event_type)
        ).all()
        by_event_type = {str(event_type): int(count) for event_type, count in by_type_rows}

        systems_rows = db.execute(
            select(
                AIGovernanceEvent.ai_system_id,
                AISystem.name,
                func.count(AIGovernanceEvent.id).label("event_count"),
            )
            .join(
                AISystem,
                AISystem.id == AIGovernanceEvent.ai_system_id,
                isouter=True,
            )
            .where(
                AIGovernanceEvent.organization_id == org_id,
                AIGovernanceEvent.created_at >= since,
                AIGovernanceEvent.ai_system_id.is_not(None),
            )
            .group_by(AIGovernanceEvent.ai_system_id, AISystem.name)
            .order_by(func.count(AIGovernanceEvent.id).desc())
            .limit(5)
        ).all()
        systems_with_most_events = [
            {
                "system_id": str(system_id),
                "system_name": system_name,
                "count": int(count),
            }
            for system_id, system_name, count in systems_rows
            if system_id is not None
        ]

        return {
            "total_events_30d": total_30d,
            "by_event_type": by_event_type,
            "systems_with_most_events": systems_with_most_events,
        }
