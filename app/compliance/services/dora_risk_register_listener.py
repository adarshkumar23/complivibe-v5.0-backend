"""Subscriber for `dora.register_gap_detected`.

Migrated from the former inline `DORAService._sync_risk_register` direct call
(Interconnection Phase 1, Step 3). The publisher (DORAService) now only DETECTS
the Art. 28 register gap and emits; this listener performs the identical
downstream work it did before -- a Risk register entry, a ControlMonitoringAlert,
an Issue, and the `dora.ict_entry_risk_linked` audit log -- via the flush-only +
SAVEPOINT-isolated bus contract (the listener never commits; the publisher's
endpoint owns the commit).
"""
import uuid

from sqlalchemy import select

from app.compliance.services.dora_service import DORA_ASSESSMENT_OVERDUE_DAYS
from app.compliance.services.issue_service import IssueService
from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.dora_ict_register import DORAICTRegister
from app.models.issue import Issue
from app.schemas.issue import IssueCreate
from app.services.audit_service import AuditService
from app.services.risk_service import RiskService


class DORARiskRegisterListener:
    def handle(self, payload: EventPayload) -> None:
        if payload.event_type != EventType.DORA_REGISTER_GAP_DETECTED:
            return
        db = payload.db
        org_id = payload.org_id  # strict tenant scope: trust only the event's org

        row = db.execute(
            select(DORAICTRegister).where(
                DORAICTRegister.id == payload.entity_id,
                DORAICTRegister.organization_id == org_id,
            )
        ).scalar_one_or_none()
        # Idempotent per entry (guarded by DORAICTRegister.risk_id), identical to
        # the pre-migration guard in _sync_risk_register.
        if row is None or row.risk_id is not None:
            return

        reason = payload.payload.get("reason")
        actor_user_id = payload.triggered_by_user_id

        if reason == "missing_exit_strategy":
            description = (
                f"Critical ICT third-party '{row.counterparty_name}' (DORA {row.dora_article}) has no "
                "documented exit strategy. Art. 28 requires a documented exit strategy for critical/"
                "important function providers so the relationship can be unwound without disrupting "
                "operations."
            )
        else:
            description = (
                f"Critical ICT third-party '{row.counterparty_name}' (DORA {row.dora_article}) has not "
                f"been reassessed in over {DORA_ASSESSMENT_OVERDUE_DAYS} days "
                f"(last assessed {row.last_assessed_at.isoformat() if row.last_assessed_at else 'never'})."
            )

        created_by = actor_user_id or row.created_by
        risk = RiskService(db).create_risk_from_service(
            organization_id=org_id,
            title=f"DORA ICT register gap: {row.counterparty_name}",
            description=description,
            category="third_party",
            likelihood=4,
            impact=4,
            treatment_strategy="mitigate",
            risk_context_external=(
                "Regulation (EU) 2022/2554 (DORA) Article 28 - management of ICT third-party risk, "
                "critical/important function exit strategy and periodic reassessment requirements."
            ),
            metadata_json={
                "source": "dora_ict_register",
                "dora_ict_register_id": str(row.id),
                "reason": reason,
            },
            created_by_user_id=created_by,
            audit_source="dora_ict_register",
        )
        row.risk_id = risk.id

        alert = ControlMonitoringAlert(
            organization_id=org_id,
            alert_type="dora_ict_register_gap",
            severity="high" if reason == "missing_exit_strategy" else "medium",
            status="open",
            title=f"DORA ICT register gap: {row.counterparty_name}",
            description=description,
            alert_context_json={
                "dora_ict_register_id": str(row.id),
                "vendor_id": str(row.vendor_id) if row.vendor_id else None,
                "risk_id": str(risk.id),
                "reason": reason,
                "event": "dora_ict_register_gap",
            },
            assigned_to_user_id=row.owner_id,
        )
        db.add(alert)
        db.flush()

        existing_issue = db.execute(
            select(Issue).where(
                Issue.organization_id == org_id,
                Issue.source_type == "risk_assessment",
                Issue.source_id == row.id,
                Issue.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing_issue is None:
            IssueService(db).create_issue(
                org_id,
                IssueCreate(
                    title=f"DORA ICT register gap: {row.counterparty_name}",
                    description=f"{description}\n\nLinked risk ID: {risk.id}",
                    issue_type="vendor_failure",
                    severity="high" if reason == "missing_exit_strategy" else "medium",
                    source_type="risk_assessment",
                    source_id=row.id,
                    owner_id=row.owner_id,
                    assigned_to=row.owner_id,
                ),
                created_by=created_by,
            )
        db.flush()
        AuditService(db).write_audit_log(
            action="dora.ict_entry_risk_linked",
            entity_type="dora_ict_register",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={"risk_id": str(risk.id), "alert_id": str(alert.id), "reason": reason},
            metadata_json={"source": "dora_ict_register"},
        )

    def register(self, bus: EventBus) -> None:
        bus.subscribe(EventType.DORA_REGISTER_GAP_DETECTED, self.handle)
