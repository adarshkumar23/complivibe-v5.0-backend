from fastapi import APIRouter
from app.ai_governance.routers import ai_systems as ai_governance_systems
from app.ai_governance.routers import atlas as ai_governance_atlas
from app.ai_governance.routers import shadow_ai as ai_governance_shadow_ai
from app.ai_governance.routers import ai_reviews as ai_governance_reviews
from app.ai_governance.routers import eu_act_workflows as ai_governance_eu_act_workflows
from app.ai_governance.routers import iso42001 as ai_governance_iso42001
from app.ai_governance.routers import nist_rmf as ai_governance_nist_rmf
from app.ai_governance.routers import third_party_ai as ai_governance_third_party_ai
from app.ai_governance.routers import guardrails as ai_governance_guardrails
from app.ai_governance.routers import approval_envelopes as ai_governance_approval_envelopes
from app.ai_governance.routers import ai_risk_assessments as ai_governance_risk_assessments
from app.ai_governance.routers import monitoring as ai_governance_monitoring
from app.ai_governance.routers import llm_observability as ai_governance_llm_observability
from app.ai_governance.routers import risk_signals as ai_governance_risk_signals
from app.ai_governance.routers import recommendations as ai_governance_recommendations
from app.ai_governance.routers import diagnostics as ai_governance_events_diagnostics
from app.ai_governance.routers import ai_governance_diagnostics as ai_governance_diagnostic_snapshots
from app.ai_governance.routers import mlops as ai_governance_mlops
from app.ai_governance.routers import mlops_ingest as ai_governance_mlops_ingest
from app.ai_governance.routers import mlops_management as ai_governance_mlops_management
from app.ai_governance.routers import contracts as ai_governance_contracts
from app.data_observability.routers import data_assets as data_observability_assets
from app.data_observability.routers import lineage as data_observability_lineage
from app.data_observability.routers import quality as data_observability_quality
from app.data_observability.routers import access_monitoring as data_observability_access
from app.data_observability.routers import retention as data_observability_retention
from app.data_observability.routers import incidents as data_observability_incidents
from app.data_observability.routers import dashboard as data_observability_dashboard
from app.data_observability.routers import obligation_coverage as data_observability_obligation_coverage
from app.data_observability.routers import obligation_suggestions as data_observability_obligation_suggestions
from app.data_observability.routers import residency as data_observability_residency
from app.auth.routers import scim as auth_scim
from app.auth.routers import sso as auth_sso
from app.integrations.security.routers import fides as security_fides
from app.integrations.security.routers import ingest as security_ingest
from app.compliance.routers import business_units as compliance_business_units
from app.compliance.routers import board_scorecard as compliance_board_scorecard
from app.compliance.routers import copilot_draft as compliance_copilot_draft
from app.compliance.routers import compliance_risk_recommendations as compliance_risk_recommendations
from app.compliance.routers import policy_drafting as compliance_policy_drafting
from app.compliance.routers import policy_attestations as compliance_policy_attestations
from app.compliance.routers import policy_exceptions as compliance_policy_exceptions
from app.compliance.routers import policy_templates as compliance_policy_templates
from app.compliance.routers import policy_risk_links as compliance_policy_risk_links
from app.compliance.routers import policy_issue_links as compliance_policy_issue_links_v2
from app.compliance.routers import pbc_requests as compliance_pbc_requests
from app.compliance.routers import audit_findings as compliance_audit_findings
from app.compliance.routers import audit_evidence_packages as compliance_audit_evidence_packages
from app.exports.routers import entity_exports as platform_entity_exports
from app.platform.routers import rate_limits as platform_rate_limits
from app.platform.routers import report_sharing as platform_report_sharing
from app.platform.routers import siem as platform_siem
from app.platform.routers import billing as platform_billing
from app.platform.routers import email_config as platform_email_config
from app.platform.routers import custom_roles as platform_custom_roles
from app.platform.routers import sessions as platform_sessions
from app.platform.routers import ip_allowlist as platform_ip_allowlist
from app.platform.routers import onboarding as platform_onboarding
from app.privacy.routers import ropa as privacy_ropa
from app.privacy.routers import dsar as privacy_dsar
from app.privacy.routers import ccpa as privacy_ccpa
from app.privacy.routers import notices as privacy_notices
from app.privacy.routers import consent as privacy_consent
from app.privacy.routers import cookies as privacy_cookies
from app.privacy.routers import dpia as privacy_dpia
from app.privacy.routers import lawful_basis as privacy_lawful_basis
from app.privacy.routers import dpa as privacy_dpa
from app.privacy.routers import notification_preferences as privacy_notification_preferences
from app.privacy.routers import digest as privacy_digest
from app.satellites.tprm_intelligence import router as tprm_intelligence_router
from app.satellites.tprm_intelligence import sanctions_router as tprm_sanctions_router
from app.satellites.tprm_intelligence import bribery_router as tprm_bribery_router
from app.satellites.tprm_intelligence import export_control_router as tprm_export_control_router
from app.api.v1 import bcm
from app.api.v1 import crisis_management
from app.api.v1 import vendor_supply_chain
from app.api.v1 import vendor_concentration_risk
from app.api.v1 import legal_matters
from app.api.v1 import ip_assets
from app.api.v1 import content_provenance
from app.api.v1 import training_datasets
from app.api.v1 import synthetic_datasets
from app.api.v1 import geopolitical_risk
from app.api.v1 import ot_ics
from app.api.v1 import ai_usage_compliance
from app.api.v1 import training_analytics
from app.api.v1 import risk_quantification
from app.api.v1 import risk_dependencies
from app.api.v1 import resilience_testing
from app.api.v1 import whistleblower
from app.api.v1 import search as search_api
from app.api.v1 import experience as experience_api

