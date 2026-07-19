"""Hybrid-trigger change-event outbox writer (patent P2).

Ported from P2 core-side-patch/change_event_outbox.py; UUID-native ai_system_id.
When a watched AI-system field changes (or a manual sync fires), a row is
written; the satellite's export endpoints filter changed_since against it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ai_governance.services.governance_graph.constants import (
    MANUAL_TRIGGER_REASON,
    WATCHED_AI_SYSTEM_FIELDS,
)
from app.models.governance_graph_change_event import GovernanceGraphChangeEvent


def _write_change_event(
    session: Session, org_id: uuid.UUID, ai_system_id: uuid.UUID, changed_field: str
) -> GovernanceGraphChangeEvent:
    event = GovernanceGraphChangeEvent(
        organization_id=org_id,
        ai_system_id=ai_system_id,
        changed_field=changed_field,
        changed_at=datetime.now(UTC),
        consumed_at=None,
    )
    session.add(event)
    session.flush()
    return event


def emit_change_event(
    session: Session, org_id: uuid.UUID, ai_system_id: uuid.UUID, changed_field: str
) -> GovernanceGraphChangeEvent:
    """Emit a change event for a WATCHED field change. Raises ValueError for an
    unwatched field (guards accidental firehose)."""
    if changed_field not in WATCHED_AI_SYSTEM_FIELDS:
        raise ValueError(
            f"{changed_field!r} is not a watched ai_system field; allowed: {sorted(WATCHED_AI_SYSTEM_FIELDS)}"
        )
    return _write_change_event(session, org_id, ai_system_id, changed_field)


def emit_manual_change_event(
    session: Session, org_id: uuid.UUID, ai_system_id: uuid.UUID, reason: str = MANUAL_TRIGGER_REASON
) -> GovernanceGraphChangeEvent:
    """Emit a manual-sync change event (not gated by the watched-field allowlist)."""
    return _write_change_event(session, org_id, ai_system_id, reason)
