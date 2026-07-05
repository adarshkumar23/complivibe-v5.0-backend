from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.sanctions_screen_result import SanctionsScreenResult
from app.models.user import User
from app.satellites.tprm_intelligence.sanctions_screening import SanctionsDatasetUnavailable, SanctionsScreeningService
from app.services.audit_service import AuditService
from app.services.vendor_service import VendorService

router = APIRouter(prefix="/vendors", tags=["tprm-intelligence"])


def _result_payload(row: SanctionsScreenResult) -> dict:
    details = row.match_details or {}
    return {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "vendor_id": str(row.vendor_id),
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "list_name": row.list_name,
        "screened_at": row.screened_at.isoformat() if row.screened_at else None,
        "match_found": row.match_found,
        "match_details": details,
        "top_score": details.get("top_score"),
        "cleared_by": str(row.cleared_by) if row.cleared_by else None,
        "cleared_at": row.cleared_at.isoformat() if row.cleared_at else None,
    }


@router.post("/{vendor_id}/sanctions-screen/compute", status_code=status.HTTP_201_CREATED)
def compute_vendor_sanctions_screen(
    vendor_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> dict:
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    if vendor.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived vendors cannot be sanctions screened")
    try:
        row = SanctionsScreeningService(db).screen_vendor(organization, vendor)
    except SanctionsDatasetUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    AuditService(db).write_audit_log(
        action="vendor.sanctions_screen.computed",
        entity_type="sanctions_screen_result",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "vendor_id": str(vendor.id),
            "match_found": row.match_found,
            "top_score": (row.match_details or {}).get("top_score"),
            "source": (row.match_details or {}).get("source"),
        },
        metadata_json={"source": "tprm_intelligence_satellite"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _result_payload(row)


@router.get("/{vendor_id}/sanctions-screen")
def get_vendor_sanctions_screen(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> dict:
    VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    row = SanctionsScreeningService(db).latest_result(organization.id, vendor_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor sanctions screen result not found")
    return _result_payload(row)


@router.post("/{vendor_id}/sanctions-screen/{result_id}/clear")
def clear_vendor_sanctions_screen(
    vendor_id: uuid.UUID,
    result_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> dict:
    VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    service = SanctionsScreeningService(db)
    row = service.get_result(organization.id, vendor_id, result_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor sanctions screen result not found")
    if row.cleared_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vendor sanctions screen result is already cleared")
    if not row.match_found:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only positive sanctions screen results can be cleared")

    before = {"cleared_by": str(row.cleared_by) if row.cleared_by else None, "cleared_at": row.cleared_at.isoformat() if row.cleared_at else None}
    row.cleared_by = current_user.id
    row.cleared_at = datetime.now(timezone.utc)
    db.flush()
    AuditService(db).write_audit_log(
        action="vendor.sanctions_screen.cleared",
        entity_type="sanctions_screen_result",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"cleared_by": str(row.cleared_by), "cleared_at": row.cleared_at.isoformat()},
        metadata_json={"source": "tprm_intelligence_satellite", "vendor_id": str(vendor_id)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _result_payload(row)
