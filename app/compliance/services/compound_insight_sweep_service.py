"""Scheduler-driven drivers for the compound-insight engine.

Two entry points, both designed to run in an APScheduler job's OWN session
(the pbc_scheduler wrapper commits): a reactive drain of event-flagged candidate
nodes (~5 min) and a nightly full sweep + auto-resolve. Traversal + AI happen
here, never in the event-bus listener.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.compound_insight_detector import CompoundInsightDetector
from app.models.compound_insight import CompoundInsightCandidate
from app.models.organization import Organization

logger = logging.getLogger(__name__)

_DRAIN_BATCH = 200


def run_compound_insight_candidate_drain(db: Session) -> dict:
    """Process event-flagged candidate nodes; mark them processed. Flush-only."""
    detector = CompoundInsightDetector(db)
    candidates = db.execute(
        select(CompoundInsightCandidate)
        .where(CompoundInsightCandidate.processed_at.is_(None))
        .order_by(CompoundInsightCandidate.flagged_at.asc())
        .limit(_DRAIN_BATCH)
    ).scalars().all()

    now = detector.utcnow()
    created = 0
    seen: set[tuple[uuid.UUID, str, uuid.UUID]] = set()
    for candidate in candidates:
        node_key = (candidate.organization_id, candidate.entity_type, candidate.entity_id)
        if node_key not in seen:
            seen.add(node_key)
            try:
                created += detector.run_for_candidate(
                    candidate.organization_id, candidate.entity_type, candidate.entity_id
                )
            except Exception:  # noqa: BLE001
                logger.exception("Compound candidate detection failed for %s", node_key)
        candidate.processed_at = now
    db.flush()
    return {"records_processed": len(candidates), "created": created}


def run_compound_insight_full_sweep(db: Session) -> dict:
    """Full sweep across all orgs: detect all patterns + auto-resolve. Flush-only."""
    detector = CompoundInsightDetector(db)
    org_ids = [r[0] for r in db.execute(select(Organization.id)).all()]
    created = 0
    resolved = 0
    for org_id in org_ids:
        try:
            result = detector.sweep_org(org_id)
            created += result["created"]
            resolved += result["auto_resolved"]
        except Exception:  # noqa: BLE001
            logger.exception("Compound insight sweep failed for org %s", org_id)
    return {"records_processed": created + resolved, "created": created, "auto_resolved": resolved}