from app.api.v1 import (
    admin_email_config,
    access_certifications,
    ai_governance,
    ai_systems,
    compliance_contracts,
    certification_programs,
    compliance_dashboard,
    compliance_policies,
    compliance_deadlines,
    common_controls,
    employee_attestations,
    audit_engagements,
    audit_schedules,
    pbc_items,
    auditor_portal,
    auditor_marketplace,
    audit_findings,
    evidence_packages,
    policy_exceptions,
    policy_issue_links,
    policy_risk_mappings,
    technical_controls,
    oscal,
    compliance_risks,
    risk_appetite,
    risk_indicators,
    risk_scores,
    risk_settings,
    control_exceptions,
    control_monitoring_alerts,
    control_monitoring,
    control_monitoring_rules,
    automation,
    audit_logs,
    auth,
    controls,
    control_tests,
    control_recommendations,
    framework_content,
    framework_pack_reviews,
    framework_review_capacity,
    dashboard,
    governance,
    governance_overrides,
    governance_override_templates,
    email,
    evidence,
    exports,
    frameworks,
    health,
    memberships,
    non_human_identities,
    obligations,
    organizations,
    pam_sessions,
    regulatory_alerts,
    recertification,
    reports,
    custom_reports,
    risks,
    roles,
    scoring,
    tasks,
    users,
    vendors,
    questionnaire_templates,
    questionnaire_responses,
    scoring_rules,
    inbound_questionnaires,
    subprocessors,
    customer_commitments,
    escalation_policies,
    issues,
    issue_settings,
    sla_policies,
    breach_notifications,
    dora,
    incident_analytics,
    trust_center_public,
    trust_center_admin,
    ai_vendor_assessments,
    vendor_mitigation,
    vendor_remediation_portal,
    ai_governance_dashboard,
    ai_drafting,
    scheduler_admin,
    sod_conflicts,
    webhooks,
    offboarding,
    attestations,
    attestation_tokens,
    carbon_accounting,
    connector_marketplace,
    import_jobs,
    pricing,
    roi_calculator,
    evidence_automation,
    compliance_bot,
    issue_sync,
)

