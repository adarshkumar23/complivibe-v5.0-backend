from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.schemas.compound_insights import (
    CompoundInsightListResponse,
    CompoundInsightRead,
)
from app.core.deps import get_current_organization, get_db, require_permission
from app.models.compound_insight import CompoundInsight
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(tags=["compound-insights"])

_ALLOWED_STATUS = {"surfaced", "auto_resolved"}


def _read(row: CompoundInsight) -> CompoundInsightRead:
    return CompoundInsightRead(
        id=row.id,
        organization_id=row.organization_id,
        pattern_id=row.pattern_id,
        severity=row.severity,
        status=row.status,
        title=row.title,
        templated_narrative=row.templated_narrative,
        narrative_source=row.narrative_source,
        narrative_headline=row.narrative_headline,
        narrative_summary=row.narrative_summary,
        recommended_actions_json=row.recommended_actions_json,
        matched_nodes_json=row.matched_nodes_json or {},
        provider_used=row.provider_used,
        detection_count=row.detection_count,
        first_detected_at=row.first_detected_at,
        last_detected_at=row.last_detected_at,
        resolved_at=row.resolved_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/compliance/compound-insights", response_model=CompoundInsightListResponse)
def list_compound_insights(
    status_filter: str | None = Query(default=None, alias="status"),
    pattern_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compound_insights:read")),
) -> CompoundInsightListResponse:
    stmt = select(CompoundInsight).where(CompoundInsight.organization_id == organization.id)
    if status_filter is not None:
        if status_filter not in _ALLOWED_STATUS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status '{status_filter}'")
        stmt = stmt.where(CompoundInsight.status == status_filter)
    if pattern_id is not None:
        stmt = stmt.where(CompoundInsight.pattern_id == pattern_id)

    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = db.execute(
        stmt.order_by(CompoundInsight.last_detected_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()
    return CompoundInsightListResponse(
        items=[_read(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.get("/compliance/compound-insights/{insight_id}", response_model=CompoundInsightRead)
def get_compound_insight(
    insight_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compound_insights:read")),
) -> CompoundInsightRead:
    row = db.execute(
        select(CompoundInsight).where(
            CompoundInsight.id == insight_id,
            CompoundInsight.organization_id == organization.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compound insight not found")
    return _read(row)
