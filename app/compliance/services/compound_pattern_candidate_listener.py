"""Event-bus hook that FLAGS a touched node for compound re-check.

This is intentionally the lightest possible listener: it writes one
`compound_insight_candidates` row via the publisher's session and returns. It
does NO graph traversal and NO AI call, so it fully honours the Phase 1
flush-only / SAVEPOINT-isolated listener contract -- a DB transaction is never
held across an external call here. The heavy work (traversal + Groq narrative)
happens later in the APScheduler drain job, in its own committed session.
"""

from __future__ import annotations

from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.compound_insight import CompoundInsightCandidate

# Event types whose subject node can participate in patterns A/B/C.
_SUBSCRIBED = (
    EventType.CONTROL_STATUS_CHANGED,
    EventType.VENDOR_ASSESSMENT_STALE,
    EventType.RISK_SCORE_UPDATED,
    EventType.EVIDENCE_EXPIRED,
    EventType.EVIDENCE_STATUS_CHANGED,
)


class CompoundPatternCandidateListener:
    def handle(self, payload: EventPayload) -> None:
        # Flush-only: mark the node as a detection candidate; do not traverse or
        # call the AI here. The publisher owns the commit.
        candidate = CompoundInsightCandidate(
            organization_id=payload.org_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            event_type=payload.event_type,
        )
        payload.db.add(candidate)
        payload.db.flush()

    def register(self, bus: EventBus) -> None:
        for event_type in _SUBSCRIBED:
            bus.subscribe(event_type, self.handle)
