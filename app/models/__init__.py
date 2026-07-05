from app.models.audit_log import AuditLog
from app.models.atlas_technique import AtlasTechnique
from app.models.applicability_evaluation_result import ApplicabilityEvaluationResult
from app.models.applicability_evaluation_run import ApplicabilityEvaluationRun
from app.models.ai_system import AISystem
from app.models.ai_content_draft import AIContentDraft
from app.models.ai_draft_revision import AIDraftRevision
from app.models.ai_inline_suggestion import AIInlineSuggestion
from app.models.ai_governance_event import AIGovernanceEvent
from app.models.ai_governance_review import AIGovernanceReview
from app.models.ai_review_criteria_response import AIReviewCriteriaResponse
from app.models.ai_risk_classification import AIRiskClassification
from app.models.ai_use_case import AIUseCase
from app.models.ai_system_control_link import AISystemControlLink
from app.models.ai_system_evidence_link import AISystemEvidenceLink
from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.ai_system_risk_assessment_snapshot import AISystemRiskAssessmentSnapshot
from app.models.ai_system_risk_classification_record_snapshot import AISystemRiskClassificationRecordSnapshot
from app.models.ai_system_risk_classification_record import AISystemRiskClassificationRecord
from app.models.ai_system_risk_classification_taxonomy_template import AISystemRiskClassificationTaxonomyTemplate
from app.models.ai_system_risk_dimension_template import AISystemRiskDimensionTemplate
from app.models.ai_system_risk_scoring_profile import AISystemRiskScoringProfile
from app.models.ai_system_governance_freeze_window import AISystemGovernanceFreezeWindow
from app.models.ai_system_governance_guardrail_policy_set import AISystemGovernanceGuardrailPolicySet
from app.models.ai_system_governance_guardrail_policy_assignment import AISystemGovernanceGuardrailPolicyAssignment
from app.models.ai_system_governance_guardrail_policy_assignment_history import AISystemGovernanceGuardrailPolicyAssignmentHistory
from app.models.ai_system_governance_guardrail_policy_set_version import AISystemGovernanceGuardrailPolicySetVersion
from app.models.ai_system_governance_operator_acknowledgement import AISystemGovernanceOperatorAcknowledgement
from app.models.ai_system_governance_attestation import AISystemGovernanceAttestation
from app.models.ai_system_governance_review_event import AISystemGovernanceReviewEvent
from app.models.ai_system_governance_review_plan_constraint import AISystemGovernanceReviewPlanConstraint
from app.models.ai_system_governance_review_plan_run import AISystemGovernanceReviewPlanRun
from app.models.ai_system_governance_review_recurrence_template import AISystemGovernanceReviewRecurrenceTemplate
from app.models.ai_system_governance_review_reminder_policy import AISystemGovernanceReviewReminderPolicy
from app.models.ai_system_governance_review_sequence_pack import AISystemGovernanceReviewSequencePack
from app.models.ai_system_governance_review_sequence_run import AISystemGovernanceReviewSequenceRun
from app.models.ai_system_governance_review_sequence_step import AISystemGovernanceReviewSequenceStep
from app.models.ai_system_governance_policy_resolution_simulation_report import AISystemGovernancePolicyResolutionSimulationReport
from app.models.ai_system_governance_policy_resolution_simulation_diff_report import (
    AISystemGovernancePolicyResolutionSimulationDiffReport,
)
from app.models.ai_system_governance_policy_diff_gating_profile import (
    AISystemGovernancePolicyDiffGatingProfile,
)
from app.models.ai_system_governance_policy_diff_gating_report import (
    AISystemGovernancePolicyDiffGatingReport,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_profile import (
    AISystemGovernanceDiagnosticExportDiffGatingProfile,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_report import (
    AISystemGovernanceDiagnosticExportDiffGatingReport,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_report import (
    AISystemGovernanceDiagnosticExportDiffGatingCompareReport,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_version import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_report import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport,
)
from app.models.ai_system_governance_policy_diff_gating_compare_report import (
    AISystemGovernancePolicyDiffGatingCompareReport,
)
from app.models.ai_system_governance_policy_diff_gating_compare_preset import (
    AISystemGovernancePolicyDiffGatingComparePreset,
)
from app.models.ai_system_governance_policy_diff_gating_compare_preset_assignment import (
    AISystemGovernancePolicyDiffGatingComparePresetAssignment,
)
from app.models.ai_system_governance_policy_diff_gating_compare_preset_assignment_history import (
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory,
)
from app.models.ai_system_governance_policy_diff_gating_compare_preset_version import (
    AISystemGovernancePolicyDiffGatingComparePresetVersion,
)
from app.models.ai_system_governance_policy_diff_gating_compare_preset_report import (
    AISystemGovernancePolicyDiffGatingComparePresetReport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_report import (
    AISystemGovernancePresetAssignmentDiagnosticReport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_diff_report import (
    AISystemGovernancePresetAssignmentDiagnosticDiffReport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_export import (
    AISystemGovernancePresetAssignmentDiagnosticExport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_export_diff_report import (
    AISystemGovernancePresetAssignmentDiagnosticExportDiffReport,
)
from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.ai_system_risk_link import AISystemRiskLink
from app.models.automation_action_log import AutomationActionLog
from app.models.automation_rule import AutomationRule
from app.models.automation_rule_execution import AutomationRuleExecution
from app.models.automation_rule_version import AutomationRuleVersion
from app.models.control import Control
from app.models.control_test_definition import ControlTestDefinition
from app.models.control_test_run import ControlTestRun
from app.models.compliance_report import ComplianceReport
from app.models.compliance_report_section import ComplianceReportSection
from app.models.custom_report_template import CustomReportTemplate
from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_policy_version import CompliancePolicyVersion
from app.models.compliance_policy_approval_request import CompliancePolicyApprovalRequest
from app.models.compliance_policy_control_link import CompliancePolicyControlLink
from app.models.export_job import ExportJob
from app.models.export_job_event import ExportJobEvent
from app.models.export_attestation import ExportAttestation
from app.models.evidence_control_link import EvidenceControlLink
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.models.compliance_risk_recommendation import ComplianceRiskRecommendation
from app.models.billing_event import BillingEvent
from app.models.business_unit import BusinessUnit
from app.models.board_scorecard_snapshot import BoardScorecardSnapshot
from app.models.ai_governance_diagnostic_snapshot import AIGovernanceDiagnosticSnapshot
from app.models.evidence_item import EvidenceItem
from app.models.email_delivery_event import EmailDeliveryEvent
from app.models.email_outbox import EmailOutbox
from app.models.email_template import EmailTemplate
from app.models.digest_config import DigestConfig
from app.models.evidence_recertification_policy import EvidenceRecertificationPolicy
from app.models.framework import Framework
from app.models.framework_content_import import FrameworkContentImport
from app.models.framework_pack_coverage_report import FrameworkPackCoverageReport
from app.models.framework_pack_promotion_request import FrameworkPackPromotionRequest
from app.models.framework_pack_review_assignment import FrameworkPackReviewAssignment
from app.models.framework_pack_review_run import FrameworkPackReviewRun
from app.models.framework_pack_review_signoff import FrameworkPackReviewSignoff
from app.models.framework_review_batch_cancellation_request import FrameworkReviewBatchCancellationRequest
from app.models.framework_review_batch_assignment_item import FrameworkReviewBatchAssignmentItem
from app.models.framework_review_batch_assignment_run import FrameworkReviewBatchAssignmentRun
from app.models.framework_review_assignment_suggestion import FrameworkReviewAssignmentSuggestion
from app.models.framework_reviewer_capacity_policy import FrameworkReviewerCapacityPolicy
from app.models.framework_reviewer_workload_snapshot import FrameworkReviewerWorkloadSnapshot
from app.models.framework_review_escalation_event import FrameworkReviewEscalationEvent
from app.models.framework_review_sla_policy import FrameworkReviewSLAPolicy
from app.models.framework_section import FrameworkSection
from app.models.framework_version import FrameworkVersion
from app.models.governance_override_approval import GovernanceOverrideApproval
from app.models.governance_override_event import GovernanceOverrideEvent
from app.models.governance_override_request import GovernanceOverrideRequest
from app.models.governance_override_template import GovernanceOverrideTemplate
from app.models.governance_override_template_version import GovernanceOverrideTemplateVersion
from app.models.membership import Membership
from app.models.membership_activation_token import MembershipActivationToken
from app.models.obligation import Obligation
from app.models.obligation_applicability_rule import ObligationApplicabilityRule
from app.models.obligation_applicability_question import ObligationApplicabilityQuestion
from app.models.obligation_content_version import ObligationContentVersion
from app.models.obligation_control_suggestion import ObligationControlSuggestion
from app.models.obligation_evidence_requirement import ObligationEvidenceRequirement
from app.models.obligation_control_recommendation import ObligationControlRecommendation
from app.models.organization_applicability_answer import OrganizationApplicabilityAnswer
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.organization_governance_setting import OrganizationGovernanceSetting
from app.models.organization_governance_evidence_manifest import OrganizationGovernanceEvidenceManifest
from app.models.organization_governance_manifest_verification_event import OrganizationGovernanceManifestVerificationEvent
from app.models.organization_governance_setting_history import OrganizationGovernanceSettingHistory
from app.models.organization_internal_signing_key import OrganizationInternalSigningKey
from app.models.organization import Organization
from app.models.organization_ai_configuration import OrganizationAIConfiguration
from app.models.subscription_plan import SubscriptionPlan
from app.models.openscap_rule_mapping import OpenSCAPRuleMapping
from app.models.rate_limit_config import RateLimitConfig
from app.models.siem_export_config import SiemExportConfig
from app.models.siem_export_run import SiemExportRun
from app.models.scim_token import ScimToken
from app.models.security_scan_job import SecurityScanJob
from app.models.sso_config import SSOConfig
from app.models.oidc_config import OIDCConfig
from app.models.oidc_auth_state import OIDCAuthState
from app.models.shared_report_link import SharedReportLink
from app.models.team_invitation import TeamInvitation
from app.models.permission import Permission
from app.models.risk import Risk
from app.models.org_risk_settings import OrgRiskSettings
from app.models.governance_signal import GovernanceSignal
from app.models.governance_autopilot_policy import GovernanceAutopilotPolicy
from app.models.governance_autopilot_approval_policy import GovernanceAutopilotApprovalPolicy
from app.models.governance_autopilot_execution_intent import GovernanceAutopilotExecutionIntent
from app.models.governance_autopilot_execution_approval import GovernanceAutopilotExecutionApproval
from app.models.governance_autopilot_execution_approval_vote import GovernanceAutopilotExecutionApprovalVote
from app.models.governance_autopilot_runner_simulation import GovernanceAutopilotRunnerSimulation
from app.models.governance_autopilot_runner_admission import GovernanceAutopilotRunnerAdmission
from app.models.governance_autopilot_runner_session import GovernanceAutopilotRunnerSession
from app.models.governance_autopilot_runner_handshake import GovernanceAutopilotRunnerHandshake
from app.models.governance_autopilot_noop_runner_event import GovernanceAutopilotNoopRunnerEvent
from app.models.governance_recommendation_snapshot import GovernanceRecommendationSnapshot
from app.models.governance_recommendation_action_disposition import GovernanceRecommendationActionDisposition
from app.models.governance_copilot_draft_snapshot import GovernanceCopilotDraftSnapshot
from app.models.risk_control_link import RiskControlLink
from app.models.risk_evidence_link import RiskEvidenceLink
from app.models.recertification_action_log import RecertificationActionLog
from app.models.recertification_run import RecertificationRun
from app.models.recommendation_generation_run import RecommendationGenerationRun
from app.models.retention_policy import RetentionPolicy
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.score_snapshot import ScoreSnapshot
from app.models.task import Task
from app.models.user import User
from app.models.user_session import UserSession
from app.models.non_human_identity import NonHumanIdentity
from app.models.pam_session_record import PAMSessionRecord
from app.models.access_certification import AccessCertificationCampaign, AccessCertificationItem
from app.models.sod_conflict import SodConflictFinding, SodConflictRule
from app.models.aml_kyc_check import AmlKycCheck
from app.models.sanctions_entity import SanctionsEntity
from app.models.sanctions_screen_result import SanctionsScreenResult
from app.models.vendor import Vendor
from app.models.vendor_external_rating import VendorExternalRating
from app.models.vendor_threat_intelligence import VendorThreatIntelligence
from app.models.vendor_assessment import VendorAssessment
from app.models.vendor_assessment_question import VendorAssessmentQuestion
from app.models.vendor_risk_score import VendorRiskScore
from app.models.vendor_control_link import VendorControlLink
from app.models.questionnaire_template import QuestionnaireTemplate
from app.models.questionnaire_template_section import QuestionnaireTemplateSection
from app.models.questionnaire_template_question import QuestionnaireTemplateQuestion
from app.models.vendor_questionnaire_response import VendorQuestionnaireResponse
from app.models.vendor_questionnaire_answer import VendorQuestionnaireAnswer
from app.models.questionnaire_scoring_rule import QuestionnaireScoringRule
from app.models.compliance_certification import ComplianceCertification
from app.models.inbound_questionnaire_session import InboundQuestionnaireSession
from app.models.inbound_questionnaire_item import InboundQuestionnaireItem
from app.models.subprocessor import Subprocessor
from app.models.subprocessor_data_transfer import SubprocessorDataTransfer
from app.models.customer_commitment import CustomerCommitment
from app.models.eu_act_annex_mapping import EUActAnnexMapping
from app.models.eu_ai_act_classification import EUAIActClassification
from app.models.eu_act_conformity_assessment import EUActConformityAssessment
from app.models.eu_act_fria import EUActFRIA
from app.models.eu_act_post_market_plan import EUActPostMarketPlan
from app.models.commitment_notification_log import CommitmentNotificationLog
from app.models.trust_center_configuration import TrustCenterConfiguration
from app.models.trust_center_access_request import TrustCenterAccessRequest
from app.models.trust_center_published_policy import TrustCenterPublishedPolicy
from app.models.ai_vendor_assessment import AIVendorAssessment
from app.models.vendor_mitigation_case import VendorMitigationCase
from app.models.vendor_mitigation_action import VendorMitigationAction
from app.models.control_monitoring_definition import ControlMonitoringDefinition
from app.models.control_monitoring_result import ControlMonitoringResult
from app.models.control_monitoring_rule import ControlMonitoringRule
from app.models.control_monitoring_rule_execution import ControlMonitoringRuleExecution
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.compliance_deadline import ComplianceDeadline
from app.models.compliance_deadline_event import ComplianceDeadlineEvent
from app.models.risk_indicator import RiskIndicator
from app.models.risk_appetite_threshold import RiskAppetiteThreshold
from app.models.entity_risk_score import EntityRiskScore
from app.models.control_exception import ControlException
from app.models.control_exception_approval import ControlExceptionApproval
from app.models.common_control_mapping import CommonControlMapping
from app.models.common_control_evidence_coverage import CommonControlEvidenceCoverage
from app.models.oscal_export_job import OscalExportJob
from app.models.technical_control_agent import TechnicalControlAgent
from app.models.technical_control_rule import TechnicalControlRule
from app.models.technical_control_result import TechnicalControlResult
from app.models.policy_attestation_campaign import PolicyAttestationCampaign
from app.models.policy_attestation import PolicyAttestation
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.policy_exception import PolicyException
from app.models.policy_exception_approval import PolicyExceptionApproval
from app.models.policy_risk_mapping import PolicyRiskMapping
from app.models.policy_risk_link import PolicyRiskLink
from app.models.policy_template import PolicyTemplate
from app.models.policy_template_clone import PolicyTemplateClone
from app.models.policy_issue_link import PolicyIssueLink
from app.models.issue import Issue
from app.models.issue_transition import IssueTransition
from app.models.org_issue_settings import OrgIssueSettings
from app.models.issue_policy_link import IssuePolicyLink
from app.models.issue_control_link import IssueControlLink
from app.models.remediation_suggestion import RemediationSuggestion
from app.models.incident_classification import IncidentClassification
from app.models.root_cause_analysis import RootCauseAnalysis
from app.models.issue_sla_policy import IssueSLAPolicy
from app.models.issue_sla_tracking import IssueSLATracking
from app.models.escalation_policy import EscalationPolicy
from app.models.escalation_event import EscalationEvent
from app.models.breach_notification import BreachNotification
from app.models.dora_ict_register import DORAICTRegister
from app.models.shadow_ai_detection import ShadowAIDetection
from app.models.ai_risk_assessment import AIRiskAssessment
from app.models.ai_risk_assessment_question import AIRiskAssessmentQuestion
from app.models.ai_risk_assessment_response import AIRiskAssessmentResponse
from app.models.ai_bias_assessment import AIBiasAssessment
from app.models.iso42001_conformity_tracker import ISO42001ConformityTracker
from app.models.nist_ai_rmf_implementation import NISTAIRMFImplementation
from app.models.ai_rmf_function_response import AIRMFFunctionResponse
from app.models.third_party_ai_assessment import ThirdPartyAIAssessment
from app.models.model_card import ModelCard
from app.models.aibom_record import AIBOMRecord
from app.models.aibom_component import AIBOMComponent
from app.models.ai_policy_guardrail import AIPolicyGuardrail
from app.models.ai_guardrail_event import AIGuardrailEvent
from app.models.ai_approval_envelope import AIApprovalEnvelope
from app.models.ai_envelope_approval import AIEnvelopeApproval
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.models.ai_risk_signal import AIRiskSignal
from app.models.ai_risk_recommendation import AIRiskRecommendation
from app.models.mlops_integration import MLOpsIntegration
from app.models.mlflow_connection import MLflowConnection
from app.models.mlflow_model_registration import MLflowModelRegistration
from app.models.mlflow_drift_event import MLflowDriftEvent
from app.models.data_asset import DataAsset
from app.models.data_asset_risk_link import DataAssetRiskLink
from app.models.data_lineage_node import DataLineageNode
from app.models.data_lineage_edge import DataLineageEdge
from app.models.openmetadata_integration import OpenMetadataIntegration
from app.models.data_quality_config import DataQualityConfig
from app.models.data_quality_reading import DataQualityReading
from app.models.data_access_log import DataAccessLog
from app.models.data_access_anomaly_rule import DataAccessAnomalyRule
from app.models.data_retention_policy import DataRetentionPolicy
from app.models.data_retention_review import DataRetentionReview
from app.models.data_incident import DataIncident
from app.models.data_asset_obligation_link import DataAssetObligationLink
from app.models.data_obligation_suggestion import DataObligationSuggestion
from app.models.data_residency_policy import DataResidencyPolicy
from app.models.data_residency_violation import DataResidencyViolation
from app.models.org_email_config import OrgEmailConfig
from app.models.org_ip_allowlist import OrgIPAllowlist
from app.models.organization_export_setting import OrganizationExportSetting
from app.models.processing_activity import ProcessingActivity
from app.models.ropa_framework_link import RopaFrameworkLink
from app.models.dpia import DPIA
from app.models.dpia_checklist_item import DPIAChecklistItem
from app.models.lawful_basis_record import LawfulBasisRecord
from app.models.data_subject_request import DataSubjectRequest
from app.models.dpa_agreement import DPAAgreement
from app.models.dsr_fulfillment_step import DSRFulfillmentStep
from app.models.dsr_sla_tracking import DSRSLATracking
from app.models.privacy_notice import PrivacyNotice
from app.models.notice_user_acknowledgement import NoticeUserAcknowledgement
from app.models.consent_record import ConsentRecord
from app.models.google_consent_mode_event import GoogleConsentModeEvent
from app.models.cookie_registry import CookieRegistry
from app.models.consent_banner_config import ConsentBannerConfig
from app.models.regulatory_change_alert import RegulatoryChangeAlert
from app.models.user_notification_preference import UserNotificationPreference
from app.models.org_ai_config import OrgAIConfig
from app.models.draft_request import DraftRequest
from app.models.webhook_endpoint import WebhookEndpoint
from app.models.webhook_delivery import WebhookDelivery
from app.models.offboarding_configuration import OffboardingConfiguration
from app.models.offboarding_record import OffboardingRecord
from app.models.scheduler_run_log import SchedulerRunLog
from app.models.audit_engagement import AuditEngagement
from app.models.pbc_item import PbcItem
from app.models.pbc_request import PBCRequest
from app.models.auditor_portal_invitation import AuditorPortalInvitation
from app.models.audit_finding import AuditFinding
from app.models.audit_schedule import AuditSchedule
from app.models.evidence_package import EvidencePackage
from app.models.evidence_package_item import EvidencePackageItem

__all__ = [
    "Organization",
    "User",
    "Membership",
    "MembershipActivationToken",
    "Role",
    "Permission",
    "RolePermission",
    "AuditLog",
    "AIGovernanceEvent",
    "AIGovernanceReview",
    "AIReviewCriteriaResponse",
    "AIRiskClassification",
    "AISystem",
    "AIUseCase",
    "AISystemControlLink",
    "AISystemEvidenceLink",
    "AISystemRiskAssessment",
    "AISystemRiskAssessmentSnapshot",
    "AISystemRiskClassificationRecordSnapshot",
    "AISystemRiskClassificationRecord",
    "AISystemRiskClassificationTaxonomyTemplate",
    "AISystemRiskDimensionTemplate",
    "AISystemRiskScoringProfile",
    "AISystemGovernanceFreezeWindow",
    "AISystemGovernanceGuardrailPolicySet",
    "AISystemGovernanceGuardrailPolicyAssignment",
    "AISystemGovernanceGuardrailPolicyAssignmentHistory",
    "AISystemGovernanceGuardrailPolicySetVersion",
    "AISystemGovernanceOperatorAcknowledgement",
    "AISystemGovernanceReview",
    "AISystemGovernanceAttestation",
    "AISystemGovernanceReviewReminderPolicy",
    "AISystemGovernanceReviewEvent",
    "AISystemGovernanceReviewPlanConstraint",
    "AISystemGovernanceReviewRecurrenceTemplate",
    "AISystemGovernanceReviewPlanRun",
    "AISystemGovernanceReviewSequencePack",
    "AISystemGovernanceReviewSequenceStep",
    "AISystemGovernanceReviewSequenceRun",
    "AISystemGovernancePolicyResolutionSimulationReport",
    "AISystemGovernancePolicyResolutionSimulationDiffReport",
    "AISystemGovernancePolicyDiffGatingProfile",
    "AISystemGovernancePolicyDiffGatingReport",
    "AISystemGovernanceDiagnosticExportDiffGatingProfile",
    "AISystemGovernanceDiagnosticExportDiffGatingReport",
    "AISystemGovernanceDiagnosticExportDiffGatingCompareReport",
    "AISystemGovernanceDiagnosticExportDiffGatingComparePreset",
    "AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment",
    "AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory",
    "AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion",
    "AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport",
    "AISystemGovernancePolicyDiffGatingCompareReport",
    "AISystemGovernancePolicyDiffGatingComparePreset",
    "AISystemGovernancePolicyDiffGatingComparePresetAssignment",
    "AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory",
    "AISystemGovernancePolicyDiffGatingComparePresetVersion",
    "AISystemGovernancePolicyDiffGatingComparePresetReport",
    "AISystemGovernancePresetAssignmentDiagnosticReport",
    "AISystemGovernancePresetAssignmentDiagnosticDiffReport",
    "AISystemGovernancePresetAssignmentDiagnosticExport",
    "AISystemGovernancePresetAssignmentDiagnosticExportDiffReport",
    "AISystemRiskLink",
    "ApplicabilityEvaluationRun",
    "ApplicabilityEvaluationResult",
    "AutomationRule",
    "AutomationRuleVersion",
    "AutomationRuleExecution",
    "AutomationActionLog",
    "Framework",
    "FrameworkVersion",
    "FrameworkSection",
    "FrameworkContentImport",
    "FrameworkPackCoverageReport",
    "FrameworkPackReviewAssignment",
    "FrameworkPackReviewRun",
    "FrameworkPackReviewSignoff",
    "FrameworkReviewBatchCancellationRequest",
    "FrameworkReviewBatchAssignmentItem",
    "FrameworkReviewBatchAssignmentRun",
    "FrameworkReviewAssignmentSuggestion",
    "FrameworkReviewerCapacityPolicy",
    "FrameworkReviewerWorkloadSnapshot",
    "FrameworkPackPromotionRequest",
    "FrameworkReviewSLAPolicy",
    "FrameworkReviewEscalationEvent",
    "GovernanceOverrideRequest",
    "GovernanceOverrideApproval",
    "GovernanceOverrideEvent",
    "GovernanceOverrideTemplate",
    "GovernanceOverrideTemplateVersion",
    "OrganizationFramework",
    "OrganizationGovernanceSetting",
    "OrganizationGovernanceEvidenceManifest",
    "OrganizationGovernanceManifestVerificationEvent",
    "OrganizationGovernanceSettingHistory",
    "OrganizationInternalSigningKey",
    "Obligation",
    "ObligationContentVersion",
    "ObligationApplicabilityQuestion",
    "ObligationApplicabilityRule",
    "ObligationEvidenceRequirement",
    "ObligationControlSuggestion",
    "ObligationControlRecommendation",
    "OrganizationApplicabilityAnswer",
    "OrganizationObligationState",
    "EmailTemplate",
    "EvidenceRecertificationPolicy",
    "EmailOutbox",
    "EmailDeliveryEvent",
    "Control",
    "ControlTestDefinition",
    "ControlTestRun",
    "ComplianceReport",
    "ComplianceReportSection",
    "CustomReportTemplate",
    "CompliancePolicy",
    "CompliancePolicyVersion",
    "CompliancePolicyApprovalRequest",
    "CompliancePolicyControlLink",
    "ExportJob",
    "ExportJobEvent",
    "ExportAttestation",
    "EvidenceControlLink",
    "ControlObligationMapping",
    "EvidenceItem",
    "Risk",
    "OrgRiskSettings",
    "GovernanceSignal",
    "GovernanceAutopilotPolicy",
    "GovernanceAutopilotApprovalPolicy",
    "GovernanceAutopilotExecutionIntent",
    "GovernanceAutopilotExecutionApproval",
    "GovernanceAutopilotExecutionApprovalVote",
    "GovernanceAutopilotRunnerSimulation",
    "GovernanceAutopilotRunnerAdmission",
    "GovernanceAutopilotRunnerSession",
    "GovernanceAutopilotRunnerHandshake",
    "GovernanceAutopilotNoopRunnerEvent",
    "GovernanceRecommendationSnapshot",
    "GovernanceRecommendationActionDisposition",
    "GovernanceCopilotDraftSnapshot",
    "RiskControlLink",
    "RiskEvidenceLink",
    "RecertificationRun",
    "RecertificationActionLog",
    "RecommendationGenerationRun",
    "RetentionPolicy",
    "Task",
    "ScoreSnapshot",
    "AmlKycCheck",
    "SanctionsEntity",
    "SanctionsScreenResult",
    "Vendor",
    "VendorExternalRating",
    "VendorThreatIntelligence",
    "VendorAssessment",
    "VendorAssessmentQuestion",
    "VendorRiskScore",
    "VendorControlLink",
    "QuestionnaireTemplate",
    "QuestionnaireTemplateSection",
    "QuestionnaireTemplateQuestion",
    "VendorQuestionnaireResponse",
    "VendorQuestionnaireAnswer",
    "QuestionnaireScoringRule",
    "ComplianceCertification",
    "InboundQuestionnaireSession",
    "InboundQuestionnaireItem",
    "Subprocessor",
    "SubprocessorDataTransfer",
    "CustomerCommitment",
    "EUActAnnexMapping",
    "EUAIActClassification",
    "EUActConformityAssessment",
    "EUActFRIA",
    "EUActPostMarketPlan",
    "CommitmentNotificationLog",
    "TrustCenterConfiguration",
    "TrustCenterAccessRequest",
    "TrustCenterPublishedPolicy",
    "AIVendorAssessment",
    "VendorMitigationCase",
    "VendorMitigationAction",
    "ControlMonitoringDefinition",
    "ControlMonitoringResult",
    "ControlMonitoringRule",
    "ControlMonitoringRuleExecution",
    "ControlMonitoringAlert",
    "ComplianceDeadline",
    "ComplianceDeadlineEvent",
    "RiskIndicator",
    "RiskAppetiteThreshold",
    "EntityRiskScore",
    "ControlException",
    "ControlExceptionApproval",
    "CommonControlMapping",
    "CommonControlEvidenceCoverage",
    "OscalExportJob",
    "TechnicalControlAgent",
    "TechnicalControlRule",
    "TechnicalControlResult",
    "PolicyAttestationCampaign",
    "PolicyAttestationRecord",
    "PolicyException",
    "PolicyExceptionApproval",
    "PolicyRiskMapping",
    "PolicyRiskLink",
    "PolicyIssueLink",
    "Issue",
    "IssueTransition",
    "OrgIssueSettings",
    "IssuePolicyLink",
    "IssueControlLink",
    "RemediationSuggestion",
    "IncidentClassification",
    "RootCauseAnalysis",
    "IssueSLAPolicy",
    "IssueSLATracking",
    "EscalationPolicy",
    "EscalationEvent",
    "BreachNotification",
    "ShadowAIDetection",
    "AIRiskAssessment",
    "AIRiskAssessmentQuestion",
    "AIRiskAssessmentResponse",
    "AIBiasAssessment",
    "ISO42001ConformityTracker",
    "NISTAIRMFImplementation",
    "AIRMFFunctionResponse",
    "ThirdPartyAIAssessment",
    "ModelCard",
    "AIBOMRecord",
    "AIBOMComponent",
    "AIPolicyGuardrail",
    "AIGuardrailEvent",
    "AIApprovalEnvelope",
    "AIEnvelopeApproval",
    "AIMonitoringConfig",
    "AIMonitoringReading",
    "AIRiskSignal",
    "AIRiskRecommendation",
    "ComplianceRiskRecommendation",
    "MLOpsIntegration",
    "DataAsset",
    "DataLineageNode",
    "DataLineageEdge",
    "OpenMetadataIntegration",
    "DataQualityConfig",
    "DataQualityReading",
    "DataAccessLog",
    "DataAccessAnomalyRule",
    "DataRetentionPolicy",
    "DataRetentionReview",
    "DataIncident",
    "DataAssetObligationLink",
    "DataObligationSuggestion",
    "DataResidencyPolicy",
    "DataResidencyViolation",
    "OrgEmailConfig",
    "ProcessingActivity",
    "RopaFrameworkLink",
    "DPIA",
    "DPIAChecklistItem",
    "LawfulBasisRecord",
    "DataSubjectRequest",
    "DPAAgreement",
    "DSRFulfillmentStep",
    "DSRSLATracking",
    "PrivacyNotice",
    "NoticeUserAcknowledgement",
    "ConsentRecord",
    "GoogleConsentModeEvent",
    "CookieRegistry",
    "ConsentBannerConfig",
    "RegulatoryChangeAlert",
    "OrgAIConfig",
    "DraftRequest",
    "WebhookEndpoint",
    "WebhookDelivery",
    "OffboardingConfiguration",
    "OffboardingRecord",
    "SchedulerRunLog",
    "ScimToken",
    "OIDCConfig",
    "OIDCAuthState",
    "NonHumanIdentity",
    "PAMSessionRecord",
    "AccessCertificationCampaign",
    "AccessCertificationItem",
    "SodConflictRule",
    "SodConflictFinding",
    "SecurityScanJob",
    "OpenSCAPRuleMapping",
    "PolicyTemplate",
    "PolicyTemplateClone",
    "AuditEngagement",
    "PbcItem",
    "PBCRequest",
    "AuditorPortalInvitation",
    "AuditFinding",
    "AuditSchedule",
    "EvidencePackage",
    "EvidencePackageItem",
]
