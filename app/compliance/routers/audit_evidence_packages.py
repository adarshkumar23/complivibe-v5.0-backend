from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.exports.services.docx_renderer import DocxRenderer
from app.exports.services.export_content_builder import ExportContentBuilder
from app.exports.services.pdf_renderer import PDFRenderer
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/compliance/audits", tags=["audit_evidence_packages"])


def _render(content, export_format: Literal["pdf", "docx"]) -> tuple[bytes, str, str]:
    if export_format == "pdf":
        rendered = PDFRenderer().render(content)
        return rendered, "application/pdf", "pdf"
    rendered = DocxRenderer().render(content)
    return (
        rendered,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    )


def _stream_file(data: bytes, media_type: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{audit_id}/evidence-package/export")
def export_audit_evidence_package(
    audit_id: uuid.UUID,
    request: Request,
    format: Literal["pdf", "docx"] = Query(default="pdf"),
    framework_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("audit:read")),
):
    content = ExportContentBuilder(db).build_audit_evidence_package(organization.id, audit_id, framework_id)
    rendered, media_type, extension = _render(content, format)

    AuditService(db).write_audit_log(
        action="export.generated",
        entity_type="audit_engagement",
        entity_id=audit_id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        metadata_json={
            "format": format,
            "report_type": "audit_evidence_package",
            "framework_id": str(framework_id) if framework_id else None,
            "evidence_item_count": sum(len(section.items) for section in content.sections),
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()

    return _stream_file(rendered, media_type, f"audit_evidence_package_{audit_id}.{extension}")
