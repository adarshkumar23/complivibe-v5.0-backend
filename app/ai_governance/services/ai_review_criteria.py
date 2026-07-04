INITIAL_APPROVAL_CRITERIA = {
    "purpose_documented": "Is the AI system's purpose clearly documented and approved?",
    "data_handling_reviewed": "Has the data handling and privacy impact been reviewed?",
    "bias_risk_assessed": "Has the potential for algorithmic bias been assessed?",
    "security_reviewed": "Has a security review been completed for this AI system?",
    "human_oversight_defined": "Is human oversight defined for all high-stakes decisions?",
    "testing_completed": "Has end-to-end testing been completed in non-production?",
    "rollback_plan": "Is a rollback plan documented?",
    "data_minimization": "Does the system process only the minimum necessary data?",
    "third_party_terms": "If using a third-party model, have contractual AI terms been reviewed?",
    "affected_population_notified": "If required, has the affected population been notified?",
    "compliance_obligations_mapped": "Have applicable compliance obligations been identified?",
    "owner_designated": "Is a named owner responsible for this AI system post-deployment?",
}

PERIODIC_CRITERIA = {
    "drift_reviewed": "Have model drift metrics been reviewed since last assessment?",
    "incidents_reviewed": "Have any AI-related incidents occurred and been addressed?",
    "scope_unchanged": "Is the system still operating within its approved scope?",
    "data_sources_unchanged": "Have the training/input data sources changed?",
    "access_controls_current": "Are access controls for this system still current?",
    "obligations_current": "Are all mapped compliance obligations still current?",
}


def criteria_for_review_type(review_type: str) -> dict[str, str]:
    if review_type == "periodic_review":
        return PERIODIC_CRITERIA
    if review_type in {"initial_review", "change_review", "pre_production_review"}:
        return INITIAL_APPROVAL_CRITERIA
    return {}
