"""Subscriber for `vendor.assessment_stale`.

Migrated from the former inline `VendorAssessmentService.sync_staleness` direct
call (Interconnection Phase 1, Step 3). The publisher now only DETECTS the overdue
assessment and emits; this listener creates the identical Risk register entry,
ControlMonitoringAlert, and `vendor_assessment.risk_linked` audit log it did
before, under the flush-only + SAVEPOINT-isolated bus contract.
"""
from sqlalchemy import select

from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.vendor import Vendor
from app.models.vendor_assessment import VendorAssessment
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService


class VendorStalenessListener:
    def handle(self, payload: EventPayload) -> None:
        if payload.event_type != EventType.VENDOR_ASSESSMENT_STALE:
            return
        db = payload.db
        org_id = payload.org_id  # strict tenant scope: trust only the event's org

        assessment = db.execute(
            select(VendorAssessment).where(
                VendorAssessment.id == payload.entity_id,
                VendorAssessment.organization_id == org_id,
            )
        ).scalar_one_or_none()
        # Idempotent per assessment (guarded by VendorAssessment.risk_id).
        if assessment is None or assessment.risk_id is not None:
            return
        vendor = db.execute(
            select(Vendor).where(Vendor.id == assessment.vendor_id, Vendor.organization_id == org_id)
        ).scalar_one_or_none()
        if vendor is None:
            return

        actor_user_id = payload.triggered_by_user_id
        description = (
            f"Vendor assessment '{assessment.title}' for vendor '{vendor.name}' is overdue: "
            f"due date {assessment.due_date.isoformat()} has passed and the assessment is still "
            f"'{assessment.status}'. An overdue vendor assessment means the vendor's risk posture "
            "has not been re-verified on schedule."
        )

        created_by = actor_user_id or assessment.created_by_user_id
        risk = RiskService(db).create_risk_from_service(
            organization_id=org_id,
            title=f"Vendor assessment overdue: {vendor.name}",
            description=description,
            category="third_party",
            likelihood=3,
            impact=3,
            treatment_strategy="mitigate",
            risk_context_external=(
                "Vendor risk assessment past its due date and not completed; vendor risk "
                "posture has not been re-verified on the required cadence."
            ),
            metadata_json={
                "source": "vendor_assessment",
                "vendor_id": str(vendor.id),
                "vendor_assessment_id": str(assessment.id),
                "reason": "assessment_overdue",
            },
            created_by_user_id=created_by,
            audit_source="vendor_assessment",
        )
        assessment.risk_id = risk.id

        alert = ControlMonitoringAlert(
            organization_id=org_id,
            alert_type="vendor_assessment_overdue",
            severity="medium",
            status="open",
            title=f"Vendor assessment overdue: {vendor.name}",
            description=description,
            alert_context_json={
                "vendor_id": str(vendor.id),
                "vendor_assessment_id": str(assessment.id),
                "due_date": assessment.due_date.isoformat(),
                "risk_id": str(risk.id),
                "event": "vendor_assessment_overdue",
            },
        )
        db.add(alert)
        db.flush()

        AuditService(db).write_audit_log(
            action="vendor_assessment.risk_linked",
            entity_type="vendor_assessment",
            entity_id=assessment.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "risk_id": str(risk.id),
                "alert_id": str(alert.id),
                "reason": "assessment_overdue",
            },
            metadata_json={"source": "vendor_assessment"},
        )

    def register(self, bus: EventBus) -> None:
        bus.subscribe(EventType.VENDOR_ASSESSMENT_STALE, self.handle)
