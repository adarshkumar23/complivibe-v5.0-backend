from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.models.whistleblower import WhistleblowerMessage
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


def _decrypted_message(
    service: WhistleblowerService,
    message: WhistleblowerMessage,
    organization_id: uuid.UUID,
) -> WhistleblowerMessageRead:
    """Message bodies are encrypted at rest; decrypt for the response only."""
    return WhistleblowerMessageRead.model_validate(message).model_copy(
        update={"content": service.decrypt_message_content(message, organization_id=organization_id)}
    )




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
        messages=[_decrypted_message(service, m, report.organization_id) for m in messages],
    )


@router.post("/status/{tracking_code}/reply", response_model=WhistleblowerMessageRead, status_code=status.HTTP_201_CREATED)
def reporter_reply(
    tracking_code: str,
    payload: WhistleblowerReporterMessageRequest,
    db: Session = Depends(get_db),
) -> WhistleblowerMessageRead:
    """Public, unauthenticated."""
    service = WhistleblowerService(db)
    message = service.add_reporter_message(
        tracking_code=tracking_code,
        content=payload.content,
    )
    db.commit()
    # Echo back the plaintext the reporter just sent, not the stored ciphertext.
    return WhistleblowerMessageRead.model_validate(message).model_copy(
        update={"content": payload.content}
    )


@router.get("/reports", response_model=list[WhistleblowerReportRead])
def list_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("whistleblower:investigate")),
) -> list[WhistleblowerReportRead]:
    service = WhistleblowerService(db)
    reports = service.list_for_investigator(
        organization_id=membership.organization_id, status_filter=status_filter
    )
    result = []
    for r in reports:
        context = service.build_report_context(r)
        item = WhistleblowerReportRead.model_validate(r)
        item.days_open = context["days_open"]
        item.context_flags = context["context_flags"]
        result.append(item)
    return result


@router.get("/reports/{report_id}", response_model=WhistleblowerReportDetailRead)
def get_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: Membership = Depends(require_permission("whistleblower:investigate")),
) -> WhistleblowerReportDetailRead:
    service = WhistleblowerService(db)
    report = service.get_report_for_investigator(organization_id=membership.organization_id, report_id=report_id)
    messages = service.get_messages(report.id)
    context = service.build_report_context(report, messages)
    return WhistleblowerReportDetailRead(
        id=report.id,
        organization_id=report.organization_id,
        anonymous_id=report.anonymous_id,
        category=report.category,
        description=service.decrypt_report_description(report),
        status=report.status,
        assigned_investigator_user_id=report.assigned_investigator_user_id,
        resolution_summary=report.resolution_summary,
        created_at=report.created_at,
        updated_at=report.updated_at,
        days_open=context["days_open"],
        context_flags=context["context_flags"],
        messages=[_decrypted_message(service, m, report.organization_id) for m in messages],
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
    # Echo back the plaintext just submitted, not the stored ciphertext.
    return WhistleblowerMessageRead.model_validate(message).model_copy(
        update={"content": payload.content}
    )


@router.patch("/reports/{report_id}/status", response_model=WhistleblowerReportRead)
def update_report_status(
    report_id: uuid.UUID,
    payload: WhistleblowerStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_permission("whistleblower:investigate")),
) -> WhistleblowerReportRead:
    service = WhistleblowerService(db)
    report = service.update_status(
        organization_id=membership.organization_id,
        report_id=report_id,
        investigator_user_id=current_user.id,
        new_status=payload.status,
        resolution_summary=payload.resolution_summary,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    db.commit()
    context = service.build_report_context(report)
    result = WhistleblowerReportRead.model_validate(report)
    result.days_open = context["days_open"]
    result.context_flags = context["context_flags"]
    return result
