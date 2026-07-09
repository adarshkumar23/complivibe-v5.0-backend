from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.models.aml_kyc_check import AmlKycCheck
from app.models.vendor import Vendor
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
# Matches the daily vendor_kyb_rescreen_sweep cadence: a KYB/AML check older than a week
# most likely means the sweep isn't reaching this vendor rather than that nothing changed
# in beneficial-ownership or adverse-media coverage since.
KYB_STALE_AFTER_DAYS = 7
KYB_ESCALATION_METADATA_PREVIOUS_TIER = "_kyb_pre_escalation_risk_tier"
KYB_ESCALATION_METADATA_ESCALATED_TO = "_kyb_escalated_to_risk_tier"
RISK_TIER_RANK = {"not_assessed": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# The 5 independent signals KYBVerificationService.compute() aggregates. GLEIF
# succeeding while the other 4 fail/skip silently used to leave an overall
# "pass" resting on as little as 1 of 5 real signals with zero visibility into
# that -- see KYBVerificationService.compute for how each is produced.
KYB_SOURCE_KEYS = ("gleif", "opencorporates", "icij_offshore_leaks", "openownership", "gdelt_adverse_media")


def _kyb_sources_checked(signals_used: dict | None) -> list[dict[str, Any]]:
    """Per-source status so a compliance officer reviewing a KYB result can see
    exactly which of the 5 signals actually contributed vs. silently failed or
    were skipped, instead of that detail being buried (or absent) inside the
    aggregate pass/fail decision.
    """
    signals_used = signals_used if isinstance(signals_used, dict) else {}
    rows = []
    for source in KYB_SOURCE_KEYS:
        signal = signals_used.get(source)
        if not isinstance(signal, dict):
            rows.append({"source": source, "status": "not_checked", "detail": "No result recorded for this source"})
            continue
        status_value = signal.get("status", "unknown")
        detail = signal.get("message") or signal.get("coverage_limitation") or None
        rows.append({"source": source, "status": status_value, "detail": detail})
    return rows


def _kyb_evidence_summary(sources_checked: list[dict[str, Any]]) -> dict[str, Any]:
    available = sum(1 for row in sources_checked if row["status"] == "available")
    total = len(sources_checked)
    return {
        "sources_checked": sources_checked,
        "sources_available_count": available,
        "sources_total_count": total,
        # A result standing on fewer than half its possible signals is thin
        # evidence, even if the aggregate decision above reads "clean" -- this
        # never overrides that decision, it just makes the thinness visible.
        "insufficient_evidence": available < 3,
    }


def _score_trend(history: list[dict], score_key: str, *, higher_is_better: bool) -> dict[str, Any]:
    """Compute a score delta/trend over a history window, skipping entries with no
    real score (``None`` -- zero signals available for that computation) rather than
    letting a missing-data snapshot masquerade as an extreme score movement.
    """
    scored = [entry[score_key] for entry in history if entry[score_key] is not None]
    if len(scored) < 2:
        return {"latest_score": history[0][score_key] if history else None, "score_delta_over_window": None, "trend": "insufficient_data"}
    latest_score = scored[0]
    oldest_score = scored[-1]
    score_delta = round(latest_score - oldest_score, 2)
    if score_delta > 1.0:
        trend = "improving" if higher_is_better else "escalating"
    elif score_delta < -1.0:
        trend = "declining" if higher_is_better else "improving"
    else:
        trend = "stable"
    return {"latest_score": latest_score, "score_delta_over_window": score_delta, "trend": trend}


def _rating_payload(row: VendorExternalRating) -> dict:
    return {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "vendor_id": str(row.vendor_id),
        "domain": row.domain,
        "signals_used": row.signals_used,
        "composite_score": float(row.composite_score) if row.composite_score is not None else None,
        # How much of the score is actually backed by real signal data (0-100). A low
        # confidence score means "we barely have any data", not "we have good data
        # that confirms a good/bad posture" -- read composite_score alongside this.
        "confidence": float(row.confidence),
        "has_sufficient_data": float(row.confidence) >= 50.0,
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
        "threat_score": float(row.threat_score) if row.threat_score is not None else None,
        # How much of the score is actually backed by real signal data (0-100). Read
        # alongside threat_score: a None/low-confidence score means "no data", never
        # treat it as "confirmed clean".
        "confidence": float(row.confidence),
        "has_sufficient_data": float(row.confidence) >= 50.0,
        "indicators_found": row.indicators_found,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
        "days_since_computed": age_days,
        "is_stale": is_stale,
        "stale_after_days": THREAT_INTEL_STALE_AFTER_DAYS,
    }


def _kyb_payload(row: AmlKycCheck, vendor: Vendor | None = None) -> dict:
    age_days: float | None = None
    is_stale = True
    if row.checked_at is not None:
        checked_at = row.checked_at if row.checked_at.tzinfo else row.checked_at.replace(tzinfo=UTC)
        age_days = round((datetime.now(UTC) - checked_at).total_seconds() / 86400.0, 2)
        is_stale = age_days > KYB_STALE_AFTER_DAYS
    name_changed_since_check = bool(vendor is not None and row.company_name and row.company_name != vendor.name)
    no_verifiable_registration = _no_verifiable_registration(row.signals_used)
    sources_checked = _kyb_sources_checked(row.signals_used)
    payload = {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "vendor_id": str(row.vendor_id),
        "company_name": row.company_name,
        "signals_used": row.signals_used,
        "offshore_links_found": row.offshore_links_found,
        "ubo_data": row.ubo_data,
        "adverse_media_found": row.adverse_media_found,
        "checked_at": row.checked_at.isoformat() if row.checked_at else None,
        "days_since_checked": age_days,
        "is_stale": is_stale,
        "stale_after_days": KYB_STALE_AFTER_DAYS,
        "name_changed_since_check": name_changed_since_check,
        "no_verifiable_registration": no_verifiable_registration,
    }
    payload.update(_kyb_evidence_summary(sources_checked))
    return payload


def _no_verifiable_registration(signals_used: dict | None) -> bool:
    """A vendor that appears in neither GLEIF (LEI registry) nor OpenCorporates (company
    registry search) is a classic shell-company red flag - not proof of wrongdoing, but a
    coverage gap that today is silently dropped because ``_kyb_risk`` only looks at
    offshore-leak/adverse-media hits. Both signals must have actually returned ("available")
    with zero matches; if either signal errored or was skipped (e.g. no OpenCorporates API
    key configured), we don't have enough coverage to make this call either way.
    """
    if not isinstance(signals_used, dict):
        return False
    gleif = signals_used.get("gleif") or {}
    opencorporates = signals_used.get("opencorporates") or {}
    if gleif.get("status") != "available" or opencorporates.get("status") != "available":
        return False
    return int(gleif.get("match_count") or 0) == 0 and int(opencorporates.get("match_count") or 0) == 0


def _kyb_risk(result_or_row: dict | AmlKycCheck) -> tuple[bool, str | None, str | None]:
    if isinstance(result_or_row, AmlKycCheck):
        company_name = result_or_row.company_name
        offshore_links_found = result_or_row.offshore_links_found
        adverse_media_found = result_or_row.adverse_media_found
        signals_used = result_or_row.signals_used
    else:
        company_name = result_or_row["company_name"]
        offshore_links_found = result_or_row["offshore_links_found"]
        adverse_media_found = result_or_row["adverse_media_found"]
        signals_used = result_or_row.get("signals_used")
    offshore_found = bool(offshore_links_found.get("found")) if isinstance(offshore_links_found, dict) else False
    if adverse_media_found or offshore_found:
        if offshore_found and adverse_media_found:
            return True, "critical", f"KYB check for {company_name} found both offshore leak links and adverse media coverage"
        if offshore_found:
            return True, "critical", f"KYB check for {company_name} found offshore leak links requiring beneficial-ownership review"
        return True, "high", f"KYB check for {company_name} found adverse media coverage requiring review"
    if _no_verifiable_registration(signals_used):
        return (
            True,
            "medium",
            f"KYB check for {company_name} found no verifiable corporate registration in GLEIF or OpenCorporates",
        )
    return False, None, None


def _refresh_existing_concentration_detection(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    audit_source: str,
) -> None:
    from app.services.vendor_concentration_risk_service import VendorConcentrationRiskService

    concentration_service = VendorConcentrationRiskService(db)
    existing_detection = concentration_service.current(organization_id)
    if existing_detection is None:
        return
    detection, risk_created, state_changed = concentration_service.recompute(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        threshold_hhi_score=existing_detection.threshold_hhi_score,
    )
    if state_changed:
        AuditService(db).write_audit_log(
            action="vendor_concentration_risk.recomputed",
            entity_type="vendor_concentration_risk_detection",
            entity_id=detection.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "status": detection.status,
                "hhi_score": detection.hhi_score,
                "risk_id": str(detection.risk_id) if detection.risk_id else None,
            },
            metadata_json={"source": audit_source, "risk_created": risk_created},
        )


