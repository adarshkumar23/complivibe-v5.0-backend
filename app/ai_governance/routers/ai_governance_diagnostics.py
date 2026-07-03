from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai_governance.schemas.ai_governance_diagnostics import (
    AIGovernanceDiagnosticDetail,
    AIGovernanceDiagnosticGenerateRequest,
    AIGovernanceDiagnosticListItem,
    AIGovernanceDiagnosticListResponse,
)
from app.ai_governance.services.ai_governance_diagnostic_service import AIGovernanceDiagnosticService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.exports.services.docx_renderer import DocxRenderer
from app.exports.services.export_content_builder import ExportContentBuilder
from app.exports.services.pdf_renderer import PDFRenderer
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/ai-governance/diagnostics", tags=["ai-governance-diagnostics"])


def _as_list_item(row) -> AIGovernanceDiagnosticListItem:
    return AIGovernanceDiagnosticListItem(
        id=row.id,
        organization_id=row.organization_id,
        business_unit_id=row.business_unit_id,
        generated_by=row.generated_by,
        snapshot_label=row.snapshot_label,
        overall_governance_score=row.overall_governance_score,
        overall_health=row.overall_health,
        ai_systems_assessed=row.ai_systems_assessed,
        critical_gaps_count=row.critical_gaps_count,
        created_at=row.created_at,
    )


def _as_detail(row) -> AIGovernanceDiagnosticDetail:
    return AIGovernanceDiagnosticDetail(**_as_list_item(row).model_dump(), snapshot_data=row.snapshot_data)


def _stream(data: bytes, media_type: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/generate", response_model=AIGovernanceDiagnosticDetail)
def generate_diagnostic_snapshot(
    payload: AIGovernanceDiagnosticGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:write")),
) -> AIGovernanceDiagnosticDetail:
    row = AIGovernanceDiagnosticService(db).generate_diagnostic(
        org_id=organization.id,
        generated_by=current_user.id,
        business_unit_id=payload.business_unit_id,
        snapshot_label=payload.snapshot_label,
    )
    db.commit()
    db.refresh(row)
    return _as_detail(row)


@router.get("", response_model=AIGovernanceDiagnosticListResponse)
def list_diagnostics(
    business_unit_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> AIGovernanceDiagnosticListResponse:
    rows, total = AIGovernanceDiagnosticService(db).list_diagnostics(
        org_id=organization.id,
        business_unit_id=business_unit_id,
        page=page,
        page_size=page_size,
    )
    return AIGovernanceDiagnosticListResponse(
        items=[_as_list_item(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{snapshot_id}", response_model=AIGovernanceDiagnosticDetail)
def get_diagnostic_snapshot(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
) -> AIGovernanceDiagnosticDetail:
    row = AIGovernanceDiagnosticService(db).get_diagnostic(
        org_id=organization.id,
        snapshot_id=snapshot_id,
    )
    return _as_detail(row)


@router.get("/{snapshot_id}/export")
def export_diagnostic_snapshot(
    snapshot_id: uuid.UUID,
    request: Request,
    format: Literal["pdf", "docx"] = Query(default="pdf"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_governance:read")),
):
    row = AIGovernanceDiagnosticService(db).get_diagnostic(
        org_id=organization.id,
        snapshot_id=snapshot_id,
    )
    content = ExportContentBuilder(db).build_ai_governance_diagnostic(row)

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
        entity_type="ai_governance_diagnostic_snapshot",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        metadata_json={"format": format, "report_type": "ai_governance_diagnostic"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return _stream(data, media_type, f"ai_governance_diagnostic_{row.id}.{ext}")
