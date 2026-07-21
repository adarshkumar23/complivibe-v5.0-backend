AI_GOVERNANCE_CONTRACTS = {
    "pillar": "Pillar 2 — AI Governance",
    "version": "1.0",
    "groups": [
        {
            "name": "ai_systems",
            "description": "AI system inventory and lifecycle management",
            "endpoints": [
                "POST /api/v1/ai-governance/systems",
                "GET  /api/v1/ai-governance/systems",
                "GET  /api/v1/ai-governance/systems/{id}",
                "POST /api/v1/ai-governance/systems/{id}/status",
                "POST /api/v1/ai-governance/systems/{id}/classify/submit",
                "POST /api/v1/ai-governance/systems/{id}/eu-act-classification",
            ],
            "protected_fields": ["organization_id", "created_by"],
            "invariants": [
                "tenant_scoped",
                "soft_delete",
                "audit_logged",
                "ai_governance_event_logged",
                "no_autonomous_compliance_decisions",
            ],
        },
        {
            "name": "ai_governance_reviews",
            "description": "Review workflow with four-eyes rule",
            "invariants": ["four_eyes_enforced", "tenant_scoped", "audit_logged"],
        },
        {
            "name": "ai_risk_assessments",
            "description": "Structured risk assessment with bias metrics",
            "invariants": [
                "bias_metrics_explicit_submission_only",
                "never_auto_called_on_production_data",
                "tenant_scoped",
                "audit_logged",
            ],
        },
        {
            "name": "model_cards",
            "description": "Model documentation with one-active-published invariant",
            "invariants": [
                "one_published_per_system",
                "sha256_content_hash",
                "version_history_preserved",
                "tenant_scoped",
            ],
        },
        {
            "name": "aibom",
            "description": "AI Bill of Materials with diff engine",
            "invariants": ["append_only_versions", "tenant_scoped", "audit_logged"],
        },
        {
            "name": "guardrails",
            "description": "Policy guardrail evaluation engine",
            "invariants": [
                "evaluation_only_no_execution",
                "ai_guardrail_events_append_only",
                "builtin_python_engine_no_opa_in_core",
                "tenant_scoped",
            ],
        },
        {
            "name": "approval_envelopes",
            "description": "Multi-approver deployment gate",
            "invariants": [
                "high_risk_minimum_2_approvers",
                "single_reject_blocks",
                "auto_status_transition_on_full_approval",
                "tenant_scoped",
            ],
        },
        {
            "name": "monitoring_configs",
            "description": (
                "AI monitoring: threshold configuration, inbound readings, and per-tier "
                "breach decisions"
            ),
            "invariants": [
                # CORRECTED. This previously read
                # "mode_b_inbound_only_no_computation_in_core", which was not true of
                # this codebase and had not been true for some time. Core DOES compute
                # here: AIMonitoringService._statistical_output_drift runs an Evidently
                # -backed distribution test over core's own stored reading history
                # (app/satellites/llm_observability/drift_adapters.py), and the
                # llm_observability feature computes hallucination, RAG retrieval
                # quality, token cost and Langfuse trace metrics in-process using
                # evidently, nannyml, aif360, fairlearn, deepeval, giskard and langfuse
                # -- all of which are pinned runtime dependencies of core, not optional
                # extras. An invariant that the code contradicts is worse than no
                # invariant, because it is quoted in reviews as though it held.
                "external_readings_are_values_not_verdicts",
                "core_computes_llm_observability_metrics_in_process",
                "core_decides_breaches_and_records_them_per_tier",
                "separate_api_key_auth_for_inbound",
                "governance_alert_on_threshold_breach",
                "breach_decisions_are_audited",
                "tenant_scoped",
            ],
            "boundary_note": (
                "The patent-P4 'satellite computes, core decides' boundary applies "
                "specifically to the EXTERNAL customer-monitoring path that P4 owns: "
                "metrics computed inside a customer's own environment, pushed to core "
                "as scalar values, where core alone compares them against the "
                "thresholds it stores and alone decides whether a breach occurred. On "
                "that path core must never accept a verdict -- is_breach, severity, "
                "alert_level and similar are refused at ingest. "
                "It does NOT apply to app/satellites/llm_observability, which is core's "
                "own first-party feature, computed in-process by deliberate design, "
                "with its own REST surface, permissions (llm_observability:read/write) "
                "and llm_observability_events table. Both statements are true at once: "
                "core does not accept someone else's verdict, and core does compute "
                "some metrics itself."
            ),
        },
        {
            "name": "risk_signals",
            "description": "Auto-generated signals with 7-day dedup",
            "invariants": [
                "7_day_deduplication_window",
                "spacy_severity_classification",
                "hooks_in_status_change_and_aibom",
                "tenant_scoped",
            ],
        },
    ],
    "patent_protected_features": [
        {
            "feature": "OPA Rego guardrail evaluation + Nobulex receipts",
            "status": "deferred to complivibe-patent-p3-agentic-enforcement",
            "core_equivalent": "BuiltInPolicyEngine",
        },
        {
            "feature": "In-environment drift/bias computation agent",
            "status": "deferred to complivibe-patent-p4-ai-monitoring",
            "core_equivalent": "Mode B inbound readings",
            "note": (
                "Deferred means the AGENT that runs inside a customer's environment "
                "lives in the satellite, not that core computes nothing. Core computes "
                "LLM-observability metrics itself (see the monitoring_configs "
                "boundary_note) and runs a distribution-drift test over its own stored "
                "reading history. What core defers is collecting from a customer's raw "
                "data, which never enters core at all."
            ),
        },
    ],
}
