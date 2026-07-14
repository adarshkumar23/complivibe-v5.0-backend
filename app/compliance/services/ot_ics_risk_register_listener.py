"""Subscriber for `ot_ics.finding_ingested`.

Migrated from the former inline `OtIcsFindingService._cascade_finding_to_risk`
direct call (Interconnection Phase 1, Step 3). The publisher now emits on every
finding ingest; this listener performs the identical downstream work -- create a
Risk register entry for a high/critical finding (tracked via finding.risk_id) and
recompute network-segment concentration -- under the flush-only + SAVEPOINT-
isolated bus contract. Segment recompute reuses OtIcsFindingService's existing
method (shared with the finding-resolution flow), so there is one source of truth.
"""
from sqlalchemy import select

from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.ot_ics_asset import OtIcsAsset
from app.models.ot_ics_finding import OtIcsFinding
from app.services.ot_ics_service import FINDING_RISK_CASCADE_SEVERITIES, OtIcsFindingService
from app.services.risk_service import RiskService


class OtIcsRiskRegisterListener:
    def handle(self, payload: EventPayload) -> None:
        if payload.event_type != EventType.OT_ICS_FINDING_INGESTED:
            return
        db = payload.db
        org_id = payload.org_id  # strict tenant scope: trust only the event's org

        finding = db.execute(
            select(OtIcsFinding).where(
                OtIcsFinding.id == payload.entity_id,
                OtIcsFinding.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if finding is None or finding.severity not in FINDING_RISK_CASCADE_SEVERITIES:
            return
        # A finding creates at most one Risk (guarded by finding.risk_id).
        if finding.risk_id is not None:
            return
        asset = db.execute(
            select(OtIcsAsset).where(OtIcsAsset.id == finding.asset_id, OtIcsAsset.organization_id == org_id)
        ).scalar_one_or_none()
        if asset is None:
            return

        description = (
            f"OT/ICS convergence monitoring detected a {finding.severity}-severity "
            f"{finding.finding_type.replace('_', ' ')} finding on asset {asset.name!r} "
            f"({asset.asset_type}, network segment {asset.network_segment or 'unspecified'})."
        )
        if finding.description:
            description += f" {finding.description}"

        risk = RiskService(db).create_risk_from_service(
            organization_id=org_id,
            title=f"OT/ICS finding: {finding.finding_type.replace('_', ' ')} on {asset.name}",
            description=description,
            category="operational",
            likelihood=3 if finding.severity == "high" else 4,
            impact=4 if finding.severity == "high" else 5,
            treatment_strategy="mitigate",
            risk_context_external=(
                f"Source: OT/ICS convergence-monitoring agent ingest. Finding id {finding.id}, "
                f"asset id {asset.id}, detected_at {finding.detected_at.isoformat()}."
            ),
            metadata_json={
                "source": "ot_ics",
                "finding_id": str(finding.id),
                "asset_id": str(asset.id),
                "network_segment": asset.network_segment,
                "finding_type": finding.finding_type,
                "severity": finding.severity,
            },
            created_by_user_id=None,
            audit_source="ot_ics_finding_ingest",
        )
        finding.risk_id = risk.id
        db.flush()

        if asset.network_segment:
            # Shared with the finding-resolution flow; single source of truth.
            OtIcsFindingService(db)._recompute_segment_risk(org_id, asset.network_segment)

    def register(self, bus: EventBus) -> None:
        bus.subscribe(EventType.OT_ICS_FINDING_INGESTED, self.handle)
