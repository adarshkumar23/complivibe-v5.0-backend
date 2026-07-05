from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
from app.satellites.tprm_intelligence.security_rating_monitoring import record_vendor_security_rating
from app.satellites.tprm_intelligence.threat_intelligence import ThreatIntelligenceService
from app.satellites.tprm_intelligence.vendor_security_rating import normalize_domain
from app.services.audit_service import AuditService
from app.services.vendor_service import VendorService
from app.services.vendor_supply_chain_service import VendorSupplyChainService

router = APIRouter(prefix="/vendors", tags=["tprm-intelligence"])

# A threat-intelligence finding is only as trustworthy as it is fresh: an old
# "clean" score can mask a compromise that happened since it was computed.
# Surface that staleness to the caller instead of presenting every finding as
# equally current.
THREAT_INTEL_STALE_AFTER_DAYS = 7


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
    age_days: float | None = None
    is_stale = True
    if row.computed_at is not None:
        computed_at = row.computed_at if row.computed_at.tzinfo else row.computed_at.replace(tzinfo=UTC)
        age_days = round((datetime.now(UTC) - computed_at).total_seconds() / 86400.0, 2)
        is_stale = age_days > THREAT_INTEL_STALE_AFTER_DAYS
    return {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "vendor_id": str(row.vendor_id),
        "domain": row.domain,
        "signals_used": row.signals_used,
        "threat_score": float(row.threat_score),
        "indicators_found": row.indicators_found,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
        "days_since_computed": age_days,
        "is_stale": is_stale,
        "stale_after_days": THREAT_INTEL_STALE_AFTER_DAYS,
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

    row = record_vendor_security_rating(
        db,
        organization_id=organization.id,
        vendor=vendor,
        domain=domain,
        actor_user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        source="tprm_intelligence_satellite",
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


@router.get("/{vendor_id}/security-rating/history")
def get_vendor_security_rating_history(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
    limit: int = 50,
) -> dict:
    """Return the rating trend over time so a reviewer sees drift, not just a snapshot."""
    VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    bounded_limit = max(1, min(limit, 200))
    rows = db.execute(
        select(VendorExternalRating)
        .where(VendorExternalRating.organization_id == organization.id, VendorExternalRating.vendor_id == vendor_id)
        .order_by(VendorExternalRating.computed_at.desc(), VendorExternalRating.id.desc())
        .limit(bounded_limit)
    ).scalars().all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor security rating not found")

    history = [_rating_payload(row) for row in rows]  # newest first
    latest_score = history[0]["composite_score"]
    oldest_score = history[-1]["composite_score"]
    score_delta = round(latest_score - oldest_score, 2)
    if len(history) < 2:
        trend = "insufficient_data"
    elif score_delta > 1.0:
        trend = "improving"
    elif score_delta < -1.0:
        trend = "declining"
    else:
        trend = "stable"

    return {
        "vendor_id": str(vendor_id),
        "count": len(history),
        "latest_score": latest_score,
        "score_delta_over_window": score_delta,
        "trend": trend,
        "history": history,
    }


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
        # Assign microsecond-precision computed_at in application code rather
        # than relying on the DB's server_default(func.now()): the primary key
        # is a random UUID (not time-ordered), so if two computes land in the
        # same second (SQLite's CURRENT_TIMESTAMP resolution -- and possible
        # even on Postgres under fast repeated rescoring), "latest" ordering by
        # (computed_at desc, id desc) would silently pick an arbitrary row
        # instead of the most recent one.
        computed_at=datetime.fromisoformat(result["computed_at"]) if result.get("computed_at") else datetime.now(UTC),
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
    if float(row.threat_score) >= 50.0:
        severity = "critical" if float(row.threat_score) >= 80.0 else "high"
        alerts = VendorSupplyChainService(db).propagate_vendor_signal(
            organization_id=organization.id,
            triggering_vendor_id=vendor.id,
            signal_type="threat_intelligence_elevated",
            severity=severity,
            explanation=f"threat intelligence score {float(row.threat_score):.2f} reached the 50.00 monitoring threshold",
            source_entity_type="vendor_threat_intelligence",
            source_entity_id=row.id,
        )
        for alert in alerts:
            AuditService(db).write_audit_log(
                action="vendor_supply_chain.alert_propagated",
                entity_type="vendor_supply_chain_alert",
                entity_id=alert.id,
                organization_id=organization.id,
                actor_user_id=current_user.id,
                after_json={"parent_vendor_id": str(alert.parent_vendor_id), "triggering_vendor_id": str(vendor.id), "signal_type": alert.signal_type, "severity": alert.severity},
                metadata_json={"source": "vendor.threat_intelligence.computed"},
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
    else:
        # Score is back below threshold: close any previously propagated nth-party
        # alerts/flags for this signal so they don't stay stuck on a stale finding.
        resolved = VendorSupplyChainService(db).resolve_vendor_signal(
            organization_id=organization.id,
            triggering_vendor_id=vendor.id,
            signal_type="threat_intelligence_elevated",
            actor_user_id=current_user.id,
        )
        for alert in resolved:
            AuditService(db).write_audit_log(
                action="vendor_supply_chain.alert_propagation_cleared",
                entity_type="vendor_supply_chain_alert",
                entity_id=alert.id,
                organization_id=organization.id,
                actor_user_id=current_user.id,
                after_json={"parent_vendor_id": str(alert.parent_vendor_id), "triggering_vendor_id": str(vendor.id), "signal_type": alert.signal_type},
                metadata_json={"source": "vendor.threat_intelligence.computed"},
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
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor threat intelligence not found")
    return _threat_payload(row)


@router.get("/{vendor_id}/threat-intelligence/history")
def get_vendor_threat_intelligence_history(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
    limit: int = 50,
) -> dict:
    """Return the threat-intel trend over time so a reviewer sees an escalating
    or clearing pattern, not just an isolated snapshot -- and whether the
    latest finding is stale relative to how often this vendor is rescored.
    """
    VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    bounded_limit = max(1, min(limit, 200))
    rows = db.execute(
        select(VendorThreatIntelligence)
        .where(VendorThreatIntelligence.organization_id == organization.id, VendorThreatIntelligence.vendor_id == vendor_id)
        .order_by(VendorThreatIntelligence.computed_at.desc(), VendorThreatIntelligence.id.desc())
        .limit(bounded_limit)
    ).scalars().all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor threat intelligence not found")

    history = [_threat_payload(row) for row in rows]  # newest first
    latest_score = history[0]["threat_score"]
    oldest_score = history[-1]["threat_score"]
    score_delta = round(latest_score - oldest_score, 2)
    if len(history) < 2:
        trend = "insufficient_data"
    elif score_delta > 1.0:
        trend = "escalating"
    elif score_delta < -1.0:
        trend = "improving"
    else:
        trend = "stable"

    return {
        "vendor_id": str(vendor_id),
        "count": len(history),
        "latest_score": latest_score,
        "score_delta_over_window": score_delta,
        "trend": trend,
        "is_stale": history[0]["is_stale"],
        "history": history,
    }


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
    offshore_found = bool(row.offshore_links_found.get("found")) if isinstance(row.offshore_links_found, dict) else False
    if row.adverse_media_found or offshore_found:
        if offshore_found and row.adverse_media_found:
            severity = "critical"
            explanation = f"KYB check for {row.company_name} found both offshore leak links and adverse media coverage"
        elif offshore_found:
            severity = "critical"
            explanation = f"KYB check for {row.company_name} found offshore leak (ICIJ) links requiring beneficial-ownership review"
        else:
            severity = "high"
            explanation = f"KYB check for {row.company_name} found adverse media coverage requiring review"
        alerts = VendorSupplyChainService(db).propagate_vendor_signal(
            organization_id=organization.id,
            triggering_vendor_id=vendor.id,
            signal_type="kyb_aml_risk_flagged",
            severity=severity,
            explanation=explanation,
            source_entity_type="aml_kyc_check",
            source_entity_id=row.id,
            actor_user_id=current_user.id,
        )
        for alert in alerts:
            AuditService(db).write_audit_log(
                action="vendor_supply_chain.alert_propagated",
                entity_type="vendor_supply_chain_alert",
                entity_id=alert.id,
                organization_id=organization.id,
                actor_user_id=current_user.id,
                after_json={"parent_vendor_id": str(alert.parent_vendor_id), "triggering_vendor_id": str(vendor.id), "signal_type": alert.signal_type, "severity": alert.severity},
                metadata_json={"source": "vendor.kyb_check.computed"},
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
