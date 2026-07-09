from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.vendor_external_rating import VendorExternalRating
from app.satellites.tprm_intelligence.vendor_security_rating import VendorSecurityRatingService
from app.services.audit_service import AuditService
from app.services.vendor_supply_chain_service import VendorSupplyChainService

logger = logging.getLogger(__name__)

DEGRADED_THRESHOLD = 70.0
CRITICAL_THRESHOLD = 50.0

# How often a vendor's security rating is refreshed automatically without any
# user action. This is what makes the monitoring "continuous" rather than a
# one-off score a user has to remember to re-trigger.
CONTINUOUS_REFRESH_INTERVAL_DAYS = 7


def record_vendor_security_rating(
    db: Session,
    *,
    organization_id: uuid.UUID,
    vendor: Vendor,
    domain: str,
    actor_user_id: uuid.UUID | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    source: str = "tprm_intelligence_satellite",
) -> VendorExternalRating:
    """Compute, persist, audit, and (if degraded) propagate one security rating.

    Shared by the on-demand POST endpoint and the continuous background sweep
    so both paths stay in lock-step on audit logging and alert propagation.
    """
    result = VendorSecurityRatingService().compute(domain)
    composite_score = result["composite_score"]
    row = VendorExternalRating(
        organization_id=organization_id,
        vendor_id=vendor.id,
        domain=result["domain"],
        signals_used=result["signals_used"],
        composite_score=Decimal(str(composite_score)) if composite_score is not None else None,
        confidence=Decimal(str(result.get("confidence", 0.0))),
        # Set explicitly (microsecond resolution) rather than relying on the
        # DB server default: some backends (SQLite's CURRENT_TIMESTAMP) only
        # have second precision, which made "latest rating" / history
        # ordering ambiguous (and effectively random, since the id tiebreaker
        # is an unordered UUID) whenever two ratings landed in the same
        # second — e.g. two fast successive manual computes.
        computed_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()

    AuditService(db).write_audit_log(
        action="vendor.security_rating.computed",
        entity_type="vendor_external_rating",
        entity_id=row.id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        after_json={
            "vendor_id": str(vendor.id),
            "domain": row.domain,
            "composite_score": float(row.composite_score) if row.composite_score is not None else None,
            "confidence": float(row.confidence),
        },
        metadata_json={"source": source},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # A score of None means zero of the 4 signals returned real data -- there is
    # nothing here to compare against the degraded/critical thresholds, and treating
    # "no data" as "below threshold" would be exactly the false-extreme-swing bug this
    # confidence field exists to prevent. Only compare when a real score exists.
    if row.composite_score is not None and float(row.composite_score) < DEGRADED_THRESHOLD:
        severity = "high" if float(row.composite_score) < CRITICAL_THRESHOLD else "medium"
        alerts = VendorSupplyChainService(db).propagate_vendor_signal(
            organization_id=organization_id,
            triggering_vendor_id=vendor.id,
            signal_type="security_rating_degraded",
            severity=severity,
            explanation=f"security rating score {float(row.composite_score):.2f} is below the {DEGRADED_THRESHOLD:.2f} monitoring threshold",
            source_entity_type="vendor_external_rating",
            source_entity_id=row.id,
        )
        for alert in alerts:
            AuditService(db).write_audit_log(
                action="vendor_supply_chain.alert_propagated",
                entity_type="vendor_supply_chain_alert",
                entity_id=alert.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                after_json={
                    "parent_vendor_id": str(alert.parent_vendor_id),
                    "triggering_vendor_id": str(vendor.id),
                    "signal_type": alert.signal_type,
                    "severity": alert.severity,
                },
                metadata_json={"source": "vendor.security_rating.computed"},
                ip_address=ip_address,
                user_agent=user_agent,
            )

    return row


def run_daily_vendor_security_rating_continuous_refresh(db: Session) -> dict[str, int]:
    """Rescore active vendors whose latest security rating is stale or missing.

    Without this sweep, "continuous monitoring" would only ever run when a
    user happens to click compute again, so a vendor's rating could silently
    degrade for months between manual checks. This keeps every active vendor's
    rating within CONTINUOUS_REFRESH_INTERVAL_DAYS of current, and reuses the
    same audit + supply-chain alert propagation path as the manual endpoint.
    """
    from app.satellites.tprm_intelligence.vendor_security_rating import normalize_domain

    cutoff = datetime.now(UTC) - timedelta(days=CONTINUOUS_REFRESH_INTERVAL_DAYS)

    latest_per_vendor = (
        select(
            VendorExternalRating.vendor_id.label("vendor_id"),
            func.max(VendorExternalRating.computed_at).label("last_computed_at"),
        )
        .group_by(VendorExternalRating.vendor_id)
        .subquery()
    )

    candidates = db.execute(
        select(Vendor, latest_per_vendor.c.last_computed_at)
        .outerjoin(latest_per_vendor, latest_per_vendor.c.vendor_id == Vendor.id)
        .where(
            Vendor.status != "archived",
            Vendor.archived_at.is_(None),
            Vendor.website.is_not(None),
        )
    ).all()

    refreshed = 0
    skipped_stale_not_due = 0
    skipped_invalid_domain = 0
    errors = 0

    for vendor, last_computed_at in candidates:
        if last_computed_at is not None:
            # Some backends (e.g. SQLite) return naive datetimes even for
            # timezone-aware columns; normalize before comparing to `cutoff`.
            if last_computed_at.tzinfo is None:
                last_computed_at = last_computed_at.replace(tzinfo=UTC)
            if last_computed_at > cutoff:
                skipped_stale_not_due += 1
                continue
        try:
            domain = normalize_domain(vendor.website or vendor.name)
        except ValueError:
            skipped_invalid_domain += 1
            continue
        try:
            record_vendor_security_rating(
                db,
                organization_id=vendor.organization_id,
                vendor=vendor,
                domain=domain,
                actor_user_id=None,
                source="tprm_intelligence_continuous_monitoring_sweep",
            )
            db.commit()
            refreshed += 1
        except Exception:
            db.rollback()
            errors += 1
            logger.exception("Continuous vendor security rating refresh failed for vendor %s", vendor.id)

    return {
        "refreshed": refreshed,
        "skipped_stale_not_due": skipped_stale_not_due,
        "skipped_invalid_domain": skipped_invalid_domain,
        "errors": errors,
        "records_processed": refreshed,
    }
