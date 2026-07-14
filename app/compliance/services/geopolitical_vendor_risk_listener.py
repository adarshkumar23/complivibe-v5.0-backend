"""Subscriber for `geopolitical.signal_critical`.

Migrated from the former inline
`GeopoliticalRiskService._cascade_critical_signals_to_vendor_risk` direct call
(Interconnection Phase 1, Step 3). The publisher now DETECTS that a critical GDELT
signal landed for a region and emits (carrying the worst signal id + region); this
listener performs the identical downstream work -- escalate each exposed vendor's
risk_tier (with `vendor.risk_tier_escalated` audit) and create one Risk register
entry per vendor/region exposure -- under the flush-only + SAVEPOINT-isolated bus
contract.
"""
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.geopolitical_risk_signal import GeopoliticalRiskSignal
from app.models.vendor import Vendor
from app.models.vendor_geopolitical_exposure import VendorGeopoliticalExposure
from app.services.audit_service import AuditService
from app.services.geopolitical_risk_service import CASCADE_SEVERITY, _VENDOR_RISK_TIER_RANK
from app.services.risk_service import RiskService


class GeopoliticalVendorRiskListener:
    def handle(self, payload: EventPayload) -> None:
        if payload.event_type != EventType.GEOPOLITICAL_SIGNAL_CRITICAL:
            return
        db = payload.db
        org_id = payload.org_id  # strict tenant scope: trust only the event's org
        region_query = payload.payload.get("region")
        actor_id = payload.triggered_by_user_id

        # The worst critical signal for this ingest was chosen by the publisher and
        # carried as the event entity; re-load it tenant-scoped.
        worst = db.execute(
            select(GeopoliticalRiskSignal).where(
                GeopoliticalRiskSignal.id == payload.entity_id,
                GeopoliticalRiskSignal.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if worst is None or region_query is None:
            return

        exposures = db.execute(
            select(VendorGeopoliticalExposure).where(
                VendorGeopoliticalExposure.organization_id == org_id,
                VendorGeopoliticalExposure.region == region_query,
                VendorGeopoliticalExposure.deleted_at.is_(None),
            )
        ).scalars().all()
        if not exposures:
            return

        audit = AuditService(db)
        for exposure in exposures:
            vendor = db.get(Vendor, exposure.vendor_id)
            if vendor is None or vendor.status == "archived" or vendor.organization_id != org_id:
                continue

            if _VENDOR_RISK_TIER_RANK.get(CASCADE_SEVERITY, 0) > _VENDOR_RISK_TIER_RANK.get(vendor.risk_tier, 0):
                before_tier = vendor.risk_tier
                vendor.risk_tier = CASCADE_SEVERITY
                db.flush()
                audit.write_audit_log(
                    action="vendor.risk_tier_escalated",
                    entity_type="vendor",
                    entity_id=vendor.id,
                    organization_id=org_id,
                    actor_user_id=actor_id,
                    before_json={"risk_tier": before_tier},
                    after_json={"risk_tier": CASCADE_SEVERITY, "reason": "geopolitical_critical_signal"},
                    metadata_json={
                        "source": "geopolitical_risk",
                        "region": region_query,
                        "signal_id": str(worst.id),
                    },
                )

            exposure.last_cascaded_severity = CASCADE_SEVERITY
            exposure.last_cascaded_at = datetime.now(UTC)

            if exposure.cascaded_risk_id is None:
                description = (
                    f"A critical geopolitical signal was detected for {region_query!r}, a region "
                    f"{vendor.name} is exposed to: {worst.headline or 'no headline available'!r} "
                    f"(category: {worst.category})."
                )
                risk = RiskService(db).create_risk_from_service(
                    organization_id=org_id,
                    title=f"Critical geopolitical exposure: {vendor.name} in {region_query}",
                    description=description,
                    category="vendor",
                    likelihood=4,
                    impact=5,
                    treatment_strategy="mitigate",
                    risk_context_external=(
                        f"Source: GDELT DOC 2.0 API. Signal id {worst.id}, category "
                        f"{worst.category}, detected_at {worst.detected_at.isoformat() if worst.detected_at else None}."
                    ),
                    metadata_json={
                        "source": "geopolitical_risk",
                        "vendor_id": str(vendor.id),
                        "region": region_query,
                        "geopolitical_signal_id": str(worst.id),
                    },
                    created_by_user_id=actor_id,
                    audit_source="geopolitical_risk",
                )
                exposure.cascaded_risk_id = risk.id
            db.flush()

    def register(self, bus: EventBus) -> None:
        bus.subscribe(EventType.GEOPOLITICAL_SIGNAL_CRITICAL, self.handle)
