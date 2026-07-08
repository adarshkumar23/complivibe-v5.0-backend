from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.export_control_check import ExportControlCheck
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.satellites.tprm_intelligence.export_control_screening import ExportControlScreeningService
from app.services.audit_service import AuditService
from app.services.vendor_service import VendorService

router = APIRouter(prefix="/vendors", tags=["tprm-intelligence"])


class ExportControlScreenRequest(BaseModel):
    item_description: str = Field(min_length=1, max_length=500)
    destination_country: str = Field(min_length=1, max_length=100)
    eccn: str | None = None
    hs_code: str | None = None


def _result_payload(row: ExportControlCheck, context: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "vendor_id": str(row.vendor_id),
        "item_description": row.item_description,
        "eccn": row.eccn,
        "hs_code": row.hs_code,
        "destination_country": row.destination_country,
        "denied_party_screening_result": row.denied_party_screening_result_json,
        "license_required": row.license_required,
        "license_determination_basis": row.license_determination_basis,
        "status": row.status,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
        "computed_by_user_id": str(row.computed_by_user_id) if row.computed_by_user_id else None,
        "denied_party_dataset_stale": False,
        "context_flags": [],
    }
    if context is not None:
        payload.update(context)
    return payload


@router.post("/{vendor_id}/export-control/screen", status_code=status.HTTP_201_CREATED)
def screen_vendor_export_control(
    vendor_id: uuid.UUID,
    body: ExportControlScreenRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("export_control:manage")),
) -> dict[str, Any]:
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)

    service = ExportControlScreeningService(db)
    try:
        row = service.screen(
            organization,
            vendor,
            item_description=body.item_description,
            destination_country=body.destination_country,
            eccn=body.eccn,
            hs_code=body.hs_code,
            computed_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    context = service.build_check_context(row)
    AuditService(db).write_audit_log(
        action="vendor.export_control_check.computed",
        entity_type="export_control_check",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "vendor_id": str(vendor.id),
            "eccn": row.eccn,
            "destination_country": row.destination_country,
            "license_required": row.license_required,
            "match_found": (row.denied_party_screening_result_json or {}).get("match_found"),
            "status": row.status,
        },
        metadata_json={"source": "tprm_intelligence_satellite"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _result_payload(row, context)


@router.get("/{vendor_id}/export-control")
def get_vendor_export_control(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("export_control:read")),
) -> dict[str, Any]:
    VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    service = ExportControlScreeningService(db)
    row = service.latest_check(organization.id, vendor_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No export control check found for this vendor yet")
    return _result_payload(row, service.build_check_context(row))


@router.get("/{vendor_id}/export-control/history")
def get_vendor_export_control_history(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("export_control:read")),
) -> list[dict[str, Any]]:
    VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    service = ExportControlScreeningService(db)
    rows = service.list_checks(organization.id, vendor_id)
    return [_result_payload(row, service.build_check_context(row)) for row in rows]
