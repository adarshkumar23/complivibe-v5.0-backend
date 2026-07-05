from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.whistleblower import (
    WhistleblowerInvestigatorMessageRequest,
    WhistleblowerMessageRead,
    WhistleblowerReporterMessageRequest,
    WhistleblowerReporterStatusRead,
    WhistleblowerReportDetailRead,
    WhistleblowerReportRead,
    WhistleblowerReportSubmitRequest,
    WhistleblowerReportSubmitResponse,
    WhistleblowerStatusUpdateRequest,
)
from app.services.whistleblower_service import WhistleblowerService

router = APIRouter(prefix="/whistleblower", tags=["whistleblower"])


@router.post("/submit", response_model=WhistleblowerReportSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_report(
    payload: WhistleblowerReportSubmitRequest,
    db: Session = Depends(get_db),
) -> WhistleblowerReportSubmitResponse:
    """Public, unauthenticated. Reporter identity is never captured here."""
    organization = db.execute(
        select(Organization).where(Organization.id == payload.organization_id)
    ).scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    report, raw_tracking_code = WhistleblowerService(db).submit_report(
        organization_id=organization.id,
        category=payload.category,
        description=payload.description,
    )
    db.commit()
    return WhistleblowerReportSubmitResponse(tracking_code=raw_tracking_code, anonymous_id=report.anonymous_id)


@router.get("/status/{tracking_code}", response_model=WhistleblowerReporterStatusRead)
def get_report_status(
    tracking_code: str,
    db: Session = Depends(get_db),
) -> WhistleblowerReporterStatusRead:
    """Public, unauthenticated. tracking_code is the sole credential."""
    service = WhistleblowerService(db)
    report = service.lookup_report_by_tracking_code(tracking_code=tracking_code)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    messages = service.get_messages(report.id)
    return WhistleblowerReporterStatusRead(
        anonymous_id=report.anonymous_id,
        category=report.category,
        status=report.status,
        created_at=report.created_at,
        messages=[WhistleblowerMessageRead.model_validate(m) for m in messages],
    )


@router.post("/status/{tracking_code}/reply", response_model=WhistleblowerMessageRead, status_code=status.HTTP_201_CREATED)
def reporter_reply(
    tracking_code: str,
    payload: WhistleblowerReporterMessageRequest,
    db: Session = Depends(get_db),
) -> WhistleblowerMessageRead:
    """Public, unauthenticated."""
    message = WhistleblowerService(db).add_reporter_message(
        tracking_code=tracking_code,
        content=payload.content,
    )
    db.commit()
    return WhistleblowerMessageRead.model_validate(message)


@router.get("/reports", response_model=list[WhistleblowerReportRead])
def list_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("whistleblower:investigate")),
) -> list[WhistleblowerReportRead]:
    reports = WhistleblowerService(db).list_for_investigator(
        organization_id=membership.organization_id, status_filter=status_filter
    )
    return [WhistleblowerReportRead.model_validate(r) for r in reports]


@router.get("/reports/{report_id}", response_model=WhistleblowerReportDetailRead)
def get_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("whistleblower:investigate")),
) -> WhistleblowerReportDetailRead:
    service = WhistleblowerService(db)
    report = service.get_report_for_investigator(organization_id=membership.organization_id, report_id=report_id)
    messages = service.get_messages(report.id)
    return WhistleblowerReportDetailRead(
        id=report.id,
        organization_id=report.organization_id,
        anonymous_id=report.anonymous_id,
        category=report.category,
        description=report.description,
        status=report.status,
        assigned_investigator_user_id=report.assigned_investigator_user_id,
        resolution_summary=report.resolution_summary,
        created_at=report.created_at,
        updated_at=report.updated_at,
        messages=[WhistleblowerMessageRead.model_validate(m) for m in messages],
    )


@router.post("/reports/{report_id}/reply", response_model=WhistleblowerMessageRead, status_code=status.HTTP_201_CREATED)
def investigator_reply(
    report_id: uuid.UUID,
    payload: WhistleblowerInvestigatorMessageRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("whistleblower:investigate")),
) -> WhistleblowerMessageRead:
    message = WhistleblowerService(db).add_investigator_message(
        organization_id=membership.organization_id,
        report_id=report_id,
        investigator_user_id=current_user.id,
        content=payload.content,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    db.commit()
    return WhistleblowerMessageRead.model_validate(message)


@router.patch("/reports/{report_id}/status", response_model=WhistleblowerReportRead)
def update_report_status(
    report_id: uuid.UUID,
    payload: WhistleblowerStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("whistleblower:investigate")),
) -> WhistleblowerReportRead:
    report = WhistleblowerService(db).update_status(
        organization_id=membership.organization_id,
        report_id=report_id,
        investigator_user_id=current_user.id,
        new_status=payload.status,
        resolution_summary=payload.resolution_summary,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    db.commit()
    return WhistleblowerReportRead.model_validate(report)
