import uuid

from sqlalchemy import select

from app.compliance.services.entity_risk_score_service import EntityRiskScoreService
from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.entity_risk_score import EntityRiskScore


class EntityScoreInvalidationListener:
    def handle(self, payload: EventPayload) -> None:
        if payload.event_type != EventType.RISK_SCORE_UPDATED:
            return

        risk_id = str(payload.entity_id)
        rows = payload.db.execute(
            select(EntityRiskScore)
            .where(EntityRiskScore.organization_id == payload.org_id)
            .order_by(EntityRiskScore.computed_at.desc(), EntityRiskScore.created_at.desc())
        ).scalars().all()

        distinct_targets: list[tuple[str, uuid.UUID]] = []
        seen: set[tuple[str, uuid.UUID]] = set()

        for row in rows:
            components = row.component_risks_json if isinstance(row.component_risks_json, list) else []
            includes_risk = any(
                isinstance(component, dict) and str(component.get("risk_id")) == risk_id
                for component in components
            )
            if not includes_risk:
                continue

            key = (row.entity_type, row.entity_id)
            if key in seen:
                continue
            seen.add(key)
            distinct_targets.append(key)

        for entity_type, entity_id in distinct_targets:
            EntityRiskScoreService.compute(
                entity_type=entity_type,
                entity_id=entity_id,
                org_id=payload.org_id,
                score_method="equal_weight",
                computed_by_user_id=None,
                db=payload.db,
            )

        if distinct_targets:
            payload.db.commit()

    def register(self, bus: EventBus) -> None:
        bus.subscribe(EventType.RISK_SCORE_UPDATED, self.handle)
