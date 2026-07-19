"""Export data source behind the satellite-pull export endpoints.

Ported from P2 core-side-patch/data_providers.py; the placeholder
_AssumedAiSystem is replaced with core's real AISystem model. Regulations
catalog and jurisdictions are supplied by config/seed (static reference data);
ai_systems come from core with an optional changed_since delta computed against
governance_graph_change_events.
"""

from __future__ import annotations

import abc
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_system import AISystem
from app.models.governance_graph_change_event import GovernanceGraphChangeEvent


class ExportDataSource(abc.ABC):
    @abc.abstractmethod
    def list_ai_systems(self, org_id: uuid.UUID, changed_since: datetime | None) -> list[dict]: ...

    @abc.abstractmethod
    def list_regulations_catalog(self, org_id: uuid.UUID, changed_since: datetime | None) -> dict: ...

    @abc.abstractmethod
    def list_jurisdictions(self, org_id: uuid.UUID, changed_since: datetime | None) -> list[dict]: ...


def _ai_system_to_export(row: AISystem) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "geographic_scope": row.geographic_scope,
        "data_categories": row.data_categories_json or [],
        "risk_tier": row.risk_tier,
    }


class SQLAlchemyExportDataSource(ExportDataSource):
    def __init__(self, session: Session, regulations_catalog: dict, jurisdictions: list[dict]) -> None:
        self.session = session
        self._regulations_catalog = regulations_catalog
        self._jurisdictions = jurisdictions

    def list_ai_systems(self, org_id: uuid.UUID, changed_since: datetime | None) -> list[dict]:
        stmt = select(AISystem).where(AISystem.organization_id == org_id, AISystem.deleted_at.is_(None))
        if changed_since is not None:
            changed_ids = select(GovernanceGraphChangeEvent.ai_system_id).where(
                GovernanceGraphChangeEvent.organization_id == org_id,
                GovernanceGraphChangeEvent.changed_at >= changed_since,
            )
            stmt = stmt.where(AISystem.id.in_(changed_ids))
        return [_ai_system_to_export(r) for r in self.session.execute(stmt).scalars().all()]

    def list_regulations_catalog(self, org_id: uuid.UUID, changed_since: datetime | None) -> dict:
        return dict(self._regulations_catalog)

    def list_jurisdictions(self, org_id: uuid.UUID, changed_since: datetime | None) -> list[dict]:
        return list(self._jurisdictions)
