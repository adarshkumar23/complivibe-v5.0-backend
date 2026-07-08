import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.ai_system_governance_review_plan_constraint import AISystemGovernanceReviewPlanConstraint
from app.models.ai_system_governance_review_plan_run import AISystemGovernanceReviewPlanRun
from app.models.ai_system_governance_review_recurrence_template import AISystemGovernanceReviewRecurrenceTemplate
from app.models.ai_system_governance_review_event import AISystemGovernanceReviewEvent
from app.models.ai_system_governance_freeze_window import AISystemGovernanceFreezeWindow
from app.models.ai_system_governance_guardrail_policy_assignment import AISystemGovernanceGuardrailPolicyAssignment
from app.models.ai_system_governance_guardrail_policy_assignment_history import (
    AISystemGovernanceGuardrailPolicyAssignmentHistory,
)
from app.models.ai_system_governance_guardrail_policy_set import AISystemGovernanceGuardrailPolicySet
from app.models.ai_system_governance_guardrail_policy_set_version import AISystemGovernanceGuardrailPolicySetVersion
from app.models.ai_system_governance_operator_acknowledgement import AISystemGovernanceOperatorAcknowledgement
from app.models.ai_system_governance_policy_resolution_simulation_report import (
    AISystemGovernancePolicyResolutionSimulationReport,
)
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
from app.models.ai_system_governance_review_reminder_policy import AISystemGovernanceReviewReminderPolicy
from app.models.ai_system_governance_review_sequence_pack import AISystemGovernanceReviewSequencePack
from app.models.ai_system_governance_review_sequence_run import AISystemGovernanceReviewSequenceRun
from app.models.ai_system_governance_review_sequence_step import AISystemGovernanceReviewSequenceStep
from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.ai_system_risk_assessment_snapshot import AISystemRiskAssessmentSnapshot
from app.models.ai_system_risk_classification_record_snapshot import AISystemRiskClassificationRecordSnapshot
from app.models.ai_system_risk_classification_record import AISystemRiskClassificationRecord
from app.models.ai_system_risk_classification_taxonomy_template import AISystemRiskClassificationTaxonomyTemplate
from app.models.ai_system_risk_dimension_template import AISystemRiskDimensionTemplate
from app.models.ai_system_risk_scoring_profile import AISystemRiskScoringProfile
from app.models.governance_signal import GovernanceSignal
from app.models.governance_autopilot_policy import GovernanceAutopilotPolicy
from app.models.governance_autopilot_approval_policy import GovernanceAutopilotApprovalPolicy
from app.models.governance_autopilot_execution_intent import GovernanceAutopilotExecutionIntent
from app.models.governance_autopilot_execution import GovernanceAutopilotExecution
from app.models.governance_autopilot_execution_approval import GovernanceAutopilotExecutionApproval
from app.models.governance_autopilot_execution_approval_vote import GovernanceAutopilotExecutionApprovalVote
from app.models.governance_autopilot_runner_simulation import GovernanceAutopilotRunnerSimulation
from app.models.governance_autopilot_runner_admission import GovernanceAutopilotRunnerAdmission
from app.models.governance_recommendation_snapshot import GovernanceRecommendationSnapshot
from app.models.governance_copilot_draft_snapshot import GovernanceCopilotDraftSnapshot
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.ai_system import (
    AISystemGovernanceReviewEventRead,
    AISystemGovernanceReviewEventResolveRequest,
    AISystemGovernanceFreezeWindowArchiveRequest,
    AISystemGovernanceFreezeWindowCreate,
    AISystemGovernanceFreezeWindowRead,
    AISystemGovernanceFreezeWindowUpdate,
    AISystemGovernanceGuardrailPolicySetActiveProfileResponse,
    AISystemGovernanceGuardrailPolicyAssignmentArchiveRequest,
    AISystemGovernanceGuardrailPolicyAssignmentCreate,
    AISystemGovernanceGuardrailPolicyAssignmentHistoryRead,
    AISystemGovernanceGuardrailPolicyAssignmentRead,
    AISystemGovernanceGuardrailPolicyAssignmentResolveRequest,
    AISystemGovernanceGuardrailPolicyAssignmentResolveResponse,
    AISystemGovernanceGuardrailPolicyAssignmentSummary,
    AISystemGovernanceGuardrailPolicyAssignmentUpdate,
    AISystemGovernancePolicyResolutionSimulationReportArchiveRequest,
    AISystemGovernancePolicyResolutionSimulationReportRead,
    AISystemGovernancePolicyResolutionSimulationDiffRequest,
    AISystemGovernancePolicyResolutionSimulationDiffResponse,
    AISystemGovernancePolicyResolutionSimulationDiffReportArchiveRequest,
    AISystemGovernancePolicyResolutionSimulationDiffReportRead,
    AISystemGovernancePolicyResolutionDiffReasonCodeCatalogResponse,
    AISystemGovernancePolicyDiffGatingProfileCreate,
    AISystemGovernancePolicyDiffGatingProfileUpdate,
    AISystemGovernancePolicyDiffGatingProfileArchiveRequest,
    AISystemGovernancePolicyDiffGatingProfileRead,
    AISystemGovernancePolicyDiffGatingClassifyRequest,
    AISystemGovernancePolicyDiffGatingClassifyResponse,
    AISystemGovernancePolicyDiffGatingReportRead,
    AISystemGovernancePolicyDiffGatingReportArchiveRequest,
    AISystemGovernancePolicyDiffGatingSummary,
    AISystemGovernancePolicyDiffGatingCompareRequest,
    AISystemGovernancePolicyDiffGatingCompareResponse,
    AISystemGovernancePolicyDiffGatingCompareReportRead,
    AISystemGovernancePolicyDiffGatingCompareReportArchiveRequest,
    AISystemGovernancePolicyDiffGatingCompareSummary,
    AISystemGovernancePolicyDiffGatingComparePresetCreate,
    AISystemGovernancePolicyDiffGatingComparePresetUpdate,
    AISystemGovernancePolicyDiffGatingComparePresetArchiveRequest,
    AISystemGovernancePolicyDiffGatingComparePresetRead,
    AISystemGovernancePolicyDiffGatingComparePresetVersionCreate,
    AISystemGovernancePolicyDiffGatingComparePresetVersionRead,
    AISystemGovernancePolicyDiffGatingComparePresetVersionActivateRequest,
    AISystemGovernancePolicyDiffGatingComparePresetVersionArchiveRequest,
    AISystemGovernancePolicyDiffGatingComparePresetPinVersionRequest,
    AISystemGovernancePolicyDiffGatingComparePresetUnpinVersionRequest,
    AISystemGovernancePolicyDiffGatingComparePresetPinningStatus,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentCreate,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentUpdate,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentArchiveRequest,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistoryRead,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentResolveRequest,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentResolveResponse,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsRequest,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsResponse,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentHealthDiagnosticsResponse,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageSummaryResponse,
    AISystemGovernancePresetAssignmentDiagnosticReportRead,
    AISystemGovernancePresetAssignmentDiagnosticReportArchiveRequest,
    AISystemGovernancePresetAssignmentDiagnosticDiffRequest,
    AISystemGovernancePresetAssignmentDiagnosticDiffResponse,
    AISystemGovernancePresetAssignmentDiagnosticDiffReportRead,
    AISystemGovernancePresetAssignmentDiagnosticDiffReportArchiveRequest,
    AISystemGovernancePresetAssignmentDiagnosticReportSummaryResponse,
    AISystemGovernancePresetAssignmentDiagnosticExportRead,
    AISystemGovernancePresetAssignmentDiagnosticExportCreateResponse,
    AISystemGovernancePresetAssignmentDiagnosticExportVerifyResponse,
    AISystemGovernancePresetAssignmentDiagnosticExportRevokeRequest,
    AISystemGovernancePresetAssignmentDiagnosticExportSummaryResponse,
    AISystemGovernancePresetAssignmentDiagnosticExportDiffRequest,
    AISystemGovernancePresetAssignmentDiagnosticExportDiffResponse,
    AISystemGovernancePresetAssignmentDiagnosticExportDiffReportRead,
    AISystemGovernancePresetAssignmentDiagnosticExportDiffReportArchiveRequest,
    AISystemGovernancePresetAssignmentDiagnosticExportDiffSummaryResponse,
    AISystemGovernancePresetAssignmentDiagnosticExportDiffReasonCodeCatalogResponse,
    AISystemGovernanceDiagnosticExportDiffGatingProfileCreate,
    AISystemGovernanceDiagnosticExportDiffGatingProfileUpdate,
    AISystemGovernanceDiagnosticExportDiffGatingProfileArchiveRequest,
    AISystemGovernanceDiagnosticExportDiffGatingProfileRead,
    AISystemGovernanceDiagnosticExportDiffGatingClassifyRequest,
    AISystemGovernanceDiagnosticExportDiffGatingClassifyResponse,
    AISystemGovernanceDiagnosticExportDiffGatingReportRead,
    AISystemGovernanceDiagnosticExportDiffGatingReportArchiveRequest,
    AISystemGovernanceDiagnosticExportDiffGatingSummary,
    AISystemGovernanceDiagnosticExportDiffGatingCompareRequest,
    AISystemGovernanceDiagnosticExportDiffGatingCompareResponse,
    AISystemGovernanceDiagnosticExportDiffGatingCompareReportRead,
    AISystemGovernanceDiagnosticExportDiffGatingCompareReportArchiveRequest,
    AISystemGovernanceDiagnosticExportDiffGatingCompareSummary,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetCreate,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetUpdate,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetArchiveRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCreate,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentUpdate,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentArchiveRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistoryRead,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentResolveRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentResolveResponse,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateDefaultRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateDefaultResponse,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentSummary,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsResponse,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHealthDiagnosticsResponse,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageSummaryResponse,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionCreate,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionActivateRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionArchiveRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetPinVersionRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetUnpinVersionRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetPinningStatus,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateResponse,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportRead,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportArchiveRequest,
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetSummary,
    AISystemGovernancePolicyDiffGatingComparePresetEvaluateDefaultRequest,
    AISystemGovernancePolicyDiffGatingComparePresetEvaluateDefaultResponse,
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentSummary,
    AISystemGovernancePolicyDiffGatingComparePresetEvaluateRequest,
    AISystemGovernancePolicyDiffGatingComparePresetEvaluateResponse,
    AISystemGovernancePolicyDiffGatingComparePresetReportRead,
    AISystemGovernancePolicyDiffGatingComparePresetReportArchiveRequest,
    AISystemGovernancePolicyDiffGatingComparePresetSummary,
    AISystemGovernancePhase5ContractsResponse,
    AISystemGovernancePhase5ContractGroup,
    AISystemGovernancePhase5CompatibilitySummaryResponse,
    AISystemGovernancePhase6ContractsResponse,
    AISystemGovernancePhase6ContractGroup,
    AISystemGovernancePhase7ContractsResponse,
    AISystemGovernancePhase7ContractGroup,
    AISystemGovernancePhase8ContractsResponse,
    AISystemGovernancePhase8ContractGroup,
    GovernanceAutopilotPolicyCreate,
    GovernanceAutopilotPolicyUpdate,
    GovernanceAutopilotPolicyArchiveRequest,
    GovernanceAutopilotPolicyRead,
    GovernanceAutopilotApprovalPolicyCreate,
    GovernanceAutopilotApprovalPolicyUpdate,
    GovernanceAutopilotApprovalPolicyArchiveRequest,
    GovernanceAutopilotApprovalPolicyRead,
    GovernanceAutopilotApprovalPolicySummary,
    GovernanceAutopilotEvaluateCandidateActionRequest,
    GovernanceAutopilotEvaluateCandidateActionResponse,
    GovernanceAutopilotEvaluateRecommendationSnapshotRequest,
    GovernanceAutopilotEvaluateRecommendationSnapshotResponse,
    GovernanceAutopilotEvaluateCopilotDraftSnapshotRequest,
    GovernanceAutopilotEvaluateCopilotDraftSnapshotResponse,
    GovernanceAutopilotSummary,
    GovernanceAutopilotCapabilitiesResponse,
    GovernanceAutopilotExecutionIntentPreviewCandidateActionRequest,
    GovernanceAutopilotExecutionIntentPreviewRecommendationSnapshotRequest,
    GovernanceAutopilotExecutionIntentPreviewCopilotDraftSnapshotRequest,
    GovernanceAutopilotExecutionIntentPreviewResponse,
    GovernanceAutopilotExecutionIntentCreate,
    GovernanceAutopilotExecutionIntentRead,
    GovernanceAutopilotExecutionIntentArchiveRequest,
    GovernanceAutopilotExecutionIntentSummary,
    GovernanceAutopilotExecutionApprovalRequestCreate,
    GovernanceAutopilotExecutionApprovalApproveRequest,
    GovernanceAutopilotExecutionApprovalRejectRequest,
    GovernanceAutopilotExecutionApprovalCancelRequest,
    GovernanceAutopilotExecutionReverseRequest,
    GovernanceAutopilotExecutionRead,
    GovernanceAutopilotExecutionApprovalRead,
    GovernanceAutopilotExecutionApprovalVoteApproveRequest,
    GovernanceAutopilotExecutionApprovalVoteRejectRequest,
    GovernanceAutopilotExecutionApprovalVoteRead,
    GovernanceAutopilotExecutionApprovalQuorumStatusResponse,
    GovernanceAutopilotExecutionIntentApprovalRequirementsResponse,
    GovernanceAutopilotExecutionIntentReadinessResponse,
    GovernanceAutopilotExecutionApprovalSummary,
    GovernanceAutopilotRunnerInterfaceContractResponse,
    GovernanceAutopilotRunnerHandoffPreviewRequest,
    GovernanceAutopilotRunnerHandoffPreviewResponse,
    GovernanceAutopilotRunnerSimulationCreate,
    GovernanceAutopilotRunnerSimulationRead,
    GovernanceAutopilotRunnerSimulationArchiveRequest,
    GovernanceAutopilotRunnerSimulationSummary,
    GovernanceAutopilotRunnerHandoffVerifyRequest,
    GovernanceAutopilotRunnerHandoffVerifyResponse,
    GovernanceAutopilotRunnerAdmissionPreviewRequest,
    GovernanceAutopilotRunnerAdmissionPreviewResponse,
    GovernanceAutopilotRunnerAdmissionCreateRequest,
    GovernanceAutopilotRunnerAdmissionRead,
    GovernanceAutopilotRunnerAdmissionTokenVerifyRequest,
    GovernanceAutopilotRunnerAdmissionTokenVerifyResponse,
    GovernanceAutopilotRunnerAdmissionRevokeRequest,
    GovernanceAutopilotRunnerAdmissionArchiveRequest,
    GovernanceAutopilotRunnerAdmissionSummary,
    GovernanceAutopilotRunnerSessionPreviewRequest,
    GovernanceAutopilotRunnerSessionPreviewResponse,
    GovernanceAutopilotRunnerSessionCreateRequest,
    GovernanceAutopilotRunnerSessionRead,
    GovernanceAutopilotRunnerSessionVerifyRequest,
    GovernanceAutopilotRunnerSessionVerifyResponse,
    GovernanceAutopilotRunnerSessionRevokeRequest,
    GovernanceAutopilotRunnerSessionArchiveRequest,
    GovernanceAutopilotRunnerSessionSummary,
    GovernanceAutopilotRunnerSessionExpireStaleResponse,
    GovernanceAutopilotRunnerHandshakeContractResponse,
    GovernanceAutopilotRunnerHandshakePreviewRequest,
    GovernanceAutopilotRunnerHandshakePreviewResponse,
    GovernanceAutopilotRunnerHandshakeCreateRequest,
    GovernanceAutopilotRunnerHandshakeRead,
    GovernanceAutopilotRunnerHandshakeVerifyRequest,
    GovernanceAutopilotRunnerHandshakeVerifyResponse,
    GovernanceAutopilotRunnerHandshakeRevokeRequest,
    GovernanceAutopilotRunnerHandshakeArchiveRequest,
    GovernanceAutopilotRunnerHandshakeSummary,
    GovernanceAutopilotNoopRunnerContractResponse,
    GovernanceAutopilotNoopRunnerEventPreviewRequest,
    GovernanceAutopilotNoopRunnerEventPreviewResponse,
    GovernanceAutopilotNoopRunnerEventCreateRequest,
    GovernanceAutopilotNoopRunnerEventRead,
    GovernanceAutopilotNoopRunnerEventVerifyRequest,
    GovernanceAutopilotNoopRunnerEventVerifyResponse,
    GovernanceAutopilotNoopRunnerEventArchiveRequest,
    GovernanceAutopilotNoopRunnerEventSummary,
    GovernanceAutopilotNoopRunnerLedgerRow,
    GovernanceAutopilotNoopRunnerTimelineReport,
    GovernanceAutopilotNoopRunnerBlockerReport,
    GovernanceAutopilotNoopRunnerReadinessReport,
    GovernanceAutopilotNoopRunnerIdempotencyReport,
    GovernanceAutopilotNoopRunnerControlPlaneHealthReport,
    GovernanceAutopilotNoopRunnerReportsContractResponse,
    GovernanceAutopilotNoopRunnerDiagnosticsManifestResponse,
    GovernanceAutopilotNoopRunnerBoundedExportResponse,
    GovernanceAutopilotNoopRunnerReportChecksumResponse,
    GovernanceAutopilotNoopRunnerCompatibilityPolicyResponse,
    GovernanceAutopilotNoopRunnerClientContractResponse,
    GovernanceAutopilotNoopRunnerFilterOptionsResponse,
    GovernanceAutopilotNoopRunnerPaginationContractResponse,
    GovernanceAutopilotNoopRunnerFieldDocsResponse,
    GovernanceAutopilotNoopRunnerDisplayMetadataResponse,
    GovernanceAutopilotNoopRunnerLocalizationMapResponse,
    GovernanceAutopilotNoopRunnerClientHintsResponse,
    AISystemRiskAssessmentArchiveRequest,
    AISystemRiskClassificationRecordArchiveRequest,
    AISystemRiskClassificationRecordCreate,
    AISystemRiskClassificationRecordRead,
    AISystemRiskClassificationRejectRequest,
    AISystemRiskClassificationRequestChangesRequest,
    AISystemRiskClassificationSubmitForReviewRequest,
    AISystemRiskClassificationMarkReviewedRequest,
    AISystemRiskClassificationSnapshotCreate,
    AISystemRiskClassificationSnapshotRead,
    AISystemRiskClassificationSummary,
    AISystemRiskClassificationTaxonomyTemplateArchiveRequest,
    AISystemRiskClassificationTaxonomyTemplateCreate,
    AISystemRiskClassificationTaxonomyTemplateRead,
    AISystemRiskClassificationTaxonomyTemplateUpdate,
    AISystemRiskAssessmentCreate,
    AISystemRiskAssessmentManualSnapshotRequest,
    AISystemRiskAssessmentRead,
    AISystemRiskAssessmentRecalculateRequest,
    AISystemRiskAssessmentApplyDimensionTemplateRequest,
    AISystemRiskAssessmentResidualRiskPreviewRequest,
    AISystemRiskAssessmentResidualRiskPreviewResponse,
    AISystemRiskAssessmentApplyResidualRiskRequest,
    AISystemRiskRefreshClassificationSignalsRequest,
    AISystemRiskRefreshClassificationSignalsResponse,
    AISystemRiskAssessmentSnapshotRead,
    GovernanceSignalAttentionRead,
    GovernanceSignalActionRequest,
    GovernanceSignalGroupRead,
    GovernanceSignalPrioritizedRead,
    GovernanceSignalPriorityExplanation,
    GovernanceSignalPrioritySummary,
    GovernanceSignalRead,
    GovernanceSignalSummary,
    GovernanceActionTemplateRead,
    GovernanceActionTemplateCatalogResponse,
    GovernanceCandidateActionRead,
    GovernanceAISystemCandidateActionsRead,
    GovernanceRiskAssessmentCandidateActionsRead,
    GovernanceCandidateActionSummary,
    GovernanceRecommendationSnapshotPreviewRequest,
    GovernanceRecommendationSnapshotCreateRequest,
    GovernanceRecommendationSnapshotPreviewResponse,
    GovernanceRecommendationSnapshotRead,
    GovernanceRecommendationSnapshotDiffResponse,
    GovernanceRecommendationSnapshotSummary,
    GovernanceRecommendationSnapshotActionsResponse,
    GovernanceRecommendationSnapshotActionRead,
    GovernanceRecommendationActionAcknowledgeRequest,
    GovernanceRecommendationActionDismissRequest,
    GovernanceRecommendationActionDeferRequest,
    GovernanceRecommendationActionAcceptRequest,
    GovernanceRecommendationActionDispositionRead,
    GovernanceRecommendationActionDispositionSummary,
    GovernanceCopilotDraftTypeCatalogResponse,
    GovernanceCopilotDraftTypeRead,
    GovernanceCopilotDraftPreviewRequest,
    GovernanceCopilotDraftPreviewRead,
    GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN,
    GOVERNANCE_COPILOT_SCOPE_TYPE_PATTERN,
    GovernanceCopilotDraftSnapshotPreviewRequest,
    GovernanceCopilotDraftSnapshotCreateRequest,
    GovernanceCopilotDraftSnapshotPreviewResponse,
    GovernanceCopilotDraftSnapshotRead,
    GovernanceCopilotDraftSnapshotDiffResponse,
    GovernanceCopilotDraftSnapshotSummary,
    AISystemRiskAssessmentSummary,
    AISystemRiskAssessmentUpdate,
    AISystemRiskDimensionTemplateCreate,
    AISystemRiskDimensionTemplateUpdate,
    AISystemRiskDimensionTemplateArchiveRequest,
    AISystemRiskDimensionTemplateRead,
    AISystemRiskDimensionTemplateSummary,
    AISystemRiskDimensionScorePreviewRequest,
    AISystemRiskDimensionScorePreviewResponse,
    AISystemRiskScorePreviewRequest,
    AISystemRiskScorePreviewResponse,
    AISystemRiskScoringProfileArchiveRequest,
    AISystemRiskScoringProfileCreate,
    AISystemRiskScoringProfileRead,
    AISystemRiskScoringProfileSummary,
    AISystemRiskScoringProfileUpdate,
    AISystemGovernancePolicyResolutionSimulationDiffSummary,
    AISystemGovernancePolicyResolutionSimulationRequest,
    AISystemGovernancePolicyResolutionSimulationResponse,
    AISystemGovernancePolicyResolutionSimulationSummary,
    AISystemGovernanceGuardrailPolicySetArchiveRequest,
    AISystemGovernanceGuardrailPolicySetCreate,
    AISystemGovernanceGuardrailPolicySetRead,
    AISystemGovernanceGuardrailPolicySetSummary,
    AISystemGovernanceGuardrailPolicySetUpdate,
    AISystemGovernanceGuardrailPolicySetVersionActivateRequest,
    AISystemGovernanceGuardrailPolicySetVersionCreate,
    AISystemGovernanceGuardrailPolicySetVersionRead,
    AISystemGovernanceGuardrailCheckRequest,
    AISystemGovernanceGuardrailCheckResponse,
    AISystemGovernanceGuardrailConflictPreviewResponse,
    AISystemGovernanceGuardrailFreezeMatch,
    AISystemGovernanceGuardrailSummary,
    AISystemGovernanceOperatorAcknowledgementRead,
    AISystemGovernanceReviewPlanConstraintArchiveRequest,
    AISystemGovernanceReviewPlanConstraintCreate,
    AISystemGovernanceReviewPlanConstraintRead,
    AISystemGovernanceReviewPlanConstraintSummary,
    AISystemGovernanceReviewPlanConstraintUpdate,
    AISystemGovernanceReviewPlanGenerateRequest,
    AISystemGovernanceReviewPlanGenerateResponse,
    AISystemGovernanceReviewPlanItem,
    AISystemGovernanceReviewPlanRunRead,
    AISystemGovernanceReviewPlanSkippedItem,
    AISystemGovernanceReviewQueueItem,
    AISystemGovernanceReviewRecurrenceSummary,
    AISystemGovernanceReviewRecurrenceTemplateArchiveRequest,
    AISystemGovernanceReviewRecurrenceTemplateCreate,
    AISystemGovernanceReviewRecurrenceTemplateRead,
    AISystemGovernanceReviewRecurrenceTemplateUpdate,
    AISystemGovernanceReviewSequenceGenerateRequest,
    AISystemGovernanceReviewSequenceGenerateResponse,
    AISystemGovernanceReviewSequencePackArchiveRequest,
    AISystemGovernanceReviewSequencePackCreate,
    AISystemGovernanceReviewSequencePackRead,
    AISystemGovernanceReviewSequencePackUpdate,
    AISystemGovernanceReviewSequencePlanItem,
    AISystemGovernanceReviewSequenceRunRead,
    AISystemGovernanceReviewSequenceSkippedItem,
    AISystemGovernanceReviewSequenceStepArchiveRequest,
    AISystemGovernanceReviewSequenceStepCreate,
    AISystemGovernanceReviewSequenceStepRead,
    AISystemGovernanceReviewSequenceStepUpdate,
    AISystemGovernanceReviewSequenceSummary,
    AISystemGovernanceReviewReminderPolicyCreate,
    AISystemGovernanceReviewReminderPolicyRead,
    AISystemGovernanceReviewReminderPolicyUpdate,
    AISystemGovernanceReviewScheduleEvaluateRequest,
    AISystemGovernanceReviewScheduleEvaluateResponse,
    AISystemGovernanceReviewScheduleSummary,
)
from app.services.ai_system_governance_recurrence_service import AISystemGovernanceRecurrenceService
from app.services.ai_system_risk_assessment_service import (
    AI_RISK_ASSESSMENT_CAVEAT,
    AI_RISK_CLASSIFICATION_CAVEAT,
    AI_RISK_DIMENSION_CAVEAT,
    AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
    AI_RISK_GOVERNANCE_SIGNAL_PRIORITY_CAVEAT,
    AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT,
    AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT,
    AI_RISK_SCORING_CAVEAT,
    AISystemRiskAssessmentService,
)
from app.services.ai_system_governance_schedule_service import AISystemGovernanceScheduleService
from app.services.ai_governance_contract_service import AIGovernanceContractService
from app.services.ai_system_governance_sequence_service import AISystemGovernanceSequenceService
from app.services.governance_copilot_draft_service import (
    GOVERNANCE_COPILOT_DRAFT_CAVEAT,
    GOVERNANCE_COPILOT_DRAFT_SNAPSHOT_CAVEAT,
    GovernanceCopilotDraftService,
)
from app.services.audit_service import AuditService
from app.services.rbac_service import RBACService

router = APIRouter(prefix="/ai-governance", tags=["ai_governance"])


@router.get("/contracts/phase5/compatibility-summary", response_model=AISystemGovernancePhase5CompatibilitySummaryResponse)
def get_phase5_contract_compatibility_summary(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePhase5CompatibilitySummaryResponse:
    _ = organization
    summary = AIGovernanceContractService().phase5_compatibility_summary()
    return AISystemGovernancePhase5CompatibilitySummaryResponse(**summary)


@router.get("/contracts/phase5", response_model=AISystemGovernancePhase5ContractsResponse)
def get_phase5_contracts(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePhase5ContractsResponse:
    _ = organization
    payload = AIGovernanceContractService().phase5_contracts_response()
    return AISystemGovernancePhase5ContractsResponse(**payload)


@router.get("/contracts/phase5/{group_key}", response_model=AISystemGovernancePhase5ContractGroup)
def get_phase5_contract_group(
    group_key: str,
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePhase5ContractGroup:
    _ = organization
    group = AIGovernanceContractService().get_phase5_contract(group_key)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract group not found")
    return AISystemGovernancePhase5ContractGroup(**group)


@router.get("/contracts/phase6", response_model=AISystemGovernancePhase6ContractsResponse)
def get_phase6_contracts(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePhase6ContractsResponse:
    _ = organization
    payload = AIGovernanceContractService().phase6_contracts_response()
    return AISystemGovernancePhase6ContractsResponse(**payload)


@router.get("/contracts/phase7", response_model=AISystemGovernancePhase7ContractsResponse)
def get_phase7_contracts(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePhase7ContractsResponse:
    _ = organization
    payload = AIGovernanceContractService().phase7_contracts_response()
    return AISystemGovernancePhase7ContractsResponse(**payload)


@router.get("/contracts/phase8", response_model=AISystemGovernancePhase8ContractsResponse)
def get_phase8_contracts(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePhase8ContractsResponse:
    _ = organization
    payload = AIGovernanceContractService().phase8_contracts_response()
    return AISystemGovernancePhase8ContractsResponse(**payload)


@router.post("/autopilot/policies", response_model=GovernanceAutopilotPolicyRead, status_code=status.HTTP_201_CREATED)
def create_governance_autopilot_policy(
    payload: GovernanceAutopilotPolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotPolicyRead:
    service = AISystemRiskAssessmentService(db)
    row = service.create_autopilot_policy(
        organization_id=organization.id,
        payload=payload.model_dump(),
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_policy.created",
        entity_type="governance_autopilot_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "mode": row.mode, "is_default": row.is_default},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_policy_read(service._autopilot_policy_payload(row))


@router.get("/autopilot/policies/resolved", response_model=GovernanceAutopilotPolicyRead)
def get_governance_autopilot_policy_resolved(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotPolicyRead:
    payload = AISystemRiskAssessmentService(db).resolved_autopilot_policy(organization_id=organization.id)
    return _governance_autopilot_policy_read(payload)


@router.get("/autopilot/policies", response_model=list[GovernanceAutopilotPolicyRead])
def list_governance_autopilot_policies(
    status_value: str | None = Query(default=None, alias="status", pattern="^(active|inactive|archived)$"),
    is_default: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotPolicyRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_autopilot_policies(
        organization_id=organization.id,
        status_value=status_value,
        is_default=is_default,
        limit=limit,
        offset=offset,
    )
    return [_governance_autopilot_policy_read(service._autopilot_policy_payload(row)) for row in rows]


@router.get("/autopilot/policies/{policy_id}", response_model=GovernanceAutopilotPolicyRead)
def get_governance_autopilot_policy_detail(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotPolicyRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_autopilot_policy(organization_id=organization.id, policy_id=policy_id)
    return _governance_autopilot_policy_read(service._autopilot_policy_payload(row))


@router.patch("/autopilot/policies/{policy_id}", response_model=GovernanceAutopilotPolicyRead)
def update_governance_autopilot_policy(
    policy_id: uuid.UUID,
    payload: GovernanceAutopilotPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotPolicyRead:
    service = AISystemRiskAssessmentService(db)
    row = service.update_autopilot_policy(
        organization_id=organization.id,
        policy_id=policy_id,
        payload=payload.model_dump(exclude_unset=True),
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_policy.updated",
        entity_type="governance_autopilot_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "mode": row.mode, "is_default": row.is_default},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_policy_read(service._autopilot_policy_payload(row))


@router.post("/autopilot/policies/{policy_id}/archive", response_model=GovernanceAutopilotPolicyRead)
def archive_governance_autopilot_policy(
    policy_id: uuid.UUID,
    payload: GovernanceAutopilotPolicyArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotPolicyRead:
    service = AISystemRiskAssessmentService(db)
    row = service.archive_autopilot_policy(
        organization_id=organization.id,
        policy_id=policy_id,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_policy.archived",
        entity_type="governance_autopilot_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "archived_at": row.archived_at.isoformat() if row.archived_at else None},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_policy_read(service._autopilot_policy_payload(row))


@router.post("/autopilot/policies/{policy_id}/set-default", response_model=GovernanceAutopilotPolicyRead)
def set_default_governance_autopilot_policy(
    policy_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotPolicyRead:
    service = AISystemRiskAssessmentService(db)
    row = service.set_default_autopilot_policy(
        organization_id=organization.id,
        policy_id=policy_id,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_policy.default_set",
        entity_type="governance_autopilot_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"is_default": row.is_default, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_policy_read(service._autopilot_policy_payload(row))


@router.post(
    "/autopilot/approval-policies",
    response_model=GovernanceAutopilotApprovalPolicyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_governance_autopilot_approval_policy(
    payload: GovernanceAutopilotApprovalPolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotApprovalPolicyRead:
    service = AISystemRiskAssessmentService(db)
    row = service.create_autopilot_approval_policy(
        organization_id=organization.id,
        payload=payload.model_dump(),
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_approval_policy.created",
        entity_type="governance_autopilot_approval_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "is_default": row.is_default, "minimum_approvals": row.minimum_approvals},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_approval_policy_read(service._autopilot_approval_policy_payload(row))


@router.get("/autopilot/approval-policies/resolved", response_model=GovernanceAutopilotApprovalPolicyRead)
def get_governance_autopilot_approval_policy_resolved(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotApprovalPolicyRead:
    payload = AISystemRiskAssessmentService(db).resolved_autopilot_approval_policy(organization_id=organization.id)
    return _governance_autopilot_approval_policy_read(payload)


@router.get("/autopilot/approval-policies/summary", response_model=GovernanceAutopilotApprovalPolicySummary)
def get_governance_autopilot_approval_policy_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotApprovalPolicySummary:
    payload = AISystemRiskAssessmentService(db).autopilot_approval_policy_summary(organization_id=organization.id)
    return GovernanceAutopilotApprovalPolicySummary(**payload)


@router.get("/autopilot/approval-policies", response_model=list[GovernanceAutopilotApprovalPolicyRead])
def list_governance_autopilot_approval_policies(
    status_value: str | None = Query(default=None, alias="status", pattern="^(active|inactive|archived)$"),
    is_default: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotApprovalPolicyRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_autopilot_approval_policies(
        organization_id=organization.id,
        status_value=status_value,
        is_default=is_default,
        limit=limit,
        offset=offset,
    )
    return [_governance_autopilot_approval_policy_read(service._autopilot_approval_policy_payload(row)) for row in rows]


@router.get("/autopilot/approval-policies/{policy_id}", response_model=GovernanceAutopilotApprovalPolicyRead)
def get_governance_autopilot_approval_policy_detail(
    policy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotApprovalPolicyRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_autopilot_approval_policy(
        organization_id=organization.id,
        approval_policy_id=policy_id,
    )
    return _governance_autopilot_approval_policy_read(service._autopilot_approval_policy_payload(row))


@router.patch("/autopilot/approval-policies/{policy_id}", response_model=GovernanceAutopilotApprovalPolicyRead)
def update_governance_autopilot_approval_policy(
    policy_id: uuid.UUID,
    payload: GovernanceAutopilotApprovalPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotApprovalPolicyRead:
    service = AISystemRiskAssessmentService(db)
    row = service.update_autopilot_approval_policy(
        organization_id=organization.id,
        approval_policy_id=policy_id,
        payload=payload.model_dump(exclude_unset=True),
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_approval_policy.updated",
        entity_type="governance_autopilot_approval_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "is_default": row.is_default, "minimum_approvals": row.minimum_approvals},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_approval_policy_read(service._autopilot_approval_policy_payload(row))


@router.post("/autopilot/approval-policies/{policy_id}/archive", response_model=GovernanceAutopilotApprovalPolicyRead)
def archive_governance_autopilot_approval_policy(
    policy_id: uuid.UUID,
    payload: GovernanceAutopilotApprovalPolicyArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotApprovalPolicyRead:
    service = AISystemRiskAssessmentService(db)
    row = service.archive_autopilot_approval_policy(
        organization_id=organization.id,
        approval_policy_id=policy_id,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_approval_policy.archived",
        entity_type="governance_autopilot_approval_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "archived_at": row.archived_at.isoformat() if row.archived_at else None},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_approval_policy_read(service._autopilot_approval_policy_payload(row))


@router.post("/autopilot/approval-policies/{policy_id}/set-default", response_model=GovernanceAutopilotApprovalPolicyRead)
def set_default_governance_autopilot_approval_policy(
    policy_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotApprovalPolicyRead:
    service = AISystemRiskAssessmentService(db)
    row = service.set_default_autopilot_approval_policy(
        organization_id=organization.id,
        approval_policy_id=policy_id,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_approval_policy.default_set",
        entity_type="governance_autopilot_approval_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"is_default": row.is_default, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_approval_policy_read(service._autopilot_approval_policy_payload(row))


@router.post("/autopilot/evaluate-candidate-action", response_model=GovernanceAutopilotEvaluateCandidateActionResponse)
def evaluate_governance_autopilot_candidate_action(
    payload: GovernanceAutopilotEvaluateCandidateActionRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotEvaluateCandidateActionResponse:
    result = AISystemRiskAssessmentService(db).evaluate_candidate_action_against_policy(
        organization_id=organization.id,
        candidate_action_json=payload.candidate_action_json,
        policy_id=payload.policy_id,
    )
    return GovernanceAutopilotEvaluateCandidateActionResponse(**result)


@router.post(
    "/autopilot/evaluate-recommendation-snapshot",
    response_model=GovernanceAutopilotEvaluateRecommendationSnapshotResponse,
)
def evaluate_governance_autopilot_recommendation_snapshot(
    payload: GovernanceAutopilotEvaluateRecommendationSnapshotRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotEvaluateRecommendationSnapshotResponse:
    result = AISystemRiskAssessmentService(db).evaluate_recommendation_snapshot_against_policy(
        organization_id=organization.id,
        recommendation_snapshot_id=payload.recommendation_snapshot_id,
        policy_id=payload.policy_id,
    )
    return GovernanceAutopilotEvaluateRecommendationSnapshotResponse(**result)


@router.post(
    "/autopilot/evaluate-copilot-draft-snapshot",
    response_model=GovernanceAutopilotEvaluateCopilotDraftSnapshotResponse,
)
def evaluate_governance_autopilot_copilot_draft_snapshot(
    payload: GovernanceAutopilotEvaluateCopilotDraftSnapshotRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotEvaluateCopilotDraftSnapshotResponse:
    result = AISystemRiskAssessmentService(db).evaluate_copilot_draft_snapshot_against_policy(
        organization_id=organization.id,
        copilot_draft_snapshot_id=payload.copilot_draft_snapshot_id,
        policy_id=payload.policy_id,
    )
    return GovernanceAutopilotEvaluateCopilotDraftSnapshotResponse(**result)


@router.get("/autopilot/summary", response_model=GovernanceAutopilotSummary)
def get_governance_autopilot_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotSummary:
    payload = AISystemRiskAssessmentService(db).autopilot_policy_summary(organization_id=organization.id)
    return GovernanceAutopilotSummary(**payload)


@router.get("/autopilot/capabilities", response_model=GovernanceAutopilotCapabilitiesResponse)
def get_governance_autopilot_capabilities(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotCapabilitiesResponse:
    _ = organization
    return GovernanceAutopilotCapabilitiesResponse(**AISystemRiskAssessmentService.autopilot_capabilities())


@router.get(
    "/autopilot/runner-interface/contract",
    response_model=GovernanceAutopilotRunnerInterfaceContractResponse,
)
def get_governance_autopilot_runner_interface_contract(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerInterfaceContractResponse:
    _ = organization
    return GovernanceAutopilotRunnerInterfaceContractResponse(
        **AISystemRiskAssessmentService.autopilot_runner_interface_contract()
    )


@router.post(
    "/autopilot/runner-interface/verify-handoff",
    response_model=GovernanceAutopilotRunnerHandoffVerifyResponse,
)
def verify_governance_autopilot_runner_handoff(
    payload: GovernanceAutopilotRunnerHandoffVerifyRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerHandoffVerifyResponse:
    _ = organization
    result = AISystemRiskAssessmentService(db).verify_runner_handoff_payload(
        handoff_payload_json=payload.handoff_payload_json
    )
    return GovernanceAutopilotRunnerHandoffVerifyResponse(**result)


@router.post(
    "/autopilot/execution-intents/preview-candidate-action",
    response_model=GovernanceAutopilotExecutionIntentPreviewResponse,
)
def preview_governance_autopilot_execution_intent_candidate_action(
    payload: GovernanceAutopilotExecutionIntentPreviewCandidateActionRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionIntentPreviewResponse:
    result = AISystemRiskAssessmentService(db).preview_execution_intent_candidate_action(
        organization_id=organization.id,
        candidate_action_json=payload.candidate_action_json,
        policy_id=payload.policy_id,
    )
    return GovernanceAutopilotExecutionIntentPreviewResponse(**result)


@router.post(
    "/autopilot/execution-intents/preview-recommendation-snapshot",
    response_model=GovernanceAutopilotExecutionIntentPreviewResponse,
)
def preview_governance_autopilot_execution_intent_recommendation_snapshot(
    payload: GovernanceAutopilotExecutionIntentPreviewRecommendationSnapshotRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionIntentPreviewResponse:
    result = AISystemRiskAssessmentService(db).preview_execution_intent_recommendation_snapshot(
        organization_id=organization.id,
        recommendation_snapshot_id=payload.recommendation_snapshot_id,
        policy_id=payload.policy_id,
    )
    return GovernanceAutopilotExecutionIntentPreviewResponse(**result)


@router.post(
    "/autopilot/execution-intents/preview-copilot-draft-snapshot",
    response_model=GovernanceAutopilotExecutionIntentPreviewResponse,
)
def preview_governance_autopilot_execution_intent_copilot_draft_snapshot(
    payload: GovernanceAutopilotExecutionIntentPreviewCopilotDraftSnapshotRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionIntentPreviewResponse:
    result = AISystemRiskAssessmentService(db).preview_execution_intent_copilot_draft_snapshot(
        organization_id=organization.id,
        copilot_draft_snapshot_id=payload.copilot_draft_snapshot_id,
        policy_id=payload.policy_id,
    )
    return GovernanceAutopilotExecutionIntentPreviewResponse(**result)


@router.post(
    "/autopilot/execution-intents",
    response_model=GovernanceAutopilotExecutionIntentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_governance_autopilot_execution_intent(
    payload: GovernanceAutopilotExecutionIntentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotExecutionIntentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.create_execution_intent(
        organization_id=organization.id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        candidate_action_json=payload.candidate_action_json,
        policy_id=payload.policy_id,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_execution_intent.created",
        entity_type="governance_autopilot_execution_intent",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"intent_status": row.intent_status, "source_type": row.source_type},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_execution_intent_read(service.execution_intent_payload(row))


@router.get(
    "/autopilot/executions",
    response_model=list[GovernanceAutopilotExecutionRead],
)
def list_governance_autopilot_executions(
    execution_status: str | None = Query(default=None, pattern="^(executed|reversed)$"),
    execution_intent_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotExecutionRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_autopilot_executions(
        organization_id=organization.id,
        execution_status=execution_status,
        execution_intent_id=execution_intent_id,
        limit=limit,
        offset=offset,
    )
    return [GovernanceAutopilotExecutionRead(**service.autopilot_execution_payload(row)) for row in rows]


@router.get(
    "/autopilot/executions/{execution_id}",
    response_model=GovernanceAutopilotExecutionRead,
)
def get_governance_autopilot_execution_detail(
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_autopilot_execution(organization_id=organization.id, execution_id=execution_id)
    return GovernanceAutopilotExecutionRead(**service.autopilot_execution_payload(row))


@router.post(
    "/autopilot/executions/{execution_id}/reverse",
    response_model=GovernanceAutopilotExecutionRead,
)
def reverse_governance_autopilot_execution(
    execution_id: uuid.UUID,
    payload: GovernanceAutopilotExecutionReverseRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotExecutionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.reverse_autopilot_execution(
        organization_id=organization.id,
        execution_id=execution_id,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_execution.reversed",
        entity_type="governance_autopilot_execution",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "execution_status": row.execution_status,
            "execution_intent_id": str(row.execution_intent_id),
            "reversal_reason": row.reversal_reason,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return GovernanceAutopilotExecutionRead(**service.autopilot_execution_payload(row))


@router.post(
    "/autopilot/execution-intents/{intent_id}/runner-handoff/preview",
    response_model=GovernanceAutopilotRunnerHandoffPreviewResponse,
)
def preview_governance_autopilot_runner_handoff_for_execution_intent(
    intent_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerHandoffPreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerHandoffPreviewResponse:
    result = AISystemRiskAssessmentService(db).preview_runner_handoff_for_execution_intent(
        organization_id=organization.id,
        intent_id=intent_id,
        approval_id=payload.approval_id,
    )
    return GovernanceAutopilotRunnerHandoffPreviewResponse(**result)


@router.post(
    "/autopilot/execution-intents/{intent_id}/runner-simulations",
    response_model=GovernanceAutopilotRunnerSimulationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_governance_autopilot_runner_simulation(
    intent_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerSimulationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerSimulationRead:
    service = AISystemRiskAssessmentService(db)
    row = service.create_runner_simulation(
        organization_id=organization.id,
        intent_id=intent_id,
        approval_id=payload.approval_id,
        idempotency_key=payload.idempotency_key,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_runner_simulation.created",
        entity_type="governance_autopilot_runner_simulation",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "simulation_status": row.simulation_status,
            "execution_intent_id": str(row.execution_intent_id),
            "idempotency_key": row.idempotency_key,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_runner_simulation_read(service.runner_simulation_payload(row))


@router.get(
    "/autopilot/runner-simulations/summary",
    response_model=GovernanceAutopilotRunnerSimulationSummary,
)
def get_governance_autopilot_runner_simulation_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerSimulationSummary:
    payload = AISystemRiskAssessmentService(db).runner_simulation_summary(organization_id=organization.id)
    return GovernanceAutopilotRunnerSimulationSummary(**payload)


@router.get(
    "/autopilot/runner-simulations",
    response_model=list[GovernanceAutopilotRunnerSimulationRead],
)
def list_governance_autopilot_runner_simulations(
    execution_intent_id: uuid.UUID | None = Query(default=None),
    simulation_status: str | None = Query(
        default=None,
        pattern="^(ready_for_runner|not_ready|blocked|approval_required|policy_denied|capability_denied|archived)$",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotRunnerSimulationRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_runner_simulations(
        organization_id=organization.id,
        execution_intent_id=execution_intent_id,
        simulation_status=simulation_status,
        limit=limit,
        offset=offset,
    )
    return [_governance_autopilot_runner_simulation_read(service.runner_simulation_payload(row)) for row in rows]


@router.get(
    "/autopilot/runner-simulations/{simulation_id}",
    response_model=GovernanceAutopilotRunnerSimulationRead,
)
def get_governance_autopilot_runner_simulation_detail(
    simulation_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerSimulationRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_runner_simulation(
        organization_id=organization.id,
        simulation_id=simulation_id,
    )
    return _governance_autopilot_runner_simulation_read(service.runner_simulation_payload(row))


@router.post(
    "/autopilot/runner-simulations/{simulation_id}/archive",
    response_model=GovernanceAutopilotRunnerSimulationRead,
)
def archive_governance_autopilot_runner_simulation(
    simulation_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerSimulationArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerSimulationRead:
    service = AISystemRiskAssessmentService(db)
    row = service.archive_runner_simulation(
        organization_id=organization.id,
        simulation_id=simulation_id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_runner_simulation.archived",
        entity_type="governance_autopilot_runner_simulation",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"simulation_status": row.simulation_status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_runner_simulation_read(service.runner_simulation_payload(row))


@router.post(
    "/autopilot/runner-simulations/{simulation_id}/admission-preview",
    response_model=GovernanceAutopilotRunnerAdmissionPreviewResponse,
)
def preview_governance_autopilot_runner_admission(
    simulation_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerAdmissionPreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerAdmissionPreviewResponse:
    result = AISystemRiskAssessmentService(db).preview_runner_admission(
        organization_id=organization.id,
        simulation_id=simulation_id,
        token_expires_at=payload.token_expires_at,
    )
    return GovernanceAutopilotRunnerAdmissionPreviewResponse(**result)


@router.post(
    "/autopilot/runner-simulations/{simulation_id}/admissions",
    response_model=GovernanceAutopilotRunnerAdmissionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_governance_autopilot_runner_admission(
    simulation_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerAdmissionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerAdmissionRead:
    service = AISystemRiskAssessmentService(db)
    row, handoff_token, created_new = service.create_runner_admission(
        organization_id=organization.id,
        simulation_id=simulation_id,
        token_expires_at=payload.token_expires_at,
        actor_user_id=current_user.id,
    )
    if created_new:
        AuditService(db).write_audit_log(
            action="governance_autopilot_runner_admission.created",
            entity_type="governance_autopilot_runner_admission",
            entity_id=row.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "admission_status": row.admission_status,
                "runner_simulation_id": str(row.runner_simulation_id),
                "execution_intent_id": str(row.execution_intent_id),
                "idempotency_key": row.idempotency_key,
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
        db.refresh(row)
    payload_out = service.runner_admission_payload(row)
    payload_out["handoff_token"] = handoff_token
    return _governance_autopilot_runner_admission_read(payload_out)


@router.get(
    "/autopilot/runner-admissions/summary",
    response_model=GovernanceAutopilotRunnerAdmissionSummary,
)
def get_governance_autopilot_runner_admission_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerAdmissionSummary:
    payload = AISystemRiskAssessmentService(db).runner_admission_summary(organization_id=organization.id)
    return GovernanceAutopilotRunnerAdmissionSummary(**payload)


@router.get(
    "/autopilot/runner-admissions",
    response_model=list[GovernanceAutopilotRunnerAdmissionRead],
)
def list_governance_autopilot_runner_admissions(
    runner_simulation_id: uuid.UUID | None = Query(default=None),
    execution_intent_id: uuid.UUID | None = Query(default=None),
    admission_status: str | None = Query(default=None, pattern="^(admitted|blocked|revoked|expired|archived)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotRunnerAdmissionRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_runner_admissions(
        organization_id=organization.id,
        runner_simulation_id=runner_simulation_id,
        execution_intent_id=execution_intent_id,
        admission_status=admission_status,
        limit=limit,
        offset=offset,
    )
    return [_governance_autopilot_runner_admission_read(service.runner_admission_payload(row)) for row in rows]


@router.get(
    "/autopilot/runner-admissions/{admission_id}",
    response_model=GovernanceAutopilotRunnerAdmissionRead,
)
def get_governance_autopilot_runner_admission_detail(
    admission_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerAdmissionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_runner_admission(
        organization_id=organization.id,
        admission_id=admission_id,
    )
    return _governance_autopilot_runner_admission_read(service.runner_admission_payload(row))


@router.post(
    "/autopilot/runner-admissions/{admission_id}/verify-token",
    response_model=GovernanceAutopilotRunnerAdmissionTokenVerifyResponse,
)
def verify_governance_autopilot_runner_admission_token(
    admission_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerAdmissionTokenVerifyRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerAdmissionTokenVerifyResponse:
    result = AISystemRiskAssessmentService(db).verify_runner_admission_token(
        organization_id=organization.id,
        admission_id=admission_id,
        handoff_token=payload.handoff_token,
    )
    return GovernanceAutopilotRunnerAdmissionTokenVerifyResponse(**result)


@router.post(
    "/autopilot/runner-admissions/{admission_id}/revoke",
    response_model=GovernanceAutopilotRunnerAdmissionRead,
)
def revoke_governance_autopilot_runner_admission(
    admission_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerAdmissionRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerAdmissionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.revoke_runner_admission(
        organization_id=organization.id,
        admission_id=admission_id,
        revoke_reason=payload.revoke_reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_runner_admission.revoked",
        entity_type="governance_autopilot_runner_admission",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "admission_status": row.admission_status,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
            "revoke_reason": row.revoke_reason,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_runner_admission_read(service.runner_admission_payload(row))


@router.post(
    "/autopilot/runner-admissions/{admission_id}/archive",
    response_model=GovernanceAutopilotRunnerAdmissionRead,
)
def archive_governance_autopilot_runner_admission(
    admission_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerAdmissionArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerAdmissionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.archive_runner_admission(
        organization_id=organization.id,
        admission_id=admission_id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_runner_admission.archived",
        entity_type="governance_autopilot_runner_admission",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"admission_status": row.admission_status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_runner_admission_read(service.runner_admission_payload(row))


@router.post(
    "/autopilot/runner-admissions/{admission_id}/session-preview",
    response_model=GovernanceAutopilotRunnerSessionPreviewResponse,
)
def preview_governance_autopilot_runner_session(
    admission_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerSessionPreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerSessionPreviewResponse:
    result = AISystemRiskAssessmentService(db).preview_runner_session(
        organization_id=organization.id,
        admission_id=admission_id,
        handoff_token=payload.handoff_token,
        expires_at=payload.expires_at,
        max_attempts=payload.max_attempts,
        replay_window_seconds=payload.replay_window_seconds,
    )
    return GovernanceAutopilotRunnerSessionPreviewResponse(**result)


@router.post(
    "/autopilot/runner-admissions/{admission_id}/sessions",
    response_model=GovernanceAutopilotRunnerSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_governance_autopilot_runner_session(
    admission_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerSessionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerSessionRead:
    service = AISystemRiskAssessmentService(db)
    row, session_token = service.create_runner_session(
        organization_id=organization.id,
        admission_id=admission_id,
        handoff_token=payload.handoff_token,
        expires_at=payload.expires_at,
        max_attempts=payload.max_attempts,
        replay_window_seconds=payload.replay_window_seconds,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_runner_session.created",
        entity_type="governance_autopilot_runner_session",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "session_status": row.session_status,
            "runner_admission_id": str(row.runner_admission_id),
            "runner_simulation_id": str(row.runner_simulation_id),
            "execution_intent_id": str(row.execution_intent_id),
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "max_attempts": row.max_attempts,
            "replay_window_seconds": row.replay_window_seconds,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    out = service.runner_session_payload(row)
    out["session_token"] = session_token
    return _governance_autopilot_runner_session_read(out)


@router.get(
    "/autopilot/runner-sessions/summary",
    response_model=GovernanceAutopilotRunnerSessionSummary,
)
def get_governance_autopilot_runner_session_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerSessionSummary:
    payload = AISystemRiskAssessmentService(db).runner_session_summary(organization_id=organization.id)
    return GovernanceAutopilotRunnerSessionSummary(**payload)


@router.get(
    "/autopilot/runner-sessions",
    response_model=list[GovernanceAutopilotRunnerSessionRead],
)
def list_governance_autopilot_runner_sessions(
    runner_admission_id: uuid.UUID | None = Query(default=None),
    runner_simulation_id: uuid.UUID | None = Query(default=None),
    execution_intent_id: uuid.UUID | None = Query(default=None),
    session_status: str | None = Query(default=None, pattern="^(active|expired|locked|revoked|archived)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotRunnerSessionRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_runner_sessions(
        organization_id=organization.id,
        runner_admission_id=runner_admission_id,
        runner_simulation_id=runner_simulation_id,
        execution_intent_id=execution_intent_id,
        session_status=session_status,
        limit=limit,
        offset=offset,
    )
    return [_governance_autopilot_runner_session_read(service.runner_session_payload(row)) for row in rows]


@router.post(
    "/autopilot/runner-sessions/expire-stale",
    response_model=GovernanceAutopilotRunnerSessionExpireStaleResponse,
)
def expire_stale_governance_autopilot_runner_sessions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerSessionExpireStaleResponse:
    service = AISystemRiskAssessmentService(db)
    result = service.expire_stale_runner_sessions(organization_id=organization.id)
    for session_id in result["expired_session_ids"]:
        AuditService(db).write_audit_log(
            action="governance_autopilot_runner_session.expired",
            entity_type="governance_autopilot_runner_session",
            entity_id=session_id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"session_status": "expired"},
            metadata_json={"source": "api", "operation": "expire_stale"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    db.commit()
    return GovernanceAutopilotRunnerSessionExpireStaleResponse(**result)


@router.get(
    "/autopilot/runner-sessions/{session_id}",
    response_model=GovernanceAutopilotRunnerSessionRead,
)
def get_governance_autopilot_runner_session_detail(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerSessionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_runner_session(
        organization_id=organization.id,
        session_id=session_id,
    )
    return _governance_autopilot_runner_session_read(service.runner_session_payload(row))


@router.post(
    "/autopilot/runner-sessions/{session_id}/verify",
    response_model=GovernanceAutopilotRunnerSessionVerifyResponse,
)
def verify_governance_autopilot_runner_session(
    session_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerSessionVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerSessionVerifyResponse:
    service = AISystemRiskAssessmentService(db)
    result = service.verify_runner_session_token(
        organization_id=organization.id,
        session_id=session_id,
        session_token=payload.session_token,
    )
    if result.get("verified_now"):
        AuditService(db).write_audit_log(
            action="governance_autopilot_runner_session.verified",
            entity_type="governance_autopilot_runner_session",
            entity_id=session_id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"session_status": result["session_status"], "attempt_count": result["attempt_count"]},
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    if result.get("verification_failed_now"):
        AuditService(db).write_audit_log(
            action="governance_autopilot_runner_session.verification_failed",
            entity_type="governance_autopilot_runner_session",
            entity_id=session_id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "session_status": result["session_status"],
                "attempt_count": result["attempt_count"],
                "validation_errors": result["validation_errors"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    if result.get("locked_now"):
        AuditService(db).write_audit_log(
            action="governance_autopilot_runner_session.locked",
            entity_type="governance_autopilot_runner_session",
            entity_id=session_id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={"session_status": result["session_status"], "attempt_count": result["attempt_count"]},
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    db.commit()
    return GovernanceAutopilotRunnerSessionVerifyResponse(
        valid=result["valid"],
        expired=result["expired"],
        session_status=result["session_status"],
        attempt_count=result["attempt_count"],
        max_attempts=result["max_attempts"],
        replay_window_seconds=result["replay_window_seconds"],
        validation_errors=result["validation_errors"],
        last_verified_at=result.get("last_verified_at"),
        caveat=result["caveat"],
    )


@router.post(
    "/autopilot/runner-sessions/{session_id}/revoke",
    response_model=GovernanceAutopilotRunnerSessionRead,
)
def revoke_governance_autopilot_runner_session(
    session_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerSessionRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerSessionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.revoke_runner_session(
        organization_id=organization.id,
        session_id=session_id,
        revoke_reason=payload.revoke_reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_runner_session.revoked",
        entity_type="governance_autopilot_runner_session",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "session_status": row.session_status,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
            "revoke_reason": row.revoke_reason,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_runner_session_read(service.runner_session_payload(row))


@router.post(
    "/autopilot/runner-sessions/{session_id}/archive",
    response_model=GovernanceAutopilotRunnerSessionRead,
)
def archive_governance_autopilot_runner_session(
    session_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerSessionArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerSessionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.archive_runner_session(
        organization_id=organization.id,
        session_id=session_id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_runner_session.archived",
        entity_type="governance_autopilot_runner_session",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"session_status": row.session_status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_runner_session_read(service.runner_session_payload(row))


@router.get(
    "/autopilot/runner-handshake/contract",
    response_model=GovernanceAutopilotRunnerHandshakeContractResponse,
)
def get_governance_autopilot_runner_handshake_contract(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerHandshakeContractResponse:
    _ = organization
    payload = AISystemRiskAssessmentService(db).autopilot_runner_handshake_contract()
    return GovernanceAutopilotRunnerHandshakeContractResponse(**payload)


@router.post(
    "/autopilot/runner-sessions/{session_id}/handshake-preview",
    response_model=GovernanceAutopilotRunnerHandshakePreviewResponse,
)
def preview_governance_autopilot_runner_handshake(
    session_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerHandshakePreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerHandshakePreviewResponse:
    result = AISystemRiskAssessmentService(db).preview_runner_handshake(
        organization_id=organization.id,
        session_id=session_id,
        idempotency_key=payload.idempotency_key,
    )
    return GovernanceAutopilotRunnerHandshakePreviewResponse(**result)


@router.post(
    "/autopilot/runner-sessions/{session_id}/handshakes",
    response_model=GovernanceAutopilotRunnerHandshakeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_governance_autopilot_runner_handshake(
    session_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerHandshakeCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerHandshakeRead:
    service = AISystemRiskAssessmentService(db)
    row, created_now = service.create_runner_handshake(
        organization_id=organization.id,
        session_id=session_id,
        session_token=payload.session_token,
        idempotency_key=payload.idempotency_key,
        actor_user_id=current_user.id,
    )
    if created_now:
        AuditService(db).write_audit_log(
            action="governance_autopilot_runner_handshake.created",
            entity_type="governance_autopilot_runner_handshake",
            entity_id=row.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "handshake_status": row.handshake_status,
                "runner_session_id": str(row.runner_session_id),
                "runner_admission_id": str(row.runner_admission_id),
                "runner_simulation_id": str(row.runner_simulation_id),
                "execution_intent_id": str(row.execution_intent_id),
                "idempotency_key": row.idempotency_key,
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_runner_handshake_read(service.runner_handshake_payload(row))


@router.get(
    "/autopilot/runner-handshakes/summary",
    response_model=GovernanceAutopilotRunnerHandshakeSummary,
)
def get_governance_autopilot_runner_handshake_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerHandshakeSummary:
    payload = AISystemRiskAssessmentService(db).runner_handshake_summary(organization_id=organization.id)
    return GovernanceAutopilotRunnerHandshakeSummary(**payload)


@router.get(
    "/autopilot/runner-handshakes",
    response_model=list[GovernanceAutopilotRunnerHandshakeRead],
)
def list_governance_autopilot_runner_handshakes(
    runner_session_id: uuid.UUID | None = Query(default=None),
    runner_admission_id: uuid.UUID | None = Query(default=None),
    runner_simulation_id: uuid.UUID | None = Query(default=None),
    execution_intent_id: uuid.UUID | None = Query(default=None),
    handshake_status: str | None = Query(
        default=None,
        pattern="^(ready_for_future_runner|blocked|session_expired|session_locked|session_revoked|admission_revoked|revoked|archived)$",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotRunnerHandshakeRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_runner_handshakes(
        organization_id=organization.id,
        runner_session_id=runner_session_id,
        runner_admission_id=runner_admission_id,
        runner_simulation_id=runner_simulation_id,
        execution_intent_id=execution_intent_id,
        handshake_status=handshake_status,
        limit=limit,
        offset=offset,
    )
    return [_governance_autopilot_runner_handshake_read(service.runner_handshake_payload(row)) for row in rows]


@router.get(
    "/autopilot/runner-handshakes/{handshake_id}",
    response_model=GovernanceAutopilotRunnerHandshakeRead,
)
def get_governance_autopilot_runner_handshake_detail(
    handshake_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerHandshakeRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_runner_handshake(
        organization_id=organization.id,
        handshake_id=handshake_id,
    )
    return _governance_autopilot_runner_handshake_read(service.runner_handshake_payload(row))


@router.post(
    "/autopilot/runner-handshakes/{handshake_id}/verify",
    response_model=GovernanceAutopilotRunnerHandshakeVerifyResponse,
)
def verify_governance_autopilot_runner_handshake(
    handshake_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerHandshakeVerifyRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotRunnerHandshakeVerifyResponse:
    result = AISystemRiskAssessmentService(db).verify_runner_handshake_envelope(
        organization_id=organization.id,
        handshake_id=handshake_id,
        handshake_payload_json=payload.handshake_payload_json,
    )
    return GovernanceAutopilotRunnerHandshakeVerifyResponse(
        valid=bool(result["valid"]),
        validation_errors=list(result["validation_errors"]),
        caveat=result["caveat"],
    )


@router.post(
    "/autopilot/runner-handshakes/{handshake_id}/revoke",
    response_model=GovernanceAutopilotRunnerHandshakeRead,
)
def revoke_governance_autopilot_runner_handshake(
    handshake_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerHandshakeRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerHandshakeRead:
    service = AISystemRiskAssessmentService(db)
    row = service.revoke_runner_handshake(
        organization_id=organization.id,
        handshake_id=handshake_id,
        revoke_reason=payload.revoke_reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_runner_handshake.revoked",
        entity_type="governance_autopilot_runner_handshake",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "handshake_status": row.handshake_status,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
            "revoke_reason": row.revoke_reason,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_runner_handshake_read(service.runner_handshake_payload(row))


@router.post(
    "/autopilot/runner-handshakes/{handshake_id}/archive",
    response_model=GovernanceAutopilotRunnerHandshakeRead,
)
def archive_governance_autopilot_runner_handshake(
    handshake_id: uuid.UUID,
    payload: GovernanceAutopilotRunnerHandshakeArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotRunnerHandshakeRead:
    service = AISystemRiskAssessmentService(db)
    row = service.archive_runner_handshake(
        organization_id=organization.id,
        handshake_id=handshake_id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_runner_handshake.archived",
        entity_type="governance_autopilot_runner_handshake",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"handshake_status": row.handshake_status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_runner_handshake_read(service.runner_handshake_payload(row))


@router.get(
    "/autopilot/noop-runner/contract",
    response_model=GovernanceAutopilotNoopRunnerContractResponse,
)
def get_governance_autopilot_noop_runner_contract(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerContractResponse:
    _ = organization
    payload = AISystemRiskAssessmentService(db).autopilot_noop_runner_contract()
    return GovernanceAutopilotNoopRunnerContractResponse(**payload)


@router.post(
    "/autopilot/runner-handshakes/{handshake_id}/noop-runner/preview",
    response_model=GovernanceAutopilotNoopRunnerEventPreviewResponse,
)
def preview_governance_autopilot_noop_runner_event(
    handshake_id: uuid.UUID,
    payload: GovernanceAutopilotNoopRunnerEventPreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerEventPreviewResponse:
    result = AISystemRiskAssessmentService(db).preview_noop_runner_event(
        organization_id=organization.id,
        handshake_id=handshake_id,
        idempotency_key=payload.idempotency_key,
    )
    return GovernanceAutopilotNoopRunnerEventPreviewResponse(**result)


@router.post(
    "/autopilot/runner-handshakes/{handshake_id}/noop-runner/events",
    response_model=GovernanceAutopilotNoopRunnerEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_governance_autopilot_noop_runner_event(
    handshake_id: uuid.UUID,
    payload: GovernanceAutopilotNoopRunnerEventCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotNoopRunnerEventRead:
    service = AISystemRiskAssessmentService(db)
    row, created_now = service.create_noop_runner_event(
        organization_id=organization.id,
        handshake_id=handshake_id,
        idempotency_key=payload.idempotency_key,
        actor_user_id=current_user.id,
    )
    if created_now:
        AuditService(db).write_audit_log(
            action="governance_autopilot_noop_runner_event.created",
            entity_type="governance_autopilot_noop_runner_event",
            entity_id=row.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "event_status": row.event_status,
                "event_type": row.event_type,
                "runner_handshake_id": str(row.runner_handshake_id),
                "runner_session_id": str(row.runner_session_id),
                "runner_admission_id": str(row.runner_admission_id),
                "runner_simulation_id": str(row.runner_simulation_id),
                "execution_intent_id": str(row.execution_intent_id),
                "idempotency_key": row.idempotency_key,
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_noop_runner_event_read(service.noop_runner_event_payload(row))


@router.get(
    "/autopilot/noop-runner/events/summary",
    response_model=GovernanceAutopilotNoopRunnerEventSummary,
)
def get_governance_autopilot_noop_runner_event_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerEventSummary:
    payload = AISystemRiskAssessmentService(db).noop_runner_event_summary(organization_id=organization.id)
    return GovernanceAutopilotNoopRunnerEventSummary(**payload)


@router.get(
    "/autopilot/noop-runner/ledger",
    response_model=list[GovernanceAutopilotNoopRunnerLedgerRow],
)
def list_governance_autopilot_noop_runner_ledger(
    event_status: str | None = Query(default=None, pattern="^(logged|blocked|archived)$"),
    runner_handshake_id: uuid.UUID | None = Query(default=None),
    runner_session_id: uuid.UUID | None = Query(default=None),
    runner_admission_id: uuid.UUID | None = Query(default=None),
    runner_simulation_id: uuid.UUID | None = Query(default=None),
    execution_intent_id: uuid.UUID | None = Query(default=None),
    blocked_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotNoopRunnerLedgerRow]:
    rows = AISystemRiskAssessmentService(db).noop_runner_operator_ledger(
        organization_id=organization.id,
        event_status=event_status,
        runner_handshake_id=runner_handshake_id,
        runner_session_id=runner_session_id,
        runner_admission_id=runner_admission_id,
        runner_simulation_id=runner_simulation_id,
        execution_intent_id=execution_intent_id,
        blocked_only=blocked_only,
        limit=limit,
        offset=offset,
    )
    return [GovernanceAutopilotNoopRunnerLedgerRow(**row) for row in rows]


@router.get(
    "/autopilot/noop-runner/reports/contract",
    response_model=GovernanceAutopilotNoopRunnerReportsContractResponse,
)
def get_governance_autopilot_noop_runner_reports_contract(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerReportsContractResponse:
    _ = organization
    payload = AISystemRiskAssessmentService.autopilot_noop_runner_reports_contract()
    return GovernanceAutopilotNoopRunnerReportsContractResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/diagnostics-manifest",
    response_model=GovernanceAutopilotNoopRunnerDiagnosticsManifestResponse,
)
def get_governance_autopilot_noop_runner_diagnostics_manifest(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerDiagnosticsManifestResponse:
    payload = AISystemRiskAssessmentService(db).noop_runner_diagnostics_manifest(organization_id=organization.id)
    return GovernanceAutopilotNoopRunnerDiagnosticsManifestResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/compatibility-policy",
    response_model=GovernanceAutopilotNoopRunnerCompatibilityPolicyResponse,
)
def get_governance_autopilot_noop_runner_compatibility_policy(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerCompatibilityPolicyResponse:
    _ = organization
    payload = AISystemRiskAssessmentService.autopilot_noop_runner_compatibility_policy()
    return GovernanceAutopilotNoopRunnerCompatibilityPolicyResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/client-contract",
    response_model=GovernanceAutopilotNoopRunnerClientContractResponse,
)
def get_governance_autopilot_noop_runner_client_contract(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerClientContractResponse:
    _ = organization
    payload = AISystemRiskAssessmentService.autopilot_noop_runner_client_contract()
    return GovernanceAutopilotNoopRunnerClientContractResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/filter-options",
    response_model=GovernanceAutopilotNoopRunnerFilterOptionsResponse,
)
def get_governance_autopilot_noop_runner_filter_options(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerFilterOptionsResponse:
    _ = organization
    payload = AISystemRiskAssessmentService.autopilot_noop_runner_filter_options()
    return GovernanceAutopilotNoopRunnerFilterOptionsResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/pagination-contract",
    response_model=GovernanceAutopilotNoopRunnerPaginationContractResponse,
)
def get_governance_autopilot_noop_runner_pagination_contract(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerPaginationContractResponse:
    _ = organization
    payload = AISystemRiskAssessmentService.autopilot_noop_runner_pagination_contract()
    return GovernanceAutopilotNoopRunnerPaginationContractResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/field-docs",
    response_model=GovernanceAutopilotNoopRunnerFieldDocsResponse,
)
def get_governance_autopilot_noop_runner_field_docs(
    report_type: str | None = Query(
        default=None,
        pattern="^(ledger|timeline|blockers|readiness|idempotency|control_plane_health|bounded_export|checksum)$",
    ),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerFieldDocsResponse:
    _ = organization
    payload = AISystemRiskAssessmentService.autopilot_noop_runner_field_docs(report_type=report_type)
    return GovernanceAutopilotNoopRunnerFieldDocsResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/display-metadata",
    response_model=GovernanceAutopilotNoopRunnerDisplayMetadataResponse,
)
def get_governance_autopilot_noop_runner_display_metadata(
    report_type: str | None = Query(
        default=None,
        pattern="^(ledger|timeline|blockers|readiness|idempotency|control_plane_health|bounded_export|checksum)$",
    ),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerDisplayMetadataResponse:
    _ = organization
    payload = AISystemRiskAssessmentService.autopilot_noop_runner_display_metadata(report_type=report_type)
    return GovernanceAutopilotNoopRunnerDisplayMetadataResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/localization-map",
    response_model=GovernanceAutopilotNoopRunnerLocalizationMapResponse,
)
def get_governance_autopilot_noop_runner_localization_map(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerLocalizationMapResponse:
    _ = organization
    payload = AISystemRiskAssessmentService.autopilot_noop_runner_localization_map()
    return GovernanceAutopilotNoopRunnerLocalizationMapResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/client-hints",
    response_model=GovernanceAutopilotNoopRunnerClientHintsResponse,
)
def get_governance_autopilot_noop_runner_client_hints(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerClientHintsResponse:
    _ = organization
    payload = AISystemRiskAssessmentService.autopilot_noop_runner_client_hints()
    return GovernanceAutopilotNoopRunnerClientHintsResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/bounded-export",
    response_model=GovernanceAutopilotNoopRunnerBoundedExportResponse,
)
def get_governance_autopilot_noop_runner_bounded_export(
    report_type: str = Query(
        ...,
        pattern="^(ledger|timeline|blockers|readiness|idempotency|control_plane_health)$",
    ),
    limit: int = Query(default=100, ge=1),
    offset: int = Query(default=0, ge=0),
    event_status: str | None = Query(default=None, pattern="^(logged|blocked|archived)$"),
    execution_intent_id: uuid.UUID | None = Query(default=None),
    runner_handshake_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerBoundedExportResponse:
    payload = AISystemRiskAssessmentService(db).noop_runner_bounded_export(
        organization_id=organization.id,
        report_type=report_type,
        limit=limit,
        offset=offset,
        event_status=event_status,
        execution_intent_id=execution_intent_id,
        runner_handshake_id=runner_handshake_id,
    )
    return GovernanceAutopilotNoopRunnerBoundedExportResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/checksum",
    response_model=GovernanceAutopilotNoopRunnerReportChecksumResponse,
)
def get_governance_autopilot_noop_runner_report_checksum(
    report_type: str = Query(
        ...,
        pattern="^(ledger|timeline|blockers|readiness|idempotency|control_plane_health)$",
    ),
    limit: int = Query(default=100, ge=1),
    offset: int = Query(default=0, ge=0),
    event_status: str | None = Query(default=None, pattern="^(logged|blocked|archived)$"),
    execution_intent_id: uuid.UUID | None = Query(default=None),
    runner_handshake_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerReportChecksumResponse:
    payload = AISystemRiskAssessmentService(db).noop_runner_report_checksum(
        organization_id=organization.id,
        report_type=report_type,
        limit=limit,
        offset=offset,
        event_status=event_status,
        execution_intent_id=execution_intent_id,
        runner_handshake_id=runner_handshake_id,
    )
    return GovernanceAutopilotNoopRunnerReportChecksumResponse(**payload)


@router.get(
    "/autopilot/noop-runner/reports/timeline",
    response_model=GovernanceAutopilotNoopRunnerTimelineReport,
)
def get_governance_autopilot_noop_runner_timeline_report(
    event_status: str | None = Query(default=None, pattern="^(logged|blocked|archived)$"),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerTimelineReport:
    payload = AISystemRiskAssessmentService(db).noop_runner_timeline_report(
        organization_id=organization.id,
        event_status=event_status,
        days=days,
    )
    return GovernanceAutopilotNoopRunnerTimelineReport(**payload)


@router.get(
    "/autopilot/noop-runner/reports/blockers",
    response_model=GovernanceAutopilotNoopRunnerBlockerReport,
)
def get_governance_autopilot_noop_runner_blocker_report(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerBlockerReport:
    payload = AISystemRiskAssessmentService(db).noop_runner_blocker_report(organization_id=organization.id)
    return GovernanceAutopilotNoopRunnerBlockerReport(**payload)


@router.get(
    "/autopilot/noop-runner/reports/readiness",
    response_model=GovernanceAutopilotNoopRunnerReadinessReport,
)
def get_governance_autopilot_noop_runner_readiness_report(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerReadinessReport:
    payload = AISystemRiskAssessmentService(db).noop_runner_readiness_report(organization_id=organization.id)
    return GovernanceAutopilotNoopRunnerReadinessReport(**payload)


@router.get(
    "/autopilot/noop-runner/reports/idempotency",
    response_model=GovernanceAutopilotNoopRunnerIdempotencyReport,
)
def get_governance_autopilot_noop_runner_idempotency_report(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerIdempotencyReport:
    payload = AISystemRiskAssessmentService(db).noop_runner_idempotency_report(organization_id=organization.id)
    return GovernanceAutopilotNoopRunnerIdempotencyReport(**payload)


@router.get(
    "/autopilot/noop-runner/reports/control-plane-health",
    response_model=GovernanceAutopilotNoopRunnerControlPlaneHealthReport,
)
def get_governance_autopilot_noop_runner_control_plane_health_report(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerControlPlaneHealthReport:
    payload = AISystemRiskAssessmentService(db).noop_runner_control_plane_health_report(organization_id=organization.id)
    return GovernanceAutopilotNoopRunnerControlPlaneHealthReport(**payload)


@router.get(
    "/autopilot/noop-runner/events",
    response_model=list[GovernanceAutopilotNoopRunnerEventRead],
)
def list_governance_autopilot_noop_runner_events(
    runner_handshake_id: uuid.UUID | None = Query(default=None),
    execution_intent_id: uuid.UUID | None = Query(default=None),
    event_status: str | None = Query(default=None, pattern="^(logged|blocked|archived)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotNoopRunnerEventRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_noop_runner_events(
        organization_id=organization.id,
        runner_handshake_id=runner_handshake_id,
        execution_intent_id=execution_intent_id,
        event_status=event_status,
        limit=limit,
        offset=offset,
    )
    return [_governance_autopilot_noop_runner_event_read(service.noop_runner_event_payload(row)) for row in rows]


@router.get(
    "/autopilot/noop-runner/events/{event_id}",
    response_model=GovernanceAutopilotNoopRunnerEventRead,
)
def get_governance_autopilot_noop_runner_event_detail(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerEventRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_noop_runner_event(organization_id=organization.id, event_id=event_id)
    return _governance_autopilot_noop_runner_event_read(service.noop_runner_event_payload(row))


@router.post(
    "/autopilot/noop-runner/events/{event_id}/verify",
    response_model=GovernanceAutopilotNoopRunnerEventVerifyResponse,
)
def verify_governance_autopilot_noop_runner_event(
    event_id: uuid.UUID,
    payload: GovernanceAutopilotNoopRunnerEventVerifyRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotNoopRunnerEventVerifyResponse:
    result = AISystemRiskAssessmentService(db).verify_noop_runner_event(
        organization_id=organization.id,
        event_id=event_id,
        event_payload_json=payload.event_payload_json,
    )
    return GovernanceAutopilotNoopRunnerEventVerifyResponse(
        valid=bool(result["valid"]),
        validation_errors=list(result["validation_errors"]),
        caveat=result["caveat"],
    )


@router.post(
    "/autopilot/noop-runner/events/{event_id}/archive",
    response_model=GovernanceAutopilotNoopRunnerEventRead,
)
def archive_governance_autopilot_noop_runner_event(
    event_id: uuid.UUID,
    payload: GovernanceAutopilotNoopRunnerEventArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotNoopRunnerEventRead:
    service = AISystemRiskAssessmentService(db)
    row = service.archive_noop_runner_event(
        organization_id=organization.id,
        event_id=event_id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_noop_runner_event.archived",
        entity_type="governance_autopilot_noop_runner_event",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"event_status": row.event_status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_noop_runner_event_read(service.noop_runner_event_payload(row))


@router.get(
    "/autopilot/execution-intents/{intent_id}/approval-requirements",
    response_model=GovernanceAutopilotExecutionIntentApprovalRequirementsResponse,
)
def get_governance_autopilot_execution_intent_approval_requirements(
    intent_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionIntentApprovalRequirementsResponse:
    payload = AISystemRiskAssessmentService(db).execution_intent_approval_requirements(
        organization_id=organization.id,
        intent_id=intent_id,
    )
    return GovernanceAutopilotExecutionIntentApprovalRequirementsResponse(**payload)


@router.post(
    "/autopilot/execution-intents/{intent_id}/approval-requests",
    response_model=GovernanceAutopilotExecutionApprovalRead,
    status_code=status.HTTP_201_CREATED,
)
def request_governance_autopilot_execution_intent_approval(
    intent_id: uuid.UUID,
    payload: GovernanceAutopilotExecutionApprovalRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotExecutionApprovalRead:
    service = AISystemRiskAssessmentService(db)
    row = service.request_execution_approval(
        organization_id=organization.id,
        intent_id=intent_id,
        approval_note=payload.approval_note,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_execution_approval.requested",
        entity_type="governance_autopilot_execution_approval",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"approval_status": row.approval_status, "execution_intent_id": str(row.execution_intent_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_execution_approval_read(service.execution_approval_payload(row))


@router.get(
    "/autopilot/execution-intents/{intent_id}/approval-requests",
    response_model=list[GovernanceAutopilotExecutionApprovalRead],
)
def list_governance_autopilot_execution_intent_approval_requests(
    intent_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotExecutionApprovalRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_execution_approvals_for_intent(
        organization_id=organization.id,
        intent_id=intent_id,
    )
    return [_governance_autopilot_execution_approval_read(service.execution_approval_payload(row)) for row in rows]


@router.get(
    "/autopilot/execution-intents/{intent_id}/readiness",
    response_model=GovernanceAutopilotExecutionIntentReadinessResponse,
)
def get_governance_autopilot_execution_intent_readiness(
    intent_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionIntentReadinessResponse:
    payload = AISystemRiskAssessmentService(db).execution_intent_readiness(
        organization_id=organization.id,
        intent_id=intent_id,
    )
    return GovernanceAutopilotExecutionIntentReadinessResponse(**payload)


@router.get(
    "/autopilot/execution-approvals/summary",
    response_model=GovernanceAutopilotExecutionApprovalSummary,
)
def get_governance_autopilot_execution_approvals_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionApprovalSummary:
    payload = AISystemRiskAssessmentService(db).execution_approval_summary(organization_id=organization.id)
    return GovernanceAutopilotExecutionApprovalSummary(**payload)


@router.get(
    "/autopilot/execution-approvals",
    response_model=list[GovernanceAutopilotExecutionApprovalRead],
)
def list_governance_autopilot_execution_approvals(
    approval_status: str | None = Query(default=None, pattern="^(requested|approved|rejected|cancelled)$"),
    execution_intent_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotExecutionApprovalRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_execution_approvals(
        organization_id=organization.id,
        approval_status=approval_status,
        execution_intent_id=execution_intent_id,
        limit=limit,
        offset=offset,
    )
    return [_governance_autopilot_execution_approval_read(service.execution_approval_payload(row)) for row in rows]


@router.get(
    "/autopilot/execution-approvals/{approval_id}/quorum-status",
    response_model=GovernanceAutopilotExecutionApprovalQuorumStatusResponse,
)
def get_governance_autopilot_execution_approval_quorum_status(
    approval_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionApprovalQuorumStatusResponse:
    payload = AISystemRiskAssessmentService(db).execution_approval_quorum_status(
        organization_id=organization.id,
        approval_id=approval_id,
    )
    return GovernanceAutopilotExecutionApprovalQuorumStatusResponse(**payload)


@router.get(
    "/autopilot/execution-approvals/{approval_id}/votes",
    response_model=list[GovernanceAutopilotExecutionApprovalVoteRead],
)
def list_governance_autopilot_execution_approval_votes(
    approval_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotExecutionApprovalVoteRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_execution_approval_votes(
        organization_id=organization.id,
        approval_id=approval_id,
    )
    return [GovernanceAutopilotExecutionApprovalVoteRead(**service.execution_approval_vote_payload(row)) for row in rows]


@router.post(
    "/autopilot/execution-approvals/{approval_id}/votes/approve",
    response_model=GovernanceAutopilotExecutionApprovalRead,
)
def vote_approve_governance_autopilot_execution_approval(
    approval_id: uuid.UUID,
    payload: GovernanceAutopilotExecutionApprovalVoteApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotExecutionApprovalRead:
    service = AISystemRiskAssessmentService(db)
    row = service.vote_approve_execution_approval(
        organization_id=organization.id,
        approval_id=approval_id,
        vote_reason=payload.vote_reason,
        vote_note=payload.vote_note,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_execution_approval_vote.approved",
        entity_type="governance_autopilot_execution_approval",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"approval_status": row.approval_status, "execution_intent_id": str(row.execution_intent_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_execution_approval_read(service.execution_approval_payload(row))


@router.post(
    "/autopilot/execution-approvals/{approval_id}/votes/reject",
    response_model=GovernanceAutopilotExecutionApprovalRead,
)
def vote_reject_governance_autopilot_execution_approval(
    approval_id: uuid.UUID,
    payload: GovernanceAutopilotExecutionApprovalVoteRejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotExecutionApprovalRead:
    service = AISystemRiskAssessmentService(db)
    row = service.vote_reject_execution_approval(
        organization_id=organization.id,
        approval_id=approval_id,
        vote_reason=payload.vote_reason,
        vote_note=payload.vote_note,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_execution_approval_vote.rejected",
        entity_type="governance_autopilot_execution_approval",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"approval_status": row.approval_status, "execution_intent_id": str(row.execution_intent_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_execution_approval_read(service.execution_approval_payload(row))


@router.get(
    "/autopilot/execution-approvals/{approval_id}",
    response_model=GovernanceAutopilotExecutionApprovalRead,
)
def get_governance_autopilot_execution_approval_detail(
    approval_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionApprovalRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_execution_approval(
        organization_id=organization.id,
        approval_id=approval_id,
    )
    return _governance_autopilot_execution_approval_read(service.execution_approval_payload(row))


@router.post(
    "/autopilot/execution-approvals/{approval_id}/approve",
    response_model=GovernanceAutopilotExecutionApprovalRead,
)
def approve_governance_autopilot_execution_approval(
    approval_id: uuid.UUID,
    payload: GovernanceAutopilotExecutionApprovalApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotExecutionApprovalRead:
    service = AISystemRiskAssessmentService(db)
    row = service.approve_execution_approval(
        organization_id=organization.id,
        approval_id=approval_id,
        decision_reason=payload.decision_reason,
        approval_note=payload.approval_note,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_execution_approval.approved",
        entity_type="governance_autopilot_execution_approval",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"approval_status": row.approval_status, "execution_intent_id": str(row.execution_intent_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_execution_approval_read(service.execution_approval_payload(row))


@router.post(
    "/autopilot/execution-approvals/{approval_id}/reject",
    response_model=GovernanceAutopilotExecutionApprovalRead,
)
def reject_governance_autopilot_execution_approval(
    approval_id: uuid.UUID,
    payload: GovernanceAutopilotExecutionApprovalRejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotExecutionApprovalRead:
    service = AISystemRiskAssessmentService(db)
    row = service.reject_execution_approval(
        organization_id=organization.id,
        approval_id=approval_id,
        decision_reason=payload.decision_reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_execution_approval.rejected",
        entity_type="governance_autopilot_execution_approval",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"approval_status": row.approval_status, "execution_intent_id": str(row.execution_intent_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_execution_approval_read(service.execution_approval_payload(row))


@router.post(
    "/autopilot/execution-approvals/{approval_id}/cancel",
    response_model=GovernanceAutopilotExecutionApprovalRead,
)
def cancel_governance_autopilot_execution_approval(
    approval_id: uuid.UUID,
    payload: GovernanceAutopilotExecutionApprovalCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotExecutionApprovalRead:
    service = AISystemRiskAssessmentService(db)
    row = service.cancel_execution_approval(
        organization_id=organization.id,
        approval_id=approval_id,
        decision_reason=payload.decision_reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_execution_approval.cancelled",
        entity_type="governance_autopilot_execution_approval",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"approval_status": row.approval_status, "execution_intent_id": str(row.execution_intent_id)},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_execution_approval_read(service.execution_approval_payload(row))


@router.get(
    "/autopilot/execution-intents/summary",
    response_model=GovernanceAutopilotExecutionIntentSummary,
)
def get_governance_autopilot_execution_intents_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionIntentSummary:
    payload = AISystemRiskAssessmentService(db).execution_intent_summary(organization_id=organization.id)
    return GovernanceAutopilotExecutionIntentSummary(**payload)


@router.get(
    "/autopilot/execution-intents",
    response_model=list[GovernanceAutopilotExecutionIntentRead],
)
def list_governance_autopilot_execution_intents(
    source_type: str | None = Query(default=None, pattern="^(candidate_action|recommendation_snapshot|copilot_draft_snapshot)$"),
    intent_status: str | None = Query(default=None, pattern="^(planned|approval_required|blocked|archived)$"),
    policy_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceAutopilotExecutionIntentRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_execution_intents(
        organization_id=organization.id,
        source_type=source_type,
        intent_status=intent_status,
        policy_id=policy_id,
        limit=limit,
        offset=offset,
    )
    return [_governance_autopilot_execution_intent_read(service.execution_intent_payload(row)) for row in rows]


@router.post(
    "/autopilot/execution-intents/{intent_id}/archive",
    response_model=GovernanceAutopilotExecutionIntentRead,
)
def archive_governance_autopilot_execution_intent(
    intent_id: uuid.UUID,
    payload: GovernanceAutopilotExecutionIntentArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceAutopilotExecutionIntentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.archive_execution_intent(
        organization_id=organization.id,
        intent_id=intent_id,
        reason=payload.reason,
    )
    AuditService(db).write_audit_log(
        action="governance_autopilot_execution_intent.archived",
        entity_type="governance_autopilot_execution_intent",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"intent_status": row.intent_status, "archived_at": row.archived_at.isoformat() if row.archived_at else None},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_autopilot_execution_intent_read(service.execution_intent_payload(row))


@router.get(
    "/autopilot/execution-intents/{intent_id}",
    response_model=GovernanceAutopilotExecutionIntentRead,
)
def get_governance_autopilot_execution_intent_detail(
    intent_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAutopilotExecutionIntentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_execution_intent(
        organization_id=organization.id,
        intent_id=intent_id,
    )
    return _governance_autopilot_execution_intent_read(service.execution_intent_payload(row))


def _policy_read(row: AISystemGovernanceReviewReminderPolicy) -> AISystemGovernanceReviewReminderPolicyRead:
    return AISystemGovernanceReviewReminderPolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        review_type=row.review_type,
        days_before_due=row.days_before_due,
        overdue_after_days=row.overdue_after_days,
        escalation_after_days=row.escalation_after_days,
        notify_assignee=row.notify_assignee,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _governance_autopilot_policy_read(payload: dict) -> GovernanceAutopilotPolicyRead:
    return GovernanceAutopilotPolicyRead(
        id=payload.get("policy_id"),
        policy_id=payload.get("policy_id"),
        organization_id=payload.get("organization_id"),
        name=payload.get("name"),
        description=payload.get("description"),
        status=payload.get("status"),
        is_default=bool(payload.get("is_default")),
        mode=payload.get("mode"),
        allowed_action_types_json=list(payload.get("allowed_action_types_json") or []),
        blocked_action_types_json=list(payload.get("blocked_action_types_json") or []),
        allowed_draft_types_json=list(payload.get("allowed_draft_types_json") or []),
        blocked_draft_types_json=list(payload.get("blocked_draft_types_json") or []),
        allowed_signal_reason_codes_json=list(payload.get("allowed_signal_reason_codes_json") or []),
        blocked_signal_reason_codes_json=list(payload.get("blocked_signal_reason_codes_json") or []),
        approval_required_action_types_json=list(payload.get("approval_required_action_types_json") or []),
        approval_required_priority_bands_json=list(payload.get("approval_required_priority_bands_json") or []),
        max_allowed_priority_band_for_auto=payload.get("max_allowed_priority_band_for_auto"),
        external_effects_allowed=bool(payload.get("external_effects_allowed")),
        task_creation_allowed=bool(payload.get("task_creation_allowed")),
        review_creation_allowed=bool(payload.get("review_creation_allowed")),
        source_record_mutation_allowed=bool(payload.get("source_record_mutation_allowed")),
        policy_json=dict(payload.get("policy_json") or {}),
        created_by_user_id=payload.get("created_by_user_id"),
        updated_by_user_id=payload.get("updated_by_user_id"),
        archived_at=payload.get("archived_at"),
        resolved_source=payload.get("resolved_source"),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
        caveat=payload.get("caveat", "Autopilot policies are deterministic guardrails only."),
    )


def _governance_autopilot_approval_policy_read(payload: dict) -> GovernanceAutopilotApprovalPolicyRead:
    return GovernanceAutopilotApprovalPolicyRead(
        approval_policy_id=payload.get("approval_policy_id"),
        organization_id=payload.get("organization_id"),
        name=payload.get("name"),
        description=payload.get("description"),
        status=payload.get("status"),
        is_default=bool(payload.get("is_default")),
        minimum_approvals=int(payload.get("minimum_approvals") or 1),
        rejection_threshold=int(payload.get("rejection_threshold") or 1),
        require_distinct_approvers=bool(payload.get("require_distinct_approvers", True)),
        block_requester_self_approval=bool(payload.get("block_requester_self_approval", True)),
        require_quorum_for_priority_bands_json=list(payload.get("require_quorum_for_priority_bands_json") or []),
        require_quorum_for_source_types_json=list(payload.get("require_quorum_for_source_types_json") or []),
        policy_json=dict(payload.get("policy_json") or {}),
        created_by_user_id=payload.get("created_by_user_id"),
        updated_by_user_id=payload.get("updated_by_user_id"),
        archived_at=payload.get("archived_at"),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
        resolved_source=payload.get("resolved_source"),
        caveat=payload.get("caveat", "Autopilot approval policies are deterministic guardrails only."),
    )


def _governance_autopilot_execution_intent_read(payload: dict) -> GovernanceAutopilotExecutionIntentRead:
    return GovernanceAutopilotExecutionIntentRead(
        id=payload["intent_id"],
        intent_id=payload["intent_id"],
        organization_id=payload["organization_id"],
        source_type=payload["source_type"],
        source_id=payload.get("source_id"),
        policy_id=payload.get("policy_id"),
        intent_status=payload["intent_status"],
        plan_payload_json=payload["plan_payload_json"],
        capability_decisions_json=payload["capability_decisions_json"],
        approval_required=bool(payload.get("approval_required")),
        blocked=bool(payload.get("blocked")),
        blocked_reasons_json=payload.get("blocked_reasons_json"),
        source_entities_json=payload["source_entities_json"],
        source_hash=payload["source_hash"],
        intent_sha256=payload["intent_sha256"],
        created_by_user_id=payload.get("created_by_user_id"),
        archived_at=payload.get("archived_at"),
        archive_reason=payload.get("archive_reason"),
        intent_age_hours=float(payload["intent_age_hours"]) if payload.get("intent_age_hours") is not None else None,
        stale_intent=bool(payload.get("stale_intent", False)),
        context_flags=[str(item) for item in payload.get("context_flags", [])],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        caveat=payload.get("caveat", "Autopilot execution intents are dry-run planning records only."),
    )


def _governance_autopilot_execution_approval_read(payload: dict) -> GovernanceAutopilotExecutionApprovalRead:
    return GovernanceAutopilotExecutionApprovalRead(
        id=payload["approval_id"],
        approval_id=payload["approval_id"],
        organization_id=payload["organization_id"],
        execution_intent_id=payload["execution_intent_id"],
        approval_status=payload["approval_status"],
        requested_by_user_id=payload.get("requested_by_user_id"),
        requested_at=payload["requested_at"],
        decided_by_user_id=payload.get("decided_by_user_id"),
        decided_at=payload.get("decided_at"),
        decision_reason=payload.get("decision_reason"),
        approval_note=payload.get("approval_note"),
        approval_policy_snapshot_json=payload["approval_policy_snapshot_json"],
        approval_requirements_json=payload["approval_requirements_json"],
        readiness_snapshot_json=payload["readiness_snapshot_json"],
        cancelled_at=payload.get("cancelled_at"),
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        approval_vote_count=int(payload.get("approval_vote_count") or 0),
        rejection_vote_count=int(payload.get("rejection_vote_count") or 0),
        quorum_met=bool(payload.get("quorum_met")),
        rejection_threshold_met=bool(payload.get("rejection_threshold_met")),
        readiness_state=payload["readiness_state"],
        ready_for_runner=bool(payload["ready_for_runner"]),
        caveat=payload.get("caveat", "Execution approvals are non-executing human authorization metadata only."),
    )


def _governance_autopilot_runner_simulation_read(payload: dict) -> GovernanceAutopilotRunnerSimulationRead:
    return GovernanceAutopilotRunnerSimulationRead(
        id=payload["simulation_id"],
        simulation_id=payload["simulation_id"],
        organization_id=payload["organization_id"],
        execution_intent_id=payload["execution_intent_id"],
        approval_id=payload.get("approval_id"),
        simulation_status=payload["simulation_status"],
        handoff_payload_json=payload["handoff_payload_json"],
        readiness_snapshot_json=payload["readiness_snapshot_json"],
        policy_snapshot_json=payload["policy_snapshot_json"],
        capability_snapshot_json=payload["capability_snapshot_json"],
        source_hash=payload["source_hash"],
        idempotency_key=payload["idempotency_key"],
        simulation_sha256=payload["simulation_sha256"],
        created_by_user_id=payload.get("created_by_user_id"),
        archived_at=payload.get("archived_at"),
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        caveat=payload.get("caveat", "Runner simulations are non-executing dry-run artifacts only."),
    )


def _governance_autopilot_runner_admission_read(payload: dict) -> GovernanceAutopilotRunnerAdmissionRead:
    return GovernanceAutopilotRunnerAdmissionRead(
        id=payload["admission_id"],
        admission_id=payload["admission_id"],
        organization_id=payload["organization_id"],
        runner_simulation_id=payload["runner_simulation_id"],
        execution_intent_id=payload["execution_intent_id"],
        approval_id=payload.get("approval_id"),
        admission_status=payload["admission_status"],
        readiness_snapshot_json=payload["readiness_snapshot_json"],
        consistency_checks_json=payload["consistency_checks_json"],
        handoff_payload_json=payload["handoff_payload_json"],
        handoff_token_fingerprint=payload.get("handoff_token_fingerprint"),
        idempotency_key=payload["idempotency_key"],
        token_expires_at=payload.get("token_expires_at"),
        admitted_by_user_id=payload.get("admitted_by_user_id"),
        revoked_by_user_id=payload.get("revoked_by_user_id"),
        revoked_at=payload.get("revoked_at"),
        revoke_reason=payload.get("revoke_reason"),
        archived_at=payload.get("archived_at"),
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        handoff_token=payload.get("handoff_token"),
        caveat=payload.get("caveat", "Runner admissions are non-executing guardrail artifacts only."),
    )


def _governance_autopilot_runner_session_read(payload: dict) -> GovernanceAutopilotRunnerSessionRead:
    return GovernanceAutopilotRunnerSessionRead(
        id=payload["session_id"],
        session_id=payload["session_id"],
        organization_id=payload["organization_id"],
        runner_admission_id=payload["runner_admission_id"],
        runner_simulation_id=payload["runner_simulation_id"],
        execution_intent_id=payload["execution_intent_id"],
        session_status=payload["session_status"],
        admission_token_fingerprint=payload.get("admission_token_fingerprint"),
        session_token_fingerprint=payload.get("session_token_fingerprint"),
        lease_payload_json=payload["lease_payload_json"],
        binding_context_json=payload["binding_context_json"],
        attempt_count=int(payload.get("attempt_count") or 0),
        max_attempts=int(payload.get("max_attempts") or 0),
        replay_window_seconds=int(payload.get("replay_window_seconds") or 0),
        expires_at=payload["expires_at"],
        last_verified_at=payload.get("last_verified_at"),
        revoked_at=payload.get("revoked_at"),
        revoked_by_user_id=payload.get("revoked_by_user_id"),
        revoke_reason=payload.get("revoke_reason"),
        archived_at=payload.get("archived_at"),
        created_by_user_id=payload.get("created_by_user_id"),
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        session_token=payload.get("session_token"),
        caveat=payload.get("caveat", "Runner sessions are non-executing guardrail artifacts only."),
    )


def _governance_autopilot_runner_handshake_read(payload: dict) -> GovernanceAutopilotRunnerHandshakeRead:
    return GovernanceAutopilotRunnerHandshakeRead(
        id=payload["handshake_id"],
        handshake_id=payload["handshake_id"],
        organization_id=payload["organization_id"],
        runner_session_id=payload["runner_session_id"],
        runner_admission_id=payload["runner_admission_id"],
        runner_simulation_id=payload["runner_simulation_id"],
        execution_intent_id=payload["execution_intent_id"],
        handshake_status=payload["handshake_status"],
        handshake_payload_json=payload["handshake_payload_json"],
        session_verification_snapshot_json=payload["session_verification_snapshot_json"],
        admission_snapshot_json=payload["admission_snapshot_json"],
        simulation_snapshot_json=payload["simulation_snapshot_json"],
        intent_snapshot_json=payload["intent_snapshot_json"],
        idempotency_key=payload["idempotency_key"],
        handshake_fingerprint=payload.get("handshake_fingerprint"),
        handshake_sha256=payload["handshake_sha256"],
        revoked_at=payload.get("revoked_at"),
        revoked_by_user_id=payload.get("revoked_by_user_id"),
        revoke_reason=payload.get("revoke_reason"),
        archived_at=payload.get("archived_at"),
        created_by_user_id=payload.get("created_by_user_id"),
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        caveat=payload.get("caveat", "Runner handshakes are non-executing future-runner contract artifacts only."),
    )


def _governance_autopilot_noop_runner_event_read(payload: dict) -> GovernanceAutopilotNoopRunnerEventRead:
    return GovernanceAutopilotNoopRunnerEventRead(
        id=payload["event_id"],
        event_id=payload["event_id"],
        organization_id=payload["organization_id"],
        runner_handshake_id=payload["runner_handshake_id"],
        runner_session_id=payload["runner_session_id"],
        runner_admission_id=payload["runner_admission_id"],
        runner_simulation_id=payload["runner_simulation_id"],
        execution_intent_id=payload["execution_intent_id"],
        event_status=payload["event_status"],
        event_type=payload["event_type"],
        noop_only=bool(payload["noop_only"]),
        dry_run=bool(payload["dry_run"]),
        execution_allowed=bool(payload["execution_allowed"]),
        idempotency_key=payload["idempotency_key"],
        event_payload_json=payload["event_payload_json"],
        noop_result_json=payload["noop_result_json"],
        source_hash=payload["source_hash"],
        event_sha256=payload["event_sha256"],
        created_by_user_id=payload.get("created_by_user_id"),
        archived_at=payload.get("archived_at"),
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        caveat=payload.get("caveat", "No-op runner events are non-executing control-plane artifacts only."),
    )


def _event_read(row: AISystemGovernanceReviewEvent) -> AISystemGovernanceReviewEventRead:
    return AISystemGovernanceReviewEventRead(
        id=row.id,
        organization_id=row.organization_id,
        ai_system_id=row.ai_system_id,
        review_id=row.review_id,
        event_type=row.event_type,
        status=row.status,
        triggered_at=row.triggered_at,
        resolved_at=row.resolved_at,
        resolved_by_user_id=row.resolved_by_user_id,
        resolution_notes=row.resolution_notes,
        details_json=row.details_json,
        created_at=row.created_at,
    )


def _recurrence_template_read(
    row: AISystemGovernanceReviewRecurrenceTemplate,
) -> AISystemGovernanceReviewRecurrenceTemplateRead:
    return AISystemGovernanceReviewRecurrenceTemplateRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        review_type=row.review_type,
        cadence_type=row.cadence_type,
        interval_value=row.interval_value,
        default_reminder_policy_id=row.default_reminder_policy_id,
        default_assigned_to_user_id=row.default_assigned_to_user_id,
        default_checklist_json=row.default_checklist_json,
        default_description=row.default_description,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _plan_run_read(row: AISystemGovernanceReviewPlanRun) -> AISystemGovernanceReviewPlanRunRead:
    return AISystemGovernanceReviewPlanRunRead(
        id=row.id,
        organization_id=row.organization_id,
        template_id=row.template_id,
        status=row.status,
        dry_run=row.dry_run,
        horizon_days=row.horizon_days,
        target_ai_system_ids_json=row.target_ai_system_ids_json,
        generated_reviews_count=row.generated_reviews_count,
        skipped_reviews_count=row.skipped_reviews_count,
        result_json=row.result_json,
        requested_by_user_id=row.requested_by_user_id,
        created_at=row.created_at,
    )


def _constraint_read(row: AISystemGovernanceReviewPlanConstraint) -> AISystemGovernanceReviewPlanConstraintRead:
    return AISystemGovernanceReviewPlanConstraintRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        target_review_type=row.target_review_type,
        prerequisite_review_type=row.prerequisite_review_type,
        constraint_type=row.constraint_type,
        enforcement_mode=row.enforcement_mode,
        min_gap_days=row.min_gap_days,
        max_gap_days=row.max_gap_days,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _sequence_pack_read(row: AISystemGovernanceReviewSequencePack) -> AISystemGovernanceReviewSequencePackRead:
    return AISystemGovernanceReviewSequencePackRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _sequence_step_read(row: AISystemGovernanceReviewSequenceStep) -> AISystemGovernanceReviewSequenceStepRead:
    return AISystemGovernanceReviewSequenceStepRead(
        id=row.id,
        organization_id=row.organization_id,
        sequence_pack_id=row.sequence_pack_id,
        step_order=row.step_order,
        review_type=row.review_type,
        title_template=row.title_template,
        description_template=row.description_template,
        offset_days_from_start=row.offset_days_from_start,
        default_reminder_policy_id=row.default_reminder_policy_id,
        default_assigned_to_user_id=row.default_assigned_to_user_id,
        default_checklist_json=row.default_checklist_json,
        require_previous_step_planned=row.require_previous_step_planned,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _sequence_run_read(row: AISystemGovernanceReviewSequenceRun) -> AISystemGovernanceReviewSequenceRunRead:
    return AISystemGovernanceReviewSequenceRunRead(
        id=row.id,
        organization_id=row.organization_id,
        sequence_pack_id=row.sequence_pack_id,
        status=row.status,
        dry_run=row.dry_run,
        target_ai_system_ids_json=row.target_ai_system_ids_json,
        start_from=row.start_from,
        apply_constraints=row.apply_constraints,
        generated_reviews_count=row.generated_reviews_count,
        skipped_reviews_count=row.skipped_reviews_count,
        result_json=row.result_json,
        requested_by_user_id=row.requested_by_user_id,
        created_at=row.created_at,
    )


def _freeze_window_read(row: AISystemGovernanceFreezeWindow) -> AISystemGovernanceFreezeWindowRead:
    return AISystemGovernanceFreezeWindowRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        scope_type=row.scope_type,
        scope_json=row.scope_json,
        priority=row.priority,
        enforcement_level=row.enforcement_level,
        override_allowed=row.override_allowed,
        precedence_notes=row.precedence_notes,
        reason=row.reason,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _operator_ack_read(
    row: AISystemGovernanceOperatorAcknowledgement,
) -> AISystemGovernanceOperatorAcknowledgementRead:
    return AISystemGovernanceOperatorAcknowledgementRead(
        id=row.id,
        organization_id=row.organization_id,
        action_type=row.action_type,
        target_type=row.target_type,
        target_id=row.target_id,
        acknowledgement_text=row.acknowledgement_text,
        reason=row.reason,
        override_freeze=row.override_freeze,
        freeze_window_ids_json=row.freeze_window_ids_json,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _policy_set_read(row: AISystemGovernanceGuardrailPolicySet) -> AISystemGovernanceGuardrailPolicySetRead:
    return AISystemGovernanceGuardrailPolicySetRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        active_version_id=row.active_version_id,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_set_version_read(
    row: AISystemGovernanceGuardrailPolicySetVersion,
) -> AISystemGovernanceGuardrailPolicySetVersionRead:
    return AISystemGovernanceGuardrailPolicySetVersionRead(
        id=row.id,
        organization_id=row.organization_id,
        policy_set_id=row.policy_set_id,
        version_number=row.version_number,
        status=row.status,
        profile_json=row.profile_json,
        change_reason=row.change_reason,
        created_by_user_id=row.created_by_user_id,
        activated_by_user_id=row.activated_by_user_id,
        activated_at=row.activated_at,
        archived_at=row.archived_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_assignment_read(
    row: AISystemGovernanceGuardrailPolicyAssignment,
) -> AISystemGovernanceGuardrailPolicyAssignmentRead:
    return AISystemGovernanceGuardrailPolicyAssignmentRead(
        id=row.id,
        organization_id=row.organization_id,
        policy_set_id=row.policy_set_id,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        scope_json=row.scope_json,
        priority=row.priority,
        status=row.status,
        reason=row.reason,
        assigned_by_user_id=row.assigned_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_assignment_history_read(
    row: AISystemGovernanceGuardrailPolicyAssignmentHistory,
) -> AISystemGovernanceGuardrailPolicyAssignmentHistoryRead:
    return AISystemGovernanceGuardrailPolicyAssignmentHistoryRead(
        id=row.id,
        organization_id=row.organization_id,
        assignment_id=row.assignment_id,
        event_type=row.event_type,
        before_json=row.before_json,
        after_json=row.after_json,
        reason=row.reason,
        changed_by_user_id=row.changed_by_user_id,
        created_at=row.created_at,
    )


def _policy_diff_gating_compare_preset_assignment_read(
    row: AISystemGovernancePolicyDiffGatingComparePresetAssignment,
) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead:
    return AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead(
        id=row.id,
        organization_id=row.organization_id,
        preset_id=row.preset_id,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        scope_json=row.scope_json,
        priority=row.priority,
        status=row.status,
        reason=row.reason,
        assigned_by_user_id=row.assigned_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_diff_gating_compare_preset_assignment_history_read(
    row: AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory,
) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistoryRead:
    return AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistoryRead(
        id=row.id,
        organization_id=row.organization_id,
        assignment_id=row.assignment_id,
        event_type=row.event_type,
        before_json=row.before_json,
        after_json=row.after_json,
        reason=row.reason,
        changed_by_user_id=row.changed_by_user_id,
        created_at=row.created_at,
    )


def _policy_resolution_simulation_report_read(
    row: AISystemGovernancePolicyResolutionSimulationReport,
) -> AISystemGovernancePolicyResolutionSimulationReportRead:
    return AISystemGovernancePolicyResolutionSimulationReportRead(
        id=row.id,
        organization_id=row.organization_id,
        title=row.title,
        description=row.description,
        status=row.status,
        requested_by_user_id=row.requested_by_user_id,
        input_contexts_json=row.input_contexts_json,
        result_json=row.result_json,
        context_count=row.context_count,
        blocked_contexts_count=row.blocked_contexts_count,
        warning_contexts_count=row.warning_contexts_count,
        no_policy_contexts_count=row.no_policy_contexts_count,
        created_at=row.created_at,
    )


def _policy_resolution_simulation_diff_report_read(
    row: AISystemGovernancePolicyResolutionSimulationDiffReport,
) -> AISystemGovernancePolicyResolutionSimulationDiffReportRead:
    return AISystemGovernancePolicyResolutionSimulationDiffReportRead(
        id=row.id,
        organization_id=row.organization_id,
        base_report_id=row.base_report_id,
        compare_report_id=row.compare_report_id,
        title=row.title,
        status=row.status,
        diff_json=row.diff_json,
        context_match_strategy=row.context_match_strategy,
        added_contexts_count=row.added_contexts_count,
        removed_contexts_count=row.removed_contexts_count,
        changed_contexts_count=row.changed_contexts_count,
        unchanged_contexts_count=row.unchanged_contexts_count,
        blocked_delta=row.blocked_delta,
        warning_delta=row.warning_delta,
        no_policy_delta=row.no_policy_delta,
        reason_code_summary_json=row.reason_code_summary_json,
        reason_code_count=row.reason_code_count,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_diff_gating_profile_read(
    row: AISystemGovernancePolicyDiffGatingProfile,
) -> AISystemGovernancePolicyDiffGatingProfileRead:
    return AISystemGovernancePolicyDiffGatingProfileRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        default_severity=row.default_severity,
        review_required_threshold=row.review_required_threshold,
        reason_code_rules_json=row.reason_code_rules_json,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_diff_gating_report_read(
    row: AISystemGovernancePolicyDiffGatingReport,
) -> AISystemGovernancePolicyDiffGatingReportRead:
    return AISystemGovernancePolicyDiffGatingReportRead(
        id=row.id,
        organization_id=row.organization_id,
        diff_report_id=row.diff_report_id,
        gating_profile_id=row.gating_profile_id,
        status=row.status,
        result_json=row.result_json,
        max_severity=row.max_severity,
        review_required=row.review_required,
        reason_code_count=row.reason_code_count,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _diagnostic_export_diff_gating_profile_read(
    row: AISystemGovernanceDiagnosticExportDiffGatingProfile,
) -> AISystemGovernanceDiagnosticExportDiffGatingProfileRead:
    return AISystemGovernanceDiagnosticExportDiffGatingProfileRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        default_severity=row.default_severity,
        review_required_threshold=row.review_required_threshold,
        reason_code_rules_json=row.reason_code_rules_json,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _diagnostic_export_diff_gating_report_read(
    row: AISystemGovernanceDiagnosticExportDiffGatingReport,
) -> AISystemGovernanceDiagnosticExportDiffGatingReportRead:
    return AISystemGovernanceDiagnosticExportDiffGatingReportRead(
        id=row.id,
        organization_id=row.organization_id,
        export_diff_report_id=row.export_diff_report_id,
        gating_profile_id=row.gating_profile_id,
        status=row.status,
        result_json=row.result_json,
        max_severity=row.max_severity,
        review_required=row.review_required,
        reason_code_count=row.reason_code_count,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _diagnostic_export_diff_gating_compare_report_read(
    row: AISystemGovernanceDiagnosticExportDiffGatingCompareReport,
) -> AISystemGovernanceDiagnosticExportDiffGatingCompareReportRead:
    return AISystemGovernanceDiagnosticExportDiffGatingCompareReportRead(
        id=row.id,
        organization_id=row.organization_id,
        base_gating_report_id=row.base_gating_report_id,
        compare_gating_report_id=row.compare_gating_report_id,
        title=row.title,
        status=row.status,
        result_json=row.result_json,
        max_severity_drift=row.max_severity_drift,
        review_required_drift=row.review_required_drift,
        reason_code_changes_count=row.reason_code_changes_count,
        severity_changes_count=row.severity_changes_count,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _diagnostic_export_diff_gating_compare_preset_read(
    row: AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead:
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        watched_reason_codes_json=row.watched_reason_codes_json,
        ignored_reason_codes_json=row.ignored_reason_codes_json,
        interpretation_rules_json=row.interpretation_rules_json,
        default_interpretation_band=row.default_interpretation_band,
        active_version_id=row.active_version_id,
        pinned_version_id=row.pinned_version_id,
        version_selection_mode=row.version_selection_mode,
        allow_explicit_version_override=row.allow_explicit_version_override,
        pinned_at=row.pinned_at,
        pinned_by_user_id=row.pinned_by_user_id,
        pin_reason=row.pin_reason,
        unpinned_at=row.unpinned_at,
        unpinned_by_user_id=row.unpinned_by_user_id,
        unpin_reason=row.unpin_reason,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _diagnostic_export_diff_gating_compare_preset_version_read(
    row: AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion,
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead:
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead(
        id=row.id,
        organization_id=row.organization_id,
        preset_id=row.preset_id,
        version_number=row.version_number,
        status=row.status,
        snapshot_json=row.snapshot_json,
        change_reason=row.change_reason,
        created_by_user_id=row.created_by_user_id,
        activated_by_user_id=row.activated_by_user_id,
        activated_at=row.activated_at,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        caveat=(
            "Preset versions and pinning control deterministic interpretation snapshots for human review. "
            "They do not approve, reject, create tasks, create reviews, mutate compare reports, "
            "or trigger automation."
        ),
    )


def _diagnostic_export_diff_gating_compare_preset_report_read(
    row: AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport,
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportRead:
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportRead(
        id=row.id,
        organization_id=row.organization_id,
        compare_report_id=row.compare_report_id,
        preset_id=row.preset_id,
        preset_version_id=row.preset_version_id,
        preset_version_number=row.preset_version_number,
        preset_snapshot_json=row.preset_snapshot_json,
        version_resolution_source=row.version_resolution_source,
        pinned_version_id=row.pinned_version_id,
        explicit_version_override_used=row.explicit_version_override_used,
        version_override_reason=row.version_override_reason,
        status=row.status,
        result_json=row.result_json,
        interpretation_band=row.interpretation_band,
        review_required=row.review_required,
        matched_rules_json=row.matched_rules_json,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _diagnostic_export_diff_gating_compare_preset_assignment_read(
    row: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment,
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead:
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead(
        id=row.id,
        organization_id=row.organization_id,
        preset_id=row.preset_id,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        scope_json=row.scope_json,
        priority=row.priority,
        status=row.status,
        reason=row.reason,
        assigned_by_user_id=row.assigned_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _diagnostic_export_diff_gating_compare_preset_assignment_history_read(
    row: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory,
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistoryRead:
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistoryRead(
        id=row.id,
        organization_id=row.organization_id,
        assignment_id=row.assignment_id,
        event_type=row.event_type,
        before_json=row.before_json,
        after_json=row.after_json,
        reason=row.reason,
        changed_by_user_id=row.changed_by_user_id,
        created_at=row.created_at,
    )


def _policy_diff_gating_compare_report_read(
    row: AISystemGovernancePolicyDiffGatingCompareReport,
) -> AISystemGovernancePolicyDiffGatingCompareReportRead:
    return AISystemGovernancePolicyDiffGatingCompareReportRead(
        id=row.id,
        organization_id=row.organization_id,
        base_gating_report_id=row.base_gating_report_id,
        compare_gating_report_id=row.compare_gating_report_id,
        title=row.title,
        status=row.status,
        result_json=row.result_json,
        base_max_severity=row.base_max_severity,
        compare_max_severity=row.compare_max_severity,
        severity_direction=row.severity_direction,
        review_required_changed=row.review_required_changed,
        base_review_required=row.base_review_required,
        compare_review_required=row.compare_review_required,
        reason_code_changes_count=row.reason_code_changes_count,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_diff_gating_compare_preset_read(
    row: AISystemGovernancePolicyDiffGatingComparePreset,
) -> AISystemGovernancePolicyDiffGatingComparePresetRead:
    return AISystemGovernancePolicyDiffGatingComparePresetRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        baseline_gating_report_id=row.baseline_gating_report_id,
        baseline_gating_profile_id=row.baseline_gating_profile_id,
        watched_reason_codes_json=row.watched_reason_codes_json,
        ignored_reason_codes_json=row.ignored_reason_codes_json,
        interpretation_rules_json=row.interpretation_rules_json,
        default_interpretation_band=row.default_interpretation_band,
        active_version_id=row.active_version_id,
        pinned_version_id=row.pinned_version_id,
        version_selection_mode=row.version_selection_mode,
        allow_explicit_version_override=row.allow_explicit_version_override,
        pinned_at=row.pinned_at,
        pinned_by_user_id=row.pinned_by_user_id,
        pin_reason=row.pin_reason,
        unpinned_at=row.unpinned_at,
        unpinned_by_user_id=row.unpinned_by_user_id,
        unpin_reason=row.unpin_reason,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _policy_diff_gating_compare_preset_version_read(
    row: AISystemGovernancePolicyDiffGatingComparePresetVersion,
) -> AISystemGovernancePolicyDiffGatingComparePresetVersionRead:
    return AISystemGovernancePolicyDiffGatingComparePresetVersionRead(
        id=row.id,
        organization_id=row.organization_id,
        preset_id=row.preset_id,
        version_number=row.version_number,
        status=row.status,
        snapshot_json=row.snapshot_json,
        change_reason=row.change_reason,
        created_by_user_id=row.created_by_user_id,
        activated_by_user_id=row.activated_by_user_id,
        activated_at=row.activated_at,
        archived_at=row.archived_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        caveat=(
            "Preset versions are immutable interpretation snapshots for human review. "
            "They do not approve, reject, create tasks, create reviews, or trigger automation."
        ),
    )


def _policy_diff_gating_compare_preset_report_read(
    row: AISystemGovernancePolicyDiffGatingComparePresetReport,
) -> AISystemGovernancePolicyDiffGatingComparePresetReportRead:
    return AISystemGovernancePolicyDiffGatingComparePresetReportRead(
        id=row.id,
        organization_id=row.organization_id,
        preset_id=row.preset_id,
        base_gating_report_id=row.base_gating_report_id,
        compare_gating_report_id=row.compare_gating_report_id,
        compare_report_id=row.compare_report_id,
        preset_version_id=row.preset_version_id,
        preset_version_number=row.preset_version_number,
        preset_snapshot_json=row.preset_snapshot_json,
        status=row.status,
        result_json=row.result_json,
        interpretation_band=row.interpretation_band,
        review_required=row.review_required,
        watched_reason_codes_hit_count=row.watched_reason_codes_hit_count,
        ignored_reason_codes_hit_count=row.ignored_reason_codes_hit_count,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _preset_assignment_diagnostic_report_read(
    row: AISystemGovernancePresetAssignmentDiagnosticReport,
) -> AISystemGovernancePresetAssignmentDiagnosticReportRead:
    return AISystemGovernancePresetAssignmentDiagnosticReportRead(
        id=row.id,
        organization_id=row.organization_id,
        title=row.title,
        description=row.description,
        status=row.status,
        input_contexts_json=row.input_contexts_json,
        result_json=row.result_json,
        context_count=row.context_count,
        resolved_contexts_count=row.resolved_contexts_count,
        unresolved_contexts_count=row.unresolved_contexts_count,
        warning_contexts_count=row.warning_contexts_count,
        critical_contexts_count=row.critical_contexts_count,
        aggregate_diagnostics_json=row.aggregate_diagnostics_json,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _preset_assignment_diagnostic_diff_report_read(
    row: AISystemGovernancePresetAssignmentDiagnosticDiffReport,
) -> AISystemGovernancePresetAssignmentDiagnosticDiffReportRead:
    return AISystemGovernancePresetAssignmentDiagnosticDiffReportRead(
        id=row.id,
        organization_id=row.organization_id,
        base_report_id=row.base_report_id,
        compare_report_id=row.compare_report_id,
        title=row.title,
        status=row.status,
        diff_json=row.diff_json,
        added_contexts_count=row.added_contexts_count,
        removed_contexts_count=row.removed_contexts_count,
        changed_contexts_count=row.changed_contexts_count,
        unchanged_contexts_count=row.unchanged_contexts_count,
        resolved_delta=row.resolved_delta,
        unresolved_delta=row.unresolved_delta,
        warning_delta=row.warning_delta,
        critical_delta=row.critical_delta,
        diagnostic_code_changes_count=row.diagnostic_code_changes_count,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _preset_assignment_diagnostic_export_read(
    row: AISystemGovernancePresetAssignmentDiagnosticExport,
) -> AISystemGovernancePresetAssignmentDiagnosticExportRead:
    return AISystemGovernancePresetAssignmentDiagnosticExportRead(
        id=row.id,
        organization_id=row.organization_id,
        export_type=row.export_type,
        source_report_id=row.source_report_id,
        source_diff_report_id=row.source_diff_report_id,
        status=row.status,
        export_payload_json=row.export_payload_json,
        canonical_payload_sha256=row.canonical_payload_sha256,
        signature_algorithm=row.signature_algorithm,
        internal_signature=row.internal_signature,
        signing_key_id=row.signing_key_id,
        exported_by_user_id=row.exported_by_user_id,
        revoked_at=row.revoked_at,
        revoked_by_user_id=row.revoked_by_user_id,
        revocation_reason=row.revocation_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _preset_assignment_diagnostic_export_diff_report_read(
    row: AISystemGovernancePresetAssignmentDiagnosticExportDiffReport,
) -> AISystemGovernancePresetAssignmentDiagnosticExportDiffReportRead:
    return AISystemGovernancePresetAssignmentDiagnosticExportDiffReportRead(
        id=row.id,
        organization_id=row.organization_id,
        base_export_id=row.base_export_id,
        compare_export_id=row.compare_export_id,
        export_type=row.export_type,
        title=row.title,
        status=row.status,
        diff_json=row.diff_json,
        base_canonical_payload_sha256=row.base_canonical_payload_sha256,
        compare_canonical_payload_sha256=row.compare_canonical_payload_sha256,
        payload_hash_changed=row.payload_hash_changed,
        base_valid_signature=row.base_valid_signature,
        compare_valid_signature=row.compare_valid_signature,
        base_trusted=row.base_trusted,
        compare_trusted=row.compare_trusted,
        added_paths_count=row.added_paths_count,
        removed_paths_count=row.removed_paths_count,
        changed_paths_count=row.changed_paths_count,
        unchanged_paths_count=row.unchanged_paths_count,
        reason_code_summary_json=row.reason_code_summary_json,
        reason_code_count=row.reason_code_count,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _risk_assessment_read(row: AISystemRiskAssessment) -> AISystemRiskAssessmentRead:
    return AISystemRiskAssessmentRead(
        id=row.id,
        organization_id=row.organization_id,
        ai_system_id=row.ai_system_id,
        title=row.title,
        description=row.description,
        assessment_type=row.assessment_type,
        status=row.status,
        owner_user_id=row.owner_user_id,
        risk_level=row.risk_level,
        likelihood=row.likelihood,
        impact=row.impact,
        scoring_profile_id=row.scoring_profile_id,
        scoring_profile_snapshot_json=row.scoring_profile_snapshot_json,
        score_explanation_json=row.score_explanation_json,
        calculated_risk_level=row.calculated_risk_level,
        dimension_template_id=row.dimension_template_id,
        latest_classification_id=row.latest_classification_id,
        classification_status=row.classification_status,
        classification_summary_json=row.classification_summary_json,
        latest_classification_review_status=row.latest_classification_review_status,
        open_signal_count=row.open_signal_count,
        dimension_template_snapshot_json=row.dimension_template_snapshot_json,
        dimension_inputs_json=row.dimension_inputs_json,
        dimension_score_json=row.dimension_score_json,
        dimension_weighted_score=row.dimension_weighted_score,
        calculated_dimension_risk_level=row.calculated_dimension_risk_level,
        residual_likelihood=row.residual_likelihood,
        residual_impact=row.residual_impact,
        calculated_residual_risk_level=row.calculated_residual_risk_level,
        residual_score_explanation_json=row.residual_score_explanation_json,
        inherent_risk_score=row.inherent_risk_score,
        residual_risk_score=row.residual_risk_score,
        risk_dimensions_json=row.risk_dimensions_json,
        risk_factors_json=row.risk_factors_json,
        mitigation_summary=row.mitigation_summary,
        assumptions=row.assumptions,
        limitations=row.limitations,
        methodology_version=row.methodology_version,
        completed_at=row.completed_at,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        caveat=AI_RISK_ASSESSMENT_CAVEAT,
    )


def _risk_assessment_snapshot_read(row: AISystemRiskAssessmentSnapshot) -> AISystemRiskAssessmentSnapshotRead:
    return AISystemRiskAssessmentSnapshotRead(
        id=row.id,
        organization_id=row.organization_id,
        risk_assessment_id=row.risk_assessment_id,
        ai_system_id=row.ai_system_id,
        snapshot_type=row.snapshot_type,
        snapshot_version=row.snapshot_version,
        snapshot_json=row.snapshot_json,
        snapshot_sha256=row.snapshot_sha256,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        caveat=AI_RISK_ASSESSMENT_CAVEAT,
    )


def _risk_scoring_profile_read(row: AISystemRiskScoringProfile) -> AISystemRiskScoringProfileRead:
    return AISystemRiskScoringProfileRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        is_default=row.is_default,
        likelihood_weights_json=row.likelihood_weights_json,
        impact_weights_json=row.impact_weights_json,
        risk_level_thresholds_json=row.risk_level_thresholds_json,
        methodology_version=row.methodology_version,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _risk_dimension_template_read(row: AISystemRiskDimensionTemplate) -> AISystemRiskDimensionTemplateRead:
    return AISystemRiskDimensionTemplateRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        is_default=row.is_default,
        dimension_weights_json=row.dimension_weights_json,
        dimension_thresholds_json=row.dimension_thresholds_json,
        methodology_version=row.methodology_version,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _risk_classification_taxonomy_read(
    row: AISystemRiskClassificationTaxonomyTemplate,
) -> AISystemRiskClassificationTaxonomyTemplateRead:
    return AISystemRiskClassificationTaxonomyTemplateRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        status=row.status,
        is_default=row.is_default,
        taxonomy_json=row.taxonomy_json,
        methodology_version=row.methodology_version,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _risk_classification_record_read(
    row: AISystemRiskClassificationRecord,
    *,
    latest_snapshot_id: uuid.UUID | None = None,
    open_signal_count: int | None = None,
) -> AISystemRiskClassificationRecordRead:
    return AISystemRiskClassificationRecordRead(
        id=row.id,
        organization_id=row.organization_id,
        ai_system_id=row.ai_system_id,
        risk_assessment_id=row.risk_assessment_id,
        taxonomy_template_id=row.taxonomy_template_id,
        taxonomy_template_snapshot_json=row.taxonomy_template_snapshot_json,
        classification_json=row.classification_json,
        status=row.status,
        review_status=row.review_status,
        review_requested_at=row.review_requested_at,
        review_requested_by_user_id=row.review_requested_by_user_id,
        reviewed_at=row.reviewed_at,
        reviewed_by_user_id=row.reviewed_by_user_id,
        review_note=row.review_note,
        change_request_note=row.change_request_note,
        rejected_at=row.rejected_at,
        rejected_by_user_id=row.rejected_by_user_id,
        rejection_reason=row.rejection_reason,
        latest_snapshot_id=latest_snapshot_id,
        open_signal_count=open_signal_count,
        confidence_level=row.confidence_level,
        justification=row.justification,
        source_type=row.source_type,
        source_reference=row.source_reference,
        evidence_ids_json=row.evidence_ids_json,
        control_ids_json=row.control_ids_json,
        risk_ids_json=row.risk_ids_json,
        created_by_user_id=row.created_by_user_id,
        archived_at=row.archived_at,
        archived_by_user_id=row.archived_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        caveat=AI_RISK_CLASSIFICATION_CAVEAT,
    )


def _risk_classification_snapshot_read(
    row: AISystemRiskClassificationRecordSnapshot,
) -> AISystemRiskClassificationSnapshotRead:
    return AISystemRiskClassificationSnapshotRead(
        id=row.id,
        organization_id=row.organization_id,
        classification_id=row.classification_id,
        risk_assessment_id=row.risk_assessment_id,
        ai_system_id=row.ai_system_id,
        snapshot_type=row.snapshot_type,
        snapshot_version=row.snapshot_version,
        snapshot_json=row.snapshot_json,
        snapshot_sha256=row.snapshot_sha256,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        caveat=AI_RISK_CLASSIFICATION_CAVEAT,
    )


def _governance_signal_read(payload: dict) -> GovernanceSignalRead:
    return GovernanceSignalRead(
        id=payload["id"],
        organization_id=payload["organization_id"],
        domain=payload["domain"],
        entity_type=payload["entity_type"],
        entity_id=payload["entity_id"],
        related_ai_system_id=payload.get("related_ai_system_id"),
        related_risk_assessment_id=payload.get("related_risk_assessment_id"),
        signal_type=payload["signal_type"],
        reason_code=payload["reason_code"],
        severity=payload["severity"],
        status=payload["status"],
        title=payload["title"],
        message=payload["message"],
        source_json=payload["source_json"],
        created_by_system=bool(payload["created_by_system"]),
        resolved_at=payload.get("resolved_at"),
        resolved_by_user_id=payload.get("resolved_by_user_id"),
        resolve_reason=payload.get("resolve_reason"),
        dismissed_at=payload.get("dismissed_at"),
        dismissed_by_user_id=payload.get("dismissed_by_user_id"),
        dismiss_reason=payload.get("dismiss_reason"),
        priority_score=float(payload["priority_score"]) if payload.get("priority_score") is not None else None,
        priority_band=payload.get("priority_band"),
        priority_explanation_json=payload.get("priority_explanation_json"),
        group_key=payload.get("group_key"),
        age_days=int(payload["age_days"]) if payload.get("age_days") is not None else None,
        stale_signal=bool(payload.get("stale_signal", False)),
        context_flags=[str(item) for item in payload.get("context_flags", [])],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        caveat=payload.get("caveat", AI_RISK_GOVERNANCE_SIGNAL_CAVEAT),
    )


def _governance_signal_prioritized_read(payload: dict) -> GovernanceSignalPrioritizedRead:
    return GovernanceSignalPrioritizedRead(
        signal_id=payload["signal_id"],
        signal_type=payload["signal_type"],
        reason_code=payload["reason_code"],
        severity=payload["severity"],
        status=payload["status"],
        entity_type=payload["entity_type"],
        entity_id=payload["entity_id"],
        related_ai_system_id=payload.get("related_ai_system_id"),
        related_risk_assessment_id=payload.get("related_risk_assessment_id"),
        priority_score=float(payload["priority_score"]),
        priority_band=payload["priority_band"],
        priority_explanation_json=payload["priority_explanation_json"],
        age_days=int(payload["age_days"]),
        group_key=payload["group_key"],
        context_flags=[str(item) for item in payload.get("context_flags", [])],
        created_at=payload["created_at"],
        caveat=payload.get("caveat", AI_RISK_GOVERNANCE_SIGNAL_PRIORITY_CAVEAT),
    )


def _governance_action_template_read(payload: dict) -> GovernanceActionTemplateRead:
    return GovernanceActionTemplateRead(
        action_key=payload["action_key"],
        title=payload["title"],
        description=payload["description"],
        action_type=payload["action_type"],
        source_reason_codes=payload["source_reason_codes"],
        default_priority_band=payload["default_priority_band"],
        recommended_owner_type=payload["recommended_owner_type"],
        target_entity_type=payload["target_entity_type"],
        target_route_hint=payload.get("target_route_hint"),
        human_approval_required=bool(payload["human_approval_required"]),
        automation_allowed=bool(payload["automation_allowed"]),
        caveat=payload.get("caveat", AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT),
    )


def _governance_candidate_action_read(payload: dict) -> GovernanceCandidateActionRead:
    return GovernanceCandidateActionRead(
        action_key=payload["action_key"],
        title=payload["title"],
        description=payload["description"],
        action_type=payload["action_type"],
        priority_score=float(payload["priority_score"]),
        priority_band=payload["priority_band"],
        source_signal_ids=payload["source_signal_ids"],
        source_reason_codes=payload["source_reason_codes"],
        target_entity_type=payload["target_entity_type"],
        target_entity_id=payload.get("target_entity_id"),
        related_ai_system_id=payload.get("related_ai_system_id"),
        related_risk_assessment_id=payload.get("related_risk_assessment_id"),
        rationale=payload["rationale"],
        rationale_json=payload["rationale_json"],
        human_approval_required=bool(payload["human_approval_required"]),
        automation_allowed=bool(payload["automation_allowed"]),
        target_route_hint=payload.get("target_route_hint"),
        caveat=payload.get("caveat", AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT),
    )


def _governance_recommendation_snapshot_read(
    row: GovernanceRecommendationSnapshot,
    *,
    actions_overlay: list[dict] | None = None,
) -> GovernanceRecommendationSnapshotRead:
    return GovernanceRecommendationSnapshotRead(
        id=row.id,
        snapshot_id=row.id,
        organization_id=row.organization_id,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        source_type=row.source_type,
        candidate_count=int(row.candidate_count),
        recommendation_payload_json=row.recommendation_payload_json,
        source_signal_ids_json=list(row.source_signal_ids_json or []),
        source_candidate_hash=row.source_candidate_hash,
        snapshot_sha256=row.snapshot_sha256,
        snapshot_version=int(row.snapshot_version),
        previous_snapshot_id=row.previous_snapshot_id,
        diff_from_previous_json=row.diff_from_previous_json,
        created_by_user_id=row.created_by_user_id,
        actions_overlay=actions_overlay,
        created_at=row.created_at,
        updated_at=row.updated_at,
        caveat=AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT,
    )


def _governance_recommendation_snapshot_action_read(payload: dict) -> GovernanceRecommendationSnapshotActionRead:
    return GovernanceRecommendationSnapshotActionRead(
        action_identity_hash=payload["action_identity_hash"],
        action_key=payload["action_key"],
        title=payload["title"],
        description=payload["description"],
        action_type=payload["action_type"],
        priority_score=float(payload["priority_score"]),
        priority_band=payload["priority_band"],
        source_signal_ids=payload["source_signal_ids"],
        source_reason_codes=payload["source_reason_codes"],
        target_entity_type=payload["target_entity_type"],
        target_entity_id=payload.get("target_entity_id"),
        related_ai_system_id=payload.get("related_ai_system_id"),
        related_risk_assessment_id=payload.get("related_risk_assessment_id"),
        rationale=payload["rationale"],
        rationale_json=payload["rationale_json"],
        human_approval_required=bool(payload["human_approval_required"]),
        automation_allowed=bool(payload["automation_allowed"]),
        target_route_hint=payload.get("target_route_hint"),
        disposition=payload.get("disposition"),
        caveat=payload.get("caveat", AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT),
    )


def _governance_recommendation_action_disposition_read(
    payload: dict,
) -> GovernanceRecommendationActionDispositionRead:
    return GovernanceRecommendationActionDispositionRead(
        id=payload["id"],
        disposition_id=payload["disposition_id"],
        recommendation_snapshot_id=payload["recommendation_snapshot_id"],
        action_identity_hash=payload["action_identity_hash"],
        action_key=payload["action_key"],
        target_entity_type=payload.get("target_entity_type"),
        target_entity_id=payload.get("target_entity_id"),
        related_ai_system_id=payload.get("related_ai_system_id"),
        related_risk_assessment_id=payload.get("related_risk_assessment_id"),
        disposition_status=payload["disposition_status"],
        note=payload.get("note"),
        reason=payload.get("reason"),
        deferred_until=payload.get("deferred_until"),
        created_by_user_id=payload.get("created_by_user_id"),
        updated_by_user_id=payload.get("updated_by_user_id"),
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        caveat=payload.get("caveat", AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT),
    )


def _governance_copilot_draft_snapshot_read(
    row: GovernanceCopilotDraftSnapshot,
) -> GovernanceCopilotDraftSnapshotRead:
    return GovernanceCopilotDraftSnapshotRead(
        id=row.id,
        snapshot_id=row.id,
        organization_id=row.organization_id,
        draft_type=row.draft_type,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        draft_payload_json=row.draft_payload_json,
        source_entities_json=row.source_entities_json,
        source_signal_ids_json=list(row.source_signal_ids_json or []),
        source_recommendation_snapshot_id=row.source_recommendation_snapshot_id,
        source_action_identity_hashes_json=list(row.source_action_identity_hashes_json or []),
        source_context_hash=row.source_context_hash,
        snapshot_sha256=row.snapshot_sha256,
        snapshot_version=int(row.snapshot_version),
        previous_snapshot_id=row.previous_snapshot_id,
        diff_from_previous_json=row.diff_from_previous_json,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        caveat=GOVERNANCE_COPILOT_DRAFT_SNAPSHOT_CAVEAT,
    )


def _classification_row_with_metadata(
    db: Session,
    row: AISystemRiskClassificationRecord,
) -> AISystemRiskClassificationRecordRead:
    latest_snapshot_id = (
        db.execute(
            select(AISystemRiskClassificationRecordSnapshot.id)
            .where(
                AISystemRiskClassificationRecordSnapshot.organization_id == row.organization_id,
                AISystemRiskClassificationRecordSnapshot.classification_id == row.id,
            )
            .order_by(AISystemRiskClassificationRecordSnapshot.snapshot_version.desc())
            .limit(1)
        ).scalar_one_or_none()
    )
    open_signal_count = int(
        db.execute(
            select(func.count(GovernanceSignal.id)).where(
                GovernanceSignal.organization_id == row.organization_id,
                GovernanceSignal.entity_type == "risk_classification",
                GovernanceSignal.entity_id == row.id,
                GovernanceSignal.status == "open",
            )
        ).scalar_one()
    )
    return _risk_classification_record_read(
        row,
        latest_snapshot_id=latest_snapshot_id,
        open_signal_count=open_signal_count,
    )


def _require_ai_systems_write_or_admin(db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID) -> None:
    if RBACService.user_has_permission(db, user_id, organization_id, "ai_systems:write"):
        return
    if RBACService.user_has_permission(db, user_id, organization_id, "ai_systems:admin"):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Missing required permission: ai_systems:write or ai_systems:admin",
    )


@router.post(
    "/ai-risk/scoring-profiles",
    response_model=AISystemRiskScoringProfileRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_risk_scoring_profile(
    payload: AISystemRiskScoringProfileCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskScoringProfileRead:
    service = AISystemRiskAssessmentService(db)
    row = service.create_scoring_profile(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        likelihood_weights_json=payload.likelihood_weights_json,
        impact_weights_json=payload.impact_weights_json,
        risk_level_thresholds_json=payload.risk_level_thresholds_json,
        methodology_version=payload.methodology_version,
        is_default=payload.is_default,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_risk_scoring_profile.created",
        entity_type="ai_system_risk_scoring_profile",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "status": row.status,
            "is_default": row.is_default,
            "methodology_version": row.methodology_version,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_scoring_profile_read(row)


@router.get("/ai-risk/scoring-profiles/summary", response_model=AISystemRiskScoringProfileSummary)
def get_ai_risk_scoring_profile_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskScoringProfileSummary:
    summary = AISystemRiskAssessmentService(db).scoring_profile_summary(organization_id=organization.id)
    return AISystemRiskScoringProfileSummary(**summary)


@router.post(
    "/ai-risk/dimension-templates",
    response_model=AISystemRiskDimensionTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_risk_dimension_template(
    payload: AISystemRiskDimensionTemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskDimensionTemplateRead:
    service = AISystemRiskAssessmentService(db)
    row = service.create_dimension_template(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        dimension_weights_json=payload.dimension_weights_json,
        dimension_thresholds_json=payload.dimension_thresholds_json,
        methodology_version=payload.methodology_version,
        is_default=payload.is_default,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_risk_dimension_template.created",
        entity_type="ai_system_risk_dimension_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"name": row.name, "status": row.status, "is_default": row.is_default},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_dimension_template_read(row)


@router.get("/ai-risk/dimension-templates/summary", response_model=AISystemRiskDimensionTemplateSummary)
def get_ai_risk_dimension_template_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskDimensionTemplateSummary:
    summary = AISystemRiskAssessmentService(db).dimension_template_summary(organization_id=organization.id)
    return AISystemRiskDimensionTemplateSummary(**summary)


@router.get("/ai-risk/dimension-templates", response_model=list[AISystemRiskDimensionTemplateRead])
def list_ai_risk_dimension_templates(
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    is_default: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemRiskDimensionTemplateRead]:
    rows = AISystemRiskAssessmentService(db).list_dimension_templates(
        organization_id=organization.id,
        status_filter=status_filter,
        include_archived=include_archived,
        is_default=is_default,
        limit=limit,
        offset=offset,
    )
    return [_risk_dimension_template_read(row) for row in rows]


@router.get("/ai-risk/dimension-templates/{template_id}", response_model=AISystemRiskDimensionTemplateRead)
def get_ai_risk_dimension_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskDimensionTemplateRead:
    row = AISystemRiskAssessmentService(db).require_dimension_template(
        organization_id=organization.id,
        template_id=template_id,
    )
    return _risk_dimension_template_read(row)


@router.patch("/ai-risk/dimension-templates/{template_id}", response_model=AISystemRiskDimensionTemplateRead)
def update_ai_risk_dimension_template(
    template_id: uuid.UUID,
    payload: AISystemRiskDimensionTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskDimensionTemplateRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_dimension_template(organization_id=organization.id, template_id=template_id)
    before = {"status": row.status, "is_default": row.is_default}
    row = service.update_dimension_template(row=row, updates=payload.model_dump(exclude_unset=True))
    AuditService(db).write_audit_log(
        action="ai_system_risk_dimension_template.updated",
        entity_type="ai_system_risk_dimension_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status, "is_default": row.is_default},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_dimension_template_read(row)


@router.post("/ai-risk/dimension-templates/{template_id}/archive", response_model=AISystemRiskDimensionTemplateRead)
def archive_ai_risk_dimension_template(
    template_id: uuid.UUID,
    payload: AISystemRiskDimensionTemplateArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskDimensionTemplateRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_dimension_template(organization_id=organization.id, template_id=template_id)
    row = service.archive_dimension_template(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_risk_dimension_template.archived",
        entity_type="ai_system_risk_dimension_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": row.status,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "is_default": row.is_default,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_dimension_template_read(row)


@router.post("/ai-risk/dimension-templates/{template_id}/set-default", response_model=AISystemRiskDimensionTemplateRead)
def set_ai_risk_dimension_template_default(
    template_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskDimensionTemplateRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_dimension_template(organization_id=organization.id, template_id=template_id)
    row = service.set_default_dimension_template(row=row)
    AuditService(db).write_audit_log(
        action="ai_system_risk_dimension_template.default_set",
        entity_type="ai_system_risk_dimension_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"is_default": row.is_default, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_dimension_template_read(row)


@router.post("/ai-risk/dimension-templates/{template_id}/preview-score", response_model=AISystemRiskDimensionScorePreviewResponse)
def preview_ai_risk_dimension_template(
    template_id: uuid.UUID,
    payload: AISystemRiskDimensionScorePreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskDimensionScorePreviewResponse:
    service = AISystemRiskAssessmentService(db)
    row = service.require_dimension_template(organization_id=organization.id, template_id=template_id)
    weighted_score, calculated_level, score_json = service.preview_dimension_score(
        template=row,
        dimension_inputs_json=payload.dimension_inputs_json,
    )
    score_json["template"] = service.dimension_template_snapshot_json(row)
    score_json["caveat"] = AI_RISK_DIMENSION_CAVEAT
    return AISystemRiskDimensionScorePreviewResponse(
        dimension_weighted_score=weighted_score,
        calculated_dimension_risk_level=calculated_level,
        dimension_score_json=score_json,
        caveat=AI_RISK_DIMENSION_CAVEAT,
    )


@router.post(
    "/ai-risk/classification-taxonomies",
    response_model=AISystemRiskClassificationTaxonomyTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_risk_classification_taxonomy(
    payload: AISystemRiskClassificationTaxonomyTemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationTaxonomyTemplateRead:
    service = AISystemRiskAssessmentService(db)
    row = service.create_classification_taxonomy_template(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        taxonomy_json=payload.taxonomy_json,
        methodology_version=payload.methodology_version,
        is_default=payload.is_default,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_risk_classification_taxonomy.created",
        entity_type="ai_system_risk_classification_taxonomy_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"name": row.name, "status": row.status, "is_default": row.is_default},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_classification_taxonomy_read(row)


@router.get(
    "/ai-risk/classification-taxonomies",
    response_model=list[AISystemRiskClassificationTaxonomyTemplateRead],
)
def list_ai_risk_classification_taxonomies(
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    is_default: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemRiskClassificationTaxonomyTemplateRead]:
    rows = AISystemRiskAssessmentService(db).list_classification_taxonomy_templates(
        organization_id=organization.id,
        status_filter=status_filter,
        include_archived=include_archived,
        is_default=is_default,
        limit=limit,
        offset=offset,
    )
    return [_risk_classification_taxonomy_read(row) for row in rows]


@router.get(
    "/ai-risk/classification-taxonomies/{taxonomy_id}",
    response_model=AISystemRiskClassificationTaxonomyTemplateRead,
)
def get_ai_risk_classification_taxonomy(
    taxonomy_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskClassificationTaxonomyTemplateRead:
    row = AISystemRiskAssessmentService(db).require_classification_taxonomy_template(
        organization_id=organization.id,
        taxonomy_id=taxonomy_id,
    )
    return _risk_classification_taxonomy_read(row)


@router.patch(
    "/ai-risk/classification-taxonomies/{taxonomy_id}",
    response_model=AISystemRiskClassificationTaxonomyTemplateRead,
)
def update_ai_risk_classification_taxonomy(
    taxonomy_id: uuid.UUID,
    payload: AISystemRiskClassificationTaxonomyTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationTaxonomyTemplateRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_classification_taxonomy_template(organization_id=organization.id, taxonomy_id=taxonomy_id)
    before = {"status": row.status, "is_default": row.is_default}
    row = service.update_classification_taxonomy_template(row=row, updates=payload.model_dump(exclude_unset=True))
    AuditService(db).write_audit_log(
        action="ai_system_risk_classification_taxonomy.updated",
        entity_type="ai_system_risk_classification_taxonomy_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status, "is_default": row.is_default},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_classification_taxonomy_read(row)


@router.post(
    "/ai-risk/classification-taxonomies/{taxonomy_id}/archive",
    response_model=AISystemRiskClassificationTaxonomyTemplateRead,
)
def archive_ai_risk_classification_taxonomy(
    taxonomy_id: uuid.UUID,
    payload: AISystemRiskClassificationTaxonomyTemplateArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationTaxonomyTemplateRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_classification_taxonomy_template(organization_id=organization.id, taxonomy_id=taxonomy_id)
    row = service.archive_classification_taxonomy_template(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_risk_classification_taxonomy.archived",
        entity_type="ai_system_risk_classification_taxonomy_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "is_default": row.is_default},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_classification_taxonomy_read(row)


@router.post(
    "/ai-risk/classification-taxonomies/{taxonomy_id}/set-default",
    response_model=AISystemRiskClassificationTaxonomyTemplateRead,
)
def set_ai_risk_classification_taxonomy_default(
    taxonomy_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationTaxonomyTemplateRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_classification_taxonomy_template(organization_id=organization.id, taxonomy_id=taxonomy_id)
    row = service.set_default_classification_taxonomy_template(row=row)
    AuditService(db).write_audit_log(
        action="ai_system_risk_classification_taxonomy.default_set",
        entity_type="ai_system_risk_classification_taxonomy_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "is_default": row.is_default},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_classification_taxonomy_read(row)


@router.get("/ai-risk/scoring-profiles", response_model=list[AISystemRiskScoringProfileRead])
def list_ai_risk_scoring_profiles(
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    is_default: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemRiskScoringProfileRead]:
    rows = AISystemRiskAssessmentService(db).list_scoring_profiles(
        organization_id=organization.id,
        status_filter=status_filter,
        include_archived=include_archived,
        is_default=is_default,
        limit=limit,
        offset=offset,
    )
    return [_risk_scoring_profile_read(row) for row in rows]


@router.get("/ai-risk/scoring-profiles/{profile_id}", response_model=AISystemRiskScoringProfileRead)
def get_ai_risk_scoring_profile(
    profile_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskScoringProfileRead:
    row = AISystemRiskAssessmentService(db).require_scoring_profile(
        organization_id=organization.id,
        profile_id=profile_id,
    )
    return _risk_scoring_profile_read(row)


@router.patch("/ai-risk/scoring-profiles/{profile_id}", response_model=AISystemRiskScoringProfileRead)
def update_ai_risk_scoring_profile(
    profile_id: uuid.UUID,
    payload: AISystemRiskScoringProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskScoringProfileRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_scoring_profile(organization_id=organization.id, profile_id=profile_id)
    before = {
        "status": row.status,
        "is_default": row.is_default,
        "methodology_version": row.methodology_version,
    }
    row = service.update_scoring_profile(row=row, updates=payload.model_dump(exclude_unset=True))
    AuditService(db).write_audit_log(
        action="ai_system_risk_scoring_profile.updated",
        entity_type="ai_system_risk_scoring_profile",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "status": row.status,
            "is_default": row.is_default,
            "methodology_version": row.methodology_version,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_scoring_profile_read(row)


@router.post("/ai-risk/scoring-profiles/{profile_id}/archive", response_model=AISystemRiskScoringProfileRead)
def archive_ai_risk_scoring_profile(
    profile_id: uuid.UUID,
    payload: AISystemRiskScoringProfileArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskScoringProfileRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_scoring_profile(organization_id=organization.id, profile_id=profile_id)
    row = service.archive_scoring_profile(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_risk_scoring_profile.archived",
        entity_type="ai_system_risk_scoring_profile",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": row.status,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "is_default": row.is_default,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_scoring_profile_read(row)


@router.post("/ai-risk/scoring-profiles/{profile_id}/set-default", response_model=AISystemRiskScoringProfileRead)
def set_ai_risk_scoring_profile_default(
    profile_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskScoringProfileRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_scoring_profile(organization_id=organization.id, profile_id=profile_id)
    row = service.set_default_scoring_profile(row=row)
    AuditService(db).write_audit_log(
        action="ai_system_risk_scoring_profile.default_set",
        entity_type="ai_system_risk_scoring_profile",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"is_default": row.is_default, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_scoring_profile_read(row)


@router.post("/ai-risk/scoring-profiles/{profile_id}/preview-score", response_model=AISystemRiskScorePreviewResponse)
def preview_ai_risk_scoring_profile(
    profile_id: uuid.UUID,
    payload: AISystemRiskScorePreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskScorePreviewResponse:
    service = AISystemRiskAssessmentService(db)
    profile = service.require_scoring_profile(organization_id=organization.id, profile_id=profile_id)
    score, calculated_level, explanation = service.preview_with_scoring_profile(
        profile=profile,
        likelihood=payload.likelihood,
        impact=payload.impact,
    )
    explanation["profile"] = service.profile_snapshot_json(profile)
    explanation["caveat"] = AI_RISK_SCORING_CAVEAT
    return AISystemRiskScorePreviewResponse(
        inherent_risk_score=score,
        calculated_risk_level=calculated_level,
        score_explanation=explanation,
        caveat=AI_RISK_SCORING_CAVEAT,
    )


@router.post("/ai-risk/assessments/{assessment_id}/recalculate-score", response_model=AISystemRiskAssessmentRead)
def recalculate_ai_risk_assessment_score(
    assessment_id: uuid.UUID,
    payload: AISystemRiskAssessmentRecalculateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskAssessmentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    before = {
        "risk_level": row.risk_level,
        "inherent_risk_score": row.inherent_risk_score,
        "calculated_risk_level": row.calculated_risk_level,
        "scoring_profile_id": str(row.scoring_profile_id) if row.scoring_profile_id else None,
    }
    row = service.recalculate_assessment_score(
        assessment=row,
        scoring_profile_id=payload.scoring_profile_id,
        apply_calculated_to_manual=payload.apply_calculated_risk_level_to_manual_risk_level,
    )
    AuditService(db).write_audit_log(
        action="ai_system_risk_assessment.score_recalculated",
        entity_type="ai_system_risk_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "risk_level": row.risk_level,
            "inherent_risk_score": row.inherent_risk_score,
            "calculated_risk_level": row.calculated_risk_level,
            "scoring_profile_id": str(row.scoring_profile_id) if row.scoring_profile_id else None,
        },
        metadata_json={
            "source": "api",
            "apply_calculated_risk_level_to_manual_risk_level": payload.apply_calculated_risk_level_to_manual_risk_level,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_assessment_read(row)


@router.post("/ai-risk/assessments/{assessment_id}/apply-dimension-template", response_model=AISystemRiskAssessmentRead)
def apply_ai_risk_dimension_template_to_assessment(
    assessment_id: uuid.UUID,
    payload: AISystemRiskAssessmentApplyDimensionTemplateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskAssessmentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    before = {
        "dimension_template_id": str(row.dimension_template_id) if row.dimension_template_id else None,
        "dimension_weighted_score": row.dimension_weighted_score,
        "calculated_dimension_risk_level": row.calculated_dimension_risk_level,
    }
    row = service.apply_dimension_template(
        assessment=row,
        dimension_template_id=payload.dimension_template_id,
        dimension_inputs_json=payload.dimension_inputs_json,
    )
    AuditService(db).write_audit_log(
        action="ai_system_risk_assessment.dimension_template_applied",
        entity_type="ai_system_risk_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "dimension_template_id": str(row.dimension_template_id) if row.dimension_template_id else None,
            "dimension_weighted_score": row.dimension_weighted_score,
            "calculated_dimension_risk_level": row.calculated_dimension_risk_level,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_assessment_read(row)


@router.post(
    "/ai-risk/assessments/{assessment_id}/preview-residual-risk",
    response_model=AISystemRiskAssessmentResidualRiskPreviewResponse,
)
def preview_ai_risk_assessment_residual_risk(
    assessment_id: uuid.UUID,
    payload: AISystemRiskAssessmentResidualRiskPreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskAssessmentResidualRiskPreviewResponse:
    service = AISystemRiskAssessmentService(db)
    row = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    score, calculated_level, explanation = service.preview_residual_risk(
        assessment=row,
        residual_likelihood=payload.residual_likelihood,
        residual_impact=payload.residual_impact,
        scoring_profile_id=payload.scoring_profile_id,
    )
    return AISystemRiskAssessmentResidualRiskPreviewResponse(
        residual_risk_score=score,
        calculated_residual_risk_level=calculated_level,
        residual_score_explanation=explanation,
        caveat=AI_RISK_DIMENSION_CAVEAT,
    )


@router.post("/ai-risk/assessments/{assessment_id}/apply-residual-risk", response_model=AISystemRiskAssessmentRead)
def apply_ai_risk_assessment_residual_risk(
    assessment_id: uuid.UUID,
    payload: AISystemRiskAssessmentApplyResidualRiskRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskAssessmentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    before = {
        "residual_likelihood": row.residual_likelihood,
        "residual_impact": row.residual_impact,
        "residual_risk_score": row.residual_risk_score,
        "calculated_residual_risk_level": row.calculated_residual_risk_level,
    }
    row = service.apply_residual_risk(
        assessment=row,
        residual_likelihood=payload.residual_likelihood,
        residual_impact=payload.residual_impact,
        scoring_profile_id=payload.scoring_profile_id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_risk_assessment.residual_risk_applied",
        entity_type="ai_system_risk_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "residual_likelihood": row.residual_likelihood,
            "residual_impact": row.residual_impact,
            "residual_risk_score": row.residual_risk_score,
            "calculated_residual_risk_level": row.calculated_residual_risk_level,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_assessment_read(row)


@router.post("/ai-risk/assessments", response_model=AISystemRiskAssessmentRead, status_code=status.HTTP_201_CREATED)
def create_ai_risk_assessment(
    payload: AISystemRiskAssessmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskAssessmentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.create_assessment(
        organization_id=organization.id,
        ai_system_id=payload.ai_system_id,
        title=payload.title,
        description=payload.description,
        assessment_type=payload.assessment_type,
        status_value=payload.status,
        owner_user_id=payload.owner_user_id,
        risk_level=payload.risk_level,
        likelihood=payload.likelihood,
        impact=payload.impact,
        risk_dimensions_json=payload.risk_dimensions_json,
        risk_factors_json=payload.risk_factors_json,
        mitigation_summary=payload.mitigation_summary,
        assumptions=payload.assumptions,
        limitations=payload.limitations,
        methodology_version=payload.methodology_version,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_risk_assessment.created",
        entity_type="ai_system_risk_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "ai_system_id": str(row.ai_system_id),
            "assessment_type": row.assessment_type,
            "status": row.status,
            "risk_level": row.risk_level,
            "likelihood": row.likelihood,
            "impact": row.impact,
            "inherent_risk_score": row.inherent_risk_score,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_assessment_read(row)


@router.get("/ai-risk/assessments/summary", response_model=AISystemRiskAssessmentSummary)
def get_ai_risk_assessment_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskAssessmentSummary:
    summary = AISystemRiskAssessmentService(db).summary(organization_id=organization.id)
    return AISystemRiskAssessmentSummary(**summary)


@router.get("/ai-risk/assessments", response_model=list[AISystemRiskAssessmentRead])
def list_ai_risk_assessments(
    ai_system_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    risk_level: str | None = Query(default=None),
    assessment_type: str | None = Query(default=None),
    owner_user_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemRiskAssessmentRead]:
    rows = AISystemRiskAssessmentService(db).list_assessments(
        organization_id=organization.id,
        ai_system_id=ai_system_id,
        status_filter=status_filter,
        risk_level=risk_level,
        assessment_type=assessment_type,
        owner_user_id=owner_user_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_risk_assessment_read(row) for row in rows]


@router.get("/ai-risk/assessments/{assessment_id}", response_model=AISystemRiskAssessmentRead)
def get_ai_risk_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskAssessmentRead:
    row = AISystemRiskAssessmentService(db).require_assessment(
        organization_id=organization.id,
        assessment_id=assessment_id,
    )
    return _risk_assessment_read(row)


@router.patch("/ai-risk/assessments/{assessment_id}", response_model=AISystemRiskAssessmentRead)
def update_ai_risk_assessment(
    assessment_id: uuid.UUID,
    payload: AISystemRiskAssessmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskAssessmentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    before = {
        "status": row.status,
        "risk_level": row.risk_level,
        "likelihood": row.likelihood,
        "impact": row.impact,
        "inherent_risk_score": row.inherent_risk_score,
    }
    row = service.update_assessment(row=row, updates=payload.model_dump(exclude_unset=True))
    AuditService(db).write_audit_log(
        action="ai_system_risk_assessment.updated",
        entity_type="ai_system_risk_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "status": row.status,
            "risk_level": row.risk_level,
            "likelihood": row.likelihood,
            "impact": row.impact,
            "inherent_risk_score": row.inherent_risk_score,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_assessment_read(row)


@router.post("/ai-risk/assessments/{assessment_id}/submit-for-review", response_model=AISystemRiskAssessmentRead)
def submit_ai_risk_assessment_for_review(
    assessment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskAssessmentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    row = service.submit_for_review(row=row)
    AuditService(db).write_audit_log(
        action="ai_system_risk_assessment.submitted_for_review",
        entity_type="ai_system_risk_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_assessment_read(row)


@router.post("/ai-risk/assessments/{assessment_id}/complete", response_model=AISystemRiskAssessmentRead)
def complete_ai_risk_assessment(
    assessment_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskAssessmentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    row = service.complete(row=row)
    snapshot = service.create_snapshot(row=row, snapshot_type="completion_snapshot", actor_user_id=current_user.id)

    audit = AuditService(db)
    audit.write_audit_log(
        action="ai_system_risk_assessment.completed",
        entity_type="ai_system_risk_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "completed_at": row.completed_at.isoformat() if row.completed_at else None},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    audit.write_audit_log(
        action="ai_system_risk_assessment_snapshot.created",
        entity_type="ai_system_risk_assessment_snapshot",
        entity_id=snapshot.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "risk_assessment_id": str(snapshot.risk_assessment_id),
            "snapshot_type": snapshot.snapshot_type,
            "snapshot_version": snapshot.snapshot_version,
            "snapshot_sha256": snapshot.snapshot_sha256,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_assessment_read(row)


@router.post("/ai-risk/assessments/{assessment_id}/archive", response_model=AISystemRiskAssessmentRead)
def archive_ai_risk_assessment(
    assessment_id: uuid.UUID,
    payload: AISystemRiskAssessmentArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskAssessmentRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    row = service.archive(row=row, actor_user_id=current_user.id)
    snapshot = service.create_snapshot(row=row, snapshot_type="archive_snapshot", actor_user_id=current_user.id)

    audit = AuditService(db)
    audit.write_audit_log(
        action="ai_system_risk_assessment.archived",
        entity_type="ai_system_risk_assessment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": row.status,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    audit.write_audit_log(
        action="ai_system_risk_assessment_snapshot.created",
        entity_type="ai_system_risk_assessment_snapshot",
        entity_id=snapshot.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "risk_assessment_id": str(snapshot.risk_assessment_id),
            "snapshot_type": snapshot.snapshot_type,
            "snapshot_version": snapshot.snapshot_version,
            "snapshot_sha256": snapshot.snapshot_sha256,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _risk_assessment_read(row)


@router.post(
    "/ai-risk/assessments/{assessment_id}/snapshots",
    response_model=AISystemRiskAssessmentSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_risk_assessment_snapshot(
    assessment_id: uuid.UUID,
    payload: AISystemRiskAssessmentManualSnapshotRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskAssessmentSnapshotRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    snapshot = service.create_snapshot(row=row, snapshot_type="manual_snapshot", actor_user_id=current_user.id)

    AuditService(db).write_audit_log(
        action="ai_system_risk_assessment_snapshot.created",
        entity_type="ai_system_risk_assessment_snapshot",
        entity_id=snapshot.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "risk_assessment_id": str(snapshot.risk_assessment_id),
            "snapshot_type": snapshot.snapshot_type,
            "snapshot_version": snapshot.snapshot_version,
            "snapshot_sha256": snapshot.snapshot_sha256,
        },
        metadata_json={"source": "api", "note": payload.note},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(snapshot)
    return _risk_assessment_snapshot_read(snapshot)


@router.get("/ai-risk/assessments/{assessment_id}/snapshots", response_model=list[AISystemRiskAssessmentSnapshotRead])
def list_ai_risk_assessment_snapshots(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemRiskAssessmentSnapshotRead]:
    service = AISystemRiskAssessmentService(db)
    service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    rows = service.list_snapshots(organization_id=organization.id, assessment_id=assessment_id)
    return [_risk_assessment_snapshot_read(row) for row in rows]


@router.get("/ai-risk/assessment-snapshots/{snapshot_id}", response_model=AISystemRiskAssessmentSnapshotRead)
def get_ai_risk_assessment_snapshot(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskAssessmentSnapshotRead:
    row = AISystemRiskAssessmentService(db).require_snapshot(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
    )
    return _risk_assessment_snapshot_read(row)


@router.post(
    "/ai-risk/assessments/{assessment_id}/classifications",
    response_model=AISystemRiskClassificationRecordRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_risk_assessment_classification(
    assessment_id: uuid.UUID,
    payload: AISystemRiskClassificationRecordCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationRecordRead:
    service = AISystemRiskAssessmentService(db)
    assessment = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    row = service.create_classification_record(
        assessment=assessment,
        taxonomy_template_id=payload.taxonomy_template_id,
        classification_json=payload.classification_json,
        confidence_level=payload.confidence_level,
        justification=payload.justification,
        source_type=payload.source_type,
        source_reference=payload.source_reference,
        evidence_ids_json=payload.evidence_ids_json,
        control_ids_json=payload.control_ids_json,
        risk_ids_json=payload.risk_ids_json,
        supersede_previous=payload.supersede_previous,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_risk_classification_record.created",
        entity_type="ai_system_risk_classification_record",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "risk_assessment_id": str(row.risk_assessment_id),
            "status": row.status,
            "confidence_level": row.confidence_level,
            "taxonomy_template_id": str(row.taxonomy_template_id) if row.taxonomy_template_id else None,
        },
        metadata_json={"source": "api", "supersede_previous": payload.supersede_previous},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _classification_row_with_metadata(db, row)


@router.get(
    "/ai-risk/assessments/{assessment_id}/classifications",
    response_model=list[AISystemRiskClassificationRecordRead],
)
def list_ai_risk_assessment_classifications(
    assessment_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    confidence_level: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemRiskClassificationRecordRead]:
    service = AISystemRiskAssessmentService(db)
    service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    rows = service.list_classification_records(
        organization_id=organization.id,
        assessment_id=assessment_id,
        status_filter=status_filter,
        include_archived=include_archived,
        confidence_level=confidence_level,
    )
    return [_classification_row_with_metadata(db, row) for row in rows]


@router.get(
    "/ai-risk/classifications/summary",
    response_model=AISystemRiskClassificationSummary,
)
def get_ai_risk_classification_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskClassificationSummary:
    summary = AISystemRiskAssessmentService(db).classification_summary(organization_id=organization.id)
    return AISystemRiskClassificationSummary(**summary)


@router.get(
    "/ai-risk/classifications/{classification_id}",
    response_model=AISystemRiskClassificationRecordRead,
)
def get_ai_risk_classification_record(
    classification_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskClassificationRecordRead:
    row = AISystemRiskAssessmentService(db).require_classification_record(
        organization_id=organization.id,
        classification_id=classification_id,
    )
    return _classification_row_with_metadata(db, row)


@router.post(
    "/ai-risk/classifications/{classification_id}/archive",
    response_model=AISystemRiskClassificationRecordRead,
)
def archive_ai_risk_classification_record(
    classification_id: uuid.UUID,
    payload: AISystemRiskClassificationRecordArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationRecordRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_classification_record(organization_id=organization.id, classification_id=classification_id)
    row = service.archive_classification_record(row=row, actor_user_id=current_user.id)
    snapshot = service.create_classification_snapshot(
        row=row,
        snapshot_type="archive_snapshot",
        actor_user_id=current_user.id,
    )
    audit = AuditService(db)
    audit.write_audit_log(
        action="ai_system_risk_classification_record.archived",
        entity_type="ai_system_risk_classification_record",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": row.status,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    audit.write_audit_log(
        action="ai_system_risk_classification_snapshot.created",
        entity_type="ai_system_risk_classification_record_snapshot",
        entity_id=snapshot.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "classification_id": str(snapshot.classification_id),
            "snapshot_type": snapshot.snapshot_type,
            "snapshot_version": snapshot.snapshot_version,
            "snapshot_sha256": snapshot.snapshot_sha256,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _classification_row_with_metadata(db, row)


@router.post(
    "/ai-risk/classifications/{classification_id}/submit-for-review",
    response_model=AISystemRiskClassificationRecordRead,
)
def submit_ai_risk_classification_for_review(
    classification_id: uuid.UUID,
    payload: AISystemRiskClassificationSubmitForReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationRecordRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_classification_record(organization_id=organization.id, classification_id=classification_id)
    row, snapshot, _ = service.submit_classification_for_review(
        row=row,
        note=payload.note,
        actor_user_id=current_user.id,
    )
    audit = AuditService(db)
    audit.write_audit_log(
        action="ai_system_risk_classification_record.submitted_for_review",
        entity_type="ai_system_risk_classification_record",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"review_status": row.review_status},
        metadata_json={"source": "api", "note": payload.note},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    audit.write_audit_log(
        action="ai_system_risk_classification_snapshot.created",
        entity_type="ai_system_risk_classification_record_snapshot",
        entity_id=snapshot.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "classification_id": str(snapshot.classification_id),
            "snapshot_type": snapshot.snapshot_type,
            "snapshot_version": snapshot.snapshot_version,
            "snapshot_sha256": snapshot.snapshot_sha256,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _classification_row_with_metadata(db, row)


@router.post(
    "/ai-risk/classifications/{classification_id}/request-changes",
    response_model=AISystemRiskClassificationRecordRead,
)
def request_ai_risk_classification_changes(
    classification_id: uuid.UUID,
    payload: AISystemRiskClassificationRequestChangesRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationRecordRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_classification_record(organization_id=organization.id, classification_id=classification_id)
    row, snapshot, _ = service.request_classification_changes(
        row=row,
        change_request_note=payload.change_request_note,
        actor_user_id=current_user.id,
    )
    audit = AuditService(db)
    audit.write_audit_log(
        action="ai_system_risk_classification_record.changes_requested",
        entity_type="ai_system_risk_classification_record",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"review_status": row.review_status, "change_request_note": row.change_request_note},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    audit.write_audit_log(
        action="ai_system_risk_classification_snapshot.created",
        entity_type="ai_system_risk_classification_record_snapshot",
        entity_id=snapshot.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "classification_id": str(snapshot.classification_id),
            "snapshot_type": snapshot.snapshot_type,
            "snapshot_version": snapshot.snapshot_version,
            "snapshot_sha256": snapshot.snapshot_sha256,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _classification_row_with_metadata(db, row)


@router.post(
    "/ai-risk/classifications/{classification_id}/mark-reviewed",
    response_model=AISystemRiskClassificationRecordRead,
)
def mark_ai_risk_classification_reviewed(
    classification_id: uuid.UUID,
    payload: AISystemRiskClassificationMarkReviewedRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationRecordRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_classification_record(organization_id=organization.id, classification_id=classification_id)
    row, snapshot, _ = service.mark_classification_reviewed(
        row=row,
        review_note=payload.review_note,
        actor_user_id=current_user.id,
    )
    audit = AuditService(db)
    audit.write_audit_log(
        action="ai_system_risk_classification_record.reviewed",
        entity_type="ai_system_risk_classification_record",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "review_status": row.review_status,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        },
        metadata_json={"source": "api", "review_note": payload.review_note},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    audit.write_audit_log(
        action="ai_system_risk_classification_snapshot.created",
        entity_type="ai_system_risk_classification_record_snapshot",
        entity_id=snapshot.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "classification_id": str(snapshot.classification_id),
            "snapshot_type": snapshot.snapshot_type,
            "snapshot_version": snapshot.snapshot_version,
            "snapshot_sha256": snapshot.snapshot_sha256,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _classification_row_with_metadata(db, row)


@router.post(
    "/ai-risk/classifications/{classification_id}/reject",
    response_model=AISystemRiskClassificationRecordRead,
)
def reject_ai_risk_classification(
    classification_id: uuid.UUID,
    payload: AISystemRiskClassificationRejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationRecordRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_classification_record(organization_id=organization.id, classification_id=classification_id)
    row, snapshot, _ = service.reject_classification(
        row=row,
        rejection_reason=payload.rejection_reason,
        actor_user_id=current_user.id,
    )
    audit = AuditService(db)
    audit.write_audit_log(
        action="ai_system_risk_classification_record.rejected",
        entity_type="ai_system_risk_classification_record",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"review_status": row.review_status, "rejection_reason": row.rejection_reason},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    audit.write_audit_log(
        action="ai_system_risk_classification_snapshot.created",
        entity_type="ai_system_risk_classification_record_snapshot",
        entity_id=snapshot.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "classification_id": str(snapshot.classification_id),
            "snapshot_type": snapshot.snapshot_type,
            "snapshot_version": snapshot.snapshot_version,
            "snapshot_sha256": snapshot.snapshot_sha256,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _classification_row_with_metadata(db, row)


@router.post(
    "/ai-risk/classifications/{classification_id}/snapshots",
    response_model=AISystemRiskClassificationSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_risk_classification_snapshot(
    classification_id: uuid.UUID,
    payload: AISystemRiskClassificationSnapshotCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemRiskClassificationSnapshotRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_classification_record(organization_id=organization.id, classification_id=classification_id)
    snapshot = service.create_classification_snapshot(
        row=row,
        snapshot_type=payload.snapshot_type,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_risk_classification_snapshot.created",
        entity_type="ai_system_risk_classification_record_snapshot",
        entity_id=snapshot.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "classification_id": str(snapshot.classification_id),
            "snapshot_type": snapshot.snapshot_type,
            "snapshot_version": snapshot.snapshot_version,
            "snapshot_sha256": snapshot.snapshot_sha256,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(snapshot)
    return _risk_classification_snapshot_read(snapshot)


@router.get(
    "/ai-risk/classifications/{classification_id}/snapshots",
    response_model=list[AISystemRiskClassificationSnapshotRead],
)
def list_ai_risk_classification_snapshots(
    classification_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemRiskClassificationSnapshotRead]:
    service = AISystemRiskAssessmentService(db)
    service.require_classification_record(organization_id=organization.id, classification_id=classification_id)
    rows = service.list_classification_snapshots(
        organization_id=organization.id,
        classification_id=classification_id,
    )
    return [_risk_classification_snapshot_read(row) for row in rows]


@router.get(
    "/ai-risk/classification-snapshots/{snapshot_id}",
    response_model=AISystemRiskClassificationSnapshotRead,
)
def get_ai_risk_classification_snapshot(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskClassificationSnapshotRead:
    row = AISystemRiskAssessmentService(db).require_classification_snapshot(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
    )
    return _risk_classification_snapshot_read(row)


@router.get("/signals/summary", response_model=GovernanceSignalSummary)
def get_governance_signals_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceSignalSummary:
    summary = AISystemRiskAssessmentService(db).governance_signal_summary(organization_id=organization.id)
    return GovernanceSignalSummary(**summary)


@router.get("/signals/priority-summary", response_model=GovernanceSignalPrioritySummary)
def get_governance_signals_priority_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceSignalPrioritySummary:
    summary = AISystemRiskAssessmentService(db).governance_signal_priority_summary(organization_id=organization.id)
    return GovernanceSignalPrioritySummary(**summary)


@router.get("/actions/templates", response_model=GovernanceActionTemplateCatalogResponse)
def list_governance_action_templates(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceActionTemplateCatalogResponse:
    _ = organization
    templates = AISystemRiskAssessmentService.governance_action_template_catalog()
    return GovernanceActionTemplateCatalogResponse(
        templates=[_governance_action_template_read(item) for item in templates],
        count=len(templates),
        caveat=AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT,
    )


@router.get("/actions/candidates/explain", response_model=GovernanceCandidateActionRead)
def explain_governance_candidate_action(
    action_key: str = Query(min_length=1),
    related_ai_system_id: uuid.UUID | None = Query(default=None),
    related_risk_assessment_id: uuid.UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCandidateActionRead:
    rows = AISystemRiskAssessmentService(db).list_candidate_actions(
        organization_id=organization.id,
        related_ai_system_id=related_ai_system_id,
        related_risk_assessment_id=related_risk_assessment_id,
        entity_type=entity_type,
        entity_id=entity_id,
        priority_band=None,
        action_type=None,
        reason_code=None,
        limit=500,
        offset=0,
    )
    matched = next((row for row in rows if row["action_key"] == action_key), None)
    if matched is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate action not found")
    return _governance_candidate_action_read(matched)


@router.get("/actions/candidates", response_model=list[GovernanceCandidateActionRead])
def list_governance_candidate_actions(
    related_ai_system_id: uuid.UUID | None = Query(default=None),
    related_risk_assessment_id: uuid.UUID | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    priority_band: str | None = Query(default=None, pattern="^(low|medium|high|urgent)$"),
    action_type: str | None = Query(
        default=None,
        pattern="^(create_record|update_record|review_record|attach_evidence|resolve_issue|create_snapshot|refresh_signals|prepare_draft)$",
    ),
    reason_code: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceCandidateActionRead]:
    rows = AISystemRiskAssessmentService(db).list_candidate_actions(
        organization_id=organization.id,
        related_ai_system_id=related_ai_system_id,
        related_risk_assessment_id=related_risk_assessment_id,
        entity_type=entity_type,
        entity_id=entity_id,
        priority_band=priority_band,
        action_type=action_type,
        reason_code=reason_code,
        limit=limit,
        offset=offset,
    )
    return [_governance_candidate_action_read(item) for item in rows]


@router.get("/actions/candidate-summary", response_model=GovernanceCandidateActionSummary)
def get_governance_candidate_action_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCandidateActionSummary:
    payload = AISystemRiskAssessmentService(db).candidate_action_summary(organization_id=organization.id)
    return GovernanceCandidateActionSummary(**payload)


@router.get("/copilot/draft-types", response_model=GovernanceCopilotDraftTypeCatalogResponse)
def list_governance_copilot_draft_types(
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftTypeCatalogResponse:
    _ = organization
    draft_types = GovernanceCopilotDraftService.draft_type_catalog()
    return GovernanceCopilotDraftTypeCatalogResponse(
        draft_types=[GovernanceCopilotDraftTypeRead(**item) for item in draft_types],
        count=len(draft_types),
        caveat=GOVERNANCE_COPILOT_DRAFT_CAVEAT,
    )


@router.post("/copilot/drafts/preview", response_model=GovernanceCopilotDraftPreviewRead)
def preview_governance_copilot_draft(
    payload: GovernanceCopilotDraftPreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftPreviewRead:
    result = GovernanceCopilotDraftService(db).preview_draft(
        organization_id=organization.id,
        draft_type=payload.draft_type,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        include_resolved_signals=payload.include_resolved_signals,
        include_dismissed_recommendations=payload.include_dismissed_recommendations,
    )
    return GovernanceCopilotDraftPreviewRead(**result)


@router.get("/ai-systems/{ai_system_id}/copilot-brief", response_model=GovernanceCopilotDraftPreviewRead)
def get_ai_system_copilot_brief(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftPreviewRead:
    payload = GovernanceCopilotDraftService(db).ai_system_copilot_brief(
        organization_id=organization.id,
        ai_system_id=ai_system_id,
    )
    return GovernanceCopilotDraftPreviewRead(**payload)


@router.get("/ai-risk/assessments/{assessment_id}/copilot-brief", response_model=GovernanceCopilotDraftPreviewRead)
def get_risk_assessment_copilot_brief(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftPreviewRead:
    payload = GovernanceCopilotDraftService(db).risk_assessment_copilot_brief(
        organization_id=organization.id,
        assessment_id=assessment_id,
    )
    return GovernanceCopilotDraftPreviewRead(**payload)


@router.get(
    "/recommendations/snapshots/{snapshot_id}/copilot-summary",
    response_model=GovernanceCopilotDraftPreviewRead,
)
def get_recommendation_snapshot_copilot_summary(
    snapshot_id: uuid.UUID,
    include_dispositions: bool = Query(default=True),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftPreviewRead:
    payload = GovernanceCopilotDraftService(db).recommendation_snapshot_copilot_summary(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
        include_dispositions=include_dispositions,
    )
    return GovernanceCopilotDraftPreviewRead(**payload)


@router.get("/copilot/executive-risk-summary", response_model=GovernanceCopilotDraftPreviewRead)
def get_executive_risk_copilot_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftPreviewRead:
    payload = GovernanceCopilotDraftService(db).executive_risk_summary(organization_id=organization.id)
    return GovernanceCopilotDraftPreviewRead(**payload)


@router.post(
    "/copilot/draft-snapshots/preview",
    response_model=GovernanceCopilotDraftSnapshotPreviewResponse,
)
def preview_governance_copilot_draft_snapshot(
    payload: GovernanceCopilotDraftSnapshotPreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftSnapshotPreviewResponse:
    result = GovernanceCopilotDraftService(db).preview_draft_snapshot(
        organization_id=organization.id,
        draft_type=payload.draft_type,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        include_resolved_signals=payload.include_resolved_signals,
        include_dismissed_recommendations=payload.include_dismissed_recommendations,
    )
    return GovernanceCopilotDraftSnapshotPreviewResponse(**result)


@router.post(
    "/copilot/draft-snapshots",
    response_model=GovernanceCopilotDraftSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_governance_copilot_draft_snapshot(
    payload: GovernanceCopilotDraftSnapshotCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceCopilotDraftSnapshotRead:
    service = GovernanceCopilotDraftService(db)
    row = service.create_draft_snapshot(
        organization_id=organization.id,
        draft_type=payload.draft_type,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        include_resolved_signals=payload.include_resolved_signals,
        include_dismissed_recommendations=payload.include_dismissed_recommendations,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_copilot_draft_snapshot.created",
        entity_type="governance_copilot_draft_snapshot",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "draft_type": row.draft_type,
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id else None,
            "snapshot_version": int(row.snapshot_version),
            "snapshot_sha256": row.snapshot_sha256,
            "source_context_hash": row.source_context_hash,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_copilot_draft_snapshot_read(row)


@router.get(
    "/copilot/draft-snapshots/latest",
    response_model=GovernanceCopilotDraftSnapshotRead,
)
def get_latest_governance_copilot_draft_snapshot(
    draft_type: str = Query(pattern=GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN),
    scope_type: str = Query(pattern=GOVERNANCE_COPILOT_SCOPE_TYPE_PATTERN),
    scope_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftSnapshotRead:
    row = GovernanceCopilotDraftService(db).latest_draft_snapshot(
        organization_id=organization.id,
        draft_type=draft_type,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return _governance_copilot_draft_snapshot_read(row)


@router.get(
    "/copilot/draft-snapshots/summary",
    response_model=GovernanceCopilotDraftSnapshotSummary,
)
def get_governance_copilot_draft_snapshot_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftSnapshotSummary:
    payload = GovernanceCopilotDraftService(db).draft_snapshot_summary(organization_id=organization.id)
    return GovernanceCopilotDraftSnapshotSummary(**payload)


@router.get(
    "/copilot/draft-snapshots",
    response_model=list[GovernanceCopilotDraftSnapshotRead],
)
def list_governance_copilot_draft_snapshots(
    draft_type: str | None = Query(default=None, pattern=GOVERNANCE_COPILOT_DRAFT_TYPE_PATTERN),
    scope_type: str | None = Query(default=None, pattern=GOVERNANCE_COPILOT_SCOPE_TYPE_PATTERN),
    scope_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceCopilotDraftSnapshotRead]:
    rows = GovernanceCopilotDraftService(db).list_draft_snapshots(
        organization_id=organization.id,
        draft_type=draft_type,
        scope_type=scope_type,
        scope_id=scope_id,
        limit=limit,
        offset=offset,
    )
    return [_governance_copilot_draft_snapshot_read(row) for row in rows]


@router.get(
    "/copilot/draft-snapshots/{snapshot_id}",
    response_model=GovernanceCopilotDraftSnapshotRead,
)
def get_governance_copilot_draft_snapshot_detail(
    snapshot_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftSnapshotRead:
    row = GovernanceCopilotDraftService(db).require_draft_snapshot(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
    )
    return _governance_copilot_draft_snapshot_read(row)


@router.get(
    "/copilot/draft-snapshots/{snapshot_id}/diff",
    response_model=GovernanceCopilotDraftSnapshotDiffResponse,
)
def diff_governance_copilot_draft_snapshots(
    snapshot_id: uuid.UUID,
    compare_to_snapshot_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceCopilotDraftSnapshotDiffResponse:
    payload = GovernanceCopilotDraftService(db).diff_draft_snapshots(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
        compare_to_snapshot_id=compare_to_snapshot_id,
    )
    return GovernanceCopilotDraftSnapshotDiffResponse(**payload)


@router.post(
    "/recommendations/snapshots/preview",
    response_model=GovernanceRecommendationSnapshotPreviewResponse,
)
def preview_governance_recommendation_snapshot(
    payload: GovernanceRecommendationSnapshotPreviewRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceRecommendationSnapshotPreviewResponse:
    filters = payload.filters
    result = AISystemRiskAssessmentService(db).preview_recommendation_snapshot(
        organization_id=organization.id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        priority_band=filters.priority_band if filters else None,
        action_type=filters.action_type if filters else None,
        reason_code=filters.reason_code if filters else None,
    )
    return GovernanceRecommendationSnapshotPreviewResponse(**result)


@router.post(
    "/recommendations/snapshots",
    response_model=GovernanceRecommendationSnapshotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_governance_recommendation_snapshot(
    payload: GovernanceRecommendationSnapshotCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceRecommendationSnapshotRead:
    filters = payload.filters
    service = AISystemRiskAssessmentService(db)
    row = service.create_recommendation_snapshot(
        organization_id=organization.id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        priority_band=filters.priority_band if filters else None,
        action_type=filters.action_type if filters else None,
        reason_code=filters.reason_code if filters else None,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_recommendation_snapshot.created",
        entity_type="governance_recommendation_snapshot",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id else None,
            "candidate_count": int(row.candidate_count),
            "snapshot_version": int(row.snapshot_version),
            "snapshot_sha256": row.snapshot_sha256,
        },
        metadata_json={"source": "api", "source_type": row.source_type},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_recommendation_snapshot_read(row)


@router.get(
    "/recommendations/snapshots/latest",
    response_model=GovernanceRecommendationSnapshotRead,
)
def get_latest_governance_recommendation_snapshot(
    scope_type: str = Query(pattern="^(organization|ai_system|risk_assessment)$"),
    scope_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceRecommendationSnapshotRead:
    row = AISystemRiskAssessmentService(db).latest_recommendation_snapshot(
        organization_id=organization.id,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return _governance_recommendation_snapshot_read(row)


@router.get(
    "/recommendations/snapshots/summary",
    response_model=GovernanceRecommendationSnapshotSummary,
)
def get_governance_recommendation_snapshot_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceRecommendationSnapshotSummary:
    payload = AISystemRiskAssessmentService(db).recommendation_snapshot_summary(organization_id=organization.id)
    return GovernanceRecommendationSnapshotSummary(**payload)


@router.get(
    "/recommendations/snapshots",
    response_model=list[GovernanceRecommendationSnapshotRead],
)
def list_governance_recommendation_snapshots(
    scope_type: str | None = Query(default=None, pattern="^(organization|ai_system|risk_assessment)$"),
    scope_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceRecommendationSnapshotRead]:
    rows = AISystemRiskAssessmentService(db).list_recommendation_snapshots(
        organization_id=organization.id,
        scope_type=scope_type,
        scope_id=scope_id,
        limit=limit,
        offset=offset,
    )
    return [_governance_recommendation_snapshot_read(row) for row in rows]


@router.get(
    "/recommendations/snapshots/{snapshot_id}/diff",
    response_model=GovernanceRecommendationSnapshotDiffResponse,
)
def diff_governance_recommendation_snapshots(
    snapshot_id: uuid.UUID,
    compare_to_snapshot_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceRecommendationSnapshotDiffResponse:
    payload = AISystemRiskAssessmentService(db).diff_recommendation_snapshots(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
        compare_to_snapshot_id=compare_to_snapshot_id,
    )
    return GovernanceRecommendationSnapshotDiffResponse(**payload)


@router.get(
    "/recommendations/snapshots/{snapshot_id}/actions",
    response_model=GovernanceRecommendationSnapshotActionsResponse,
)
def list_governance_recommendation_snapshot_actions(
    snapshot_id: uuid.UUID,
    include_dispositions: bool = Query(default=True),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceRecommendationSnapshotActionsResponse:
    payload = AISystemRiskAssessmentService(db).list_snapshot_actions(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
        include_dispositions=include_dispositions,
    )
    return GovernanceRecommendationSnapshotActionsResponse(
        snapshot_id=payload["snapshot_id"],
        action_count=int(payload["action_count"]),
        actions=[_governance_recommendation_snapshot_action_read(item) for item in payload["actions"]],
        caveat=payload.get("caveat", AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT),
    )


@router.post(
    "/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/acknowledge",
    response_model=GovernanceRecommendationActionDispositionRead,
)
def acknowledge_governance_recommendation_action(
    snapshot_id: uuid.UUID,
    action_identity_hash: str,
    payload: GovernanceRecommendationActionAcknowledgeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceRecommendationActionDispositionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.upsert_recommendation_action_disposition(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
        action_identity_hash=action_identity_hash,
        disposition_status="acknowledged",
        note=payload.note,
        reason=None,
        deferred_until=None,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_recommendation_action.acknowledged",
        entity_type="governance_recommendation_action_disposition",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"disposition_status": row.disposition_status, "action_identity_hash": row.action_identity_hash},
        metadata_json={"source": "api", "snapshot_id": str(snapshot_id)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_recommendation_action_disposition_read(
        service.recommendation_action_disposition_payload(row=row)
    )


@router.post(
    "/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/dismiss",
    response_model=GovernanceRecommendationActionDispositionRead,
)
def dismiss_governance_recommendation_action(
    snapshot_id: uuid.UUID,
    action_identity_hash: str,
    payload: GovernanceRecommendationActionDismissRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceRecommendationActionDispositionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.upsert_recommendation_action_disposition(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
        action_identity_hash=action_identity_hash,
        disposition_status="dismissed",
        note=payload.note,
        reason=payload.reason,
        deferred_until=None,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_recommendation_action.dismissed",
        entity_type="governance_recommendation_action_disposition",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"disposition_status": row.disposition_status, "action_identity_hash": row.action_identity_hash},
        metadata_json={"source": "api", "snapshot_id": str(snapshot_id), "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_recommendation_action_disposition_read(
        service.recommendation_action_disposition_payload(row=row)
    )


@router.post(
    "/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/defer",
    response_model=GovernanceRecommendationActionDispositionRead,
)
def defer_governance_recommendation_action(
    snapshot_id: uuid.UUID,
    action_identity_hash: str,
    payload: GovernanceRecommendationActionDeferRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceRecommendationActionDispositionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.upsert_recommendation_action_disposition(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
        action_identity_hash=action_identity_hash,
        disposition_status="deferred",
        note=payload.note,
        reason=payload.reason,
        deferred_until=payload.deferred_until,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_recommendation_action.deferred",
        entity_type="governance_recommendation_action_disposition",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "disposition_status": row.disposition_status,
            "action_identity_hash": row.action_identity_hash,
            "deferred_until": row.deferred_until.isoformat() if row.deferred_until else None,
        },
        metadata_json={"source": "api", "snapshot_id": str(snapshot_id), "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_recommendation_action_disposition_read(
        service.recommendation_action_disposition_payload(row=row)
    )


@router.post(
    "/recommendations/snapshots/{snapshot_id}/actions/{action_identity_hash}/accept-for-manual-work",
    response_model=GovernanceRecommendationActionDispositionRead,
)
def accept_governance_recommendation_action_for_manual_work(
    snapshot_id: uuid.UUID,
    action_identity_hash: str,
    payload: GovernanceRecommendationActionAcceptRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceRecommendationActionDispositionRead:
    service = AISystemRiskAssessmentService(db)
    row = service.upsert_recommendation_action_disposition(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
        action_identity_hash=action_identity_hash,
        disposition_status="accepted_for_manual_work",
        note=payload.note,
        reason=None,
        deferred_until=None,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="governance_recommendation_action.accepted_for_manual_work",
        entity_type="governance_recommendation_action_disposition",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"disposition_status": row.disposition_status, "action_identity_hash": row.action_identity_hash},
        metadata_json={"source": "api", "snapshot_id": str(snapshot_id)},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _governance_recommendation_action_disposition_read(
        service.recommendation_action_disposition_payload(row=row)
    )


@router.get(
    "/recommendations/snapshots/{snapshot_id}",
    response_model=GovernanceRecommendationSnapshotRead,
)
def get_governance_recommendation_snapshot_detail(
    snapshot_id: uuid.UUID,
    include_dispositions: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceRecommendationSnapshotRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_recommendation_snapshot(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
    )
    actions_overlay = None
    if include_dispositions:
        actions_overlay_payload = service.list_snapshot_actions(
            organization_id=organization.id,
            snapshot_id=snapshot_id,
            include_dispositions=True,
        )
        actions_overlay = [dict(item) for item in actions_overlay_payload["actions"]]
    return _governance_recommendation_snapshot_read(row, actions_overlay=actions_overlay)


@router.get(
    "/recommendations/action-dispositions/summary",
    response_model=GovernanceRecommendationActionDispositionSummary,
)
def get_governance_recommendation_action_disposition_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceRecommendationActionDispositionSummary:
    payload = AISystemRiskAssessmentService(db).recommendation_action_disposition_summary(
        organization_id=organization.id
    )
    return GovernanceRecommendationActionDispositionSummary(**payload)


@router.get(
    "/recommendations/action-dispositions",
    response_model=list[GovernanceRecommendationActionDispositionRead],
)
def list_governance_recommendation_action_dispositions(
    snapshot_id: uuid.UUID | None = Query(default=None),
    disposition_status: str | None = Query(
        default=None,
        pattern="^(acknowledged|dismissed|deferred|accepted_for_manual_work)$",
    ),
    action_key: str | None = Query(default=None),
    related_ai_system_id: uuid.UUID | None = Query(default=None),
    related_risk_assessment_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceRecommendationActionDispositionRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_recommendation_action_dispositions(
        organization_id=organization.id,
        snapshot_id=snapshot_id,
        disposition_status=disposition_status,
        action_key=action_key,
        related_ai_system_id=related_ai_system_id,
        related_risk_assessment_id=related_risk_assessment_id,
        limit=limit,
        offset=offset,
    )
    return [
        _governance_recommendation_action_disposition_read(
            service.recommendation_action_disposition_payload(row=row)
        )
        for row in rows
    ]


@router.get("/signals/prioritized", response_model=list[GovernanceSignalPrioritizedRead])
def list_prioritized_governance_signals(
    domain: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    related_ai_system_id: uuid.UUID | None = Query(default=None),
    related_risk_assessment_id: uuid.UUID | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    priority_band: str | None = Query(default=None, pattern="^(low|medium|high|urgent)$"),
    status_filter: str | None = Query(default="open", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceSignalPrioritizedRead]:
    rows = AISystemRiskAssessmentService(db).list_prioritized_governance_signals(
        organization_id=organization.id,
        domain=domain,
        entity_type=entity_type,
        related_ai_system_id=related_ai_system_id,
        related_risk_assessment_id=related_risk_assessment_id,
        signal_type=signal_type,
        reason_code=reason_code,
        severity=severity,
        status_filter=status_filter,
        priority_band=priority_band,
        limit=limit,
        offset=offset,
    )
    return [_governance_signal_prioritized_read(item) for item in rows]


@router.get("/signals/groups", response_model=list[GovernanceSignalGroupRead])
def list_governance_signal_groups(
    domain: str | None = Query(default=None),
    related_ai_system_id: uuid.UUID | None = Query(default=None),
    related_risk_assessment_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default="open", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceSignalGroupRead]:
    groups = AISystemRiskAssessmentService(db).governance_signal_groups(
        organization_id=organization.id,
        domain=domain,
        related_ai_system_id=related_ai_system_id,
        related_risk_assessment_id=related_risk_assessment_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    result: list[GovernanceSignalGroupRead] = []
    for row in groups:
        result.append(
            GovernanceSignalGroupRead(
                group_key=row["group_key"],
                group_title=row["group_title"],
                related_ai_system_id=row.get("related_ai_system_id"),
                related_risk_assessment_id=row.get("related_risk_assessment_id"),
                signal_count=int(row["signal_count"]),
                highest_priority_score=float(row["highest_priority_score"]),
                highest_priority_band=row["highest_priority_band"],
                severities_count=row["severities_count"],
                reason_codes_count=row["reason_codes_count"],
                signals=[_governance_signal_prioritized_read(item) for item in row["signals"]],
                caveat=row.get("caveat", AI_RISK_GOVERNANCE_SIGNAL_PRIORITY_CAVEAT),
            )
        )
    return result


@router.get("/signals", response_model=list[GovernanceSignalRead])
def list_governance_signals(
    domain: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    related_ai_system_id: uuid.UUID | None = Query(default=None),
    related_risk_assessment_id: uuid.UUID | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status_filter: str | None = Query(default="open", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[GovernanceSignalRead]:
    service = AISystemRiskAssessmentService(db)
    rows = service.list_governance_signals(
        organization_id=organization.id,
        domain=domain,
        entity_type=entity_type,
        entity_id=entity_id,
        related_ai_system_id=related_ai_system_id,
        related_risk_assessment_id=related_risk_assessment_id,
        signal_type=signal_type,
        reason_code=reason_code,
        severity=severity,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    priority_map = service._priority_payload_map_for_signal_rows(organization_id=organization.id, rows=rows)
    return [
        _governance_signal_read(
            service.governance_signal_payload(
                row=row,
                priority_payload=priority_map.get(row.id),
            )
        )
        for row in rows
    ]


@router.get("/signals/{signal_id}", response_model=GovernanceSignalRead)
def get_governance_signal_detail(
    signal_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceSignalRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_governance_signal(
        organization_id=organization.id,
        signal_id=signal_id,
    )
    priority_map = service._priority_payload_map_for_signal_rows(organization_id=organization.id, rows=[row])
    return _governance_signal_read(
        service.governance_signal_payload(
            row=row,
            priority_payload=priority_map.get(row.id),
        )
    )


@router.get("/signals/{signal_id}/priority-explanation", response_model=GovernanceSignalPriorityExplanation)
def get_governance_signal_priority_explanation(
    signal_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceSignalPriorityExplanation:
    payload = AISystemRiskAssessmentService(db).governance_signal_priority_explanation(
        organization_id=organization.id,
        signal_id=signal_id,
    )
    return GovernanceSignalPriorityExplanation(**payload)


@router.post("/signals/{signal_id}/resolve", response_model=GovernanceSignalRead)
def resolve_governance_signal(
    signal_id: uuid.UUID,
    payload: GovernanceSignalActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceSignalRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_governance_signal(organization_id=organization.id, signal_id=signal_id)
    row = service.resolve_governance_signal(row=row, reason=payload.reason, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="governance_signal.resolved",
        entity_type="governance_signal",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    priority_map = service._priority_payload_map_for_signal_rows(organization_id=organization.id, rows=[row])
    return _governance_signal_read(
        service.governance_signal_payload(
            row=row,
            priority_payload=priority_map.get(row.id),
        )
    )


@router.get("/ai-systems/{ai_system_id}/attention", response_model=GovernanceSignalAttentionRead)
def get_ai_system_attention_view(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceSignalAttentionRead:
    payload = AISystemRiskAssessmentService(db).ai_system_attention_view(
        organization_id=organization.id,
        ai_system_id=ai_system_id,
    )
    return GovernanceSignalAttentionRead(
        ai_system_id=payload["ai_system_id"],
        open_signal_count=int(payload["open_signal_count"]),
        highest_priority_score=float(payload["highest_priority_score"]),
        highest_priority_band=payload["highest_priority_band"],
        top_signals=[_governance_signal_prioritized_read(item) for item in payload["top_signals"]],
        latest_risk_assessment_id=payload.get("latest_risk_assessment_id"),
        latest_manual_risk_level=payload.get("latest_manual_risk_level"),
        latest_calculated_residual_risk_level=payload.get("latest_calculated_residual_risk_level"),
        attention_summary=payload["attention_summary"],
        caveat=payload.get("caveat", AI_RISK_GOVERNANCE_SIGNAL_PRIORITY_CAVEAT),
    )


@router.get("/ai-systems/{ai_system_id}/candidate-actions", response_model=GovernanceAISystemCandidateActionsRead)
def get_ai_system_candidate_actions(
    ai_system_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceAISystemCandidateActionsRead:
    payload = AISystemRiskAssessmentService(db).ai_system_candidate_actions(
        organization_id=organization.id,
        ai_system_id=ai_system_id,
    )
    return GovernanceAISystemCandidateActionsRead(
        ai_system_id=payload["ai_system_id"],
        candidate_action_count=int(payload["candidate_action_count"]),
        highest_priority_band=payload["highest_priority_band"],
        actions=[_governance_candidate_action_read(item) for item in payload["actions"]],
        caveat=payload.get("caveat", AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT),
    )


@router.post("/signals/{signal_id}/dismiss", response_model=GovernanceSignalRead)
def dismiss_governance_signal(
    signal_id: uuid.UUID,
    payload: GovernanceSignalActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> GovernanceSignalRead:
    service = AISystemRiskAssessmentService(db)
    row = service.require_governance_signal(organization_id=organization.id, signal_id=signal_id)
    row = service.dismiss_governance_signal(row=row, reason=payload.reason, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="governance_signal.dismissed",
        entity_type="governance_signal",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"status": row.status, "dismissed_at": row.dismissed_at.isoformat() if row.dismissed_at else None},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    priority_map = service._priority_payload_map_for_signal_rows(organization_id=organization.id, rows=[row])
    return _governance_signal_read(
        service.governance_signal_payload(
            row=row,
            priority_payload=priority_map.get(row.id),
        )
    )


@router.get(
    "/ai-risk/assessments/{assessment_id}/candidate-actions",
    response_model=GovernanceRiskAssessmentCandidateActionsRead,
)
def get_risk_assessment_candidate_actions(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> GovernanceRiskAssessmentCandidateActionsRead:
    payload = AISystemRiskAssessmentService(db).risk_assessment_candidate_actions(
        organization_id=organization.id,
        assessment_id=assessment_id,
    )
    return GovernanceRiskAssessmentCandidateActionsRead(
        assessment_id=payload["assessment_id"],
        candidate_action_count=int(payload["candidate_action_count"]),
        highest_priority_band=payload["highest_priority_band"],
        actions=[_governance_candidate_action_read(item) for item in payload["actions"]],
        caveat=payload.get("caveat", AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT),
    )


@router.post(
    "/ai-risk/assessments/{assessment_id}/refresh-classification-signals",
    response_model=AISystemRiskRefreshClassificationSignalsResponse,
)
def refresh_assessment_classification_signals(
    assessment_id: uuid.UUID,
    payload: AISystemRiskRefreshClassificationSignalsRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemRiskRefreshClassificationSignalsResponse:
    if payload.persist_signals and not RBACService.user_has_permission(db, current_user.id, organization.id, "ai_systems:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing required permission: ai_systems:write")

    service = AISystemRiskAssessmentService(db)
    assessment = service.require_assessment(organization_id=organization.id, assessment_id=assessment_id)
    result = service.refresh_assessment_classification_signals(
        assessment=assessment,
        persist_signals=payload.persist_signals,
    )
    if payload.persist_signals:
        AuditService(db).write_audit_log(
            action="governance_signal.refresh_persisted",
            entity_type="ai_system_risk_assessment",
            entity_id=assessment.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "candidate_count": result["candidate_count"],
                "created_count": result["created_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemRiskRefreshClassificationSignalsResponse(**result)


@router.post(
    "/review-recurrence-templates",
    response_model=AISystemGovernanceReviewRecurrenceTemplateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_recurrence_template(
    payload: AISystemGovernanceReviewRecurrenceTemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewRecurrenceTemplateRead:
    service = AISystemGovernanceRecurrenceService(db)
    row = service.create_template(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        review_type=payload.review_type,
        cadence_type=payload.cadence_type,
        interval_value=payload.interval_value,
        default_reminder_policy_id=payload.default_reminder_policy_id,
        default_assigned_to_user_id=payload.default_assigned_to_user_id,
        default_checklist_json=payload.default_checklist_json,
        default_description=payload.default_description,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_recurrence_template.created",
        entity_type="ai_system_governance_review_recurrence_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "review_type": row.review_type,
            "cadence_type": row.cadence_type,
            "interval_value": row.interval_value,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _recurrence_template_read(row)


@router.get("/review-recurrence-templates", response_model=list[AISystemGovernanceReviewRecurrenceTemplateRead])
def list_recurrence_templates(
    status_filter: str | None = Query(default=None, alias="status"),
    review_type: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceReviewRecurrenceTemplateRead]:
    rows = AISystemGovernanceRecurrenceService(db).list_templates(
        organization_id=organization.id,
        status_filter=status_filter,
        review_type=review_type,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_recurrence_template_read(row) for row in rows]


@router.patch(
    "/review-recurrence-templates/{template_id}",
    response_model=AISystemGovernanceReviewRecurrenceTemplateRead,
)
def update_recurrence_template(
    template_id: uuid.UUID,
    payload: AISystemGovernanceReviewRecurrenceTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewRecurrenceTemplateRead:
    service = AISystemGovernanceRecurrenceService(db)
    row = service.require_template(organization_id=organization.id, template_id=template_id)
    before = {
        "name": row.name,
        "status": row.status,
        "review_type": row.review_type,
        "cadence_type": row.cadence_type,
        "interval_value": row.interval_value,
    }
    row = service.update_template(
        row=row,
        name=payload.name,
        description=payload.description,
        review_type=payload.review_type,
        cadence_type=payload.cadence_type,
        interval_value=payload.interval_value,
        default_reminder_policy_id=payload.default_reminder_policy_id,
        default_assigned_to_user_id=payload.default_assigned_to_user_id,
        default_checklist_json=payload.default_checklist_json,
        default_description=payload.default_description,
        status_value=payload.status,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_recurrence_template.updated",
        entity_type="ai_system_governance_review_recurrence_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "status": row.status,
            "review_type": row.review_type,
            "cadence_type": row.cadence_type,
            "interval_value": row.interval_value,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _recurrence_template_read(row)


@router.post(
    "/review-recurrence-templates/{template_id}/archive",
    response_model=AISystemGovernanceReviewRecurrenceTemplateRead,
)
def archive_recurrence_template(
    template_id: uuid.UUID,
    payload: AISystemGovernanceReviewRecurrenceTemplateArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> AISystemGovernanceReviewRecurrenceTemplateRead:
    _require_ai_systems_write_or_admin(db, user_id=current_user.id, organization_id=organization.id)
    service = AISystemGovernanceRecurrenceService(db)
    row = service.require_template(organization_id=organization.id, template_id=template_id)
    before = {
        "status": row.status,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
    }
    row = service.archive_template(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_recurrence_template.archived",
        entity_type="ai_system_governance_review_recurrence_template",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "status": row.status,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _recurrence_template_read(row)


@router.post(
    "/review-plan-constraints",
    response_model=AISystemGovernanceReviewPlanConstraintRead,
    status_code=status.HTTP_201_CREATED,
)
def create_review_plan_constraint(
    payload: AISystemGovernanceReviewPlanConstraintCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewPlanConstraintRead:
    service = AISystemGovernanceRecurrenceService(db)
    row = service.create_constraint(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        target_review_type=payload.target_review_type,
        prerequisite_review_type=payload.prerequisite_review_type,
        constraint_type=payload.constraint_type,
        enforcement_mode=payload.enforcement_mode,
        min_gap_days=payload.min_gap_days,
        max_gap_days=payload.max_gap_days,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_review_plan_constraint.created",
        entity_type="ai_system_governance_review_plan_constraint",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "target_review_type": row.target_review_type,
            "prerequisite_review_type": row.prerequisite_review_type,
            "constraint_type": row.constraint_type,
            "enforcement_mode": row.enforcement_mode,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _constraint_read(row)


@router.get("/review-plan-constraints", response_model=list[AISystemGovernanceReviewPlanConstraintRead])
def list_review_plan_constraints(
    status_filter: str | None = Query(default=None, alias="status"),
    target_review_type: str | None = Query(default=None),
    prerequisite_review_type: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceReviewPlanConstraintRead]:
    rows = AISystemGovernanceRecurrenceService(db).list_constraints(
        organization_id=organization.id,
        status_filter=status_filter,
        target_review_type=target_review_type,
        prerequisite_review_type=prerequisite_review_type,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_constraint_read(row) for row in rows]


@router.get("/review-plan-constraints/summary", response_model=AISystemGovernanceReviewPlanConstraintSummary)
def review_plan_constraint_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceReviewPlanConstraintSummary:
    summary = AISystemGovernanceRecurrenceService(db).constraint_summary(organization_id=organization.id)
    return AISystemGovernanceReviewPlanConstraintSummary(**summary)


@router.patch("/review-plan-constraints/{constraint_id}", response_model=AISystemGovernanceReviewPlanConstraintRead)
def update_review_plan_constraint(
    constraint_id: uuid.UUID,
    payload: AISystemGovernanceReviewPlanConstraintUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewPlanConstraintRead:
    service = AISystemGovernanceRecurrenceService(db)
    row = service.require_constraint(organization_id=organization.id, constraint_id=constraint_id)
    before = {
        "name": row.name,
        "status": row.status,
        "target_review_type": row.target_review_type,
        "prerequisite_review_type": row.prerequisite_review_type,
        "constraint_type": row.constraint_type,
        "enforcement_mode": row.enforcement_mode,
        "min_gap_days": row.min_gap_days,
        "max_gap_days": row.max_gap_days,
    }
    row = service.update_constraint(
        row=row,
        name=payload.name,
        description=payload.description,
        target_review_type=payload.target_review_type,
        prerequisite_review_type=payload.prerequisite_review_type,
        constraint_type=payload.constraint_type,
        enforcement_mode=payload.enforcement_mode,
        min_gap_days=payload.min_gap_days,
        max_gap_days=payload.max_gap_days,
        status_value=payload.status,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_review_plan_constraint.updated",
        entity_type="ai_system_governance_review_plan_constraint",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "status": row.status,
            "target_review_type": row.target_review_type,
            "prerequisite_review_type": row.prerequisite_review_type,
            "constraint_type": row.constraint_type,
            "enforcement_mode": row.enforcement_mode,
            "min_gap_days": row.min_gap_days,
            "max_gap_days": row.max_gap_days,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _constraint_read(row)


@router.post("/review-plan-constraints/{constraint_id}/archive", response_model=AISystemGovernanceReviewPlanConstraintRead)
def archive_review_plan_constraint(
    constraint_id: uuid.UUID,
    payload: AISystemGovernanceReviewPlanConstraintArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewPlanConstraintRead:
    service = AISystemGovernanceRecurrenceService(db)
    row = service.require_constraint(organization_id=organization.id, constraint_id=constraint_id)
    before = {
        "status": row.status,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
    }
    row = service.archive_constraint(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_review_plan_constraint.archived",
        entity_type="ai_system_governance_review_plan_constraint",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "status": row.status,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _constraint_read(row)


@router.post(
    "/review-recurrence-templates/{template_id}/generate-plan",
    response_model=AISystemGovernanceReviewPlanGenerateResponse,
)
def generate_recurrence_plan(
    template_id: uuid.UUID,
    payload: AISystemGovernanceReviewPlanGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewPlanGenerateResponse:
    service = AISystemGovernanceRecurrenceService(db)
    template = service.require_template(organization_id=organization.id, template_id=template_id)
    result = service.generate_plan(
        organization_id=organization.id,
        template=template,
        dry_run=payload.dry_run,
        horizon_days=payload.horizon_days,
        ai_system_ids=payload.ai_system_ids,
        start_from=payload.start_from,
        actor_user_id=current_user.id,
        apply_constraints=payload.apply_constraints,
        constraint_ids=payload.constraint_ids,
    )

    AuditService(db).write_audit_log(
        action=(
            "ai_system_governance_review_plan.previewed"
            if payload.dry_run
            else "ai_system_governance_review_plan.applied"
        ),
        entity_type="ai_system_governance_review_plan_run",
        entity_id=result["run_id"],
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "template_id": str(template.id),
            "dry_run": result["dry_run"],
            "horizon_days": result["horizon_days"],
            "planned_count": result["planned_count"],
            "created_count": result["created_count"],
            "skipped_count": result["skipped_count"],
            "apply_constraints": payload.apply_constraints,
            "constraint_ids": [str(item) for item in payload.constraint_ids] if payload.constraint_ids else None,
            "run_id": str(result["run_id"]) if result["run_id"] else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()

    return AISystemGovernanceReviewPlanGenerateResponse(
        dry_run=result["dry_run"],
        template_id=result["template_id"],
        horizon_days=result["horizon_days"],
        planned_count=result["planned_count"],
        created_count=result["created_count"],
        skipped_count=result["skipped_count"],
        planned_reviews=[AISystemGovernanceReviewPlanItem(**row) for row in result["planned_reviews"]],
        skipped_reviews=[AISystemGovernanceReviewPlanSkippedItem(**row) for row in result["skipped_reviews"]],
        run_id=result["run_id"],
        caveat=result["caveat"],
    )


@router.get("/review-plan-runs", response_model=list[AISystemGovernanceReviewPlanRunRead])
def list_recurrence_plan_runs(
    template_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    dry_run: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceReviewPlanRunRead]:
    rows = AISystemGovernanceRecurrenceService(db).list_plan_runs(
        organization_id=organization.id,
        template_id=template_id,
        status_filter=status_filter,
        dry_run=dry_run,
        limit=limit,
        offset=offset,
    )
    return [_plan_run_read(row) for row in rows]


@router.get("/review-plan-runs/{run_id}", response_model=AISystemGovernanceReviewPlanRunRead)
def get_recurrence_plan_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceReviewPlanRunRead:
    row = AISystemGovernanceRecurrenceService(db).require_plan_run(
        organization_id=organization.id,
        run_id=run_id,
    )
    return _plan_run_read(row)


@router.get("/review-recurrence-summary", response_model=AISystemGovernanceReviewRecurrenceSummary)
def recurrence_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceReviewRecurrenceSummary:
    summary = AISystemGovernanceRecurrenceService(db).recurrence_summary(organization_id=organization.id)
    return AISystemGovernanceReviewRecurrenceSummary(**summary)


@router.post(
    "/guardrails/policy-sets",
    response_model=AISystemGovernanceGuardrailPolicySetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_guardrail_policy_set(
    payload: AISystemGovernanceGuardrailPolicySetCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceGuardrailPolicySetRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.create_policy_set(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_guardrail_policy_set.created",
        entity_type="ai_system_governance_guardrail_policy_set",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"name": row.name, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_set_read(row)


@router.get("/guardrails/policy-sets", response_model=list[AISystemGovernanceGuardrailPolicySetRead])
def list_guardrail_policy_sets(
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceGuardrailPolicySetRead]:
    rows = AISystemGovernanceSequenceService(db).list_policy_sets(
        organization_id=organization.id,
        status_filter=status_filter,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_policy_set_read(row) for row in rows]


@router.patch("/guardrails/policy-sets/{policy_set_id}", response_model=AISystemGovernanceGuardrailPolicySetRead)
def update_guardrail_policy_set(
    policy_set_id: uuid.UUID,
    payload: AISystemGovernanceGuardrailPolicySetUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceGuardrailPolicySetRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_set(organization_id=organization.id, policy_set_id=policy_set_id)
    before = {"name": row.name, "status": row.status}
    row = service.update_policy_set(
        row=row,
        name=payload.name,
        description=payload.description,
        status_value=payload.status,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_guardrail_policy_set.updated",
        entity_type="ai_system_governance_guardrail_policy_set",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"name": row.name, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_set_read(row)


@router.post("/guardrails/policy-sets/{policy_set_id}/archive", response_model=AISystemGovernanceGuardrailPolicySetRead)
def archive_guardrail_policy_set(
    policy_set_id: uuid.UUID,
    payload: AISystemGovernanceGuardrailPolicySetArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceGuardrailPolicySetRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_set(organization_id=organization.id, policy_set_id=policy_set_id)
    before = {"status": row.status}
    row = service.archive_policy_set(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_guardrail_policy_set.archived",
        entity_type="ai_system_governance_guardrail_policy_set",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_set_read(row)


@router.post(
    "/guardrails/policy-sets/{policy_set_id}/versions",
    response_model=AISystemGovernanceGuardrailPolicySetVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_guardrail_policy_set_version(
    policy_set_id: uuid.UUID,
    payload: AISystemGovernanceGuardrailPolicySetVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceGuardrailPolicySetVersionRead:
    service = AISystemGovernanceSequenceService(db)
    policy_set = service.require_policy_set(organization_id=organization.id, policy_set_id=policy_set_id)
    row = service.create_policy_set_version(
        organization_id=organization.id,
        policy_set=policy_set,
        profile_json=payload.profile_json,
        change_reason=payload.change_reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_guardrail_policy_set_version.created",
        entity_type="ai_system_governance_guardrail_policy_set_version",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "policy_set_id": str(policy_set.id),
            "version_number": row.version_number,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_set_version_read(row)


@router.get(
    "/guardrails/policy-sets/{policy_set_id}/versions",
    response_model=list[AISystemGovernanceGuardrailPolicySetVersionRead],
)
def list_guardrail_policy_set_versions(
    policy_set_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceGuardrailPolicySetVersionRead]:
    service = AISystemGovernanceSequenceService(db)
    service.require_policy_set(organization_id=organization.id, policy_set_id=policy_set_id)
    rows = service.list_policy_set_versions(organization_id=organization.id, policy_set_id=policy_set_id)
    return [_policy_set_version_read(row) for row in rows]


@router.post(
    "/guardrails/policy-sets/{policy_set_id}/versions/{version_id}/activate",
    response_model=AISystemGovernanceGuardrailPolicySetVersionRead,
)
def activate_guardrail_policy_set_version(
    policy_set_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: AISystemGovernanceGuardrailPolicySetVersionActivateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceGuardrailPolicySetVersionRead:
    service = AISystemGovernanceSequenceService(db)
    policy_set = service.require_policy_set(organization_id=organization.id, policy_set_id=policy_set_id)
    version = service.require_policy_version(
        organization_id=organization.id,
        policy_set_id=policy_set_id,
        version_id=version_id,
    )
    version = service.activate_policy_set_version(
        organization_id=organization.id,
        policy_set=policy_set,
        version=version,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_guardrail_policy_set_version.activated",
        entity_type="ai_system_governance_guardrail_policy_set_version",
        entity_id=version.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"policy_set_id": str(policy_set.id), "version_number": version.version_number},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(version)
    return _policy_set_version_read(version)


@router.get(
    "/guardrails/policy-sets/{policy_set_id}/active-profile",
    response_model=AISystemGovernanceGuardrailPolicySetActiveProfileResponse,
)
def get_guardrail_policy_set_active_profile(
    policy_set_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceGuardrailPolicySetActiveProfileResponse:
    policy_set, version = AISystemGovernanceSequenceService(db).get_active_policy_profile(
        organization_id=organization.id,
        policy_set_id=policy_set_id,
    )
    return AISystemGovernanceGuardrailPolicySetActiveProfileResponse(
        policy_set_id=policy_set.id,
        policy_set_name=policy_set.name,
        version_id=version.id,
        version_number=version.version_number,
        profile_json=version.profile_json,
        caveat=(
            "Guardrail policy profiles are deterministic configuration records. "
            "They do not autonomously execute, approve, or complete AI governance work."
        ),
    )


@router.post(
    "/guardrails/freeze-windows",
    response_model=AISystemGovernanceFreezeWindowRead,
    status_code=status.HTTP_201_CREATED,
)
def create_freeze_window(
    payload: AISystemGovernanceFreezeWindowCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> AISystemGovernanceFreezeWindowRead:
    _require_ai_systems_write_or_admin(db, user_id=current_user.id, organization_id=organization.id)
    service = AISystemGovernanceSequenceService(db)
    row = service.create_freeze_window(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        scope_type=payload.scope_type,
        scope_json=payload.scope_json,
        priority=payload.priority,
        enforcement_level=payload.enforcement_level,
        override_allowed=payload.override_allowed,
        precedence_notes=payload.precedence_notes,
        reason=payload.reason,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_freeze_window.created",
        entity_type="ai_system_governance_freeze_window",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "status": row.status,
            "scope_type": row.scope_type,
            "priority": row.priority,
            "enforcement_level": row.enforcement_level,
            "override_allowed": row.override_allowed,
            "starts_at": row.starts_at.isoformat(),
            "ends_at": row.ends_at.isoformat(),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _freeze_window_read(row)


@router.get("/guardrails/freeze-windows", response_model=list[AISystemGovernanceFreezeWindowRead])
def list_freeze_windows(
    status_filter: str | None = Query(default=None, alias="status"),
    active_at: datetime | None = Query(default=None),
    scope_type: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceFreezeWindowRead]:
    rows = AISystemGovernanceSequenceService(db).list_freeze_windows(
        organization_id=organization.id,
        status_filter=status_filter,
        active_at=active_at,
        scope_type=scope_type,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_freeze_window_read(row) for row in rows]


@router.patch("/guardrails/freeze-windows/{freeze_window_id}", response_model=AISystemGovernanceFreezeWindowRead)
def update_freeze_window(
    freeze_window_id: uuid.UUID,
    payload: AISystemGovernanceFreezeWindowUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> AISystemGovernanceFreezeWindowRead:
    _require_ai_systems_write_or_admin(db, user_id=current_user.id, organization_id=organization.id)
    service = AISystemGovernanceSequenceService(db)
    row = service.require_freeze_window(organization_id=organization.id, freeze_window_id=freeze_window_id)
    before = {
        "status": row.status,
        "scope_type": row.scope_type,
        "priority": row.priority,
        "enforcement_level": row.enforcement_level,
        "override_allowed": row.override_allowed,
        "starts_at": row.starts_at.isoformat(),
        "ends_at": row.ends_at.isoformat(),
    }
    row = service.update_freeze_window(
        row=row,
        name=payload.name,
        description=payload.description,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        scope_type=payload.scope_type,
        scope_json=payload.scope_json,
        priority=payload.priority,
        enforcement_level=payload.enforcement_level,
        override_allowed=payload.override_allowed,
        precedence_notes=payload.precedence_notes,
        reason=payload.reason,
        status_value=payload.status,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_freeze_window.updated",
        entity_type="ai_system_governance_freeze_window",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "status": row.status,
            "scope_type": row.scope_type,
            "priority": row.priority,
            "enforcement_level": row.enforcement_level,
            "override_allowed": row.override_allowed,
            "starts_at": row.starts_at.isoformat(),
            "ends_at": row.ends_at.isoformat(),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _freeze_window_read(row)


@router.post(
    "/guardrails/freeze-windows/{freeze_window_id}/archive",
    response_model=AISystemGovernanceFreezeWindowRead,
)
def archive_freeze_window(
    freeze_window_id: uuid.UUID,
    payload: AISystemGovernanceFreezeWindowArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> AISystemGovernanceFreezeWindowRead:
    _require_ai_systems_write_or_admin(db, user_id=current_user.id, organization_id=organization.id)
    service = AISystemGovernanceSequenceService(db)
    row = service.require_freeze_window(organization_id=organization.id, freeze_window_id=freeze_window_id)
    before = {"status": row.status}
    row = service.archive_freeze_window(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_freeze_window.archived",
        entity_type="ai_system_governance_freeze_window",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _freeze_window_read(row)


@router.post("/guardrails/check", response_model=AISystemGovernanceGuardrailCheckResponse)
def guardrail_check(
    payload: AISystemGovernanceGuardrailCheckRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceGuardrailCheckResponse:
    result = AISystemGovernanceSequenceService(db).evaluate_guardrails(
        organization_id=organization.id,
        action_type=payload.action_type,
        sequence_pack_id=payload.sequence_pack_id,
        recurrence_template_id=payload.recurrence_template_id,
        ai_system_ids=payload.ai_system_ids,
        review_types=payload.review_types,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        rollout_class=payload.rollout_class,
        policy_set_id=payload.policy_set_id,
    )
    return AISystemGovernanceGuardrailCheckResponse(
        blocked=result["blocked"],
        matching_freeze_windows=[AISystemGovernanceGuardrailFreezeMatch(**item) for item in result["matching_freeze_windows"]],
        resolution=result["resolution"],
        warnings=result["warnings"],
        required_acknowledgement_text=result["required_acknowledgement_text"],
        policy_set_id=result["policy_set_id"],
        policy_version_id=result["policy_version_id"],
        policy_resolution=result["policy_resolution"],
        caveat=result["caveat"],
    )


@router.post("/guardrails/resolve-conflicts", response_model=AISystemGovernanceGuardrailConflictPreviewResponse)
def guardrail_resolve_conflicts(
    payload: AISystemGovernanceGuardrailCheckRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceGuardrailConflictPreviewResponse:
    preview = AISystemGovernanceSequenceService(db).preview_guardrail_conflicts(
        organization_id=organization.id,
        action_type=payload.action_type,
        sequence_pack_id=payload.sequence_pack_id,
        recurrence_template_id=payload.recurrence_template_id,
        ai_system_ids=payload.ai_system_ids,
        review_types=payload.review_types,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        rollout_class=payload.rollout_class,
        policy_set_id=payload.policy_set_id,
    )
    return AISystemGovernanceGuardrailConflictPreviewResponse(
        all_matching_freeze_windows=[
            AISystemGovernanceGuardrailFreezeMatch(**item) for item in preview["all_matching_freeze_windows"]
        ],
        sorted_precedence_order=preview["sorted_precedence_order"],
        primary_blocking_window=(
            AISystemGovernanceGuardrailFreezeMatch(**preview["primary_blocking_window"])
            if preview["primary_blocking_window"] is not None
            else None
        ),
        final_decision=preview["final_decision"],
        policy_set_id=preview["policy_set_id"],
        policy_version_id=preview["policy_version_id"],
        policy_resolution=preview["policy_resolution"],
        explanation=preview["explanation"],
        caveat=preview["caveat"],
    )


@router.post(
    "/review-sequence-packs",
    response_model=AISystemGovernanceReviewSequencePackRead,
    status_code=status.HTTP_201_CREATED,
)
def create_sequence_pack(
    payload: AISystemGovernanceReviewSequencePackCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewSequencePackRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.create_pack(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_review_sequence_pack.created",
        entity_type="ai_system_governance_review_sequence_pack",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={"name": row.name, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _sequence_pack_read(row)


@router.get("/review-sequence-packs", response_model=list[AISystemGovernanceReviewSequencePackRead])
def list_sequence_packs(
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceReviewSequencePackRead]:
    rows = AISystemGovernanceSequenceService(db).list_packs(
        organization_id=organization.id,
        status_filter=status_filter,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_sequence_pack_read(row) for row in rows]


@router.patch("/review-sequence-packs/{pack_id}", response_model=AISystemGovernanceReviewSequencePackRead)
def update_sequence_pack(
    pack_id: uuid.UUID,
    payload: AISystemGovernanceReviewSequencePackUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewSequencePackRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_pack(organization_id=organization.id, pack_id=pack_id)
    before = {"name": row.name, "status": row.status}
    row = service.update_pack(
        row=row,
        name=payload.name,
        description=payload.description,
        status_value=payload.status,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_review_sequence_pack.updated",
        entity_type="ai_system_governance_review_sequence_pack",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"name": row.name, "status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _sequence_pack_read(row)


@router.post("/review-sequence-packs/{pack_id}/archive", response_model=AISystemGovernanceReviewSequencePackRead)
def archive_sequence_pack(
    pack_id: uuid.UUID,
    payload: AISystemGovernanceReviewSequencePackArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewSequencePackRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_pack(organization_id=organization.id, pack_id=pack_id)
    before = {"status": row.status}
    row = service.archive_pack(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_review_sequence_pack.archived",
        entity_type="ai_system_governance_review_sequence_pack",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _sequence_pack_read(row)


@router.post(
    "/review-sequence-packs/{pack_id}/steps",
    response_model=AISystemGovernanceReviewSequenceStepRead,
    status_code=status.HTTP_201_CREATED,
)
def create_sequence_step(
    pack_id: uuid.UUID,
    payload: AISystemGovernanceReviewSequenceStepCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewSequenceStepRead:
    service = AISystemGovernanceSequenceService(db)
    pack = service.require_pack(organization_id=organization.id, pack_id=pack_id)
    row = service.create_step(
        organization_id=organization.id,
        pack=pack,
        step_order=payload.step_order,
        review_type=payload.review_type,
        title_template=payload.title_template,
        description_template=payload.description_template,
        offset_days_from_start=payload.offset_days_from_start,
        default_reminder_policy_id=payload.default_reminder_policy_id,
        default_assigned_to_user_id=payload.default_assigned_to_user_id,
        default_checklist_json=payload.default_checklist_json,
        require_previous_step_planned=payload.require_previous_step_planned,
        status_value=payload.status,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_review_sequence_step.created",
        entity_type="ai_system_governance_review_sequence_step",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "sequence_pack_id": str(pack.id),
            "step_order": row.step_order,
            "review_type": row.review_type,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _sequence_step_read(row)


@router.get("/review-sequence-packs/{pack_id}/steps", response_model=list[AISystemGovernanceReviewSequenceStepRead])
def list_sequence_steps(
    pack_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceReviewSequenceStepRead]:
    service = AISystemGovernanceSequenceService(db)
    service.require_pack(organization_id=organization.id, pack_id=pack_id)
    rows = service.list_steps(organization_id=organization.id, pack_id=pack_id)
    return [_sequence_step_read(row) for row in rows]


@router.patch(
    "/review-sequence-packs/{pack_id}/steps/{step_id}",
    response_model=AISystemGovernanceReviewSequenceStepRead,
)
def update_sequence_step(
    pack_id: uuid.UUID,
    step_id: uuid.UUID,
    payload: AISystemGovernanceReviewSequenceStepUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewSequenceStepRead:
    service = AISystemGovernanceSequenceService(db)
    service.require_pack(organization_id=organization.id, pack_id=pack_id)
    row = service.require_step(organization_id=organization.id, pack_id=pack_id, step_id=step_id)
    before = {
        "step_order": row.step_order,
        "review_type": row.review_type,
        "status": row.status,
        "offset_days_from_start": row.offset_days_from_start,
    }
    row = service.update_step(
        organization_id=organization.id,
        row=row,
        step_order=payload.step_order,
        review_type=payload.review_type,
        title_template=payload.title_template,
        description_template=payload.description_template,
        offset_days_from_start=payload.offset_days_from_start,
        default_reminder_policy_id=payload.default_reminder_policy_id,
        default_assigned_to_user_id=payload.default_assigned_to_user_id,
        default_checklist_json=payload.default_checklist_json,
        require_previous_step_planned=payload.require_previous_step_planned,
        status_value=payload.status,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_review_sequence_step.updated",
        entity_type="ai_system_governance_review_sequence_step",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "step_order": row.step_order,
            "review_type": row.review_type,
            "status": row.status,
            "offset_days_from_start": row.offset_days_from_start,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _sequence_step_read(row)


@router.post(
    "/review-sequence-packs/{pack_id}/steps/{step_id}/archive",
    response_model=AISystemGovernanceReviewSequenceStepRead,
)
def archive_sequence_step(
    pack_id: uuid.UUID,
    step_id: uuid.UUID,
    payload: AISystemGovernanceReviewSequenceStepArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewSequenceStepRead:
    service = AISystemGovernanceSequenceService(db)
    service.require_pack(organization_id=organization.id, pack_id=pack_id)
    row = service.require_step(organization_id=organization.id, pack_id=pack_id, step_id=step_id)
    before = {"status": row.status}
    row = service.archive_step(row=row)
    AuditService(db).write_audit_log(
        action="ai_system_governance_review_sequence_step.archived",
        entity_type="ai_system_governance_review_sequence_step",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _sequence_step_read(row)


@router.post(
    "/review-sequence-packs/{pack_id}/generate-sequence",
    response_model=AISystemGovernanceReviewSequenceGenerateResponse,
)
def generate_sequence(
    pack_id: uuid.UUID,
    payload: AISystemGovernanceReviewSequenceGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewSequenceGenerateResponse:
    service = AISystemGovernanceSequenceService(db)
    pack = service.require_pack(organization_id=organization.id, pack_id=pack_id)
    result = service.generate_sequence(
        organization_id=organization.id,
        pack=pack,
        dry_run=payload.dry_run,
        ai_system_ids=payload.ai_system_ids,
        start_from=payload.start_from,
        apply_constraints=payload.apply_constraints,
        acknowledgement_text=payload.acknowledgement_text,
        override_freeze=payload.override_freeze,
        override_reason=payload.override_reason,
        guardrail_policy_set_id=payload.guardrail_policy_set_id,
        rollout_class=payload.rollout_class,
        actor_user_id=current_user.id,
    )
    if result["operator_acknowledgement"] is not None:
        ack = result["operator_acknowledgement"]
        AuditService(db).write_audit_log(
            action="ai_system_governance_operator_acknowledgement.created",
            entity_type="ai_system_governance_operator_acknowledgement",
            entity_id=ack.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "action_type": ack.action_type,
                "target_type": ack.target_type,
                "target_id": str(ack.target_id) if ack.target_id else None,
                "override_freeze": ack.override_freeze,
                "freeze_window_ids_json": ack.freeze_window_ids_json,
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    AuditService(db).write_audit_log(
        action=(
            "ai_system_governance_review_sequence.previewed"
            if payload.dry_run
            else "ai_system_governance_review_sequence.applied"
        ),
        entity_type="ai_system_governance_review_sequence_run",
        entity_id=result["run_id"],
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "sequence_pack_id": str(pack.id),
            "dry_run": result["dry_run"],
            "planned_count": result["planned_count"],
            "created_count": result["created_count"],
            "skipped_count": result["skipped_count"],
            "run_id": str(result["run_id"]) if result["run_id"] else None,
            "apply_constraints": payload.apply_constraints,
            "guardrail_blocked": result["guardrail_results"]["blocked"],
            "guardrail_policy_set_id": (
                str(result["guardrail_results"]["policy_set_id"])
                if result["guardrail_results"]["policy_set_id"]
                else None
            ),
            "guardrail_policy_version_id": (
                str(result["guardrail_results"]["policy_version_id"])
                if result["guardrail_results"]["policy_version_id"]
                else None
            ),
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return AISystemGovernanceReviewSequenceGenerateResponse(
        dry_run=result["dry_run"],
        sequence_pack_id=result["sequence_pack_id"],
        planned_count=result["planned_count"],
        created_count=result["created_count"],
        skipped_count=result["skipped_count"],
        planned_reviews=[AISystemGovernanceReviewSequencePlanItem(**row) for row in result["planned_reviews"]],
        skipped_reviews=[AISystemGovernanceReviewSequenceSkippedItem(**row) for row in result["skipped_reviews"]],
        run_id=result["run_id"],
        guardrail_results=result["guardrail_results"],
        caveat=result["caveat"],
    )


@router.get("/review-sequence-runs", response_model=list[AISystemGovernanceReviewSequenceRunRead])
def list_sequence_runs(
    sequence_pack_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    dry_run: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceReviewSequenceRunRead]:
    rows = AISystemGovernanceSequenceService(db).list_runs(
        organization_id=organization.id,
        sequence_pack_id=sequence_pack_id,
        status_filter=status_filter,
        dry_run=dry_run,
        limit=limit,
        offset=offset,
    )
    return [_sequence_run_read(row) for row in rows]


@router.get("/review-sequence-runs/{run_id}", response_model=AISystemGovernanceReviewSequenceRunRead)
def get_sequence_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceReviewSequenceRunRead:
    row = AISystemGovernanceSequenceService(db).require_run(organization_id=organization.id, run_id=run_id)
    return _sequence_run_read(row)


@router.get("/review-sequence-summary", response_model=AISystemGovernanceReviewSequenceSummary)
def review_sequence_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceReviewSequenceSummary:
    summary = AISystemGovernanceSequenceService(db).summary(organization_id=organization.id)
    return AISystemGovernanceReviewSequenceSummary(**summary)


@router.get("/guardrails/operator-acknowledgements", response_model=list[AISystemGovernanceOperatorAcknowledgementRead])
def list_operator_acknowledgements(
    action_type: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    target_id: uuid.UUID | None = Query(default=None),
    override_freeze: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceOperatorAcknowledgementRead]:
    rows = AISystemGovernanceSequenceService(db).list_operator_acknowledgements(
        organization_id=organization.id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        override_freeze=override_freeze,
        limit=limit,
        offset=offset,
    )
    return [_operator_ack_read(row) for row in rows]


@router.get("/guardrails/summary", response_model=AISystemGovernanceGuardrailSummary)
def guardrail_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceGuardrailSummary:
    summary = AISystemGovernanceSequenceService(db).guardrail_summary(organization_id=organization.id)
    return AISystemGovernanceGuardrailSummary(**summary)


@router.get("/guardrails/policy-sets/summary", response_model=AISystemGovernanceGuardrailPolicySetSummary)
def guardrail_policy_set_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceGuardrailPolicySetSummary:
    summary = AISystemGovernanceSequenceService(db).policy_set_summary(organization_id=organization.id)
    return AISystemGovernanceGuardrailPolicySetSummary(**summary)


@router.post(
    "/guardrails/policy-assignments",
    response_model=AISystemGovernanceGuardrailPolicyAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_guardrail_policy_assignment(
    payload: AISystemGovernanceGuardrailPolicyAssignmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceGuardrailPolicyAssignmentRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.create_policy_assignment(
        organization_id=organization.id,
        policy_set_id=payload.policy_set_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        scope_json=payload.scope_json,
        priority=payload.priority,
        reason=payload.reason,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_guardrail_policy_assignment.created",
        entity_type="ai_system_governance_guardrail_policy_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "policy_set_id": str(row.policy_set_id),
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id else None,
            "priority": row.priority,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_assignment_read(row)


@router.get("/guardrails/policy-assignments", response_model=list[AISystemGovernanceGuardrailPolicyAssignmentRead])
def list_guardrail_policy_assignments(
    status_filter: str | None = Query(default=None, alias="status"),
    scope_type: str | None = Query(default=None),
    policy_set_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceGuardrailPolicyAssignmentRead]:
    rows = AISystemGovernanceSequenceService(db).list_policy_assignments(
        organization_id=organization.id,
        status_filter=status_filter,
        scope_type=scope_type,
        policy_set_id=policy_set_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_policy_assignment_read(row) for row in rows]


@router.post(
    "/guardrails/policy-assignments/resolve",
    response_model=AISystemGovernanceGuardrailPolicyAssignmentResolveResponse,
)
def resolve_guardrail_policy_assignment(
    payload: AISystemGovernanceGuardrailPolicyAssignmentResolveRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceGuardrailPolicyAssignmentResolveResponse:
    result = AISystemGovernanceSequenceService(db).resolve_policy_assignment(
        organization_id=organization.id,
        explicit_policy_set_id=payload.explicit_policy_set_id,
        sequence_pack_id=payload.sequence_pack_id,
        ai_system_ids=payload.ai_system_ids,
        review_types=payload.review_types,
        rollout_class=payload.rollout_class,
    )
    return AISystemGovernanceGuardrailPolicyAssignmentResolveResponse(
        resolved_policy_set_id=result["resolved_policy_set_id"],
        resolved_policy_version_id=result["resolved_policy_version_id"],
        resolution_source=result["resolution_source"],
        assignment_id=result["assignment_id"],
        precedence_trace=result["precedence_trace"],
        caveat=result["caveat"],
    )


@router.post(
    "/guardrails/policy-resolution/simulate",
    response_model=AISystemGovernancePolicyResolutionSimulationResponse,
)
def simulate_policy_resolution(
    payload: AISystemGovernancePolicyResolutionSimulationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyResolutionSimulationResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.run_policy_resolution_simulation(
        organization_id=organization.id,
        title=payload.title,
        description=payload.description,
        persist_report=payload.persist_report,
        contexts=[row.model_dump() for row in payload.contexts],
        actor_user_id=current_user.id,
    )
    if payload.persist_report:
        AuditService(db).write_audit_log(
            action="ai_system_governance_policy_resolution_simulation.generated",
            entity_type="ai_system_governance_policy_resolution_simulation_report",
            entity_id=result["report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "persisted": True,
                "context_count": result["context_count"],
                "blocked_contexts_count": result["blocked_contexts_count"],
                "warning_contexts_count": result["warning_contexts_count"],
                "no_policy_contexts_count": result["no_policy_contexts_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernancePolicyResolutionSimulationResponse(**result)


@router.get(
    "/guardrails/policy-resolution/simulation-reports",
    response_model=list[AISystemGovernancePolicyResolutionSimulationReportRead],
)
def list_policy_resolution_simulation_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePolicyResolutionSimulationReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_policy_resolution_simulation_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return [_policy_resolution_simulation_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/simulation-reports/{report_id}",
    response_model=AISystemGovernancePolicyResolutionSimulationReportRead,
)
def get_policy_resolution_simulation_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyResolutionSimulationReportRead:
    row = AISystemGovernanceSequenceService(db).require_simulation_report(
        organization_id=organization.id,
        report_id=report_id,
    )
    return _policy_resolution_simulation_report_read(row)


@router.post(
    "/guardrails/policy-resolution/simulation-reports/{report_id}/archive",
    response_model=AISystemGovernancePolicyResolutionSimulationReportRead,
)
def archive_policy_resolution_simulation_report(
    report_id: uuid.UUID,
    payload: AISystemGovernancePolicyResolutionSimulationReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyResolutionSimulationReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_simulation_report(organization_id=organization.id, report_id=report_id)
    before = {"status": row.status}
    row = service.archive_policy_resolution_simulation_report(row=row)
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_resolution_simulation.archived",
        entity_type="ai_system_governance_policy_resolution_simulation_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_resolution_simulation_report_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-reason-codes",
    response_model=AISystemGovernancePolicyResolutionDiffReasonCodeCatalogResponse,
)
def policy_resolution_diff_reason_code_catalog(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyResolutionDiffReasonCodeCatalogResponse:
    _ = organization
    _ = membership
    result = AISystemGovernanceSequenceService(db).diff_reason_code_catalog()
    return AISystemGovernancePolicyResolutionDiffReasonCodeCatalogResponse(**result)


@router.get(
    "/guardrails/policy-resolution/simulation-summary",
    response_model=AISystemGovernancePolicyResolutionSimulationSummary,
)
def policy_resolution_simulation_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyResolutionSimulationSummary:
    summary = AISystemGovernanceSequenceService(db).policy_resolution_simulation_summary(organization_id=organization.id)
    return AISystemGovernancePolicyResolutionSimulationSummary(**summary)


@router.post(
    "/guardrails/policy-resolution/simulation-reports/diff",
    response_model=AISystemGovernancePolicyResolutionSimulationDiffResponse,
)
def diff_policy_resolution_simulation_reports(
    payload: AISystemGovernancePolicyResolutionSimulationDiffRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyResolutionSimulationDiffResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.diff_simulation_reports(
        organization_id=organization.id,
        base_report_id=payload.base_report_id,
        compare_report_id=payload.compare_report_id,
        title=payload.title,
        persist_diff=payload.persist_diff,
        context_match_strategy=payload.context_match_strategy,
        actor_user_id=current_user.id,
    )
    if payload.persist_diff:
        AuditService(db).write_audit_log(
            action="ai_system_governance_policy_resolution_simulation_diff.generated",
            entity_type="ai_system_governance_policy_resolution_simulation_diff_report",
            entity_id=result["diff_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "base_report_id": str(result["base_report_id"]),
                "compare_report_id": str(result["compare_report_id"]),
                "added_contexts_count": result["added_contexts_count"],
                "removed_contexts_count": result["removed_contexts_count"],
                "changed_contexts_count": result["changed_contexts_count"],
                "unchanged_contexts_count": result["unchanged_contexts_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernancePolicyResolutionSimulationDiffResponse(**result)


@router.get(
    "/guardrails/policy-resolution/simulation-diff-reports",
    response_model=list[AISystemGovernancePolicyResolutionSimulationDiffReportRead],
)
def list_policy_resolution_simulation_diff_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    base_report_id: uuid.UUID | None = Query(default=None),
    compare_report_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePolicyResolutionSimulationDiffReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_simulation_diff_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        base_report_id=base_report_id,
        compare_report_id=compare_report_id,
        limit=limit,
        offset=offset,
    )
    return [_policy_resolution_simulation_diff_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}",
    response_model=AISystemGovernancePolicyResolutionSimulationDiffReportRead,
)
def get_policy_resolution_simulation_diff_report(
    diff_report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyResolutionSimulationDiffReportRead:
    row = AISystemGovernanceSequenceService(db).require_simulation_diff_report(
        organization_id=organization.id,
        diff_report_id=diff_report_id,
    )
    return _policy_resolution_simulation_diff_report_read(row)


@router.post(
    "/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}/archive",
    response_model=AISystemGovernancePolicyResolutionSimulationDiffReportRead,
)
def archive_policy_resolution_simulation_diff_report(
    diff_report_id: uuid.UUID,
    payload: AISystemGovernancePolicyResolutionSimulationDiffReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyResolutionSimulationDiffReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_simulation_diff_report(organization_id=organization.id, diff_report_id=diff_report_id)
    before = {"status": row.status}
    row = service.archive_simulation_diff_report(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_resolution_simulation_diff.archived",
        entity_type="ai_system_governance_policy_resolution_simulation_diff_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_resolution_simulation_diff_report_read(row)


@router.get(
    "/guardrails/policy-resolution/simulation-diff-summary",
    response_model=AISystemGovernancePolicyResolutionSimulationDiffSummary,
)
def policy_resolution_simulation_diff_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyResolutionSimulationDiffSummary:
    summary = AISystemGovernanceSequenceService(db).simulation_diff_summary(organization_id=organization.id)
    return AISystemGovernancePolicyResolutionSimulationDiffSummary(**summary)


@router.post(
    "/guardrails/policy-resolution/diff-gating-profiles",
    response_model=AISystemGovernancePolicyDiffGatingProfileRead,
    status_code=status.HTTP_201_CREATED,
)
def create_policy_diff_gating_profile(
    payload: AISystemGovernancePolicyDiffGatingProfileCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingProfileRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.create_policy_diff_gating_profile(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        status_value=payload.status,
        default_severity=payload.default_severity,
        review_required_threshold=payload.review_required_threshold,
        reason_code_rules_json=payload.reason_code_rules_json,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_profile.created",
        entity_type="ai_system_governance_policy_diff_gating_profile",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "status": row.status,
            "default_severity": row.default_severity,
            "review_required_threshold": row.review_required_threshold,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_profile_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-profiles",
    response_model=list[AISystemGovernancePolicyDiffGatingProfileRead],
)
def list_policy_diff_gating_profiles(
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePolicyDiffGatingProfileRead]:
    rows = AISystemGovernanceSequenceService(db).list_policy_diff_gating_profiles(
        organization_id=organization.id,
        status_filter=status_filter,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_policy_diff_gating_profile_read(row) for row in rows]


@router.patch(
    "/guardrails/policy-resolution/diff-gating-profiles/{profile_id}",
    response_model=AISystemGovernancePolicyDiffGatingProfileRead,
)
def update_policy_diff_gating_profile(
    profile_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingProfileRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_diff_gating_profile(organization_id=organization.id, profile_id=profile_id)
    before = {
        "name": row.name,
        "status": row.status,
        "default_severity": row.default_severity,
        "review_required_threshold": row.review_required_threshold,
    }
    row = service.update_policy_diff_gating_profile(row=row, updates=payload.model_dump(exclude_unset=True))
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_profile.updated",
        entity_type="ai_system_governance_policy_diff_gating_profile",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "status": row.status,
            "default_severity": row.default_severity,
            "review_required_threshold": row.review_required_threshold,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_profile_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-profiles/{profile_id}/archive",
    response_model=AISystemGovernancePolicyDiffGatingProfileRead,
)
def archive_policy_diff_gating_profile(
    profile_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingProfileArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingProfileRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_diff_gating_profile(organization_id=organization.id, profile_id=profile_id)
    before = {"status": row.status}
    row = service.archive_policy_diff_gating_profile(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_profile.archived",
        entity_type="ai_system_governance_policy_diff_gating_profile",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_profile_read(row)


@router.post(
    "/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}/classify",
    response_model=AISystemGovernancePolicyDiffGatingClassifyResponse,
)
def classify_policy_resolution_simulation_diff_report(
    diff_report_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingClassifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingClassifyResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.classify_policy_resolution_diff(
        organization_id=organization.id,
        diff_report_id=diff_report_id,
        gating_profile_id=payload.gating_profile_id,
        persist_report=payload.persist_report,
        actor_user_id=current_user.id,
    )
    if payload.persist_report:
        AuditService(db).write_audit_log(
            action="ai_system_governance_policy_diff_gating_report.generated",
            entity_type="ai_system_governance_policy_diff_gating_report",
            entity_id=result["gating_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "diff_report_id": str(result["diff_report_id"]),
                "gating_profile_id": str(result["gating_profile_id"]),
                "max_severity": result["max_severity"],
                "review_required": result["review_required"],
                "reason_code_count": result["reason_code_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernancePolicyDiffGatingClassifyResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-reports",
    response_model=list[AISystemGovernancePolicyDiffGatingReportRead],
)
def list_policy_diff_gating_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    diff_report_id: uuid.UUID | None = Query(default=None),
    gating_profile_id: uuid.UUID | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    max_severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePolicyDiffGatingReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_policy_diff_gating_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        diff_report_id=diff_report_id,
        gating_profile_id=gating_profile_id,
        review_required=review_required,
        max_severity=max_severity,
        limit=limit,
        offset=offset,
    )
    return [_policy_diff_gating_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-reports/{gating_report_id}",
    response_model=AISystemGovernancePolicyDiffGatingReportRead,
)
def get_policy_diff_gating_report(
    gating_report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingReportRead:
    row = AISystemGovernanceSequenceService(db).require_policy_diff_gating_report(
        organization_id=organization.id,
        gating_report_id=gating_report_id,
    )
    return _policy_diff_gating_report_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-reports/{gating_report_id}/archive",
    response_model=AISystemGovernancePolicyDiffGatingReportRead,
)
def archive_policy_diff_gating_report(
    gating_report_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_diff_gating_report(organization_id=organization.id, gating_report_id=gating_report_id)
    before = {"status": row.status}
    row = service.archive_policy_diff_gating_report(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_report.archived",
        entity_type="ai_system_governance_policy_diff_gating_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_report_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-summary",
    response_model=AISystemGovernancePolicyDiffGatingSummary,
)
def policy_diff_gating_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingSummary:
    summary = AISystemGovernanceSequenceService(db).policy_diff_gating_summary(organization_id=organization.id)
    return AISystemGovernancePolicyDiffGatingSummary(**summary)


@router.post(
    "/guardrails/policy-resolution/diff-gating-reports/compare",
    response_model=AISystemGovernancePolicyDiffGatingCompareResponse,
)
def compare_policy_diff_gating_reports(
    payload: AISystemGovernancePolicyDiffGatingCompareRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingCompareResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.compare_policy_diff_gating_reports(
        organization_id=organization.id,
        base_gating_report_id=payload.base_gating_report_id,
        compare_gating_report_id=payload.compare_gating_report_id,
        title=payload.title,
        persist_compare=payload.persist_compare,
        actor_user_id=current_user.id,
    )
    if payload.persist_compare:
        AuditService(db).write_audit_log(
            action="ai_system_governance_policy_diff_gating_compare.generated",
            entity_type="ai_system_governance_policy_diff_gating_compare_report",
            entity_id=result["compare_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "base_gating_report_id": str(result["base_gating_report_id"]),
                "compare_gating_report_id": str(result["compare_gating_report_id"]),
                "severity_direction": result["severity_direction"],
                "review_required_changed": result["review_required_changed"],
                "reason_code_changes_count": result["reason_code_changes_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernancePolicyDiffGatingCompareResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-reports",
    response_model=list[AISystemGovernancePolicyDiffGatingCompareReportRead],
)
def list_policy_diff_gating_compare_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    base_gating_report_id: uuid.UUID | None = Query(default=None),
    compare_gating_report_id: uuid.UUID | None = Query(default=None),
    severity_direction: str | None = Query(default=None),
    review_required_changed: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePolicyDiffGatingCompareReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_policy_diff_gating_compare_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        base_gating_report_id=base_gating_report_id,
        compare_gating_report_id=compare_gating_report_id,
        severity_direction=severity_direction,
        review_required_changed=review_required_changed,
        limit=limit,
        offset=offset,
    )
    return [_policy_diff_gating_compare_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-reports/{compare_report_id}",
    response_model=AISystemGovernancePolicyDiffGatingCompareReportRead,
)
def get_policy_diff_gating_compare_report(
    compare_report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingCompareReportRead:
    row = AISystemGovernanceSequenceService(db).require_policy_diff_gating_compare_report(
        organization_id=organization.id,
        compare_report_id=compare_report_id,
    )
    return _policy_diff_gating_compare_report_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-reports/{compare_report_id}/archive",
    response_model=AISystemGovernancePolicyDiffGatingCompareReportRead,
)
def archive_policy_diff_gating_compare_report(
    compare_report_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingCompareReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingCompareReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_diff_gating_compare_report(
        organization_id=organization.id,
        compare_report_id=compare_report_id,
    )
    before = {"status": row.status}
    row = service.archive_policy_diff_gating_compare_report(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare.archived",
        entity_type="ai_system_governance_policy_diff_gating_compare_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_report_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-summary",
    response_model=AISystemGovernancePolicyDiffGatingCompareSummary,
)
def policy_diff_gating_compare_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingCompareSummary:
    summary = AISystemGovernanceSequenceService(db).policy_diff_gating_compare_summary(organization_id=organization.id)
    return AISystemGovernancePolicyDiffGatingCompareSummary(**summary)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-presets",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_policy_diff_gating_compare_preset(
    payload: AISystemGovernancePolicyDiffGatingComparePresetCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.create_policy_diff_gating_compare_preset(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        status_value=payload.status,
        baseline_gating_report_id=payload.baseline_gating_report_id,
        baseline_gating_profile_id=payload.baseline_gating_profile_id,
        watched_reason_codes_json=payload.watched_reason_codes_json,
        ignored_reason_codes_json=payload.ignored_reason_codes_json,
        interpretation_rules_json=payload.interpretation_rules_json,
        default_interpretation_band=payload.default_interpretation_band,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset.created",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "status": row.status,
            "default_interpretation_band": row.default_interpretation_band,
            "baseline_gating_report_id": str(row.baseline_gating_report_id) if row.baseline_gating_report_id else None,
            "baseline_gating_profile_id": str(row.baseline_gating_profile_id) if row.baseline_gating_profile_id else None,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_preset_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-presets",
    response_model=list[AISystemGovernancePolicyDiffGatingComparePresetRead],
)
def list_policy_diff_gating_compare_presets(
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePolicyDiffGatingComparePresetRead]:
    rows = AISystemGovernanceSequenceService(db).list_policy_diff_gating_compare_presets(
        organization_id=organization.id,
        status_filter=status_filter,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_policy_diff_gating_compare_preset_read(row) for row in rows]


@router.patch(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetRead,
)
def update_policy_diff_gating_compare_preset(
    preset_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_diff_gating_compare_preset(organization_id=organization.id, preset_id=preset_id)
    before = {
        "name": row.name,
        "status": row.status,
        "default_interpretation_band": row.default_interpretation_band,
        "baseline_gating_report_id": str(row.baseline_gating_report_id) if row.baseline_gating_report_id else None,
        "baseline_gating_profile_id": str(row.baseline_gating_profile_id) if row.baseline_gating_profile_id else None,
        "version_selection_mode": row.version_selection_mode,
        "allow_explicit_version_override": row.allow_explicit_version_override,
    }
    row = service.update_policy_diff_gating_compare_preset(row=row, updates=payload.model_dump(exclude_unset=True))
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset.updated",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "status": row.status,
            "default_interpretation_band": row.default_interpretation_band,
            "baseline_gating_report_id": str(row.baseline_gating_report_id) if row.baseline_gating_report_id else None,
            "baseline_gating_profile_id": str(row.baseline_gating_profile_id) if row.baseline_gating_profile_id else None,
            "version_selection_mode": row.version_selection_mode,
            "allow_explicit_version_override": row.allow_explicit_version_override,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_preset_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/archive",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetRead,
)
def archive_policy_diff_gating_compare_preset(
    preset_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_diff_gating_compare_preset(organization_id=organization.id, preset_id=preset_id)
    before = {"status": row.status}
    row = service.archive_policy_diff_gating_compare_preset(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset.archived",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_preset_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_policy_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetVersionRead:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_policy_diff_gating_compare_preset(organization_id=organization.id, preset_id=preset_id)
    row = service.create_policy_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset=preset,
        change_reason=payload.change_reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset_version.created",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset_version",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "preset_id": str(row.preset_id),
            "version_number": row.version_number,
            "status": row.status,
        },
        metadata_json={"source": "api", "change_reason": payload.change_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_preset_version_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions",
    response_model=list[AISystemGovernancePolicyDiffGatingComparePresetVersionRead],
)
def list_policy_diff_gating_compare_preset_versions(
    preset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePolicyDiffGatingComparePresetVersionRead]:
    service = AISystemGovernanceSequenceService(db)
    service.require_policy_diff_gating_compare_preset(organization_id=organization.id, preset_id=preset_id)
    rows = service.list_policy_diff_gating_compare_preset_versions(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    return [_policy_diff_gating_compare_preset_version_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions/{version_id}",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetVersionRead,
)
def get_policy_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetVersionRead:
    row = AISystemGovernanceSequenceService(db).require_policy_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset_id=preset_id,
        version_id=version_id,
    )
    return _policy_diff_gating_compare_preset_version_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions/{version_id}/activate",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetVersionRead,
)
def activate_policy_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetVersionActivateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetVersionRead:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_policy_diff_gating_compare_preset(organization_id=organization.id, preset_id=preset_id)
    row = service.require_policy_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset_id=preset_id,
        version_id=version_id,
    )
    row = service.activate_policy_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset=preset,
        version=row,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset_version.activated",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset_version",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "preset_id": str(preset_id),
            "version_number": row.version_number,
            "status": row.status,
            "preset_active_version_id": str(preset.active_version_id) if preset.active_version_id else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_preset_version_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/versions/{version_id}/archive",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetVersionRead,
)
def archive_policy_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetVersionArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetVersionRead:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_policy_diff_gating_compare_preset(organization_id=organization.id, preset_id=preset_id)
    row = service.require_policy_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset_id=preset_id,
        version_id=version_id,
    )
    before = {"status": row.status}
    row = service.archive_policy_diff_gating_compare_preset_version(preset=preset, version=row)
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset_version.archived",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset_version",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_preset_version_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/pin-version",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetRead,
)
def pin_policy_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetPinVersionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetRead:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_policy_diff_gating_compare_preset(organization_id=organization.id, preset_id=preset_id)
    version = service.require_policy_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset_id=preset_id,
        version_id=payload.version_id,
    )
    before = {
        "pinned_version_id": str(preset.pinned_version_id) if preset.pinned_version_id else None,
        "version_selection_mode": preset.version_selection_mode,
        "allow_explicit_version_override": preset.allow_explicit_version_override,
    }
    preset = service.pin_policy_diff_gating_compare_preset_version(
        preset=preset,
        version=version,
        version_selection_mode=payload.version_selection_mode,
        allow_explicit_version_override=payload.allow_explicit_version_override,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset.version_pinned",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset",
        entity_id=preset.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "pinned_version_id": str(preset.pinned_version_id) if preset.pinned_version_id else None,
            "version_selection_mode": preset.version_selection_mode,
            "allow_explicit_version_override": preset.allow_explicit_version_override,
            "pinned_at": preset.pinned_at.isoformat() if preset.pinned_at else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(preset)
    return _policy_diff_gating_compare_preset_read(preset)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/unpin-version",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetRead,
)
def unpin_policy_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetUnpinVersionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetRead:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_policy_diff_gating_compare_preset(organization_id=organization.id, preset_id=preset_id)
    before = {
        "pinned_version_id": str(preset.pinned_version_id) if preset.pinned_version_id else None,
        "version_selection_mode": preset.version_selection_mode,
        "allow_explicit_version_override": preset.allow_explicit_version_override,
    }
    preset = service.unpin_policy_diff_gating_compare_preset_version(
        preset=preset,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset.version_unpinned",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset",
        entity_id=preset.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "pinned_version_id": str(preset.pinned_version_id) if preset.pinned_version_id else None,
            "version_selection_mode": preset.version_selection_mode,
            "allow_explicit_version_override": preset.allow_explicit_version_override,
            "unpinned_at": preset.unpinned_at.isoformat() if preset.unpinned_at else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(preset)
    return _policy_diff_gating_compare_preset_read(preset)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/pinning-status",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetPinningStatus,
)
def get_policy_diff_gating_compare_preset_pinning_status(
    preset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetPinningStatus:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_policy_diff_gating_compare_preset(organization_id=organization.id, preset_id=preset_id)
    pinned_version_number = None
    if preset.pinned_version_id is not None:
        version = service.require_policy_diff_gating_compare_preset_version(
            organization_id=organization.id,
            preset_id=preset.id,
            version_id=preset.pinned_version_id,
        )
        pinned_version_number = version.version_number
    return AISystemGovernancePolicyDiffGatingComparePresetPinningStatus(
        preset_id=preset.id,
        pinned_version_id=preset.pinned_version_id,
        pinned_version_number=pinned_version_number,
        version_selection_mode=preset.version_selection_mode,
        allow_explicit_version_override=preset.allow_explicit_version_override,
        pinned_at=preset.pinned_at,
        pinned_by_user_id=preset.pinned_by_user_id,
        pin_reason=preset.pin_reason,
        unpinned_at=preset.unpinned_at,
        unpinned_by_user_id=preset.unpinned_by_user_id,
        unpin_reason=preset.unpin_reason,
        caveat=(
            "Preset version pinning controls deterministic interpretation snapshots for human review. "
            "It does not approve, reject, create tasks, create reviews, or trigger automation."
        ),
    )


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/evaluate",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetEvaluateResponse,
)
def evaluate_policy_diff_gating_compare_preset(
    preset_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetEvaluateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetEvaluateResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.evaluate_policy_diff_gating_compare_preset(
        organization_id=organization.id,
        preset_id=preset_id,
        preset_version_id=payload.preset_version_id,
        version_override_reason=payload.version_override_reason,
        base_gating_report_id=payload.base_gating_report_id,
        compare_gating_report_id=payload.compare_gating_report_id,
        persist_report=payload.persist_report,
        persist_compare_report=payload.persist_compare_report,
        actor_user_id=current_user.id,
    )
    if payload.persist_compare_report and result.get("compare_report_id") is not None:
        compare_result = result["compare_result"]
        AuditService(db).write_audit_log(
            action="ai_system_governance_policy_diff_gating_compare.generated",
            entity_type="ai_system_governance_policy_diff_gating_compare_report",
            entity_id=result["compare_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "base_gating_report_id": str(compare_result["base_gating_report_id"]),
                "compare_gating_report_id": str(compare_result["compare_gating_report_id"]),
                "severity_direction": compare_result["severity_direction"],
                "review_required_changed": compare_result["review_required_changed"],
                "reason_code_changes_count": compare_result["reason_code_changes_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    if payload.persist_report and result.get("preset_report_id") is not None:
        AuditService(db).write_audit_log(
            action="ai_system_governance_policy_diff_gating_compare_preset_report.generated",
            entity_type="ai_system_governance_policy_diff_gating_compare_preset_report",
            entity_id=result["preset_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "preset_id": str(result["preset_id"]),
                "preset_version_id": str(result["preset_version_id"]) if result.get("preset_version_id") else None,
                "preset_version_number": result.get("preset_version_number"),
                "version_resolution_source": result.get("version_resolution_source"),
                "pinned_version_id": str(result["pinned_version_id"]) if result.get("pinned_version_id") else None,
                "explicit_version_override_used": bool(result.get("explicit_version_override_used", False)),
                "version_override_reason": result.get("version_override_reason"),
                "base_gating_report_id": str(result["base_gating_report_id"]),
                "compare_gating_report_id": str(result["compare_gating_report_id"]),
                "compare_report_id": str(result["compare_report_id"]) if result.get("compare_report_id") else None,
                "interpretation_band": result["interpretation_band"],
                "review_required": result["review_required"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    if payload.persist_compare_report or payload.persist_report:
        db.commit()
    return AISystemGovernancePolicyDiffGatingComparePresetEvaluateResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-reports",
    response_model=list[AISystemGovernancePolicyDiffGatingComparePresetReportRead],
)
def list_policy_diff_gating_compare_preset_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    preset_id: uuid.UUID | None = Query(default=None),
    interpretation_band: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePolicyDiffGatingComparePresetReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_policy_diff_gating_compare_preset_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        preset_id=preset_id,
        interpretation_band=interpretation_band,
        review_required=review_required,
        limit=limit,
        offset=offset,
    )
    return [_policy_diff_gating_compare_preset_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-reports/{preset_report_id}",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetReportRead,
)
def get_policy_diff_gating_compare_preset_report(
    preset_report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetReportRead:
    row = AISystemGovernanceSequenceService(db).require_policy_diff_gating_compare_preset_report(
        organization_id=organization.id,
        preset_report_id=preset_report_id,
    )
    return _policy_diff_gating_compare_preset_report_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-reports/{preset_report_id}/archive",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetReportRead,
)
def archive_policy_diff_gating_compare_preset_report(
    preset_report_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_diff_gating_compare_preset_report(
        organization_id=organization.id,
        preset_report_id=preset_report_id,
    )
    before = {"status": row.status}
    row = service.archive_policy_diff_gating_compare_preset_report(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset_report.archived",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_preset_report_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-summary",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetSummary,
)
def policy_diff_gating_compare_preset_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetSummary:
    summary = AISystemGovernanceSequenceService(db).policy_diff_gating_compare_preset_summary(
        organization_id=organization.id
    )
    return AISystemGovernancePolicyDiffGatingComparePresetSummary(**summary)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_policy_diff_gating_compare_preset_assignment(
    payload: AISystemGovernancePolicyDiffGatingComparePresetAssignmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.create_policy_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        preset_id=payload.preset_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        scope_json=payload.scope_json,
        priority=payload.priority,
        reason=payload.reason,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset_assignment.created",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "preset_id": str(row.preset_id),
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id else None,
            "scope_json": row.scope_json,
            "priority": row.priority,
            "status": row.status,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_preset_assignment_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
    response_model=list[AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead],
)
def list_policy_diff_gating_compare_preset_assignments(
    status_filter: str | None = Query(default=None, alias="status"),
    scope_type: str | None = Query(default=None),
    preset_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead]:
    rows = AISystemGovernanceSequenceService(db).list_policy_diff_gating_compare_preset_assignments(
        organization_id=organization.id,
        status_filter=status_filter,
        scope_type=scope_type,
        preset_id=preset_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_policy_diff_gating_compare_preset_assignment_read(row) for row in rows]


@router.patch(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment_id}",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead,
)
def update_policy_diff_gating_compare_preset_assignment(
    assignment_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetAssignmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        assignment_id=assignment_id,
    )
    before = {
        "preset_id": str(row.preset_id),
        "scope_type": row.scope_type,
        "scope_id": str(row.scope_id) if row.scope_id else None,
        "scope_json": row.scope_json,
        "priority": row.priority,
        "status": row.status,
    }
    row = service.update_policy_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        row=row,
        updates=payload.model_dump(exclude_unset=True),
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset_assignment.updated",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "preset_id": str(row.preset_id),
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id else None,
            "scope_json": row.scope_json,
            "priority": row.priority,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_preset_assignment_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment_id}/archive",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead,
)
def archive_policy_diff_gating_compare_preset_assignment(
    assignment_id: uuid.UUID,
    payload: AISystemGovernancePolicyDiffGatingComparePresetAssignmentArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        assignment_id=assignment_id,
    )
    before = {"status": row.status}
    row = service.archive_policy_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        row=row,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_policy_diff_gating_compare_preset_assignment.archived",
        entity_type="ai_system_governance_policy_diff_gating_compare_preset_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_diff_gating_compare_preset_assignment_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment_id}/history",
    response_model=list[AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistoryRead],
)
def list_policy_diff_gating_compare_preset_assignment_history(
    assignment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistoryRead]:
    service = AISystemGovernanceSequenceService(db)
    service.require_policy_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        assignment_id=assignment_id,
    )
    rows = service.list_policy_diff_gating_compare_preset_assignment_history(
        organization_id=organization.id,
        assignment_id=assignment_id,
    )
    return [_policy_diff_gating_compare_preset_assignment_history_read(row) for row in rows]


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/resolve",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetAssignmentResolveResponse,
)
def resolve_policy_diff_gating_compare_preset_assignment(
    payload: AISystemGovernancePolicyDiffGatingComparePresetAssignmentResolveRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentResolveResponse:
    resolved = AISystemGovernanceSequenceService(db).resolve_policy_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        explicit_preset_id=payload.explicit_preset_id,
        sequence_pack_id=payload.sequence_pack_id,
        ai_system_ids=payload.ai_system_ids,
        review_types=payload.review_types,
        rollout_class=payload.rollout_class,
    )
    return AISystemGovernancePolicyDiffGatingComparePresetAssignmentResolveResponse(**resolved)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-diagnostics",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsResponse,
)
def policy_diff_gating_compare_preset_assignment_coverage_diagnostics(
    payload: AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.policy_diff_gating_compare_preset_assignment_coverage_diagnostics(
        organization_id=organization.id,
        contexts=[item.model_dump() for item in payload.contexts],
        title=payload.title,
        description=payload.description,
        persist_report=payload.persist_report,
        include_inactive_assignments=payload.include_inactive_assignments,
        include_archived_assignments=payload.include_archived_assignments,
        include_preset_version_diagnostics=payload.include_preset_version_diagnostics,
        actor_user_id=current_user.id,
    )
    if payload.persist_report and result.get("report_id") is not None:
        AuditService(db).write_audit_log(
            action="ai_system_governance_preset_assignment_diagnostic_report.generated",
            entity_type="ai_system_governance_preset_assignment_diagnostic_report",
            entity_id=result["report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "context_count": result["context_count"],
                "resolved_contexts_count": result["resolved_contexts_count"],
                "unresolved_contexts_count": result["unresolved_contexts_count"],
                "warning_contexts_count": result["warning_contexts_count"],
                "critical_contexts_count": result["critical_contexts_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageDiagnosticsResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/health-diagnostics",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetAssignmentHealthDiagnosticsResponse,
)
def policy_diff_gating_compare_preset_assignment_health_diagnostics(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentHealthDiagnosticsResponse:
    result = AISystemGovernanceSequenceService(db).policy_diff_gating_compare_preset_assignment_health_diagnostics(
        organization_id=organization.id
    )
    return AISystemGovernancePolicyDiffGatingComparePresetAssignmentHealthDiagnosticsResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-summary",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageSummaryResponse,
)
def policy_diff_gating_compare_preset_assignment_coverage_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageSummaryResponse:
    result = AISystemGovernanceSequenceService(db).policy_diff_gating_compare_preset_assignment_coverage_summary(
        organization_id=organization.id
    )
    return AISystemGovernancePolicyDiffGatingComparePresetAssignmentCoverageSummaryResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports",
    response_model=list[AISystemGovernancePresetAssignmentDiagnosticReportRead],
)
def list_preset_assignment_diagnostic_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePresetAssignmentDiagnosticReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_preset_assignment_diagnostic_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return [_preset_assignment_diagnostic_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}",
    response_model=AISystemGovernancePresetAssignmentDiagnosticReportRead,
)
def get_preset_assignment_diagnostic_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticReportRead:
    row = AISystemGovernanceSequenceService(db).require_preset_assignment_diagnostic_report(
        organization_id=organization.id,
        report_id=report_id,
    )
    return _preset_assignment_diagnostic_report_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}/archive",
    response_model=AISystemGovernancePresetAssignmentDiagnosticReportRead,
)
def archive_preset_assignment_diagnostic_report(
    report_id: uuid.UUID,
    payload: AISystemGovernancePresetAssignmentDiagnosticReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePresetAssignmentDiagnosticReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_preset_assignment_diagnostic_report(organization_id=organization.id, report_id=report_id)
    before = {"status": row.status}
    row = service.archive_preset_assignment_diagnostic_report(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_preset_assignment_diagnostic_report.archived",
        entity_type="ai_system_governance_preset_assignment_diagnostic_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _preset_assignment_diagnostic_report_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff",
    response_model=AISystemGovernancePresetAssignmentDiagnosticDiffResponse,
)
def diff_preset_assignment_diagnostic_reports(
    payload: AISystemGovernancePresetAssignmentDiagnosticDiffRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticDiffResponse:
    result = AISystemGovernanceSequenceService(db).diff_preset_assignment_diagnostic_reports(
        organization_id=organization.id,
        base_report_id=payload.base_report_id,
        compare_report_id=payload.compare_report_id,
        title=payload.title,
        persist_diff=payload.persist_diff,
        context_match_strategy=payload.context_match_strategy,
        actor_user_id=current_user.id,
    )
    if payload.persist_diff and result.get("diff_report_id") is not None:
        AuditService(db).write_audit_log(
            action="ai_system_governance_preset_assignment_diagnostic_diff.generated",
            entity_type="ai_system_governance_preset_assignment_diagnostic_diff_report",
            entity_id=result["diff_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "base_report_id": str(result["base_report_id"]),
                "compare_report_id": str(result["compare_report_id"]),
                "added_contexts_count": result["added_contexts_count"],
                "removed_contexts_count": result["removed_contexts_count"],
                "changed_contexts_count": result["changed_contexts_count"],
                "diagnostic_code_changes_count": result["diagnostic_code_changes_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernancePresetAssignmentDiagnosticDiffResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports",
    response_model=list[AISystemGovernancePresetAssignmentDiagnosticDiffReportRead],
)
def list_preset_assignment_diagnostic_diff_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    base_report_id: uuid.UUID | None = Query(default=None),
    compare_report_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePresetAssignmentDiagnosticDiffReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_preset_assignment_diagnostic_diff_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        base_report_id=base_report_id,
        compare_report_id=compare_report_id,
        limit=limit,
        offset=offset,
    )
    return [_preset_assignment_diagnostic_diff_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}",
    response_model=AISystemGovernancePresetAssignmentDiagnosticDiffReportRead,
)
def get_preset_assignment_diagnostic_diff_report(
    diff_report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticDiffReportRead:
    row = AISystemGovernanceSequenceService(db).require_preset_assignment_diagnostic_diff_report(
        organization_id=organization.id,
        diff_report_id=diff_report_id,
    )
    return _preset_assignment_diagnostic_diff_report_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}/archive",
    response_model=AISystemGovernancePresetAssignmentDiagnosticDiffReportRead,
)
def archive_preset_assignment_diagnostic_diff_report(
    diff_report_id: uuid.UUID,
    payload: AISystemGovernancePresetAssignmentDiagnosticDiffReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePresetAssignmentDiagnosticDiffReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_preset_assignment_diagnostic_diff_report(
        organization_id=organization.id,
        diff_report_id=diff_report_id,
    )
    before = {"status": row.status}
    row = service.archive_preset_assignment_diagnostic_diff_report(row=row, actor_user_id=current_user.id)
    AuditService(db).write_audit_log(
        action="ai_system_governance_preset_assignment_diagnostic_diff.archived",
        entity_type="ai_system_governance_preset_assignment_diagnostic_diff_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _preset_assignment_diagnostic_diff_report_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-report-summary",
    response_model=AISystemGovernancePresetAssignmentDiagnosticReportSummaryResponse,
)
def preset_assignment_diagnostic_report_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticReportSummaryResponse:
    result = AISystemGovernanceSequenceService(db).preset_assignment_diagnostic_report_summary(
        organization_id=organization.id
    )
    return AISystemGovernancePresetAssignmentDiagnosticReportSummaryResponse(**result)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}/export",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportCreateResponse,
)
def export_preset_assignment_diagnostic_report(
    report_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportCreateResponse:
    service = AISystemGovernanceSequenceService(db)
    row = service.export_preset_assignment_diagnostic_report(
        organization_id=organization.id,
        report_id=report_id,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_preset_assignment_diagnostic_export.generated",
        entity_type="ai_system_governance_preset_assignment_diagnostic_export",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "export_type": row.export_type,
            "source_report_id": str(row.source_report_id) if row.source_report_id else None,
            "source_diff_report_id": str(row.source_diff_report_id) if row.source_diff_report_id else None,
            "status": row.status,
            "canonical_payload_sha256": row.canonical_payload_sha256,
            "signature_algorithm": row.signature_algorithm,
            "signing_key_id": row.signing_key_id,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return AISystemGovernancePresetAssignmentDiagnosticExportCreateResponse(
        export_id=row.id,
        export_type=row.export_type,
        source_report_id=row.source_report_id,
        source_diff_report_id=row.source_diff_report_id,
        canonical_payload_sha256=row.canonical_payload_sha256,
        signature_algorithm=row.signature_algorithm,
        internal_signature=row.internal_signature,
        signing_key_id=row.signing_key_id,
        caveat=(
            "This export uses an internal CompliVibe integrity signature. "
            "It is not a legal e-signature, external audit attestation, or certification."
        ),
    )


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}/export",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportCreateResponse,
)
def export_preset_assignment_diagnostic_diff_report(
    diff_report_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportCreateResponse:
    service = AISystemGovernanceSequenceService(db)
    row = service.export_preset_assignment_diagnostic_diff_report(
        organization_id=organization.id,
        diff_report_id=diff_report_id,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_preset_assignment_diagnostic_export.generated",
        entity_type="ai_system_governance_preset_assignment_diagnostic_export",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "export_type": row.export_type,
            "source_report_id": str(row.source_report_id) if row.source_report_id else None,
            "source_diff_report_id": str(row.source_diff_report_id) if row.source_diff_report_id else None,
            "status": row.status,
            "canonical_payload_sha256": row.canonical_payload_sha256,
            "signature_algorithm": row.signature_algorithm,
            "signing_key_id": row.signing_key_id,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return AISystemGovernancePresetAssignmentDiagnosticExportCreateResponse(
        export_id=row.id,
        export_type=row.export_type,
        source_report_id=row.source_report_id,
        source_diff_report_id=row.source_diff_report_id,
        canonical_payload_sha256=row.canonical_payload_sha256,
        signature_algorithm=row.signature_algorithm,
        internal_signature=row.internal_signature,
        signing_key_id=row.signing_key_id,
        caveat=(
            "This export uses an internal CompliVibe integrity signature. "
            "It is not a legal e-signature, external audit attestation, or certification."
        ),
    )


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports",
    response_model=list[AISystemGovernancePresetAssignmentDiagnosticExportRead],
)
def list_preset_assignment_diagnostic_exports(
    export_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    source_report_id: uuid.UUID | None = Query(default=None),
    source_diff_report_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePresetAssignmentDiagnosticExportRead]:
    rows = AISystemGovernanceSequenceService(db).list_preset_assignment_diagnostic_exports(
        organization_id=organization.id,
        export_type=export_type,
        status_filter=status_filter,
        source_report_id=source_report_id,
        source_diff_report_id=source_diff_report_id,
        limit=limit,
        offset=offset,
    )
    return [_preset_assignment_diagnostic_export_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportRead,
)
def get_preset_assignment_diagnostic_export(
    export_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportRead:
    row = AISystemGovernanceSequenceService(db).require_preset_assignment_diagnostic_export(
        organization_id=organization.id,
        export_id=export_id,
    )
    return _preset_assignment_diagnostic_export_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/verify",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportVerifyResponse,
)
def verify_preset_assignment_diagnostic_export(
    export_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportVerifyResponse:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_preset_assignment_diagnostic_export(
        organization_id=organization.id,
        export_id=export_id,
    )
    result = service.verify_preset_assignment_diagnostic_export(
        organization_id=organization.id,
        row=row,
    )
    return AISystemGovernancePresetAssignmentDiagnosticExportVerifyResponse(**result)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/revoke",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportRead,
)
def revoke_preset_assignment_diagnostic_export(
    export_id: uuid.UUID,
    payload: AISystemGovernancePresetAssignmentDiagnosticExportRevokeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_preset_assignment_diagnostic_export(
        organization_id=organization.id,
        export_id=export_id,
    )
    before = {"status": row.status}
    row = service.revoke_preset_assignment_diagnostic_export(
        row=row,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_preset_assignment_diagnostic_export.revoked",
        entity_type="ai_system_governance_preset_assignment_diagnostic_export",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _preset_assignment_diagnostic_export_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reason-codes",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportDiffReasonCodeCatalogResponse,
)
def preset_assignment_diagnostic_export_diff_reason_code_catalog(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportDiffReasonCodeCatalogResponse:
    _ = organization
    _ = membership
    result = AISystemGovernanceSequenceService(db).preset_assignment_diagnostic_export_diff_reason_code_catalog()
    return AISystemGovernancePresetAssignmentDiagnosticExportDiffReasonCodeCatalogResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-summary",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportSummaryResponse,
)
def preset_assignment_diagnostic_export_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportSummaryResponse:
    result = AISystemGovernanceSequenceService(db).preset_assignment_diagnostic_export_summary(
        organization_id=organization.id
    )
    return AISystemGovernancePresetAssignmentDiagnosticExportSummaryResponse(**result)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportDiffResponse,
)
def diff_preset_assignment_diagnostic_exports(
    payload: AISystemGovernancePresetAssignmentDiagnosticExportDiffRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportDiffResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.diff_preset_assignment_diagnostic_exports(
        organization_id=organization.id,
        base_export_id=payload.base_export_id,
        compare_export_id=payload.compare_export_id,
        title=payload.title,
        persist_diff=payload.persist_diff,
        actor_user_id=current_user.id,
    )
    if payload.persist_diff and result.get("export_diff_report_id") is not None:
        AuditService(db).write_audit_log(
            action="ai_system_governance_preset_assignment_diagnostic_export_diff.generated",
            entity_type="ai_system_governance_preset_assignment_diagnostic_export_diff_report",
            entity_id=result["export_diff_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "base_export_id": str(result["base_export_id"]),
                "compare_export_id": str(result["compare_export_id"]),
                "export_type": result["export_type"],
                "payload_hash_changed": result["payload_hash_changed"],
                "added_paths_count": result["added_paths_count"],
                "removed_paths_count": result["removed_paths_count"],
                "changed_paths_count": result["changed_paths_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernancePresetAssignmentDiagnosticExportDiffResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports",
    response_model=list[AISystemGovernancePresetAssignmentDiagnosticExportDiffReportRead],
)
def list_preset_assignment_diagnostic_export_diff_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    export_type: str | None = Query(default=None),
    base_export_id: uuid.UUID | None = Query(default=None),
    compare_export_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernancePresetAssignmentDiagnosticExportDiffReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_preset_assignment_diagnostic_export_diff_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        export_type=export_type,
        base_export_id=base_export_id,
        compare_export_id=compare_export_id,
        limit=limit,
        offset=offset,
    )
    return [_preset_assignment_diagnostic_export_diff_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportDiffReportRead,
)
def get_preset_assignment_diagnostic_export_diff_report(
    export_diff_report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportDiffReportRead:
    row = AISystemGovernanceSequenceService(db).require_preset_assignment_diagnostic_export_diff_report(
        organization_id=organization.id,
        export_diff_report_id=export_diff_report_id,
    )
    return _preset_assignment_diagnostic_export_diff_report_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}/archive",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportDiffReportRead,
)
def archive_preset_assignment_diagnostic_export_diff_report(
    export_diff_report_id: uuid.UUID,
    payload: AISystemGovernancePresetAssignmentDiagnosticExportDiffReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportDiffReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_preset_assignment_diagnostic_export_diff_report(
        organization_id=organization.id,
        export_diff_report_id=export_diff_report_id,
    )
    before = {"status": row.status}
    row = service.archive_preset_assignment_diagnostic_export_diff_report(
        row=row,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_preset_assignment_diagnostic_export_diff.archived",
        entity_type="ai_system_governance_preset_assignment_diagnostic_export_diff_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _preset_assignment_diagnostic_export_diff_report_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-summary",
    response_model=AISystemGovernancePresetAssignmentDiagnosticExportDiffSummaryResponse,
)
def preset_assignment_diagnostic_export_diff_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePresetAssignmentDiagnosticExportDiffSummaryResponse:
    result = AISystemGovernanceSequenceService(db).preset_assignment_diagnostic_export_diff_summary(
        organization_id=organization.id
    )
    return AISystemGovernancePresetAssignmentDiagnosticExportDiffSummaryResponse(**result)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingProfileRead,
    status_code=status.HTTP_201_CREATED,
)
def create_diagnostic_export_diff_gating_profile(
    payload: AISystemGovernanceDiagnosticExportDiffGatingProfileCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingProfileRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.create_diagnostic_export_diff_gating_profile(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        status_value=payload.status,
        default_severity=payload.default_severity,
        review_required_threshold=payload.review_required_threshold,
        reason_code_rules_json=payload.reason_code_rules_json,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_profile.created",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_profile",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "status": row.status,
            "default_severity": row.default_severity,
            "review_required_threshold": row.review_required_threshold,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_profile_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles",
    response_model=list[AISystemGovernanceDiagnosticExportDiffGatingProfileRead],
)
def list_diagnostic_export_diff_gating_profiles(
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceDiagnosticExportDiffGatingProfileRead]:
    rows = AISystemGovernanceSequenceService(db).list_diagnostic_export_diff_gating_profiles(
        organization_id=organization.id,
        status_filter=status_filter,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_diagnostic_export_diff_gating_profile_read(row) for row in rows]


@router.patch(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles/{profile_id}",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingProfileRead,
)
def update_diagnostic_export_diff_gating_profile(
    profile_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingProfileRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_diagnostic_export_diff_gating_profile(
        organization_id=organization.id,
        profile_id=profile_id,
    )
    before = {
        "name": row.name,
        "status": row.status,
        "default_severity": row.default_severity,
        "review_required_threshold": row.review_required_threshold,
    }
    row = service.update_diagnostic_export_diff_gating_profile(
        row=row,
        updates=payload.model_dump(exclude_unset=True),
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_profile.updated",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_profile",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "status": row.status,
            "default_severity": row.default_severity,
            "review_required_threshold": row.review_required_threshold,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_profile_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles/{profile_id}/archive",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingProfileRead,
)
def archive_diagnostic_export_diff_gating_profile(
    profile_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingProfileArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingProfileRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_diagnostic_export_diff_gating_profile(
        organization_id=organization.id,
        profile_id=profile_id,
    )
    before = {"status": row.status}
    row = service.archive_diagnostic_export_diff_gating_profile(
        row=row,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_profile.archived",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_profile",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_profile_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}/classify",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingClassifyResponse,
)
def classify_diagnostic_export_diff_report(
    export_diff_report_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingClassifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingClassifyResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.classify_diagnostic_export_diff(
        organization_id=organization.id,
        export_diff_report_id=export_diff_report_id,
        gating_profile_id=payload.gating_profile_id,
        persist_report=payload.persist_report,
        actor_user_id=current_user.id,
    )
    if payload.persist_report:
        AuditService(db).write_audit_log(
            action="ai_system_governance_diagnostic_export_diff_gating_report.generated",
            entity_type="ai_system_governance_diagnostic_export_diff_gating_report",
            entity_id=result["gating_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "export_diff_report_id": str(result["export_diff_report_id"]),
                "gating_profile_id": str(result["gating_profile_id"]),
                "max_severity": result["max_severity"],
                "review_required": result["review_required"],
                "reason_code_count": result["reason_code_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernanceDiagnosticExportDiffGatingClassifyResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports",
    response_model=list[AISystemGovernanceDiagnosticExportDiffGatingReportRead],
)
def list_diagnostic_export_diff_gating_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    export_diff_report_id: uuid.UUID | None = Query(default=None),
    gating_profile_id: uuid.UUID | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    max_severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceDiagnosticExportDiffGatingReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_diagnostic_export_diff_gating_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        export_diff_report_id=export_diff_report_id,
        gating_profile_id=gating_profile_id,
        review_required=review_required,
        max_severity=max_severity,
        limit=limit,
        offset=offset,
    )
    return [_diagnostic_export_diff_gating_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/{gating_report_id}",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingReportRead,
)
def get_diagnostic_export_diff_gating_report(
    gating_report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingReportRead:
    row = AISystemGovernanceSequenceService(db).require_diagnostic_export_diff_gating_report(
        organization_id=organization.id,
        gating_report_id=gating_report_id,
    )
    return _diagnostic_export_diff_gating_report_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/{gating_report_id}/archive",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingReportRead,
)
def archive_diagnostic_export_diff_gating_report(
    gating_report_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_diagnostic_export_diff_gating_report(
        organization_id=organization.id,
        gating_report_id=gating_report_id,
    )
    before = {"status": row.status}
    row = service.archive_diagnostic_export_diff_gating_report(
        row=row,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_report.archived",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_report_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-summary",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingSummary,
)
def diagnostic_export_diff_gating_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingSummary:
    summary = AISystemGovernanceSequenceService(db).diagnostic_export_diff_gating_summary(organization_id=organization.id)
    return AISystemGovernanceDiagnosticExportDiffGatingSummary(**summary)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/compare",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingCompareResponse,
)
def compare_diagnostic_export_diff_gating_reports(
    payload: AISystemGovernanceDiagnosticExportDiffGatingCompareRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingCompareResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.compare_diagnostic_export_diff_gating_reports(
        organization_id=organization.id,
        base_gating_report_id=payload.base_gating_report_id,
        compare_gating_report_id=payload.compare_gating_report_id,
        title=payload.title,
        persist_compare=payload.persist_compare,
        actor_user_id=current_user.id,
    )
    if payload.persist_compare:
        AuditService(db).write_audit_log(
            action="ai_system_governance_diagnostic_export_diff_gating_compare_report.generated",
            entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_report",
            entity_id=result["compare_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "base_gating_report_id": str(result["base_gating_report_id"]),
                "compare_gating_report_id": str(result["compare_gating_report_id"]),
                "max_severity_drift": result["max_severity_drift"],
                "review_required_drift": result["review_required_drift"],
                "reason_code_changes_count": result["reason_code_changes_count"],
                "severity_changes_count": result["severity_changes_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernanceDiagnosticExportDiffGatingCompareResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports",
    response_model=list[AISystemGovernanceDiagnosticExportDiffGatingCompareReportRead],
)
def list_diagnostic_export_diff_gating_compare_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    base_gating_report_id: uuid.UUID | None = Query(default=None),
    compare_gating_report_id: uuid.UUID | None = Query(default=None),
    max_severity_drift: str | None = Query(default=None),
    review_required_drift: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceDiagnosticExportDiffGatingCompareReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_diagnostic_export_diff_gating_compare_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        base_gating_report_id=base_gating_report_id,
        compare_gating_report_id=compare_gating_report_id,
        max_severity_drift=max_severity_drift,
        review_required_drift=review_required_drift,
        limit=limit,
        offset=offset,
    )
    return [_diagnostic_export_diff_gating_compare_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingCompareReportRead,
)
def get_diagnostic_export_diff_gating_compare_report(
    compare_report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingCompareReportRead:
    row = AISystemGovernanceSequenceService(db).require_diagnostic_export_diff_gating_compare_report(
        organization_id=organization.id,
        compare_report_id=compare_report_id,
    )
    return _diagnostic_export_diff_gating_compare_report_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/archive",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingCompareReportRead,
)
def archive_diagnostic_export_diff_gating_compare_report(
    compare_report_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingCompareReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingCompareReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_diagnostic_export_diff_gating_compare_report(
        organization_id=organization.id,
        compare_report_id=compare_report_id,
    )
    before = {"status": row.status}
    row = service.archive_diagnostic_export_diff_gating_compare_report(
        row=row,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_report.archived",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_report_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-summary",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingCompareSummary,
)
def diagnostic_export_diff_gating_compare_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingCompareSummary:
    summary = AISystemGovernanceSequenceService(db).diagnostic_export_diff_gating_compare_summary(
        organization_id=organization.id
    )
    return AISystemGovernanceDiagnosticExportDiffGatingCompareSummary(**summary)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_diagnostic_export_diff_gating_compare_preset(
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.create_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        name=payload.name,
        description=payload.description,
        watched_reason_codes_json=payload.watched_reason_codes_json,
        ignored_reason_codes_json=payload.ignored_reason_codes_json,
        interpretation_rules_json=payload.interpretation_rules_json,
        default_interpretation_band=payload.default_interpretation_band,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset.created",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "status": row.status,
            "default_interpretation_band": row.default_interpretation_band,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_preset_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets",
    response_model=list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead],
)
def list_diagnostic_export_diff_gating_compare_presets(
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead]:
    rows = AISystemGovernanceSequenceService(db).list_diagnostic_export_diff_gating_compare_presets(
        organization_id=organization.id,
        status_filter=status_filter,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_diagnostic_export_diff_gating_compare_preset_read(row) for row in rows]


@router.patch(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead,
)
def update_diagnostic_export_diff_gating_compare_preset(
    preset_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    before = {
        "name": row.name,
        "status": row.status,
        "default_interpretation_band": row.default_interpretation_band,
    }
    row = service.update_diagnostic_export_diff_gating_compare_preset(
        row=row,
        updates=payload.model_dump(exclude_unset=True),
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset.updated",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "status": row.status,
            "default_interpretation_band": row.default_interpretation_band,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_preset_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/archive",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead,
)
def archive_diagnostic_export_diff_gating_compare_preset(
    preset_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    before = {"status": row.status}
    row = service.archive_diagnostic_export_diff_gating_compare_preset(
        row=row,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset.archived",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_preset_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_diagnostic_export_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    row = service.create_diagnostic_export_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset=preset,
        change_reason=payload.change_reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset_version.created",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset_version",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "preset_id": str(row.preset_id),
            "version_number": row.version_number,
            "status": row.status,
        },
        metadata_json={"source": "api", "change_reason": payload.change_reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_preset_version_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions",
    response_model=list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead],
)
def list_diagnostic_export_diff_gating_compare_preset_versions(
    preset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead]:
    service = AISystemGovernanceSequenceService(db)
    service.require_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    rows = service.list_diagnostic_export_diff_gating_compare_preset_versions(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    return [_diagnostic_export_diff_gating_compare_preset_version_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions/{version_id}",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead,
)
def get_diagnostic_export_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead:
    row = AISystemGovernanceSequenceService(db).require_diagnostic_export_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset_id=preset_id,
        version_id=version_id,
    )
    return _diagnostic_export_diff_gating_compare_preset_version_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions/{version_id}/activate",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead,
)
def activate_diagnostic_export_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionActivateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    row = service.require_diagnostic_export_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset_id=preset_id,
        version_id=version_id,
    )
    row = service.activate_diagnostic_export_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset=preset,
        version=row,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset_version.activated",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset_version",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "preset_id": str(preset_id),
            "version_number": row.version_number,
            "status": row.status,
            "preset_active_version_id": str(preset.active_version_id) if preset.active_version_id else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_preset_version_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/versions/{version_id}/archive",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead,
)
def archive_diagnostic_export_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersionRead:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    row = service.require_diagnostic_export_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset_id=preset_id,
        version_id=version_id,
    )
    before = {"status": row.status}
    row = service.archive_diagnostic_export_diff_gating_compare_preset_version(
        preset=preset,
        version=row,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset_version.archived",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset_version",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_preset_version_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/pin-version",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead,
)
def pin_diagnostic_export_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetPinVersionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    version = service.require_diagnostic_export_diff_gating_compare_preset_version(
        organization_id=organization.id,
        preset_id=preset_id,
        version_id=payload.version_id,
    )
    before = {
        "pinned_version_id": str(preset.pinned_version_id) if preset.pinned_version_id else None,
        "version_selection_mode": preset.version_selection_mode,
        "allow_explicit_version_override": preset.allow_explicit_version_override,
    }
    preset = service.pin_diagnostic_export_diff_gating_compare_preset_version(
        preset=preset,
        version=version,
        version_selection_mode=payload.version_selection_mode,
        allow_explicit_version_override=payload.allow_explicit_version_override,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset.version_pinned",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset",
        entity_id=preset.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "pinned_version_id": str(preset.pinned_version_id) if preset.pinned_version_id else None,
            "version_selection_mode": preset.version_selection_mode,
            "allow_explicit_version_override": preset.allow_explicit_version_override,
            "pinned_at": preset.pinned_at.isoformat() if preset.pinned_at else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(preset)
    return _diagnostic_export_diff_gating_compare_preset_read(preset)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/unpin-version",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead,
)
def unpin_diagnostic_export_diff_gating_compare_preset_version(
    preset_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetUnpinVersionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetRead:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    before = {
        "pinned_version_id": str(preset.pinned_version_id) if preset.pinned_version_id else None,
        "version_selection_mode": preset.version_selection_mode,
        "allow_explicit_version_override": preset.allow_explicit_version_override,
    }
    preset = service.unpin_diagnostic_export_diff_gating_compare_preset_version(
        preset=preset,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset.version_unpinned",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset",
        entity_id=preset.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "pinned_version_id": str(preset.pinned_version_id) if preset.pinned_version_id else None,
            "version_selection_mode": preset.version_selection_mode,
            "allow_explicit_version_override": preset.allow_explicit_version_override,
            "unpinned_at": preset.unpinned_at.isoformat() if preset.unpinned_at else None,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(preset)
    return _diagnostic_export_diff_gating_compare_preset_read(preset)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets/{preset_id}/pinning-status",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetPinningStatus,
)
def get_diagnostic_export_diff_gating_compare_preset_pinning_status(
    preset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetPinningStatus:
    service = AISystemGovernanceSequenceService(db)
    preset = service.require_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        preset_id=preset_id,
    )
    active_version_number = None
    if preset.active_version_id is not None:
        active_version = service.require_diagnostic_export_diff_gating_compare_preset_version(
            organization_id=organization.id,
            preset_id=preset.id,
            version_id=preset.active_version_id,
        )
        active_version_number = active_version.version_number
    pinned_version_number = None
    if preset.pinned_version_id is not None:
        pinned_version = service.require_diagnostic_export_diff_gating_compare_preset_version(
            organization_id=organization.id,
            preset_id=preset.id,
            version_id=preset.pinned_version_id,
        )
        pinned_version_number = pinned_version.version_number
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetPinningStatus(
        preset_id=preset.id,
        active_version_id=preset.active_version_id,
        active_version_number=active_version_number,
        pinned_version_id=preset.pinned_version_id,
        pinned_version_number=pinned_version_number,
        version_selection_mode=preset.version_selection_mode,
        allow_explicit_version_override=preset.allow_explicit_version_override,
        pinned_at=preset.pinned_at,
        pinned_by_user_id=preset.pinned_by_user_id,
        pin_reason=preset.pin_reason,
        unpinned_at=preset.unpinned_at,
        unpinned_by_user_id=preset.unpinned_by_user_id,
        unpin_reason=preset.unpin_reason,
        caveat=(
            "Preset versions and pinning control deterministic interpretation snapshots for human review. "
            "They do not approve, reject, create tasks, create reviews, mutate compare reports, "
            "or trigger automation."
        ),
    )


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/evaluate-preset",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateResponse,
)
def evaluate_diagnostic_export_diff_gating_compare_preset(
    compare_report_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.evaluate_diagnostic_export_diff_gating_compare_preset(
        organization_id=organization.id,
        compare_report_id=compare_report_id,
        preset_id=payload.preset_id,
        preset_version_id=payload.preset_version_id,
        version_override_reason=payload.version_override_reason,
        persist_report=payload.persist_report,
        actor_user_id=current_user.id,
    )
    if payload.persist_report:
        AuditService(db).write_audit_log(
            action="ai_system_governance_diagnostic_export_diff_gating_compare_preset_report.generated",
            entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset_report",
            entity_id=result["preset_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "compare_report_id": str(result["compare_report_id"]),
                "preset_id": str(result["preset_id"]),
                "preset_version_id": str(result["preset_version_id"]) if result.get("preset_version_id") else None,
                "version_resolution_source": result.get("version_resolution_source"),
                "interpretation_band": result["interpretation_band"],
                "review_required": result["review_required"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports",
    response_model=list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportRead],
)
def list_diagnostic_export_diff_gating_compare_preset_reports(
    status_filter: str | None = Query(default=None, alias="status"),
    compare_report_id: uuid.UUID | None = Query(default=None),
    preset_id: uuid.UUID | None = Query(default=None),
    interpretation_band: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportRead]:
    rows = AISystemGovernanceSequenceService(db).list_diagnostic_export_diff_gating_compare_preset_reports(
        organization_id=organization.id,
        status_filter=status_filter,
        compare_report_id=compare_report_id,
        preset_id=preset_id,
        interpretation_band=interpretation_band,
        review_required=review_required,
        limit=limit,
        offset=offset,
    )
    return [_diagnostic_export_diff_gating_compare_preset_report_read(row) for row in rows]


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports/{preset_report_id}",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportRead,
)
def get_diagnostic_export_diff_gating_compare_preset_report(
    preset_report_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportRead:
    row = AISystemGovernanceSequenceService(db).require_diagnostic_export_diff_gating_compare_preset_report(
        organization_id=organization.id,
        preset_report_id=preset_report_id,
    )
    return _diagnostic_export_diff_gating_compare_preset_report_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports/{preset_report_id}/archive",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportRead,
)
def archive_diagnostic_export_diff_gating_compare_preset_report(
    preset_report_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetReportRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_diagnostic_export_diff_gating_compare_preset_report(
        organization_id=organization.id,
        preset_report_id=preset_report_id,
    )
    before = {"status": row.status}
    row = service.archive_diagnostic_export_diff_gating_compare_preset_report(
        row=row,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset_report.archived",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset_report",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_preset_report_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-summary",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetSummary,
)
def diagnostic_export_diff_gating_compare_preset_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetSummary:
    summary = AISystemGovernanceSequenceService(db).diagnostic_export_diff_gating_compare_preset_summary(
        organization_id=organization.id
    )
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetSummary(**summary)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_diagnostic_export_diff_gating_compare_preset_assignment(
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.create_diagnostic_export_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        preset_id=payload.preset_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        scope_json=payload.scope_json,
        priority=payload.priority,
        reason=payload.reason,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment.created",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "preset_id": str(row.preset_id),
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id else None,
            "scope_json": row.scope_json,
            "priority": row.priority,
            "status": row.status,
        },
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_preset_assignment_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments",
    response_model=list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead],
)
def list_diagnostic_export_diff_gating_compare_preset_assignments(
    status_filter: str | None = Query(default=None, alias="status"),
    scope_type: str | None = Query(default=None),
    preset_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead]:
    rows = AISystemGovernanceSequenceService(db).list_diagnostic_export_diff_gating_compare_preset_assignments(
        organization_id=organization.id,
        status_filter=status_filter,
        scope_type=scope_type,
        preset_id=preset_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_diagnostic_export_diff_gating_compare_preset_assignment_read(row) for row in rows]


@router.patch(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/{assignment_id}",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead,
)
def update_diagnostic_export_diff_gating_compare_preset_assignment(
    assignment_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_diagnostic_export_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        assignment_id=assignment_id,
    )
    before = {
        "preset_id": str(row.preset_id),
        "scope_type": row.scope_type,
        "scope_id": str(row.scope_id) if row.scope_id else None,
        "scope_json": row.scope_json,
        "priority": row.priority,
        "status": row.status,
    }
    row = service.update_diagnostic_export_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        row=row,
        updates=payload.model_dump(exclude_unset=True),
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment.updated",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "preset_id": str(row.preset_id),
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id else None,
            "scope_json": row.scope_json,
            "priority": row.priority,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_preset_assignment_read(row)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/{assignment_id}/archive",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead,
)
def archive_diagnostic_export_diff_gating_compare_preset_assignment(
    assignment_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_diagnostic_export_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        assignment_id=assignment_id,
    )
    before = {"status": row.status}
    row = service.archive_diagnostic_export_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        row=row,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment.archived",
        entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _diagnostic_export_diff_gating_compare_preset_assignment_read(row)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/{assignment_id}/history",
    response_model=list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistoryRead],
)
def list_diagnostic_export_diff_gating_compare_preset_assignment_history(
    assignment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistoryRead]:
    service = AISystemGovernanceSequenceService(db)
    service.require_diagnostic_export_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        assignment_id=assignment_id,
    )
    rows = service.list_diagnostic_export_diff_gating_compare_preset_assignment_history(
        organization_id=organization.id,
        assignment_id=assignment_id,
    )
    return [_diagnostic_export_diff_gating_compare_preset_assignment_history_read(row) for row in rows]


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/resolve",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentResolveResponse,
)
def resolve_diagnostic_export_diff_gating_compare_preset_assignment(
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentResolveRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentResolveResponse:
    resolved = AISystemGovernanceSequenceService(db).resolve_diagnostic_export_diff_gating_compare_preset_assignment(
        organization_id=organization.id,
        explicit_preset_id=payload.explicit_preset_id,
        compare_report_id=payload.compare_report_id,
        gating_profile_id=payload.gating_profile_id,
        sequence_pack_id=payload.sequence_pack_id,
        ai_system_ids=payload.ai_system_ids,
        review_types=payload.review_types,
        rollout_class=payload.rollout_class,
        export_type=payload.export_type,
    )
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentResolveResponse(**resolved)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/evaluate-default-preset",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateDefaultResponse,
)
def evaluate_diagnostic_export_diff_gating_compare_preset_default(
    compare_report_id: uuid.UUID,
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateDefaultRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateDefaultResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.evaluate_diagnostic_export_diff_gating_compare_preset_default(
        organization_id=organization.id,
        compare_report_id=compare_report_id,
        explicit_preset_id=payload.explicit_preset_id,
        gating_profile_id=payload.gating_profile_id,
        sequence_pack_id=payload.sequence_pack_id,
        ai_system_ids=payload.ai_system_ids,
        review_types=payload.review_types,
        rollout_class=payload.rollout_class,
        export_type=payload.export_type,
        preset_version_id=payload.preset_version_id,
        version_override_reason=payload.version_override_reason,
        persist_report=payload.persist_report,
        actor_user_id=current_user.id,
    )
    if payload.persist_report and result.get("preset_report_id") is not None:
        preset_resolution = result.get("preset_resolution") if isinstance(result.get("preset_resolution"), dict) else {}
        AuditService(db).write_audit_log(
            action="ai_system_governance_diagnostic_export_diff_gating_compare_preset_report.generated",
            entity_type="ai_system_governance_diagnostic_export_diff_gating_compare_preset_report",
            entity_id=result["preset_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "compare_report_id": str(result["compare_report_id"]),
                "preset_id": str(result["preset_id"]),
                "preset_resolution": {
                    "resolved_preset_id": (
                        str(preset_resolution.get("resolved_preset_id"))
                        if preset_resolution.get("resolved_preset_id")
                        else None
                    ),
                    "resolution_source": preset_resolution.get("resolution_source"),
                    "assignment_id": (
                        str(preset_resolution.get("assignment_id")) if preset_resolution.get("assignment_id") else None
                    ),
                },
                "preset_version_id": str(result["preset_version_id"]) if result.get("preset_version_id") else None,
                "preset_version_number": result.get("preset_version_number"),
                "version_resolution_source": result.get("version_resolution_source"),
                "pinned_version_id": str(result["pinned_version_id"]) if result.get("pinned_version_id") else None,
                "explicit_version_override_used": bool(result.get("explicit_version_override_used", False)),
                "version_override_reason": result.get("version_override_reason"),
                "interpretation_band": result["interpretation_band"],
                "review_required": result["review_required"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetEvaluateDefaultResponse(**result)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/coverage-diagnostics",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsResponse,
)
def diagnostic_export_diff_gating_compare_preset_assignment_coverage_diagnostics(
    payload: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsRequest,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsResponse:
    result = AISystemGovernanceSequenceService(db).diagnostic_export_diff_gating_compare_preset_assignment_coverage_diagnostics(
        organization_id=organization.id,
        contexts=[item.model_dump() for item in payload.contexts],
        include_inactive_assignments=payload.include_inactive_assignments,
        include_archived_assignments=payload.include_archived_assignments,
        include_version_diagnostics=payload.include_version_diagnostics,
    )
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageDiagnosticsResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/health-diagnostics",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHealthDiagnosticsResponse,
)
def diagnostic_export_diff_gating_compare_preset_assignment_health_diagnostics(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHealthDiagnosticsResponse:
    result = AISystemGovernanceSequenceService(db).diagnostic_export_diff_gating_compare_preset_assignment_health_diagnostics(
        organization_id=organization.id
    )
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHealthDiagnosticsResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/coverage-summary",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageSummaryResponse,
)
def diagnostic_export_diff_gating_compare_preset_assignment_coverage_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageSummaryResponse:
    result = AISystemGovernanceSequenceService(db).diagnostic_export_diff_gating_compare_preset_assignment_coverage_summary(
        organization_id=organization.id
    )
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentCoverageSummaryResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments/summary",
    response_model=AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentSummary,
)
def diagnostic_export_diff_gating_compare_preset_assignment_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentSummary:
    summary = AISystemGovernanceSequenceService(db).diagnostic_export_diff_gating_compare_preset_assignment_summary(
        organization_id=organization.id
    )
    return AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentSummary(**summary)


@router.post(
    "/guardrails/policy-resolution/diff-gating-compare-presets/evaluate-default",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetEvaluateDefaultResponse,
)
def evaluate_policy_diff_gating_compare_preset_default(
    payload: AISystemGovernancePolicyDiffGatingComparePresetEvaluateDefaultRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetEvaluateDefaultResponse:
    service = AISystemGovernanceSequenceService(db)
    result = service.evaluate_policy_diff_gating_compare_preset_default(
        organization_id=organization.id,
        explicit_preset_id=payload.explicit_preset_id,
        base_gating_report_id=payload.base_gating_report_id,
        compare_gating_report_id=payload.compare_gating_report_id,
        sequence_pack_id=payload.sequence_pack_id,
        ai_system_ids=payload.ai_system_ids,
        review_types=payload.review_types,
        rollout_class=payload.rollout_class,
        preset_version_id=payload.preset_version_id,
        version_override_reason=payload.version_override_reason,
        persist_report=payload.persist_report,
        persist_compare_report=payload.persist_compare_report,
        actor_user_id=current_user.id,
    )
    if payload.persist_compare_report and result.get("compare_report_id") is not None:
        compare_result = result["compare_result"]
        AuditService(db).write_audit_log(
            action="ai_system_governance_policy_diff_gating_compare.generated",
            entity_type="ai_system_governance_policy_diff_gating_compare_report",
            entity_id=result["compare_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "base_gating_report_id": str(compare_result["base_gating_report_id"]),
                "compare_gating_report_id": str(compare_result["compare_gating_report_id"]),
                "severity_direction": compare_result["severity_direction"],
                "review_required_changed": compare_result["review_required_changed"],
                "reason_code_changes_count": compare_result["reason_code_changes_count"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    if payload.persist_report and result.get("preset_report_id") is not None:
        preset_resolution = result.get("preset_resolution") if isinstance(result.get("preset_resolution"), dict) else {}
        AuditService(db).write_audit_log(
            action="ai_system_governance_policy_diff_gating_compare_preset_report.generated",
            entity_type="ai_system_governance_policy_diff_gating_compare_preset_report",
            entity_id=result["preset_report_id"],
            organization_id=organization.id,
            actor_user_id=current_user.id,
            after_json={
                "preset_id": str(result["preset_id"]),
                "preset_resolution": {
                    "resolved_preset_id": (
                        str(preset_resolution.get("resolved_preset_id"))
                        if preset_resolution.get("resolved_preset_id")
                        else None
                    ),
                    "resolution_source": preset_resolution.get("resolution_source"),
                    "assignment_id": (
                        str(preset_resolution.get("assignment_id")) if preset_resolution.get("assignment_id") else None
                    ),
                },
                "preset_version_id": str(result["preset_version_id"]) if result.get("preset_version_id") else None,
                "preset_version_number": result.get("preset_version_number"),
                "version_resolution_source": result.get("version_resolution_source"),
                "pinned_version_id": str(result["pinned_version_id"]) if result.get("pinned_version_id") else None,
                "explicit_version_override_used": bool(result.get("explicit_version_override_used", False)),
                "version_override_reason": result.get("version_override_reason"),
                "base_gating_report_id": str(result["base_gating_report_id"]),
                "compare_gating_report_id": str(result["compare_gating_report_id"]),
                "compare_report_id": str(result["compare_report_id"]) if result.get("compare_report_id") else None,
                "interpretation_band": result["interpretation_band"],
                "review_required": result["review_required"],
            },
            metadata_json={"source": "api"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    if payload.persist_compare_report or payload.persist_report:
        db.commit()
    return AISystemGovernancePolicyDiffGatingComparePresetEvaluateDefaultResponse(**result)


@router.get(
    "/guardrails/policy-resolution/diff-gating-compare-preset-assignments/summary",
    response_model=AISystemGovernancePolicyDiffGatingComparePresetAssignmentSummary,
)
def policy_diff_gating_compare_preset_assignment_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentSummary:
    summary = AISystemGovernanceSequenceService(db).policy_diff_gating_compare_preset_assignment_summary(
        organization_id=organization.id
    )
    return AISystemGovernancePolicyDiffGatingComparePresetAssignmentSummary(**summary)


@router.get(
    "/guardrails/policy-assignments/summary",
    response_model=AISystemGovernanceGuardrailPolicyAssignmentSummary,
)
def guardrail_policy_assignment_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceGuardrailPolicyAssignmentSummary:
    summary = AISystemGovernanceSequenceService(db).policy_assignment_summary(organization_id=organization.id)
    return AISystemGovernanceGuardrailPolicyAssignmentSummary(**summary)


@router.patch(
    "/guardrails/policy-assignments/{assignment_id}",
    response_model=AISystemGovernanceGuardrailPolicyAssignmentRead,
)
def update_guardrail_policy_assignment(
    assignment_id: uuid.UUID,
    payload: AISystemGovernanceGuardrailPolicyAssignmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceGuardrailPolicyAssignmentRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_assignment(organization_id=organization.id, assignment_id=assignment_id)
    before = {
        "policy_set_id": str(row.policy_set_id),
        "scope_type": row.scope_type,
        "scope_id": str(row.scope_id) if row.scope_id else None,
        "priority": row.priority,
        "status": row.status,
    }
    update_data = payload.model_dump(exclude_unset=True)
    row = service.update_policy_assignment(
        organization_id=organization.id,
        row=row,
        updates=update_data,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_guardrail_policy_assignment.updated",
        entity_type="ai_system_governance_guardrail_policy_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "policy_set_id": str(row.policy_set_id),
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id else None,
            "priority": row.priority,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_assignment_read(row)


@router.post(
    "/guardrails/policy-assignments/{assignment_id}/archive",
    response_model=AISystemGovernanceGuardrailPolicyAssignmentRead,
)
def archive_guardrail_policy_assignment(
    assignment_id: uuid.UUID,
    payload: AISystemGovernanceGuardrailPolicyAssignmentArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceGuardrailPolicyAssignmentRead:
    service = AISystemGovernanceSequenceService(db)
    row = service.require_policy_assignment(organization_id=organization.id, assignment_id=assignment_id)
    before = {"status": row.status}
    row = service.archive_policy_assignment(
        organization_id=organization.id,
        row=row,
        reason=payload.reason,
        actor_user_id=current_user.id,
    )
    AuditService(db).write_audit_log(
        action="ai_system_governance_guardrail_policy_assignment.archived",
        entity_type="ai_system_governance_guardrail_policy_assignment",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api", "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _policy_assignment_read(row)


@router.get(
    "/guardrails/policy-assignments/{assignment_id}/history",
    response_model=list[AISystemGovernanceGuardrailPolicyAssignmentHistoryRead],
)
def list_guardrail_policy_assignment_history(
    assignment_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceGuardrailPolicyAssignmentHistoryRead]:
    service = AISystemGovernanceSequenceService(db)
    service.require_policy_assignment(organization_id=organization.id, assignment_id=assignment_id)
    rows = service.list_policy_assignment_history(organization_id=organization.id, assignment_id=assignment_id)
    return [_policy_assignment_history_read(row) for row in rows]


@router.post(
    "/review-reminder-policies",
    response_model=AISystemGovernanceReviewReminderPolicyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_review_reminder_policy(
    payload: AISystemGovernanceReviewReminderPolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> AISystemGovernanceReviewReminderPolicyRead:
    _require_ai_systems_write_or_admin(db, user_id=current_user.id, organization_id=organization.id)
    service = AISystemGovernanceScheduleService(db)
    row = service.create_reminder_policy(
        organization_id=organization.id,
        name=payload.name,
        review_type=payload.review_type,
        days_before_due=payload.days_before_due,
        overdue_after_days=payload.overdue_after_days,
        escalation_after_days=payload.escalation_after_days,
        notify_assignee=payload.notify_assignee,
        status_value=payload.status,
        actor_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="ai_system_governance_review_reminder_policy.created",
        entity_type="ai_system_governance_review_reminder_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json={
            "name": row.name,
            "review_type": row.review_type,
            "status": row.status,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.get("/review-reminder-policies", response_model=list[AISystemGovernanceReviewReminderPolicyRead])
def list_review_reminder_policies(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceReviewReminderPolicyRead]:
    rows = AISystemGovernanceScheduleService(db).list_reminder_policies(organization_id=organization.id)
    return [_policy_read(row) for row in rows]


@router.patch("/review-reminder-policies/{policy_id}", response_model=AISystemGovernanceReviewReminderPolicyRead)
def update_review_reminder_policy(
    policy_id: uuid.UUID,
    payload: AISystemGovernanceReviewReminderPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> AISystemGovernanceReviewReminderPolicyRead:
    _require_ai_systems_write_or_admin(db, user_id=current_user.id, organization_id=organization.id)
    service = AISystemGovernanceScheduleService(db)
    row = service.require_reminder_policy(organization_id=organization.id, policy_id=policy_id)
    before = {
        "name": row.name,
        "status": row.status,
        "days_before_due": row.days_before_due,
        "overdue_after_days": row.overdue_after_days,
        "escalation_after_days": row.escalation_after_days,
    }
    row = service.update_reminder_policy(
        row=row,
        name=payload.name,
        review_type=payload.review_type,
        days_before_due=payload.days_before_due,
        overdue_after_days=payload.overdue_after_days,
        escalation_after_days=payload.escalation_after_days,
        notify_assignee=payload.notify_assignee,
        status_value=payload.status,
    )

    AuditService(db).write_audit_log(
        action="ai_system_governance_review_reminder_policy.updated",
        entity_type="ai_system_governance_review_reminder_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={
            "name": row.name,
            "status": row.status,
            "days_before_due": row.days_before_due,
            "overdue_after_days": row.overdue_after_days,
            "escalation_after_days": row.escalation_after_days,
        },
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.post("/review-reminder-policies/{policy_id}/archive", response_model=AISystemGovernanceReviewReminderPolicyRead)
def archive_review_reminder_policy(
    policy_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
) -> AISystemGovernanceReviewReminderPolicyRead:
    _require_ai_systems_write_or_admin(db, user_id=current_user.id, organization_id=organization.id)
    service = AISystemGovernanceScheduleService(db)
    row = service.require_reminder_policy(organization_id=organization.id, policy_id=policy_id)
    before = {"status": row.status}
    row = service.archive_reminder_policy(row=row)

    AuditService(db).write_audit_log(
        action="ai_system_governance_review_reminder_policy.archived",
        entity_type="ai_system_governance_review_reminder_policy",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status},
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(row)
    return _policy_read(row)


@router.get("/review-queue", response_model=list[AISystemGovernanceReviewQueueItem])
def due_review_queue(
    status_filter: str | None = Query(default=None, alias="status"),
    review_type: str | None = Query(default=None),
    overdue_only: bool = Query(default=False),
    due_before: str | None = Query(default=None),
    assigned_to_user_id: uuid.UUID | None = Query(default=None),
    ai_system_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceReviewQueueItem]:
    due_before_dt = None
    if due_before:
        try:
            due_before_dt = datetime.fromisoformat(due_before.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="due_before must be an ISO datetime") from exc

    rows = AISystemGovernanceScheduleService(db).queue_items(
        organization_id=organization.id,
        status_filter=status_filter,
        review_type=review_type,
        overdue_only=overdue_only,
        due_before=due_before_dt,
        assigned_to_user_id=assigned_to_user_id,
        ai_system_id=ai_system_id,
        limit=limit,
        offset=offset,
    )
    return [AISystemGovernanceReviewQueueItem(**row) for row in rows]


@router.post("/review-queue/evaluate-schedules", response_model=AISystemGovernanceReviewScheduleEvaluateResponse)
def evaluate_review_schedules(
    payload: AISystemGovernanceReviewScheduleEvaluateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewScheduleEvaluateResponse:
    service = AISystemGovernanceScheduleService(db)
    result = service.evaluate_schedules(
        organization_id=organization.id,
        dry_run=payload.dry_run,
        notify=payload.notify,
        actor_user_id=current_user.id,
    )

    AuditService(db).write_audit_log(
        action="ai_system_governance_review_schedule.evaluated",
        entity_type="ai_system_governance_review_schedule",
        organization_id=organization.id,
        actor_user_id=current_user.id,
        after_json=result,
        metadata_json={"source": "api"},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    return AISystemGovernanceReviewScheduleEvaluateResponse(**result)


@router.get("/review-events", response_model=list[AISystemGovernanceReviewEventRead])
def list_review_events(
    event_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    review_id: uuid.UUID | None = Query(default=None),
    ai_system_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> list[AISystemGovernanceReviewEventRead]:
    rows = AISystemGovernanceScheduleService(db).list_events(
        organization_id=organization.id,
        event_type=event_type,
        status_filter=status_filter,
        review_id=review_id,
        ai_system_id=ai_system_id,
        limit=limit,
        offset=offset,
    )
    return [_event_read(row) for row in rows]


@router.post("/review-events/{event_id}/resolve", response_model=AISystemGovernanceReviewEventRead)
def resolve_review_event(
    event_id: uuid.UUID,
    payload: AISystemGovernanceReviewEventResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:write")),
) -> AISystemGovernanceReviewEventRead:
    service = AISystemGovernanceScheduleService(db)
    row = service.require_event(organization_id=organization.id, event_id=event_id)
    before = {"status": row.status, "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None}
    row = service.resolve_event(
        row=row,
        actor_user_id=current_user.id,
        resolution_notes=payload.resolution_notes,
    )

    AuditService(db).write_audit_log(
        action="ai_system_governance_review_event.resolved",
        entity_type="ai_system_governance_review_event",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=current_user.id,
        before_json=before,
        after_json={"status": row.status, "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None},
        metadata_json={"source": "api", "resolution_notes": payload.resolution_notes},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(row)
    return _event_read(row)


@router.get("/review-schedule-summary", response_model=AISystemGovernanceReviewScheduleSummary)
def review_schedule_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ai_systems:read")),
) -> AISystemGovernanceReviewScheduleSummary:
    summary = AISystemGovernanceScheduleService(db).schedule_summary(organization_id=organization.id)
    return AISystemGovernanceReviewScheduleSummary(**summary)
