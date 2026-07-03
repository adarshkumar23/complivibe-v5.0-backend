from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.compliance.schemas.board_scorecard import (
    BoardScorecardDetail,
    BoardScorecardGenerateRequest,
    BoardScorecardListItem,
    BoardScorecardListResponse,
)
from app.compliance.services.board_scorecard_service import BoardScorecardService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.exports.services.docx_renderer import DocxRenderer
from app.exports.services.export_content_builder import ExportContentBuilder
from app.exports.services.pdf_renderer import PDFRenderer
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/compliance/board-scorecard", tags=["board-scorecard"])


def _as_list_item(row) -> BoardScorecardListItem:
    return BoardScorecardListItem(
        id=row.id,
        organization_id=row.organization_id,
        business_unit_id=row.business_unit_id,
        generated_by=row.generated_by,
        snapshot_label=row.snapshot_label,
        overall_compliance_score=float(row.overall_compliance_score),
        created_at=row.created_at,
    )


def _stream(data: bytes, media_type: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/generate", response_model=BoardScorecardDetail)
def generate_board_scorecard_snapshot(
    payload: BoardScorecardGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> BoardScorecardDetail:
    row = BoardScorecardService(db).generate_snapshot(
        org_id=organization.id,
        business_unit_id=payload.business_unit_id,
        generated_by=current_user.id,
        snapshot_label=payload.snapshot_label,
    )
    db.commit()
    db.refresh(row)
    return BoardScorecardDetail(
        **_as_list_item(row).model_dump(),
        snapshot_data=row.snapshot_data,
    )


@router.get("", response_model=BoardScorecardListResponse)
def list_board_scorecard_snapshots(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    business_unit_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> BoardScorecardListResponse:
    rows, total = BoardScorecardService(db).list_snapshots(
        organization.id,
        page=page,
        page_size=page_size,
        business_unit_id=business_unit_id,
        date_from=date_from,
        date_to=date_to,
    )
    return BoardScorecardListResponse(
        items=[_as_list_item(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{snapshot_id}", response_model=BoardScorecardDetail)
def get_board_scorecard_snapshot(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> BoardScorecardDetail:
    row = BoardScorecardService(db).get_snapshot(organization.id, snapshot_id)
    return BoardScorecardDetail(
        **_as_list_item(row).model_dump(),
        snapshot_data=row.snapshot_data,
    )


@router.get("/{snapshot_id}/export")
def export_board_scorecard_snapshot(
    snapshot_id: uuid.UUID,
    request: Request,
    format: Literal["pdf", "docx"] = Query(default="pdf"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
):
    row = BoardScorecardService(db).get_snapshot(organization.id, snapshot_id)
    content = ExportContentBuilder(db).build_board_scorecard(row)

    if format == "pdf":
        data = PDFRenderer().render(content)
        media_type = "application/pdf"
        ext = "pdf"
    else:
        data = DocxRenderer().render(content)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"

    AuditService(db).write_audit_log(
        action="export.generated",
        entity_type="board_scorecard_snapshot",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        metadata_json={"format": format, "report_type": "board_scorecard"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return _stream(data, media_type, f"board_scorecard_{row.id}.{ext}")
