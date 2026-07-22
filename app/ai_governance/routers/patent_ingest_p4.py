"""Inbound push from the patent-P4 AI-monitoring satellite.

Built on patent_ingest_p2 as the template: same bearer scoped-key auth, same
organisation-derived-from-the-key rule, same rate limiter, same commit-in-the-router
shape. The only deliberate difference is the scope -- 'p4_ingest' rather than P2's
'ingest', so a key leaked from one satellite cannot authenticate the other.

THE BOUNDARY THIS ROUTE ENFORCES
================================
The satellite computes metrics inside the customer's environment and pushes SCALARS.
Core alone compares them against the thresholds it stores and alone decides whether a
breach occurred. Two things follow, and both are enforced here rather than assumed:

* A verdict-shaped field (is_breach, severity, alert_level, within_threshold, ...) is
  REFUSED, not stripped. Stripping would let a satellite believe its verdict had been
  accepted and acted on.
* `reading_source` is never taken from the payload. It is core's own vocabulary, NOT
  NULL with a CHECK of ('manual', 'api_report'), and machine ingest is always
  'api_report'. Letting a caller set it would let them mislabel an automated push as a
  human entry.

Note this route does not, and cannot, weaken the same-named boundary for
llm_observability, which is core's own in-process computation -- see the boundary_note
in ai_contracts.py. The rule here is about not accepting someone else's verdict.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.schemas.monitoring import P4MonitoringPushResult, P4MonitoringReadingPush
from app.ai_governance.services.compliance_event_bridge import ComplianceEventBridge
from app.ai_governance.services.governance_graph.scope_deps import require_p4_ingest_scope
from app.ai_governance.services.governance_workflow_engine import GovernanceWorkflowEngine
from app.core.deps import get_db
from app.core.rate_limiter import rate_limiter
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_system import AISystem

router = APIRouter(prefix="/patent-ingest/p4", tags=["patent-ingest-p4"])


@router.post("/monitoring-reading", response_model=P4MonitoringPushResult, status_code=status.HTTP_202_ACCEPTED)
@rate_limiter.limiter.limit("120/minute")
def post_monitoring_reading(
    payload: P4MonitoringReadingPush,
    request: Request,
    db: Session = Depends(get_db),
    org_id: uuid.UUID = Depends(require_p4_ingest_scope()),
) -> P4MonitoringPushResult:
    """Accept one measurement, then evaluate every configured tier for it.

    202, not 201: the reading is stored and the tiers are evaluated, but whatever
    governance workflow that triggers is core's business and the satellite is not
    waiting on it. The response reports what core decided, so a satellite can log it,
    but it deliberately carries no verdict the satellite could act on.
    """
    # The organisation is derived from the key, never the payload -- but the referenced
    # ai_system_id is caller-supplied, so it must be validated to belong to THAT org. A key
    # referencing another org's system_id would otherwise persist a reading stamped with the
    # key's org yet pointing at a system that org does not own (an orphan measurement that no
    # config could ever evaluate). Reject rather than store it. Batch-5 finding.
    system_in_org = db.execute(
        select(AISystem.id).where(
            AISystem.id == payload.ai_system_id,
            AISystem.organization_id == org_id,
            AISystem.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if system_in_org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ai_system_id does not belong to this key's organization",
        )

    bridge = ComplianceEventBridge(db)
    reading = bridge.record_collected_reading(
        org_id,
        value=payload.value,
        collection_mode=payload.collection_mode,
        config_id=payload.config_id,
        metric_type=payload.metric_type,
        sample_size=payload.sample_size,
        computed_by=payload.computed_by,
        reported_at=payload.reported_at,
        source_tool=payload.source_tool,
        # Deliberately not from the payload -- see the module docstring.
    )

    # Every ACTIVE tier configured for this (system, metric). A reading for a metric
    # nobody has configured a threshold for is still stored: it is a measurement, and it
    # becomes evaluable the moment someone configures one.
    configs = list(
        db.execute(
            select(AIMonitoringConfig).where(
                AIMonitoringConfig.organization_id == org_id,
                AIMonitoringConfig.ai_system_id == payload.ai_system_id,
                AIMonitoringConfig.metric_type == payload.metric_type,
                AIMonitoringConfig.is_active.is_(True),
                AIMonitoringConfig.deleted_at.is_(None),
            )
        ).scalars().all()
    )

    events = GovernanceWorkflowEngine(db).dispatch_for_reading(
        org_id, reading=reading, configs=configs, observed_value=payload.value
    )
    db.commit()

    return P4MonitoringPushResult(
        reading_id=reading.id,
        organization_id=org_id,
        breach_events=len(events),
        tiers_dispatched=[event.tier for event in events],
    )
