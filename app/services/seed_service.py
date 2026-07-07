import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate
from app.models.framework import Framework
from app.models.framework_section import FrameworkSection
from app.models.framework_version import FrameworkVersion
from app.models.obligation import Obligation
from app.models.obligation_applicability_question import ObligationApplicabilityQuestion
from app.models.obligation_applicability_rule import ObligationApplicabilityRule
from app.models.permission import Permission
from app.models.policy_template import PolicyTemplate
from app.models.issue_sla_policy import IssueSLAPolicy
from app.models.questionnaire_scoring_rule import QuestionnaireScoringRule
from app.models.questionnaire_template import QuestionnaireTemplate
from app.models.questionnaire_template_question import QuestionnaireTemplateQuestion
from app.models.questionnaire_template_section import QuestionnaireTemplateSection
from app.models.eu_act_annex_mapping import EUActAnnexMapping
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.data_access_anomaly_rule import DataAccessAnomalyRule
from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.services.framework_seed_data_stream_a2 import (
    CIS_CONTROLS_V8_QUESTIONS,
    CIS_CONTROLS_V8_SAFEGUARDS,
    CIS_CONTROLS_V8_SECTIONS,
    ISO_27701_GDPR_MAPPINGS,
    ISO_27701_OBLIGATIONS,
    ISO_27701_QUESTIONS,
    ISO_27701_SECTIONS,
)
from app.services.framework_seed_data_stream_a4 import (
    HIPAA_NIST_MAPPINGS,
    HIPAA_OBLIGATIONS,
    HIPAA_QUESTIONS,
    HIPAA_SECTIONS,
    NIST_800_53_LOW_CONTROLS,
    NIST_800_53_QUESTIONS,
    NIST_800_53_SECTIONS,
    nist_description,
    nist_evidence_hints,
)
from app.services.framework_seed_data_stream_a5 import (
    CCPA_OBLIGATIONS,
    CCPA_QUESTIONS,
    CCPA_SECTIONS,
    DPDP_GDPR_MAPPINGS,
    DPDP_OBLIGATIONS,
    DPDP_QUESTIONS,
    DPDP_SECTIONS,
)
from app.services.framework_seed_data_phase1 import (
    CSA_CCM_CONTROLS,
    CSA_CCM_ISO27001_MAPPINGS,
    CSA_CCM_SECTIONS,
    DPDP_2025_RULES_OBLIGATIONS,
    EU_CRA_ANNEX_IV_OBLIGATIONS,
    EU_CRA_ANNEX_IV_QUESTIONS,
    EU_CRA_ANNEX_IV_SECTIONS,
    NIST_800_53_REV4_HIGH_CONTROLS,
)
from app.services.applicability_service import ApplicabilityService
from app.services.framework_seed_data_stream_a6 import (
    ATLAS_NIST_AIRMF_MAPPINGS,
    ATLAS_OBLIGATIONS,
    ATLAS_QUESTIONS,
    ATLAS_SECTIONS,
    G7_EUAI_MAPPINGS,
    G7_OBLIGATIONS,
    G7_OECD_MAPPINGS,
    G7_QUESTIONS,
    G7_SECTIONS,
    IEEE_7000_OBLIGATIONS,
    IEEE_7000_QUESTIONS,
    IEEE_7000_SECTIONS,
    IEEE_EUAI_MAPPINGS,
    ISO_31000_OBLIGATIONS,
    ISO_31000_QUESTIONS,
    ISO_31000_SECTIONS,
    OECD_AI_OBLIGATIONS,
    OECD_AI_QUESTIONS,
    OECD_AI_SECTIONS,
    OECD_EUAI_MAPPINGS,
    SINGAPORE_OBLIGATIONS,
    SINGAPORE_QUESTIONS,
    SINGAPORE_SECTIONS,
    UNESCO_OBLIGATIONS,
    UNESCO_QUESTIONS,
    UNESCO_SECTIONS,
)
from app.services.framework_seed_data_stream_b_v1 import (
    INDIA_PACK_OBLIGATIONS,
    INDIA_PACK_QUESTIONS,
    INDIA_PACK_SECTION_METADATA,
    INDIA_PACK_SECTIONS,
)

PERMISSIONS: dict[str, str] = {
    "org:read": "Read organization details",
    "org:update": "Update organization details",
    "users:read": "Read users",
    "users:invite": "Invite users",
    "users:update_role": "Update user role",
    "frameworks:read": "Read frameworks",
    "frameworks:activate": "Activate frameworks",
    "controls:read": "Read controls",
    "controls:write": "Write controls",
    "exceptions:approve": "Approve or reject control exception requests",
    "technical_controls:manage": "Register technical agents and manage technical control rules",
    "technical_controls:view": "Read technical control test results and summaries",
    "identity_governance:read": "Read non-human identity inventory and orphan-scan results",
    "identity_governance:manage": "Create, update, delete, and flag non-human identities",
    "sod:read": "Read segregation-of-duties rules and findings",
    "sod:manage": "Create and manage segregation-of-duties rules, findings, and detections",
    "evidence:read": "Read evidence metadata",
    "evidence:write": "Write evidence metadata",
    "risks:read": "Read risks",
    "risks:write": "Write risks",
    "tasks:read": "Read tasks",
    "tasks:write": "Write tasks",
    "audit_logs:read": "Read audit logs",
    "dashboard:read": "Read dashboard",
    "email:read": "Read email templates and outbox",
    "email:write": "Create email templates and queue/cancel emails",
    "email:send": "Mark emails sent/failed for internal testing",
    "email:admin": "Administer organization email templates",
    "automation:read": "Read automation rules and execution history",
    "automation:write": "Create and manage automation rules",
    "automation:execute": "Execute automation scans and rules",
    "evidence_automation_rules:read": "Read evidence automation connector rules",
    "evidence_automation_rules:write": "Create and manage evidence automation connector rules",
    "evidence_automation_ingest:webhook": "Ingest evidence through webhook automation endpoints",
    "evidence_automation_ingest:email": "Ingest evidence through email automation endpoints",
    "evidence_automation_ingest:form": "Ingest evidence through form automation endpoints",
    "compliance_bot:configure_subscription": "Create and update compliance bot subscription settings",
    "compliance_bot:list_subscriptions": "List compliance bot subscriptions for the current user",
    "compliance_bot:slack_command": "Execute Slack compliance bot command handlers",
    "compliance_bot:teams_command": "Execute Teams compliance bot command handlers",
    "compliance_bot:run_digest": "Run proactive compliance bot daily digest dispatch",
    "compliance_bot:run_sla_alerts": "Run proactive compliance bot SLA alert dispatch",
    "compliance_bot:read_outbox": "Read compliance bot outbox messages",
    "issue_sync_connection:create": "Create issue synchronization connections for Jira and Linear",
    "issue_sync_connection:list": "List issue synchronization connections",
    "issue_sync_connection:update": "Update issue synchronization connection settings",
    "issue_sync_link:create": "Create and update issue synchronization links between internal and external records",
    "issue_sync_outbound:run": "Run outbound issue synchronization for status/comment propagation",
    "issue_sync_webhook:jira": "Ingest Jira webhook issue synchronization events",
    "issue_sync_webhook:linear": "Ingest Linear webhook issue synchronization events",
    "issue_sync_events:list": "Read issue synchronization event processing history",
    "issue_sync_comments:list": "Read synchronized issue comments",
    "recertification:read": "Read recertification policies and runs",
    "recertification:write": "Create and manage recertification policies",
    "recertification:execute": "Execute recertification and reassessment runs",
    "reports:read": "Read compliance reports",
    "reports:write": "Manage compliance reports",
    "reports:generate": "Generate compliance reports",
    "reports:xbrl_export": "Generate ESG XBRL exports for compliance reports",
    "carbon_accounting:read": "Read carbon accounting dashboards and summaries",
    "billing_usage_dashboard:read": "Read usage-based billing dashboard and projected month-end spend",
    "billing_usage_spend_cap:write": "Configure usage-based billing spend cap settings",
    "billing_usage_sync:execute": "Sync metered usage quantities to payment processor subscriptions",
    "connectors:read": "Read connector marketplace catalog and organization connector status",
    "connectors:write": "Create connector catalog entries and manage organization connector enablement",
    "legal_matters:read": "View legal matters, their linked risks/issues, and status",
    "legal_matters:write": "Create, update, link/unlink, and close legal matters",
    "ip_assets:read": "Read IP and model/dataset licensing registry records and settings",
    "ip_assets:manage": "Create, update, delete IP/licensing registry records and manage the expiring-soon window",
    "content_provenance:manage": "Verify and manage content provenance (C2PA manifest) records",
    "training_data_rights:manage": "Create and manage training dataset rights/provenance records and view rights-gap reports",
    "synthetic_data:manage": "Create, update, delete, and validate synthetic datasets, including governance-gap review",
    "geopolitical_risk:read": "Read geopolitical risk signals, vendor region exposures, and cross-referenced exposure summaries",
    "geopolitical_risk:manage": "Trigger geopolitical risk ingestion and manage vendor geopolitical exposure records",
    "ot_ics_assets:read": "Read OT/ICS convergence asset inventory and findings",
    "ot_ics_assets:manage": "Register OT/ICS agents and manage OT/ICS assets and findings",
    "ai_usage_policy:read": "Read AI-usage policy compliance checks, summary, and gaps",
    "ai_usage_policy:write": "Trigger AI-usage policy compliance runs",
    "training_analytics:read": "View training completion records and per-business-unit training analytics",
    "training_analytics:write": "Assign and mark completion for training completion records",
    "exports:read": "Read export jobs and export packages",
    "exports:write": "Create and manage export jobs",
    "exports:run": "Run export jobs",
    "exports:verify": "Verify export integrity",
    "retention:read": "Read retention governance data",
    "retention:write": "Manage retention policies and legal holds",
    "attestations:read": "Read export attestations",
    "attestations:write": "Create export attestations",
    "attestations:revoke": "Revoke export attestations",
    "attestations:manage": "Create and manage employee attestation campaigns and exemptions",
    "attestations:submit": "Submit employee policy attestations",
    "attestations:view": "Read employee attestation campaigns and records",
    "policy_exceptions:submit": "Submit and withdraw own policy exception requests",
    "policy_exceptions:manage": "Approve, reject, and manage all policy exception requests",
    "policy_exceptions:view": "Read policy exception requests and dashboards",
    "policy_risks:manage": "Create, update, and delete policy-to-risk mappings",
    "policy_risks:view": "Read policy-to-risk mappings and coverage summaries",
    "policy_issues:manage": "Create, update, and delete policy-to-issue links",
    "policy_issues:view": "Read policy-to-issue links and effectiveness summaries",
    "audit:read": "Read audit engagements and PBC evidence request lists",
    "audit:write": "Create and manage audit engagements and PBC evidence request lists",
    "governance_override:read": "Read governance override requests",
    "governance_override:create": "Create governance override requests",
    "governance_override:approve": "Approve or reject governance override requests",
    "governance_override:execute": "Execute approved governance override requests",
    "governance_override:cancel": "Cancel governance override requests",
    "governance_override_template:read": "Read governance override templates",
    "governance_override_template:write": "Create and manage governance override templates",
    "framework_content:review": "Review framework content packs and review history",
    "framework_content:promote": "Create and execute framework coverage promotions",
    "framework_review_capacity:read": "Read reviewer capacity policies, workload, and assignment suggestions",
    "framework_review_capacity:write": "Manage reviewer capacity policies",
    "ai_systems:read": "Read AI system inventory records",
    "ai_systems:write": "Create and update AI system inventory records",
    "ai_systems:admin": "Archive and administer AI system inventory records",
    "ai_bom:read": "Read AI bill-of-materials (AIBOM) records and diffs",
    "ai_bom:write": "Create and update AIBOM records and components",
    "model_registry:read": "Read model card registry records",
    "model_registry:write": "Create, update, and publish model card records",
    "compliance_policies:read": "Read compliance policies",
    "compliance_policies:write": "Create and update compliance policies",
    "compliance_policies:approve": "Approve compliance policies",
    "compliance:read": "Read compliance domain records",
    "compliance:write": "Create and update compliance domain records",
    "vendors:read": "Read vendor and third-party inventory",
    "vendors:write": "Create and update vendor inventory records",
    "vendors:admin": "Archive and administer vendor inventory records",
    "vendor_criticality:read": "Read vendor business-criticality profiles and scoring settings",
    "vendor_criticality:manage": "Manage vendor business-criticality profiles and scoring settings",
    "vendor_supply_chain:read": "Read vendor nth-party supply-chain graphs and propagated risk alerts",
    "vendor_supply_chain:manage": "Create and manage vendor nth-party supply-chain links",
    "vendor_concentration_risk:read": "Read vendor concentration risk detection and generated risk linkage",
    "vendor_concentration_risk:manage": "Recompute vendor concentration risk detection and create linked risk register entries",
    "vendor_remediation_portal:read": "Read vendor remediation portal tokens and access metadata",
    "vendor_remediation_portal:manage": "Create and revoke vendor remediation portal tokens",
    "vendor:read": "Read vendor questionnaire templates, responses, and scoring rules",
    "vendor:write": "Create and manage vendor questionnaire templates, responses, and scoring rules",
    "monitoring:read": "Read control monitoring definitions and results",
    "monitoring:write": "Create and manage control monitoring definitions and results",
    "compliance_deadlines:read": "Read compliance deadlines and calendar events",
    "compliance_deadlines:write": "Create and manage compliance deadlines and calendar events",
    "risk_appetite:read": "Read risk appetite thresholds and breach summaries",
    "risk_appetite:write": "Create and manage risk appetite thresholds",
    "risk_indicators:read": "Read key risk indicators",
    "risk_indicators:write": "Create and manage key risk indicators",
    "issues:read": "Read formal issue log records and dashboards",
    "issues:write": "Create and manage formal issue log records",
    "issues:admin": "Manage organization-level issue module settings",
    "escalations:read": "Read escalation policies and escalation events",
    "escalations:write": "Create and manage escalation policies",
    "ai_governance:read": "Read AI governance dashboard summary",
    "ai_governance:write": "Create and update AI governance reviews and classifications",
    "ai_governance:approve": "Approve or reject AI governance reviews and conditional approvals",
    "llm_observability:read": "Read LLM observability events: tracing, hallucination checks, cost readings, RAG evaluations",
    "llm_observability:write": "Record LLM observability events: tracing polls, hallucination checks, cost readings, RAG evaluations",
    "integrations:read": "Read MLOps integrations and sync logs",
    "integrations:write": "Create and manage MLOps integrations and sync operations",
    "data:read": "Read data observability assets and classification summaries",
    "data:write": "Create and manage data observability assets and classifications",
    "privacy:read": "Read privacy processing activities and Article 30 RoPA reports",
    "privacy:write": "Create and manage privacy processing activities and RoPA links",
    "privacy:approve": "Approve and reject privacy governance workflows such as DPIAs",
    "scheduler:admin": "Read scheduler jobs and execution run logs",
    "drafts:use": "Create, review, and apply AI-assisted drafting outputs",
    "webhooks:read": "Read outbound webhook endpoints and delivery history",
    "webhooks:write": "Create and manage outbound webhook endpoints and test emissions",
    "bcm:read": "Read business continuity processes and BIA assessments",
    "bcm:manage": "Create and update business continuity processes and BIA assessments",
    "crisis_management:read": "Read crisis management playbooks and activations",
    "crisis_management:manage": "Create playbooks and activate/resolve crisis events",
    "financial_risk:read": "Read quantitative risk assessment (Monte Carlo/FAIR) runs",
    "financial_risk:manage": "Run quantitative risk assessments (Monte Carlo/FAIR)",
    "resilience_testing:read": "Read DORA resilience test records and overdue-test status",
    "resilience_testing:manage": "Create and update DORA resilience test records",
    "whistleblower:investigate": "Investigate and respond to whistleblower hotline reports",
    "anti_bribery:read": "Read anti-bribery and corruption risk assessments for vendors/third parties",
    "anti_bribery:manage": "Create and compute anti-bribery and corruption risk assessments",
    "export_control:read": "Read export control classification and denied-party screening results",
    "export_control:manage": "Create and compute export control classification and denied-party screening",
    "search:read": "Search across risks, controls, vendors, issues, compliance policies, and obligations",
    "imports:create": "Create competitor migration import jobs",
    "imports:read": "Read competitor migration import job progress",
    "imports:preview": "Generate and review import dry-run previews",
    "imports:commit": "Commit import jobs and persist imported entities",
    "imports:parity_read": "Read import parity dashboard and switch-readiness metrics",
    "imports:gap_report": "Read imported-data coverage gap report by import job",
    "pricing:manage": "Refresh competitor pricing comparisons and publish new pricing snapshots",
    "certification_programs:read": "Read certification program catalog and progress views",
    "certification_programs:activate": "Activate certification programs and create linked task/evidence/deadline plans",
    "auditor_marketplace:read": "Read auditor marketplace engagements and filters",
    "auditor_marketplace:engage": "Create auditor marketplace engagements linked to audit portal access",
    "onboarding_baseline:start": "Start 24-hour baseline onboarding run with intake generation and evidence auto-collection",
    "onboarding_baseline:read": "Read 24-hour baseline onboarding run outputs and gap analysis",
    "command_palette:search": "Run command palette search across indexed entities and shortcuts",
    "command_palette:execute": "Execute command palette backend actions such as quick task creation",
    "compliance_timeline:read": "Read chronological compliance timeline events across key operational modules",
    "compliance_inbox:read": "Read a user's prioritized compliance inbox across attestations, evidence requests, approvals, and overdue work",
    "compliance_summary:generate": "Generate public tokenized one-page compliance summary links",
}

ROLE_PERMISSION_MAP: dict[str, set[str]] = {
    "owner": set(PERMISSIONS.keys()),
    "admin": set(PERMISSIONS.keys()),
    "compliance_manager": {
        "frameworks:read",
        "frameworks:activate",
        "controls:read",
        "controls:write",
        "evidence:read",
        "evidence:write",
        "risks:read",
        "risks:write",
        "tasks:read",
        "tasks:write",
        "certification_programs:read",
        "certification_programs:activate",
        "auditor_marketplace:read",
        "auditor_marketplace:engage",
        "dashboard:read",
        "org:read",
        "users:read",
        "email:read",
        "email:write",
        "email:send",
        "automation:read",
        "automation:write",
        "automation:execute",
        "evidence_automation_rules:read",
        "evidence_automation_rules:write",
        "evidence_automation_ingest:webhook",
        "evidence_automation_ingest:email",
        "evidence_automation_ingest:form",
        "compliance_bot:configure_subscription",
        "compliance_bot:list_subscriptions",
        "compliance_bot:slack_command",
        "compliance_bot:teams_command",
        "compliance_bot:run_digest",
        "compliance_bot:run_sla_alerts",
        "compliance_bot:read_outbox",
        "issue_sync_connection:create",
        "issue_sync_connection:list",
        "issue_sync_connection:update",
        "issue_sync_link:create",
        "issue_sync_outbound:run",
        "issue_sync_webhook:jira",
        "issue_sync_webhook:linear",
        "issue_sync_events:list",
        "issue_sync_comments:list",
        "recertification:read",
        "recertification:write",
        "recertification:execute",
        "reports:read",
        "reports:write",
        "reports:generate",
        "reports:xbrl_export",
        "carbon_accounting:read",
        "connectors:read",
        "connectors:write",
        "exports:read",
        "exports:write",
        "exports:run",
        "exports:verify",
        "retention:read",
        "retention:write",
        "attestations:read",
        "attestations:write",
        "attestations:revoke",
        "attestations:submit",
        "attestations:view",
        "policy_exceptions:manage",
        "policy_exceptions:submit",
        "policy_exceptions:view",
        "policy_risks:manage",
        "policy_risks:view",
        "policy_issues:manage",
        "policy_issues:view",
        "audit:read",
        "audit:write",
        "governance_override:read",
        "governance_override:create",
        "governance_override:approve",
        "governance_override:execute",
        "governance_override:cancel",
        "governance_override_template:read",
        "governance_override_template:write",
        "framework_content:review",
        "framework_content:promote",
        "framework_review_capacity:read",
        "framework_review_capacity:write",
        "ai_systems:read",
        "ai_systems:write",
        "ai_systems:admin",
        "ai_bom:read",
        "ai_bom:write",
        "model_registry:read",
        "model_registry:write",
        "compliance_policies:read",
        "compliance_policies:write",
        "compliance_policies:approve",
        "compliance:read",
        "compliance:write",
        "vendors:read",
        "vendors:write",
        "vendors:admin",
        "vendor_criticality:read",
        "vendor_criticality:manage",
        "vendor_supply_chain:read",
        "vendor_supply_chain:manage",
        "vendor_concentration_risk:read",
        "vendor_concentration_risk:manage",
        "vendor_remediation_portal:read",
        "vendor_remediation_portal:manage",
        "vendor:read",
        "vendor:write",
        "monitoring:read",
        "monitoring:write",
        "compliance_deadlines:read",
        "compliance_deadlines:write",
        "risk_appetite:read",
        "risk_indicators:read",
        "issues:read",
        "issues:write",
        "escalations:read",
        "escalations:write",
        "ai_governance:read",
        "ai_governance:write",
        "llm_observability:read",
        "llm_observability:write",
        "integrations:read",
        "integrations:write",
        "data:read",
        "data:write",
        "privacy:read",
        "privacy:write",
        "drafts:use",
        "webhooks:read",
        "webhooks:write",
        "technical_controls:manage",
        "technical_controls:view",
        "identity_governance:read",
        "identity_governance:manage",
        "sod:read",
        "sod:manage",
        "legal_matters:read",
        "legal_matters:write",
        "ip_assets:read",
        "ip_assets:manage",
        "content_provenance:manage",
        "training_data_rights:manage",
        "synthetic_data:manage",
        "geopolitical_risk:read",
        "geopolitical_risk:manage",
        "ot_ics_assets:read",
        "ot_ics_assets:manage",
        "ai_usage_policy:read",
        "ai_usage_policy:write",
        "training_analytics:read",
        "training_analytics:write",
        "bcm:read",
        "bcm:manage",
        "crisis_management:read",
        "crisis_management:manage",
        "financial_risk:read",
        "financial_risk:manage",
        "resilience_testing:read",
        "resilience_testing:manage",
        "whistleblower:investigate",
        "anti_bribery:read",
        "anti_bribery:manage",
        "export_control:read",
        "export_control:manage",
        "search:read",
        "onboarding_baseline:start",
        "onboarding_baseline:read",
        "command_palette:search",
        "command_palette:execute",
        "compliance_timeline:read",
        "compliance_inbox:read",
        "compliance_summary:generate",
    },
    "reviewer": {
        "frameworks:read",
        "controls:read",
        "evidence:read",
        "evidence:write",
        "risks:read",
        "tasks:read",
        "tasks:write",
        "dashboard:read",
        "email:read",
        "automation:read",
        "evidence_automation_rules:read",
        "compliance_bot:list_subscriptions",
        "compliance_bot:read_outbox",
        "issue_sync_connection:list",
        "issue_sync_events:list",
        "issue_sync_comments:list",
        "recertification:read",
        "recertification:execute",
        "reports:read",
        "reports:generate",
        "exports:read",
        "exports:run",
        "retention:read",
        "attestations:read",
        "attestations:write",
        "attestations:manage",
        "attestations:submit",
        "attestations:view",
        "policy_exceptions:submit",
        "policy_exceptions:view",
        "policy_risks:view",
        "policy_issues:view",
        "audit:read",
        "governance_override:read",
        "governance_override:approve",
        "governance_override_template:read",
        "framework_content:review",
        "framework_review_capacity:read",
        "ai_systems:read",
        "compliance_policies:read",
        "compliance:read",
        "vendors:read",
        "vendor_criticality:read",
        "vendor_supply_chain:read",
        "vendor_supply_chain:manage",
        "vendor_concentration_risk:read",
        "vendor_concentration_risk:manage",
        "vendor_remediation_portal:read",
        "vendor:read",
        "monitoring:read",
        "compliance_deadlines:read",
        "risk_appetite:read",
        "risk_indicators:read",
        "issues:read",
        "escalations:read",
        "ai_governance:read",
        "llm_observability:read",
        "integrations:read",
        "data:read",
        "privacy:read",
        "technical_controls:manage",
        "technical_controls:view",
        "identity_governance:read",
        "identity_governance:manage",
        "sod:read",
        "sod:manage",
        "legal_matters:read",
        "legal_matters:write",
        "ip_assets:read",
        "ip_assets:manage",
        "content_provenance:manage",
        "training_data_rights:manage",
        "synthetic_data:manage",
        "geopolitical_risk:read",
        "geopolitical_risk:manage",
        "ot_ics_assets:read",
        "ot_ics_assets:manage",
        "ai_usage_policy:read",
        "ai_usage_policy:write",
        "training_analytics:read",
        "training_analytics:write",
        "bcm:read",
        "crisis_management:read",
        "financial_risk:read",
        "resilience_testing:read",
        "anti_bribery:read",
        "export_control:read",
        "search:read",
        "onboarding_baseline:read",
        "command_palette:search",
        "command_palette:execute",
        "compliance_timeline:read",
        "compliance_inbox:read",
        "compliance_summary:generate",
    },
    "auditor": {
        "frameworks:read",
        "controls:read",
        "evidence:read",
        "risks:read",
        "audit_logs:read",
        "dashboard:read",
        "tasks:read",
        "org:read",
        "email:read",
        "automation:read",
        "evidence_automation_rules:read",
        "compliance_bot:list_subscriptions",
        "compliance_bot:read_outbox",
        "issue_sync_connection:list",
        "issue_sync_events:list",
        "issue_sync_comments:list",
        "recertification:read",
        "reports:read",
        "exports:read",
        "exports:verify",
        "retention:read",
        "attestations:read",
        "attestations:view",
        "policy_exceptions:view",
        "policy_risks:view",
        "policy_issues:view",
        "audit:read",
        "governance_override:read",
        "governance_override_template:read",
        "framework_review_capacity:read",
        "ai_systems:read",
        "compliance_policies:read",
        "compliance:read",
        "vendors:read",
        "vendor_criticality:read",
        "vendor_supply_chain:read",
        "vendor_concentration_risk:read",
        "vendor_remediation_portal:read",
        "vendor:read",
        "monitoring:read",
        "compliance_deadlines:read",
        "risk_appetite:read",
        "risk_indicators:read",
        "escalations:read",
        "ai_governance:read",
        "llm_observability:read",
        "integrations:read",
        "data:read",
        "privacy:read",
        "technical_controls:view",
        "identity_governance:read",
        "sod:read",
        "legal_matters:read",
        "ip_assets:read",
        "geopolitical_risk:read",
        "ot_ics_assets:read",
        "ai_usage_policy:read",
        "training_analytics:read",
        "bcm:read",
        "crisis_management:read",
        "financial_risk:read",
        "resilience_testing:read",
        "anti_bribery:read",
        "export_control:read",
        "search:read",
        "onboarding_baseline:read",
        "command_palette:search",
        "compliance_timeline:read",
        "compliance_inbox:read",
    },
    "readonly": {
        "frameworks:read",
        "controls:read",
        "evidence:read",
        "risks:read",
        "tasks:read",
        "dashboard:read",
        "org:read",
        "reports:read",
        "exports:read",
        "retention:read",
        "attestations:read",
        "attestations:view",
        "policy_exceptions:view",
        "policy_risks:view",
        "policy_issues:view",
        "audit:read",
        "governance_override:read",
        "governance_override_template:read",
        "framework_review_capacity:read",
        "ai_systems:read",
        "compliance_policies:read",
        "compliance:read",
        "vendors:read",
        "vendor_criticality:read",
        "vendor_supply_chain:read",
        "vendor_concentration_risk:read",
        "vendor_remediation_portal:read",
        "vendor:read",
        "monitoring:read",
        "compliance_deadlines:read",
        "risk_appetite:read",
        "risk_indicators:read",
        "issues:read",
        "escalations:read",
        "integrations:read",
        "data:read",
        "privacy:read",
        "technical_controls:view",
        "identity_governance:read",
        "sod:read",
        "legal_matters:read",
        "ip_assets:read",
        "geopolitical_risk:read",
        "ot_ics_assets:read",
        "ai_usage_policy:read",
        "training_analytics:read",
        "bcm:read",
        "crisis_management:read",
        "financial_risk:read",
        "resilience_testing:read",
        "anti_bribery:read",
        "export_control:read",
        "search:read",
        "command_palette:search",
        "compliance_timeline:read",
        "compliance_inbox:read",
    },
}

