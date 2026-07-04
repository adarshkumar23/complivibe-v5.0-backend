from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.models.aml_kyc_check import AmlKycCheck
from app.models.vendor_external_rating import VendorExternalRating
from app.models.vendor_threat_intelligence import VendorThreatIntelligence
from app.satellites.tprm_intelligence.kyb_verification import KYBVerificationService
from app.satellites.tprm_intelligence.threat_intelligence import ThreatIntelligenceService
from app.satellites.tprm_intelligence.vendor_security_rating import VendorSecurityRatingService, normalize_domain
from app.services.audit_service import AuditService
from app.services.vendor_service import VendorService

router = APIRouter(prefix="/vendors", tags=["tprm-intelligence"])


def _rating_payload(row: VendorExternalRating) -> dict:
    return {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "vendor_id": str(row.vendor_id),
        "domain": row.domain,
        "signals_used": row.signals_used,
        "composite_score": float(row.composite_score),
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
    }


def _threat_payload(row: VendorThreatIntelligence) -> dict:
    return {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "vendor_id": str(row.vendor_id),
        "domain": row.domain,
        "signals_used": row.signals_used,
        "threat_score": float(row.threat_score),
        "indicators_found": row.indicators_found,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
    }


def _kyb_payload(row: AmlKycCheck) -> dict:
    return {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "vendor_id": str(row.vendor_id),
        "company_name": row.company_name,
        "signals_used": row.signals_used,
        "offshore_links_found": row.offshore_links_found,
        "ubo_data": row.ubo_data,
        "adverse_media_found": row.adverse_media_found,
        "checked_at": row.checked_at.isoformat() if row.checked_at else None,
    }


@router.post("/{vendor_id}/security-rating/compute", status_code=status.HTTP_201_CREATED)
def compute_vendor_security_rating(
    vendor_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> dict:
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    if vendor.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived vendors cannot be rescored")
    domain_source = vendor.website or vendor.name
    try:
        domain = normalize_domain(domain_source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    result = VendorSecurityRatingService().compute(domain)
    row = VendorExternalRating(
        organization_id=organization.id,
        vendor_id=vendor.id,
        domain=result["domain"],
        signals_used=result["signals_used"],
        composite_score=Decimal(str(result["composite_score"])),
    )
    db.add(row)
    db.flush()
    AuditService(db).write_audit_log(
        action="vendor.security_rating.computed",
        entity_type="vendor_external_rating",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"vendor_id": str(vendor.id), "domain": row.domain, "composite_score": float(row.composite_score)},
        metadata_json={"source": "tprm_intelligence_satellite"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _rating_payload(row)


@router.get("/{vendor_id}/security-rating")
def get_vendor_security_rating(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> dict:
    VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    row = db.execute(
        select(VendorExternalRating)
        .where(VendorExternalRating.organization_id == organization.id, VendorExternalRating.vendor_id == vendor_id)
        .order_by(VendorExternalRating.computed_at.desc(), VendorExternalRating.id.desc())
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor security rating not found")
    return _rating_payload(row)


@router.post("/{vendor_id}/threat-intelligence/compute", status_code=status.HTTP_201_CREATED)
def compute_vendor_threat_intelligence(
    vendor_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> dict:
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    if vendor.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived vendors cannot be rescored")
    try:
        domain = normalize_domain(vendor.website or vendor.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    result = ThreatIntelligenceService().compute(domain)
    row = VendorThreatIntelligence(
        organization_id=organization.id,
        vendor_id=vendor.id,
        domain=result["domain"],
        signals_used=result["signals_used"],
        threat_score=Decimal(str(result["threat_score"])),
        indicators_found=result["indicators_found"],
    )
    db.add(row)
    db.flush()
    AuditService(db).write_audit_log(
        action="vendor.threat_intelligence.computed",
        entity_type="vendor_threat_intelligence",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"vendor_id": str(vendor.id), "domain": row.domain, "threat_score": float(row.threat_score)},
        metadata_json={"source": "tprm_intelligence_satellite"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _threat_payload(row)


@router.get("/{vendor_id}/threat-intelligence")
def get_vendor_threat_intelligence(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> dict:
    VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    row = db.execute(
        select(VendorThreatIntelligence)
        .where(VendorThreatIntelligence.organization_id == organization.id, VendorThreatIntelligence.vendor_id == vendor_id)
        .order_by(VendorThreatIntelligence.computed_at.desc(), VendorThreatIntelligence.id.desc())
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor threat intelligence not found")
    return _threat_payload(row)


@router.post("/{vendor_id}/kyb-check/compute", status_code=status.HTTP_201_CREATED)
def compute_vendor_kyb_check(
    vendor_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:write")),
) -> dict:
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    if vendor.status == "archived":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived vendors cannot be checked")
    try:
        result = KYBVerificationService().compute(vendor.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    row = AmlKycCheck(
        organization_id=organization.id,
        vendor_id=vendor.id,
        company_name=result["company_name"],
        signals_used=result["signals_used"],
        offshore_links_found=result["offshore_links_found"],
        ubo_data=result["ubo_data"],
        adverse_media_found=result["adverse_media_found"],
    )
    db.add(row)
    db.flush()
    AuditService(db).write_audit_log(
        action="vendor.kyb_check.computed",
        entity_type="aml_kyc_check",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "vendor_id": str(vendor.id),
            "company_name": row.company_name,
            "adverse_media_found": row.adverse_media_found,
            "offshore_links_found": row.offshore_links_found.get("found") if isinstance(row.offshore_links_found, dict) else None,
        },
        metadata_json={"source": "tprm_intelligence_satellite"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _kyb_payload(row)


@router.get("/{vendor_id}/kyb-check")
def get_vendor_kyb_check(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> dict:
    VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    row = db.execute(
        select(AmlKycCheck)
        .where(AmlKycCheck.organization_id == organization.id, AmlKycCheck.vendor_id == vendor_id)
        .order_by(AmlKycCheck.checked_at.desc(), AmlKycCheck.id.desc())
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor KYB check not found")
    return _kyb_payload(row)
