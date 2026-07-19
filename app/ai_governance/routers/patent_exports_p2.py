import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai_governance.services.governance_graph.data_providers import (
    ExportDataSource,
    SQLAlchemyExportDataSource,
)
from app.ai_governance.services.governance_graph.scope_deps import require_patent_export_scope
from app.core.deps import get_db

router = APIRouter(prefix="/patent-exports/p2", tags=["patent-exports-p2"])


def get_export_data_source(db: Session = Depends(get_db)) -> ExportDataSource:
    # Regulations catalog + jurisdictions are static reference data (seeded
    # separately; empty until the reference set is loaded). ai_systems come from
    # core with an optional changed_since delta.
    return SQLAlchemyExportDataSource(db, regulations_catalog={}, jurisdictions=[])


def _envelope(items, changed_since: datetime | None) -> dict:
    return {"items": items, "meta": {"count": len(items) if hasattr(items, "__len__") else None,
                                     "changed_since": changed_since.isoformat() if changed_since else None}}


@router.get("/ai-systems")
def get_ai_systems(
    changed_since: datetime | None = Query(default=None),
    org_id: uuid.UUID = Depends(require_patent_export_scope()),
    data_source: ExportDataSource = Depends(get_export_data_source),
) -> dict:
    items = data_source.list_ai_systems(org_id, changed_since)
    return _envelope(items, changed_since)


@router.get("/regulations-catalog")
def get_regulations_catalog(
    changed_since: datetime | None = Query(default=None),
    org_id: uuid.UUID = Depends(require_patent_export_scope()),
    data_source: ExportDataSource = Depends(get_export_data_source),
) -> dict:
    catalog = data_source.list_regulations_catalog(org_id, changed_since)
    return {"catalog": catalog, "meta": {"changed_since": changed_since.isoformat() if changed_since else None}}


@router.get("/jurisdictions")
def get_jurisdictions(
    changed_since: datetime | None = Query(default=None),
    org_id: uuid.UUID = Depends(require_patent_export_scope()),
    data_source: ExportDataSource = Depends(get_export_data_source),
) -> dict:
    items = data_source.list_jurisdictions(org_id, changed_since)
    return _envelope(items, changed_since)
