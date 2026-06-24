from app.core.event_bus import EventBus


def register_event_listeners() -> None:
    bus = EventBus.get_instance()

    from app.compliance.services.risk_recalculation_listener import RiskRecalculationListener
    from app.compliance.services.entity_score_invalidation_listener import EntityScoreInvalidationListener

    RiskRecalculationListener().register(bus)
    EntityScoreInvalidationListener().register(bus)
