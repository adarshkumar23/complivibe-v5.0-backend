import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, ClassVar

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class EventType:
    CONTROL_STATUS_CHANGED = "control.status_changed"
    EVIDENCE_STATUS_CHANGED = "evidence.status_changed"
    EVIDENCE_EXPIRED = "evidence.expired"
    EVIDENCE_UPLOADED = "evidence.uploaded"
    VENDOR_SCORE_UPDATED = "vendor_risk.score_updated"
    RISK_SCORE_UPDATED = "risk.score_updated"
    # Phase 1 Step 3 -- cross-domain point-to-point connections migrated onto the bus.
    DORA_REGISTER_GAP_DETECTED = "dora.register_gap_detected"
    VENDOR_ASSESSMENT_STALE = "vendor.assessment_stale"
    GEOPOLITICAL_SIGNAL_CRITICAL = "geopolitical.signal_critical"
    OT_ICS_FINDING_INGESTED = "ot_ics.finding_ingested"


@dataclass(slots=True)
class EventPayload:
    org_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    event_type: str
    previous_value: Any
    new_value: Any
    triggered_by: str
    db: Session
    # Extended fields (all defaulted so existing call sites still construct
    # positionally/by-keyword unchanged). `db` is the live session shared with
    # the publisher's transaction and is NEVER persisted; everything below is.
    payload: dict = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    triggered_by_user_id: uuid.UUID | None = None
    correlation_id: uuid.UUID = field(default_factory=uuid.uuid4)


class EventBus:
    _instance: ClassVar["EventBus | None"] = None

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[EventPayload], None]]] = {}

    @classmethod
    def get_instance(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _listener_key(listener: Callable[[EventPayload], None]) -> tuple[str, str, str]:
        owner = listener.__self__.__class__.__qualname__ if hasattr(listener, "__self__") and listener.__self__ is not None else ""
        return (listener.__module__, owner, listener.__qualname__)

    def subscribe(self, event_type: str, listener: Callable[[EventPayload], None]) -> None:
        listeners = self._listeners.setdefault(event_type, [])
        incoming_key = self._listener_key(listener)
        if any(self._listener_key(existing) == incoming_key for existing in listeners):
            return
        listeners.append(listener)

    def _persist_event(self, event_type: str, payload: EventPayload) -> None:
        """Write the durable domain_events row for this publish, in the
        publisher's transaction, BEFORE any listener runs. Imported lazily to
        avoid a core->models import cycle at startup. If this flush fails, the
        exception propagates and the publish fails loudly -- events are never
        silently dropped.
        """
        from app.models.domain_event import DomainEvent

        event = DomainEvent(
            organization_id=payload.org_id,
            event_type=event_type,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            payload_json=dict(payload.payload) if payload.payload else {},
            previous_value=payload.previous_value,
            new_value=payload.new_value,
            occurred_at=payload.occurred_at,
            triggered_by=payload.triggered_by,
            triggered_by_user_id=payload.triggered_by_user_id,
            correlation_id=payload.correlation_id,
        )
        payload.db.add(event)
        payload.db.flush()

    def emit(self, event_type: str, payload: EventPayload) -> None:
        # Persist first (fails loudly on write error), then dispatch.
        self._persist_event(event_type, payload)

        for listener in self._listeners.get(event_type, []):
            try:
                # SAVEPOINT-per-handler isolation: a handler that raises --
                # including a DB error such as IntegrityError, which would
                # otherwise leave the shared Session in a pending-rollback
                # state -- rolls back ONLY its own writes. The session stays
                # usable so every sibling listener still runs, and the
                # publisher's own transaction is untouched. Commit ownership
                # sits with the caller (endpoint/scheduler), not the listener.
                with payload.db.begin_nested():
                    listener(payload)
            except Exception:
                logger.exception(
                    "Event listener failed for event_type=%s organization_id=%s entity=%s:%s",
                    event_type,
                    payload.org_id,
                    payload.entity_type,
                    payload.entity_id,
                )

    def clear_listeners(self) -> None:
        self._listeners.clear()
