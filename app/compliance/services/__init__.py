from __future__ import annotations

from importlib import import_module
from typing import Any

_SERVICE_MODULES = {
    "KRICalculator": "app.compliance.services.kri_calculator",
    "RiskGraphService": "app.compliance.services.risk_graph_service",
    "RiskAppetiteService": "app.compliance.services.risk_appetite_service",
    "RiskScoringService": "app.compliance.services.risk_scoring_service",
    "ControlExceptionService": "app.compliance.services.control_exception_service",
    "CommonControlsService": "app.compliance.services.common_controls_service",
    "OSCALExportService": "app.compliance.services.oscal_export_service",
    "TechnicalControlEvaluator": "app.compliance.services.technical_control_service",
    "TechnicalControlAgentService": "app.compliance.services.technical_control_service",
    "TechnicalControlRuleService": "app.compliance.services.technical_control_service",
    "TechnicalControlResultService": "app.compliance.services.technical_control_service",
    "AttestationCampaignService": "app.compliance.services.employee_attestation_service",
    "AttestationRecordService": "app.compliance.services.employee_attestation_service",
    "PolicyExceptionService": "app.compliance.services.policy_exception_service",
    "PolicyIssueLinkService": "app.compliance.services.policy_issue_link_service",
    "PolicyRiskMappingService": "app.compliance.services.policy_risk_mapping_service",
    "PolicyTemplateService": "app.compliance.services.policy_template_service",
    "AuditEngagementService": "app.compliance.services.audit_engagement_service",
    "PbcService": "app.compliance.services.pbc_service",
    "PBCRequestService": "app.compliance.services.pbc_request_service",
    "AuditorPortalService": "app.compliance.services.auditor_portal_service",
    "AuditFindingService": "app.compliance.services.audit_finding_service",
    "AuditScheduleService": "app.compliance.services.audit_schedule_service",
    "EvidencePackageService": "app.compliance.services.evidence_package_service",
    "QuestionnaireTemplateService": "app.compliance.services.questionnaire_template_service",
    "QuestionnaireScoringService": "app.compliance.services.questionnaire_scoring_service",
    "InboundQuestionnaireService": "app.compliance.services.inbound_questionnaire_service",
    "SubprocessorService": "app.compliance.services.subprocessor_service",
    "CustomerCommitmentService": "app.compliance.services.customer_commitment_service",
    "IssueService": "app.compliance.services.issue_service",
    "RCAService": "app.compliance.services.rca_service",
    "SLAService": "app.compliance.services.sla_service",
    "EscalationService": "app.compliance.services.escalation_service",
    "BreachNotificationService": "app.compliance.services.breach_notification_service",
    "IssuePolicyLinkService": "app.compliance.services.issue_policy_link_service",
    "IssueControlLinkService": "app.compliance.services.issue_control_link_service",
    "RemediationService": "app.compliance.services.remediation_service",
    "ClassificationService": "app.compliance.services.classification_service",
    "WebhookService": "app.compliance.services.webhook_service",
    "OffboardingService": "app.compliance.services.offboarding_service",
}

__all__ = list(_SERVICE_MODULES)


def __getattr__(name: str) -> Any:
    try:
        module_name = _SERVICE_MODULES[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