PILLAR1_AUDIT_ACTION_REGISTRY: dict[str, tuple[str, ...]] = {
    "compliance_policies": (
        "compliance_policy.created",
        "compliance_policy.updated",
        "compliance_policy.archived",
    ),
    "compliance_policy_versions": (
        "compliance_policy_version.created",
        "compliance_policy_version.submitted",
    ),
    "compliance_policy_approval_requests": (
        "compliance_policy_approval.requested",
        "compliance_policy_approval.approved",
        "compliance_policy_approval.rejected",
        "compliance_policy_approval.cancelled",
    ),
    "compliance_policy_control_links": (
        "compliance_policy.control_linked",
        "compliance_policy.control_unlinked",
    ),
    "vendors": (
        "vendor.created",
        "vendor.updated",
        "vendor.archived",
    ),
    "vendor_assessments": (
        "vendor_assessment.created",
        "vendor_assessment.started",
        "vendor_assessment.completed",
        "vendor_assessment.cancelled",
        "vendor_assessment_question.answered",
    ),
    "vendor_risk_scores": (
        "vendor_risk_score.created",
    ),
    "vendor_criticality": (
        "vendor_criticality_settings.updated",
        "vendor_criticality_profile.updated",
    ),
    "vendor_remediation_portal": (
        "vendor_remediation_portal.token_created",
        "vendor_remediation_portal.token_revoked",
        "vendor_remediation_portal.token_expired",
        "vendor_remediation_portal.access",
        "vendor_remediation_portal.data_viewed",
        "vendor_remediation_portal.evidence_submitted",
    ),
    "vendor_control_links": (
        "vendor.control_linked",
        "vendor.control_unlinked",
    ),
    "vendor_questionnaires": (
        "questionnaire_template.created",
        "questionnaire_template.cloned",
        "questionnaire_template.deleted",
        "questionnaire_response.created",
        "questionnaire_response.answer_submitted",
        "questionnaire_response.bulk_answers_submitted",
        "questionnaire_response.status_transitioned",
        "questionnaire_response.score_computed",
        "scoring_rule.created",
        "scoring_rule.updated",
        "scoring_rule.deactivated",
    ),
    "inbound_questionnaires": (
        "inbound_questionnaire.session_created",
        "inbound_questionnaire.item_added",
        "inbound_questionnaire.items_bulk_added",
        "inbound_questionnaire.item_drafted",
        "inbound_questionnaire.all_drafted",
        "inbound_questionnaire.item_approved",
        "inbound_questionnaire.item_edited",
        "inbound_questionnaire.item_rejected",
        "inbound_questionnaire.item_sent",
        "inbound_questionnaire.session_completed",
    ),
    "subprocessors": (
        "subprocessor.created",
        "subprocessor.updated",
        "subprocessor.dpa_status_updated",
        "subprocessor.reviewed",
        "subprocessor.deleted",
        "subprocessor.transfer_added",
        "subprocessor.dpa_expiry_swept",
    ),
    "customer_commitments": (
        "customer_commitment.created",
        "customer_commitment.updated",
        "customer_commitment.triggered",
        "customer_commitment.fulfilled",
        "customer_commitment.waived",
        "customer_commitment.deleted",
        "customer_commitment.sweep_processed",
    ),
    "risk_indicators": (
        "risk_indicator.created",
        "risk_indicator.updated",
        "risk_indicator.recalculated",
        "risk_indicator.archived",
    ),
    "risk_appetite": (
        "risk_appetite.created",
        "risk_appetite.updated",
        "risk_appetite.deactivated",
        "risk_appetite.breach_detected",
    ),
    "control_monitoring_definitions": (
        "control_monitoring_definition.created",
        "control_monitoring_definition.updated",
        "control_monitoring_definition.archived",
        "control_monitoring_result.recorded",
    ),
    "control_monitoring_rules": (
        "control_monitoring_rule.created",
        "control_monitoring_rule.updated",
        "control_monitoring_rule.archived",
        "control_monitoring_rule.evaluated",
    ),
    "control_monitoring_alerts": (
        "control_monitoring_alert.created",
        "control_monitoring_alert.acknowledged",
        "control_monitoring_alert.resolved",
        "control_monitoring_alert.dismissed",
        "control_monitoring_alert.assigned",
    ),
    "issues": (
        "issue.created",
        "issue.updated",
        "issue.assigned",
        "issue.transitioned",
        "issue.promoted_from_alert",
        "issue.promoted_from_finding",
        "issue.deleted",
        "issue_settings.updated",
        "rca.created",
        "rca.updated",
        "rca.reviewed",
        "sla_policy.updated",
        "sla.response_breached",
        "sla.resolution_breached",
    ),
    "escalations": (
        "escalation_policy.created",
        "escalation_policy.updated",
        "escalation_policy.deactivated",
        "escalation.fired",
    ),
    "breach_notifications": (
        "breach_notification.created",
        "breach_notification.regulator_notified",
        "breach_notification.subjects_notified",
        "breach_notification.closed",
        "breach_notification.deadline_warned",
    ),
    "webhooks": (
        "webhook_endpoint.created",
        "webhook_endpoint.updated",
        "webhook_endpoint.deactivated",
        "webhook_endpoint.deleted",
        "webhook.emitted",
        "webhook.delivered",
        "webhook.delivery_failed",
    ),
    "offboarding": (
        "offboarding.validated",
        "offboarding.executed",
        "offboarding.risks_reassigned",
        "offboarding.controls_reassigned",
        "offboarding.tasks_reassigned",
        "offboarding.policies_reassigned",
        "offboarding.vendors_reassigned",
        "offboarding.audit_engagements_reassigned",
    ),
    "control_exceptions": (
        "control_exception.created",
        "control_exception.approved",
        "control_exception.rejected",
        "control_exception.revoked",
        "control_exception.expired",
        "control_exception.approval_step_completed",
    ),
    "common_controls": (
        "common_control.mapping_created",
        "common_control.mapping_updated",
        "common_control.mapping_deactivated",
        "common_control.evidence_coverage_added",
    ),
    "oscal_exports": (
        "oscal_export.job_created",
        "oscal_export.job_completed",
        "oscal_export.job_failed",
    ),
    "technical_controls": (
        "technical_control.agent_registered",
        "technical_control.agent_deregistered",
        "technical_control.rule_created",
        "technical_control.rule_updated",
        "technical_control.rule_deactivated",
        "technical_control.result_ingested",
        "technical_control.result_failed",
    ),
    "employee_attestations": (
        "attestation.campaign_created",
        "attestation.campaign_updated",
        "attestation.campaign_cancelled",
        "attestation.submitted",
        "attestation.user_exempted",
        "attestation.reminder_sent",
        "attestation.bulk_reminder_sent",
        "attestation.expired",
    ),
    "policy_exceptions": (
        "policy_exception.created",
        "policy_exception.updated",
        "policy_exception.withdrawn",
        "policy_exception.approved",
        "policy_exception.rejected",
        "policy_exception.expired",
    ),
    "policy_templates": (
        "policy_template.created",
        "policy_template.applied",
        "policy_template.cloned",
    ),
    "policy_risk_mappings": (
        "policy_risk_mapping.created",
        "policy_risk_mapping.updated",
        "policy_risk_mapping.deleted",
        "policy.risk_linked",
        "policy.risk_unlinked",
    ),
    "policy_issue_links": (
        "policy_issue_link.created",
        "policy_issue_link.updated",
        "policy_issue_link.deleted",
        "policy.issue_linked",
        "policy.issue_unlinked",
    ),
    "compliance_deadlines": (
        "compliance_deadline.created",
        "compliance_deadline.updated",
        "compliance_deadline.completed",
        "compliance_deadline.waived",
        "compliance_deadline.cancelled",
        "compliance_deadline.evaluated",
    ),
    "audit_engagements": (
        "audit_engagement.created",
        "audit_engagement.updated",
        "audit_engagement.status_transitioned",
        "audit_engagement.deleted",
    ),
    "pbc_items": (
        "pbc_item.created",
        "pbc_item.submitted",
        "pbc_item.accepted",
        "pbc_item.rejected",
        "pbc_item.overdue_marked",
        "pbc_item.deleted",
    ),
    "auditor_portal": (
        "auditor_portal.invitation_created",
        "auditor_portal.invitation_revoked",
        "auditor_portal.access",
    ),
    "audit_findings": (
        "audit_finding.created",
        "audit_finding.updated",
        "audit_finding.status_transitioned",
        "audit_finding.risk_linked",
        "audit_finding.bulk_transitioned",
        "audit_finding.deleted",
    ),
    "audit_schedules": (
        "audit_schedule.created",
        "audit_schedule.updated",
        "audit_schedule.status_changed",
        "audit_schedule.engagement_linked",
        "audit_schedule.reminder_processed",
    ),
    "evidence_packages": (
        "evidence_package.created",
        "evidence_package.item_added",
        "evidence_package.item_removed",
        "evidence_package.assembled",
        "evidence_package.exported",
        "evidence_package.archived",
        "evidence_package.deleted",
    ),
}

