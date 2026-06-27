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
            "description": "AI monitoring inbound reading endpoint",
            "invariants": [
                "mode_b_inbound_only_no_computation_in_core",
                "separate_api_key_auth_for_inbound",
                "governance_alert_on_threshold_breach",
                "tenant_scoped",
            ],
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
        },
    ],
}