def _restore_kyb_escalated_vendor_tier(
    db: Session,
    *,
    organization_id: uuid.UUID,
    vendor: Vendor,
    actor_user_id: uuid.UUID | None,
    audit_source: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    prior_rows = db.execute(
        select(AmlKycCheck)
        .where(AmlKycCheck.organization_id == organization_id, AmlKycCheck.vendor_id == vendor.id)
        .order_by(AmlKycCheck.checked_at.desc(), AmlKycCheck.id.desc())
    ).scalars().all()
    restore_tier = None
    escalated_to = None
    for prior in prior_rows:
        signals = prior.signals_used if isinstance(prior.signals_used, dict) else {}
        restore_tier = signals.get(KYB_ESCALATION_METADATA_PREVIOUS_TIER)
        escalated_to = signals.get(KYB_ESCALATION_METADATA_ESCALATED_TO)
        if restore_tier and escalated_to:
            break
    if not restore_tier or not escalated_to or vendor.risk_tier != escalated_to:
        return
    before_tier = vendor.risk_tier
    vendor.risk_tier = restore_tier
    db.flush()
    AuditService(db).write_audit_log(
        action="vendor.risk_tier_escalated",
        entity_type="vendor",
        entity_id=vendor.id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        before_json={"risk_tier": before_tier},
        after_json={"risk_tier": restore_tier, "reason": "kyb_aml_risk_recovered"},
        metadata_json={"source": audit_source},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _refresh_existing_concentration_detection(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        audit_source=audit_source,
    )


def compute_vendor_kyb_check_and_apply_effects(
    db: Session,
    organization: Organization,
    vendor: Vendor,
    *,
    actor_user_id: uuid.UUID | None,
    audit_source: str = "tprm_intelligence_satellite",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AmlKycCheck:
    try:
        result = KYBVerificationService().compute(vendor.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    has_risk, severity, explanation = _kyb_risk(result)
    signals_used: dict[str, Any] = dict(result.get("signals_used") or {})
    if has_risk and severity and RISK_TIER_RANK.get(severity, 0) > RISK_TIER_RANK.get(vendor.risk_tier, 0):
        signals_used[KYB_ESCALATION_METADATA_PREVIOUS_TIER] = vendor.risk_tier
        signals_used[KYB_ESCALATION_METADATA_ESCALATED_TO] = severity

    row = AmlKycCheck(
        organization_id=organization.id,
        vendor_id=vendor.id,
        checked_at=datetime.now(UTC),
        company_name=result["company_name"],
        signals_used=signals_used,
        offshore_links_found=result["offshore_links_found"],
        ubo_data=result["ubo_data"],
        adverse_media_found=result["adverse_media_found"],
    )
    db.add(row)
    db.flush()
    audit = AuditService(db)
    audit.write_audit_log(
        action="vendor.kyb_check.computed",
        entity_type="aml_kyc_check",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=actor_user_id,
        after_json={
            "vendor_id": str(vendor.id),
            "company_name": row.company_name,
            "adverse_media_found": row.adverse_media_found,
            "offshore_links_found": row.offshore_links_found.get("found") if isinstance(row.offshore_links_found, dict) else None,
        },
        metadata_json={"source": audit_source},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if has_risk and severity and explanation:
        if RISK_TIER_RANK.get(severity, 0) > RISK_TIER_RANK.get(vendor.risk_tier, 0):
            before_tier = vendor.risk_tier
            vendor.risk_tier = severity
            db.flush()
            audit.write_audit_log(
                action="vendor.risk_tier_escalated",
                entity_type="vendor",
                entity_id=vendor.id,
                organization_id=organization.id,
                actor_user_id=actor_user_id,
                before_json={"risk_tier": before_tier},
                after_json={"risk_tier": severity, "reason": "kyb_aml_risk_flagged"},
                metadata_json={"source": audit_source, "aml_kyc_check_id": str(row.id)},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            _refresh_existing_concentration_detection(
                db,
                organization_id=organization.id,
                actor_user_id=actor_user_id,
                audit_source=audit_source,
            )
        alerts = VendorSupplyChainService(db).propagate_vendor_signal(
            organization_id=organization.id,
            triggering_vendor_id=vendor.id,
            signal_type="kyb_aml_risk_flagged",
            severity=severity,
            explanation=explanation,
            source_entity_type="aml_kyc_check",
            source_entity_id=row.id,
            actor_user_id=actor_user_id,
        )
        for alert in alerts:
            audit.write_audit_log(
                action="vendor_supply_chain.alert_propagated",
                entity_type="vendor_supply_chain_alert",
                entity_id=alert.id,
                organization_id=organization.id,
                actor_user_id=actor_user_id,
                after_json={"parent_vendor_id": str(alert.parent_vendor_id), "triggering_vendor_id": str(vendor.id), "signal_type": alert.signal_type, "severity": alert.severity},
                metadata_json={"source": "vendor.kyb_check.computed"},
                ip_address=ip_address,
                user_agent=user_agent,
            )
    else:
        resolved_alerts = VendorSupplyChainService(db).resolve_vendor_signal(
            organization_id=organization.id,
            triggering_vendor_id=vendor.id,
            signal_type="kyb_aml_risk_flagged",
            actor_user_id=actor_user_id,
        )
        if resolved_alerts:
            audit.write_audit_log(
                action="vendor_supply_chain.alert_propagation_cleared",
                entity_type="vendor",
                entity_id=vendor.id,
                organization_id=organization.id,
                actor_user_id=actor_user_id,
                after_json={"signal_type": "kyb_aml_risk_flagged", "resolved_alert_count": len(resolved_alerts)},
                metadata_json={"source": "vendor.kyb_check.computed"},
                ip_address=ip_address,
                user_agent=user_agent,
            )
        _restore_kyb_escalated_vendor_tier(
            db,
            organization_id=organization.id,
            vendor=vendor,
            actor_user_id=actor_user_id,
            audit_source=audit_source,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    return row


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
        .limit(1)
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
    trend_info = _score_trend(history, "composite_score", higher_is_better=True)

    return {
        "vendor_id": str(vendor_id),
        "count": len(history),
        **trend_info,
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
    threat_score = result["threat_score"]
    row = VendorThreatIntelligence(
        organization_id=organization.id,
        vendor_id=vendor.id,
        domain=result["domain"],
        signals_used=result["signals_used"],
        threat_score=Decimal(str(threat_score)) if threat_score is not None else None,
        confidence=Decimal(str(result.get("confidence", 0.0))),
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
        after_json={
            "vendor_id": str(vendor.id),
            "domain": row.domain,
            "threat_score": float(row.threat_score) if row.threat_score is not None else None,
            "confidence": float(row.confidence),
        },
        metadata_json={"source": "tprm_intelligence_satellite"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    # A None threat_score means zero signals returned real data -- there is nothing to
    # compare against the elevated-threat threshold, and a fabricated 0.0 previously
    # made "no data" indistinguishable from (and read as) "confirmed clean". Only
    # evaluate the threshold when a real score exists.
    if row.threat_score is not None and float(row.threat_score) >= 50.0:
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
    trend_info = _score_trend(history, "threat_score", higher_is_better=False)

    return {
        "vendor_id": str(vendor_id),
        "count": len(history),
        **trend_info,
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
    row = compute_vendor_kyb_check_and_apply_effects(
        db,
        organization,
        vendor,
        actor_user_id=current_user.id,
        audit_source="tprm_intelligence_satellite",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _kyb_payload(row, vendor)


def run_periodic_vendor_kyb_rescreen_sweep(db: Session) -> dict[str, int]:
    vendor_ids = db.execute(
        select(Vendor.id).where(Vendor.status != "archived").order_by(Vendor.organization_id, Vendor.id)
    ).scalars().all()

    screened = 0
    risk_flags_found = 0
    errors = 0
    for vendor_id in vendor_ids:
        try:
            vendor = db.get(Vendor, vendor_id)
            if vendor is None:
                continue
            organization = db.get(Organization, vendor.organization_id)
            if organization is None:
                continue
            row = compute_vendor_kyb_check_and_apply_effects(
                db,
                organization,
                vendor,
                actor_user_id=None,
                audit_source="kyb_rescreen_sweep",
            )
            db.commit()
            screened += 1
            has_risk, _, _ = _kyb_risk(row)
            if has_risk:
                risk_flags_found += 1
        except Exception:
            db.rollback()
            errors += 1

    return {
        "vendors_screened": screened,
        "risk_flags_found": risk_flags_found,
        "errors": errors,
        "records_processed": screened,
    }


@router.get("/{vendor_id}/kyb-check")
def get_vendor_kyb_check(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
) -> dict:
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    row = db.execute(
        select(AmlKycCheck)
        .where(AmlKycCheck.organization_id == organization.id, AmlKycCheck.vendor_id == vendor_id)
        .order_by(AmlKycCheck.checked_at.desc(), AmlKycCheck.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor KYB check not found")
    return _kyb_payload(row, vendor)


_KYB_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1}


@router.get("/{vendor_id}/kyb-check/history")
def get_vendor_kyb_check_history(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendors:read")),
    limit: int = 50,
) -> dict:
    """Return the KYB/AML screening trend over time so a reviewer sees an escalating
    or clearing beneficial-ownership/adverse-media pattern, not just an isolated
    snapshot -- mirrors the ``/security-rating/history`` and
    ``/threat-intelligence/history`` endpoints (same pagination, auth/org-scoping,
    and response-shape conventions) so KYB/AML has the same historical visibility as
    its sibling vendor-intelligence signals.
    """
    vendor = VendorService(db).require_vendor_in_org(organization.id, vendor_id)
    bounded_limit = max(1, min(limit, 200))
    rows = db.execute(
        select(AmlKycCheck)
        .where(AmlKycCheck.organization_id == organization.id, AmlKycCheck.vendor_id == vendor_id)
        .order_by(AmlKycCheck.checked_at.desc(), AmlKycCheck.id.desc())
        .limit(bounded_limit)
    ).scalars().all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor KYB check not found")

    history = [_kyb_payload(row, vendor) for row in rows]  # newest first

    # KYB/AML doesn't produce a continuous numeric score like security-rating/threat-
    # intelligence -- its output is a has_risk/severity determination per check. Trend
    # is derived from the severity rank instead of a score delta, but the response
    # shape (count, trend, is_stale, history) intentionally matches the sibling
    # endpoints above.
    risk_flags = [_kyb_risk(row) for row in rows]
    latest_has_risk, latest_severity, _ = risk_flags[0]
    if len(rows) < 2:
        trend = "insufficient_data"
    else:
        oldest_has_risk, oldest_severity, _ = risk_flags[-1]
        latest_rank = _KYB_SEVERITY_RANK.get(latest_severity, 0) if latest_has_risk else 0
        oldest_rank = _KYB_SEVERITY_RANK.get(oldest_severity, 0) if oldest_has_risk else 0
        if latest_rank > oldest_rank:
            trend = "escalating"
        elif latest_rank < oldest_rank:
            trend = "improving"
        else:
            trend = "stable"

    return {
        "vendor_id": str(vendor_id),
        "count": len(history),
        "latest_has_risk": latest_has_risk,
        "latest_severity": latest_severity,
        "trend": trend,
        "is_stale": history[0]["is_stale"],
        "history": history,
    }