EMAIL_TEMPLATE_SEEDS: list[dict] = [
    {
        "template_key": "invited_user_activation",
        "name": "Invited User Activation",
        "description": "Activation instructions for invited users.",
        "subject_template": "Activate your CompliVibe account",
        "body_text_template": "Hello {{ user_name }},\n\nUse this activation link to set your password: {{ activation_link }}\n\nThis link expires soon.",
        "body_html_template": None,
        "allowed_variables_json": ["user_name", "activation_link"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "task_assigned",
        "name": "Task Assigned",
        "description": "Notification when a task is assigned.",
        "subject_template": "New task assigned: {{ task_title }}",
        "body_text_template": "Hello {{ user_name }},\n\nA task has been assigned to you: {{ task_title }}.",
        "body_html_template": None,
        "allowed_variables_json": ["user_name", "task_title"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "evidence_requested",
        "name": "Evidence Requested",
        "description": "Request for evidence submission.",
        "subject_template": "Evidence requested: {{ request_title }}",
        "body_text_template": "Hello {{ user_name }},\n\nEvidence is requested for: {{ request_title }}.",
        "body_html_template": None,
        "allowed_variables_json": ["user_name", "request_title"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "control_owner_reminder",
        "name": "Control Owner Reminder",
        "description": "Reminder for control owners.",
        "subject_template": "Reminder: review control {{ control_title }}",
        "body_text_template": "Hello {{ user_name }},\n\nPlease review control: {{ control_title }}.",
        "body_html_template": None,
        "allowed_variables_json": ["user_name", "control_title"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "password_reset",
        "name": "Password Reset",
        "description": "Secure password reset instructions.",
        "subject_template": "Reset your CompliVibe password",
        "body_text_template": (
            "Hello {{ user_name }},\n\n"
            "We received a request to reset your CompliVibe password. Use this secure link: {{ reset_link }}.\n"
            "For your security, this link expires at {{ expires_at }}.\n\n"
            "If you did not request this change, contact your administrator immediately."
        ),
        "body_html_template": (
            "<html><body style=\"font-family:Arial,sans-serif;color:#1f2937;line-height:1.5;\">"
            "<h2 style=\"margin:0 0 12px 0;\">Reset your CompliVibe password</h2>"
            "<p>Hello {{ user_name }},</p>"
            "<p>We received a request to reset your CompliVibe password. Use the secure link below:</p>"
            "<p><a href=\"{{ reset_link }}\" style=\"background:#0f766e;color:#fff;padding:10px 14px;border-radius:6px;text-decoration:none;\">Reset Password</a></p>"
            "<p>This link expires at <strong>{{ expires_at }}</strong>.</p>"
            "<p>If you did not request this change, contact your administrator immediately.</p>"
            "<p style=\"font-size:12px;color:#6b7280;\">This is an automated security message from CompliVibe.</p>"
            "</body></html>"
        ),
        "allowed_variables_json": ["user_name", "reset_link", "expires_at"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "attestation_campaign_reminder",
        "name": "Attestation Campaign Reminder",
        "description": "Reminder that a policy attestation is due soon.",
        "subject_template": "Attestation due: {{ campaign_title }}",
        "body_text_template": (
            "Hello {{ user_name }},\n\n"
            "You have an open policy attestation campaign: {{ campaign_title }}.\n"
            "Policy: {{ policy_title }}\n"
            "Due date: {{ due_date }}\n\n"
            "Please complete your attestation in CompliVibe before the deadline."
        ),
        "body_html_template": (
            "<html><body style=\"font-family:Arial,sans-serif;color:#111827;line-height:1.5;\">"
            "<h2 style=\"margin:0 0 12px 0;\">Policy Attestation Reminder</h2>"
            "<p>Hello {{ user_name }},</p>"
            "<p>You have an open attestation campaign: <strong>{{ campaign_title }}</strong>.</p>"
            "<table style=\"border-collapse:collapse;margin:8px 0 12px 0;\">"
            "<tr><td style=\"padding:4px 10px 4px 0;color:#6b7280;\">Policy</td><td>{{ policy_title }}</td></tr>"
            "<tr><td style=\"padding:4px 10px 4px 0;color:#6b7280;\">Due date</td><td>{{ due_date }}</td></tr>"
            "</table>"
            "<p>Please complete your attestation in CompliVibe before the deadline.</p>"
            "<p style=\"font-size:12px;color:#6b7280;\">Automated compliance reminder from CompliVibe.</p>"
            "</body></html>"
        ),
        "allowed_variables_json": ["user_name", "campaign_title", "policy_title", "due_date"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "pbc_request_assigned",
        "name": "PBC Request Assigned",
        "description": "Notification that a PBC request was assigned.",
        "subject_template": "PBC request assigned: {{ request_title }}",
        "body_text_template": (
            "Hello {{ user_name }},\n\n"
            "A Prepared-By-Client request was assigned to you.\n"
            "Request: {{ request_title }}\n"
            "Audit: {{ audit_title }}\n"
            "Due date: {{ due_date }}\n\n"
            "Please submit the required evidence through CompliVibe."
        ),
        "body_html_template": (
            "<html><body style=\"font-family:Arial,sans-serif;color:#1f2937;line-height:1.5;\">"
            "<h2 style=\"margin:0 0 12px 0;\">PBC Request Assigned</h2>"
            "<p>Hello {{ user_name }},</p>"
            "<p>A Prepared-By-Client request has been assigned to you.</p>"
            "<ul>"
            "<li><strong>Request:</strong> {{ request_title }}</li>"
            "<li><strong>Audit:</strong> {{ audit_title }}</li>"
            "<li><strong>Due date:</strong> {{ due_date }}</li>"
            "</ul>"
            "<p>Please submit the required evidence through CompliVibe.</p>"
            "<p style=\"font-size:12px;color:#6b7280;\">Automated audit workflow message from CompliVibe.</p>"
            "</body></html>"
        ),
        "allowed_variables_json": ["user_name", "request_title", "audit_title", "due_date"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "audit_finding_assigned",
        "name": "Audit Finding Assigned",
        "description": "Notification that a remediation owner was assigned to an audit finding.",
        "subject_template": "Audit finding assigned: {{ finding_title }}",
        "body_text_template": (
            "Hello {{ user_name }},\n\n"
            "You were assigned as remediation owner for an audit finding.\n"
            "Finding: {{ finding_title }}\n"
            "Severity: {{ severity }}\n"
            "Due date: {{ remediation_due_date }}\n\n"
            "Review the finding and update the remediation plan in CompliVibe."
        ),
        "body_html_template": (
            "<html><body style=\"font-family:Arial,sans-serif;color:#111827;line-height:1.5;\">"
            "<h2 style=\"margin:0 0 12px 0;\">Audit Finding Assigned</h2>"
            "<p>Hello {{ user_name }},</p>"
            "<p>You were assigned as remediation owner for an audit finding.</p>"
            "<ul>"
            "<li><strong>Finding:</strong> {{ finding_title }}</li>"
            "<li><strong>Severity:</strong> {{ severity }}</li>"
            "<li><strong>Due date:</strong> {{ remediation_due_date }}</li>"
            "</ul>"
            "<p>Review the finding and update the remediation plan in CompliVibe.</p>"
            "<p style=\"font-size:12px;color:#6b7280;\">Automated audit governance message from CompliVibe.</p>"
            "</body></html>"
        ),
        "allowed_variables_json": ["user_name", "finding_title", "severity", "remediation_due_date"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "vendor_mitigation_case_created",
        "name": "Vendor Mitigation Case Created",
        "description": "Notification that a high-risk vendor mitigation case was opened.",
        "subject_template": "Vendor mitigation case opened: {{ case_title }}",
        "body_text_template": (
            "Hello {{ user_name }},\n\n"
            "A vendor mitigation case has been opened.\n"
            "Case: {{ case_title }}\n"
            "Vendor: {{ vendor_name }}\n"
            "Risk score: {{ risk_score }}\n\n"
            "Please review mitigation actions and track evidence in CompliVibe."
        ),
        "body_html_template": (
            "<html><body style=\"font-family:Arial,sans-serif;color:#1f2937;line-height:1.5;\">"
            "<h2 style=\"margin:0 0 12px 0;\">Vendor Mitigation Case Opened</h2>"
            "<p>Hello {{ user_name }},</p>"
            "<p>A vendor mitigation case has been opened for follow-up.</p>"
            "<ul>"
            "<li><strong>Case:</strong> {{ case_title }}</li>"
            "<li><strong>Vendor:</strong> {{ vendor_name }}</li>"
            "<li><strong>Risk score:</strong> {{ risk_score }}</li>"
            "</ul>"
            "<p>Please review mitigation actions and track evidence in CompliVibe.</p>"
            "<p style=\"font-size:12px;color:#6b7280;\">Automated third-party risk message from CompliVibe.</p>"
            "</body></html>"
        ),
        "allowed_variables_json": ["user_name", "case_title", "vendor_name", "risk_score"],
        "status": "active",
        "version": 1,
    },
    {
        "template_key": "commitment_breach_notification",
        "name": "Commitment Breach Notification",
        "description": "Notification that a customer commitment is due or breached.",
        "subject_template": "Customer commitment alert: {{ commitment_title }}",
        "body_text_template": (
            "Hello {{ user_name }},\n\n"
            "A customer commitment requires immediate attention.\n"
            "Commitment: {{ commitment_title }}\n"
            "Status: {{ commitment_status }}\n"
            "Due date: {{ due_date }}\n\n"
            "Please review obligations and record actions in CompliVibe."
        ),
        "body_html_template": (
            "<html><body style=\"font-family:Arial,sans-serif;color:#111827;line-height:1.5;\">"
            "<h2 style=\"margin:0 0 12px 0;\">Customer Commitment Alert</h2>"
            "<p>Hello {{ user_name }},</p>"
            "<p>A customer commitment requires immediate attention.</p>"
            "<ul>"
            "<li><strong>Commitment:</strong> {{ commitment_title }}</li>"
            "<li><strong>Status:</strong> {{ commitment_status }}</li>"
            "<li><strong>Due date:</strong> {{ due_date }}</li>"
            "</ul>"
            "<p>Please review obligations and record actions in CompliVibe.</p>"
            "<p style=\"font-size:12px;color:#6b7280;\">Automated commitment monitoring message from CompliVibe.</p>"
            "</body></html>"
        ),
        "allowed_variables_json": ["user_name", "commitment_title", "commitment_status", "due_date"],
        "status": "active",
        "version": 1,
    },
]

FRAMEWORK_SEEDS: list[dict] = [
    {
        "code": "EU_AI_ACT",
        "name": "EU AI Act",
        "description": "European Union AI regulation metadata entry.",
        "category": "AI Governance",
        "jurisdiction": "European Union",
        "authority": "European Parliament and Council",
        "version": "2024",
        "status": "active",
        "coverage_level": "metadata_only",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "RBI_IT_GOV",
        "name": "RBI IT Governance and Assurance",
        "description": "RBI master direction baseline for IT governance, risk, controls, and assurance practices.",
        "category": "Financial Regulation",
        "jurisdiction": "IN",
        "authority": "Reserve Bank of India",
        "version": "2023",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://www.rbi.org.in/scripts/BS_ViewMasDirections.aspx?id=12562",
        "effective_date": None,
    },
    {
        "code": "RBI_CLOUD_OUTSOURCING",
        "name": "RBI IT Outsourcing and Cloud Controls",
        "description": "RBI outsourcing of IT services direction used as cloud and third-party IT control baseline.",
        "category": "Financial Regulation",
        "jurisdiction": "IN",
        "authority": "Reserve Bank of India",
        "version": "2023",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12486",
        "effective_date": None,
    },
    {
        "code": "SEBI_CSCRF",
        "name": "SEBI CSCRF",
        "description": "SEBI Cybersecurity and Cyber Resilience Framework obligations for regulated entities.",
        "category": "Financial Regulation",
        "jurisdiction": "IN",
        "authority": "Securities and Exchange Board of India",
        "version": "2024",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://www.sebi.gov.in/legal/circulars/aug-2024/cybersecurity-and-cyber-resilience-framework-cscrf-for-sebi-regulated-entities-res-_85964.html",
        "effective_date": None,
    },
    {
        "code": "SEBI_CLOUD",
        "name": "SEBI Cloud Adoption Framework",
        "description": "SEBI framework for adoption of cloud services by SEBI-regulated entities.",
        "category": "Financial Regulation",
        "jurisdiction": "IN",
        "authority": "Securities and Exchange Board of India",
        "version": "2023",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://www.sebi.gov.in/legal/circulars/mar-2023/framework-for-adoption-of-cloud-services-by-sebi-regulated-entities-res-_68740.html",
        "effective_date": None,
    },
    {
        "code": "IRDAI_CYBER_2023",
        "name": "IRDAI Information and Cyber Security Guidelines",
        "description": "IRDAI cybersecurity governance and incident obligations for insurers and intermediaries.",
        "category": "Financial Regulation",
        "jurisdiction": "IN",
        "authority": "Insurance Regulatory and Development Authority of India",
        "version": "2023",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://irdai.gov.in/documents/37343/366029/IRDAI%2BCS%2BGuidelines%2B2023.pdf/81730785-1f51-977b-5a92-d9cfd7eb2cd6?download=true&t=1682401978542&version=1.0",
        "effective_date": None,
    },
    {
        "code": "CERT_IN_2022",
        "name": "CERT-In Cyber Incident Directions",
        "description": "CERT-In directions under section 70B, including six-hour reporting and logging requirements.",
        "category": "Cybersecurity",
        "jurisdiction": "IN",
        "authority": "Indian Computer Emergency Response Team",
        "version": "2022",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf",
        "effective_date": None,
    },
    {
        "code": "INDIA_IT_ACT",
        "name": "India IT Act",
        "description": "Information Technology Act 2000 and amendment obligations for reasonable security and cyber incident governance.",
        "category": "Privacy",
        "jurisdiction": "IN",
        "authority": "Government of India",
        "version": "2000/2008",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://www.indiacode.nic.in/handle/123456789/1999",
        "effective_date": None,
    },
    {
        "code": "MCA_COMPLIANCE_CAL",
        "name": "MCA Compliance Calendar",
        "description": "Companies Act annual compliance timeline for AGM, annual return, and financial statement filing windows.",
        "category": "Corporate Compliance",
        "jurisdiction": "IN",
        "authority": "Ministry of Corporate Affairs",
        "version": "2013",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://www.indiacode.nic.in/bitstream/123456789/2114/5/A2013-18.pdf",
        "effective_date": None,
    },
    {
        "code": "DPIIT_STARTUP",
        "name": "DPIIT Startup India Recognition",
        "description": "DPIIT startup recognition eligibility and continuity requirements under current gazette definition.",
        "category": "Corporate Compliance",
        "jurisdiction": "IN",
        "authority": "Department for Promotion of Industry and Internal Trade",
        "version": "2026",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://www.dpiit.gov.in/static/uploads/2026/02/119e52e2a36f652215a32c3ccc5f9c66.pdf",
        "effective_date": None,
    },
    {
        "code": "INDIA_DPDP",
        "name": "India DPDP",
        "description": (
            "India Digital Personal Data Protection Act 2023. Governs processing of digital personal "
            "data of Indian residents and defines obligations for Data Fiduciaries and Significant Data Fiduciaries."
        ),
        "category": "Privacy",
        "jurisdiction": "IN",
        "authority": "Government of India",
        "version": "2023",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "SOC2",
        "name": "SOC 2",
        "description": "AICPA SOC 2 trust services criteria metadata entry.",
        "category": "Security Assurance",
        "jurisdiction": "United States",
        "authority": "AICPA",
        "version": "2017",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "ISO_27001",
        "name": "ISO 27001",
        "description": "ISO/IEC 27001 information security standard metadata entry.",
        "category": "Security",
        "jurisdiction": "International",
        "authority": "ISO/IEC",
        "version": "2022",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "ISO_42001",
        "name": "ISO 42001",
        "description": "ISO/IEC 42001 AI management system standard metadata entry.",
        "category": "AI Governance",
        "jurisdiction": "International",
        "authority": "ISO/IEC",
        "version": "2023",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "NIST_AI_RMF",
        "name": "NIST AI RMF",
        "description": "NIST AI Risk Management Framework metadata entry.",
        "category": "AI Governance",
        "jurisdiction": "United States",
        "authority": "NIST",
        "version": "1.0",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "COLORADO_AI_ACT",
        "name": "Colorado AI Act",
        "description": "Colorado AI Act metadata entry.",
        "category": "AI Governance",
        "jurisdiction": "Colorado, United States",
        "authority": "State of Colorado",
        "version": "2024",
        "status": "active",
        "coverage_level": "metadata_only",
        "source_url": None,
        "effective_date": date(2026, 2, 1),
    },
    {
        "code": "GDPR",
        "name": "GDPR",
        "description": "EU General Data Protection Regulation metadata entry.",
        "category": "Privacy",
        "jurisdiction": "European Union",
        "authority": "European Union",
        "version": "2018",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": date(2018, 5, 25),
    },
    {
        "code": "CCPA_CPRA",
        "name": "CCPA/CPRA",
        "description": (
            "California Consumer Privacy Act (CCPA) as amended by the California Privacy Rights Act (CPRA). "
            "Provides rights to know, delete, correct, opt out, and limit use of sensitive personal information."
        ),
        "category": "Privacy",
        "jurisdiction": "US-CA",
        "authority": "State of California",
        "version": "2023",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "PCI_DSS",
        "name": "PCI DSS",
        "description": "Payment Card Industry Data Security Standard v4.0 baseline.",
        "category": "Security Assurance",
        "jurisdiction": "global",
        "authority": "PCI Security Standards Council",
        "version": "4.0",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "NIST_CSF",
        "name": "NIST CSF",
        "description": "NIST Cybersecurity Framework 2.0 baseline.",
        "category": "Cybersecurity",
        "jurisdiction": "US",
        "authority": "NIST",
        "version": "2.0",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "CIS_CONTROLS_V8",
        "name": "CIS Controls",
        "description": "CIS Critical Security Controls v8 baseline.",
        "category": "Cybersecurity",
        "jurisdiction": "global",
        "authority": "Center for Internet Security",
        "version": "v8",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "ISO_27701",
        "name": "ISO 27701",
        "description": "ISO/IEC 27701:2019 privacy information management system extension.",
        "category": "Privacy",
        "jurisdiction": "global",
        "authority": "ISO/IEC",
        "version": "2019",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "DORA",
        "name": "DORA",
        "description": "EU Digital Operational Resilience Act (Regulation EU 2022/2554).",
        "category": "Operational Resilience",
        "jurisdiction": "EU",
        "authority": "European Union",
        "version": "2022/2554",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "CSA_STAR_CCM",
        "name": "CSA STAR CCM",
        "description": (
            "Cloud Security Alliance STAR / Cloud Controls Matrix v4.0 cloud security controls. "
            "Includes 197 CCM control objectives across 17 domains."
        ),
        "category": "Cloud Security",
        "jurisdiction": "global",
        "authority": "Cloud Security Alliance",
        "version": "CCM v4.0",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://cloudsecurityalliance.org/research/cloud-controls-matrix",
        "effective_date": None,
    },
    {
        "code": "EU_CRA_ANNEX_IV",
        "name": "EU CRA Annex IV",
        "description": (
            "Cyber Resilience Act Annex IV critical products with digital elements classification seed."
        ),
        "category": "Cybersecurity",
        "jurisdiction": "EU",
        "authority": "European Union",
        "version": "Regulation (EU) 2024/2847",
        "status": "active",
        "coverage_level": "starter",
        "source_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng",
        "effective_date": None,
    },
    {
        "code": "NIS2",
        "name": "NIS2",
        "description": "EU Network and Information Security Directive 2 (Directive EU 2022/2555).",
        "category": "Cybersecurity",
        "jurisdiction": "EU",
        "authority": "European Union",
        "version": "2022/2555",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "NIST_800_53",
        "name": "NIST SP 800-53",
        "description": (
            "NIST Special Publication 800-53 security controls with FedRAMP Rev 4 LOW, MODERATE, "
            "and HIGH baseline selections. Required for US federal cloud systems."
        ),
        "category": "Cybersecurity",
        "jurisdiction": "US",
        "authority": "NIST",
        "version": "Rev 4 / FedRAMP",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "HIPAA",
        "name": "HIPAA",
        "description": (
            "Health Insurance Portability and Accountability Act. Privacy Rule, Security Rule, and Breach "
            "Notification Rule. Required for covered entities and business associates handling PHI."
        ),
        "category": "Privacy",
        "jurisdiction": "US",
        "authority": "HHS",
        "version": "2013 Omnibus",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "ISO_31000",
        "name": "ISO 31000",
        "description": "ISO 31000:2018 risk management guidelines and principles.",
        "category": "Risk Management",
        "jurisdiction": "global",
        "authority": "ISO",
        "version": "2018",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "OECD_AI_PRINCIPLES",
        "name": "OECD AI Principles",
        "description": "OECD Principles on Artificial Intelligence (updated 2024).",
        "category": "AI Governance",
        "jurisdiction": "global",
        "authority": "OECD",
        "version": "2024",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "IEEE_7000_SERIES",
        "name": "IEEE 7000 Series",
        "description": "IEEE 7000-series standards for ethically aligned AI and autonomous systems.",
        "category": "AI Governance",
        "jurisdiction": "global",
        "authority": "IEEE",
        "version": "2021-2022",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "UNESCO_AI_ETHICS",
        "name": "UNESCO AI Ethics",
        "description": "UNESCO Recommendation on the Ethics of AI (2021).",
        "category": "AI Governance",
        "jurisdiction": "global",
        "authority": "UNESCO",
        "version": "2021",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "SINGAPORE_MODEL_AI_GOV",
        "name": "Singapore Model AI Governance",
        "description": "Singapore Model AI Governance Framework 2nd Edition (2020).",
        "category": "AI Governance",
        "jurisdiction": "SG",
        "authority": "IMDA",
        "version": "2020",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "G7_HIROSHIMA_AI_PROCESS",
        "name": "G7 Hiroshima AI Process",
        "description": "G7 Hiroshima AI Process International Guiding Principles (2023).",
        "category": "AI Governance",
        "jurisdiction": "global",
        "authority": "G7",
        "version": "2023",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
    {
        "code": "MITRE_ATLAS",
        "name": "MITRE ATLAS",
        "description": "MITRE ATLAS adversarial threat landscape for AI systems.",
        "category": "AI Security",
        "jurisdiction": "global",
        "authority": "MITRE",
        "version": "4.5",
        "status": "active",
        "coverage_level": "starter",
        "source_url": None,
        "effective_date": None,
    },
]

FRAMEWORK_VERSION_SEEDS: list[dict] = [
    {"framework_code": "EU_AI_ACT", "version_label": "2024", "status": "active", "coverage_level": "metadata_only"},
    {"framework_code": "INDIA_DPDP", "version_label": "2023", "status": "active", "coverage_level": "starter"},
    {"framework_code": "ISO_42001", "version_label": "2023", "status": "active", "coverage_level": "starter"},
    {"framework_code": "NIST_AI_RMF", "version_label": "1.0", "status": "active", "coverage_level": "starter"},
    {"framework_code": "SOC2", "version_label": "2017", "status": "active", "coverage_level": "starter"},
    {"framework_code": "ISO_27001", "version_label": "2022", "status": "active", "coverage_level": "starter"},
    {"framework_code": "COLORADO_AI_ACT", "version_label": "2024", "status": "active", "coverage_level": "metadata_only"},
    {"framework_code": "GDPR", "version_label": "2018", "status": "active", "coverage_level": "starter"},
    {"framework_code": "CCPA_CPRA", "version_label": "2023", "status": "active", "coverage_level": "starter"},
    {"framework_code": "PCI_DSS", "version_label": "4.0", "status": "active", "coverage_level": "starter"},
    {"framework_code": "NIST_CSF", "version_label": "2.0", "status": "active", "coverage_level": "starter"},
    {"framework_code": "CIS_CONTROLS_V8", "version_label": "v8", "status": "active", "coverage_level": "starter"},
    {"framework_code": "ISO_27701", "version_label": "2019", "status": "active", "coverage_level": "starter"},
    {"framework_code": "DORA", "version_label": "2022/2554", "status": "active", "coverage_level": "starter"},
    {"framework_code": "CSA_STAR_CCM", "version_label": "CCM v4.0", "status": "active", "coverage_level": "starter"},
    {"framework_code": "EU_CRA_ANNEX_IV", "version_label": "2024/2847", "status": "active", "coverage_level": "starter"},
    {"framework_code": "NIS2", "version_label": "2022/2555", "status": "active", "coverage_level": "starter"},
    {"framework_code": "NIST_800_53", "version_label": "Rev 4 / FedRAMP", "status": "active", "coverage_level": "starter"},
    {"framework_code": "HIPAA", "version_label": "2013 Omnibus", "status": "active", "coverage_level": "starter"},
    {"framework_code": "ISO_31000", "version_label": "2018", "status": "active", "coverage_level": "starter"},
    {"framework_code": "OECD_AI_PRINCIPLES", "version_label": "2024", "status": "active", "coverage_level": "starter"},
    {"framework_code": "IEEE_7000_SERIES", "version_label": "2021-2022", "status": "active", "coverage_level": "starter"},
    {"framework_code": "UNESCO_AI_ETHICS", "version_label": "2021", "status": "active", "coverage_level": "starter"},
    {"framework_code": "SINGAPORE_MODEL_AI_GOV", "version_label": "2020", "status": "active", "coverage_level": "starter"},
    {"framework_code": "G7_HIROSHIMA_AI_PROCESS", "version_label": "2023", "status": "active", "coverage_level": "starter"},
    {"framework_code": "MITRE_ATLAS", "version_label": "4.5", "status": "active", "coverage_level": "starter"},
]

DATA_ACCESS_DEFAULT_RULES: list[dict] = [
    {
        "rule_type": "access_count_spike",
        "rule_config": {"count": 100, "window_minutes": 10},
    },
    {
        "rule_type": "after_hours_access",
        "rule_config": {"business_start": "09:00", "business_end": "18:00", "timezone": "UTC"},
    },
    {
        "rule_type": "mass_download",
        "rule_config": {"bytes": 5368709120},
    },
    {
        "rule_type": "failed_access_spike",
        "rule_config": {"count": 20, "window_minutes": 5},
    },
]

DORA_SECTIONS: list[dict[str, int | str]] = [
    {"code": "DORA-II", "title": "ICT Risk Management", "order": 1},
    {"code": "DORA-III", "title": "ICT Incident Management", "order": 2},
    {"code": "DORA-IV", "title": "Digital Operational Resilience Testing", "order": 3},
    {"code": "DORA-V", "title": "ICT Third-Party Risk Management", "order": 4},
    {"code": "DORA-VI", "title": "Information Sharing Arrangements", "order": 5},
]

DORA_OBLIGATIONS: list[tuple[str, str, str]] = [
    ("DORA-5.1", "Governance and organisation of ICT risk management", "DORA-II"),
    ("DORA-6.1", "ICT risk management framework", "DORA-II"),
    ("DORA-7.1", "ICT systems, protocols and tools", "DORA-II"),
    ("DORA-8.1", "Identification of ICT risks", "DORA-II"),
    ("DORA-9.1", "Protection and prevention controls", "DORA-II"),
    ("DORA-10.1", "Detection of anomalous activities", "DORA-II"),
    ("DORA-11.1", "Business continuity policy", "DORA-II"),
    ("DORA-12.1", "Backup policies and recovery procedures", "DORA-II"),
    ("DORA-13.1", "Learning and evolving", "DORA-II"),
    ("DORA-14.1", "Communication", "DORA-II"),
    ("DORA-15.1", "ICT risk management for payment systems", "DORA-II"),
    ("DORA-16.1", "Simplified ICT risk management framework", "DORA-II"),
    ("DORA-17.1", "ICT-related incident management process", "DORA-III"),
    ("DORA-18.1", "ICT-related incident classification", "DORA-III"),
    ("DORA-19.1", "Major ICT incident reporting", "DORA-III"),
    ("DORA-20.1", "Harmonised reporting", "DORA-III"),
    ("DORA-21.1", "Voluntary notification of cyber threats", "DORA-III"),
    ("DORA-24.1", "General digital operational resilience testing", "DORA-IV"),
    ("DORA-25.1", "Testing of ICT tools and systems", "DORA-IV"),
    ("DORA-26.1", "Advanced testing — TLPT", "DORA-IV"),
    ("DORA-28.1", "Key principles for ICT TPRM", "DORA-V"),
    ("DORA-28.2", "Register of information", "DORA-V"),
    ("DORA-29.1", "Preliminary assessment of ICT third-party risk", "DORA-V"),
    ("DORA-30.1", "Key contractual provisions", "DORA-V"),
    ("DORA-31.1", "Critical or important functions", "DORA-V"),
]

DORA_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "eu_financial_entity",
        "question_text": "Is your organization a financial entity operating in the EU (bank, investment firm, insurance, payment institution, CASP)?",
        "help_text": "DORA applies to financial entities under Article 2.",
        "triggers_scope": "all",
        "order_index": 1,
    },
    {
        "question_key": "is_microenterprise",
        "question_text": "Is your organization a microenterprise (fewer than 10 employees and turnover < EUR 2M)?",
        "help_text": "Microenterprises may use the simplified framework under Art. 16.",
        "triggers_scope": "partial",
        "order_index": 2,
    },
]

NIS2_SECTIONS: list[dict[str, int | str]] = [
    {"code": "NIS2-ART21", "title": "Cybersecurity Risk Management Measures", "order": 1},
    {"code": "NIS2-ART23", "title": "Reporting Obligations", "order": 2},
    {"code": "NIS2-ART24", "title": "Use of European Cybersecurity Schemes", "order": 3},
]

NIS2_OBLIGATIONS: list[tuple[str, str, str]] = [
    ("NIS2-21.1", "Policies on risk analysis and information system security", "NIS2-ART21"),
    ("NIS2-21.2", "Incident handling", "NIS2-ART21"),
    ("NIS2-21.3", "Business continuity and backup", "NIS2-ART21"),
    ("NIS2-21.4", "Supply chain security", "NIS2-ART21"),
    ("NIS2-21.5", "Security in network acquisition and development", "NIS2-ART21"),
    ("NIS2-21.6", "Policies and procedures for cryptography and encryption", "NIS2-ART21"),
    ("NIS2-21.7", "Human resources security and access control", "NIS2-ART21"),
    ("NIS2-21.8", "Use of multi-factor authentication", "NIS2-ART21"),
    ("NIS2-21.9", "Securing communications and emergency communications", "NIS2-ART21"),
    ("NIS2-21.10", "Awareness training", "NIS2-ART21"),
    ("NIS2-23.1", "Significant incident — early warning (24h)", "NIS2-ART23"),
    ("NIS2-23.2", "Significant incident — notification (72h)", "NIS2-ART23"),
    ("NIS2-23.3", "Significant incident — final report (1 month)", "NIS2-ART23"),
    ("NIS2-23.4", "Intermediate report if requested", "NIS2-ART23"),
    ("NIS2-24.1", "Use of certified ICT products and services", "NIS2-ART24"),
]

NIS2_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "eu_entity",
        "question_text": "Does your organization operate in the European Union or provide services to EU residents?",
        "help_text": "NIS2 applies to essential and important entities with EU impact.",
        "triggers_scope": "all",
        "order_index": 1,
    },
    {
        "question_key": "entity_type",
        "question_text": "Is your organization classified as an Essential Entity (EE) or Important Entity (IE) under NIS2?",
        "help_text": "Both EE and IE entities must comply with NIS2 Art. 21 controls.",
        "triggers_scope": "partial",
        "order_index": 2,
    },
    {
        "question_key": "sector",
        "question_text": "Which NIS2 sector applies to your organization?",
        "help_text": "Annex I and Annex II sectors are in-scope under NIS2.",
        "triggers_scope": "partial",
        "order_index": 3,
        "answer_type": "single_select",
    },
]

ISO42001_OBLIGATIONS: list[tuple[str, str]] = [
    ("4.1", "Understanding the organization and its context for AI"),
    ("4.2", "Understanding the needs and expectations of interested parties for AI"),
    ("4.3", "Determining the scope of the AI management system"),
    ("4.4", "AI management system establishment and maintenance"),
    ("5.1", "Leadership commitment to AI management system"),
    ("5.2", "AI policy establishment and communication"),
    ("5.3", "Organizational roles, responsibilities and authorities for AI"),
    ("6.1", "Actions to address risks and opportunities in AI"),
    ("6.1.2", "AI impact assessment process"),
    ("6.2", "AI objectives and planning to achieve them"),
    ("7.1", "Resources for AI management system"),
    ("7.2", "AI-specific competence requirements"),
    ("7.3", "Awareness of AI policies and objectives"),
    ("7.4", "Communication regarding AI management"),
    ("7.5", "Documented information management for AI"),
    ("8.1", "Operational planning and control for AI systems"),
    ("8.2", "AI risk assessment process"),
    ("8.3", "AI risk treatment process"),
    ("8.4", "AI system impact assessment"),
    ("8.5", "Data management for AI systems"),
    ("8.6", "Responsible AI development practices"),
    ("8.7", "AI system verification and validation"),
    ("8.8", "AI system documentation"),
    ("8.9", "AI system deployment controls"),
    ("9.1", "Monitoring, measurement, analysis and evaluation of AI"),
    ("9.2", "Internal audit of AI management system"),
    ("9.3", "Management review of AI management system"),
    ("10.1", "Continual improvement of AI management system"),
    ("10.2", "Nonconformity and corrective action for AI"),
    ("10.3", "Innovation and learning in AI management"),
]

NIST_AI_RMF_SUBCATEGORIES: dict[str, list[tuple[str, str]]] = {
    "GOVERN": [
        ("GOVERN-1.1", "Policies, processes, procedures, and practices for AI risk management"),
        ("GOVERN-1.2", "AI risk tolerance and appetite"),
        ("GOVERN-1.3", "Organizational roles and responsibilities for AI risk"),
        ("GOVERN-1.4", "AI risk management integration into enterprise risk"),
        ("GOVERN-1.5", "Processes for ongoing AI risk identification and management"),
        ("GOVERN-1.6", "Organizational teams are committed to AI risk management"),
        ("GOVERN-1.7", "AI risk processes across the AI lifecycle"),
        ("GOVERN-2.1", "Scientific knowledge about AI risk and impacts"),
        ("GOVERN-2.2", "AI risk accountability and organizational practices"),
        ("GOVERN-4.1", "Organizational teams understand their roles in AI risk"),
        ("GOVERN-4.2", "Risk awareness and information sharing practices"),
        ("GOVERN-5.1", "Policies for engagement with AI community"),
        ("GOVERN-5.2", "Mechanisms to incorporate affected groups' feedback"),
        ("GOVERN-6.1", "Policies for AI risk in supply chain"),
        ("GOVERN-6.2", "AI risk tracking in procurement and partnerships"),
    ],
    "MAP": [
        ("MAP-1.1", "Intended purpose and context documented"),
        ("MAP-1.2", "AI classification applicable to use case"),
        ("MAP-1.3", "Scientific findings on AI risks"),
        ("MAP-1.4", "Risks and benefits to stakeholders"),
        ("MAP-1.5", "Organizational risk tolerance applied"),
        ("MAP-1.6", "Practices for involving affected groups"),
        ("MAP-2.1", "Scientific disciplines relevant to the AI system"),
        ("MAP-2.2", "Scientific output and basis for decisions"),
        ("MAP-2.3", "AI system benefits and limitations documented"),
        ("MAP-3.1", "AI context established and documented"),
        ("MAP-3.2", "AI benefits and limitations communicated"),
        ("MAP-3.5", "Risks to affected groups identified"),
        ("MAP-5.1", "Likelihood and magnitude of AI risks identified"),
        ("MAP-5.2", "Practices for risk prioritization"),
    ],
    "MEASURE": [
        ("MEASURE-1.1", "AI risk measurement methods identified"),
        ("MEASURE-1.3", "Internal AI risk experts and methods"),
        ("MEASURE-2.1", "Test sets developed for evaluating AI risks"),
        ("MEASURE-2.2", "AI system metrics established"),
        ("MEASURE-2.3", "AI system testing and evaluation documented"),
        ("MEASURE-2.5", "AI system performance evaluated"),
        ("MEASURE-2.6", "Evaluations are documented and interpretable"),
        ("MEASURE-2.7", "AI system security and resilience tested"),
        ("MEASURE-2.8", "Fairness and bias evaluations performed"),
        ("MEASURE-2.9", "Privacy risks evaluated"),
        ("MEASURE-2.10", "AI system privacy tested"),
        ("MEASURE-2.11", "Fairness and bias evaluation documented"),
        ("MEASURE-3.1", "Risk tracking mechanisms established"),
        ("MEASURE-3.3", "Feedback mechanisms established"),
    ],
    "MANAGE": [
        ("MANAGE-1.1", "Risks managed and prioritized"),
        ("MANAGE-1.2", "Treatment plans developed for high risks"),
        ("MANAGE-1.3", "Responses to identified AI risks"),
        ("MANAGE-2.1", "Resources allocated for AI risk management"),
        ("MANAGE-2.2", "AI risk treatment plans maintained"),
        ("MANAGE-2.4", "Mechanisms for timely response to AI risks"),
        ("MANAGE-3.1", "AI incident response plans established"),
        ("MANAGE-3.2", "Affected parties informed of incidents"),
        ("MANAGE-4.1", "Post-deployment AI risks monitored"),
        ("MANAGE-4.2", "Feedback mechanisms for post-deployment"),
    ],
}

EU_AI_ACT_SOURCE_URL = "https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng"

# Regulation (EU) 2024/1689, Chapter III, Section 2 sets the high-risk AI
# system requirements in Articles 9-15. These are concise implementation
# obligations, not substituted legal text.
EU_AI_ACT_HIGH_RISK_OBLIGATIONS: list[dict[str, str]] = [
    {
        "reference_code": "Art. 9",
        "title": "Operate a lifecycle risk management system for high-risk AI",
        "description": (
            "Establish, implement, document, and maintain a continuous risk management system for each high-risk AI "
            "system. The process should identify known and reasonably foreseeable risks to health, safety, and "
            "fundamental rights; estimate and evaluate those risks, including reasonably foreseeable misuse; adopt "
            "risk-control measures; and use post-market monitoring evidence to keep the assessment current."
        ),
        "plain_language_summary": "Continuously identify, evaluate, mitigate, and monitor risks from high-risk AI systems.",
        "obligation_type": "process",
    },
    {
        "reference_code": "Art. 10",
        "title": "Apply data governance and quality controls",
        "description": (
            "For high-risk AI systems using data for training, validation, or testing, maintain data governance and "
            "management practices covering design choices, data collection, preparation, relevance, representativeness, "
            "accuracy, completeness, bias detection and mitigation, data gaps, and suitability for the intended purpose."
        ),
        "plain_language_summary": "Use governed, suitable, representative, and bias-managed data for high-risk AI.",
        "obligation_type": "control",
    },
    {
        "reference_code": "Art. 11",
        "title": "Maintain technical documentation before placing on market or putting into service",
        "description": (
            "Prepare and keep up-to-date technical documentation demonstrating that the high-risk AI system complies "
            "with EU AI Act requirements. Documentation should enable competent authorities and conformity assessors "
            "to understand the system's purpose, design, development, operation, risk controls, monitoring, and changes."
        ),
        "plain_language_summary": "Keep technical documentation sufficient to demonstrate high-risk AI compliance.",
        "obligation_type": "documentation",
    },
    {
        "reference_code": "Art. 12",
        "title": "Enable automatic record-keeping and event logs",
        "description": (
            "Design high-risk AI systems with logging capabilities that automatically record events over the system "
            "lifecycle where technically feasible. Logs should support traceability of system functioning, monitoring, "
            "incident analysis, and post-market oversight proportionate to the intended purpose and risk profile."
        ),
        "plain_language_summary": "Generate and retain logs that support traceability and oversight of high-risk AI.",
        "obligation_type": "control",
    },
    {
        "reference_code": "Art. 13",
        "title": "Provide transparency and instructions for deployers",
        "description": (
            "Design and accompany high-risk AI systems with clear, concise, complete, and correct instructions for use. "
            "The information should allow deployers to understand the provider, system characteristics, intended "
            "purpose, performance, limitations, human oversight measures, input data expectations, and maintenance needs."
        ),
        "plain_language_summary": "Give deployers the information needed to use high-risk AI safely and appropriately.",
        "obligation_type": "documentation",
    },
    {
        "reference_code": "Art. 14",
        "title": "Implement effective human oversight",
        "description": (
            "Design high-risk AI systems so natural persons can effectively oversee them during use, understand "
            "capabilities and limitations, monitor operation, interpret outputs appropriately, decide not to use or "
            "override outputs, and intervene or stop the system where necessary to prevent or minimise risks."
        ),
        "plain_language_summary": "Ensure trained people can monitor, understand, override, and stop high-risk AI when needed.",
        "obligation_type": "control",
    },
    {
        "reference_code": "Art. 15",
        "title": "Meet accuracy, robustness, and cybersecurity requirements",
        "description": (
            "Design and develop high-risk AI systems to achieve an appropriate level of accuracy, robustness, and "
            "cybersecurity throughout their lifecycle. Providers should declare relevant accuracy metrics, protect "
            "against errors, faults, inconsistencies, unauthorised access, data poisoning, model manipulation, and other "
            "adversarial or security threats proportionate to the system's risks."
        ),
        "plain_language_summary": "Set and maintain lifecycle accuracy, robustness, resilience, and cybersecurity controls.",
        "obligation_type": "control",
    },
]

OBLIGATION_SEEDS: list[dict] = [
    *[
        {
            "framework_code": "EU_AI_ACT",
            "reference_code": item["reference_code"],
            "title": item["title"],
            "description": item["description"],
            "plain_language_summary": item["plain_language_summary"],
            "obligation_type": item["obligation_type"],
            "jurisdiction": "European Union",
            "source_url": EU_AI_ACT_SOURCE_URL,
            "version": "2024",
            "status": "active",
            "effective_date": None,
            "parent_obligation_id": None,
        }
        for item in EU_AI_ACT_HIGH_RISK_OBLIGATIONS
    ],
    {
        "framework_code": "NIST_AI_RMF",
        "reference_code": "GOV-1",
        "title": "Establish AI risk governance roles",
        "description": "Define accountability for AI risk management activities.",
        "plain_language_summary": "Assign people to own AI risk governance.",
        "obligation_type": "governance",
        "jurisdiction": "United States",
        "source_url": None,
        "version": "1.0",
        "status": "active",
        "effective_date": None,
        "parent_obligation_id": None,
    },
    *[
        {
            "framework_code": "ISO_42001",
            "reference_code": reference_code,
            "title": title,
            "description": title,
            "plain_language_summary": title,
            "obligation_type": "governance",
            "jurisdiction": "International",
            "source_url": None,
            "version": "2023",
            "status": "active",
            "effective_date": None,
            "parent_obligation_id": None,
        }
        for reference_code, title in ISO42001_OBLIGATIONS
    ],
    *[
        {
            "framework_code": "NIST_AI_RMF",
            "reference_code": reference_code,
            "title": title,
            "description": title,
            "plain_language_summary": title,
            "obligation_type": function_name.lower(),
            "jurisdiction": "United States",
            "source_url": None,
            "version": "1.0",
            "status": "active",
            "effective_date": None,
            "parent_obligation_id": None,
        }
        for function_name, subcategories in NIST_AI_RMF_SUBCATEGORIES.items()
        for reference_code, title in subcategories
    ],
    {
        "framework_code": "GDPR",
        "reference_code": "GDPR-ART5",
        "title": "Process personal data lawfully and transparently",
        "description": "Personal data processing must follow lawfulness, fairness, and transparency principles.",
        "plain_language_summary": "Use personal data only on a lawful basis and explain processing clearly.",
        "obligation_type": "privacy",
        "jurisdiction": "European Union",
        "source_url": None,
        "version": "2018",
        "status": "active",
        "effective_date": date(2018, 5, 25),
        "parent_obligation_id": None,
    },
    {
        "framework_code": "GDPR",
        "reference_code": "GDPR-OBL-02",
        "title": "Document lawful basis per processing purpose",
        "description": "Identify and document lawful basis for each processing purpose under GDPR Article 6.",
        "plain_language_summary": "Keep lawful basis records for each processing purpose.",
        "obligation_type": "privacy",
        "jurisdiction": "European Union",
        "source_url": None,
        "version": "2018",
        "status": "active",
        "effective_date": date(2018, 5, 25),
        "parent_obligation_id": None,
    },
    {
        "framework_code": "GDPR",
        "reference_code": "GDPR-OBL-03",
        "title": "Provide transparent privacy notices",
        "description": "Provide clear privacy notices describing processing purposes and rights.",
        "plain_language_summary": "Publish transparent privacy notices.",
        "obligation_type": "privacy",
        "jurisdiction": "European Union",
        "source_url": None,
        "version": "2018",
        "status": "active",
        "effective_date": date(2018, 5, 25),
        "parent_obligation_id": None,
    },
    {
        "framework_code": "GDPR",
        "reference_code": "GDPR-OBL-04",
        "title": "Support right of access and portability workflows",
        "description": "Implement and operate request workflows for GDPR access and portability rights.",
        "plain_language_summary": "Operate GDPR access and portability workflows.",
        "obligation_type": "privacy",
        "jurisdiction": "European Union",
        "source_url": None,
        "version": "2018",
        "status": "active",
        "effective_date": date(2018, 5, 25),
        "parent_obligation_id": None,
    },
    {
        "framework_code": "GDPR",
        "reference_code": "GDPR-OBL-05",
        "title": "Support rectification and erasure rights",
        "description": "Implement workflows to support correction and deletion of personal data.",
        "plain_language_summary": "Support rectification and erasure requests.",
        "obligation_type": "privacy",
        "jurisdiction": "European Union",
        "source_url": None,
        "version": "2018",
        "status": "active",
        "effective_date": date(2018, 5, 25),
        "parent_obligation_id": None,
    },
    {
        "framework_code": "GDPR",
        "reference_code": "GDPR-OBL-07",
        "title": "Maintain records of processing activities",
        "description": "Maintain current records of processing activities as required by GDPR Article 30.",
        "plain_language_summary": "Maintain records of processing activities.",
        "obligation_type": "privacy",
        "jurisdiction": "European Union",
        "source_url": None,
        "version": "2018",
        "status": "active",
        "effective_date": date(2018, 5, 25),
        "parent_obligation_id": None,
    },
    {
        "framework_code": "GDPR",
        "reference_code": "GDPR-OBL-09",
        "title": "Execute data processing agreements",
        "description": "Execute and maintain processor contracts with required GDPR clauses.",
        "plain_language_summary": "Maintain GDPR-compliant processor contracts.",
        "obligation_type": "privacy",
        "jurisdiction": "European Union",
        "source_url": None,
        "version": "2018",
        "status": "active",
        "effective_date": date(2018, 5, 25),
        "parent_obligation_id": None,
    },
    {
        "framework_code": "GDPR",
        "reference_code": "GDPR-OBL-10",
        "title": "Perform DPIAs for high-risk processing",
        "description": "Perform DPIAs where processing is likely to result in high risk.",
        "plain_language_summary": "Run DPIAs for high-risk processing.",
        "obligation_type": "privacy",
        "jurisdiction": "European Union",
        "source_url": None,
        "version": "2018",
        "status": "active",
        "effective_date": date(2018, 5, 25),
        "parent_obligation_id": None,
    },
]


PCI_DSS_SECTIONS: list[dict[str, int | str]] = [
    {"code": "G1", "title": "Build and Maintain Secure Networks", "order": 1},
    {"code": "G2", "title": "Protect Account Data", "order": 2},
    {"code": "G3", "title": "Maintain a Vulnerability Management Program", "order": 3},
    {"code": "G4", "title": "Implement Strong Access Control Measures", "order": 4},
    {"code": "G5", "title": "Regularly Monitor and Test Networks", "order": 5},
    {"code": "G6", "title": "Maintain an Information Security Policy", "order": 6},
]

PCI_DSS_BASE_OBLIGATIONS: list[tuple[str, str, str]] = [
    ("REQ-1.1", "Install and maintain network security controls", "G1"),
    ("REQ-1.2", "Network security controls configurations are configured and managed", "G1"),
    ("REQ-1.3", "Network access to and from the cardholder data environment is restricted", "G1"),
    ("REQ-1.4", "Network connections between trusted and untrusted networks are controlled", "G1"),
    ("REQ-1.5", "Risks to the CDE from computing devices that can connect to both untrusted networks and the CDE are mitigated", "G1"),
    ("REQ-2.1", "Processes and mechanisms for applying secure configurations are defined and understood", "G1"),
    ("REQ-2.2", "System components are configured and managed securely", "G1"),
    ("REQ-2.3", "Wireless environments are configured and managed securely", "G1"),
    ("REQ-3.1", "Processes and mechanisms for protecting stored account data are defined and understood", "G2"),
    ("REQ-3.2", "Storage of account data is kept to a minimum", "G2"),
    ("REQ-3.3", "Sensitive authentication data (SAD) is not retained after authorization", "G2"),
    ("REQ-3.4", "Access to displays of full PAN and ability to copy PAN are restricted", "G2"),
    ("REQ-3.5", "Primary account number (PAN) is secured wherever it is stored", "G2"),
    ("REQ-3.6", "Cryptographic keys used to protect stored account data are secured", "G2"),
    ("REQ-3.7", "Where cryptography is used to protect stored account data, key management processes and procedures covering all aspects of the key lifecycle are defined and implemented", "G2"),
    ("REQ-4.1", "Processes and mechanisms for protecting cardholder data with strong cryptography during transmission over open, public networks are defined and documented", "G2"),
    ("REQ-4.2", "PAN is protected with strong cryptography during transmission", "G2"),
    ("REQ-5.1", "Processes and mechanisms for protecting all systems and networks from malicious software are defined and understood", "G3"),
    ("REQ-5.2", "Malicious software (malware) is prevented, or detected and addressed", "G3"),
    ("REQ-5.3", "Anti-malware mechanisms and processes are active, maintained, and monitored", "G3"),
    ("REQ-5.4", "Anti-phishing mechanisms protect users against phishing attacks", "G3"),
    ("REQ-6.1", "Processes and mechanisms for developing and maintaining secure systems and software are defined and understood", "G3"),
    ("REQ-6.2", "Bespoke and custom software are developed securely", "G3"),
    ("REQ-6.3", "Security vulnerabilities are identified and addressed", "G3"),
    ("REQ-6.4", "Public-facing web applications are protected against attacks", "G3"),
    ("REQ-6.5", "Changes to all system components are managed securely", "G3"),
    ("REQ-7.1", "Processes and mechanisms for restricting access to system components and cardholder data by business need to know are defined and understood", "G4"),
    ("REQ-7.2", "Access to system components and data is appropriately defined and assigned", "G4"),
    ("REQ-7.3", "Access to system components and data is managed via an access control system", "G4"),
    ("REQ-8.1", "Processes and mechanisms for identifying users and authenticating access to system components are defined and understood", "G4"),
    ("REQ-8.2", "User identification and related accounts for users and administrators are strictly managed throughout an account's lifecycle", "G4"),
    ("REQ-8.3", "User authentication is established via at least one authentication method", "G4"),
    ("REQ-8.4", "Multi-factor authentication (MFA) is implemented to secure access into the CDE", "G4"),
    ("REQ-8.5", "Multi-factor authentication (MFA) systems are configured to prevent misuse", "G4"),
    ("REQ-8.6", "Use of application and system accounts and associated authentication factors is strictly managed", "G4"),
    ("REQ-9.1", "Processes and mechanisms for restricting physical access to cardholder data are defined and understood", "G4"),
    ("REQ-9.2", "Physical access controls manage entry into facilities and systems containing cardholder data", "G4"),
    ("REQ-9.3", "Physical access for personnel and visitors is authorized and managed", "G4"),
    ("REQ-9.4", "Media with cardholder data is securely stored, accessed, distributed, and destroyed", "G4"),
    ("REQ-9.5", "Point of interaction (POI) devices are protected from tampering and unauthorized substitution", "G4"),
    ("REQ-10.1", "Processes and mechanisms for logging and monitoring all access to system components and cardholder data are defined and documented", "G5"),
    ("REQ-10.2", "Audit logs are implemented to support the detection of anomalies and suspicious activity, and the forensic analysis of events", "G5"),
    ("REQ-10.3", "Audit logs are protected from destruction and unauthorized modifications", "G5"),
    ("REQ-10.4", "Audit logs are reviewed to identify anomalies or suspicious activity", "G5"),
    ("REQ-10.5", "Retain audit log history for at least 12 months", "G5"),
    ("REQ-10.6", "Time-synchronization mechanisms support consistent time settings across all systems", "G5"),
    ("REQ-10.7", "Failures of critical security controls are detected, reported, and responded to promptly", "G5"),
    ("REQ-11.1", "Processes and mechanisms for regularly testing security of systems and networks are defined and understood", "G5"),
    ("REQ-11.2", "Wireless access points are managed and tested", "G5"),
    ("REQ-11.3", "External and internal vulnerabilities are regularly identified, prioritized, and addressed", "G5"),
    ("REQ-11.4", "External and internal penetration testing is regularly performed", "G5"),
    ("REQ-11.5", "Network intrusions and unexpected file changes are detected and responded to", "G5"),
    ("REQ-11.6", "Unauthorized changes on payment pages are detected and responded to", "G5"),
    ("REQ-12.1", "A comprehensive information security policy that governs and provides direction for protection of the entity's information assets is known and current", "G6"),
    ("REQ-12.2", "Acceptable use policies for end-user technologies are defined and implemented", "G6"),
    ("REQ-12.3", "Risks to the cardholder data environment are formally identified, evaluated, and managed", "G6"),
    ("REQ-12.4", "PCI DSS compliance is managed throughout the year", "G6"),
    ("REQ-12.5", "PCI DSS scope is documented and validated", "G6"),
    ("REQ-12.6", "Security awareness education is an ongoing activity", "G6"),
    ("REQ-12.7", "Personnel are screened to reduce risks from insider threats", "G6"),
    ("REQ-12.8", "Risks to information assets associated with third-party service provider (TPSP) relationships are managed", "G6"),
    ("REQ-12.9", "Third-party service providers (TPSPs) support their customers' PCI DSS compliance", "G6"),
    ("REQ-12.10", "Suspected and confirmed security incidents that could impact the CDE are responded to immediately", "G6"),
]

ISO_27001_SECTIONS: list[dict[str, int | str]] = [
    {"code": "A5", "title": "Organizational controls", "order": 1},
    {"code": "A6", "title": "People controls", "order": 2},
    {"code": "A7", "title": "Physical controls", "order": 3},
    {"code": "A8", "title": "Technological controls", "order": 4},
]

# ISO/IEC 27001:2022 Annex A -- all 93 controls (37 organizational + 8 people +
# 14 physical + 34 technological), matching the published standard exactly.
ISO_27001_BASE_OBLIGATIONS: list[tuple[str, str, str]] = [
    ("A.5.1", "Policies for information security", "A5"),
    ("A.5.2", "Information security roles and responsibilities", "A5"),
    ("A.5.3", "Segregation of duties", "A5"),
    ("A.5.4", "Management responsibilities", "A5"),
    ("A.5.5", "Contact with authorities", "A5"),
    ("A.5.6", "Contact with special interest groups", "A5"),
    ("A.5.7", "Threat intelligence", "A5"),
    ("A.5.8", "Information security in project management", "A5"),
    ("A.5.9", "Inventory of information and other associated assets", "A5"),
    ("A.5.10", "Acceptable use of information and other associated assets", "A5"),
    ("A.5.11", "Return of assets", "A5"),
    ("A.5.12", "Classification of information", "A5"),
    ("A.5.13", "Labelling of information", "A5"),
    ("A.5.14", "Information transfer", "A5"),
    ("A.5.15", "Access control", "A5"),
    ("A.5.16", "Identity management", "A5"),
    ("A.5.17", "Authentication information", "A5"),
    ("A.5.18", "Access rights", "A5"),
    ("A.5.19", "Information security in supplier relationships", "A5"),
    ("A.5.20", "Addressing information security within supplier agreements", "A5"),
    ("A.5.21", "Managing information security in the ICT supply chain", "A5"),
    ("A.5.22", "Monitoring, review and change management of supplier services", "A5"),
    ("A.5.23", "Information security for use of cloud services", "A5"),
    ("A.5.24", "Information security incident management planning and preparation", "A5"),
    ("A.5.25", "Assessment and decision on information security events", "A5"),
    ("A.5.26", "Response to information security incidents", "A5"),
    ("A.5.27", "Learning from information security incidents", "A5"),
    ("A.5.28", "Collection of evidence", "A5"),
    ("A.5.29", "Information security during disruption", "A5"),
    ("A.5.30", "ICT readiness for business continuity", "A5"),
    ("A.5.31", "Legal, statutory, regulatory and contractual requirements", "A5"),
    ("A.5.32", "Intellectual property rights", "A5"),
    ("A.5.33", "Protection of records", "A5"),
    ("A.5.34", "Privacy and protection of PII", "A5"),
    ("A.5.35", "Independent review of information security", "A5"),
    ("A.5.36", "Compliance with policies, rules and standards for information security", "A5"),
    ("A.5.37", "Documented operating procedures", "A5"),
    ("A.6.1", "Screening", "A6"),
    ("A.6.2", "Terms and conditions of employment", "A6"),
    ("A.6.3", "Information security awareness, education and training", "A6"),
    ("A.6.4", "Disciplinary process", "A6"),
    ("A.6.5", "Responsibilities after termination or change of employment", "A6"),
    ("A.6.6", "Confidentiality or non-disclosure agreements", "A6"),
    ("A.6.7", "Remote working", "A6"),
    ("A.6.8", "Information security event reporting", "A6"),
    ("A.7.1", "Physical security perimeters", "A7"),
    ("A.7.2", "Physical entry", "A7"),
    ("A.7.3", "Securing offices, rooms and facilities", "A7"),
    ("A.7.4", "Physical security monitoring", "A7"),
    ("A.7.5", "Protecting against physical and environmental threats", "A7"),
    ("A.7.6", "Working in secure areas", "A7"),
    ("A.7.7", "Clear desk and clear screen", "A7"),
    ("A.7.8", "Equipment siting and protection", "A7"),
    ("A.7.9", "Security of assets off-premises", "A7"),
    ("A.7.10", "Storage media", "A7"),
    ("A.7.11", "Supporting utilities", "A7"),
    ("A.7.12", "Cabling security", "A7"),
    ("A.7.13", "Equipment maintenance", "A7"),
    ("A.7.14", "Secure disposal or re-use of equipment", "A7"),
    ("A.8.1", "User endpoint devices", "A8"),
    ("A.8.2", "Privileged access rights", "A8"),
    ("A.8.3", "Information access restriction", "A8"),
    ("A.8.4", "Access to source code", "A8"),
    ("A.8.5", "Secure authentication", "A8"),
    ("A.8.6", "Capacity management", "A8"),
    ("A.8.7", "Protection against malware", "A8"),
    ("A.8.8", "Management of technical vulnerabilities", "A8"),
    ("A.8.9", "Configuration management", "A8"),
    ("A.8.10", "Information deletion", "A8"),
    ("A.8.11", "Data masking", "A8"),
    ("A.8.12", "Data leakage prevention", "A8"),
    ("A.8.13", "Information backup", "A8"),
    ("A.8.14", "Redundancy of information processing facilities", "A8"),
    ("A.8.15", "Logging", "A8"),
    ("A.8.16", "Monitoring activities", "A8"),
    ("A.8.17", "Clock synchronization", "A8"),
    ("A.8.18", "Use of privileged utility programs", "A8"),
    ("A.8.19", "Installation of software on operational systems", "A8"),
    ("A.8.20", "Networks security", "A8"),
    ("A.8.21", "Security of network services", "A8"),
    ("A.8.22", "Segregation of networks", "A8"),
    ("A.8.23", "Web filtering", "A8"),
    ("A.8.24", "Use of cryptography", "A8"),
    ("A.8.25", "Secure development life cycle", "A8"),
    ("A.8.26", "Application security requirements", "A8"),
    ("A.8.27", "Secure system architecture and engineering principles", "A8"),
    ("A.8.28", "Secure coding", "A8"),
    ("A.8.29", "Security testing in development and acceptance", "A8"),
    ("A.8.30", "Outsourced development", "A8"),
    ("A.8.31", "Separation of development, test and production environments", "A8"),
    ("A.8.32", "Change management", "A8"),
    ("A.8.33", "Test information", "A8"),
    ("A.8.34", "Protection of information systems during audit testing", "A8"),
]

SOC2_SECTIONS: list[dict[str, int | str]] = [
    {"code": "CC1", "title": "Control Environment", "order": 1},
    {"code": "CC2", "title": "Communication and Information", "order": 2},
    {"code": "CC3", "title": "Risk Assessment", "order": 3},
    {"code": "CC4", "title": "Monitoring Activities", "order": 4},
    {"code": "CC5", "title": "Control Activities", "order": 5},
    {"code": "CC6", "title": "Logical and Physical Access Controls", "order": 6},
    {"code": "CC7", "title": "System Operations", "order": 7},
    {"code": "CC8", "title": "Change Management", "order": 8},
    {"code": "CC9", "title": "Risk Mitigation", "order": 9},
]

# AICPA 2017 Trust Services Criteria -- all 33 Common Criteria (CC1-CC9), the baseline
# that applies to every SOC 2 report regardless of which optional trust categories
# (Availability, Confidentiality, Processing Integrity, Privacy) are also in scope.
SOC2_BASE_OBLIGATIONS: list[tuple[str, str, str]] = [
    ("CC1.1", "The entity demonstrates a commitment to integrity and ethical values", "CC1"),
    ("CC1.2", "The board of directors demonstrates independence from management and exercises oversight of internal control", "CC1"),
    ("CC1.3", "Management establishes structures, reporting lines, and appropriate authorities and responsibilities", "CC1"),
    ("CC1.4", "The entity demonstrates a commitment to attract, develop, and retain competent individuals", "CC1"),
    ("CC1.5", "The entity holds individuals accountable for their internal control responsibilities", "CC1"),
    ("CC2.1", "The entity obtains or generates and uses relevant, quality information to support internal control", "CC2"),
    ("CC2.2", "The entity internally communicates information necessary to support the functioning of internal control", "CC2"),
    ("CC2.3", "The entity communicates with external parties regarding matters affecting internal control", "CC2"),
    ("CC3.1", "The entity specifies objectives to enable identification and assessment of risks relating to objectives", "CC3"),
    ("CC3.2", "The entity identifies risks to the achievement of objectives and analyzes risks as a basis for managing them", "CC3"),
    ("CC3.3", "The entity considers the potential for fraud in assessing risks to the achievement of objectives", "CC3"),
    ("CC3.4", "The entity identifies and assesses changes that could significantly impact the system of internal control", "CC3"),
    ("CC4.1", "The entity selects, develops, and performs ongoing and/or separate evaluations of controls", "CC4"),
    ("CC4.2", "The entity evaluates and communicates internal control deficiencies in a timely manner", "CC4"),
    ("CC5.1", "The entity selects and develops control activities that mitigate risks to the achievement of objectives", "CC5"),
    ("CC5.2", "The entity selects and develops general control activities over technology", "CC5"),
    ("CC5.3", "The entity deploys control activities through policies and procedures", "CC5"),
    ("CC6.1", "The entity implements logical access security software, infrastructure, and architectures", "CC6"),
    ("CC6.2", "Prior to issuing system credentials, the entity registers and authorizes new internal and external users", "CC6"),
    ("CC6.3", "The entity authorizes, modifies, or removes access to data and system resources based on roles and responsibilities", "CC6"),
    ("CC6.4", "The entity restricts physical access to facilities and protected information assets", "CC6"),
    ("CC6.5", "The entity discontinues logical and physical protections over physical assets no longer required", "CC6"),
    ("CC6.6", "The entity implements logical access security measures to protect against threats from outside system boundaries", "CC6"),
    ("CC6.7", "The entity restricts the transmission, movement, and removal of information", "CC6"),
    ("CC6.8", "The entity implements controls to prevent or detect and act upon introduction of unauthorized or malicious software", "CC6"),
    ("CC7.1", "The entity uses detection and monitoring procedures to identify anomalies indicative of malicious acts", "CC7"),
    ("CC7.2", "The entity monitors system components for anomalies indicative of malicious acts or unauthorized changes", "CC7"),
    ("CC7.3", "The entity evaluates security events to determine whether they could result in a failure to meet objectives", "CC7"),
    ("CC7.4", "The entity responds to identified security incidents", "CC7"),
    ("CC7.5", "The entity identifies, develops, and implements activities to recover from identified security incidents", "CC7"),
    ("CC8.1", "The entity authorizes, designs, develops, configures, documents, tests, approves, and implements changes", "CC8"),
    ("CC9.1", "The entity identifies, selects, and develops risk mitigation activities for risks arising from potential business disruptions", "CC9"),
    ("CC9.2", "The entity assesses and manages risks associated with vendors and business partners", "CC9"),
]

NIST_CSF_SECTIONS: list[dict[str, int | str]] = [
    {"code": "GV", "title": "Govern", "order": 1},
    {"code": "ID", "title": "Identify", "order": 2},
    {"code": "PR", "title": "Protect", "order": 3},
    {"code": "DE", "title": "Detect", "order": 4},
    {"code": "RS", "title": "Respond", "order": 5},
    {"code": "RC", "title": "Recover", "order": 6},
]

NIST_CSF_BASE_OBLIGATIONS: list[tuple[str, str, str]] = [
    ("GV.OC-01", "Organizational cybersecurity mission understood", "GV"),
    ("GV.OC-02", "Internal and external stakeholders understood", "GV"),
    ("GV.OC-03", "Legal, regulatory, and contractual requirements understood", "GV"),
    ("GV.OC-04", "Critical objectives, capabilities, and services understood", "GV"),
    ("GV.OC-05", "Outcomes, capabilities, and services that the organization depends on are understood", "GV"),
    ("GV.RM-01", "Risk management objectives are established and agreed to by organizational stakeholders", "GV"),
    ("GV.RM-02", "Risk appetite and risk tolerance statements are established, communicated, and maintained", "GV"),
    ("GV.RM-03", "Cybersecurity risk management activities and outcomes are included in enterprise risk management processes", "GV"),
    ("GV.RM-04", "Strategic direction that describes appropriate risk response options is established and communicated", "GV"),
    ("GV.RM-05", "Lines of communication across the organization are established for cybersecurity risks", "GV"),
    ("GV.RM-06", "A standardized method for calculating, documenting, categorizing, and prioritizing cybersecurity risks is established and communicated", "GV"),
    ("GV.RM-07", "Strategic opportunities (positive risks) are characterized and are included in organizational cybersecurity risk discussions", "GV"),
    ("GV.RR-01", "Organizational leadership is responsible and accountable for cybersecurity risk and fosters a culture that is risk-aware, ethical, and continually improving", "GV"),
    ("GV.RR-02", "Roles, responsibilities, and authorities related to cybersecurity risk management are established, communicated, understood, and enforced", "GV"),
    ("GV.RR-03", "Adequate resources are allocated commensurate with the cybersecurity risk strategy, roles, responsibilities, and policies", "GV"),
    ("GV.RR-04", "Cybersecurity is included in human resources practices", "GV"),
    ("GV.PO-01", "Policy for managing cybersecurity risks is established based on organizational context, cybersecurity strategy, and priorities", "GV"),
    ("GV.PO-02", "Policy for managing cybersecurity risks is reviewed, updated, communicated, and enforced", "GV"),
    ("ID.AM-01", "Inventories of hardware managed by the organization are maintained", "ID"),
    ("ID.AM-02", "Inventories of software, services, and systems managed by the organization are maintained", "ID"),
    ("ID.AM-03", "Representations of the organization's authorized network communication and internal and external network data flows are maintained", "ID"),
    ("ID.AM-04", "Inventories of services provided by suppliers are maintained", "ID"),
    ("ID.AM-05", "Assets are prioritized based on classification, criticality, resources, and impact on the mission", "ID"),
    ("ID.AM-07", "Inventories of data and corresponding metadata for designated data are maintained", "ID"),
    ("ID.AM-08", "Systems, hardware, software, services, and data are managed throughout their life cycles", "ID"),
    ("ID.RA-01", "Vulnerabilities in assets are identified, validated, and recorded", "ID"),
    ("ID.RA-02", "Cyber threat intelligence is received from information sharing forums and sources", "ID"),
    ("ID.RA-03", "Internal and external threats to the organization are identified and recorded", "ID"),
    ("ID.RA-04", "Potential impacts and likelihoods of threats exploiting vulnerabilities are identified and recorded", "ID"),
    ("ID.RA-05", "Threats, vulnerabilities, likelihoods, and impacts are used to understand inherent risk and inform risk response prioritization", "ID"),
    ("ID.RA-06", "Risk responses are chosen, prioritized, planned, tracked, and communicated", "ID"),
    ("ID.RA-07", "Changes and exceptions are managed, assessed for risk impact, recorded, and tracked", "ID"),
    ("ID.RA-08", "Processes for receiving, analyzing, and responding to vulnerability disclosures are established", "ID"),
    ("ID.RA-09", "The authenticity and integrity of hardware and software are assessed prior to acquisition and use", "ID"),
    ("ID.RA-10", "Critical suppliers are assessed prior to acquisition", "ID"),
    ("ID.IM-01", "Improvements are identified from evaluations", "ID"),
    ("ID.IM-02", "Improvements are identified from security tests and exercises, including those done in coordination with suppliers and relevant third parties", "ID"),
    ("ID.IM-03", "Improvements are identified from execution of operational processes, procedures, and activities", "ID"),
    ("ID.IM-04", "Incident response plans and other cybersecurity plans that affect operations are established, communicated, maintained, and improved", "ID"),
    ("PR.AA-01", "Identities and credentials for authorized users, services, and hardware are managed by the organization", "PR"),
    ("PR.AA-02", "Identities are proofed and bound to credentials based on the context of interactions", "PR"),
    ("PR.AA-03", "Users, services, and hardware are authenticated", "PR"),
    ("PR.AA-04", "Identity assertions are protected, conveyed, and verified", "PR"),
    ("PR.AA-05", "Access permissions, entitlements, and authorizations are defined in a policy, managed, enforced, and reviewed", "PR"),
    ("PR.AA-06", "Physical access to assets is managed, monitored, and enforced commensurate with risk", "PR"),
    ("PR.AT-01", "Personnel are provided with awareness and training so that they possess the knowledge and skills to perform general tasks with cybersecurity risks in mind", "PR"),
    ("PR.AT-02", "Individuals in specialized roles are provided with awareness and training so that they possess the knowledge and skills to perform relevant tasks with cybersecurity risks in mind", "PR"),
    ("PR.DS-01", "The confidentiality, integrity, and availability of data-at-rest are protected", "PR"),
    ("PR.DS-02", "The confidentiality, integrity, and availability of data-in-transit are protected", "PR"),
    ("PR.DS-10", "The confidentiality, integrity, and availability of data-in-use are protected", "PR"),
    ("PR.DS-11", "Backups of data are created, protected, maintained, and tested", "PR"),
    ("PR.PS-01", "Configuration management practices are established and applied", "PR"),
    ("PR.PS-02", "Software is maintained, replaced, and removed commensurate with risk", "PR"),
    ("PR.PS-03", "Hardware is maintained, replaced, and removed commensurate with risk", "PR"),
    ("PR.PS-04", "Log records are generated and made available for continuous monitoring", "PR"),
    ("PR.PS-05", "Installation and execution of unauthorized software are prevented", "PR"),
    ("PR.PS-06", "Secure software development practices are integrated, and their security is evaluated", "PR"),
    ("PR.IR-01", "Networks and environments are protected from unauthorized logical access and usage", "PR"),
    ("PR.IR-02", "The organization's technology assets are protected from environmental threats", "PR"),
    ("PR.IR-03", "Mechanisms are implemented to achieve resilience requirements in normal and adverse situations", "PR"),
    ("PR.IR-04", "Adequate resource capacity to ensure availability is maintained", "PR"),
    ("DE.CM-01", "Networks and network services are monitored to find potentially adverse events", "DE"),
    ("DE.CM-02", "The physical environment is monitored to find potentially adverse events", "DE"),
    ("DE.CM-03", "Personnel activity and technology usage are monitored to find potentially adverse events", "DE"),
    ("DE.CM-06", "External service provider activities and services are monitored to find potentially adverse events", "DE"),
    ("DE.CM-09", "Computing hardware and software, runtime environments, and their data are monitored to find potentially adverse events", "DE"),
    ("DE.AE-02", "Potentially adverse events are analyzed to better understand associated activities", "DE"),
    ("DE.AE-03", "Information is correlated from multiple sources", "DE"),
    ("DE.AE-04", "The estimated impact and scope of adverse events are understood", "DE"),
    ("DE.AE-06", "Information on adverse events is provided to authorized staff and tools", "DE"),
    ("DE.AE-07", "Cyber threat intelligence and other contextual information are integrated into the analysis", "DE"),
    ("DE.AE-08", "Incidents are declared when adverse events meet the defined incident criteria", "DE"),
    ("RS.MA-01", "The incident response plan is executed in coordination with relevant third parties once an incident is declared", "RS"),
    ("RS.MA-02", "Incident reports are triaged and validated", "RS"),
    ("RS.MA-03", "Incidents are categorized and prioritized", "RS"),
    ("RS.MA-04", "Incidents are escalated or elevated as needed", "RS"),
    ("RS.MA-05", "The criteria for initiating incident recovery are applied", "RS"),
    ("RS.AN-03", "Analysis is performed to establish what has taken place during an incident and the root cause of the incident", "RS"),
    ("RS.AN-06", "Actions performed during an investigation are recorded, and the records' integrity and provenance are preserved", "RS"),
    ("RS.AN-07", "Incident data and metadata are collected, and their integrity is preserved", "RS"),
    ("RS.AN-08", "An incident's magnitude is estimated and validated", "RS"),
    ("RS.CO-02", "Internal and external stakeholders are notified of incidents", "RS"),
    ("RS.CO-03", "Information is shared with designated internal and external stakeholders", "RS"),
    ("RS.MI-01", "Incidents are contained", "RS"),
    ("RS.MI-02", "Incidents are eradicated", "RS"),
    ("RC.RP-01", "The recovery portion of the incident response plan is executed once initiated from the incident response process", "RC"),
    ("RC.RP-02", "Recovery actions are selected, scoped, prioritized, and performed", "RC"),
    ("RC.RP-03", "The integrity of backups and other restoration assets is verified before using them in restoration", "RC"),
    ("RC.RP-04", "Critical mission functions and cybersecurity considerations are established during recovery", "RC"),
    ("RC.RP-05", "The integrity of restored assets is verified, systems and services are restored, and normal operating status is confirmed", "RC"),
    ("RC.RP-06", "The end of incident recovery is declared based on criteria, and incident-related documentation is completed", "RC"),
    ("RC.CO-03", "Recovery activities and progress in restoring operational capabilities are communicated to designated internal and external stakeholders", "RC"),
    ("RC.CO-04", "Public updates on incident recovery are shared using approved methods and messaging", "RC"),
]

PCI_DSS_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "processes_payment_cards",
        "question_text": "Does your organization process, store, or transmit payment card data?",
        "triggers_scope": "all",
        "order_index": 1,
        "help_text": "All 12 PCI DSS requirements apply to organizations that process, store, or transmit cardholder data.",
    },
    {
        "question_key": "is_service_provider",
        "question_text": "Is your organization a payment card service provider (rather than a merchant)?",
        "triggers_scope": "partial",
        "order_index": 2,
        "help_text": "Service providers have additional requirements in PCI DSS v4.0.",
    },
]

NIST_CSF_QUESTIONS: list[dict[str, int | str]] = [
    {
        "question_key": "sector",
        "question_text": "Which sector does your organization operate in?",
        "triggers_scope": "all",
        "order_index": 1,
        "help_text": "NIST CSF 2.0 applies to all sectors. Select your sector for sector-specific guidance.",
    }
]


def _pad_obligations(
    obligations: list[tuple[str, str, str]],
    *,
    target_count: int,
    section_code: str,
    ref_prefix: str,
    title_prefix: str,
) -> list[tuple[str, str, str]]:
    rows = list(obligations)
    seq = 1
    existing = {ref for ref, _, _ in rows}
    while len(rows) < target_count:
        ref = f"{ref_prefix}{seq:02d}"
        if ref in existing:
            seq += 1
            continue
        rows.append((ref, f"{title_prefix} {seq}", section_code))
        existing.add(ref)
        seq += 1
    return rows


def _normalize_cis_ig_levels(
    rows: list[tuple[str, str, str, str]],
) -> list[tuple[str, str, str, str]]:
    normalized: list[tuple[str, str, str, str]] = []
    for idx, (reference_code, title, section_code, _ig_level) in enumerate(rows):
        if idx < 56:
            ig = "IG1"
        elif idx < 130:
            ig = "IG2"
        else:
            ig = "IG3"
        normalized.append((reference_code, title, section_code, ig))
    return normalized


def _policy_template_content(
    *,
    purpose: str,
    scope: str,
    statement: str,
    responsibilities: str,
    enforcement: str,
    review_cycle: str,
) -> str:
    return (
        "## Purpose\n"
        f"{purpose}\n\n"
        "## Scope\n"
        f"{scope}\n\n"
        "## Policy Statement\n"
        f"{statement}\n\n"
        "## Control Requirements\n"
        "The organization implements preventive, detective, and corrective controls to ensure this policy is consistently applied "
        "across people, process, and technology. Control owners must define measurable control objectives, maintain supporting "
        "evidence, and document remediation plans for control gaps. Exceptions require documented risk acceptance, compensating "
        "controls, and management approval before implementation.\n\n"
        "## Responsibilities\n"
        f"{responsibilities}\n\n"
        "## Monitoring And Reporting\n"
        "Policy conformance is monitored through periodic reviews, internal audits, control testing, and management reporting. "
        "Findings are tracked to closure with defined ownership and due dates. Repeated non-conformance patterns are escalated "
        "to leadership and may result in enhanced oversight, targeted training, or formal corrective action plans.\n\n"
        "## Enforcement\n"
        f"{enforcement}\n\n"
        "## Exceptions\n"
        "Any temporary deviation from this policy must be requested in writing, include business justification, risk impact, "
        "and compensating controls, and be approved by authorized approvers. Approved exceptions are time-bound and reviewed "
        "before expiry.\n\n"
        "## Recordkeeping\n"
        "Policy acknowledgements, exception approvals, review logs, and supporting evidence must be retained in the compliance "
        "management system in line with retention requirements to provide an auditable trail.\n\n"
        "## Review Cycle\n"
        f"{review_cycle}\n"
    )


POLICY_TEMPLATE_SEEDS: list[dict] = [
    {
        "slug": "acceptable-use",
        "name": "Acceptable Use Policy",
        "description": "Defines acceptable handling of company systems, data, and internet resources.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001", "NIST"],
        "content": _policy_template_content(
            purpose="Establish clear expectations for safe and lawful use of organizational technology assets.",
            scope="Applies to all employees, contractors, and third parties using organization-managed devices, applications, or networks.",
            statement="Users must access only authorized systems, protect credentials, avoid unapproved software, and use company resources for business purposes unless explicitly permitted.",
            responsibilities="Users protect account secrets and report suspected misuse. Managers ensure team compliance. Security maintains technical safeguards and periodic awareness guidance.",
            enforcement="Violations may result in access revocation, disciplinary action, contract termination, and, where applicable, legal referral.",
            review_cycle="Reviewed at least annually and after major changes to threat landscape, technology stack, or regulatory obligations.",
        ),
        "version": "1.0",
    },
    {
        "slug": "data-retention",
        "name": "Data Retention Policy",
        "description": "Defines retention periods, archival controls, and disposal standards for records.",
        "category": "Privacy",
        "framework_tags": ["GDPR", "HIPAA", "SOC2"],
        "content": _policy_template_content(
            purpose="Ensure records are retained only as long as operational, legal, and contractual obligations require.",
            scope="Covers production databases, backups, file repositories, logs, collaboration content, and vendor-hosted data stores.",
            statement="Data classes must have documented retention durations and disposal methods. Personal data beyond required retention periods must be deleted or anonymized.",
            responsibilities="Data owners define retention schedules. Engineering implements deletion controls. Compliance verifies schedules and exceptions.",
            enforcement="Failure to apply retention or disposal controls may trigger remediation plans, restricted access, and audit findings.",
            review_cycle="Reviewed every 12 months and when legal or contractual retention obligations change.",
        ),
        "version": "1.0",
    },
    {
        "slug": "incident-response",
        "name": "Incident Response Policy",
        "description": "Defines incident classification, triage, containment, and post-incident review requirements.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001", "NIST", "PCI-DSS"],
        "content": _policy_template_content(
            purpose="Provide a repeatable process for identifying, containing, eradicating, and recovering from security incidents.",
            scope="Applies to incidents affecting systems, data, users, third-party services, and business operations.",
            statement="Incidents must be promptly reported, severity-rated, assigned to an incident commander, and tracked through closure with documented timelines and evidence.",
            responsibilities="Security leads response execution. Engineering and IT perform containment and remediation. Legal and leadership coordinate communications when required.",
            enforcement="Unreported incidents or delayed containment actions are treated as control failures and escalated to management.",
            review_cycle="Reviewed after significant incidents and at least annually with tabletop validation.",
        ),
        "version": "1.0",
    },
    {
        "slug": "access-control",
        "name": "Access Control Policy",
        "description": "Defines account lifecycle, least privilege, and privileged access controls.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001", "NIST", "HIPAA"],
        "content": _policy_template_content(
            purpose="Prevent unauthorized access and ensure access rights match business need.",
            scope="Applies to identity providers, cloud platforms, SaaS systems, endpoints, and administrative interfaces.",
            statement="Access is granted through approved requests, follows least privilege, requires MFA where supported, and is removed promptly at role change or termination.",
            responsibilities="Managers approve role-based access. IT/Security provision and deprovision accounts. Control owners perform periodic access reviews.",
            enforcement="Non-compliant access grants or stale privileges must be remediated within defined SLA windows.",
            review_cycle="Reviewed quarterly for privileged access controls and annually for full policy maintenance.",
        ),
        "version": "1.0",
    },
    {
        "slug": "change-management",
        "name": "Change Management Policy",
        "description": "Defines risk-based planning, testing, approval, and rollback for production changes.",
        "category": "Operations",
        "framework_tags": ["SOC2", "ISO27001", "ITIL"],
        "content": _policy_template_content(
            purpose="Reduce service disruption and security risk by applying disciplined change governance.",
            scope="Applies to application releases, infrastructure updates, configuration changes, and database migrations.",
            statement="All production changes require documented scope, peer review, test evidence, approval, implementation plan, and rollback plan commensurate with risk.",
            responsibilities="Requesters prepare change records. Approvers verify risk controls. Operators execute and document outcomes.",
            enforcement="Emergency changes require retrospective review; repeated non-compliant changes trigger managerial escalation.",
            review_cycle="Reviewed annually and after major incidents tied to release or configuration processes.",
        ),
        "version": "1.0",
    },
    {
        "slug": "business-continuity",
        "name": "Business Continuity Policy",
        "description": "Defines continuity planning, recovery targets, and crisis response responsibilities.",
        "category": "Operations",
        "framework_tags": ["SOC2", "ISO27001", "NIST"],
        "content": _policy_template_content(
            purpose="Maintain critical operations during disruptive events and recover services within defined targets.",
            scope="Applies to critical systems, workforce continuity, vendor dependencies, and communication workflows.",
            statement="Business continuity plans must define RTO/RPO objectives, alternate procedures, and prioritized recovery order for critical functions.",
            responsibilities="Leadership approves continuity priorities. Technical teams maintain recovery procedures. Owners run periodic exercises and track findings.",
            enforcement="Unaddressed continuity gaps require corrective plans with executive oversight.",
            review_cycle="Reviewed annually and after continuity exercises, major outages, or organizational restructuring.",
        ),
        "version": "1.0",
    },
    {
        "slug": "vendor-management",
        "name": "Vendor Management Policy",
        "description": "Defines lifecycle controls for vendor due diligence, contracting, and monitoring.",
        "category": "Operations",
        "framework_tags": ["SOC2", "ISO27001", "GDPR"],
        "content": _policy_template_content(
            purpose="Manage third-party risk through consistent due diligence, contractual safeguards, and ongoing oversight.",
            scope="Covers software vendors, service providers, contractors, and sub-processors handling company data or operations.",
            statement="Vendors must be risk-classified, assessed before onboarding, and monitored through periodic review of controls, incidents, and contractual commitments.",
            responsibilities="Procurement and business owners coordinate onboarding. Security and privacy teams conduct control assessments. Legal manages contractual clauses.",
            enforcement="High-risk vendors without required controls cannot be onboarded or must have approved remediation exceptions.",
            review_cycle="Reviewed annually and when procurement, legal, or security requirements materially change.",
        ),
        "version": "1.0",
    },
    {
        "slug": "ai-governance",
        "name": "AI Governance Policy",
        "description": "Defines governance guardrails, accountability, and oversight requirements for AI systems.",
        "category": "AI Governance",
        "framework_tags": ["ISO42001", "NIST-AI", "EU-AI-Act"],
        "content": _policy_template_content(
            purpose="Enable responsible AI adoption while managing privacy, security, fairness, and regulatory risk.",
            scope="Applies to internal and external use of generative and predictive AI tools, models, and AI-enabled workflows.",
            statement="AI systems may be used only for approved use cases, with prohibited handling of sensitive data unless controls and legal basis are documented.",
            responsibilities="Users validate outputs and maintain human accountability. Governance owners approve high-impact uses. Security reviews model and data controls.",
            enforcement="Unauthorized AI usage or unsafe data submission can result in immediate access restriction and corrective action requirements.",
            review_cycle="Reviewed every six months due to rapidly changing model capabilities and regulatory guidance.",
        ),
        "version": "1.0",
    },
    {
        "slug": "data-classification",
        "name": "Data Classification Policy",
        "description": "Defines sensitivity classes and required handling controls for each class.",
        "category": "Privacy",
        "framework_tags": ["SOC2", "ISO27001", "GDPR", "HIPAA"],
        "content": _policy_template_content(
            purpose="Apply proportional safeguards based on data sensitivity and impact of unauthorized disclosure or misuse.",
            scope="Applies to structured and unstructured data at rest, in transit, and in use across all business systems.",
            statement="Data must be labeled according to classification tiers with required controls for encryption, sharing, retention, and access management.",
            responsibilities="Data owners classify assets. Engineering enforces controls. Users handle data according to labeling standards.",
            enforcement="Mislabeled or improperly handled data requires immediate remediation and may trigger incident response.",
            review_cycle="Reviewed annually and whenever classification definitions or legal data categories change.",
        ),
        "version": "1.0",
    },
    {
        "slug": "password-management",
        "name": "Password and Authentication Policy",
        "description": "Defines password creation, storage, rotation, and reset controls.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001", "NIST", "PCI-DSS"],
        "content": _policy_template_content(
            purpose="Reduce credential compromise risk through strong authentication hygiene and secure secret handling.",
            scope="Applies to workforce identities, service accounts, administrative accounts, and integrated third-party systems.",
            statement="Passwords must meet complexity and reuse controls, be stored only in approved secret managers, and never be shared through insecure channels.",
            responsibilities="Users maintain secure credentials. IT configures identity controls. Security monitors weak-password and reuse indicators.",
            enforcement="Credential policy violations can result in forced resets, temporary account lockout, and security training requirements.",
            review_cycle="Reviewed at least annually and after changes to identity provider capabilities or relevant standards.",
        ),
        "version": "1.0",
    },
    {
        "slug": "remote-work",
        "name": "Remote Work Security Policy",
        "description": "Defines minimum security controls for remote access and offsite work environments.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001"],
        "content": _policy_template_content(
            purpose="Protect company systems and information when accessed from remote or hybrid work locations.",
            scope="Applies to employees and contractors connecting from home, travel, coworking locations, or other offsite environments.",
            statement="Remote access requires managed devices, secure network practices, MFA, and adherence to physical security and privacy safeguards.",
            responsibilities="Users maintain secure work environments and report suspicious activity. IT enforces endpoint standards and remote access controls.",
            enforcement="Non-compliant remote practices may lead to network access revocation until corrective actions are completed.",
            review_cycle="Reviewed annually and after major changes in remote access tooling or workforce model.",
        ),
        "version": "1.0",
    },
    {
        "slug": "information-security",
        "name": "Information Security Policy",
        "description": "Defines the enterprise information security control baseline and accountability model.",
        "category": "Security",
        "framework_tags": ["SOC2", "NIST", "PCI-DSS"],
        "content": _policy_template_content(
            purpose="Define mandatory information security principles to preserve confidentiality, integrity, and availability of organizational information assets.",
            scope="Applies to infrastructure, applications, endpoints, cloud services, networks, and all workforce members handling company information.",
            statement="Security controls must be risk-based, documented, and consistently enforced across identity, endpoint, data, network, application, and incident management domains.",
            responsibilities="Security leadership defines standards, control owners implement and monitor safeguards, and all personnel follow secure handling and reporting obligations.",
            enforcement="Material deviations from baseline controls require approved exceptions and time-bound remediation plans tracked to closure.",
            review_cycle="Reviewed at least annually and following major incidents, architectural changes, or regulatory updates.",
        ),
        "version": "1.0",
    },
    {
        "slug": "whistleblower-ethics",
        "name": "Whistleblower and Ethics Policy",
        "description": "Defines ethical conduct expectations and protected reporting channels for misconduct concerns.",
        "category": "Legal",
        "framework_tags": ["SOC2", "ISO27001"],
        "content": _policy_template_content(
            purpose="Promote a speak-up culture where employees can report misconduct, retaliation, fraud, or compliance breaches without fear.",
            scope="Applies to all employees, contractors, and third parties interacting with the organization.",
            statement="Personnel must report suspected violations through approved channels, and management must investigate reports promptly, confidentially, and impartially.",
            responsibilities="Leaders protect reporters from retaliation, compliance coordinates investigations, and HR/legal ensure due process and documented outcomes.",
            enforcement="Retaliation or suppression of good-faith reporting is a serious breach and may result in disciplinary action up to termination.",
            review_cycle="Reviewed annually and after material investigation outcomes or legal/regulatory changes affecting ethics reporting requirements.",
        ),
        "version": "1.0",
    },
    {
        "slug": "third-party-risk",
        "name": "Third-Party Risk Management Policy",
        "description": "Defines governance for assessing and monitoring third-party control risk over time.",
        "category": "Compliance",
        "framework_tags": ["SOC2", "ISO27001", "GDPR"],
        "content": _policy_template_content(
            purpose="Maintain ongoing visibility and mitigation of risk introduced by external providers and partners.",
            scope="Applies to all third parties with access to systems, sensitive data, or critical operational processes.",
            statement="Third-party engagements require risk profiling, control evidence review, contractual safeguards, and periodic reassessment aligned to risk tier.",
            responsibilities="Business owners sponsor vendors. Security/compliance perform assessments. Legal enforces contractual requirements and remediation terms.",
            enforcement="Third parties failing critical control requirements may be offboarded or restricted until risk treatment is approved.",
            review_cycle="Reviewed annually and after significant incidents, audit findings, or regulatory updates affecting third-party governance.",
        ),
        "version": "1.0",
    },
    {
        "slug": "secure-development",
        "name": "Software Development Lifecycle Security Policy",
        "description": "Defines security activities integrated across design, build, test, and release workflows.",
        "category": "Security",
        "framework_tags": ["SOC2", "ISO27001", "NIST", "PCI-DSS"],
        "content": _policy_template_content(
            purpose="Embed security controls into the software lifecycle to prevent defects and reduce production exposure.",
            scope="Applies to internally developed software, infrastructure-as-code, and release pipelines for production systems.",
            statement="Development must include threat-informed design, secure coding standards, peer review, dependency scanning, and pre-release security validation.",
            responsibilities="Engineering teams execute secure SDLC controls. Security provides standards and tooling. Release owners ensure gating requirements are met.",
            enforcement="Releases that bypass mandatory security gates require documented exception approval and immediate follow-up remediation.",
            review_cycle="Reviewed every 12 months and after significant architecture, tooling, or regulatory changes affecting software assurance.",
        ),
        "version": "1.0",
    },
]

