"""Core-side persistence for patent-P4 monitoring decisions.

This is the half of the compliance event bridge that RECORDS what core decided. The
half that DISPATCHES a governance workflow (the nine repository protocols, the
create_issue / update_risk_score / require_review implementations) is deliberately not
here yet -- it is a separate change with its own tests.

The split matters for correctness, not just sequencing. A breach event is written and
audited BEFORE any workflow runs, so a dispatch that fails or is not yet implemented
cannot lose the record that core determined a breach occurred. `workflow_reference` is
filled in afterwards, which is exactly why it is nullable.

What is enforced here
---------------------
* Every breach decision writes an audit entry through the existing, unchanged
  AuditService.write_audit_log signature. There is no such thing as an unaudited
  breach decision: the audit write is in the same flush as the row.
* `suspend_system` is refused outright rather than silently no-oped -- see
  DISABLED_WORKFLOW_VALUES for why an unimplemented halt-the-system workflow is the
  most dangerous possible thing to accept quietly.
* Collected readings carry a valid `reading_source`, validated against core's existing
  ALLOWED_READING_SOURCES rather than a second copy of that vocabulary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.validation import validate_choice
from app.models.ai_monitoring_breach_event import AIMonitoringBreachEvent
from app.models.ai_monitoring_config import (
    DISABLED_WORKFLOW_VALUES,
    SELECTABLE_WORKFLOW_VALUES,
    THRESHOLD_OPERATORS,
    AIMonitoringConfig,
)
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.services.audit_service import AuditService

#: Mode A/C collection is machine ingest, so it reports as 'api_report' -- the same
#: value receive_inbound_reading already uses. Named rather than inlined so the choice
#: is visible when core's reading_source vocabulary next changes.
COLLECTED_READING_SOURCE = "api_report"

COLLECTION_MODES = ("a", "b", "c")


class ComplianceEventBridge:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def record_collected_reading(
        self,
        org_id: uuid.UUID,
        *,
        value: Decimal,
        collection_mode: str,
        config_id: uuid.UUID | None = None,
        metric_type: str | None = None,
        sample_size: int | None = None,
        computed_by: str | None = None,
        reported_at: datetime | None = None,
        source_tool: str | None = None,
        reading_source: str = COLLECTED_READING_SOURCE,
    ) -> AIMonitoringReading:
        """Persist a measurement collected outside core.

        `reading_source` is validated against core's own ALLOWED_READING_SOURCES rather
        than trusted. The column is NOT NULL with a CHECK constraint, so an invalid or
        missing value is a 500 at insert time; validating here turns that into a 422
        naming the field. Imported lazily to avoid a circular import with
        AIMonitoringService, which imports this module's siblings.

        `within_threshold` is left NULL: this path records what was measured. Whether it
        breached is a decision, and decisions are recorded by record_breach_decision as
        one row per tier.
        """
        from app.ai_governance.services.ai_monitoring_service import ALLOWED_READING_SOURCES

        reading_source = validate_choice(reading_source, ALLOWED_READING_SOURCES, "reading_source")
        collection_mode = validate_choice(collection_mode, set(COLLECTION_MODES), "collection_mode")

        row = AIMonitoringReading(
            organization_id=org_id,
            config_id=config_id,
            value=value,
            reading_source=reading_source,
            source_tool=source_tool,
            within_threshold=None,
            created_at=self.utcnow(),
            collection_mode=collection_mode,
            metric_type=metric_type,
            sample_size=sample_size,
            computed_by=computed_by,
            reported_at=reported_at,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def record_breach_decision(
        self,
        org_id: uuid.UUID,
        *,
        reading: AIMonitoringReading,
        config: AIMonitoringConfig,
        observed_value: Decimal,
        actor_user_id: uuid.UUID | None = None,
        decided_by: str = "core.compliance_event_bridge",
    ) -> AIMonitoringBreachEvent:
        """Record that core decided this reading breached this config's tier.

        Writes the decision and its audit entry together. The audit entry is not
        optional and not deferred: a breach decision that left no trail would defeat the
        point of recording it at all.
        """
        workflow = config.workflow_to_trigger

        # Refuse rather than no-op. A customer who selected an unimplemented workflow
        # believes something happens on breach; silently doing nothing is the failure
        # mode this check exists to prevent. Schemas already exclude these values from
        # the selectable set, so reaching here means a row predates that or was written
        # directly -- either way it must be loud.
        if workflow in DISABLED_WORKFLOW_VALUES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"workflow_to_trigger '{workflow}' is defined but not implemented, so it "
                    "cannot be dispatched. It is excluded from the selectable set; a config "
                    "holding it must be repointed at an implemented workflow "
                    f"({', '.join(SELECTABLE_WORKFLOW_VALUES)}) before this breach can be "
                    "actioned. Refusing rather than silently taking no action."
                ),
            )

        operator = validate_choice(config.threshold_operator, set(THRESHOLD_OPERATORS), "threshold_operator")

        event = AIMonitoringBreachEvent(
            organization_id=org_id,
            reading_id=reading.id,
            config_id=config.id,
            ai_system_id=config.ai_system_id,
            metric_type=config.metric_type,
            tier=config.tier,
            escalation_order=config.escalation_order,
            observed_value=observed_value,
            threshold_value=config.threshold_value,
            threshold_operator=operator,
            obligation_id=config.obligation_id,
            workflow_triggered=workflow,
            workflow_reference=None,
            decided_at=self.utcnow(),
            decided_by=decided_by,
        )
        self.db.add(event)
        self.db.flush()

        # Unchanged AuditService signature -- this is a caller, not a reason to alter it.
        # actor_user_id is None when core itself decided, which is the honest record: no
        # human made this call. after_json carries both operands so the decision can be
        # re-derived from the trail alone, without joining back to a config that may
        # since have been edited.
        AuditService(self.db).write_audit_log(
            action="ai_monitoring.breach_decided",
            entity_type="ai_monitoring_breach_event",
            entity_id=event.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json={
                "reading_id": str(reading.id),
                "config_id": str(config.id),
                "ai_system_id": str(config.ai_system_id),
                "metric_type": config.metric_type,
                "tier": config.tier,
                "escalation_order": config.escalation_order,
                "observed_value": str(observed_value),
                "threshold_value": str(config.threshold_value),
                "threshold_operator": operator,
                "obligation_id": str(config.obligation_id) if config.obligation_id else None,
                "workflow_triggered": workflow,
            },
            metadata_json={"source": "compliance_event_bridge", "decided_by": decided_by},
        )
        return event

    def attach_workflow_reference(
        self, event: AIMonitoringBreachEvent, reference: str, *, org_id: uuid.UUID
    ) -> AIMonitoringBreachEvent:
        """Record what the dispatched workflow produced, once it has produced it.

        Separate from record_breach_decision so a dispatch failure cannot roll back the
        decision itself. Audited as its own action for the same reason: the trail should
        show the decision and its follow-through as two facts, because they can and do
        occur apart.
        """
        before = event.workflow_reference
        event.workflow_reference = reference
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ai_monitoring.breach_workflow_dispatched",
            entity_type="ai_monitoring_breach_event",
            entity_id=event.id,
            organization_id=org_id,
            actor_user_id=None,
            before_json={"workflow_reference": before},
            after_json={"workflow_reference": reference, "workflow_triggered": event.workflow_triggered},
            metadata_json={"source": "compliance_event_bridge"},
        )
        return event