api_router = APIRouter()
api_router.include_router(ai_governance_atlas.atlas_router)
api_router.include_router(ai_governance_atlas.systems_router)
api_router.include_router(ai_governance_systems.router)
api_router.include_router(ai_governance_systems.scorecard_router)
api_router.include_router(ai_governance_shadow_ai.router)
api_router.include_router(ai_governance_reviews.router)
api_router.include_router(ai_governance_eu_act_workflows.router)
api_router.include_router(ai_governance_iso42001.router)
api_router.include_router(ai_governance_nist_rmf.router)
api_router.include_router(ai_governance_third_party_ai.router)
api_router.include_router(ai_governance_guardrails.router)
api_router.include_router(ai_governance_guardrails.events_router)
api_router.include_router(ai_governance_approval_envelopes.router)
api_router.include_router(ai_governance_monitoring.router)
api_router.include_router(ai_governance_monitoring.inbound_router)
api_router.include_router(ai_governance_llm_observability.router)
api_router.include_router(ai_governance_risk_signals.router)
api_router.include_router(ai_governance_recommendations.router)
api_router.include_router(ai_governance_events_diagnostics.router)
api_router.include_router(ai_governance_diagnostic_snapshots.router)
api_router.include_router(ai_governance_mlops.router)
api_router.include_router(ai_governance_mlops_ingest.router)
api_router.include_router(ai_governance_mlops_management.org_router)
api_router.include_router(ai_governance_mlops_management.mlflow_router)
api_router.include_router(ai_governance_mlops_management.coverage_router)
api_router.include_router(ai_governance_contracts.router)
api_router.include_router(data_observability_assets.router)
api_router.include_router(data_observability_lineage.router)
api_router.include_router(data_observability_quality.router)
api_router.include_router(data_observability_access.router)
api_router.include_router(data_observability_retention.router)
api_router.include_router(data_observability_incidents.router)
api_router.include_router(data_observability_dashboard.router)
api_router.include_router(data_observability_obligation_coverage.router)
api_router.include_router(data_observability_obligation_suggestions.router)
api_router.include_router(data_observability_residency.router)
api_router.include_router(privacy_ropa.router)
api_router.include_router(privacy_dsar.router)
api_router.include_router(privacy_ccpa.router)
api_router.include_router(privacy_notices.router)
api_router.include_router(privacy_consent.router)
api_router.include_router(privacy_cookies.router)
api_router.include_router(privacy_dpia.router)
api_router.include_router(privacy_lawful_basis.router)
api_router.include_router(privacy_dpa.router)
api_router.include_router(privacy_notification_preferences.router)
api_router.include_router(privacy_digest.router)
api_router.include_router(ai_governance_risk_assessments.systems_router)
api_router.include_router(ai_governance_risk_assessments.router)
api_router.include_router(ai_governance.router)
api_router.include_router(ai_governance_dashboard.router)
api_router.include_router(ai_drafting.router)
api_router.include_router(admin_email_config.router)
api_router.include_router(ai_systems.router)
api_router.include_router(automation.router)
api_router.include_router(health.router)
api_router.include_router(platform_entity_exports.router)
api_router.include_router(compliance_policy_drafting.router)
# employee_attestations and policy_exceptions register literal sibling paths
# (/attestation-campaigns/dashboard, /policy-exceptions/dashboard) that a
# same-prefix parameterized route ({campaign_id}/{exception_id}) registered
# earlier would otherwise shadow -- FastAPI matches routes in registration
# order, so the literal-path routers must come first.
api_router.include_router(employee_attestations.router)
api_router.include_router(policy_exceptions.router)
api_router.include_router(compliance_policy_attestations.router)
api_router.include_router(compliance_policy_exceptions.router)
api_router.include_router(compliance_policy_templates.router)
api_router.include_router(compliance_policy_risk_links.router)
api_router.include_router(compliance_policy_issue_links_v2.router)
api_router.include_router(compliance_pbc_requests.router)
api_router.include_router(compliance_audit_findings.router)
api_router.include_router(compliance_audit_evidence_packages.router)
api_router.include_router(platform_custom_roles.router)
api_router.include_router(platform_sessions.router)
api_router.include_router(platform_ip_allowlist.router)
api_router.include_router(organizations.router)
api_router.include_router(auth.router)
api_router.include_router(auth_sso.router)
api_router.include_router(auth_scim.router)
api_router.include_router(platform_rate_limits.router)
api_router.include_router(import_jobs.router)
api_router.include_router(platform_siem.router)
api_router.include_router(platform_report_sharing.router)
api_router.include_router(platform_billing.router)
api_router.include_router(platform_email_config.router)
api_router.include_router(platform_onboarding.router)
api_router.include_router(security_ingest.router)
api_router.include_router(security_fides.router)
api_router.include_router(compliance_business_units.router)
api_router.include_router(compliance_board_scorecard.router)
api_router.include_router(compliance_copilot_draft.router)
api_router.include_router(compliance_risk_recommendations.router)
api_router.include_router(users.router)
api_router.include_router(memberships.router)
api_router.include_router(non_human_identities.router)
api_router.include_router(pam_sessions.router)
api_router.include_router(access_certifications.router)
api_router.include_router(roles.router)
api_router.include_router(sod_conflicts.router)
api_router.include_router(audit_logs.router)
api_router.include_router(frameworks.router)
api_router.include_router(frameworks.compliance_router)
api_router.include_router(frameworks.semantic_router)
api_router.include_router(framework_pack_reviews.router)
api_router.include_router(framework_pack_reviews.queue_router)
api_router.include_router(framework_review_capacity.router)
api_router.include_router(obligations.router)
api_router.include_router(obligations.compliance_router)
api_router.include_router(regulatory_alerts.router)
api_router.include_router(controls.router)
api_router.include_router(control_tests.router)
api_router.include_router(control_recommendations.router)
api_router.include_router(framework_content.router)
api_router.include_router(evidence.router)
api_router.include_router(evidence_automation.router)
api_router.include_router(compliance_bot.router)
api_router.include_router(issue_sync.router)
api_router.include_router(risks.router)
api_router.include_router(recertification.router)
api_router.include_router(reports.router)
api_router.include_router(reports.compliance_router)
api_router.include_router(custom_reports.router)
api_router.include_router(tasks.router)
api_router.include_router(scoring.router)
api_router.include_router(dashboard.router)
api_router.include_router(governance.router)
api_router.include_router(governance_overrides.router)
api_router.include_router(governance_override_templates.router)
api_router.include_router(compliance_policies.router)
api_router.include_router(compliance_contracts.router)
api_router.include_router(compliance_dashboard.router)
api_router.include_router(compliance_deadlines.router)
api_router.include_router(common_controls.router)
api_router.include_router(audit_engagements.router)
api_router.include_router(audit_schedules.router)
api_router.include_router(pbc_items.router)
api_router.include_router(auditor_portal.router)
api_router.include_router(auditor_marketplace.public_router)
api_router.include_router(auditor_marketplace.router)
api_router.include_router(audit_findings.router)
api_router.include_router(evidence_packages.router)
api_router.include_router(policy_issue_links.router)
api_router.include_router(policy_risk_mappings.router)
api_router.include_router(technical_controls.router)
api_router.include_router(technical_controls.ingest_router)
api_router.include_router(oscal.router)
api_router.include_router(compliance_risks.router)
api_router.include_router(risk_appetite.router)
api_router.include_router(risk_indicators.router)
api_router.include_router(risk_scores.router)
api_router.include_router(risk_settings.router)
api_router.include_router(control_exceptions.router)
api_router.include_router(control_monitoring_alerts.router)
api_router.include_router(control_monitoring.router)
api_router.include_router(control_monitoring_rules.router)
api_router.include_router(exports.router)
api_router.include_router(attestations.router)
api_router.include_router(attestation_tokens.router)
api_router.include_router(email.router)
api_router.include_router(vendors.router)
api_router.include_router(vendor_supply_chain.router)
api_router.include_router(vendor_concentration_risk.router)
api_router.include_router(tprm_intelligence_router.router)
api_router.include_router(tprm_sanctions_router.router)
api_router.include_router(tprm_bribery_router.router)
api_router.include_router(tprm_export_control_router.router)
api_router.include_router(questionnaire_templates.router)
api_router.include_router(questionnaire_responses.router)
api_router.include_router(scoring_rules.router)
api_router.include_router(inbound_questionnaires.router)
api_router.include_router(subprocessors.router)
api_router.include_router(customer_commitments.router)
api_router.include_router(escalation_policies.router)
api_router.include_router(issues.router)
api_router.include_router(issue_settings.router)
api_router.include_router(sla_policies.router)
api_router.include_router(certification_programs.router)
api_router.include_router(breach_notifications.router)
api_router.include_router(dora.router)
api_router.include_router(issues.remediation_router)
api_router.include_router(incident_analytics.router)
api_router.include_router(trust_center_public.router)
api_router.include_router(trust_center_admin.router)
api_router.include_router(ai_vendor_assessments.router)
api_router.include_router(vendor_mitigation.router)
api_router.include_router(vendor_remediation_portal.router)
api_router.include_router(scheduler_admin.router)
api_router.include_router(webhooks.router)
api_router.include_router(offboarding.router)
api_router.include_router(carbon_accounting.router)
api_router.include_router(connector_marketplace.router)
api_router.include_router(pricing.router)
api_router.include_router(roi_calculator.router)
api_router.include_router(legal_matters.router)
api_router.include_router(ip_assets.router)
api_router.include_router(content_provenance.router)
api_router.include_router(training_datasets.router)
api_router.include_router(synthetic_datasets.router)
api_router.include_router(geopolitical_risk.router)
api_router.include_router(ot_ics.router)
api_router.include_router(ot_ics.ingest_router)
api_router.include_router(ai_usage_compliance.router)
api_router.include_router(training_analytics.router)
api_router.include_router(bcm.router)
api_router.include_router(crisis_management.router)
api_router.include_router(risk_quantification.router)
api_router.include_router(risk_dependencies.router)
api_router.include_router(resilience_testing.router)
api_router.include_router(whistleblower.router)
api_router.include_router(search_api.router)
api_router.include_router(experience_api.router)
