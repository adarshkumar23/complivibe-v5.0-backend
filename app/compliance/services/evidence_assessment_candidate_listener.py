"""Event-bus hook that FLAGS a newly-uploaded evidence item for AI assessment.

The lightest possible listener (Phase 1 flush-only / SAVEPOINT-isolated contract):
it writes one ``evidence_ai_assessment_candidates`` row via the publisher's
session and returns. It does NO text extraction and NO AI call -- a DB
transaction is never held across an external call here. The heavy work
(extraction + Groq/Azure assessment) happens later in the APScheduler drain, in
its own committed session.

Subscribes to EVIDENCE_UPLOADED only -- fired by the R2 file-upload endpoint
(POST /evidence/{id}/file). The metadata-only create path does not upload a file
and does not emit EVIDENCE_UPLOADED, so it is (correctly) not assessed.
"""

from __future__ import annotations

from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.evidence_ai_assessment import EvidenceAiAssessmentCandidate


class EvidenceAssessmentCandidateListener:
    def handle(self, payload: EventPayload) -> None:
        # Flush-only: mark the uploaded evidence item as an assessment candidate;
        # do not extract or call the AI here. The publisher owns the commit.
        candidate = EvidenceAiAssessmentCandidate(
            organization_id=payload.org_id,
            evidence_item_id=payload.entity_id,
            event_type=payload.event_type,
        )
        payload.db.add(candidate)
        payload.db.flush()

    def register(self, bus: EventBus) -> None:
        bus.subscribe(EventType.EVIDENCE_UPLOADED, self.handle)
