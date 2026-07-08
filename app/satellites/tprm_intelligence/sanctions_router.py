from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.sanctions_screen_result import SanctionsScreenResult
from app.models.user import User
from app.models.vendor import Vendor
from app.satellites.tprm_intelligence.sanctions_screening import (
    SANCTIONS_ESCALATED_RISK_TIER,
    SANCTIONS_RESULT_STALE_AFTER_DAYS,
    SanctionsDatasetUnavailable,
    SanctionsScreeningService,
    screen_vendor_and_apply_effects,
)
from app.services.audit_service import AuditService
from app.services.vendor_service import VendorService
from app.services.vendor_supply_chain_service import VendorSupplyChainService

router = APIRouter(prefix="/vendors", tags=["tprm-intelligence"])


def _result_payload(row: SanctionsScreenResult, vendor: Vendor | None = None) -> dict:
    details = row.match_details or {}
    age_days: float | None = None
    is_stale = True
    if row.screened_at is not None:
        screened_at = row.screened_at if row.screened_at.tzinfo else row.screened_at.replace(tzinfo=UTC)
        age_days = round((datetime.now(UTC) - screened_at).total_seconds() / 86400.0, 2)
        is_stale = age_days > SANCTIONS_RESULT_STALE_AFTER_DAYS
    # A result screened under an old company name is only as trustworthy as that name:
    # if the vendor has since been renamed (merger, rebrand, data correction) the result
    # reflects the WRONG query and must not be presented as current coverage for the
    # vendor's current identity.
    query_name = details.get("query_name")
    name_changed_since_screening = bool(vendor is not None and query_name and query_name != vendor.name)
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
        "near_miss": bool(details.get("near_miss")),
        "cleared_by": str(row.cleared_by) if row.cleared_by else None,
        "cleared_at": row.cleared_at.isoformat() if row.cleared_at else None,
        "days_since_screened": age_days,
        "is_stale": is_stale,
        "stale_after_days": SANCTIONS_RESULT_STALE_AFTER_DAYS,
        "name_changed_since_screening": name_changed_since_screening,
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
        row = screen_vendor_and_apply_effects(
            db,
            organization,
            vendor,
            actor_user_id=current_user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except SanctionsDatasetUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    db.commit()
    db.refresh(row)
    return _result_payload(row, vendor)


@router.get("/{vendor_id}/sanctions-screen")
def get_vendor_sanctions_screen(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> dict:
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    row = SanctionsScreeningService(db).latest_result(organization.id, vendor_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor sanctions screen result not found")
    return _result_payload(row, vendor)


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
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
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
    # This match auto-escalated the vendor's own risk tier to "critical". Since a human
    # has now reviewed and confirmed it was a false positive, restore the tier the vendor
    # had immediately before that escalation (only if nothing else has since re-escalated
    # it away from "critical").
    pre_escalation_tier = (row.match_details or {}).get("pre_escalation_risk_tier")
    if pre_escalation_tier and vendor.risk_tier == SANCTIONS_ESCALATED_RISK_TIER:
        tier_before = vendor.risk_tier
        vendor.risk_tier = pre_escalation_tier
        db.flush()
        AuditService(db).write_audit_log(
            action="vendor.risk_tier_escalated",
            entity_type="vendor",
            entity_id=vendor.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            before_json={"risk_tier": tier_before},
            after_json={"risk_tier": pre_escalation_tier, "reason": "sanctions_match_cleared"},
            metadata_json={"source": "tprm_intelligence_satellite", "sanctions_screen_result_id": str(row.id)},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    # A human has reviewed and cleared the match: close the nth-party alert/flag this
    # match propagated upstream so first-party vendors aren't stuck flagged forever.
    resolved = VendorSupplyChainService(db).resolve_vendor_signal(
        organization_id=organization.id,
        triggering_vendor_id=vendor_id,
        signal_type="sanctions_match_found",
        actor_user_id=current_user.id,
    )
    for alert in resolved:
        AuditService(db).write_audit_log(
            action="vendor_supply_chain.alert_propagation_cleared",
            entity_type="vendor_supply_chain_alert",
            entity_id=alert.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"parent_vendor_id": str(alert.parent_vendor_id), "triggering_vendor_id": str(vendor_id), "signal_type": alert.signal_type},
            metadata_json={"source": "vendor.sanctions_screen.cleared"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    db.commit()
    db.refresh(row)
    return _result_payload(row, vendor)
