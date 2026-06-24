import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, ClassVar

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class EventType:
    CONTROL_STATUS_CHANGED = "control.status_changed"
    EVIDENCE_STATUS_CHANGED = "evidence.status_changed"
    EVIDENCE_EXPIRED = "evidence.expired"
    VENDOR_SCORE_UPDATED = "vendor_risk.score_updated"
    RISK_SCORE_UPDATED = "risk.score_updated"


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

    def emit(self, event_type: str, payload: EventPayload) -> None:
        listeners = self._listeners.get(event_type, [])
        for listener in listeners:
            try:
                listener(payload)
            except Exception:
                logger.exception("Event listener failed for event_type=%s", event_type)

    def clear_listeners(self) -> None:
        self._listeners.clear()
