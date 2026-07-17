from app.core.event_bus import EventBus


def register_event_listeners() -> None:
    bus = EventBus.get_instance()

    from app.compliance.services.risk_recalculation_listener import RiskRecalculationListener
    from app.compliance.services.entity_score_invalidation_listener import EntityScoreInvalidationListener

    RiskRecalculationListener().register(bus)
    EntityScoreInvalidationListener().register(bus)

    # Phase 1 Step 3 -- cross-domain point-to-point connections migrated onto the bus.
    from app.compliance.services.dora_risk_register_listener import DORARiskRegisterListener
    from app.compliance.services.vendor_staleness_listener import VendorStalenessListener
    from app.compliance.services.geopolitical_vendor_risk_listener import GeopoliticalVendorRiskListener
    from app.compliance.services.ot_ics_risk_register_listener import OtIcsRiskRegisterListener

    DORARiskRegisterListener().register(bus)
    VendorStalenessListener().register(bus)
    GeopoliticalVendorRiskListener().register(bus)
    OtIcsRiskRegisterListener().register(bus)

    # Phase 3 -- compound-exposure recommendation engine. Flags touched nodes for
    # a later (out-of-transaction) compound re-check; does no traversal/AI itself.
    from app.compliance.services.compound_pattern_candidate_listener import CompoundPatternCandidateListener

    CompoundPatternCandidateListener().register(bus)

    # Evidence-vault AI-assist -- flags a newly uploaded evidence file for async
    # assessment (extraction + AI happen in the drain, never in this listener).
    from app.compliance.services.evidence_assessment_candidate_listener import EvidenceAssessmentCandidateListener

    EvidenceAssessmentCandidateListener().register(bus)
