from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.exports.schemas.export_settings import ExportSettingsRead, ExportSettingsUpdate
from app.exports.services.docx_renderer import DocxRenderer
from app.exports.services.export_content_builder import ExportContentBuilder
from app.exports.services.pdf_renderer import PDFRenderer
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.organization_export_setting import OrganizationExportSetting
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import AuditService

router = APIRouter(tags=["entity-exports"])


def _require_org_admin(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


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


def _write_export_audit(
    *,
    db: Session,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID | None,
    export_format: str,
    report_type: str | None = None,
    request: Request,
) -> None:
    AuditService(db).write_audit_log(
        action="export.generated",
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        metadata_json={
            "format": export_format,
            "report_type": report_type,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/compliance/policies/{policy_id}/export")
def export_policy(
    policy_id: uuid.UUID,
    request: Request,
    format: Literal["pdf", "docx"] = Query(default="pdf"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
):
    content = ExportContentBuilder(db).build_policy(organization.id, policy_id)
    rendered, media_type, extension = _render(content, format)
    _write_export_audit(
        db=db,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_type="compliance_policy",
        entity_id=policy_id,
        export_format=format,
        request=request,
    )
    db.commit()
    return _stream_file(rendered, media_type, f"policy_{policy_id}.{extension}")


@router.get("/compliance/controls/{control_id}/export")
def export_control(
    control_id: uuid.UUID,
    request: Request,
    format: Literal["pdf", "docx"] = Query(default="pdf"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
):
    content = ExportContentBuilder(db).build_control(organization.id, control_id)
    rendered, media_type, extension = _render(content, format)
    _write_export_audit(
        db=db,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_type="control",
        entity_id=control_id,
        export_format=format,
        request=request,
    )
    db.commit()
    return _stream_file(rendered, media_type, f"control_{control_id}.{extension}")


@router.get("/risks/{risk_id}/export")
def export_risk(
    risk_id: uuid.UUID,
    request: Request,
    format: Literal["pdf", "docx"] = Query(default="pdf"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("risks:read")),
):
    content = ExportContentBuilder(db).build_risk(organization.id, risk_id)
    rendered, media_type, extension = _render(content, format)
    _write_export_audit(
        db=db,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_type="risk",
        entity_id=risk_id,
        export_format=format,
        request=request,
    )
    db.commit()
    return _stream_file(rendered, media_type, f"risk_{risk_id}.{extension}")


@router.get("/vendors/{vendor_id}/export")
def export_vendor(
    vendor_id: uuid.UUID,
    request: Request,
    format: Literal["pdf", "docx"] = Query(default="pdf"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
):
    content = ExportContentBuilder(db).build_vendor(organization.id, vendor_id)
    rendered, media_type, extension = _render(content, format)
    _write_export_audit(
        db=db,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_type="vendor",
        entity_id=vendor_id,
        export_format=format,
        request=request,
    )
    db.commit()
    return _stream_file(rendered, media_type, f"vendor_{vendor_id}.{extension}")


@router.get("/compliance/reports/posture/export")
def export_posture_report(
    request: Request,
    format: Literal["pdf", "docx"] = Query(default="pdf"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
):
    content = ExportContentBuilder(db).build_posture_report(organization.id)
    rendered, media_type, extension = _render(content, format)
    _write_export_audit(
        db=db,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_type="compliance_report",
        entity_id=None,
        export_format=format,
        report_type="posture",
        request=request,
    )
    db.commit()
    return _stream_file(rendered, media_type, f"posture_report.{extension}")


@router.get("/compliance/reports/framework-coverage/export")
def export_framework_coverage_report(
    request: Request,
    format: Literal["pdf", "docx"] = Query(default="pdf"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance_policies:read")),
):
    content = ExportContentBuilder(db).build_framework_coverage_report(organization.id)
    rendered, media_type, extension = _render(content, format)
    _write_export_audit(
        db=db,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        entity_type="compliance_report",
        entity_id=None,
        export_format=format,
        report_type="framework_coverage",
        request=request,
    )
    db.commit()
    return _stream_file(rendered, media_type, f"framework_coverage_report.{extension}")


@router.get("/organizations/export-settings", response_model=ExportSettingsRead)
def get_export_settings(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("compliance:read")),
):
    _require_org_admin(db, membership)
    row = (
        db.query(OrganizationExportSetting)
        .filter(OrganizationExportSetting.organization_id == organization.id)
        .first()
    )
    if row is None:
        return ExportSettingsRead(
            id=None,
            organization_id=organization.id,
            logo_url=None,
            company_display_name=organization.name,
            footer_text="Generated by CompliVibe",
            primary_color_hex="#1F4B99",
            created_at=None,
            updated_at=None,
        )
    return ExportSettingsRead(
        id=row.id,
        organization_id=row.organization_id,
        logo_url=row.logo_url,
        company_display_name=row.company_display_name or organization.name,
        footer_text=row.footer_text,
        primary_color_hex=row.primary_color_hex,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.put("/organizations/export-settings", response_model=ExportSettingsRead)
def upsert_export_settings(
    payload: ExportSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("compliance:write")),
):
    _require_org_admin(db, membership)
    row = (
        db.query(OrganizationExportSetting)
        .filter(OrganizationExportSetting.organization_id == organization.id)
        .first()
    )
    if row is None:
        row = OrganizationExportSetting(
            organization_id=organization.id,
            logo_url=payload.logo_url,
            company_display_name=payload.company_display_name,
            footer_text=payload.footer_text,
            primary_color_hex=payload.primary_color_hex,
        )
        db.add(row)
    else:
        row.logo_url = payload.logo_url
        row.company_display_name = payload.company_display_name
        row.footer_text = payload.footer_text
        row.primary_color_hex = payload.primary_color_hex
        row.updated_at = datetime.now(UTC)

    db.flush()
    AuditService(db).write_audit_log(
        action="organization.export_settings_updated",
        entity_type="organization_export_settings",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        metadata_json={"source": "api"},
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.commit()
    db.refresh(row)

    return ExportSettingsRead(
        id=row.id,
        organization_id=row.organization_id,
        logo_url=row.logo_url,
        company_display_name=row.company_display_name or organization.name,
        footer_text=row.footer_text,
        primary_color_hex=row.primary_color_hex,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