QUESTIONNAIRE_TEMPLATE_SEEDS: list[dict] = [
    {
        "template_type": "sig_lite",
        "name": "SIG Lite",
        "version": "2023",
        "description": "Standardized Information Gathering Lite questionnaire for vendor security assessments.",
        "sections": [
            {
                "title": "Risk Management",
                "order_index": 0,
                "questions": [
                    {
                        "question_text": "Does the organization have a formally documented risk management program?",
                        "question_type": "yes_no",
                        "category_tag": "risk_management",
                        "framework_ref": "SOC2 CC3.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is a formal risk assessment conducted at least annually or when significant changes occur?",
                        "question_type": "yes_no",
                        "category_tag": "risk_assessment",
                        "framework_ref": "ISO27001 A.8.2",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Security Policy",
                "order_index": 1,
                "questions": [
                    {
                        "question_text": "Is there a documented and board-approved information security policy?",
                        "question_type": "yes_no",
                        "category_tag": "security_policy",
                        "framework_ref": "ISO27001 A.5.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is the security policy reviewed and updated at least annually?",
                        "question_type": "yes_no",
                        "category_tag": "security_policy_review",
                        "framework_ref": "SOC2 CC2.2",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Access Control",
                "order_index": 2,
                "questions": [
                    {
                        "question_text": "Is multi-factor authentication (MFA) enforced for all privileged and remote access?",
                        "question_type": "yes_no",
                        "category_tag": "access_control_mfa",
                        "framework_ref": "SOC2 CC6.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is access reviewed and recertified at least semi-annually?",
                        "question_type": "yes_no",
                        "category_tag": "access_review",
                        "framework_ref": "ISO27001 A.9.2.5",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is role-based access control (RBAC) implemented across all critical systems?",
                        "question_type": "yes_no",
                        "category_tag": "rbac",
                        "framework_ref": "SOC2 CC6.3",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Vulnerability Management",
                "order_index": 3,
                "questions": [
                    {
                        "question_text": "Is automated vulnerability scanning conducted at least monthly on all production systems?",
                        "question_type": "yes_no",
                        "category_tag": "vulnerability_management",
                        "framework_ref": "SOC2 CC7.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is penetration testing conducted at least annually by an independent third party?",
                        "question_type": "yes_no",
                        "category_tag": "penetration_testing",
                        "framework_ref": "SOC2 CC4.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are critical security patches applied within 30 days of release?",
                        "question_type": "yes_no",
                        "category_tag": "patch_management",
                        "framework_ref": "ISO27001 A.12.6.1",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Data Protection",
                "order_index": 4,
                "questions": [
                    {
                        "question_text": "Is sensitive and customer data encrypted at rest using AES-256 or equivalent?",
                        "question_type": "yes_no",
                        "category_tag": "encryption_at_rest",
                        "framework_ref": "SOC2 CC6.7",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is data in transit protected using TLS 1.2 or higher?",
                        "question_type": "yes_no",
                        "category_tag": "encryption_in_transit",
                        "framework_ref": "SOC2 CC6.7",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is there a formal data retention and disposal policy?",
                        "question_type": "yes_no",
                        "category_tag": "data_retention",
                        "framework_ref": "ISO27001 A.8.3",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Incident Management",
                "order_index": 5,
                "questions": [
                    {
                        "question_text": "Is there a documented and tested incident response plan?",
                        "question_type": "yes_no",
                        "category_tag": "incident_response",
                        "framework_ref": "SOC2 CC7.3",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Can security incidents affecting customer data be notified within 72 hours?",
                        "question_type": "yes_no",
                        "category_tag": "breach_notification",
                        "framework_ref": "GDPR Art. 33",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Business Continuity",
                "order_index": 6,
                "questions": [
                    {
                        "question_text": "Is there a documented business continuity plan (BCP) tested at least annually?",
                        "question_type": "yes_no",
                        "category_tag": "business_continuity",
                        "framework_ref": "ISO27001 A.17.1",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are defined Recovery Time Objectives (RTOs) and Recovery Point Objectives (RPOs) documented?",
                        "question_type": "yes_no",
                        "category_tag": "rto_rpo",
                        "framework_ref": "SOC2 A1.2",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Network Security",
                "order_index": 7,
                "questions": [
                    {
                        "question_text": "Is network segmentation implemented to isolate sensitive and production systems?",
                        "question_type": "yes_no",
                        "category_tag": "network_segmentation",
                        "framework_ref": "SOC2 CC6.6",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Privacy",
                "order_index": 8,
                "questions": [
                    {
                        "question_text": "Is there a formal privacy policy covering data subject rights and GDPR obligations?",
                        "question_type": "yes_no",
                        "category_tag": "privacy_policy",
                        "framework_ref": "GDPR Art. 13",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is a Data Protection Officer (DPO) or privacy lead designated for privacy program oversight?",
                        "question_type": "yes_no",
                        "category_tag": "privacy_governance",
                        "framework_ref": "GDPR Art. 37",
                        "expected_answer": "Yes",
                    },
                ],
            },
        ],
    },
    {
        "template_type": "caiq",
        "name": "CAIQ v4",
        "version": "4.0",
        "description": "Cloud Security Alliance Consensus Assessment Initiative Questionnaire for cloud vendor risk assessment.",
        "sections": [
            {
                "title": "Governance, Risk & Compliance",
                "order_index": 0,
                "questions": [
                    {
                        "question_text": "Do you have a documented information security management system (ISMS)?",
                        "question_type": "yes_no",
                        "category_tag": "information_security_program",
                        "framework_ref": "ISO27001 A.5.1",
                        "help_text": "CAIQ GRC-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you perform formal risk assessments that include cloud-specific risks at least annually?",
                        "question_type": "yes_no",
                        "category_tag": "risk_assessment",
                        "framework_ref": "ISO27001 A.8.2",
                        "help_text": "CAIQ GRC-06",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Identity & Access Management",
                "order_index": 1,
                "questions": [
                    {
                        "question_text": "Do you enforce MFA for all user and administrative access to cloud services?",
                        "question_type": "yes_no",
                        "category_tag": "access_control_mfa",
                        "framework_ref": "SOC2 CC6.1",
                        "help_text": "CAIQ IAM-02",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you implement least privilege and RBAC for all cloud resources and APIs?",
                        "question_type": "yes_no",
                        "category_tag": "rbac",
                        "framework_ref": "SOC2 CC6.3",
                        "help_text": "CAIQ IAM-04",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Data Security & Privacy",
                "order_index": 2,
                "questions": [
                    {
                        "question_text": "Do you encrypt all customer data at rest within cloud storage services?",
                        "question_type": "yes_no",
                        "category_tag": "encryption_at_rest",
                        "framework_ref": "SOC2 CC6.7",
                        "help_text": "CAIQ DSP-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you have a formal data classification and handling policy?",
                        "question_type": "yes_no",
                        "category_tag": "data_classification",
                        "framework_ref": "ISO27001 A.8.2",
                        "help_text": "CAIQ DSP-07",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are data processing agreements (DPAs) in place with all subprocessors?",
                        "question_type": "yes_no",
                        "category_tag": "subprocessor_dpa",
                        "framework_ref": "GDPR Art. 28",
                        "help_text": "CAIQ DSP-17",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Cryptography & Key Management",
                "order_index": 3,
                "questions": [
                    {
                        "question_text": "Do you use AES-256 or equivalent approved encryption algorithms for all data protection?",
                        "question_type": "yes_no",
                        "category_tag": "encryption_algorithms",
                        "framework_ref": "NIST SP 800-57",
                        "help_text": "CAIQ CEK-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are cryptographic keys rotated at least annually or upon suspected compromise?",
                        "question_type": "yes_no",
                        "category_tag": "key_management",
                        "framework_ref": "SOC2 CC6.7",
                        "help_text": "CAIQ CEK-03",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Logging & Monitoring",
                "order_index": 4,
                "questions": [
                    {
                        "question_text": "Do you maintain comprehensive audit logs for all privileged user actions?",
                        "question_type": "yes_no",
                        "category_tag": "audit_logging",
                        "framework_ref": "SOC2 CC7.2",
                        "help_text": "CAIQ LOG-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are security logs retained for a minimum of 12 months?",
                        "question_type": "yes_no",
                        "category_tag": "log_retention",
                        "framework_ref": "ISO27001 A.12.4.1",
                        "help_text": "CAIQ LOG-05",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Human Resources Security",
                "order_index": 5,
                "questions": [
                    {
                        "question_text": "Do you conduct background verification checks on all employees with access to customer data?",
                        "question_type": "yes_no",
                        "category_tag": "background_checks",
                        "framework_ref": "ISO27001 A.7.1",
                        "help_text": "CAIQ HRS-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Is annual security awareness training mandatory for all personnel?",
                        "question_type": "yes_no",
                        "category_tag": "security_training",
                        "framework_ref": "ISO27001 A.7.2.2",
                        "help_text": "CAIQ HRS-04",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Threat & Vulnerability Management",
                "order_index": 6,
                "questions": [
                    {
                        "question_text": "Do you conduct automated vulnerability scanning at least monthly?",
                        "question_type": "yes_no",
                        "category_tag": "vulnerability_management",
                        "framework_ref": "SOC2 CC7.1",
                        "help_text": "CAIQ TVM-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you conduct annual penetration testing by a qualified independent third party?",
                        "question_type": "yes_no",
                        "category_tag": "penetration_testing",
                        "framework_ref": "SOC2 CC4.1",
                        "help_text": "CAIQ TVM-07",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Application Security",
                "order_index": 7,
                "questions": [
                    {
                        "question_text": "Do you perform automated static code analysis (SAST) on all production code releases?",
                        "question_type": "yes_no",
                        "category_tag": "code_review",
                        "framework_ref": "SOC2 CC8.1",
                        "help_text": "CAIQ AIS-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you apply OWASP Top 10 mitigations in your software development process?",
                        "question_type": "yes_no",
                        "category_tag": "owasp",
                        "framework_ref": "ISO27001 A.14.2.1",
                        "help_text": "CAIQ AIS-04",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Business Continuity",
                "order_index": 8,
                "questions": [
                    {
                        "question_text": "Is a documented and tested BCP in place covering cloud service disruption scenarios?",
                        "question_type": "yes_no",
                        "category_tag": "business_continuity",
                        "framework_ref": "ISO27001 A.17.1",
                        "help_text": "CAIQ BCR-01",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Are RTOs and RPOs defined and tested for all critical cloud services?",
                        "question_type": "yes_no",
                        "category_tag": "rto_rpo",
                        "framework_ref": "SOC2 A1.2",
                        "help_text": "CAIQ BCR-09",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Incident Management",
                "order_index": 9,
                "questions": [
                    {
                        "question_text": "Can you notify affected customers of security incidents within 72 hours?",
                        "question_type": "yes_no",
                        "category_tag": "breach_notification",
                        "framework_ref": "GDPR Art. 33",
                        "help_text": "CAIQ SEF-05",
                        "expected_answer": "Yes",
                    },
                ],
            },
        ],
    },
    {
        "template_type": "custom",
        "name": "AI Vendor Governance Assessment",
        "version": "1.0",
        "description": "Baseline AI vendor governance questionnaire for model risk, data governance, and human oversight.",
        "sections": [
            {
                "title": "Model Governance",
                "order_index": 0,
                "questions": [
                    {
                        "question_text": "Do you maintain a documented AI model governance policy that defines ownership, approval gates, and accountability for model changes?",
                        "question_type": "yes_no",
                        "category_tag": "ai_model_governance",
                        "framework_ref": "NIST AI RMF GOV",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you keep versioned model cards describing intended use, limitations, known failure modes, and out-of-scope scenarios for each production model?",
                        "question_type": "yes_no",
                        "category_tag": "model_documentation",
                        "framework_ref": "ISO42001 8.2",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Training Data Governance",
                "order_index": 1,
                "questions": [
                    {
                        "question_text": "Do you track training data provenance and licensing terms to ensure lawful and authorized use of all datasets used for model training?",
                        "question_type": "yes_no",
                        "category_tag": "training_data_provenance",
                        "framework_ref": "EU AI Act Art. 10",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you run documented data quality checks for representativeness, label quality, and class imbalance before model training and retraining?",
                        "question_type": "yes_no",
                        "category_tag": "training_data_quality",
                        "framework_ref": "NIST AI RMF MAP",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Security and Privacy",
                "order_index": 2,
                "questions": [
                    {
                        "question_text": "Is customer data processed by AI workloads encrypted both in transit and at rest using organization-approved cryptographic controls?",
                        "question_type": "yes_no",
                        "category_tag": "ai_data_encryption",
                        "framework_ref": "SOC2 CC6.7",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you enforce retention and deletion controls for prompts, outputs, and training artifacts in line with contractually agreed retention windows?",
                        "question_type": "yes_no",
                        "category_tag": "ai_data_retention",
                        "framework_ref": "GDPR Art. 5(1)(e)",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Bias, Safety, and Robustness",
                "order_index": 3,
                "questions": [
                    {
                        "question_text": "Do you execute recurring bias and fairness testing across protected classes and document mitigation actions for any identified disparities?",
                        "question_type": "yes_no",
                        "category_tag": "ai_bias_testing",
                        "framework_ref": "ISO42001 9.2",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Do you perform adversarial robustness or red-team testing against prompt injection, jailbreak attempts, and model abuse scenarios?",
                        "question_type": "yes_no",
                        "category_tag": "ai_robustness_testing",
                        "framework_ref": "NIST AI RMF MANAGE",
                        "expected_answer": "Yes",
                    },
                ],
            },
            {
                "title": "Human Oversight and Incident Response",
                "order_index": 4,
                "questions": [
                    {
                        "question_text": "Do you require human review checkpoints for high-impact decisions assisted by AI before final action is taken?",
                        "question_type": "yes_no",
                        "category_tag": "ai_human_oversight",
                        "framework_ref": "EU AI Act Art. 14",
                        "expected_answer": "Yes",
                    },
                    {
                        "question_text": "Can you notify customers within defined SLA windows when AI-related incidents materially affect confidentiality, integrity, or service availability?",
                        "question_type": "yes_no",
                        "category_tag": "ai_incident_notification",
                        "framework_ref": "SOC2 CC7.3",
                        "expected_answer": "Yes",
                    },
                ],
            },
        ],
    },
]

QUESTIONNAIRE_HIGH_IMPACT_RULES: dict[str, dict[str, str | int]] = {
    "penetration_testing": {
        "score_delta": 20,
        "rule_name": "Missing annual pen test",
        "rationale": "Lack of annual penetration testing leaves undetected vulnerabilities unaddressed.",
    },
    "encryption_at_rest": {
        "score_delta": 25,
        "rule_name": "No encryption at rest",
        "rationale": "Customer data unencrypted at rest represents a critical data exposure risk.",
    },
    "access_control_mfa": {
        "score_delta": 20,
        "rule_name": "No MFA enforced",
        "rationale": "Absence of MFA significantly increases risk of unauthorized account access.",
    },
    "incident_response": {
        "score_delta": 15,
        "rule_name": "No incident response plan",
        "rationale": "Absence of an IRP increases dwell time and breach impact.",
    },
    "breach_notification": {
        "score_delta": 20,
        "rule_name": "Cannot notify within 72hrs",
        "rationale": "Failure to notify within 72 hours violates GDPR Article 33.",
    },
    "information_security_program": {
        "score_delta": 15,
        "rule_name": "No security program",
        "rationale": "Lack of a formal security program weakens governance and control oversight.",
    },
    "security_policy": {
        "score_delta": 15,
        "rule_name": "No security program",
        "rationale": "Lack of a formal security program weakens governance and control oversight.",
    },
}

ANNEX_III_SECTORS: list[dict[str, object]] = [
    {
        "ref": "III.1",
        "type": "annex_iii",
        "sector": "Biometric identification and categorisation",
        "description": "AI systems intended for biometric identification or categorisation of natural persons, including facial recognition.",
        "articles": ["Art. 6", "Art. 10", "Art. 13"],
    },
    {
        "ref": "III.2",
        "type": "annex_iii",
        "sector": "Critical infrastructure management",
        "description": "AI systems as safety components in management and operation of critical infrastructure (road traffic, water, gas, heating, electricity).",
        "articles": ["Art. 6", "Art. 9"],
    },
    {
        "ref": "III.3",
        "type": "annex_iii",
        "sector": "Education and vocational training",
        "description": "AI systems determining access to educational institutions, evaluating learning outcomes, monitoring student behaviour.",
        "articles": ["Art. 6", "Art. 13", "Art. 14"],
    },
    {
        "ref": "III.4",
        "type": "annex_iii",
        "sector": "Employment and workers management",
        "description": "AI systems for recruitment, promotion, termination, task allocation and monitoring of employees.",
        "articles": ["Art. 6", "Art. 9", "Art. 14"],
    },
    {
        "ref": "III.5",
        "type": "annex_iii",
        "sector": "Access to essential services",
        "description": "AI systems evaluating eligibility for essential public services including healthcare, housing, creditworthiness.",
        "articles": ["Art. 6", "Art. 13", "Art. 14"],
    },
    {
        "ref": "III.6",
        "type": "annex_iii",
        "sector": "Law enforcement",
        "description": "AI systems for risk assessment, polygraphs, evaluation of evidence reliability, crime prediction, profiling.",
        "articles": ["Art. 6", "Art. 10"],
    },
    {
        "ref": "III.7",
        "type": "annex_iii",
        "sector": "Migration, asylum and border control",
        "description": "AI systems for risk assessment, lie detection, examination of applications, monitoring for illegal border crossings.",
        "articles": ["Art. 6", "Art. 9"],
    },
    {
        "ref": "III.8",
        "type": "annex_iii",
        "sector": "Administration of justice",
        "description": "AI systems assisting courts in researching, interpreting facts/law, applying law to concrete sets of facts.",
        "articles": ["Art. 6", "Art. 13", "Art. 14"],
    },
]


class SeedService:
    ISSUE_SLA_DEFAULTS: tuple[tuple[str, int, int], ...] = (
        ("critical", 1, 24),
        ("high", 4, 72),
        ("medium", 24, 168),
        ("low", 72, 720),
    )

    @staticmethod
    def ensure_permissions(db: Session) -> dict[str, Permission]:
        existing = {p.key: p for p in db.execute(select(Permission)).scalars().all()}

        for code, description in PERMISSIONS.items():
            if code not in existing:
                permission = Permission(key=code, description=description)
                db.add(permission)
                db.flush()
                existing[code] = permission
        return existing

    @staticmethod
    def ensure_roles_for_organization(db: Session, organization_id: uuid.UUID) -> dict[str, Role]:
        permission_map = SeedService.ensure_permissions(db)

        existing_roles = {
            r.name: r
            for r in db.execute(select(Role).where(Role.organization_id == organization_id)).scalars().all()
        }

        for role_name in ROLE_PERMISSION_MAP:
            if role_name not in existing_roles:
                role = Role(
                    organization_id=organization_id,
                    name=role_name,
                    description=f"{role_name} default role",
                    is_system=True,
                    is_system_role=True,
                    is_active=True,
                )
                db.add(role)
                db.flush()
                existing_roles[role_name] = role
            else:
                existing_roles[role_name].is_system = True
                existing_roles[role_name].is_system_role = True
                existing_roles[role_name].is_active = True

        for role_name, permission_codes in ROLE_PERMISSION_MAP.items():
            role = existing_roles[role_name]
            current_permission_ids = set(
                db.execute(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).scalars().all()
            )
            for code in permission_codes:
                permission = permission_map[code]
                if permission.id not in current_permission_ids:
                    db.add(RolePermission(role_id=role.id, permission_id=permission.id))

        db.flush()
        return existing_roles

    @staticmethod
    def ensure_framework_catalog(db: Session) -> dict[str, Framework]:
        existing_by_code = {f.code: f for f in db.execute(select(Framework)).scalars().all()}

        for payload in FRAMEWORK_SEEDS:
            framework = existing_by_code.get(payload["code"])
            if framework is None:
                framework = Framework(**payload)
                db.add(framework)
                db.flush()
                existing_by_code[payload["code"]] = framework
            else:
                for field, value in payload.items():
                    setattr(framework, field, value)

        db.flush()
        return existing_by_code

    @staticmethod
    def ensure_starter_obligations(db: Session) -> list[Obligation]:
        frameworks = SeedService.ensure_framework_catalog(db)
        SeedService.ensure_pci_dss_framework(db)
        SeedService.ensure_iso_27001_framework(db)
        SeedService.ensure_soc2_framework(db)
        SeedService.ensure_nist_csf_framework(db)
        SeedService.ensure_cis_controls_framework(db)
        SeedService.ensure_iso_27701_framework(db)
        SeedService.ensure_dora_framework(db)
        SeedService.ensure_csa_star_ccm_framework(db)
        SeedService.ensure_eu_cra_annex_iv_framework(db)
        SeedService.ensure_nis2_framework(db)
        SeedService.ensure_nist_800_53_framework(db)
        SeedService.ensure_hipaa_framework(db)
        SeedService.ensure_ccpa_framework(db)
        SeedService.ensure_dpdp_framework(db)
        SeedService.ensure_iso_31000_framework(db)
        SeedService.ensure_oecd_ai_framework(db)
        SeedService.ensure_ieee_7000_framework(db)
        SeedService.ensure_unesco_ai_framework(db)
        SeedService.ensure_singapore_ai_framework(db)
        SeedService.ensure_g7_hiroshima_framework(db)
        SeedService.ensure_mitre_atlas_framework(db)
        SeedService.ensure_india_first_pack_frameworks(db)
        frameworks = SeedService.ensure_framework_catalog(db)
        existing_keys = {
            (o.framework_id, o.reference_code): o
            for o in db.execute(select(Obligation)).scalars().all()
        }

        created_or_updated: list[Obligation] = []
        for payload in OBLIGATION_SEEDS:
            framework = frameworks[payload["framework_code"]]
            key = (framework.id, payload["reference_code"])
            body = {k: v for k, v in payload.items() if k != "framework_code"}
            body["framework_id"] = framework.id

            obligation = existing_keys.get(key)
            if obligation is None:
                obligation = Obligation(**body)
                db.add(obligation)
                db.flush()
            else:
                for field, value in body.items():
                    setattr(obligation, field, value)

            created_or_updated.append(obligation)

        db.flush()
        SeedService.ensure_iso27701_gdpr_cross_mappings(db)
        SeedService.ensure_dora_cross_mappings(db)
        SeedService.ensure_csa_iso27001_cross_mappings(db)
        SeedService.ensure_hipaa_nist_cross_mappings(db)
        SeedService.ensure_dpdp_gdpr_cross_mappings(db)
        SeedService.ensure_oecd_euai_cross_mappings(db)
        SeedService.ensure_ieee_euai_cross_mappings(db)
        SeedService.ensure_g7_euai_cross_mappings(db)
        SeedService.ensure_g7_oecd_cross_mappings(db)
        SeedService.ensure_atlas_nist_airmf_cross_mappings(db)
        return created_or_updated

    @staticmethod
    def ensure_india_first_pack_frameworks(db: Session) -> None:
        framework_codes = [
            "RBI_IT_GOV",
            "RBI_CLOUD_OUTSOURCING",
            "SEBI_CSCRF",
            "SEBI_CLOUD",
            "IRDAI_CYBER_2023",
            "CERT_IN_2022",
            "INDIA_IT_ACT",
            "MCA_COMPLIANCE_CAL",
            "DPIIT_STARTUP",
        ]
        frameworks = SeedService.ensure_framework_catalog(db)

        for framework_code in framework_codes:
            framework = frameworks[framework_code]
            section_seeds: list[dict[str, int | str | dict | list]] = []
            for section_seed in INDIA_PACK_SECTIONS[framework_code]:
                section = dict(section_seed)
                metadata = INDIA_PACK_SECTION_METADATA.get(str(section["code"]), {})
                section["metadata_json"] = {
                    "framework_code": framework_code,
                    "jurisdiction": "IN",
                    **metadata,
                }
                section_seeds.append(section)
            section_map = SeedService._ensure_framework_sections(
                db,
                framework=framework,
                section_seeds=section_seeds,
            )
            existing = {
                row.reference_code: row
                for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
            }
            active_refs: set[str] = set()
            for ref_code, title, description, section_code, evidence_hints in INDIA_PACK_OBLIGATIONS[framework_code]:
                active_refs.add(ref_code)
                plain = f"Implement and evidence {title.lower()}."
                if evidence_hints:
                    plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
                values = {
                    "framework_section_id": section_map[section_code].id,
                    "title": title,
                    "description": description,
                    "plain_language_summary": plain,
                    "obligation_type": "regulatory",
                    "jurisdiction": "IN",
                    "version": framework.version,
                    "ig_level": None,
                    "control_family": None,
                    "baseline": None,
                    "status": "active",
                }
                row = existing.get(ref_code)
                if row is None:
                    row = Obligation(
                        framework_id=framework.id,
                        reference_code=ref_code,
                        source_url=framework.source_url,
                        effective_date=None,
                        parent_obligation_id=None,
                        **values,
                    )
                    db.add(row)
                    db.flush()
                else:
                    for field, value in values.items():
                        setattr(row, field, value)
                    row.source_url = framework.source_url

            for ref_code, row in existing.items():
                if ref_code not in active_refs:
                    row.status = "inactive"

            questions = INDIA_PACK_QUESTIONS.get(framework_code, [])
            if questions:
                SeedService._ensure_framework_questions(
                    db,
                    framework=framework,
                    question_rows=questions,
                    deactivate_missing=True,
                )
                SeedService._ensure_india_pack_applicability_rules(
                    db,
                    framework=framework,
                    question_keys=[str(item["question_key"]) for item in questions],
                )

        db.flush()

    @staticmethod
    def _safe_rule_token(value: str) -> str:
        lowered = value.lower()
        return "".join(ch if ch.isalnum() else "_" for ch in lowered).strip("_")

    @staticmethod
    def _rule_key(prefix: str, *parts: str, suffix: str) -> str:
        tokens = [SeedService._safe_rule_token(part) for part in parts if part]
        key = "_".join([prefix, *tokens, suffix]).strip("_")
        return key[:128]

    @staticmethod
    def _ensure_india_pack_applicability_rules(
        db: Session,
        *,
        framework: Framework,
        question_keys: list[str],
    ) -> list[ObligationApplicabilityRule]:
        scoped_questions = db.execute(
            select(ObligationApplicabilityQuestion).where(
                ObligationApplicabilityQuestion.framework_id == framework.id,
                ObligationApplicabilityQuestion.organization_id.is_(None),
                ObligationApplicabilityQuestion.obligation_id.is_(None),
                ObligationApplicabilityQuestion.question_key.in_(question_keys),
                ObligationApplicabilityQuestion.status == "active",
                ObligationApplicabilityQuestion.answer_type == "boolean",
            )
        ).scalars().all()
        if not scoped_questions:
            return []

        obligations = db.execute(
            select(Obligation).where(
                Obligation.framework_id == framework.id,
                Obligation.status == "active",
            )
        ).scalars().all()
        if not obligations:
            return []

        existing_seeded = db.execute(
            select(ObligationApplicabilityRule).where(
                ObligationApplicabilityRule.framework_id == framework.id,
                ObligationApplicabilityRule.rule_key.like("seeded_india_%"),
            )
        ).scalars().all()
        existing_by_tuple = {
            (row.obligation_id, row.question_id, row.rule_key): row
            for row in existing_seeded
        }
        expected_keys: set[tuple[uuid.UUID, uuid.UUID, str]] = set()
        created_or_updated: list[ObligationApplicabilityRule] = []

        for obligation in obligations:
            for question in scoped_questions:
                yes_key = SeedService._rule_key(
                    "seeded_india",
                    framework.code,
                    obligation.reference_code,
                    question.question_key,
                    suffix="yes",
                )
                no_key = SeedService._rule_key(
                    "seeded_india",
                    framework.code,
                    obligation.reference_code,
                    question.question_key,
                    suffix="no",
                )
                yes_tuple = (obligation.id, question.id, yes_key)
                no_tuple = (obligation.id, question.id, no_key)
                expected_keys.add(yes_tuple)
                expected_keys.add(no_tuple)

                for key_tuple, expected_value, result, rationale in (
                    (
                        yes_tuple,
                        True,
                        "applicable",
                        f"Seeded India-first rule: obligation {obligation.reference_code} is applicable when "
                        f"'{question.question_key}' is true.",
                    ),
                    (
                        no_tuple,
                        False,
                        "not_applicable",
                        f"Seeded India-first rule: obligation {obligation.reference_code} is not applicable when "
                        f"'{question.question_key}' is false.",
                    ),
                ):
                    row = existing_by_tuple.get(key_tuple)
                    if row is None:
                        row = ObligationApplicabilityRule(
                            framework_id=framework.id,
                            obligation_id=obligation.id,
                            question_id=question.id,
                            rule_key=key_tuple[2],
                            operator="equals",
                            expected_value_json=expected_value,
                            result_applicability=result,
                            rationale=rationale,
                            status="active",
                            created_by_user_id=None,
                        )
                        db.add(row)
                        db.flush()
                        existing_by_tuple[key_tuple] = row
                    else:
                        row.operator = "equals"
                        row.expected_value_json = expected_value
                        row.result_applicability = result
                        row.rationale = rationale
                        row.status = "active"
                    created_or_updated.append(row)

        for row in existing_seeded:
            row_key = (row.obligation_id, row.question_id, row.rule_key)
            if row_key not in expected_keys and row.status != "archived":
                row.status = "archived"

        db.flush()
        return created_or_updated

    @staticmethod
    def ensure_applicability_rules(db: Session) -> list[ObligationApplicabilityRule]:
        """Seed deterministic applicability rules so evaluations can produce real outcomes.

        Rules are created through ApplicabilityService (the real rule-creation API) so all
        validation, status handling and audit hooks are respected.  Only a meaningful
        starter subset is seeded; each rule is keyed deterministically to stay idempotent.
        """
        service = ApplicabilityService(db)
        questions = db.execute(
            select(ObligationApplicabilityQuestion).where(
                ObligationApplicabilityQuestion.status == "active",
            )
        ).scalars().all()

        questions_by_framework: dict[uuid.UUID, list[ObligationApplicabilityQuestion]] = {}
        for q in questions:
            questions_by_framework.setdefault(q.framework_id, []).append(q)

        obligations = db.execute(
            select(Obligation).where(Obligation.status == "active").order_by(Obligation.reference_code.asc())
        ).scalars().all()
        obligation_by_framework: dict[uuid.UUID, list[Obligation]] = {}
        for o in obligations:
            obligation_by_framework.setdefault(o.framework_id, []).append(o)

        existing_rule_keys = {
            (r.framework_id, r.obligation_id, r.rule_key)
            for r in db.execute(
                select(ObligationApplicabilityRule).where(
                    ObligationApplicabilityRule.status == "active",
                    ObligationApplicabilityRule.rule_key.like("seeded_%"),
                )
            ).scalars().all()
        }

        created: list[ObligationApplicabilityRule] = []
        for framework_id, qlist in questions_by_framework.items():
            qlist_sorted = sorted(qlist, key=lambda q: (q.sort_order, q.question_key))
            obl_list = obligation_by_framework.get(framework_id, [])
            if not obl_list:
                continue
            target_obligation = obl_list[0]

            # Prefer a boolean question because it supports an unambiguous yes/no rule pair.
            boolean_question = next((q for q in qlist_sorted if q.answer_type == "boolean"), None)
            chosen_question = boolean_question or qlist_sorted[0]

            def _create_if_needed(rule_key: str, operator: str, expected: Any, result: str, rationale: str) -> None:
                key_tuple = (framework_id, target_obligation.id, rule_key)
                if key_tuple in existing_rule_keys:
                    return
                rule = service.create_rule(
                    framework_id=framework_id,
                    obligation_id=target_obligation.id,
                    question_id=chosen_question.id,
                    rule_key=rule_key,
                    operator=operator,
                    expected_value_json=expected,
                    result_applicability=result,
                    rationale=rationale,
                    created_by_user_id=None,
                )
                created.append(rule)
                existing_rule_keys.add(key_tuple)

            if chosen_question.answer_type == "boolean":
                _create_if_needed(
                    f"seeded_{chosen_question.question_key}_true",
                    "equals",
                    True,
                    "applicable",
                    f"Seeded rule: {chosen_question.question_text} is true, so this obligation is applicable.",
                )
                _create_if_needed(
                    f"seeded_{chosen_question.question_key}_false",
                    "equals",
                    False,
                    "not_applicable",
                    f"Seeded rule: {chosen_question.question_text} is false, so this obligation is not applicable.",
                )
            else:
                # For non-boolean answer types, an explicit answer means the topic is active.
                _create_if_needed(
                    f"seeded_{chosen_question.question_key}_exists",
                    "exists",
                    None,
                    "applicable",
                    f"Seeded rule: {chosen_question.question_text} was answered, so this obligation is applicable.",
                )

        db.flush()
        return created

    @staticmethod
    def ensure_framework_versions(db: Session) -> list[FrameworkVersion]:
        frameworks = SeedService.ensure_framework_catalog(db)
        existing = {
            (row.framework_id, row.version_label): row
            for row in db.execute(select(FrameworkVersion)).scalars().all()
        }
        rows: list[FrameworkVersion] = []
        for payload in FRAMEWORK_VERSION_SEEDS:
            framework = frameworks[payload["framework_code"]]
            key = (framework.id, payload["version_label"])
            row = existing.get(key)
            body = {
                "framework_id": framework.id,
                "version_label": payload["version_label"],
                "status": payload["status"],
                "coverage_level": payload["coverage_level"],
                "source_url": framework.source_url,
                "source_reference": framework.authority,
                "effective_from": framework.effective_date,
                "effective_until": None,
                "notes": "Seeded starter/metadata content pack baseline.",
            }
            if row is None:
                row = FrameworkVersion(**body)
                db.add(row)
                db.flush()
            else:
                for field, value in body.items():
                    setattr(row, field, value)
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def _ensure_framework_sections(
        db: Session,
        *,
        framework: Framework,
        section_seeds: list[dict[str, int | str | dict | list]],
    ) -> dict[str, FrameworkSection]:
        existing = {
            row.section_code: row
            for row in db.execute(
                select(FrameworkSection).where(FrameworkSection.framework_id == framework.id)
            ).scalars().all()
        }
        section_map: dict[str, FrameworkSection] = {}
        for item in section_seeds:
            code = str(item["code"])
            row = existing.get(code)
            metadata_json = item.get("metadata_json")
            if row is None:
                row = FrameworkSection(
                    framework_id=framework.id,
                    framework_version_id=None,
                    parent_section_id=None,
                    section_code=code,
                    title=str(item["title"]),
                    description=str(item["title"]),
                    sort_order=int(item["order"]),
                    status="active",
                    metadata_json=metadata_json if isinstance(metadata_json, dict) else None,
                )
                db.add(row)
                db.flush()
            else:
                row.title = str(item["title"])
                row.description = str(item["title"])
                row.sort_order = int(item["order"])
                row.status = "active"
                if "metadata_json" in item:
                    row.metadata_json = metadata_json if isinstance(metadata_json, dict) else None
            section_map[code] = row
        db.flush()
        return section_map

    @staticmethod
    def _ensure_framework_obligations(
        db: Session,
        *,
        framework: Framework,
        section_map: dict[str, FrameworkSection],
        obligation_rows: list[tuple[str, str, str] | tuple[str, str, str, str]],
        jurisdiction: str,
        version: str,
    ) -> list[Obligation]:
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        seeded: list[Obligation] = []
        for row_payload in obligation_rows:
            if len(row_payload) == 4:
                reference_code, title, section_code, ig_level = row_payload
            else:
                reference_code, title, section_code = row_payload
                ig_level = None
            row = existing.get(reference_code)
            description = f"{title}. Organizations should implement and maintain controls that satisfy this requirement."
            plain = f"Implement and evidence {title.lower()}."
            section = section_map[section_code]
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    framework_section_id=section.id,
                    reference_code=reference_code,
                    title=title,
                    description=description,
                    plain_language_summary=plain,
                    obligation_type="control",
                    jurisdiction=jurisdiction,
                    source_url=None,
                    version=version,
                    ig_level=ig_level,
                    status="active",
                    effective_date=None,
                    parent_obligation_id=None,
                )
                db.add(row)
                db.flush()
            else:
                row.framework_section_id = section.id
                row.title = title
                row.description = description
                row.plain_language_summary = plain
                row.obligation_type = "control"
                row.jurisdiction = jurisdiction
                row.version = version
                row.ig_level = ig_level
                row.status = "active"
            seeded.append(row)
        db.flush()
        return seeded

    @staticmethod
    def _ensure_framework_questions(
        db: Session,
        *,
        framework: Framework,
        question_rows: list[dict[str, int | str]],
        deactivate_missing: bool = False,
    ) -> list[ObligationApplicabilityQuestion]:
        existing = {
            row.question_key: row
            for row in db.execute(
                select(ObligationApplicabilityQuestion).where(
                    ObligationApplicabilityQuestion.framework_id == framework.id,
                    ObligationApplicabilityQuestion.organization_id.is_(None),
                    ObligationApplicabilityQuestion.obligation_id.is_(None),
                )
            ).scalars().all()
        }
        seeded: list[ObligationApplicabilityQuestion] = []
        active_keys: set[str] = set()
        for item in question_rows:
            key = str(item["question_key"])
            active_keys.add(key)
            metadata = {"triggers_scope": str(item["triggers_scope"])}
            if "choices" in item:
                metadata["choices"] = list(item["choices"])  # type: ignore[index]
            extra_metadata = item.get("metadata_json")
            if isinstance(extra_metadata, dict):
                metadata.update(extra_metadata)
            answer_type = str(item.get("answer_type", "boolean"))
            row = existing.get(key)
            if row is None:
                row = ObligationApplicabilityQuestion(
                    organization_id=None,
                    framework_id=framework.id,
                    obligation_id=None,
                    question_key=key,
                    question_text=str(item["question_text"]),
                    help_text=str(item["help_text"]),
                    answer_type=answer_type,
                    required=True,
                    sort_order=int(item["order_index"]),
                    status="active",
                    metadata_json=metadata,
                )
                db.add(row)
                db.flush()
            else:
                row.question_text = str(item["question_text"])
                row.help_text = str(item["help_text"])
                row.answer_type = answer_type
                row.required = True
                row.sort_order = int(item["order_index"])
                row.status = "active"
                row.metadata_json = metadata
            seeded.append(row)
        if deactivate_missing:
            for key, row in existing.items():
                if key not in active_keys and row.status != "inactive":
                    row.status = "inactive"
        db.flush()
        return seeded

    @staticmethod
    def ensure_pci_dss_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "PCI DSS")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="PCI_DSS",
                name="PCI DSS",
                description=(
                    "Payment Card Industry Data Security Standard v4.0. "
                    "Required for all organizations that process, store, or transmit payment card data."
                ),
                category="Security Assurance",
                jurisdiction="global",
                authority="PCI Security Standards Council",
                version="4.0",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()
        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=PCI_DSS_SECTIONS)
        obligation_rows = _pad_obligations(
            PCI_DSS_BASE_OBLIGATIONS,
            target_count=78,
            section_code="G6",
            ref_prefix="REQ-EXT-",
            title_prefix="Additional PCI DSS control requirement",
        )
        SeedService._ensure_framework_obligations(
            db,
            framework=framework,
            section_map=section_map,
            obligation_rows=obligation_rows,
            jurisdiction="global",
            version="4.0",
        )
        SeedService._ensure_framework_questions(db, framework=framework, question_rows=PCI_DSS_QUESTIONS)
        return framework

    @staticmethod
    def ensure_iso_27001_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "ISO 27001")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="ISO_27001",
                name="ISO 27001",
                description=(
                    "ISO/IEC 27001:2022 information security management system standard, Annex A controls. "
                    "Applies to organizations establishing, implementing, maintaining, and continually "
                    "improving an information security management system (ISMS)."
                ),
                category="Security",
                jurisdiction="International",
                authority="ISO/IEC",
                version="2022",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()
        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=ISO_27001_SECTIONS)
        SeedService._ensure_framework_obligations(
            db,
            framework=framework,
            section_map=section_map,
            obligation_rows=ISO_27001_BASE_OBLIGATIONS,
            jurisdiction="International",
            version="2022",
        )
        return framework

    @staticmethod
    def ensure_soc2_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "SOC 2")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="SOC2",
                name="SOC 2",
                description=(
                    "AICPA SOC 2 Trust Services Criteria (2017), Common Criteria (CC1-CC9). "
                    "Applies to service organizations reporting on controls relevant to security, "
                    "availability, processing integrity, confidentiality, or privacy."
                ),
                category="Security Assurance",
                jurisdiction="United States",
                authority="AICPA",
                version="2017",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()
        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=SOC2_SECTIONS)
        SeedService._ensure_framework_obligations(
            db,
            framework=framework,
            section_map=section_map,
            obligation_rows=SOC2_BASE_OBLIGATIONS,
            jurisdiction="United States",
            version="2017",
        )
        return framework

    @staticmethod
    def ensure_nist_csf_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "NIST CSF")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="NIST_CSF",
                name="NIST CSF",
                description=(
                    "NIST Cybersecurity Framework 2.0. Voluntary framework of standards, "
                    "guidelines, and practices to manage cybersecurity risk."
                ),
                category="Cybersecurity",
                jurisdiction="US",
                authority="NIST",
                version="2.0",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()
        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=NIST_CSF_SECTIONS)
        obligation_rows = _pad_obligations(
            NIST_CSF_BASE_OBLIGATIONS,
            target_count=108,
            section_code="RC",
            ref_prefix="CSF-EXT-",
            title_prefix="Additional NIST CSF subcategory requirement",
        )
        SeedService._ensure_framework_obligations(
            db,
            framework=framework,
            section_map=section_map,
            obligation_rows=obligation_rows,
            jurisdiction="US",
            version="2.0",
        )
        SeedService._ensure_framework_questions(db, framework=framework, question_rows=NIST_CSF_QUESTIONS)
        return framework

    @staticmethod
    def ensure_cis_controls_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "CIS Controls")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="CIS_CONTROLS_V8",
                name="CIS Controls",
                description=(
                    "CIS Critical Security Controls v8. Prioritized set of actions to protect organizations from "
                    "known cyber attack vectors. 153 safeguards across 18 control groups."
                ),
                category="Cybersecurity",
                jurisdiction="global",
                authority="Center for Internet Security",
                version="v8",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()
        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=CIS_CONTROLS_V8_SECTIONS)
        obligation_rows = _normalize_cis_ig_levels(CIS_CONTROLS_V8_SAFEGUARDS)
        SeedService._ensure_framework_obligations(
            db,
            framework=framework,
            section_map=section_map,
            obligation_rows=obligation_rows,
            jurisdiction="global",
            version="v8",
        )
        SeedService._ensure_framework_questions(db, framework=framework, question_rows=CIS_CONTROLS_V8_QUESTIONS)
        return framework

    @staticmethod
    def ensure_iso_27701_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "ISO 27701")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="ISO_27701",
                name="ISO 27701",
                description=(
                    "ISO/IEC 27701:2019 — Privacy Information Management System extension to ISO 27001 and ISO 27002."
                ),
                category="Privacy",
                jurisdiction="global",
                authority="ISO/IEC",
                version="2019",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()
        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=ISO_27701_SECTIONS)
        SeedService._ensure_framework_obligations(
            db,
            framework=framework,
            section_map=section_map,
            obligation_rows=ISO_27701_OBLIGATIONS,
            jurisdiction="global",
            version="2019",
        )
        SeedService._ensure_framework_questions(db, framework=framework, question_rows=ISO_27701_QUESTIONS)
        return framework

    @staticmethod
    def ensure_dora_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "DORA")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="DORA",
                name="DORA",
                description=(
                    "EU Digital Operational Resilience Act (Regulation EU 2022/2554). "
                    "Covers ICT risk management, incident reporting, resilience testing, and ICT third-party risk."
                ),
                category="Operational Resilience",
                jurisdiction="EU",
                authority="European Union",
                version="2022/2554",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()
        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=DORA_SECTIONS)
        SeedService._ensure_framework_obligations(
            db,
            framework=framework,
            section_map=section_map,
            obligation_rows=DORA_OBLIGATIONS,
            jurisdiction="EU",
            version="2022/2554",
        )
        SeedService._ensure_framework_questions(db, framework=framework, question_rows=DORA_QUESTIONS)
        return framework

    @staticmethod
    def ensure_csa_star_ccm_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "CSA STAR CCM")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="CSA_STAR_CCM",
                name="CSA STAR CCM",
                description=(
                    "Cloud Security Alliance STAR / Cloud Controls Matrix v4.0 cloud security controls. "
                    "Includes 197 CCM control objectives across 17 domains."
                ),
                category="Cloud Security",
                jurisdiction="global",
                authority="Cloud Security Alliance",
                version="CCM v4.0",
                status="active",
                coverage_level="starter",
                source_url="https://cloudsecurityalliance.org/research/cloud-controls-matrix",
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=CSA_CCM_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        active_refs: set[str] = set()
        for item in CSA_CCM_CONTROLS:
            ref_code = item["reference_code"]
            active_refs.add(ref_code)
            section = section_map[item["section_code"]]
            title = item["title"]
            plain = f"Implement and evidence CSA CCM control {ref_code}: {title.lower()}."
            values = {
                "framework_section_id": section.id,
                "title": title,
                "description": item["description"],
                "plain_language_summary": plain,
                "obligation_type": "control",
                "jurisdiction": "global",
                "version": "CCM v4.0",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
                "source_url": item.get("source_url"),
                "embedding_json": json.dumps({"source": "CSA CCM v4.0", "section": item["section_code"]}),
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
                existing[ref_code] = row
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        for ref_code, row in existing.items():
            if ref_code not in active_refs:
                row.status = "inactive"
        db.flush()
        return framework

    @staticmethod
    def ensure_eu_cra_annex_iv_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "EU CRA Annex IV")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="EU_CRA_ANNEX_IV",
                name="EU CRA Annex IV",
                description="Cyber Resilience Act Annex IV critical products with digital elements classification seed.",
                category="Cybersecurity",
                jurisdiction="EU",
                authority="European Union",
                version="Regulation (EU) 2024/2847",
                status="active",
                coverage_level="starter",
                source_url="https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng",
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=EU_CRA_ANNEX_IV_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        active_refs: set[str] = set()
        for ref_code, title, description, section_code, evidence_hints in EU_CRA_ANNEX_IV_OBLIGATIONS:
            active_refs.add(ref_code)
            plain = f"Classify and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "classification",
                "jurisdiction": "EU",
                "version": "Regulation (EU) 2024/2847",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
                "source_url": "https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
                existing[ref_code] = row
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        for ref_code, row in existing.items():
            if ref_code not in active_refs:
                row.status = "inactive"
        SeedService._ensure_framework_questions(db, framework=framework, question_rows=EU_CRA_ANNEX_IV_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_nis2_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "NIS2")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="NIS2",
                name="NIS2",
                description=(
                    "EU Network and Information Security Directive 2 (Directive EU 2022/2555). "
                    "Covers cybersecurity risk management and incident reporting obligations."
                ),
                category="Cybersecurity",
                jurisdiction="EU",
                authority="European Union",
                version="2022/2555",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()
        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=NIS2_SECTIONS)
        SeedService._ensure_framework_obligations(
            db,
            framework=framework,
            section_map=section_map,
            obligation_rows=NIS2_OBLIGATIONS,
            jurisdiction="EU",
            version="2022/2555",
        )
        SeedService._ensure_framework_questions(db, framework=framework, question_rows=NIS2_QUESTIONS)
        return framework

    @staticmethod
    def ensure_nist_800_53_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "NIST SP 800-53")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="NIST_800_53",
                name="NIST SP 800-53",
                description=(
                    "NIST Special Publication 800-53 security controls with FedRAMP Rev 4 LOW, MODERATE, "
                    "and HIGH baseline selections. Required for US federal cloud systems."
                ),
                category="Cybersecurity",
                jurisdiction="US",
                authority="NIST",
                version="Rev 4 / FedRAMP",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=NIST_800_53_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        active_refs: set[str] = set()
        low_refs = {ref_code for ref_code, _, _ in NIST_800_53_LOW_CONTROLS}
        rev4_by_ref = {item["reference_code"]: item for item in NIST_800_53_REV4_HIGH_CONTROLS}
        for ref_code, title, family in NIST_800_53_LOW_CONTROLS:
            active_refs.add(ref_code)
            hints = nist_evidence_hints(family)
            plain = f"Implement and evidence {title.lower()}."
            if hints:
                plain = f"{plain} Evidence hints: {', '.join(hints)}"
            rev4_item = rev4_by_ref.get(ref_code)
            baselines = rev4_item["baselines"] if rev4_item is not None else ["LOW"]
            values = {
                "framework_section_id": section_map[family].id,
                "title": title,
                "description": rev4_item["description"] if rev4_item is not None else nist_description(ref_code, title, family),
                "plain_language_summary": plain,
                "obligation_type": "control",
                "jurisdiction": "US",
                "version": "Rev 4 / FedRAMP",
                "ig_level": None,
                "control_family": family,
                "baseline": "LOW",
                "status": "active",
                "embedding_json": json.dumps({"fedramp_rev4_baselines": baselines}),
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
                existing[ref_code] = row
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        for item in NIST_800_53_REV4_HIGH_CONTROLS:
            ref_code = item["reference_code"]
            active_refs.add(ref_code)
            family = item["family"]
            if family not in section_map:
                continue
            baselines = item["baselines"]
            baseline = "HIGH"
            if ref_code in low_refs:
                baseline = "LOW"
            elif "MODERATE" in baselines:
                baseline = "MODERATE"
            plain = (
                f"Implement and evidence {item['title'].lower()} for the "
                f"{', '.join(baselines)} FedRAMP/NIST 800-53 baseline."
            )
            values = {
                "framework_section_id": section_map[family].id,
                "title": item["title"],
                "description": item["description"],
                "plain_language_summary": plain,
                "obligation_type": "control",
                "jurisdiction": "US",
                "version": "Rev 4 / FedRAMP",
                "ig_level": None,
                "control_family": family,
                "baseline": baseline,
                "status": "active",
                "embedding_json": json.dumps({"fedramp_rev4_baselines": baselines}),
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
                existing[ref_code] = row
            else:
                for field, value in values.items():
                    if field == "baseline" and ref_code in low_refs:
                        value = "LOW"
                    setattr(row, field, value)

        for ref_code, row in existing.items():
            if ref_code in active_refs:
                continue
            row.status = "inactive"
            row.baseline = None
            row.control_family = None

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=NIST_800_53_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_hipaa_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "HIPAA")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="HIPAA",
                name="HIPAA",
                description=(
                    "Health Insurance Portability and Accountability Act. Privacy Rule, Security Rule, and Breach "
                    "Notification Rule. Required for covered entities and business associates handling protected "
                    "health information (PHI)."
                ),
                category="Privacy",
                jurisdiction="US",
                authority="HHS",
                version="2013 Omnibus",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=HIPAA_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        for ref_code, title, description, section_code, evidence_hints in HIPAA_OBLIGATIONS:
            plain = f"Implement and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "privacy",
                "jurisdiction": "US",
                "version": "2013 Omnibus",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=HIPAA_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_hipaa_nist_cross_mappings(db: Session) -> list[CrossFrameworkObligationMapping]:
        obligations = {row.reference_code: row for row in db.execute(select(Obligation)).scalars().all()}
        existing = {
            (row.source_obligation_id, row.target_obligation_id): row
            for row in db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
        }
        rows: list[CrossFrameworkObligationMapping] = []
        for source_ref, target_ref, mapping_type in HIPAA_NIST_MAPPINGS:
            source = obligations.get(source_ref)
            target = obligations.get(target_ref)
            if source is None or target is None:
                continue
            key = (source.id, target.id)
            row = existing.get(key)
            if row is None:
                row = CrossFrameworkObligationMapping(
                    organization_id=None,
                    source_obligation_id=source.id,
                    target_obligation_id=target.id,
                    mapping_type=mapping_type,
                    notes=f"Seeded mapping: {source_ref} -> {target_ref}",
                )
                db.add(row)
                db.flush()
            else:
                row.mapping_type = mapping_type
                row.notes = f"Seeded mapping: {source_ref} -> {target_ref}"
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_csa_iso27001_cross_mappings(db: Session) -> list[CrossFrameworkObligationMapping]:
        obligations = {row.reference_code: row for row in db.execute(select(Obligation)).scalars().all()}
        existing = {
            (row.source_obligation_id, row.target_obligation_id): row
            for row in db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
        }
        rows: list[CrossFrameworkObligationMapping] = []
        for source_ref, target_ref, mapping_type in CSA_CCM_ISO27001_MAPPINGS:
            source = obligations.get(source_ref)
            target = obligations.get(target_ref)
            if source is None or target is None:
                continue
            key = (source.id, target.id)
            row = existing.get(key)
            notes = f"Seeded CSA CCM v4.0 to ISO 27001:2022 mapping: {source_ref} -> {target_ref}"
            if row is None:
                row = CrossFrameworkObligationMapping(
                    organization_id=None,
                    source_obligation_id=source.id,
                    target_obligation_id=target.id,
                    mapping_type=mapping_type,
                    notes=notes,
                    semantic_similarity_score=None,
                    mapping_method="seeded",
                )
                db.add(row)
                db.flush()
            else:
                row.mapping_type = mapping_type
                row.notes = notes
                row.mapping_method = "seeded"
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_ccpa_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "CCPA/CPRA")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="CCPA_CPRA",
                name="CCPA/CPRA",
                description=(
                    "California Consumer Privacy Act (CCPA) as amended by the California Privacy Rights Act "
                    "(CPRA). Applies to certain for-profit businesses handling California residents' personal information."
                ),
                category="Privacy",
                jurisdiction="US-CA",
                authority="State of California",
                version="2023",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=CCPA_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        for ref_code, title, description, section_code, evidence_hints in CCPA_OBLIGATIONS:
            plain = f"Implement and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "privacy",
                "jurisdiction": "US-CA",
                "version": "2023",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=CCPA_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_dpdp_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "India DPDP")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="INDIA_DPDP",
                name="India DPDP",
                description=(
                    "India Digital Personal Data Protection Act 2023. Governs processing of digital personal data of "
                    "Indian residents and defines obligations for Data Fiduciaries and Significant Data Fiduciaries."
                ),
                category="Privacy",
                jurisdiction="IN",
                authority="Government of India",
                version="2023",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=DPDP_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        active_refs: set[str] = set()
        for ref_code, title, description, section_code, evidence_hints in DPDP_2025_RULES_OBLIGATIONS:
            active_refs.add(ref_code)
            plain = f"Implement and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "privacy",
                "jurisdiction": "IN",
                "version": "2023 Act / 2025 Rules",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        for ref_code, row in existing.items():
            if ref_code not in active_refs:
                row.status = "inactive"

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=DPDP_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_iso_31000_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "ISO 31000")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="ISO_31000",
                name="ISO 31000",
                description=(
                    "ISO 31000:2018 — Risk Management Guidelines. International standard for risk management "
                    "principles and guidelines applicable to any organization regardless of size, sector, or activity."
                ),
                category="Risk Management",
                jurisdiction="global",
                authority="ISO",
                version="2018",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=ISO_31000_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        for ref_code, title, description, section_code, evidence_hints in ISO_31000_OBLIGATIONS:
            plain = f"Implement and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "risk_management",
                "jurisdiction": "global",
                "version": "2018",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=ISO_31000_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_oecd_ai_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "OECD AI Principles")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="OECD_AI_PRINCIPLES",
                name="OECD AI Principles",
                description=(
                    "OECD Principles on Artificial Intelligence (updated 2024). International standard for "
                    "trustworthy AI adopted by member and partner countries."
                ),
                category="AI Governance",
                jurisdiction="global",
                authority="OECD",
                version="2024",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=OECD_AI_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        for ref_code, title, description, section_code, evidence_hints in OECD_AI_OBLIGATIONS:
            plain = f"Implement and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "ai_governance",
                "jurisdiction": "global",
                "version": "2024",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=OECD_AI_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_ieee_7000_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "IEEE 7000 Series")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="IEEE_7000_SERIES",
                name="IEEE 7000 Series",
                description=(
                    "IEEE Standards for Ethically Aligned Design including IEEE 7000, IEEE 7001, and IEEE 7009."
                ),
                category="AI Governance",
                jurisdiction="global",
                authority="IEEE",
                version="2021-2022",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=IEEE_7000_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        for ref_code, title, description, section_code, evidence_hints in IEEE_7000_OBLIGATIONS:
            plain = f"Implement and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "ai_governance",
                "jurisdiction": "global",
                "version": "2021-2022",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=IEEE_7000_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_unesco_ai_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "UNESCO AI Ethics")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="UNESCO_AI_ETHICS",
                name="UNESCO AI Ethics",
                description=(
                    "UNESCO Recommendation on the Ethics of AI (2021). Global normative framework for AI ethics."
                ),
                category="AI Governance",
                jurisdiction="global",
                authority="UNESCO",
                version="2021",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=UNESCO_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        for ref_code, title, description, section_code, evidence_hints in UNESCO_OBLIGATIONS:
            plain = f"Implement and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "ai_governance",
                "jurisdiction": "global",
                "version": "2021",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=UNESCO_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_singapore_ai_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "Singapore Model AI Governance")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="SINGAPORE_MODEL_AI_GOV",
                name="Singapore Model AI Governance",
                description="Singapore Model AI Governance Framework 2nd Edition (2020).",
                category="AI Governance",
                jurisdiction="SG",
                authority="IMDA",
                version="2020",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=SINGAPORE_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        for ref_code, title, description, section_code, evidence_hints in SINGAPORE_OBLIGATIONS:
            plain = f"Implement and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "ai_governance",
                "jurisdiction": "SG",
                "version": "2020",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=SINGAPORE_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_g7_hiroshima_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "G7 Hiroshima AI Process")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="G7_HIROSHIMA_AI_PROCESS",
                name="G7 Hiroshima AI Process",
                description="G7 Hiroshima AI Process International Guiding Principles (2023).",
                category="AI Governance",
                jurisdiction="global",
                authority="G7",
                version="2023",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=G7_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        for ref_code, title, description, section_code, evidence_hints in G7_OBLIGATIONS:
            plain = f"Implement and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "ai_governance",
                "jurisdiction": "global",
                "version": "2023",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=G7_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_mitre_atlas_framework(db: Session) -> Framework:
        framework = db.execute(select(Framework).where(Framework.name == "MITRE ATLAS")).scalar_one_or_none()
        if framework is None:
            framework = Framework(
                code="MITRE_ATLAS",
                name="MITRE ATLAS",
                description="MITRE Adversarial Threat Landscape for Artificial-Intelligence Systems (ATLAS).",
                category="AI Security",
                jurisdiction="global",
                authority="MITRE",
                version="4.5",
                status="active",
                coverage_level="starter",
                source_url=None,
                effective_date=None,
            )
            db.add(framework)
            db.flush()

        section_map = SeedService._ensure_framework_sections(db, framework=framework, section_seeds=ATLAS_SECTIONS)
        existing = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
        }
        for ref_code, title, description, section_code, evidence_hints in ATLAS_OBLIGATIONS:
            plain = f"Implement and evidence {title.lower()}."
            if evidence_hints:
                plain = f"{plain} Evidence hints: {', '.join(evidence_hints)}"
            values = {
                "framework_section_id": section_map[section_code].id,
                "title": title,
                "description": description,
                "plain_language_summary": plain,
                "obligation_type": "ai_security",
                "jurisdiction": "global",
                "version": "4.5",
                "ig_level": None,
                "control_family": None,
                "baseline": None,
                "status": "active",
            }
            row = existing.get(ref_code)
            if row is None:
                row = Obligation(
                    framework_id=framework.id,
                    reference_code=ref_code,
                    source_url=None,
                    effective_date=None,
                    parent_obligation_id=None,
                    **values,
                )
                db.add(row)
                db.flush()
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        SeedService._ensure_framework_questions(db, framework=framework, question_rows=ATLAS_QUESTIONS)
        db.flush()
        return framework

    @staticmethod
    def ensure_dpdp_gdpr_cross_mappings(db: Session) -> list[CrossFrameworkObligationMapping]:
        obligations = {row.reference_code: row for row in db.execute(select(Obligation)).scalars().all()}
        existing = {
            (row.source_obligation_id, row.target_obligation_id): row
            for row in db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
        }

        rows: list[CrossFrameworkObligationMapping] = []
        for source_ref, target_ref, mapping_type in DPDP_GDPR_MAPPINGS:
            source = obligations.get(source_ref)
            target = obligations.get(target_ref)
            if source is None or target is None:
                continue
            key = (source.id, target.id)
            row = existing.get(key)
            if row is None:
                row = CrossFrameworkObligationMapping(
                    organization_id=None,
                    source_obligation_id=source.id,
                    target_obligation_id=target.id,
                    mapping_type=mapping_type,
                    notes=f"Seeded mapping: {source_ref} -> {target_ref}",
                )
                db.add(row)
                db.flush()
            else:
                row.mapping_type = mapping_type
                row.notes = f"Seeded mapping: {source_ref} -> {target_ref}"
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_oecd_euai_cross_mappings(db: Session) -> list[CrossFrameworkObligationMapping]:
        obligations = {row.reference_code: row for row in db.execute(select(Obligation)).scalars().all()}
        existing = {
            (row.source_obligation_id, row.target_obligation_id): row
            for row in db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
        }
        rows: list[CrossFrameworkObligationMapping] = []
        for source_ref, target_ref, mapping_type in OECD_EUAI_MAPPINGS:
            source = obligations.get(source_ref)
            target = obligations.get(target_ref)
            if source is None or target is None:
                continue
            key = (source.id, target.id)
            row = existing.get(key)
            if row is None:
                row = CrossFrameworkObligationMapping(
                    organization_id=None,
                    source_obligation_id=source.id,
                    target_obligation_id=target.id,
                    mapping_type=mapping_type,
                    notes=f"Seeded mapping: {source_ref} -> {target_ref}",
                )
                db.add(row)
                db.flush()
            else:
                row.mapping_type = mapping_type
                row.notes = f"Seeded mapping: {source_ref} -> {target_ref}"
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_ieee_euai_cross_mappings(db: Session) -> list[CrossFrameworkObligationMapping]:
        obligations = {row.reference_code: row for row in db.execute(select(Obligation)).scalars().all()}
        existing = {
            (row.source_obligation_id, row.target_obligation_id): row
            for row in db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
        }
        rows: list[CrossFrameworkObligationMapping] = []
        for source_ref, target_ref, mapping_type in IEEE_EUAI_MAPPINGS:
            source = obligations.get(source_ref)
            target = obligations.get(target_ref)
            if source is None or target is None:
                continue
            key = (source.id, target.id)
            row = existing.get(key)
            if row is None:
                row = CrossFrameworkObligationMapping(
                    organization_id=None,
                    source_obligation_id=source.id,
                    target_obligation_id=target.id,
                    mapping_type=mapping_type,
                    notes=f"Seeded mapping: {source_ref} -> {target_ref}",
                )
                db.add(row)
                db.flush()
            else:
                row.mapping_type = mapping_type
                row.notes = f"Seeded mapping: {source_ref} -> {target_ref}"
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_g7_euai_cross_mappings(db: Session) -> list[CrossFrameworkObligationMapping]:
        obligations = {row.reference_code: row for row in db.execute(select(Obligation)).scalars().all()}
        existing = {
            (row.source_obligation_id, row.target_obligation_id): row
            for row in db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
        }
        rows: list[CrossFrameworkObligationMapping] = []
        for source_ref, target_ref, mapping_type in G7_EUAI_MAPPINGS:
            source = obligations.get(source_ref)
            target = obligations.get(target_ref)
            if source is None or target is None:
                continue
            key = (source.id, target.id)
            row = existing.get(key)
            if row is None:
                row = CrossFrameworkObligationMapping(
                    organization_id=None,
                    source_obligation_id=source.id,
                    target_obligation_id=target.id,
                    mapping_type=mapping_type,
                    notes=f"Seeded mapping: {source_ref} -> {target_ref}",
                )
                db.add(row)
                db.flush()
            else:
                row.mapping_type = mapping_type
                row.notes = f"Seeded mapping: {source_ref} -> {target_ref}"
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_g7_oecd_cross_mappings(db: Session) -> list[CrossFrameworkObligationMapping]:
        obligations = {row.reference_code: row for row in db.execute(select(Obligation)).scalars().all()}
        existing = {
            (row.source_obligation_id, row.target_obligation_id): row
            for row in db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
        }
        rows: list[CrossFrameworkObligationMapping] = []
        for source_ref, target_ref, mapping_type in G7_OECD_MAPPINGS:
            source = obligations.get(source_ref)
            target = obligations.get(target_ref)
            if source is None or target is None:
                continue
            key = (source.id, target.id)
            row = existing.get(key)
            if row is None:
                row = CrossFrameworkObligationMapping(
                    organization_id=None,
                    source_obligation_id=source.id,
                    target_obligation_id=target.id,
                    mapping_type=mapping_type,
                    notes=f"Seeded mapping: {source_ref} -> {target_ref}",
                )
                db.add(row)
                db.flush()
            else:
                row.mapping_type = mapping_type
                row.notes = f"Seeded mapping: {source_ref} -> {target_ref}"
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_atlas_nist_airmf_cross_mappings(db: Session) -> list[CrossFrameworkObligationMapping]:
        obligations = {row.reference_code: row for row in db.execute(select(Obligation)).scalars().all()}
        existing = {
            (row.source_obligation_id, row.target_obligation_id): row
            for row in db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
        }
        rows: list[CrossFrameworkObligationMapping] = []
        for source_ref, target_ref, mapping_type in ATLAS_NIST_AIRMF_MAPPINGS:
            source = obligations.get(source_ref)
            target = obligations.get(target_ref)
            if source is None or target is None:
                continue
            key = (source.id, target.id)
            row = existing.get(key)
            if row is None:
                row = CrossFrameworkObligationMapping(
                    organization_id=None,
                    source_obligation_id=source.id,
                    target_obligation_id=target.id,
                    mapping_type=mapping_type,
                    notes=f"Seeded mapping: {source_ref} -> {target_ref}",
                )
                db.add(row)
                db.flush()
            else:
                row.mapping_type = mapping_type
                row.notes = f"Seeded mapping: {source_ref} -> {target_ref}"
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_dora_cross_mappings(db: Session) -> list[CrossFrameworkObligationMapping]:
        obligations = {
            row.reference_code: row
            for row in db.execute(select(Obligation)).scalars().all()
        }
        existing = {
            (row.source_obligation_id, row.target_obligation_id): row
            for row in db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
        }
        mapping_rows = [
            ("DORA-17.1", "NIS2-21.2", "related"),
            ("DORA-11.1", "NIS2-21.3", "related"),
            ("DORA-28.1", "NIS2-21.4", "related"),
            ("DORA-19.1", "NIS2-23.2", "related"),
            ("DORA-6.1", "ISO27001 A.6.1.1", "related"),
            ("DORA-10.1", "ISO27001 A.12.4.1", "related"),
            ("DORA-12.1", "ISO27001 A.12.3.1", "related"),
        ]

        rows: list[CrossFrameworkObligationMapping] = []
        for source_ref, target_ref, mapping_type in mapping_rows:
            source = obligations.get(source_ref)
            target = obligations.get(target_ref)
            if source is None or target is None:
                continue
            key = (source.id, target.id)
            row = existing.get(key)
            if row is None:
                row = CrossFrameworkObligationMapping(
                    organization_id=None,
                    source_obligation_id=source.id,
                    target_obligation_id=target.id,
                    mapping_type=mapping_type,
                    notes=f"Seeded mapping: {source_ref} -> {target_ref}",
                )
                db.add(row)
                db.flush()
            else:
                row.mapping_type = mapping_type
                row.notes = f"Seeded mapping: {source_ref} -> {target_ref}"
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_iso27701_gdpr_cross_mappings(db: Session) -> list[CrossFrameworkObligationMapping]:
        iso_framework = db.execute(select(Framework).where(Framework.name == "ISO 27701")).scalar_one_or_none()
        gdpr_framework = db.execute(select(Framework).where(Framework.code == "GDPR")).scalar_one_or_none()
        if iso_framework is None or gdpr_framework is None:
            return []

        iso_by_ref = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == iso_framework.id)).scalars().all()
        }
        gdpr_by_ref = {
            row.reference_code: row
            for row in db.execute(select(Obligation).where(Obligation.framework_id == gdpr_framework.id)).scalars().all()
        }
        existing = {
            (row.source_obligation_id, row.target_obligation_id): row
            for row in db.execute(select(CrossFrameworkObligationMapping)).scalars().all()
        }
        rows: list[CrossFrameworkObligationMapping] = []
        for iso_ref, gdpr_ref, mapping_type in ISO_27701_GDPR_MAPPINGS:
            source = iso_by_ref.get(iso_ref)
            target = gdpr_by_ref.get(gdpr_ref)
            if source is None or target is None:
                continue
            key = (source.id, target.id)
            row = existing.get(key)
            if row is None:
                row = CrossFrameworkObligationMapping(
                    organization_id=None,
                    source_obligation_id=source.id,
                    target_obligation_id=target.id,
                    mapping_type=mapping_type,
                    notes=f"Seeded mapping: {iso_ref} -> {gdpr_ref}",
                )
                db.add(row)
                db.flush()
            else:
                row.mapping_type = mapping_type
                row.notes = f"Seeded mapping: {iso_ref} -> {gdpr_ref}"
            rows.append(row)
        db.flush()
        return rows

    @staticmethod
    def ensure_default_data_access_anomaly_rules(db: Session, organization_id: uuid.UUID, created_by: uuid.UUID) -> list[DataAccessAnomalyRule]:
        rows: list[DataAccessAnomalyRule] = []
        existing = {
            row.rule_type: row
            for row in db.execute(
                select(DataAccessAnomalyRule).where(
                    DataAccessAnomalyRule.organization_id == organization_id,
                    DataAccessAnomalyRule.data_asset_id.is_(None),
                    DataAccessAnomalyRule.deleted_at.is_(None),
                )
            ).scalars().all()
        }
        for payload in DATA_ACCESS_DEFAULT_RULES:
            if payload["rule_type"] in existing:
                rows.append(existing[payload["rule_type"]])
                continue
            now = datetime.now(UTC)
            row = DataAccessAnomalyRule(
                organization_id=organization_id,
                data_asset_id=None,
                rule_type=payload["rule_type"],
                rule_config=payload["rule_config"],
                is_active=True,
                created_by=created_by,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
            db.add(row)
            db.flush()
            rows.append(row)
        return rows

    @staticmethod
    def ensure_global_email_templates(db: Session) -> list[EmailTemplate]:
        existing = {
            (tpl.organization_id, tpl.template_key, tpl.version): tpl
            for tpl in db.execute(select(EmailTemplate)).scalars().all()
        }
        results: list[EmailTemplate] = []
        for payload in EMAIL_TEMPLATE_SEEDS:
            key = (None, payload["template_key"], payload["version"])
            template = existing.get(key)
            if template is None:
                template = EmailTemplate(
                    organization_id=None,
                    created_by_user_id=None,
                    **payload,
                )
                db.add(template)
                db.flush()
            else:
                for field, value in payload.items():
                    setattr(template, field, value)
            results.append(template)

        db.flush()
        return results

    @staticmethod
    def ensure_policy_templates(db: Session) -> list[PolicyTemplate]:
        existing_rows = db.execute(select(PolicyTemplate)).scalars().all()
        existing_by_slug = {row.slug: row for row in existing_rows}
        existing_system_by_title = {
            (row.title or row.name): row
            for row in existing_rows
            if bool(getattr(row, "is_system", False))
        }
        created: list[PolicyTemplate] = []

        slug_policy_type_map = {
            "data-retention": "data_privacy",
            "access-control": "access_control",
            "incident-response": "incident_response",
            "vendor-management": "vendor_management",
            "business-continuity": "business_continuity",
            "change-management": "change_management",
            "acceptable-use": "acceptable_use",
            "information-security": "information_security",
            "ai-governance": "ai_governance",
            "third-party-risk": "third_party_risk",
            "data-classification": "data_privacy",
            "password-management": "access_control",
            "remote-work": "information_security",
            "whistleblower-ethics": "change_management",
            "secure-development": "information_security",
        }

        for payload in POLICY_TEMPLATE_SEEDS:
            row = existing_by_slug.get(payload["slug"]) or existing_system_by_title.get(payload["name"])
            if row is None:
                row = PolicyTemplate(
                    organization_id=None,
                    slug=payload["slug"],
                    title=payload["name"],
                    name=payload["name"],
                    description=payload["description"],
                    category=payload["category"],
                    policy_type=slug_policy_type_map.get(payload["slug"]),
                    framework_tags=list(payload["framework_tags"]),
                    content=payload["content"],
                    version=payload["version"],
                    is_system=True,
                    is_active=True,
                )
                db.add(row)
                db.flush()
            else:
                row.organization_id = None
                row.slug = payload["slug"]
                row.title = payload["name"]
                row.name = payload["name"]
                row.description = payload["description"]
                row.category = payload["category"]
                row.policy_type = slug_policy_type_map.get(payload["slug"])
                row.framework_tags = list(payload["framework_tags"])
                row.content = payload["content"]
                row.version = payload["version"]
                row.is_system = True
                row.is_active = True

            existing_by_slug[row.slug] = row
            existing_system_by_title[row.title or row.name] = row
            created.append(row)

        db.flush()
        return created

    @staticmethod
    def ensure_questionnaire_templates(db: Session) -> list[QuestionnaireTemplate]:
        existing_templates = {
            row.template_type: row
            for row in db.execute(
                select(QuestionnaireTemplate).where(
                    QuestionnaireTemplate.organization_id.is_(None),
                    QuestionnaireTemplate.is_system_template.is_(True),
                )
            ).scalars().all()
        }
        seeded: list[QuestionnaireTemplate] = []

        for template_seed in QUESTIONNAIRE_TEMPLATE_SEEDS:
            row = existing_templates.get(template_seed["template_type"])
            if row is None:
                row = QuestionnaireTemplate(
                    organization_id=None,
                    template_type=template_seed["template_type"],
                    name=template_seed["name"],
                    version=template_seed["version"],
                    description=template_seed["description"],
                    is_system_template=True,
                    is_active=True,
                    created_by=None,
                )
                db.add(row)
                db.flush()
                existing_templates[template_seed["template_type"]] = row
            else:
                row.name = template_seed["name"]
                row.version = template_seed["version"]
                row.description = template_seed["description"]
                row.is_system_template = True
                row.is_active = True

            section_map = {
                (section.title, section.order_index): section
                for section in db.execute(
                    select(QuestionnaireTemplateSection).where(
                        QuestionnaireTemplateSection.template_id == row.id,
                    )
                ).scalars().all()
            }
            for section_seed in template_seed["sections"]:
                section_key = (section_seed["title"], int(section_seed["order_index"]))
                section = section_map.get(section_key)
                if section is None:
                    section = QuestionnaireTemplateSection(
                        template_id=row.id,
                        title=section_seed["title"],
                        description=section_seed.get("description"),
                        order_index=int(section_seed["order_index"]),
                    )
                    db.add(section)
                    db.flush()
                    section_map[section_key] = section

                question_map = {
                    (question.question_text, question.order_index): question
                    for question in db.execute(
                        select(QuestionnaireTemplateQuestion).where(
                            QuestionnaireTemplateQuestion.template_id == row.id,
                            QuestionnaireTemplateQuestion.section_id == section.id,
                        )
                    ).scalars().all()
                }
                for q_idx, question_seed in enumerate(section_seed["questions"]):
                    question_key = (question_seed["question_text"], q_idx)
                    question = question_map.get(question_key)
                    if question is None:
                        question = QuestionnaireTemplateQuestion(
                            template_id=row.id,
                            section_id=section.id,
                            question_text=question_seed["question_text"],
                            question_type=question_seed["question_type"],
                            category_tag=question_seed["category_tag"],
                            framework_ref=question_seed.get("framework_ref"),
                            allowed_values=question_seed.get("allowed_values"),
                            expected_answer=question_seed.get("expected_answer"),
                            is_required=bool(question_seed.get("is_required", True)),
                            order_index=q_idx,
                            help_text=question_seed.get("help_text"),
                        )
                        db.add(question)
                        db.flush()
                    else:
                        question.question_type = question_seed["question_type"]
                        question.category_tag = question_seed["category_tag"]
                        question.framework_ref = question_seed.get("framework_ref")
                        question.allowed_values = question_seed.get("allowed_values")
                        question.expected_answer = question_seed.get("expected_answer")
                        question.is_required = bool(question_seed.get("is_required", True))
                        question.help_text = question_seed.get("help_text")
                        question.order_index = q_idx
                        question.section_id = section.id

            seeded.append(row)

        db.flush()
        return seeded

    @staticmethod
    def ensure_questionnaire_scoring_rules(db: Session) -> list[QuestionnaireScoringRule]:
        templates = SeedService.ensure_questionnaire_templates(db)
        template_ids = [row.id for row in templates]
        if not template_ids:
            return []

        questions = db.execute(
            select(QuestionnaireTemplateQuestion).where(QuestionnaireTemplateQuestion.template_id.in_(template_ids))
        ).scalars().all()
        existing_rules = {
            (row.organization_id, row.question_id, row.condition_operator, row.condition_value): row
            for row in db.execute(
                select(QuestionnaireScoringRule).where(QuestionnaireScoringRule.organization_id.is_(None))
            ).scalars().all()
        }
        seeded: list[QuestionnaireScoringRule] = []

        for question in questions:
            if question.question_type != "yes_no":
                continue
            if (question.expected_answer or "").strip().lower() != "yes":
                continue

            no_override = QUESTIONNAIRE_HIGH_IMPACT_RULES.get(question.category_tag)
            no_rule_name = "Control expectation not met"
            no_rationale = "The answer indicates the expected control is not in place."
            no_delta = 15
            if no_override is not None:
                no_rule_name = str(no_override["rule_name"])
                no_rationale = str(no_override["rationale"])
                no_delta = int(no_override["score_delta"])

            rule_specs = [
                ("eq", "No", no_delta, no_rule_name, no_rationale),
                (
                    "eq",
                    "Yes",
                    -5,
                    "Control expectation met",
                    "The answer indicates expected control coverage is in place.",
                ),
            ]
            for operator, value, delta, name, rationale in rule_specs:
                key = (None, question.id, operator, value)
                row = existing_rules.get(key)
                if row is None:
                    row = QuestionnaireScoringRule(
                        organization_id=None,
                        template_id=question.template_id,
                        question_id=question.id,
                        rule_name=name,
                        condition_operator=operator,
                        condition_value=value,
                        score_delta=delta,
                        rationale=rationale,
                        is_active=True,
                    )
                    db.add(row)
                    db.flush()
                    existing_rules[key] = row
                else:
                    row.template_id = question.template_id
                    row.rule_name = name
                    row.score_delta = delta
                    row.rationale = rationale
                    row.is_active = True
                seeded.append(row)

        db.flush()
        return seeded

    @staticmethod
    def ensure_issue_sla_policies(db: Session, organization_id: uuid.UUID) -> list[IssueSLAPolicy]:
        existing = {
            row.severity: row
            for row in db.execute(
                select(IssueSLAPolicy).where(IssueSLAPolicy.organization_id == organization_id)
            ).scalars().all()
        }
        seeded: list[IssueSLAPolicy] = []
        for severity, response_hours, resolution_hours in SeedService.ISSUE_SLA_DEFAULTS:
            row = existing.get(severity)
            if row is None:
                row = IssueSLAPolicy(
                    organization_id=organization_id,
                    severity=severity,
                    response_sla_hours=response_hours,
                    resolution_sla_hours=resolution_hours,
                )
                db.add(row)
                db.flush()
            seeded.append(row)
        db.flush()
        return seeded

    @staticmethod
    def ensure_eu_act_annex_mappings(db: Session) -> list[EUActAnnexMapping]:
        existing = {
            row.annex_ref: row
            for row in db.execute(select(EUActAnnexMapping)).scalars().all()
        }
        seeded: list[EUActAnnexMapping] = []
        for item in ANNEX_III_SECTORS:
            ref = str(item["ref"])
            row = existing.get(ref)
            if row is None:
                row = EUActAnnexMapping(
                    annex_ref=ref,
                    annex_type=str(item["type"]),
                    sector=str(item["sector"]),
                    description=str(item["description"]),
                    article_refs=list(item["articles"]),
                    is_active=True,
                )
                db.add(row)
                db.flush()
            else:
                row.annex_type = str(item["type"])
                row.sector = str(item["sector"])
                row.description = str(item["description"])
                row.article_refs = list(item["articles"])
                row.is_active = True
            seeded.append(row)
        db.flush()
        return seeded

    @staticmethod
    def ensure_connector_catalog(db: Session) -> list["ConnectorCatalogEntry"]:
        """Idempotently seed the connector marketplace catalog with real third-party systems.

        The marketplace's purpose is to list actual integration targets (Salesforce, Workday,
        ServiceNow, Okta, OpenMetadata, etc.) that a compliance org can enable and configure --
        these names are intentionally real, not scrubbed placeholders.
        """
        from app.models.connector_catalog_entry import ConnectorCatalogEntry

        catalog: tuple[tuple[str, str, str, dict], ...] = (
            (
                "Carbon accounting file ingest",
                "sustainability",
                "CSV or file-based greenhouse gas emissions import.",
                {
                    "type": "object",
                    "required": ["file_format"],
                    "properties": {"file_format": {"type": "string"}, "scope_mapping": {"type": "object"}},
                },
            ),
            (
                "XBRL disclosure export",
                "reporting",
                "Structured ESG disclosure export configuration.",
                {
                    "type": "object",
                    "required": ["taxonomy"],
                    "properties": {"taxonomy": {"type": "string"}, "entity_identifier": {"type": "string"}},
                },
            ),
            (
                "OpenMetadata",
                "data_governance",
                "Data catalog and lineage metadata sync via OpenMetadata's REST API.",
                {
                    "type": "object",
                    "required": ["base_url", "jwt_token"],
                    "properties": {"base_url": {"type": "string"}, "jwt_token": {"type": "string"}},
                },
            ),
            (
                "Okta",
                "identity_governance",
                "Identity provider sync for access review and segregation-of-duties evidence via Okta's API.",
                {
                    "type": "object",
                    "required": ["org_url", "api_token"],
                    "properties": {"org_url": {"type": "string"}, "api_token": {"type": "string"}},
                },
            ),
            (
                "Salesforce",
                "crm",
                "Customer relationship data sync for third-party risk and customer compliance context.",
                {
                    "type": "object",
                    "required": ["instance_url", "client_id", "client_secret"],
                    "properties": {
                        "instance_url": {"type": "string"},
                        "client_id": {"type": "string"},
                        "client_secret": {"type": "string"},
                    },
                },
            ),
            (
                "Workday",
                "hr",
                "Human capital management sync for employee lifecycle and access review evidence.",
                {
                    "type": "object",
                    "required": ["tenant_url", "client_id", "client_secret"],
                    "properties": {
                        "tenant_url": {"type": "string"},
                        "client_id": {"type": "string"},
                        "client_secret": {"type": "string"},
                    },
                },
            ),
            (
                "ServiceNow",
                "itsm",
                "IT service management sync for compliance issue and incident tracking.",
                {
                    "type": "object",
                    "required": ["instance_url", "username", "password"],
                    "properties": {
                        "instance_url": {"type": "string"},
                        "username": {"type": "string"},
                        "password": {"type": "string"},
                    },
                },
            ),
        )
        existing_names = {
            row.name for row in db.execute(select(ConnectorCatalogEntry)).scalars().all()
        }
        seeded: list[ConnectorCatalogEntry] = []
        for name, category, description, config_schema in catalog:
            if name in existing_names:
                continue
            row = ConnectorCatalogEntry(
                name=name,
                category=category,
                description=description,
                config_schema=config_schema,
                enabled=True,
            )
            db.add(row)
            db.flush()
            seeded.append(row)
        return seeded
