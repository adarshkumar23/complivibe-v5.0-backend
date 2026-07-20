import hashlib
import hmac
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.ai_system import AISystem
from app.models.ai_system_governance_freeze_window import AISystemGovernanceFreezeWindow
from app.models.ai_system_governance_guardrail_policy_assignment import AISystemGovernanceGuardrailPolicyAssignment
from app.models.ai_system_governance_guardrail_policy_assignment_history import (
    AISystemGovernanceGuardrailPolicyAssignmentHistory,
)
from app.models.ai_system_governance_guardrail_policy_set import AISystemGovernanceGuardrailPolicySet
from app.models.ai_system_governance_guardrail_policy_set_version import AISystemGovernanceGuardrailPolicySetVersion
from app.models.ai_system_governance_operator_acknowledgement import AISystemGovernanceOperatorAcknowledgement
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
from app.models.ai_system_governance_policy_resolution_simulation_report import (
    AISystemGovernancePolicyResolutionSimulationReport,
)
from app.models.organization_internal_signing_key import OrganizationInternalSigningKey
from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.ai_system_governance_review_plan_constraint import AISystemGovernanceReviewPlanConstraint
from app.models.ai_system_governance_review_recurrence_template import AISystemGovernanceReviewRecurrenceTemplate
from app.models.ai_system_governance_review_reminder_policy import AISystemGovernanceReviewReminderPolicy
from app.models.ai_system_governance_review_sequence_pack import AISystemGovernanceReviewSequencePack
from app.models.ai_system_governance_review_sequence_run import AISystemGovernanceReviewSequenceRun
from app.models.ai_system_governance_review_sequence_step import AISystemGovernanceReviewSequenceStep
from app.services.ai_system_service import AISystemService

SEQUENCE_CAVEAT = (
    "Sequence-pack generation is manually triggered. CompliVibe does not autonomously create, start, "
    "approve, or complete AI governance reviews."
)
GUARDRAIL_CAVEAT = (
    "Governance guardrails are deterministic operator controls. They do not autonomously create, start, "
    "approve, or complete AI governance reviews."
)
GUARDRAIL_POLICY_CAVEAT = (
    "Guardrail policy profiles are deterministic configuration records. They do not autonomously execute, "
    "approve, or complete AI governance work."
)
GUARDRAIL_POLICY_ASSIGNMENT_CAVEAT = (
    "Guardrail policy assignments are deterministic defaults. Explicit operator-selected policy profiles take "
    "precedence. These mappings do not autonomously execute, approve, or complete AI governance work."
)
POLICY_RESOLUTION_SIMULATION_CAVEAT = (
    "Policy resolution simulations are read-only planning reports. They do not create reviews, sequence runs, "
    "acknowledgements, or policy changes."
)
POLICY_RESOLUTION_SIMULATION_DIFF_CAVEAT = (
    "Simulation report diffs are deterministic comparison reports. They do not create reviews, sequence runs, "
    "acknowledgements, freeze windows, policy assignments, or policy changes."
)
POLICY_RESOLUTION_SIMULATION_DIFF_REASON_CODE_CAVEAT = (
    "Diff reason codes are deterministic labels for review and change-control workflows. "
    "They do not trigger automation or mutate governance records."
)
POLICY_DIFF_GATING_CAVEAT = (
    "Policy-diff gating is read-only classification for human review. It does not approve, reject, "
    "create tasks, create reviews, or trigger automation."
)
POLICY_DIFF_GATING_COMPARE_CAVEAT = (
    "Gating compare reports are read-only drift reports for human review. "
    "They do not approve, reject, create tasks, create reviews, or trigger automation."
)
POLICY_DIFF_GATING_COMPARE_PRESET_CAVEAT = (
    "Gating compare presets are deterministic interpretation configurations for human review. "
    "They do not approve, reject, create tasks, create reviews, or trigger automation."
)
POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_CAVEAT = (
    "Preset versions are immutable interpretation snapshots for human review. "
    "They do not approve, reject, create tasks, create reviews, or trigger automation."
)
POLICY_DIFF_GATING_COMPARE_PRESET_PINNING_CAVEAT = (
    "Preset version pinning controls deterministic interpretation snapshots for human review. "
    "It does not approve, reject, create tasks, create reviews, or trigger automation."
)
POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_CAVEAT = (
    "Gating compare preset assignments are deterministic defaults for human review interpretation. "
    "Explicit operator-selected presets take precedence. These mappings do not approve, reject, "
    "create tasks, create reviews, or trigger automation."
)
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_CAVEAT = (
    "Diagnostic export-diff gating compare preset assignments are deterministic defaults for human review "
    "interpretation. Explicit operator-selected presets take precedence. These mappings do not approve, "
    "reject, create tasks, create reviews, or trigger automation."
)
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT = (
    "Diagnostic export-diff gating compare preset assignment diagnostics are read-only operator visibility checks. "
    "They do not approve, reject, create tasks, create reviews, or trigger automation."
)
POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT = (
    "Preset assignment diagnostics are read-only operator visibility checks. "
    "They do not approve, reject, create tasks, create reviews, or trigger automation."
)
POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_REPORTS_CAVEAT = (
    "Persisted diagnostics reports are immutable operator visibility snapshots. "
    "They do not approve, reject, create tasks, create reviews, mutate assignments, or trigger automation."
)
POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_CAVEAT = (
    "This export uses an internal CompliVibe integrity signature. "
    "It is not a legal e-signature, external audit attestation, or certification."
)
POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_VERIFY_CAVEAT = (
    "This endpoint verifies an internal CompliVibe export integrity signature. "
    "It is not a legal e-signature validation, external audit attestation, or certification."
)
POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_DIFF_CAVEAT = (
    "Diagnostic export diffs are deterministic JSON comparison records. "
    "They do not mutate exports, revoke exports, create files, create reviews, or trigger automation."
)
POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_DIFF_REASON_CODE_CAVEAT = (
    "Diagnostic export diff reason codes are deterministic labels for human review and change-control workflows. "
    "They do not trigger automation or mutate governance records."
)
DIAGNOSTIC_EXPORT_DIFF_GATING_CAVEAT = (
    "Diagnostic export-diff gating is read-only classification for human review. "
    "It does not approve, reject, create tasks, create reviews, mutate exports, or trigger automation."
)
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_CAVEAT = (
    "Diagnostic export-diff gating compare is a read-only baseline comparison for human review. "
    "It does not approve, reject, create tasks, create reviews, mutate gating reports, or trigger automation."
)
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_CAVEAT = (
    "Diagnostic export-diff gating compare presets are deterministic interpretation helpers for human review. "
    "They do not approve, reject, create tasks, create reviews, mutate compare reports, or trigger automation."
)
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_VERSION_CAVEAT = (
    "Preset versions are immutable interpretation snapshots for human review. "
    "They do not approve, reject, create tasks, create reviews, mutate compare reports, or trigger automation."
)
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_PINNING_CAVEAT = (
    "Preset versions and pinning control deterministic interpretation snapshots for human review. "
    "They do not approve, reject, create tasks, create reviews, mutate compare reports, or trigger automation."
)
POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_PURPOSE = "preset_assignment_diagnostic_export"
POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_SIGNATURE_ALGORITHM = "HMAC-SHA256"
DIAGNOSTIC_EXPORT_VALIDITY_DAYS = 365
PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_DIFF_REASON_CODE_CATALOG: list[dict[str, str]] = [
    {
        "code": "BASE_EXPORT_SIGNATURE_INVALID",
        "category": "signature",
        "description": "The base export signature verification failed.",
        "severity_hint": "critical",
    },
    {
        "code": "BASE_EXPORT_UNTRUSTED",
        "category": "trust",
        "description": "The base export is currently untrusted.",
        "severity_hint": "warning",
    },
    {
        "code": "COMPARE_EXPORT_SIGNATURE_INVALID",
        "category": "signature",
        "description": "The compare export signature verification failed.",
        "severity_hint": "critical",
    },
    {
        "code": "COMPARE_EXPORT_UNTRUSTED",
        "category": "trust",
        "description": "The compare export is currently untrusted.",
        "severity_hint": "warning",
    },
    {
        "code": "EXPORT_PATH_ADDED",
        "category": "path",
        "description": "A JSON path exists only in the compare export payload.",
        "severity_hint": "warning",
    },
    {
        "code": "EXPORT_PATH_CHANGED",
        "category": "path",
        "description": "A JSON path value changed between base and compare payloads.",
        "severity_hint": "warning",
    },
    {
        "code": "EXPORT_PATH_REMOVED",
        "category": "path",
        "description": "A JSON path exists only in the base export payload.",
        "severity_hint": "warning",
    },
    {
        "code": "EXPORT_PATH_UNCHANGED",
        "category": "path",
        "description": "A shared JSON path value remained unchanged between payloads.",
        "severity_hint": "info",
    },
    {
        "code": "EXPORT_PAYLOAD_HASH_CHANGED",
        "category": "hash",
        "description": "The canonical payload SHA-256 value changed between exports.",
        "severity_hint": "warning",
    },
    {
        "code": "EXPORT_PAYLOAD_HASH_UNCHANGED",
        "category": "hash",
        "description": "The canonical payload SHA-256 value is unchanged between exports.",
        "severity_hint": "info",
    },
    {
        "code": "EXPORT_SOURCE_DIFF_REPORT_CHANGED",
        "category": "source",
        "description": "The source diagnostic diff report identifier changed.",
        "severity_hint": "info",
    },
    {
        "code": "EXPORT_SOURCE_REPORT_CHANGED",
        "category": "source",
        "description": "The source diagnostic report identifier changed.",
        "severity_hint": "info",
    },
    {
        "code": "EXPORT_TYPE_MATCHED",
        "category": "source",
        "description": "Both compared exports share the same export type.",
        "severity_hint": "info",
    },
    {
        "code": "SOURCE_EXPORT_REVOKED",
        "category": "trust",
        "description": "At least one source export is revoked.",
        "severity_hint": "critical",
    },
]
POLICY_RESOLUTION_SIMULATION_DIFF_REASON_CODE_CATALOG: list[dict[str, str]] = [
    {
        "code": "BLOCKED_STATUS_DECREASED",
        "category": "aggregate",
        "description": "The number of blocked contexts decreased versus the base report.",
        "severity_hint": "warning",
    },
    {
        "code": "BLOCKED_STATUS_INCREASED",
        "category": "aggregate",
        "description": "The number of blocked contexts increased versus the base report.",
        "severity_hint": "critical",
    },
    {
        "code": "CONTEXT_ADDED",
        "category": "context",
        "description": "A context exists only in the compare report.",
        "severity_hint": "warning",
    },
    {
        "code": "CONTEXT_CHANGED",
        "category": "context",
        "description": "A matched context has at least one policy or guardrail change.",
        "severity_hint": "warning",
    },
    {
        "code": "CONTEXT_REMOVED",
        "category": "context",
        "description": "A context exists only in the base report.",
        "severity_hint": "warning",
    },
    {
        "code": "CONTEXT_UNCHANGED",
        "category": "context",
        "description": "A matched context has no policy or guardrail changes.",
        "severity_hint": "info",
    },
    {
        "code": "ENFORCEMENT_LEVEL_CHANGED",
        "category": "guardrail_resolution",
        "description": "Guardrail enforcement level changed for the context.",
        "severity_hint": "warning",
    },
    {
        "code": "GUARDRAIL_BLOCKED_CHANGED",
        "category": "guardrail_resolution",
        "description": "Guardrail blocked status changed for the context.",
        "severity_hint": "critical",
    },
    {
        "code": "GUARDRAIL_INFO_CHANGED",
        "category": "guardrail_resolution",
        "description": "Guardrail informational messages changed for the context.",
        "severity_hint": "info",
    },
    {
        "code": "GUARDRAIL_WARNINGS_CHANGED",
        "category": "guardrail_resolution",
        "description": "Guardrail warning messages changed for the context.",
        "severity_hint": "warning",
    },
    {
        "code": "MATCHING_WINDOW_COUNT_CHANGED",
        "category": "guardrail_resolution",
        "description": "The number of matching guardrail windows changed for the context.",
        "severity_hint": "info",
    },
    {
        "code": "NO_POLICY_STATUS_DECREASED",
        "category": "aggregate",
        "description": "The number of contexts without a resolved policy decreased.",
        "severity_hint": "info",
    },
    {
        "code": "NO_POLICY_STATUS_INCREASED",
        "category": "aggregate",
        "description": "The number of contexts without a resolved policy increased.",
        "severity_hint": "warning",
    },
    {
        "code": "OVERRIDE_ALLOWED_CHANGED",
        "category": "guardrail_resolution",
        "description": "Guardrail override allowance changed for the context.",
        "severity_hint": "critical",
    },
    {
        "code": "POLICY_ASSIGNMENT_CHANGED",
        "category": "policy_resolution",
        "description": "Resolved policy assignment mapping changed for the context.",
        "severity_hint": "warning",
    },
    {
        "code": "POLICY_PRECEDENCE_TRACE_CHANGED",
        "category": "policy_resolution",
        "description": "Policy precedence trace changed for the context.",
        "severity_hint": "info",
    },
    {
        "code": "POLICY_RESOLUTION_SOURCE_CHANGED",
        "category": "policy_resolution",
        "description": "Policy resolution source changed for the context.",
        "severity_hint": "warning",
    },
    {
        "code": "POLICY_SET_CHANGED",
        "category": "policy_resolution",
        "description": "Resolved policy set changed for the context.",
        "severity_hint": "warning",
    },
    {
        "code": "POLICY_VERSION_CHANGED",
        "category": "policy_resolution",
        "description": "Resolved policy version changed for the context.",
        "severity_hint": "warning",
    },
    {
        "code": "PRIMARY_BLOCKING_WINDOW_CHANGED",
        "category": "guardrail_resolution",
        "description": "Primary blocking freeze window changed for the context.",
        "severity_hint": "warning",
    },
    {
        "code": "WARNING_STATUS_DECREASED",
        "category": "aggregate",
        "description": "The number of warning contexts decreased versus the base report.",
        "severity_hint": "info",
    },
    {
        "code": "WARNING_STATUS_INCREASED",
        "category": "aggregate",
        "description": "The number of warning contexts increased versus the base report.",
        "severity_hint": "warning",
    },
]
FREEZE_ACK_TEXT = "CONFIRM_SEQUENCE_APPLY_DURING_FREEZE"
REVIEW_TYPES = {
    "initial_review",
    "pre_production_review",
    "periodic_review",
    "change_review",
    "retirement_review",
}
SCOPE_SPECIFICITY = {
    "all_ai_governance": 1,
    "review_type": 2,
    "sequence_pack": 3,
    "ai_system": 4,
}
KNOWN_SCOPE_ORDER = ["ai_system", "sequence_pack", "review_type", "all_ai_governance"]
POLICY_ASSIGNMENT_SCOPE_PRECEDENCE: list[tuple[str, str]] = [
    ("sequence_pack", "mapped_sequence_pack"),
    ("ai_system", "mapped_ai_system"),
    ("review_type", "mapped_review_type"),
    ("rollout_class", "mapped_rollout_class"),
    ("all_ai_governance", "mapped_all_ai_governance"),
]
POLICY_DIFF_GATING_SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]
POLICY_DIFF_GATING_INTERPRETATION_BANDS = ["stable", "attention", "review_required", "critical_review"]
POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODES = {
    "active_then_mutable",
    "pinned_preferred",
    "pinned_required",
}
POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_SCOPE_PRECEDENCE: list[tuple[str, str]] = [
    ("sequence_pack", "mapped_sequence_pack"),
    ("ai_system", "mapped_ai_system"),
    ("review_type", "mapped_review_type"),
    ("rollout_class", "mapped_rollout_class"),
    ("all_ai_governance", "mapped_all_ai_governance"),
]
DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_SCOPE_PRECEDENCE: list[tuple[str, str]] = [
    ("diagnostic_export_diff_gating_compare_report", "mapped_diagnostic_export_diff_gating_compare_report"),
    ("diagnostic_export_diff_gating_profile", "mapped_diagnostic_export_diff_gating_profile"),
    ("sequence_pack", "mapped_sequence_pack"),
    ("ai_system", "mapped_ai_system"),
    ("review_type", "mapped_review_type"),
    ("rollout_class", "mapped_rollout_class"),
    ("export_type", "mapped_export_type"),
    ("all_ai_governance", "mapped_all_ai_governance"),
]


class AISystemGovernanceSequenceService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @classmethod
    def json_safe(cls, value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, datetime):
            return cls.ensure_utc(value).isoformat()
        if isinstance(value, list):
            return [cls.json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): cls.json_safe(item) for key, item in value.items()}
        return value

    @staticmethod
    def canonical_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @classmethod
    def canonical_sha256(cls, payload: dict[str, Any]) -> str:
        return hashlib.sha256(cls.canonical_json(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def as_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return cls.ensure_utc(value)

    @classmethod
    def normalize_start_from(cls, value: datetime | date | None) -> datetime:
        if value is None:
            now = cls.now()
            return datetime(now.year, now.month, now.day, tzinfo=UTC)
        if isinstance(value, datetime):
            return cls.ensure_utc(value)
        return datetime(value.year, value.month, value.day, tzinfo=UTC)

    def require_pack(self, *, organization_id: uuid.UUID, pack_id: uuid.UUID) -> AISystemGovernanceReviewSequencePack:
        row = self.db.execute(
            select(AISystemGovernanceReviewSequencePack).where(
                AISystemGovernanceReviewSequencePack.id == pack_id,
                AISystemGovernanceReviewSequencePack.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance review sequence pack not found")
        return row

    def require_step(
        self,
        *,
        organization_id: uuid.UUID,
        pack_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> AISystemGovernanceReviewSequenceStep:
        row = self.db.execute(
            select(AISystemGovernanceReviewSequenceStep).where(
                AISystemGovernanceReviewSequenceStep.id == step_id,
                AISystemGovernanceReviewSequenceStep.organization_id == organization_id,
                AISystemGovernanceReviewSequenceStep.sequence_pack_id == pack_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance review sequence step not found")
        return row

    def require_run(self, *, organization_id: uuid.UUID, run_id: uuid.UUID) -> AISystemGovernanceReviewSequenceRun:
        row = self.db.execute(
            select(AISystemGovernanceReviewSequenceRun).where(
                AISystemGovernanceReviewSequenceRun.id == run_id,
                AISystemGovernanceReviewSequenceRun.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance review sequence run not found")
        return row

    def require_freeze_window(
        self,
        *,
        organization_id: uuid.UUID,
        freeze_window_id: uuid.UUID,
    ) -> AISystemGovernanceFreezeWindow:
        row = self.db.execute(
            select(AISystemGovernanceFreezeWindow).where(
                AISystemGovernanceFreezeWindow.id == freeze_window_id,
                AISystemGovernanceFreezeWindow.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance freeze window not found")
        return row

    def require_policy_set(
        self,
        *,
        organization_id: uuid.UUID,
        policy_set_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicySet:
        row = self.db.execute(
            select(AISystemGovernanceGuardrailPolicySet).where(
                AISystemGovernanceGuardrailPolicySet.id == policy_set_id,
                AISystemGovernanceGuardrailPolicySet.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardrail policy set not found")
        return row

    def require_policy_version(
        self,
        *,
        organization_id: uuid.UUID,
        policy_set_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicySetVersion:
        row = self.db.execute(
            select(AISystemGovernanceGuardrailPolicySetVersion).where(
                AISystemGovernanceGuardrailPolicySetVersion.id == version_id,
                AISystemGovernanceGuardrailPolicySetVersion.organization_id == organization_id,
                AISystemGovernanceGuardrailPolicySetVersion.policy_set_id == policy_set_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardrail policy set version not found")
        return row

    def require_policy_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicyAssignment:
        row = self.db.execute(
            select(AISystemGovernanceGuardrailPolicyAssignment).where(
                AISystemGovernanceGuardrailPolicyAssignment.id == assignment_id,
                AISystemGovernanceGuardrailPolicyAssignment.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardrail policy assignment not found")
        return row

    def require_simulation_report(
        self,
        *,
        organization_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> AISystemGovernancePolicyResolutionSimulationReport:
        row = self.db.execute(
            select(AISystemGovernancePolicyResolutionSimulationReport).where(
                AISystemGovernancePolicyResolutionSimulationReport.id == report_id,
                AISystemGovernancePolicyResolutionSimulationReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy resolution simulation report not found")
        return row

    def require_simulation_diff_report(
        self,
        *,
        organization_id: uuid.UUID,
        diff_report_id: uuid.UUID,
    ) -> AISystemGovernancePolicyResolutionSimulationDiffReport:
        row = self.db.execute(
            select(AISystemGovernancePolicyResolutionSimulationDiffReport).where(
                AISystemGovernancePolicyResolutionSimulationDiffReport.id == diff_report_id,
                AISystemGovernancePolicyResolutionSimulationDiffReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy resolution simulation diff report not found")
        return row

    def require_policy_diff_gating_profile(
        self,
        *,
        organization_id: uuid.UUID,
        profile_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingProfile:
        row = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingProfile).where(
                AISystemGovernancePolicyDiffGatingProfile.id == profile_id,
                AISystemGovernancePolicyDiffGatingProfile.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy diff gating profile not found")
        return row

    def require_policy_diff_gating_report(
        self,
        *,
        organization_id: uuid.UUID,
        gating_report_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingReport:
        row = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingReport).where(
                AISystemGovernancePolicyDiffGatingReport.id == gating_report_id,
                AISystemGovernancePolicyDiffGatingReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy diff gating report not found")
        return row

    def require_diagnostic_export_diff_gating_profile(
        self,
        *,
        organization_id: uuid.UUID,
        profile_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingProfile:
        row = self.db.execute(
            select(AISystemGovernanceDiagnosticExportDiffGatingProfile).where(
                AISystemGovernanceDiagnosticExportDiffGatingProfile.id == profile_id,
                AISystemGovernanceDiagnosticExportDiffGatingProfile.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic export diff gating profile not found")
        return row

    def require_diagnostic_export_diff_gating_report(
        self,
        *,
        organization_id: uuid.UUID,
        gating_report_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingReport:
        row = self.db.execute(
            select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
                AISystemGovernanceDiagnosticExportDiffGatingReport.id == gating_report_id,
                AISystemGovernanceDiagnosticExportDiffGatingReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic export diff gating report not found")
        return row

    def require_diagnostic_export_diff_gating_compare_report(
        self,
        *,
        organization_id: uuid.UUID,
        compare_report_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingCompareReport:
        row = self.db.execute(
            select(AISystemGovernanceDiagnosticExportDiffGatingCompareReport).where(
                AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id == compare_report_id,
                AISystemGovernanceDiagnosticExportDiffGatingCompareReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic export diff gating compare report not found",
            )
        return row

    def require_diagnostic_export_diff_gating_compare_preset(
        self,
        *,
        organization_id: uuid.UUID,
        preset_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePreset:
        row = self.db.execute(
            select(AISystemGovernanceDiagnosticExportDiffGatingComparePreset).where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id == preset_id,
                AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic export diff gating compare preset not found",
            )
        return row

    def require_diagnostic_export_diff_gating_compare_preset_report(
        self,
        *,
        organization_id: uuid.UUID,
        preset_report_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport:
        row = self.db.execute(
            select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport).where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.id == preset_report_id,
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic export diff gating compare preset report not found",
            )
        return row

    def require_diagnostic_export_diff_gating_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment:
        row = self.db.execute(
            select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment).where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id == assignment_id,
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic export diff gating compare preset assignment not found",
            )
        return row

    def require_diagnostic_export_diff_gating_compare_preset_version(
        self,
        *,
        organization_id: uuid.UUID,
        preset_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion:
        row = self.db.execute(
            select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion).where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.id == version_id,
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.organization_id == organization_id,
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.preset_id == preset_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Diagnostic export diff gating compare preset version not found",
            )
        return row

    def require_policy_diff_gating_compare_report(
        self,
        *,
        organization_id: uuid.UUID,
        compare_report_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingCompareReport:
        row = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingCompareReport).where(
                AISystemGovernancePolicyDiffGatingCompareReport.id == compare_report_id,
                AISystemGovernancePolicyDiffGatingCompareReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy diff gating compare report not found")
        return row

    def require_policy_diff_gating_compare_preset(
        self,
        *,
        organization_id: uuid.UUID,
        preset_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePreset:
        row = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingComparePreset).where(
                AISystemGovernancePolicyDiffGatingComparePreset.id == preset_id,
                AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy diff gating compare preset not found")
        return row

    def require_policy_diff_gating_compare_preset_report(
        self,
        *,
        organization_id: uuid.UUID,
        preset_report_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetReport:
        row = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingComparePresetReport).where(
                AISystemGovernancePolicyDiffGatingComparePresetReport.id == preset_report_id,
                AISystemGovernancePolicyDiffGatingComparePresetReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy diff gating compare preset report not found",
            )
        return row

    def require_policy_diff_gating_compare_preset_version(
        self,
        *,
        organization_id: uuid.UUID,
        preset_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetVersion:
        row = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingComparePresetVersion).where(
                AISystemGovernancePolicyDiffGatingComparePresetVersion.id == version_id,
                AISystemGovernancePolicyDiffGatingComparePresetVersion.organization_id == organization_id,
                AISystemGovernancePolicyDiffGatingComparePresetVersion.preset_id == preset_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy diff gating compare preset version not found",
            )
        return row

    def require_policy_diff_gating_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetAssignment:
        row = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingComparePresetAssignment).where(
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.id == assignment_id,
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Policy diff gating compare preset assignment not found",
            )
        return row

    def require_preset_assignment_diagnostic_report(
        self,
        *,
        organization_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> AISystemGovernancePresetAssignmentDiagnosticReport:
        row = self.db.execute(
            select(AISystemGovernancePresetAssignmentDiagnosticReport).where(
                AISystemGovernancePresetAssignmentDiagnosticReport.id == report_id,
                AISystemGovernancePresetAssignmentDiagnosticReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preset assignment diagnostic report not found",
            )
        return row

    def require_preset_assignment_diagnostic_diff_report(
        self,
        *,
        organization_id: uuid.UUID,
        diff_report_id: uuid.UUID,
    ) -> AISystemGovernancePresetAssignmentDiagnosticDiffReport:
        row = self.db.execute(
            select(AISystemGovernancePresetAssignmentDiagnosticDiffReport).where(
                AISystemGovernancePresetAssignmentDiagnosticDiffReport.id == diff_report_id,
                AISystemGovernancePresetAssignmentDiagnosticDiffReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preset assignment diagnostic diff report not found",
            )
        return row

    def require_preset_assignment_diagnostic_export(
        self,
        *,
        organization_id: uuid.UUID,
        export_id: uuid.UUID,
    ) -> AISystemGovernancePresetAssignmentDiagnosticExport:
        row = self.db.execute(
            select(AISystemGovernancePresetAssignmentDiagnosticExport).where(
                AISystemGovernancePresetAssignmentDiagnosticExport.id == export_id,
                AISystemGovernancePresetAssignmentDiagnosticExport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preset assignment diagnostic export not found",
            )
        return row

    def require_preset_assignment_diagnostic_export_diff_report(
        self,
        *,
        organization_id: uuid.UUID,
        export_diff_report_id: uuid.UUID,
    ) -> AISystemGovernancePresetAssignmentDiagnosticExportDiffReport:
        row = self.db.execute(
            select(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport).where(
                AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id == export_diff_report_id,
                AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preset assignment diagnostic export diff report not found",
            )
        return row

    def diff_reason_code_catalog(self) -> dict[str, Any]:
        return {
            "reason_codes": sorted(
                [dict(item) for item in POLICY_RESOLUTION_SIMULATION_DIFF_REASON_CODE_CATALOG],
                key=lambda item: item["code"],
            ),
            "caveat": POLICY_RESOLUTION_SIMULATION_DIFF_REASON_CODE_CAVEAT,
        }

    def preset_assignment_diagnostic_export_diff_reason_code_catalog(self) -> dict[str, Any]:
        return {
            "reason_codes": sorted(
                [dict(item) for item in PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_DIFF_REASON_CODE_CATALOG],
                key=lambda item: item["code"],
            ),
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_DIFF_REASON_CODE_CAVEAT,
        }

    @staticmethod
    def _reason_code_catalog_codes() -> set[str]:
        return {str(item["code"]) for item in POLICY_RESOLUTION_SIMULATION_DIFF_REASON_CODE_CATALOG}

    @staticmethod
    def _export_diff_reason_code_catalog_codes() -> set[str]:
        return {str(item["code"]) for item in PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_DIFF_REASON_CODE_CATALOG}

    @staticmethod
    def _preset_assignment_diagnostic_export_diff_reason_code_map() -> dict[str, dict[str, str]]:
        return {
            str(item["code"]): {
                "category": str(item["category"]),
                "description": str(item["description"]),
                "severity_hint": str(item["severity_hint"]),
            }
            for item in PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_DIFF_REASON_CODE_CATALOG
        }

    @staticmethod
    def _validate_gating_severity(value: str, *, field_name: str) -> str:
        if value not in POLICY_DIFF_GATING_SEVERITY_ORDER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} must be one of: {', '.join(POLICY_DIFF_GATING_SEVERITY_ORDER)}",
            )
        return value

    @staticmethod
    def _validate_interpretation_band(value: str, *, field_name: str) -> str:
        if value not in POLICY_DIFF_GATING_INTERPRETATION_BANDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} must be one of: {', '.join(POLICY_DIFF_GATING_INTERPRETATION_BANDS)}",
            )
        return value

    @staticmethod
    def _validate_preset_version_selection_mode(value: str, *, field_name: str = "version_selection_mode") -> str:
        if value not in POLICY_DIFF_GATING_COMPARE_PRESET_VERSION_SELECTION_MODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{field_name} must be one of: "
                    "active_then_mutable, pinned_preferred, pinned_required"
                ),
            )
        return value

    def _validate_reason_code_list(self, value: dict | list | None, *, field_name: str) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} must be a list")
        valid_codes = self._reason_code_catalog_codes()
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} entries must be strings")
            if item not in valid_codes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field_name} contains unknown reason code: {item}",
                )
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    def _validate_export_diff_reason_code_list(self, value: dict | list | None, *, field_name: str) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} must be a list")
        valid_codes = self._export_diff_reason_code_catalog_codes()
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} entries must be strings")
            if item not in valid_codes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field_name} contains unknown reason code: {item}",
                )
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    def _validate_interpretation_rules_json(self, value: dict | list | None) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="interpretation_rules_json must be an object")
        out: dict[str, Any] = {}
        band_fields = {
            "severity_increase_band",
            "review_required_flip_band",
            "watched_reason_code_band",
        }
        for key in band_fields:
            if key in value:
                band_value = value.get(key)
                if not isinstance(band_value, str):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"interpretation_rules_json.{key} must be a string",
                    )
                out[key] = self._validate_interpretation_band(band_value, field_name=f"interpretation_rules_json.{key}")
        bool_key = "ignored_reason_codes_do_not_affect_band"
        if bool_key in value:
            if not isinstance(value.get(bool_key), bool):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"interpretation_rules_json.{bool_key} must be boolean",
                )
            out[bool_key] = bool(value[bool_key])
        return out

    def _validate_diagnostic_export_diff_gating_compare_interpretation_rules_json(
        self,
        value: dict | list | None,
    ) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="interpretation_rules_json must be an object")
        out: dict[str, Any] = {}
        band_fields = {
            "severity_increase_band",
            "severity_decrease_band",
            "review_required_flip_to_required_band",
            "review_required_flip_to_not_required_band",
            "watched_reason_code_band",
        }
        for key in band_fields:
            if key in value:
                band_value = value.get(key)
                if not isinstance(band_value, str):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"interpretation_rules_json.{key} must be a string",
                    )
                out[key] = self._validate_interpretation_band(band_value, field_name=f"interpretation_rules_json.{key}")

        bool_fields = {"ignored_reason_codes_do_not_affect_band", "watched_reason_codes_override_ignored"}
        for key in bool_fields:
            if key in value:
                if not isinstance(value.get(key), bool):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"interpretation_rules_json.{key} must be boolean",
                    )
                out[key] = bool(value[key])

        def _normalize_thresholds(raw: Any, *, field_name: str) -> list[dict[str, Any]]:
            if raw is None:
                return []
            if not isinstance(raw, list):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"interpretation_rules_json.{field_name} must be a list",
                )
            normalized: list[dict[str, Any]] = []
            for idx, item in enumerate(raw):
                if not isinstance(item, dict):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"interpretation_rules_json.{field_name}[{idx}] must be an object",
                    )
                min_changes = item.get("min_changes")
                band = item.get("band")
                if not isinstance(min_changes, int) or min_changes < 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"interpretation_rules_json.{field_name}[{idx}].min_changes must be a non-negative integer",
                    )
                if not isinstance(band, str):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"interpretation_rules_json.{field_name}[{idx}].band must be a string",
                    )
                normalized.append(
                    {
                        "min_changes": int(min_changes),
                        "band": self._validate_interpretation_band(
                            band,
                            field_name=f"interpretation_rules_json.{field_name}[{idx}].band",
                        ),
                    }
                )
            normalized.sort(key=lambda item: (int(item["min_changes"]), str(item["band"])))
            return normalized

        out["reason_code_changes_thresholds"] = _normalize_thresholds(
            value.get("reason_code_changes_thresholds"),
            field_name="reason_code_changes_thresholds",
        )
        out["severity_changes_thresholds"] = _normalize_thresholds(
            value.get("severity_changes_thresholds"),
            field_name="severity_changes_thresholds",
        )
        return out

    def _validate_reason_code_rules_json(
        self,
        value: dict | list | None,
        *,
        valid_codes: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason_code_rules_json must be an object")
        allowed_codes = valid_codes if valid_codes is not None else self._reason_code_catalog_codes()
        normalized: dict[str, dict[str, Any]] = {}
        for reason_code, rule in value.items():
            if reason_code not in allowed_codes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"reason_code_rules_json contains unknown reason code: {reason_code}",
                )
            if not isinstance(rule, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"reason_code_rules_json.{reason_code} must be an object",
                )
            severity = rule.get("severity")
            if not isinstance(severity, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"reason_code_rules_json.{reason_code}.severity is required",
                )
            normalized_rule: dict[str, Any] = {
                "severity": self._validate_gating_severity(severity, field_name=f"reason_code_rules_json.{reason_code}.severity"),
            }
            if "review_required" in rule and not isinstance(rule.get("review_required"), bool):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"reason_code_rules_json.{reason_code}.review_required must be boolean",
                )
            if "review_required" in rule:
                normalized_rule["review_required"] = bool(rule["review_required"])
            if "notes" in rule and rule.get("notes") is not None:
                if not isinstance(rule.get("notes"), str):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"reason_code_rules_json.{reason_code}.notes must be string",
                    )
                normalized_rule["notes"] = rule["notes"]
            normalized[reason_code] = normalized_rule
        return normalized

    def _normalize_gating_profile_inputs(
        self,
        *,
        default_severity: str,
        review_required_threshold: str,
        reason_code_rules_json: dict | list | None,
    ) -> tuple[str, str, dict[str, dict[str, Any]]]:
        normalized_default = self._validate_gating_severity(default_severity, field_name="default_severity")
        normalized_threshold = self._validate_gating_severity(
            review_required_threshold,
            field_name="review_required_threshold",
        )
        normalized_rules = self._validate_reason_code_rules_json(reason_code_rules_json)
        return normalized_default, normalized_threshold, normalized_rules

    def _normalize_export_diff_gating_profile_inputs(
        self,
        *,
        default_severity: str,
        review_required_threshold: str,
        reason_code_rules_json: dict | list | None,
    ) -> tuple[str, str, dict[str, dict[str, Any]]]:
        normalized_default = self._validate_gating_severity(default_severity, field_name="default_severity")
        normalized_threshold = self._validate_gating_severity(
            review_required_threshold,
            field_name="review_required_threshold",
        )
        normalized_rules = self._validate_reason_code_rules_json(
            reason_code_rules_json,
            valid_codes=self._export_diff_reason_code_catalog_codes(),
        )
        return normalized_default, normalized_threshold, normalized_rules

    def _normalize_diagnostic_export_diff_gating_compare_preset_inputs(
        self,
        *,
        watched_reason_codes_json: dict | list | None,
        ignored_reason_codes_json: dict | list | None,
        interpretation_rules_json: dict | list | None,
        default_interpretation_band: str,
    ) -> tuple[list[str], list[str], dict[str, Any], str]:
        normalized_watched = self._validate_export_diff_reason_code_list(
            watched_reason_codes_json,
            field_name="watched_reason_codes_json",
        )
        normalized_ignored = self._validate_export_diff_reason_code_list(
            ignored_reason_codes_json,
            field_name="ignored_reason_codes_json",
        )
        normalized_rules = self._validate_diagnostic_export_diff_gating_compare_interpretation_rules_json(
            interpretation_rules_json
        )
        normalized_default_band = self._validate_interpretation_band(
            default_interpretation_band,
            field_name="default_interpretation_band",
        )
        return normalized_watched, normalized_ignored, normalized_rules, normalized_default_band

    @staticmethod
    def _diagnostic_export_diff_gating_compare_preset_snapshot_from_row(
        row: AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
    ) -> dict[str, Any]:
        watched = row.watched_reason_codes_json if isinstance(row.watched_reason_codes_json, list) else []
        ignored = row.ignored_reason_codes_json if isinstance(row.ignored_reason_codes_json, list) else []
        rules = row.interpretation_rules_json if isinstance(row.interpretation_rules_json, dict) else {}
        return {
            "name": row.name,
            "description": row.description,
            "watched_reason_codes_json": watched,
            "ignored_reason_codes_json": ignored,
            "interpretation_rules_json": rules,
            "default_interpretation_band": row.default_interpretation_band,
        }

    def _normalize_diagnostic_export_diff_gating_compare_preset_snapshot(
        self,
        *,
        snapshot_json: dict | list | None,
    ) -> dict[str, Any]:
        if not isinstance(snapshot_json, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Diagnostic export diff gating compare preset version snapshot_json is invalid",
            )
        normalized_watched, normalized_ignored, normalized_rules, normalized_default_band = (
            self._normalize_diagnostic_export_diff_gating_compare_preset_inputs(
                watched_reason_codes_json=snapshot_json.get("watched_reason_codes_json"),
                ignored_reason_codes_json=snapshot_json.get("ignored_reason_codes_json"),
                interpretation_rules_json=snapshot_json.get("interpretation_rules_json"),
                default_interpretation_band=str(snapshot_json.get("default_interpretation_band") or "stable"),
            )
        )
        return {
            "name": str(snapshot_json.get("name") or ""),
            "description": snapshot_json.get("description"),
            "watched_reason_codes_json": normalized_watched,
            "ignored_reason_codes_json": normalized_ignored,
            "interpretation_rules_json": normalized_rules,
            "default_interpretation_band": normalized_default_band,
        }

    def _normalize_gating_compare_preset_inputs(
        self,
        *,
        organization_id: uuid.UUID,
        baseline_gating_report_id: uuid.UUID | None,
        baseline_gating_profile_id: uuid.UUID | None,
        watched_reason_codes_json: dict | list | None,
        ignored_reason_codes_json: dict | list | None,
        interpretation_rules_json: dict | list | None,
        default_interpretation_band: str,
    ) -> tuple[
        uuid.UUID | None,
        uuid.UUID | None,
        list[str],
        list[str],
        dict[str, Any],
        str,
    ]:
        if baseline_gating_report_id is not None:
            self.require_policy_diff_gating_report(
                organization_id=organization_id,
                gating_report_id=baseline_gating_report_id,
            )
        if baseline_gating_profile_id is not None:
            self.require_policy_diff_gating_profile(
                organization_id=organization_id,
                profile_id=baseline_gating_profile_id,
            )
        normalized_watched = self._validate_reason_code_list(
            watched_reason_codes_json,
            field_name="watched_reason_codes_json",
        )
        normalized_ignored = self._validate_reason_code_list(
            ignored_reason_codes_json,
            field_name="ignored_reason_codes_json",
        )
        normalized_rules = self._validate_interpretation_rules_json(interpretation_rules_json)
        normalized_default_band = self._validate_interpretation_band(
            default_interpretation_band,
            field_name="default_interpretation_band",
        )
        return (
            baseline_gating_report_id,
            baseline_gating_profile_id,
            normalized_watched,
            normalized_ignored,
            normalized_rules,
            normalized_default_band,
        )

    @staticmethod
    def _preset_snapshot_from_row(row: AISystemGovernancePolicyDiffGatingComparePreset) -> dict[str, Any]:
        watched = row.watched_reason_codes_json if isinstance(row.watched_reason_codes_json, list) else []
        ignored = row.ignored_reason_codes_json if isinstance(row.ignored_reason_codes_json, list) else []
        rules = row.interpretation_rules_json if isinstance(row.interpretation_rules_json, dict) else {}
        return {
            "name": row.name,
            "description": row.description,
            "baseline_gating_report_id": str(row.baseline_gating_report_id) if row.baseline_gating_report_id else None,
            "baseline_gating_profile_id": str(row.baseline_gating_profile_id) if row.baseline_gating_profile_id else None,
            "watched_reason_codes_json": watched,
            "ignored_reason_codes_json": ignored,
            "interpretation_rules_json": rules,
            "default_interpretation_band": row.default_interpretation_band,
        }

    def _normalize_gating_compare_preset_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_json: dict | list | None,
    ) -> dict[str, Any]:
        if not isinstance(snapshot_json, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preset version snapshot_json is invalid")
        raw_baseline_report = snapshot_json.get("baseline_gating_report_id")
        raw_baseline_profile = snapshot_json.get("baseline_gating_profile_id")
        try:
            baseline_report_id = uuid.UUID(str(raw_baseline_report)) if raw_baseline_report is not None else None
            baseline_profile_id = uuid.UUID(str(raw_baseline_profile)) if raw_baseline_profile is not None else None
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preset version snapshot_json is invalid") from None
        (
            normalized_baseline_report_id,
            normalized_baseline_profile_id,
            normalized_watched,
            normalized_ignored,
            normalized_rules,
            normalized_default_band,
        ) = self._normalize_gating_compare_preset_inputs(
            organization_id=organization_id,
            baseline_gating_report_id=baseline_report_id,
            baseline_gating_profile_id=baseline_profile_id,
            watched_reason_codes_json=snapshot_json.get("watched_reason_codes_json"),
            ignored_reason_codes_json=snapshot_json.get("ignored_reason_codes_json"),
            interpretation_rules_json=snapshot_json.get("interpretation_rules_json"),
            default_interpretation_band=str(snapshot_json.get("default_interpretation_band") or "stable"),
        )
        return {
            "name": str(snapshot_json.get("name") or ""),
            "description": snapshot_json.get("description"),
            "baseline_gating_report_id": normalized_baseline_report_id,
            "baseline_gating_profile_id": normalized_baseline_profile_id,
            "watched_reason_codes_json": normalized_watched,
            "ignored_reason_codes_json": normalized_ignored,
            "interpretation_rules_json": normalized_rules,
            "default_interpretation_band": normalized_default_band,
        }

    @staticmethod
    def _extract_scope_value(
        *,
        scope_type: str,
        scope_id: uuid.UUID | None,
        scope_json: dict | list | None,
    ) -> str | None:
        if scope_type in {
            "sequence_pack",
            "ai_system",
            "diagnostic_export_diff_gating_compare_report",
            "diagnostic_export_diff_gating_profile",
        }:
            return str(scope_id) if scope_id is not None else None
        if scope_type in {"review_type", "rollout_class", "export_type"}:
            if not isinstance(scope_json, dict):
                return None
            if scope_type == "review_type":
                key = "review_type"
            elif scope_type == "rollout_class":
                key = "rollout_class"
            else:
                key = "export_type"
            value = scope_json.get(key)
            return str(value) if isinstance(value, str) and value.strip() else None
        return None

    def _validate_policy_assignment_scope(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        scope_json: dict | list | None,
    ) -> tuple[uuid.UUID | None, dict | None]:
        normalized_scope_id = scope_id
        normalized_scope_json: dict | None = None
        if scope_type == "all_ai_governance":
            return None, None
        if scope_type == "sequence_pack":
            if scope_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_id is required for sequence_pack scope")
            self.require_pack(organization_id=organization_id, pack_id=scope_id)
            return scope_id, None
        if scope_type == "ai_system":
            if scope_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_id is required for ai_system scope")
            ai_system = self.db.execute(
                select(AISystem.id).where(
                    AISystem.organization_id == organization_id,
                    AISystem.id == scope_id,
                )
            ).scalar_one_or_none()
            if ai_system is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scoped ai_system not found")
            return scope_id, None
        if scope_type == "review_type":
            if not isinstance(scope_json, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.review_type is required")
            review_type = scope_json.get("review_type")
            if review_type not in REVIEW_TYPES:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.review_type is invalid")
            normalized_scope_json = {"review_type": review_type}
            normalized_scope_id = None
            return normalized_scope_id, normalized_scope_json
        if scope_type == "rollout_class":
            if not isinstance(scope_json, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.rollout_class is required")
            rollout_class = scope_json.get("rollout_class")
            if not isinstance(rollout_class, str) or not rollout_class.strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.rollout_class is required")
            normalized_scope_json = {"rollout_class": rollout_class.strip()}
            normalized_scope_id = None
            return normalized_scope_id, normalized_scope_json
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope_type")

    def _validate_diag_export_diff_compare_preset_assignment_scope(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        scope_json: dict | list | None,
    ) -> tuple[uuid.UUID | None, dict | None]:
        normalized_scope_id = scope_id
        normalized_scope_json: dict | None = None
        if scope_type == "all_ai_governance":
            return None, None
        if scope_type == "diagnostic_export_diff_gating_compare_report":
            if scope_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_id is required for diagnostic_export_diff_gating_compare_report scope",
                )
            self.require_diagnostic_export_diff_gating_compare_report(
                organization_id=organization_id,
                compare_report_id=scope_id,
            )
            return scope_id, None
        if scope_type == "diagnostic_export_diff_gating_profile":
            if scope_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_id is required for diagnostic_export_diff_gating_profile scope",
                )
            self.require_diagnostic_export_diff_gating_profile(
                organization_id=organization_id,
                profile_id=scope_id,
            )
            return scope_id, None
        if scope_type == "sequence_pack":
            if scope_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_id is required for sequence_pack scope")
            self.require_pack(organization_id=organization_id, pack_id=scope_id)
            return scope_id, None
        if scope_type == "ai_system":
            if scope_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_id is required for ai_system scope")
            ai_system = self.db.execute(
                select(AISystem.id).where(
                    AISystem.organization_id == organization_id,
                    AISystem.id == scope_id,
                )
            ).scalar_one_or_none()
            if ai_system is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scoped ai_system not found")
            return scope_id, None
        if scope_type == "review_type":
            if not isinstance(scope_json, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.review_type is required")
            review_type = scope_json.get("review_type")
            if review_type not in REVIEW_TYPES:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.review_type is invalid")
            normalized_scope_json = {"review_type": review_type}
            normalized_scope_id = None
            return normalized_scope_id, normalized_scope_json
        if scope_type == "rollout_class":
            if not isinstance(scope_json, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.rollout_class is required")
            rollout_class = scope_json.get("rollout_class")
            if not isinstance(rollout_class, str) or not rollout_class.strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.rollout_class is required")
            normalized_scope_json = {"rollout_class": rollout_class.strip()}
            normalized_scope_id = None
            return normalized_scope_id, normalized_scope_json
        if scope_type == "export_type":
            if not isinstance(scope_json, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.export_type is required")
            export_type = scope_json.get("export_type")
            if export_type not in {"diagnostic_report", "diagnostic_diff_report"}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.export_type is invalid")
            normalized_scope_json = {"export_type": export_type}
            normalized_scope_id = None
            return normalized_scope_id, normalized_scope_json
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope_type")

    @staticmethod
    def _assignment_snapshot(row: AISystemGovernanceGuardrailPolicyAssignment) -> dict[str, Any]:
        return {
            "policy_set_id": str(row.policy_set_id),
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id is not None else None,
            "scope_json": row.scope_json,
            "priority": row.priority,
            "status": row.status,
            "reason": row.reason,
        }

    def _create_policy_assignment_history(
        self,
        *,
        organization_id: uuid.UUID,
        assignment_id: uuid.UUID,
        event_type: str,
        before_json: dict | list | None,
        after_json: dict | list | None,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicyAssignmentHistory:
        row = AISystemGovernanceGuardrailPolicyAssignmentHistory(
            organization_id=organization_id,
            assignment_id=assignment_id,
            event_type=event_type,
            before_json=before_json,
            after_json=after_json,
            reason=reason,
            changed_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    @staticmethod
    def _preset_assignment_snapshot(row: AISystemGovernancePolicyDiffGatingComparePresetAssignment) -> dict[str, Any]:
        return {
            "preset_id": str(row.preset_id),
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id is not None else None,
            "scope_json": row.scope_json,
            "priority": row.priority,
            "status": row.status,
            "reason": row.reason,
        }

    def _create_preset_assignment_history(
        self,
        *,
        organization_id: uuid.UUID,
        assignment_id: uuid.UUID,
        event_type: str,
        before_json: dict | list | None,
        after_json: dict | list | None,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory:
        row = AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory(
            organization_id=organization_id,
            assignment_id=assignment_id,
            event_type=event_type,
            before_json=before_json,
            after_json=after_json,
            reason=reason,
            changed_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    @staticmethod
    def _diag_export_diff_compare_preset_assignment_snapshot(
        row: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment,
    ) -> dict[str, Any]:
        return {
            "preset_id": str(row.preset_id),
            "scope_type": row.scope_type,
            "scope_id": str(row.scope_id) if row.scope_id is not None else None,
            "scope_json": row.scope_json,
            "priority": row.priority,
            "status": row.status,
            "reason": row.reason,
        }

    def _create_diag_export_diff_compare_preset_assignment_history(
        self,
        *,
        organization_id: uuid.UUID,
        assignment_id: uuid.UUID,
        event_type: str,
        before_json: dict | list | None,
        after_json: dict | list | None,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory:
        row = AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory(
            organization_id=organization_id,
            assignment_id=assignment_id,
            event_type=event_type,
            before_json=before_json,
            after_json=after_json,
            reason=reason,
            changed_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _assert_no_duplicate_active_policy_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        scope_json: dict | None,
        exclude_assignment_id: uuid.UUID | None = None,
    ) -> None:
        stmt = select(AISystemGovernanceGuardrailPolicyAssignment).where(
            AISystemGovernanceGuardrailPolicyAssignment.organization_id == organization_id,
            AISystemGovernanceGuardrailPolicyAssignment.status == "active",
            AISystemGovernanceGuardrailPolicyAssignment.scope_type == scope_type,
        )
        if exclude_assignment_id is not None:
            stmt = stmt.where(AISystemGovernanceGuardrailPolicyAssignment.id != exclude_assignment_id)
        rows = self.db.execute(stmt).scalars().all()
        expected = self._extract_scope_value(scope_type=scope_type, scope_id=scope_id, scope_json=scope_json)
        for row in rows:
            existing = self._extract_scope_value(scope_type=row.scope_type, scope_id=row.scope_id, scope_json=row.scope_json)
            if existing == expected:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Active policy assignment already exists for this exact scope",
                )

    def _assert_no_duplicate_active_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        scope_json: dict | None,
        exclude_assignment_id: uuid.UUID | None = None,
    ) -> None:
        stmt = select(AISystemGovernancePolicyDiffGatingComparePresetAssignment).where(
            AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id,
            AISystemGovernancePolicyDiffGatingComparePresetAssignment.status == "active",
            AISystemGovernancePolicyDiffGatingComparePresetAssignment.scope_type == scope_type,
        )
        if exclude_assignment_id is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id != exclude_assignment_id)
        rows = self.db.execute(stmt).scalars().all()
        expected = self._extract_scope_value(scope_type=scope_type, scope_id=scope_id, scope_json=scope_json)
        for row in rows:
            existing = self._extract_scope_value(scope_type=row.scope_type, scope_id=row.scope_id, scope_json=row.scope_json)
            if existing == expected:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Active preset assignment already exists for this exact scope",
                )

    def _assert_no_duplicate_active_diag_export_diff_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        scope_json: dict | None,
        exclude_assignment_id: uuid.UUID | None = None,
    ) -> None:
        stmt = select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.organization_id == organization_id,
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.status == "active",
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.scope_type == scope_type,
        )
        if exclude_assignment_id is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id != exclude_assignment_id)
        rows = self.db.execute(stmt).scalars().all()
        expected = self._extract_scope_value(scope_type=scope_type, scope_id=scope_id, scope_json=scope_json)
        for row in rows:
            existing = self._extract_scope_value(scope_type=row.scope_type, scope_id=row.scope_id, scope_json=row.scope_json)
            if existing == expected:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Active diagnostic export diff gating compare preset assignment already exists for this exact scope",
                )

    @staticmethod
    def _validate_policy_profile(profile_json: dict) -> dict:
        if not isinstance(profile_json, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="profile_json must be an object")
        strategy = profile_json.get("resolution_strategy")
        if strategy != "deterministic_precedence_v1":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="profile_json.resolution_strategy must be deterministic_precedence_v1")
        allow_override = bool(profile_json.get("allow_operator_override", True))
        ack_text = profile_json.get("acknowledgement_text")
        if allow_override and (not isinstance(ack_text, str) or not ack_text.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="profile_json.acknowledgement_text is required when allow_operator_override=true",
            )
        scope_order = profile_json.get("scope_precedence_order")
        if not isinstance(scope_order, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="profile_json.scope_precedence_order must be a list")
        if sorted(scope_order) != sorted(KNOWN_SCOPE_ORDER) or len(scope_order) != len(KNOWN_SCOPE_ORDER):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="profile_json.scope_precedence_order must include each scope type exactly once",
            )
        return {
            "resolution_strategy": strategy,
            "acknowledgement_text": ack_text.strip() if isinstance(ack_text, str) else FREEZE_ACK_TEXT,
            "allow_operator_override": allow_override,
            "require_override_reason": bool(profile_json.get("require_override_reason", True)),
            "include_info_windows": bool(profile_json.get("include_info_windows", True)),
            "include_warn_windows": bool(profile_json.get("include_warn_windows", True)),
            "include_block_windows": bool(profile_json.get("include_block_windows", True)),
            "scope_precedence_order": scope_order,
        }

    def create_policy_set(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicySet:
        row = AISystemGovernanceGuardrailPolicySet(
            organization_id=organization_id,
            name=name,
            description=description,
            status=status_value,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_policy_sets(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceGuardrailPolicySet]:
        stmt = select(AISystemGovernanceGuardrailPolicySet).where(
            AISystemGovernanceGuardrailPolicySet.organization_id == organization_id,
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernanceGuardrailPolicySet.status == status_filter)
        if not include_archived:
            stmt = stmt.where(AISystemGovernanceGuardrailPolicySet.status != "archived")
        return (
            self.db.execute(stmt.order_by(AISystemGovernanceGuardrailPolicySet.created_at.desc()).offset(offset).limit(limit))
            .scalars()
            .all()
        )

    def update_policy_set(
        self,
        *,
        row: AISystemGovernanceGuardrailPolicySet,
        name: str | None,
        description: str | None,
        status_value: str | None,
    ) -> AISystemGovernanceGuardrailPolicySet:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived guardrail policy sets cannot be updated")
        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        if status_value is not None:
            row.status = status_value
        self.db.flush()
        return row

    def archive_policy_set(
        self,
        *,
        row: AISystemGovernanceGuardrailPolicySet,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicySet:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def create_policy_set_version(
        self,
        *,
        organization_id: uuid.UUID,
        policy_set: AISystemGovernanceGuardrailPolicySet,
        profile_json: dict,
        change_reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicySetVersion:
        if policy_set.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived guardrail policy sets cannot accept new versions")
        normalized_profile = self._validate_policy_profile(profile_json)
        max_version = self.db.execute(
            select(func.max(AISystemGovernanceGuardrailPolicySetVersion.version_number)).where(
                AISystemGovernanceGuardrailPolicySetVersion.organization_id == organization_id,
                AISystemGovernanceGuardrailPolicySetVersion.policy_set_id == policy_set.id,
            )
        ).scalar_one()
        next_version = int(max_version or 0) + 1
        row = AISystemGovernanceGuardrailPolicySetVersion(
            organization_id=organization_id,
            policy_set_id=policy_set.id,
            version_number=next_version,
            status="draft",
            profile_json=normalized_profile,
            change_reason=change_reason,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_policy_set_versions(
        self,
        *,
        organization_id: uuid.UUID,
        policy_set_id: uuid.UUID,
    ) -> list[AISystemGovernanceGuardrailPolicySetVersion]:
        return (
            self.db.execute(
                select(AISystemGovernanceGuardrailPolicySetVersion)
                .where(
                    AISystemGovernanceGuardrailPolicySetVersion.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicySetVersion.policy_set_id == policy_set_id,
                )
                .order_by(
                    AISystemGovernanceGuardrailPolicySetVersion.version_number.desc(),
                    AISystemGovernanceGuardrailPolicySetVersion.created_at.desc(),
                )
            )
            .scalars()
            .all()
        )

    def activate_policy_set_version(
        self,
        *,
        organization_id: uuid.UUID,
        policy_set: AISystemGovernanceGuardrailPolicySet,
        version: AISystemGovernanceGuardrailPolicySetVersion,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicySetVersion:
        existing_active = None
        if policy_set.active_version_id is not None:
            existing_active = self.db.execute(
                select(AISystemGovernanceGuardrailPolicySetVersion).where(
                    AISystemGovernanceGuardrailPolicySetVersion.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicySetVersion.id == policy_set.active_version_id,
                )
            ).scalar_one_or_none()
        if existing_active is not None and existing_active.id != version.id:
            existing_active.status = "deprecated"
        version.status = "active"
        version.activated_by_user_id = actor_user_id
        version.activated_at = self.now()
        policy_set.active_version_id = version.id
        self.db.flush()
        return version

    def get_active_policy_profile(
        self,
        *,
        organization_id: uuid.UUID,
        policy_set_id: uuid.UUID,
    ) -> tuple[AISystemGovernanceGuardrailPolicySet, AISystemGovernanceGuardrailPolicySetVersion]:
        policy_set = self.require_policy_set(organization_id=organization_id, policy_set_id=policy_set_id)
        if policy_set.active_version_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Guardrail policy set has no active version")
        version = self.db.execute(
            select(AISystemGovernanceGuardrailPolicySetVersion).where(
                AISystemGovernanceGuardrailPolicySetVersion.organization_id == organization_id,
                AISystemGovernanceGuardrailPolicySetVersion.policy_set_id == policy_set.id,
                AISystemGovernanceGuardrailPolicySetVersion.id == policy_set.active_version_id,
            )
        ).scalar_one_or_none()
        if version is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Guardrail policy set active version is invalid")
        normalized = self._validate_policy_profile(version.profile_json)
        version.profile_json = normalized
        return policy_set, version

    @staticmethod
    def _normalize_uuid_values(values: list[Any], *, field_name: str) -> list[str]:
        normalized: list[str] = []
        for value in values:
            try:
                normalized.append(str(uuid.UUID(str(value))))
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"scope_json.{field_name} must contain valid UUID values",
                ) from None
        return normalized

    def _validate_scope_json(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_json: dict | list | None,
    ) -> dict | None:
        if scope_type == "all_ai_governance":
            return None
        if not isinstance(scope_json, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json must be an object for selected scope_type")

        if scope_type == "review_type":
            review_types = scope_json.get("review_types")
            if not isinstance(review_types, list) or not review_types:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.review_types must be a non-empty list")
            if any(item not in REVIEW_TYPES for item in review_types):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scope_json.review_types contains invalid review type")
            return {"review_types": sorted({str(item) for item in review_types})}

        if scope_type == "sequence_pack":
            pack_ids = scope_json.get("sequence_pack_ids")
            if not isinstance(pack_ids, list) or not pack_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_json.sequence_pack_ids must be a non-empty list",
                )
            normalized = self._normalize_uuid_values(pack_ids, field_name="sequence_pack_ids")
            existing = (
                self.db.execute(
                    select(AISystemGovernanceReviewSequencePack.id).where(
                        AISystemGovernanceReviewSequencePack.organization_id == organization_id,
                        AISystemGovernanceReviewSequencePack.id.in_([uuid.UUID(item) for item in normalized]),
                    )
                )
                .scalars()
                .all()
            )
            if len(existing) != len(set(normalized)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_json.sequence_pack_ids must belong to the same organization",
                )
            return {"sequence_pack_ids": sorted(set(normalized))}

        if scope_type == "ai_system":
            ai_system_ids = scope_json.get("ai_system_ids")
            if not isinstance(ai_system_ids, list) or not ai_system_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_json.ai_system_ids must be a non-empty list",
                )
            normalized = self._normalize_uuid_values(ai_system_ids, field_name="ai_system_ids")
            existing = (
                self.db.execute(
                    select(AISystem.id).where(
                        AISystem.organization_id == organization_id,
                        AISystem.id.in_([uuid.UUID(item) for item in normalized]),
                    )
                )
                .scalars()
                .all()
            )
            if len(existing) != len(set(normalized)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_json.ai_system_ids must belong to the same organization",
                )
            return {"ai_system_ids": sorted(set(normalized))}

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported scope_type")

    def _validate_freeze_window_dates(self, *, starts_at: datetime, ends_at: datetime) -> tuple[datetime, datetime]:
        starts = self.ensure_utc(starts_at)
        ends = self.ensure_utc(ends_at)
        if starts >= ends:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="starts_at must be before ends_at")
        return starts, ends

    def create_freeze_window(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        starts_at: datetime,
        ends_at: datetime,
        scope_type: str,
        scope_json: dict | list | None,
        priority: int,
        enforcement_level: str,
        override_allowed: bool,
        precedence_notes: str | None,
        reason: str,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceFreezeWindow:
        if priority < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="priority must be non-negative")
        starts, ends = self._validate_freeze_window_dates(starts_at=starts_at, ends_at=ends_at)
        normalized_scope_json = self._validate_scope_json(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_json=scope_json,
        )
        row = AISystemGovernanceFreezeWindow(
            organization_id=organization_id,
            name=name,
            description=description,
            status=status_value,
            starts_at=starts,
            ends_at=ends,
            scope_type=scope_type,
            scope_json=normalized_scope_json,
            priority=priority,
            enforcement_level=enforcement_level,
            override_allowed=override_allowed,
            precedence_notes=precedence_notes,
            reason=reason,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_freeze_windows(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        active_at: datetime | None,
        scope_type: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceFreezeWindow]:
        stmt = select(AISystemGovernanceFreezeWindow).where(AISystemGovernanceFreezeWindow.organization_id == organization_id)
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernanceFreezeWindow.status == status_filter)
        if scope_type is not None:
            stmt = stmt.where(AISystemGovernanceFreezeWindow.scope_type == scope_type)
        if not include_archived:
            stmt = stmt.where(AISystemGovernanceFreezeWindow.status != "archived")
        if active_at is not None:
            at = self.ensure_utc(active_at)
            stmt = stmt.where(
                AISystemGovernanceFreezeWindow.starts_at <= at,
                AISystemGovernanceFreezeWindow.ends_at >= at,
            )
        return (
            self.db.execute(stmt.order_by(AISystemGovernanceFreezeWindow.created_at.desc()).offset(offset).limit(limit))
            .scalars()
            .all()
        )

    def update_freeze_window(
        self,
        *,
        row: AISystemGovernanceFreezeWindow,
        name: str | None,
        description: str | None,
        starts_at: datetime | None,
        ends_at: datetime | None,
        scope_type: str | None,
        scope_json: dict | list | None,
        priority: int | None,
        enforcement_level: str | None,
        override_allowed: bool | None,
        precedence_notes: str | None,
        reason: str | None,
        status_value: str | None,
    ) -> AISystemGovernanceFreezeWindow:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived freeze windows cannot be updated")

        effective_scope_type = scope_type if scope_type is not None else row.scope_type
        effective_scope_json = scope_json if scope_json is not None else row.scope_json
        effective_starts = starts_at if starts_at is not None else row.starts_at
        effective_ends = ends_at if ends_at is not None else row.ends_at
        starts, ends = self._validate_freeze_window_dates(starts_at=effective_starts, ends_at=effective_ends)
        effective_priority = priority if priority is not None else row.priority
        if effective_priority < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="priority must be non-negative")
        normalized_scope_json = self._validate_scope_json(
            organization_id=row.organization_id,
            scope_type=effective_scope_type,
            scope_json=effective_scope_json,
        )

        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        if starts_at is not None:
            row.starts_at = starts
        if ends_at is not None:
            row.ends_at = ends
        if scope_type is not None:
            row.scope_type = scope_type
        if scope_json is not None or scope_type is not None:
            row.scope_json = normalized_scope_json
        if priority is not None:
            row.priority = priority
        if enforcement_level is not None:
            row.enforcement_level = enforcement_level
        if override_allowed is not None:
            row.override_allowed = override_allowed
        if precedence_notes is not None:
            row.precedence_notes = precedence_notes
        if reason is not None:
            row.reason = reason
        if status_value is not None:
            row.status = status_value
        self.db.flush()
        return row

    def archive_freeze_window(
        self,
        *,
        row: AISystemGovernanceFreezeWindow,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceFreezeWindow:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def _scope_matches(
        self,
        *,
        freeze_window: AISystemGovernanceFreezeWindow,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID],
        review_types: list[str],
    ) -> bool:
        if freeze_window.scope_type == "all_ai_governance":
            return True
        scope_json = freeze_window.scope_json if isinstance(freeze_window.scope_json, dict) else {}
        if freeze_window.scope_type == "sequence_pack":
            if sequence_pack_id is None:
                return False
            pack_ids = {str(item) for item in scope_json.get("sequence_pack_ids", [])}
            return str(sequence_pack_id) in pack_ids
        if freeze_window.scope_type == "review_type":
            scoped = {str(item) for item in scope_json.get("review_types", [])}
            return len(scoped.intersection(set(review_types))) > 0
        if freeze_window.scope_type == "ai_system":
            scoped = {str(item) for item in scope_json.get("ai_system_ids", [])}
            return len(scoped.intersection({str(item) for item in ai_system_ids})) > 0
        return False

    def _freeze_precedence_key(
        self,
        freeze_window: AISystemGovernanceFreezeWindow,
        *,
        scope_precedence_order: list[str] | None = None,
    ) -> tuple[int, int, float, str]:
        scope_order = scope_precedence_order or KNOWN_SCOPE_ORDER
        specificity_map = {scope: len(scope_order) - idx for idx, scope in enumerate(scope_order)}
        return (
            -int(freeze_window.priority),
            -int(specificity_map.get(freeze_window.scope_type, SCOPE_SPECIFICITY.get(freeze_window.scope_type, 0))),
            -self.ensure_utc(freeze_window.starts_at).timestamp(),
            str(freeze_window.id),
        )

    def _resolve_guardrail_conflicts(
        self,
        matches: list[AISystemGovernanceFreezeWindow],
        *,
        scope_precedence_order: list[str] | None = None,
    ) -> dict[str, Any]:
        ordered = sorted(matches, key=lambda item: self._freeze_precedence_key(item, scope_precedence_order=scope_precedence_order))
        precedence_order = [str(item.id) for item in ordered]
        block_windows = [item for item in ordered if item.enforcement_level not in {"info", "warn", "block"} or item.enforcement_level == "block"]
        warn_windows = [item for item in ordered if item.enforcement_level == "warn"]
        info_windows = [item for item in ordered if item.enforcement_level == "info"]
        primary_block = block_windows[0] if block_windows else None
        blocked = primary_block is not None
        warnings = [
            f"Freeze window {item.name} ({item.id}) enforcement={item.enforcement_level}"
            for item in warn_windows
        ]
        info = [
            f"Freeze window {item.name} ({item.id}) enforcement={item.enforcement_level}"
            for item in info_windows
        ]
        return {
            "blocked": blocked,
            "primary_blocking_window_id": primary_block.id if primary_block else None,
            "override_allowed": bool(primary_block.override_allowed) if primary_block else True,
            "enforcement_level": primary_block.enforcement_level if primary_block else ("warn" if warn_windows else ("info" if info_windows else "none")),
            "precedence_order": precedence_order,
            "matching_window_count": len(ordered),
            "warnings": warnings,
            "info": info,
        }

    def evaluate_guardrails(
        self,
        *,
        organization_id: uuid.UUID,
        action_type: str,
        sequence_pack_id: uuid.UUID | None,
        recurrence_template_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID] | None,
        review_types: list[str] | None,
        planned_start: datetime | None,
        planned_end: datetime | None,
        rollout_class: str | None = None,
        policy_set_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        policy_resolution = self.resolve_policy_assignment(
            organization_id=organization_id,
            explicit_policy_set_id=policy_set_id,
            sequence_pack_id=sequence_pack_id,
            ai_system_ids=ai_system_ids,
            review_types=review_types,
            rollout_class=rollout_class,
        )
        profile = policy_resolution["profile_json"]

        if sequence_pack_id is not None:
            self.require_pack(organization_id=organization_id, pack_id=sequence_pack_id)
        if recurrence_template_id is not None:
            recurrence = self.db.execute(
                select(AISystemGovernanceReviewRecurrenceTemplate).where(
                    AISystemGovernanceReviewRecurrenceTemplate.organization_id == organization_id,
                    AISystemGovernanceReviewRecurrenceTemplate.id == recurrence_template_id,
                )
            ).scalar_one_or_none()
            if recurrence is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI governance review recurrence template not found")
        ai_ids = ai_system_ids or []
        if ai_ids:
            existing = (
                self.db.execute(
                    select(AISystem.id).where(
                        AISystem.organization_id == organization_id,
                        AISystem.id.in_(ai_ids),
                    )
                )
                .scalars()
                .all()
            )
            if len(existing) != len(set(ai_ids)):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more ai_system_ids not found")

        review_type_values = review_types or []
        if any(item not in REVIEW_TYPES for item in review_type_values):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="review_types contains invalid review type")

        start_at = self.ensure_utc(planned_start) if planned_start is not None else self.now()
        end_at = self.ensure_utc(planned_end) if planned_end is not None else start_at
        if start_at > end_at:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="planned_start must be before or equal to planned_end")

        active_windows = (
            self.db.execute(
                select(AISystemGovernanceFreezeWindow).where(
                    AISystemGovernanceFreezeWindow.organization_id == organization_id,
                    AISystemGovernanceFreezeWindow.status == "active",
                    AISystemGovernanceFreezeWindow.starts_at <= end_at,
                    AISystemGovernanceFreezeWindow.ends_at >= start_at,
                )
            )
            .scalars()
            .all()
        )
        matches = [
            row
            for row in active_windows
            if self._scope_matches(
                freeze_window=row,
                sequence_pack_id=sequence_pack_id,
                ai_system_ids=ai_ids,
                review_types=review_type_values,
            )
        ]
        scope_order = profile["scope_precedence_order"] if profile is not None else None
        ordered_matches = sorted(matches, key=lambda item: self._freeze_precedence_key(item, scope_precedence_order=scope_order))
        resolution = self._resolve_guardrail_conflicts(ordered_matches, scope_precedence_order=scope_order)
        warnings = [f"{len(ordered_matches)} active governance freeze window(s) match this action and time range"] if ordered_matches else []
        warnings.extend(resolution["warnings"])
        allow_operator_override = profile["allow_operator_override"] if profile is not None else True
        require_override_reason = profile["require_override_reason"] if profile is not None else True
        if resolution["blocked"] and not allow_operator_override:
            resolution["override_allowed"] = False
        required_ack_value = profile["acknowledgement_text"] if profile is not None else FREEZE_ACK_TEXT
        required_ack = required_ack_value if (resolution["blocked"] and resolution["override_allowed"]) else None
        include_info = True if profile is None else profile["include_info_windows"]
        include_warn = True if profile is None else profile["include_warn_windows"]
        include_block = True if profile is None else profile["include_block_windows"]
        display_matches = []
        for row in ordered_matches:
            if row.enforcement_level == "info" and not include_info:
                continue
            if row.enforcement_level == "warn" and not include_warn:
                continue
            if row.enforcement_level not in {"info", "warn"} and not include_block:
                continue
            display_matches.append(row)
        return {
            "blocked": resolution["blocked"],
            "matching_freeze_windows": [
                {
                    "id": row.id,
                    "name": row.name,
                    "scope_type": row.scope_type,
                    "priority": row.priority,
                    "enforcement_level": row.enforcement_level,
                    "override_allowed": row.override_allowed,
                    "starts_at": row.starts_at,
                    "ends_at": row.ends_at,
                    "reason": row.reason,
                }
                for row in display_matches
            ],
            "resolution": resolution,
            "warnings": warnings,
            "required_acknowledgement_text": required_ack,
            "caveat": GUARDRAIL_CAVEAT,
            "action_type": action_type,
            "planned_start": start_at,
            "planned_end": end_at,
            "policy_set_id": policy_resolution["resolved_policy_set_id"],
            "policy_version_id": policy_resolution["resolved_policy_version_id"],
            "policy_resolution": {
                "resolved_policy_set_id": policy_resolution["resolved_policy_set_id"],
                "resolved_policy_version_id": policy_resolution["resolved_policy_version_id"],
                "resolution_source": policy_resolution["resolution_source"],
                "assignment_id": policy_resolution["assignment_id"],
                "precedence_trace": policy_resolution["precedence_trace"],
                "caveat": policy_resolution["caveat"],
            },
            "allow_operator_override": allow_operator_override,
            "require_override_reason": require_override_reason,
        }

    def preview_guardrail_conflicts(
        self,
        *,
        organization_id: uuid.UUID,
        action_type: str,
        sequence_pack_id: uuid.UUID | None,
        recurrence_template_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID] | None,
        review_types: list[str] | None,
        planned_start: datetime | None,
        planned_end: datetime | None,
        rollout_class: str | None = None,
        policy_set_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        result = self.evaluate_guardrails(
            organization_id=organization_id,
            action_type=action_type,
            sequence_pack_id=sequence_pack_id,
            recurrence_template_id=recurrence_template_id,
            ai_system_ids=ai_system_ids,
            review_types=review_types,
            planned_start=planned_start,
            planned_end=planned_end,
            rollout_class=rollout_class,
            policy_set_id=policy_set_id,
        )
        primary_blocking_window = None
        if result["resolution"]["primary_blocking_window_id"] is not None:
            primary_blocking_window = next(
                (
                    item
                    for item in result["matching_freeze_windows"]
                    if item["id"] == result["resolution"]["primary_blocking_window_id"]
                ),
                None,
            )
        if result["resolution"]["blocked"]:
            explanation = (
                "At least one matching freeze window has block enforcement. "
                "The highest-precedence block window determines the final decision."
            )
        elif result["resolution"]["warnings"]:
            explanation = "No blocking freeze windows matched; warning-level windows were detected."
        elif result["resolution"]["info"]:
            explanation = "Only info-level freeze windows matched."
        else:
            explanation = "No matching freeze windows."
        return {
            "all_matching_freeze_windows": result["matching_freeze_windows"],
            "sorted_precedence_order": result["resolution"]["precedence_order"],
            "primary_blocking_window": primary_blocking_window,
            "final_decision": result["resolution"],
            "policy_set_id": result["policy_set_id"],
            "policy_version_id": result["policy_version_id"],
            "policy_resolution": result["policy_resolution"],
            "explanation": explanation,
            "caveat": result["caveat"],
        }

    def create_operator_acknowledgement(
        self,
        *,
        organization_id: uuid.UUID,
        action_type: str,
        target_type: str,
        target_id: uuid.UUID | None,
        acknowledgement_text: str,
        reason: str | None,
        override_freeze: bool,
        freeze_window_ids: list[uuid.UUID] | None,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceOperatorAcknowledgement:
        row = AISystemGovernanceOperatorAcknowledgement(
            organization_id=organization_id,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            acknowledgement_text=acknowledgement_text,
            reason=reason,
            override_freeze=override_freeze,
            freeze_window_ids_json=[str(item) for item in freeze_window_ids] if freeze_window_ids else None,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_operator_acknowledgements(
        self,
        *,
        organization_id: uuid.UUID,
        action_type: str | None,
        target_type: str | None,
        target_id: uuid.UUID | None,
        override_freeze: bool | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceOperatorAcknowledgement]:
        stmt = select(AISystemGovernanceOperatorAcknowledgement).where(
            AISystemGovernanceOperatorAcknowledgement.organization_id == organization_id
        )
        if action_type is not None:
            stmt = stmt.where(AISystemGovernanceOperatorAcknowledgement.action_type == action_type)
        if target_type is not None:
            stmt = stmt.where(AISystemGovernanceOperatorAcknowledgement.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(AISystemGovernanceOperatorAcknowledgement.target_id == target_id)
        if override_freeze is not None:
            stmt = stmt.where(AISystemGovernanceOperatorAcknowledgement.override_freeze == override_freeze)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceOperatorAcknowledgement.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def _validate_step_defaults(
        self,
        *,
        organization_id: uuid.UUID,
        default_reminder_policy_id: uuid.UUID | None,
        default_assigned_to_user_id: uuid.UUID | None,
    ) -> None:
        if default_reminder_policy_id is not None:
            policy = self.db.execute(
                select(AISystemGovernanceReviewReminderPolicy).where(
                    AISystemGovernanceReviewReminderPolicy.id == default_reminder_policy_id,
                    AISystemGovernanceReviewReminderPolicy.organization_id == organization_id,
                )
            ).scalar_one_or_none()
            if policy is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Default reminder policy not found")
            if policy.status != "active":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="default_reminder_policy_id must reference an active reminder policy",
                )
        AISystemService(self.db).ensure_active_member(
            organization_id,
            default_assigned_to_user_id,
            field_name="default_assigned_to_user_id",
        )

    def _assert_active_step_order_available(
        self,
        *,
        organization_id: uuid.UUID,
        pack_id: uuid.UUID,
        step_order: int,
        exclude_step_id: uuid.UUID | None = None,
    ) -> None:
        stmt = select(AISystemGovernanceReviewSequenceStep).where(
            AISystemGovernanceReviewSequenceStep.organization_id == organization_id,
            AISystemGovernanceReviewSequenceStep.sequence_pack_id == pack_id,
            AISystemGovernanceReviewSequenceStep.step_order == step_order,
            AISystemGovernanceReviewSequenceStep.status == "active",
        )
        if exclude_step_id is not None:
            stmt = stmt.where(AISystemGovernanceReviewSequenceStep.id != exclude_step_id)
        existing = self.db.execute(stmt).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active sequence step_order already exists in this pack")

    def create_pack(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceReviewSequencePack:
        row = AISystemGovernanceReviewSequencePack(
            organization_id=organization_id,
            name=name,
            description=description,
            status=status_value,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_packs(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceReviewSequencePack]:
        stmt = select(AISystemGovernanceReviewSequencePack).where(
            AISystemGovernanceReviewSequencePack.organization_id == organization_id,
        )
        if status_filter:
            stmt = stmt.where(AISystemGovernanceReviewSequencePack.status == status_filter)
        if not include_archived:
            stmt = stmt.where(AISystemGovernanceReviewSequencePack.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceReviewSequencePack.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def update_pack(
        self,
        *,
        row: AISystemGovernanceReviewSequencePack,
        name: str | None,
        description: str | None,
        status_value: str | None,
    ) -> AISystemGovernanceReviewSequencePack:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived sequence packs cannot be updated")
        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        if status_value is not None:
            row.status = status_value
        self.db.flush()
        return row

    def archive_pack(
        self,
        *,
        row: AISystemGovernanceReviewSequencePack,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceReviewSequencePack:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def create_step(
        self,
        *,
        organization_id: uuid.UUID,
        pack: AISystemGovernanceReviewSequencePack,
        step_order: int,
        review_type: str,
        title_template: str | None,
        description_template: str | None,
        offset_days_from_start: int,
        default_reminder_policy_id: uuid.UUID | None,
        default_assigned_to_user_id: uuid.UUID | None,
        default_checklist_json: dict | list | None,
        require_previous_step_planned: bool,
        status_value: str,
    ) -> AISystemGovernanceReviewSequenceStep:
        if pack.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sequence pack must be active")
        if offset_days_from_start < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset_days_from_start must be non-negative")
        self._validate_step_defaults(
            organization_id=organization_id,
            default_reminder_policy_id=default_reminder_policy_id,
            default_assigned_to_user_id=default_assigned_to_user_id,
        )
        if status_value == "active":
            self._assert_active_step_order_available(
                organization_id=organization_id,
                pack_id=pack.id,
                step_order=step_order,
            )

        row = AISystemGovernanceReviewSequenceStep(
            organization_id=organization_id,
            sequence_pack_id=pack.id,
            step_order=step_order,
            review_type=review_type,
            title_template=title_template,
            description_template=description_template,
            offset_days_from_start=offset_days_from_start,
            default_reminder_policy_id=default_reminder_policy_id,
            default_assigned_to_user_id=default_assigned_to_user_id,
            default_checklist_json=default_checklist_json,
            require_previous_step_planned=require_previous_step_planned,
            status=status_value,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_steps(self, *, organization_id: uuid.UUID, pack_id: uuid.UUID) -> list[AISystemGovernanceReviewSequenceStep]:
        return (
            self.db.execute(
                select(AISystemGovernanceReviewSequenceStep)
                .where(
                    AISystemGovernanceReviewSequenceStep.organization_id == organization_id,
                    AISystemGovernanceReviewSequenceStep.sequence_pack_id == pack_id,
                )
                .order_by(AISystemGovernanceReviewSequenceStep.step_order.asc(), AISystemGovernanceReviewSequenceStep.created_at.asc())
            )
            .scalars()
            .all()
        )

    def update_step(
        self,
        *,
        organization_id: uuid.UUID,
        row: AISystemGovernanceReviewSequenceStep,
        step_order: int | None,
        review_type: str | None,
        title_template: str | None,
        description_template: str | None,
        offset_days_from_start: int | None,
        default_reminder_policy_id: uuid.UUID | None,
        default_assigned_to_user_id: uuid.UUID | None,
        default_checklist_json: dict | list | None,
        require_previous_step_planned: bool | None,
        status_value: str | None,
    ) -> AISystemGovernanceReviewSequenceStep:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived sequence steps cannot be updated")

        effective_offset = offset_days_from_start if offset_days_from_start is not None else row.offset_days_from_start
        if effective_offset < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offset_days_from_start must be non-negative")

        self._validate_step_defaults(
            organization_id=organization_id,
            default_reminder_policy_id=default_reminder_policy_id,
            default_assigned_to_user_id=default_assigned_to_user_id,
        )

        effective_step_order = step_order if step_order is not None else row.step_order
        effective_status = status_value if status_value is not None else row.status
        if effective_status == "active":
            self._assert_active_step_order_available(
                organization_id=organization_id,
                pack_id=row.sequence_pack_id,
                step_order=effective_step_order,
                exclude_step_id=row.id,
            )

        if step_order is not None:
            row.step_order = step_order
        if review_type is not None:
            row.review_type = review_type
        if title_template is not None:
            row.title_template = title_template
        if description_template is not None:
            row.description_template = description_template
        if offset_days_from_start is not None:
            row.offset_days_from_start = offset_days_from_start
        if default_reminder_policy_id is not None:
            row.default_reminder_policy_id = default_reminder_policy_id
        if default_assigned_to_user_id is not None:
            row.default_assigned_to_user_id = default_assigned_to_user_id
        if default_checklist_json is not None:
            row.default_checklist_json = default_checklist_json
        if require_previous_step_planned is not None:
            row.require_previous_step_planned = require_previous_step_planned
        if status_value is not None:
            row.status = status_value
        self.db.flush()
        return row

    def archive_step(self, *, row: AISystemGovernanceReviewSequenceStep) -> AISystemGovernanceReviewSequenceStep:
        row.status = "archived"
        self.db.flush()
        return row

    def _target_ai_systems(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_ids: list[uuid.UUID] | None,
    ) -> list[AISystem]:
        if ai_system_ids is not None:
            all_in_org = (
                self.db.execute(
                    select(AISystem).where(
                        AISystem.organization_id == organization_id,
                        AISystem.id.in_(ai_system_ids),
                    )
                )
                .scalars()
                .all()
            )
            found = {row.id for row in all_in_org}
            missing = [item for item in ai_system_ids if item not in found]
            if missing:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more ai_system_ids not found")
            rows = [row for row in all_in_org if row.lifecycle_status != "archived"]
        else:
            rows = (
                self.db.execute(
                    select(AISystem).where(
                        AISystem.organization_id == organization_id,
                        AISystem.lifecycle_status != "archived",
                    )
                )
                .scalars()
                .all()
            )
        rows.sort(key=lambda row: str(row.id))
        return rows

    def _existing_review_key(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        review_type: str,
        due_at: datetime,
    ) -> bool:
        existing = self.db.execute(
            select(AISystemGovernanceReview).where(
                AISystemGovernanceReview.organization_id == organization_id,
                AISystemGovernanceReview.ai_system_id == ai_system_id,
                AISystemGovernanceReview.review_type == review_type,
                AISystemGovernanceReview.status != "cancelled",
                AISystemGovernanceReview.due_at == due_at,
            )
        ).scalar_one_or_none()
        return existing is not None

    def _select_constraints(
        self,
        *,
        organization_id: uuid.UUID,
        target_review_type: str,
        apply_constraints: bool,
    ) -> list[AISystemGovernanceReviewPlanConstraint]:
        if not apply_constraints:
            return []
        rows = (
            self.db.execute(
                select(AISystemGovernanceReviewPlanConstraint)
                .where(
                    AISystemGovernanceReviewPlanConstraint.organization_id == organization_id,
                    AISystemGovernanceReviewPlanConstraint.status == "active",
                    AISystemGovernanceReviewPlanConstraint.target_review_type == target_review_type,
                )
                .order_by(AISystemGovernanceReviewPlanConstraint.created_at.asc())
            )
            .scalars()
            .all()
        )
        return rows

    @staticmethod
    def _prerequisite_reference(review: AISystemGovernanceReview) -> datetime:
        if review.completed_at is not None:
            return review.completed_at
        if review.due_at is not None:
            return review.due_at
        return review.created_at

    def _evaluate_constraint(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        planned_due_at: datetime,
        constraint: AISystemGovernanceReviewPlanConstraint,
    ) -> dict[str, Any]:
        rows = (
            self.db.execute(
                select(AISystemGovernanceReview).where(
                    AISystemGovernanceReview.organization_id == organization_id,
                    AISystemGovernanceReview.ai_system_id == ai_system_id,
                    AISystemGovernanceReview.review_type == constraint.prerequisite_review_type,
                    AISystemGovernanceReview.status == "completed",
                )
            )
            .scalars()
            .all()
        )
        references = sorted([self.ensure_utc(self._prerequisite_reference(row)) for row in rows])
        references = [ref for ref in references if ref <= planned_due_at]

        result: dict[str, Any] = {
            "constraint_id": str(constraint.id),
            "name": constraint.name,
            "constraint_type": constraint.constraint_type,
            "enforcement_mode": constraint.enforcement_mode,
            "passed": True,
            "reason": None,
            "warning": False,
        }

        if not references:
            result["passed"] = False
            result["reason"] = "missing_completed_prerequisite"
            result["warning"] = constraint.enforcement_mode == "warn"
            return result

        if constraint.constraint_type == "prerequisite_completed":
            return result

        latest = references[-1]
        gap_days = max(0, (planned_due_at.date() - latest.date()).days)
        result["gap_days"] = gap_days
        if constraint.min_gap_days is not None and gap_days < constraint.min_gap_days:
            result["passed"] = False
            result["reason"] = "min_gap_not_satisfied"
        if constraint.max_gap_days is not None and gap_days > constraint.max_gap_days:
            result["passed"] = False
            result["reason"] = "max_gap_exceeded"
        if result["passed"] is False:
            result["warning"] = constraint.enforcement_mode == "warn"
        return result

    def _active_steps_for_pack(
        self,
        *,
        organization_id: uuid.UUID,
        pack_id: uuid.UUID,
    ) -> list[AISystemGovernanceReviewSequenceStep]:
        rows = (
            self.db.execute(
                select(AISystemGovernanceReviewSequenceStep)
                .where(
                    AISystemGovernanceReviewSequenceStep.organization_id == organization_id,
                    AISystemGovernanceReviewSequenceStep.sequence_pack_id == pack_id,
                    AISystemGovernanceReviewSequenceStep.status == "active",
                )
                .order_by(AISystemGovernanceReviewSequenceStep.step_order.asc(), AISystemGovernanceReviewSequenceStep.created_at.asc())
            )
            .scalars()
            .all()
        )
        return rows

    def generate_sequence(
        self,
        *,
        organization_id: uuid.UUID,
        pack: AISystemGovernanceReviewSequencePack,
        dry_run: bool,
        ai_system_ids: list[uuid.UUID] | None,
        start_from: datetime | date | None,
        apply_constraints: bool,
        acknowledgement_text: str | None,
        override_freeze: bool,
        override_reason: str | None,
        guardrail_policy_set_id: uuid.UUID | None,
        rollout_class: str | None,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        if pack.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sequence pack must be active")

        start_at = self.normalize_start_from(start_from)
        steps = self._active_steps_for_pack(organization_id=organization_id, pack_id=pack.id)
        if not steps:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sequence pack has no active steps")

        targets = self._target_ai_systems(organization_id=organization_id, ai_system_ids=ai_system_ids)
        planned_end = start_at + timedelta(days=max(step.offset_days_from_start for step in steps))
        guardrail_results = self.evaluate_guardrails(
            organization_id=organization_id,
            action_type="sequence_apply",
            sequence_pack_id=pack.id,
            recurrence_template_id=None,
            ai_system_ids=[row.id for row in targets],
            review_types=sorted({step.review_type for step in steps}),
            planned_start=start_at,
            planned_end=planned_end,
            rollout_class=rollout_class,
            policy_set_id=guardrail_policy_set_id,
        )
        operator_acknowledgement: AISystemGovernanceOperatorAcknowledgement | None = None
        guardrail_resolution = guardrail_results["resolution"]
        required_ack_text = guardrail_results["required_acknowledgement_text"] or FREEZE_ACK_TEXT
        if not dry_run and guardrail_resolution["blocked"]:
            if not guardrail_resolution["override_allowed"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Active blocking freeze window does not allow override",
                )
            if acknowledgement_text != required_ack_text:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"acknowledgement_text must be exactly {required_ack_text}",
                )
            if override_freeze is not True:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="override_freeze must be true during active freeze")
            if guardrail_results["require_override_reason"] and (not override_reason or not override_reason.strip()):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="override_reason is required during active freeze")
            operator_acknowledgement = self.create_operator_acknowledgement(
                organization_id=organization_id,
                action_type="sequence_apply",
                target_type="sequence_pack",
                target_id=pack.id,
                acknowledgement_text=acknowledgement_text,
                reason=override_reason.strip() if override_reason else None,
                override_freeze=True,
                freeze_window_ids=[
                    item["id"]
                    for item in guardrail_results["matching_freeze_windows"]
                    if item["enforcement_level"] == "block"
                ],
                actor_user_id=actor_user_id,
            )

        planned_reviews: list[dict[str, Any]] = []
        skipped_reviews: list[dict[str, Any]] = []
        created_count = 0

        for ai_system in targets:
            previous_step_planned = True
            has_previous = False
            for step in steps:
                due_at = start_at + timedelta(days=step.offset_days_from_start)
                constraint_results: list[dict[str, Any]] = []

                if has_previous and step.require_previous_step_planned and not previous_step_planned:
                    skipped_reviews.append(
                        {
                            "ai_system_id": ai_system.id,
                            "step_id": step.id,
                            "step_order": step.step_order,
                            "review_type": step.review_type,
                            "due_at": due_at,
                            "reason": "previous_step_not_planned",
                            "constraint_results": [],
                        }
                    )
                    previous_step_planned = False
                    has_previous = True
                    continue

                if self._existing_review_key(
                    organization_id=organization_id,
                    ai_system_id=ai_system.id,
                    review_type=step.review_type,
                    due_at=due_at,
                ):
                    skipped_reviews.append(
                        {
                            "ai_system_id": ai_system.id,
                            "step_id": step.id,
                            "step_order": step.step_order,
                            "review_type": step.review_type,
                            "due_at": due_at,
                            "reason": "duplicate_existing_review",
                            "constraint_results": [],
                        }
                    )
                    previous_step_planned = False
                    has_previous = True
                    continue

                constraints = self._select_constraints(
                    organization_id=organization_id,
                    target_review_type=step.review_type,
                    apply_constraints=apply_constraints,
                )
                constraint_results = [
                    self._evaluate_constraint(
                        organization_id=organization_id,
                        ai_system_id=ai_system.id,
                        planned_due_at=due_at,
                        constraint=constraint,
                    )
                    for constraint in constraints
                ]
                blocked = any(
                    result["passed"] is False and result["enforcement_mode"] == "block"
                    for result in constraint_results
                )
                if blocked:
                    skipped_reviews.append(
                        {
                            "ai_system_id": ai_system.id,
                            "step_id": step.id,
                            "step_order": step.step_order,
                            "review_type": step.review_type,
                            "due_at": due_at,
                            "reason": "constraint_blocked",
                            "constraint_results": constraint_results,
                        }
                    )
                    previous_step_planned = False
                    has_previous = True
                    continue

                title = step.title_template or f"{pack.name}: {step.review_type}"
                planned_item = {
                    "ai_system_id": ai_system.id,
                    "step_id": step.id,
                    "step_order": step.step_order,
                    "review_type": step.review_type,
                    "title": title,
                    "due_at": due_at,
                    "assigned_to_user_id": step.default_assigned_to_user_id,
                    "reminder_policy_id": step.default_reminder_policy_id,
                    "constraint_results": constraint_results,
                }
                planned_reviews.append(planned_item)

                if not dry_run:
                    review = AISystemGovernanceReview(
                        organization_id=organization_id,
                        ai_system_id=ai_system.id,
                        review_type=step.review_type,
                        status="pending",
                        outcome=None,
                        title=title,
                        description=step.description_template,
                        checklist_json=step.default_checklist_json,
                        requested_by_user_id=actor_user_id,
                        assigned_to_user_id=step.default_assigned_to_user_id,
                        caveat=(
                            "This governance review is a manual internal CompliVibe governance checkpoint. "
                            "It is not legal advice, regulatory approval, or certification."
                        ),
                        due_at=due_at,
                        reminder_policy_id=step.default_reminder_policy_id,
                    )
                    self.db.add(review)
                    created_count += 1

                previous_step_planned = True
                has_previous = True

        result_json = {
            "dry_run": dry_run,
            "sequence_pack_id": str(pack.id),
            "start_from": start_at.isoformat(),
            "apply_constraints": apply_constraints,
            "guardrail_results": {
                "blocked": guardrail_results["blocked"],
                "matching_freeze_windows": [
                    {
                        "id": str(item["id"]),
                        "name": item["name"],
                        "scope_type": item["scope_type"],
                        "starts_at": item["starts_at"].isoformat(),
                        "ends_at": item["ends_at"].isoformat(),
                        "reason": item["reason"],
                    }
                    for item in guardrail_results["matching_freeze_windows"]
                ],
                "warnings": guardrail_results["warnings"],
                "resolution": {
                    "blocked": guardrail_results["resolution"]["blocked"],
                    "primary_blocking_window_id": (
                        str(guardrail_results["resolution"]["primary_blocking_window_id"])
                        if guardrail_results["resolution"]["primary_blocking_window_id"] is not None
                        else None
                    ),
                    "override_allowed": guardrail_results["resolution"]["override_allowed"],
                    "enforcement_level": guardrail_results["resolution"]["enforcement_level"],
                    "precedence_order": guardrail_results["resolution"]["precedence_order"],
                    "matching_window_count": guardrail_results["resolution"]["matching_window_count"],
                    "warnings": guardrail_results["resolution"]["warnings"],
                    "info": guardrail_results["resolution"]["info"],
                },
                "required_acknowledgement_text": guardrail_results["required_acknowledgement_text"],
                "caveat": guardrail_results["caveat"],
                "policy_set_id": str(guardrail_results["policy_set_id"]) if guardrail_results["policy_set_id"] else None,
                "policy_version_id": str(guardrail_results["policy_version_id"]) if guardrail_results["policy_version_id"] else None,
                "policy_resolution": {
                    "resolved_policy_set_id": (
                        str(guardrail_results["policy_resolution"]["resolved_policy_set_id"])
                        if guardrail_results["policy_resolution"]["resolved_policy_set_id"]
                        else None
                    ),
                    "resolved_policy_version_id": (
                        str(guardrail_results["policy_resolution"]["resolved_policy_version_id"])
                        if guardrail_results["policy_resolution"]["resolved_policy_version_id"]
                        else None
                    ),
                    "resolution_source": guardrail_results["policy_resolution"]["resolution_source"],
                    "assignment_id": (
                        str(guardrail_results["policy_resolution"]["assignment_id"])
                        if guardrail_results["policy_resolution"]["assignment_id"]
                        else None
                    ),
                    "precedence_trace": guardrail_results["policy_resolution"]["precedence_trace"],
                    "caveat": guardrail_results["policy_resolution"]["caveat"],
                },
                "require_override_reason": guardrail_results["require_override_reason"],
            },
            "planned_count": len(planned_reviews),
            "created_count": 0 if dry_run else created_count,
            "skipped_count": len(skipped_reviews),
            "planned_reviews": [
                {
                    "ai_system_id": str(item["ai_system_id"]),
                    "step_id": str(item["step_id"]),
                    "step_order": item["step_order"],
                    "review_type": item["review_type"],
                    "title": item["title"],
                    "due_at": item["due_at"].isoformat(),
                    "assigned_to_user_id": str(item["assigned_to_user_id"]) if item["assigned_to_user_id"] else None,
                    "reminder_policy_id": str(item["reminder_policy_id"]) if item["reminder_policy_id"] else None,
                    "constraint_results": item["constraint_results"],
                }
                for item in planned_reviews
            ],
            "skipped_reviews": [
                {
                    "ai_system_id": str(item["ai_system_id"]),
                    "step_id": str(item["step_id"]),
                    "step_order": item["step_order"],
                    "review_type": item["review_type"],
                    "due_at": item["due_at"].isoformat(),
                    "reason": item["reason"],
                    "constraint_results": item["constraint_results"],
                }
                for item in skipped_reviews
            ],
            "caveat": SEQUENCE_CAVEAT,
        }

        run = AISystemGovernanceReviewSequenceRun(
            organization_id=organization_id,
            sequence_pack_id=pack.id,
            status="previewed" if dry_run else "applied",
            dry_run=dry_run,
            target_ai_system_ids_json=[str(item.id) for item in targets] if ai_system_ids is not None else None,
            start_from=start_at,
            apply_constraints=apply_constraints,
            generated_reviews_count=len(planned_reviews) if dry_run else created_count,
            skipped_reviews_count=len(skipped_reviews),
            result_json=result_json,
            requested_by_user_id=actor_user_id,
        )
        self.db.add(run)
        self.db.flush()

        return {
            "dry_run": dry_run,
            "sequence_pack_id": pack.id,
            "planned_count": len(planned_reviews),
            "created_count": 0 if dry_run else created_count,
            "skipped_count": len(skipped_reviews),
            "planned_reviews": planned_reviews,
            "skipped_reviews": skipped_reviews,
            "run_id": run.id,
            "guardrail_results": {
                "blocked": guardrail_results["blocked"],
                "matching_freeze_windows": guardrail_results["matching_freeze_windows"],
                "warnings": guardrail_results["warnings"],
                "resolution": guardrail_results["resolution"],
                "required_acknowledgement_text": guardrail_results["required_acknowledgement_text"],
                "caveat": guardrail_results["caveat"],
                "policy_set_id": guardrail_results["policy_set_id"],
                "policy_version_id": guardrail_results["policy_version_id"],
                "policy_resolution": guardrail_results["policy_resolution"],
                "require_override_reason": guardrail_results["require_override_reason"],
            },
            "operator_acknowledgement": operator_acknowledgement,
            "caveat": SEQUENCE_CAVEAT,
        }

    def list_runs(
        self,
        *,
        organization_id: uuid.UUID,
        sequence_pack_id: uuid.UUID | None,
        status_filter: str | None,
        dry_run: bool | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceReviewSequenceRun]:
        stmt = select(AISystemGovernanceReviewSequenceRun).where(
            AISystemGovernanceReviewSequenceRun.organization_id == organization_id,
        )
        if sequence_pack_id is not None:
            stmt = stmt.where(AISystemGovernanceReviewSequenceRun.sequence_pack_id == sequence_pack_id)
        if status_filter:
            stmt = stmt.where(AISystemGovernanceReviewSequenceRun.status == status_filter)
        if dry_run is not None:
            stmt = stmt.where(AISystemGovernanceReviewSequenceRun.dry_run == dry_run)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceReviewSequenceRun.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def guardrail_summary(self, *, organization_id: uuid.UUID) -> dict[str, int | dict[str, int]]:
        now = self.now()
        active_freeze_windows = int(
            self.db.execute(
                select(func.count(AISystemGovernanceFreezeWindow.id)).where(
                    AISystemGovernanceFreezeWindow.organization_id == organization_id,
                    AISystemGovernanceFreezeWindow.status == "active",
                )
            ).scalar_one()
        )
        inactive_freeze_windows = int(
            self.db.execute(
                select(func.count(AISystemGovernanceFreezeWindow.id)).where(
                    AISystemGovernanceFreezeWindow.organization_id == organization_id,
                    AISystemGovernanceFreezeWindow.status == "inactive",
                )
            ).scalar_one()
        )
        archived_freeze_windows = int(
            self.db.execute(
                select(func.count(AISystemGovernanceFreezeWindow.id)).where(
                    AISystemGovernanceFreezeWindow.organization_id == organization_id,
                    AISystemGovernanceFreezeWindow.status == "archived",
                )
            ).scalar_one()
        )
        active_now_freeze_windows = int(
            self.db.execute(
                select(func.count(AISystemGovernanceFreezeWindow.id)).where(
                    AISystemGovernanceFreezeWindow.organization_id == organization_id,
                    AISystemGovernanceFreezeWindow.status == "active",
                    AISystemGovernanceFreezeWindow.starts_at <= now,
                    AISystemGovernanceFreezeWindow.ends_at >= now,
                )
            ).scalar_one()
        )
        acknowledgements_total = int(
            self.db.execute(
                select(func.count(AISystemGovernanceOperatorAcknowledgement.id)).where(
                    AISystemGovernanceOperatorAcknowledgement.organization_id == organization_id,
                )
            ).scalar_one()
        )
        freeze_overrides_total = int(
            self.db.execute(
                select(func.count(AISystemGovernanceOperatorAcknowledgement.id)).where(
                    AISystemGovernanceOperatorAcknowledgement.organization_id == organization_id,
                    AISystemGovernanceOperatorAcknowledgement.override_freeze.is_(True),
                )
            ).scalar_one()
        )
        block_freeze_windows = int(
            self.db.execute(
                select(func.count(AISystemGovernanceFreezeWindow.id)).where(
                    AISystemGovernanceFreezeWindow.organization_id == organization_id,
                    AISystemGovernanceFreezeWindow.enforcement_level == "block",
                    AISystemGovernanceFreezeWindow.status != "archived",
                )
            ).scalar_one()
        )
        warn_freeze_windows = int(
            self.db.execute(
                select(func.count(AISystemGovernanceFreezeWindow.id)).where(
                    AISystemGovernanceFreezeWindow.organization_id == organization_id,
                    AISystemGovernanceFreezeWindow.enforcement_level == "warn",
                    AISystemGovernanceFreezeWindow.status != "archived",
                )
            ).scalar_one()
        )
        info_freeze_windows = int(
            self.db.execute(
                select(func.count(AISystemGovernanceFreezeWindow.id)).where(
                    AISystemGovernanceFreezeWindow.organization_id == organization_id,
                    AISystemGovernanceFreezeWindow.enforcement_level == "info",
                    AISystemGovernanceFreezeWindow.status != "archived",
                )
            ).scalar_one()
        )
        override_disallowed_windows = int(
            self.db.execute(
                select(func.count(AISystemGovernanceFreezeWindow.id)).where(
                    AISystemGovernanceFreezeWindow.organization_id == organization_id,
                    AISystemGovernanceFreezeWindow.override_allowed.is_(False),
                    AISystemGovernanceFreezeWindow.status != "archived",
                )
            ).scalar_one()
        )
        highest_priority_value = self.db.execute(
            select(func.max(AISystemGovernanceFreezeWindow.priority)).where(
                AISystemGovernanceFreezeWindow.organization_id == organization_id,
            )
        ).scalar_one()
        by_scope_rows = self.db.execute(
            select(AISystemGovernanceFreezeWindow.scope_type, func.count(AISystemGovernanceFreezeWindow.id))
            .where(AISystemGovernanceFreezeWindow.organization_id == organization_id)
            .group_by(AISystemGovernanceFreezeWindow.scope_type)
        ).all()
        return {
            "active_freeze_windows": active_freeze_windows,
            "inactive_freeze_windows": inactive_freeze_windows,
            "archived_freeze_windows": archived_freeze_windows,
            "active_now_freeze_windows": active_now_freeze_windows,
            "block_freeze_windows": block_freeze_windows,
            "warn_freeze_windows": warn_freeze_windows,
            "info_freeze_windows": info_freeze_windows,
            "override_disallowed_windows": override_disallowed_windows,
            "highest_priority": int(highest_priority_value or 0),
            "acknowledgements_total": acknowledgements_total,
            "freeze_overrides_total": freeze_overrides_total,
            "by_scope_type": {str(key): int(count) for key, count in by_scope_rows if key is not None},
        }

    def policy_set_summary(self, *, organization_id: uuid.UUID) -> dict[str, int]:
        active_policy_sets = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicySet.id)).where(
                    AISystemGovernanceGuardrailPolicySet.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicySet.status == "active",
                )
            ).scalar_one()
        )
        inactive_policy_sets = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicySet.id)).where(
                    AISystemGovernanceGuardrailPolicySet.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicySet.status == "inactive",
                )
            ).scalar_one()
        )
        archived_policy_sets = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicySet.id)).where(
                    AISystemGovernanceGuardrailPolicySet.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicySet.status == "archived",
                )
            ).scalar_one()
        )
        total_versions = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicySetVersion.id)).where(
                    AISystemGovernanceGuardrailPolicySetVersion.organization_id == organization_id,
                )
            ).scalar_one()
        )
        active_versions = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicySetVersion.id)).where(
                    AISystemGovernanceGuardrailPolicySetVersion.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicySetVersion.status == "active",
                )
            ).scalar_one()
        )
        draft_versions = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicySetVersion.id)).where(
                    AISystemGovernanceGuardrailPolicySetVersion.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicySetVersion.status == "draft",
                )
            ).scalar_one()
        )
        deprecated_versions = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicySetVersion.id)).where(
                    AISystemGovernanceGuardrailPolicySetVersion.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicySetVersion.status == "deprecated",
                )
            ).scalar_one()
        )
        policy_sets_without_active_version = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicySet.id)).where(
                    AISystemGovernanceGuardrailPolicySet.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicySet.status != "archived",
                    AISystemGovernanceGuardrailPolicySet.active_version_id.is_(None),
                )
            ).scalar_one()
        )
        return {
            "active_policy_sets": active_policy_sets,
            "inactive_policy_sets": inactive_policy_sets,
            "archived_policy_sets": archived_policy_sets,
            "total_versions": total_versions,
            "active_versions": active_versions,
            "draft_versions": draft_versions,
            "deprecated_versions": deprecated_versions,
            "policy_sets_without_active_version": policy_sets_without_active_version,
        }

    def create_policy_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        policy_set_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        scope_json: dict | list | None,
        priority: int,
        reason: str,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicyAssignment:
        policy_set = self.require_policy_set(organization_id=organization_id, policy_set_id=policy_set_id)
        if policy_set.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived guardrail policy sets cannot be assigned")
        normalized_scope_id, normalized_scope_json = self._validate_policy_assignment_scope(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            scope_json=scope_json,
        )
        if status_value == "active":
            self._assert_no_duplicate_active_policy_assignment(
                organization_id=organization_id,
                scope_type=scope_type,
                scope_id=normalized_scope_id,
                scope_json=normalized_scope_json,
            )
        row = AISystemGovernanceGuardrailPolicyAssignment(
            organization_id=organization_id,
            policy_set_id=policy_set_id,
            scope_type=scope_type,
            scope_id=normalized_scope_id,
            scope_json=normalized_scope_json,
            priority=priority,
            status=status_value,
            reason=reason,
            assigned_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        self._create_policy_assignment_history(
            organization_id=organization_id,
            assignment_id=row.id,
            event_type="created",
            before_json=None,
            after_json=self._assignment_snapshot(row),
            reason=reason,
            actor_user_id=actor_user_id,
        )
        return row

    def list_policy_assignments(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        scope_type: str | None,
        policy_set_id: uuid.UUID | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceGuardrailPolicyAssignment]:
        stmt = select(AISystemGovernanceGuardrailPolicyAssignment).where(
            AISystemGovernanceGuardrailPolicyAssignment.organization_id == organization_id,
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernanceGuardrailPolicyAssignment.status == status_filter)
        if scope_type is not None:
            stmt = stmt.where(AISystemGovernanceGuardrailPolicyAssignment.scope_type == scope_type)
        if policy_set_id is not None:
            stmt = stmt.where(AISystemGovernanceGuardrailPolicyAssignment.policy_set_id == policy_set_id)
        if not include_archived:
            stmt = stmt.where(AISystemGovernanceGuardrailPolicyAssignment.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(
                    AISystemGovernanceGuardrailPolicyAssignment.priority.desc(),
                    AISystemGovernanceGuardrailPolicyAssignment.updated_at.desc(),
                    AISystemGovernanceGuardrailPolicyAssignment.id.asc(),
                )
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def update_policy_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        row: AISystemGovernanceGuardrailPolicyAssignment,
        updates: dict[str, Any],
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicyAssignment:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived policy assignments cannot be updated")
        before = self._assignment_snapshot(row)
        effective_policy_set_id = updates.get("policy_set_id", row.policy_set_id)
        policy_set = self.require_policy_set(organization_id=organization_id, policy_set_id=effective_policy_set_id)
        if policy_set.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived guardrail policy sets cannot be assigned")
        effective_scope_type = updates.get("scope_type", row.scope_type)
        effective_scope_id = updates["scope_id"] if "scope_id" in updates else row.scope_id
        effective_scope_json = updates["scope_json"] if "scope_json" in updates else row.scope_json
        normalized_scope_id, normalized_scope_json = self._validate_policy_assignment_scope(
            organization_id=organization_id,
            scope_type=effective_scope_type,
            scope_id=effective_scope_id,
            scope_json=effective_scope_json,
        )
        effective_status = updates.get("status", row.status)
        if effective_status == "active":
            self._assert_no_duplicate_active_policy_assignment(
                organization_id=organization_id,
                scope_type=effective_scope_type,
                scope_id=normalized_scope_id,
                scope_json=normalized_scope_json,
                exclude_assignment_id=row.id,
            )
        row.policy_set_id = effective_policy_set_id
        row.scope_type = effective_scope_type
        row.scope_id = normalized_scope_id
        row.scope_json = normalized_scope_json
        if "priority" in updates:
            row.priority = int(updates["priority"])
        row.status = effective_status
        if "reason" in updates and updates["reason"] is not None:
            row.reason = updates["reason"]
        self.db.flush()
        self._create_policy_assignment_history(
            organization_id=organization_id,
            assignment_id=row.id,
            event_type="updated",
            before_json=before,
            after_json=self._assignment_snapshot(row),
            reason=updates.get("reason") or row.reason,
            actor_user_id=actor_user_id,
        )
        return row

    def archive_policy_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        row: AISystemGovernanceGuardrailPolicyAssignment,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceGuardrailPolicyAssignment:
        before = self._assignment_snapshot(row)
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        self._create_policy_assignment_history(
            organization_id=organization_id,
            assignment_id=row.id,
            event_type="archived",
            before_json=before,
            after_json=self._assignment_snapshot(row),
            reason=reason,
            actor_user_id=actor_user_id,
        )
        return row

    def list_policy_assignment_history(
        self,
        *,
        organization_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> list[AISystemGovernanceGuardrailPolicyAssignmentHistory]:
        return (
            self.db.execute(
                select(AISystemGovernanceGuardrailPolicyAssignmentHistory)
                .where(
                    AISystemGovernanceGuardrailPolicyAssignmentHistory.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicyAssignmentHistory.assignment_id == assignment_id,
                )
                .order_by(AISystemGovernanceGuardrailPolicyAssignmentHistory.created_at.desc())
            )
            .scalars()
            .all()
        )

    def _assignment_candidates_for_scope(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID],
        review_types: list[str],
        rollout_class: str | None,
    ) -> list[AISystemGovernanceGuardrailPolicyAssignment]:
        stmt = select(AISystemGovernanceGuardrailPolicyAssignment).where(
            AISystemGovernanceGuardrailPolicyAssignment.organization_id == organization_id,
            AISystemGovernanceGuardrailPolicyAssignment.status == "active",
            AISystemGovernanceGuardrailPolicyAssignment.scope_type == scope_type,
        )
        if scope_type == "sequence_pack":
            if sequence_pack_id is None:
                return []
            stmt = stmt.where(AISystemGovernanceGuardrailPolicyAssignment.scope_id == sequence_pack_id)
        elif scope_type == "ai_system":
            if not ai_system_ids:
                return []
            stmt = stmt.where(AISystemGovernanceGuardrailPolicyAssignment.scope_id.in_(ai_system_ids))
        elif scope_type in {"review_type", "rollout_class"}:
            pass
        elif scope_type == "all_ai_governance":
            pass
        else:
            return []
        rows = self.db.execute(
            stmt.order_by(
                AISystemGovernanceGuardrailPolicyAssignment.priority.desc(),
                AISystemGovernanceGuardrailPolicyAssignment.updated_at.desc(),
                AISystemGovernanceGuardrailPolicyAssignment.id.asc(),
            )
        ).scalars().all()
        if scope_type == "review_type":
            return [
                row
                for row in rows
                if self._extract_scope_value(scope_type=scope_type, scope_id=row.scope_id, scope_json=row.scope_json) in review_types
            ]
        if scope_type == "rollout_class":
            if not rollout_class:
                return []
            return [
                row
                for row in rows
                if self._extract_scope_value(scope_type=scope_type, scope_id=row.scope_id, scope_json=row.scope_json) == rollout_class
            ]
        return rows

    def resolve_policy_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        explicit_policy_set_id: uuid.UUID | None,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID] | None,
        review_types: list[str] | None,
        rollout_class: str | None,
    ) -> dict[str, Any]:
        ai_ids = sorted({item for item in (ai_system_ids or [])}, key=lambda item: str(item))
        review_type_values = sorted({item for item in (review_types or [])})
        if sequence_pack_id is not None:
            self.require_pack(organization_id=organization_id, pack_id=sequence_pack_id)
        if ai_ids:
            found = self.db.execute(
                select(AISystem.id).where(
                    AISystem.organization_id == organization_id,
                    AISystem.id.in_(ai_ids),
                )
            ).scalars().all()
            if len(found) != len(ai_ids):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more ai_system_ids not found")
        if any(item not in REVIEW_TYPES for item in review_type_values):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="review_types contains invalid review type")

        precedence_trace: list[dict[str, Any]] = []
        if explicit_policy_set_id is not None:
            policy_set, policy_version = self.get_active_policy_profile(
                organization_id=organization_id,
                policy_set_id=explicit_policy_set_id,
            )
            precedence_trace.append(
                {
                    "scope_type": "explicit_request",
                    "matched": True,
                    "policy_set_id": str(policy_set.id),
                    "policy_version_id": str(policy_version.id),
                }
            )
            return {
                "resolved_policy_set_id": policy_set.id,
                "resolved_policy_version_id": policy_version.id,
                "resolution_source": "explicit_request",
                "assignment_id": None,
                "precedence_trace": precedence_trace,
                "caveat": GUARDRAIL_POLICY_ASSIGNMENT_CAVEAT,
                "profile_json": policy_version.profile_json,
            }

        for scope_type, source in POLICY_ASSIGNMENT_SCOPE_PRECEDENCE:
            candidates = self._assignment_candidates_for_scope(
                organization_id=organization_id,
                scope_type=scope_type,
                sequence_pack_id=sequence_pack_id,
                ai_system_ids=ai_ids,
                review_types=review_type_values,
                rollout_class=rollout_class.strip() if isinstance(rollout_class, str) else None,
            )
            precedence_trace.append(
                {
                    "scope_type": scope_type,
                    "source": source,
                    "candidate_assignment_ids": [str(item.id) for item in candidates],
                    "matched": bool(candidates),
                }
            )
            if not candidates:
                continue
            selected = candidates[0]
            policy_set, policy_version = self.get_active_policy_profile(
                organization_id=organization_id,
                policy_set_id=selected.policy_set_id,
            )
            precedence_trace[-1]["selected_assignment_id"] = str(selected.id)
            precedence_trace[-1]["selected_policy_set_id"] = str(policy_set.id)
            precedence_trace[-1]["selected_policy_version_id"] = str(policy_version.id)
            return {
                "resolved_policy_set_id": policy_set.id,
                "resolved_policy_version_id": policy_version.id,
                "resolution_source": source,
                "assignment_id": selected.id,
                "precedence_trace": precedence_trace,
                "caveat": GUARDRAIL_POLICY_ASSIGNMENT_CAVEAT,
                "profile_json": policy_version.profile_json,
            }

        return {
            "resolved_policy_set_id": None,
            "resolved_policy_version_id": None,
            "resolution_source": "none",
            "assignment_id": None,
            "precedence_trace": precedence_trace,
            "caveat": GUARDRAIL_POLICY_ASSIGNMENT_CAVEAT,
            "profile_json": None,
        }

    def policy_assignment_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        active_assignments = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicyAssignment.id)).where(
                    AISystemGovernanceGuardrailPolicyAssignment.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicyAssignment.status == "active",
                )
            ).scalar_one()
        )
        inactive_assignments = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicyAssignment.id)).where(
                    AISystemGovernanceGuardrailPolicyAssignment.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicyAssignment.status == "inactive",
                )
            ).scalar_one()
        )
        archived_assignments = int(
            self.db.execute(
                select(func.count(AISystemGovernanceGuardrailPolicyAssignment.id)).where(
                    AISystemGovernanceGuardrailPolicyAssignment.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicyAssignment.status == "archived",
                )
            ).scalar_one()
        )
        by_scope_rows = self.db.execute(
            select(
                AISystemGovernanceGuardrailPolicyAssignment.scope_type,
                func.count(AISystemGovernanceGuardrailPolicyAssignment.id),
            )
            .where(AISystemGovernanceGuardrailPolicyAssignment.organization_id == organization_id)
            .group_by(AISystemGovernanceGuardrailPolicyAssignment.scope_type)
        ).all()
        missing_active_version_rows = (
            self.db.execute(
                select(AISystemGovernanceGuardrailPolicyAssignment).where(
                    AISystemGovernanceGuardrailPolicyAssignment.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicyAssignment.status == "active",
                )
            )
            .scalars()
            .all()
        )
        assignments_without_active_policy_version = 0
        for row in missing_active_version_rows:
            policy_set = self.db.execute(
                select(AISystemGovernanceGuardrailPolicySet).where(
                    AISystemGovernanceGuardrailPolicySet.organization_id == organization_id,
                    AISystemGovernanceGuardrailPolicySet.id == row.policy_set_id,
                )
            ).scalar_one_or_none()
            if policy_set is None or policy_set.active_version_id is None:
                assignments_without_active_policy_version += 1

        highest_priority_value = self.db.execute(
            select(func.max(AISystemGovernanceGuardrailPolicyAssignment.priority)).where(
                AISystemGovernanceGuardrailPolicyAssignment.organization_id == organization_id,
            )
        ).scalar_one()
        return {
            "active_assignments": active_assignments,
            "inactive_assignments": inactive_assignments,
            "archived_assignments": archived_assignments,
            "by_scope_type": {str(key): int(count) for key, count in by_scope_rows if key is not None},
            "assignments_without_active_policy_version": int(assignments_without_active_policy_version),
            "highest_priority": int(highest_priority_value or 0),
            "caveat": GUARDRAIL_POLICY_ASSIGNMENT_CAVEAT,
        }

    @staticmethod
    def _serialize_simulation_context(context: dict[str, Any]) -> dict[str, Any]:
        return {
            "context_key": context.get("context_key"),
            "explicit_policy_set_id": str(context["explicit_policy_set_id"]) if context.get("explicit_policy_set_id") else None,
            "sequence_pack_id": str(context["sequence_pack_id"]) if context.get("sequence_pack_id") else None,
            "ai_system_ids": [str(item) for item in (context.get("ai_system_ids") or [])],
            "review_types": context.get("review_types") or [],
            "rollout_class": context.get("rollout_class"),
            "planned_start": context["planned_start"].isoformat() if context.get("planned_start") else None,
            "planned_end": context["planned_end"].isoformat() if context.get("planned_end") else None,
        }

    @staticmethod
    def _serialize_policy_resolution(policy_resolution: dict[str, Any]) -> dict[str, Any]:
        return {
            "resolved_policy_set_id": (
                str(policy_resolution["resolved_policy_set_id"]) if policy_resolution.get("resolved_policy_set_id") else None
            ),
            "resolved_policy_version_id": (
                str(policy_resolution["resolved_policy_version_id"]) if policy_resolution.get("resolved_policy_version_id") else None
            ),
            "resolution_source": policy_resolution.get("resolution_source"),
            "assignment_id": str(policy_resolution["assignment_id"]) if policy_resolution.get("assignment_id") else None,
            "precedence_trace": policy_resolution.get("precedence_trace") or [],
            "caveat": policy_resolution.get("caveat"),
        }

    def run_policy_resolution_simulation(
        self,
        *,
        organization_id: uuid.UUID,
        title: str | None,
        description: str | None,
        persist_report: bool,
        contexts: list[dict[str, Any]],
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        if not contexts:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contexts must not be empty")
        if len(contexts) > 100:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="contexts must be <= 100")

        simulated_contexts: list[dict[str, Any]] = []
        blocked_count = 0
        warning_count = 0
        no_policy_count = 0

        for context in contexts:
            context_key = context.get("context_key")
            guardrail_result = self.evaluate_guardrails(
                organization_id=organization_id,
                action_type="sequence_apply",
                sequence_pack_id=context.get("sequence_pack_id"),
                recurrence_template_id=None,
                ai_system_ids=context.get("ai_system_ids"),
                review_types=context.get("review_types"),
                planned_start=context.get("planned_start"),
                planned_end=context.get("planned_end"),
                rollout_class=context.get("rollout_class"),
                policy_set_id=context.get("explicit_policy_set_id"),
            )
            policy_resolution = self._serialize_policy_resolution(guardrail_result["policy_resolution"])
            guardrail_resolution = guardrail_result["resolution"]
            if guardrail_resolution["blocked"]:
                blocked_count += 1
            if guardrail_resolution["warnings"] or guardrail_resolution["info"]:
                warning_count += 1
            if policy_resolution["resolution_source"] == "none":
                no_policy_count += 1

            simulated_contexts.append(
                {
                    "context_key": context_key,
                    "policy_resolution": policy_resolution,
                    "guardrail_resolution": {
                        "blocked": guardrail_result["blocked"],
                        "resolution": guardrail_resolution,
                        "warnings": guardrail_result["warnings"],
                    },
                    "precedence_trace": policy_resolution["precedence_trace"],
                    "caveat": POLICY_RESOLUTION_SIMULATION_CAVEAT,
                }
            )

        report: AISystemGovernancePolicyResolutionSimulationReport | None = None
        if persist_report:
            report_title = title.strip() if isinstance(title, str) and title.strip() else f"Policy resolution simulation {self.now().isoformat()}"
            report = AISystemGovernancePolicyResolutionSimulationReport(
                organization_id=organization_id,
                title=report_title,
                description=description,
                status="generated",
                requested_by_user_id=actor_user_id,
                input_contexts_json=[self._serialize_simulation_context(item) for item in contexts],
                result_json=self.json_safe(
                    {
                    "contexts": simulated_contexts,
                    "context_count": len(simulated_contexts),
                    "blocked_contexts_count": blocked_count,
                    "warning_contexts_count": warning_count,
                    "no_policy_contexts_count": no_policy_count,
                    "caveat": POLICY_RESOLUTION_SIMULATION_CAVEAT,
                    }
                ),
                context_count=len(simulated_contexts),
                blocked_contexts_count=blocked_count,
                warning_contexts_count=warning_count,
                no_policy_contexts_count=no_policy_count,
            )
            self.db.add(report)
            self.db.flush()

        return {
            "persisted": persist_report,
            "report_id": report.id if report is not None else None,
            "context_count": len(simulated_contexts),
            "blocked_contexts_count": blocked_count,
            "warning_contexts_count": warning_count,
            "no_policy_contexts_count": no_policy_count,
            "contexts": simulated_contexts,
            "caveat": POLICY_RESOLUTION_SIMULATION_CAVEAT,
        }

    def list_policy_resolution_simulation_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePolicyResolutionSimulationReport]:
        stmt = select(AISystemGovernancePolicyResolutionSimulationReport).where(
            AISystemGovernancePolicyResolutionSimulationReport.organization_id == organization_id,
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePolicyResolutionSimulationReport.status == status_filter)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePolicyResolutionSimulationReport.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_policy_resolution_simulation_report(
        self,
        *,
        row: AISystemGovernancePolicyResolutionSimulationReport,
    ) -> AISystemGovernancePolicyResolutionSimulationReport:
        row.status = "archived"
        self.db.flush()
        return row

    def policy_resolution_simulation_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        total_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyResolutionSimulationReport.id)).where(
                    AISystemGovernancePolicyResolutionSimulationReport.organization_id == organization_id,
                )
            ).scalar_one()
        )
        active_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyResolutionSimulationReport.id)).where(
                    AISystemGovernancePolicyResolutionSimulationReport.organization_id == organization_id,
                    AISystemGovernancePolicyResolutionSimulationReport.status == "generated",
                )
            ).scalar_one()
        )
        archived_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyResolutionSimulationReport.id)).where(
                    AISystemGovernancePolicyResolutionSimulationReport.organization_id == organization_id,
                    AISystemGovernancePolicyResolutionSimulationReport.status == "archived",
                )
            ).scalar_one()
        )
        totals = self.db.execute(
            select(
                func.coalesce(func.sum(AISystemGovernancePolicyResolutionSimulationReport.context_count), 0),
                func.coalesce(func.sum(AISystemGovernancePolicyResolutionSimulationReport.blocked_contexts_count), 0),
                func.coalesce(func.sum(AISystemGovernancePolicyResolutionSimulationReport.warning_contexts_count), 0),
                func.coalesce(func.sum(AISystemGovernancePolicyResolutionSimulationReport.no_policy_contexts_count), 0),
                func.max(AISystemGovernancePolicyResolutionSimulationReport.created_at),
            ).where(AISystemGovernancePolicyResolutionSimulationReport.organization_id == organization_id)
        ).one()
        return {
            "total_reports": total_reports,
            "active_reports": active_reports,
            "archived_reports": archived_reports,
            "total_contexts_simulated": int(totals[0] or 0),
            "blocked_contexts_total": int(totals[1] or 0),
            "warning_contexts_total": int(totals[2] or 0),
            "no_policy_contexts_total": int(totals[3] or 0),
            "latest_report_at": totals[4],
        }

    @staticmethod
    def _sim_report_contexts(report: AISystemGovernancePolicyResolutionSimulationReport) -> list[dict[str, Any]]:
        result_json = report.result_json if isinstance(report.result_json, dict) else {}
        contexts = result_json.get("contexts")
        if not isinstance(contexts, list):
            return []
        return [item for item in contexts if isinstance(item, dict)]

    @staticmethod
    def _context_key(context: dict[str, Any]) -> str | None:
        key = context.get("context_key")
        if isinstance(key, str) and key.strip():
            return key.strip()
        return None

    @staticmethod
    def _extract_guardrail_resolution_fields(context: dict[str, Any]) -> dict[str, Any]:
        guardrail = context.get("guardrail_resolution")
        if not isinstance(guardrail, dict):
            guardrail = {}
        resolution = guardrail.get("resolution")
        if not isinstance(resolution, dict):
            resolution = {}
        return {
            "blocked": bool(guardrail.get("blocked", resolution.get("blocked", False))),
            "primary_blocking_window_id": resolution.get("primary_blocking_window_id"),
            "override_allowed": bool(resolution.get("override_allowed", True)),
            "enforcement_level": resolution.get("enforcement_level"),
            "matching_window_count": int(resolution.get("matching_window_count") or 0),
            "warnings": resolution.get("warnings") if isinstance(resolution.get("warnings"), list) else [],
            "info": resolution.get("info") if isinstance(resolution.get("info"), list) else [],
        }

    @staticmethod
    def _extract_policy_resolution_fields(context: dict[str, Any]) -> dict[str, Any]:
        policy = context.get("policy_resolution")
        if not isinstance(policy, dict):
            policy = {}
        return {
            "resolution_source": policy.get("resolution_source"),
            "resolved_policy_set_id": policy.get("resolved_policy_set_id"),
            "resolved_policy_version_id": policy.get("resolved_policy_version_id"),
            "assignment_id": policy.get("assignment_id"),
            "precedence_trace": policy.get("precedence_trace") if isinstance(policy.get("precedence_trace"), list) else [],
        }

    def _match_simulation_context_pairs(
        self,
        *,
        base_contexts: list[dict[str, Any]],
        compare_contexts: list[dict[str, Any]],
        context_match_strategy: str,
    ) -> tuple[list[tuple[int, int]], list[int], list[int]]:
        pairs: list[tuple[int, int]] = []
        base_unmatched = set(range(len(base_contexts)))
        compare_unmatched = set(range(len(compare_contexts)))

        base_key_map: dict[str, list[int]] = {}
        compare_key_map: dict[str, list[int]] = {}
        for idx, context in enumerate(base_contexts):
            key = self._context_key(context)
            if key is not None:
                base_key_map.setdefault(key, []).append(idx)
        for idx, context in enumerate(compare_contexts):
            key = self._context_key(context)
            if key is not None:
                compare_key_map.setdefault(key, []).append(idx)

        for key in sorted(set(base_key_map.keys()).intersection(compare_key_map.keys())):
            b_list = base_key_map[key]
            c_list = compare_key_map[key]
            for i in range(min(len(b_list), len(c_list))):
                b_idx = b_list[i]
                c_idx = c_list[i]
                if b_idx in base_unmatched and c_idx in compare_unmatched:
                    pairs.append((b_idx, c_idx))
                    base_unmatched.remove(b_idx)
                    compare_unmatched.remove(c_idx)

        if context_match_strategy == "context_key_then_index":
            for b_idx in sorted(base_unmatched):
                if b_idx in compare_unmatched:
                    pairs.append((b_idx, b_idx))
                    compare_unmatched.remove(b_idx)
            matched_base = {b for b, _ in pairs}
            base_unmatched = {idx for idx in base_unmatched if idx not in matched_base}

        pairs.sort(key=lambda item: item[0])
        return pairs, sorted(base_unmatched), sorted(compare_unmatched)

    def diff_simulation_reports(
        self,
        *,
        organization_id: uuid.UUID,
        base_report_id: uuid.UUID,
        compare_report_id: uuid.UUID,
        title: str | None,
        persist_diff: bool,
        context_match_strategy: str,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        if context_match_strategy not in {"context_key_then_index", "context_key_only"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid context_match_strategy")

        base_report = self.require_simulation_report(organization_id=organization_id, report_id=base_report_id)
        compare_report = self.require_simulation_report(organization_id=organization_id, report_id=compare_report_id)
        base_contexts = self._sim_report_contexts(base_report)
        compare_contexts = self._sim_report_contexts(compare_report)
        pairs, base_unmatched, compare_unmatched = self._match_simulation_context_pairs(
            base_contexts=base_contexts,
            compare_contexts=compare_contexts,
            context_match_strategy=context_match_strategy,
        )

        context_diffs: list[dict[str, Any]] = []
        reason_code_summary: dict[str, int] = {}
        changed_count = 0
        unchanged_count = 0
        policy_changed_count = 0
        guardrail_changed_count = 0
        precedence_trace_changed_count = 0

        def add_reason_code(code: str) -> None:
            reason_code_summary[code] = int(reason_code_summary.get(code, 0)) + 1

        for b_idx, c_idx in pairs:
            base_ctx = base_contexts[b_idx]
            compare_ctx = compare_contexts[c_idx]
            base_policy = self._extract_policy_resolution_fields(base_ctx)
            compare_policy = self._extract_policy_resolution_fields(compare_ctx)
            base_guardrail = self._extract_guardrail_resolution_fields(base_ctx)
            compare_guardrail = self._extract_guardrail_resolution_fields(compare_ctx)

            policy_field_config = [
                ("resolution_source", "policy_resolution.resolution_source", "POLICY_RESOLUTION_SOURCE_CHANGED"),
                ("resolved_policy_set_id", "policy_resolution.resolved_policy_set_id", "POLICY_SET_CHANGED"),
                ("resolved_policy_version_id", "policy_resolution.resolved_policy_version_id", "POLICY_VERSION_CHANGED"),
                ("assignment_id", "policy_resolution.assignment_id", "POLICY_ASSIGNMENT_CHANGED"),
            ]
            policy_changed_fields: list[str] = []
            guardrail_changed_fields: list[str] = []
            field_changes: list[dict[str, Any]] = []
            reason_codes: list[str] = []

            def add_context_reason(code: str) -> None:
                if code not in reason_codes:
                    reason_codes.append(code)
                add_reason_code(code)

            def add_field_change(field_name: str, field_path: str, reason_code: str, before_value: Any, after_value: Any) -> None:
                if before_value == after_value:
                    return
                field_changes.append(
                    {
                        "field_path": field_path,
                        "reason_code": reason_code,
                        "before_value": before_value,
                        "after_value": after_value,
                    }
                )
                add_context_reason(reason_code)
                if field_name.startswith("policy_"):
                    policy_changed_fields.append(field_name.removeprefix("policy_"))
                elif field_name.startswith("guardrail_"):
                    guardrail_changed_fields.append(field_name.removeprefix("guardrail_"))

            for policy_field, policy_path, reason_code in policy_field_config:
                add_field_change(
                    f"policy_{policy_field}",
                    policy_path,
                    reason_code,
                    base_policy.get(policy_field),
                    compare_policy.get(policy_field),
                )

            precedence_changed = base_policy.get("precedence_trace") != compare_policy.get("precedence_trace")
            add_field_change(
                "policy_precedence_trace",
                "policy_resolution.precedence_trace",
                "POLICY_PRECEDENCE_TRACE_CHANGED",
                base_policy.get("precedence_trace"),
                compare_policy.get("precedence_trace"),
            )

            guardrail_field_config = [
                ("blocked", "guardrail_resolution.blocked", "GUARDRAIL_BLOCKED_CHANGED"),
                (
                    "primary_blocking_window_id",
                    "guardrail_resolution.primary_blocking_window_id",
                    "PRIMARY_BLOCKING_WINDOW_CHANGED",
                ),
                ("override_allowed", "guardrail_resolution.override_allowed", "OVERRIDE_ALLOWED_CHANGED"),
                ("enforcement_level", "guardrail_resolution.enforcement_level", "ENFORCEMENT_LEVEL_CHANGED"),
                ("matching_window_count", "guardrail_resolution.matching_window_count", "MATCHING_WINDOW_COUNT_CHANGED"),
                ("warnings", "guardrail_resolution.warnings", "GUARDRAIL_WARNINGS_CHANGED"),
                ("info", "guardrail_resolution.info", "GUARDRAIL_INFO_CHANGED"),
            ]
            for guardrail_field, guardrail_path, reason_code in guardrail_field_config:
                add_field_change(
                    f"guardrail_{guardrail_field}",
                    guardrail_path,
                    reason_code,
                    base_guardrail.get(guardrail_field),
                    compare_guardrail.get(guardrail_field),
                )

            context_changed = bool(policy_changed_fields or guardrail_changed_fields)
            if context_changed:
                changed_count += 1
                add_context_reason("CONTEXT_CHANGED")
            else:
                unchanged_count += 1
                add_context_reason("CONTEXT_UNCHANGED")
            if any(field != "precedence_trace" for field in policy_changed_fields):
                policy_changed_count += 1
            if guardrail_changed_fields:
                guardrail_changed_count += 1
            if precedence_changed:
                precedence_trace_changed_count += 1

            context_diffs.append(
                {
                    "match_type": "matched",
                    "base_index": b_idx,
                    "compare_index": c_idx,
                    "context_key": self._context_key(compare_ctx) or self._context_key(base_ctx) or f"index_{b_idx}",
                    "changed": context_changed,
                    "policy_changed_fields": policy_changed_fields,
                    "guardrail_changed_fields": guardrail_changed_fields,
                    "base_policy_resolution": base_policy,
                    "compare_policy_resolution": compare_policy,
                    "base_guardrail_resolution": base_guardrail,
                    "compare_guardrail_resolution": compare_guardrail,
                    "reason_codes": reason_codes,
                    "field_changes": field_changes,
                }
            )

        for idx in base_unmatched:
            add_reason_code("CONTEXT_REMOVED")
            context_diffs.append(
                {
                    "match_type": "removed",
                    "base_index": idx,
                    "compare_index": None,
                    "context_key": self._context_key(base_contexts[idx]) or f"index_{idx}",
                    "changed": True,
                    "base_context": base_contexts[idx],
                    "reason_codes": ["CONTEXT_REMOVED"],
                    "field_changes": [],
                }
            )
        for idx in compare_unmatched:
            add_reason_code("CONTEXT_ADDED")
            context_diffs.append(
                {
                    "match_type": "added",
                    "base_index": None,
                    "compare_index": idx,
                    "context_key": self._context_key(compare_contexts[idx]) or f"index_{idx}",
                    "changed": True,
                    "compare_context": compare_contexts[idx],
                    "reason_codes": ["CONTEXT_ADDED"],
                    "field_changes": [],
                }
            )
        context_diffs.sort(key=lambda item: (item["context_key"], str(item.get("match_type")), int(item.get("base_index") or 0)))

        blocked_delta = int(compare_report.blocked_contexts_count - base_report.blocked_contexts_count)
        warning_delta = int(compare_report.warning_contexts_count - base_report.warning_contexts_count)
        no_policy_delta = int(compare_report.no_policy_contexts_count - base_report.no_policy_contexts_count)
        if blocked_delta > 0:
            add_reason_code("BLOCKED_STATUS_INCREASED")
        elif blocked_delta < 0:
            add_reason_code("BLOCKED_STATUS_DECREASED")
        if warning_delta > 0:
            add_reason_code("WARNING_STATUS_INCREASED")
        elif warning_delta < 0:
            add_reason_code("WARNING_STATUS_DECREASED")
        if no_policy_delta > 0:
            add_reason_code("NO_POLICY_STATUS_INCREASED")
        elif no_policy_delta < 0:
            add_reason_code("NO_POLICY_STATUS_DECREASED")

        reason_code_count = int(sum(reason_code_summary.values()))

        diff_payload = {
            "persisted": persist_diff,
            "diff_report_id": None,
            "base_report_id": base_report.id,
            "compare_report_id": compare_report.id,
            "context_match_strategy": context_match_strategy,
            "added_contexts_count": len(compare_unmatched),
            "removed_contexts_count": len(base_unmatched),
            "changed_contexts_count": changed_count,
            "unchanged_contexts_count": unchanged_count,
            "blocked_delta": blocked_delta,
            "warning_delta": warning_delta,
            "no_policy_delta": no_policy_delta,
            "policy_changed_count": policy_changed_count,
            "guardrail_changed_count": guardrail_changed_count,
            "precedence_trace_changed_count": precedence_trace_changed_count,
            "reason_code_summary": reason_code_summary,
            "reason_code_count": reason_code_count,
            "context_diffs": context_diffs,
            "caveat": POLICY_RESOLUTION_SIMULATION_DIFF_CAVEAT,
        }

        if persist_diff:
            row = AISystemGovernancePolicyResolutionSimulationDiffReport(
                organization_id=organization_id,
                base_report_id=base_report.id,
                compare_report_id=compare_report.id,
                title=title.strip() if isinstance(title, str) and title.strip() else None,
                status="generated",
                diff_json=self.json_safe({**diff_payload, "persisted": True, "diff_report_id": None}),
                context_match_strategy=context_match_strategy,
                added_contexts_count=len(compare_unmatched),
                removed_contexts_count=len(base_unmatched),
                changed_contexts_count=changed_count,
                unchanged_contexts_count=unchanged_count,
                blocked_delta=blocked_delta,
                warning_delta=warning_delta,
                no_policy_delta=no_policy_delta,
                reason_code_summary_json=reason_code_summary,
                reason_code_count=reason_code_count,
                created_by_user_id=actor_user_id,
            )
            self.db.add(row)
            self.db.flush()
            row.diff_json["diff_report_id"] = str(row.id)
            self.db.flush()
            diff_payload["persisted"] = True
            diff_payload["diff_report_id"] = row.id

        return diff_payload

    def list_simulation_diff_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        base_report_id: uuid.UUID | None,
        compare_report_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePolicyResolutionSimulationDiffReport]:
        stmt = select(AISystemGovernancePolicyResolutionSimulationDiffReport).where(
            AISystemGovernancePolicyResolutionSimulationDiffReport.organization_id == organization_id,
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePolicyResolutionSimulationDiffReport.status == status_filter)
        if base_report_id is not None:
            stmt = stmt.where(AISystemGovernancePolicyResolutionSimulationDiffReport.base_report_id == base_report_id)
        if compare_report_id is not None:
            stmt = stmt.where(AISystemGovernancePolicyResolutionSimulationDiffReport.compare_report_id == compare_report_id)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePolicyResolutionSimulationDiffReport.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_simulation_diff_report(
        self,
        *,
        row: AISystemGovernancePolicyResolutionSimulationDiffReport,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyResolutionSimulationDiffReport:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def simulation_diff_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        total_diff_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyResolutionSimulationDiffReport.id)).where(
                    AISystemGovernancePolicyResolutionSimulationDiffReport.organization_id == organization_id,
                )
            ).scalar_one()
        )
        active_diff_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyResolutionSimulationDiffReport.id)).where(
                    AISystemGovernancePolicyResolutionSimulationDiffReport.organization_id == organization_id,
                    AISystemGovernancePolicyResolutionSimulationDiffReport.status == "generated",
                )
            ).scalar_one()
        )
        archived_diff_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyResolutionSimulationDiffReport.id)).where(
                    AISystemGovernancePolicyResolutionSimulationDiffReport.organization_id == organization_id,
                    AISystemGovernancePolicyResolutionSimulationDiffReport.status == "archived",
                )
            ).scalar_one()
        )
        totals = self.db.execute(
            select(
                func.coalesce(func.sum(AISystemGovernancePolicyResolutionSimulationDiffReport.changed_contexts_count), 0),
                func.coalesce(func.sum(AISystemGovernancePolicyResolutionSimulationDiffReport.added_contexts_count), 0),
                func.coalesce(func.sum(AISystemGovernancePolicyResolutionSimulationDiffReport.removed_contexts_count), 0),
                func.max(AISystemGovernancePolicyResolutionSimulationDiffReport.created_at),
            ).where(AISystemGovernancePolicyResolutionSimulationDiffReport.organization_id == organization_id)
        ).one()

        policy_changed_total = 0
        guardrail_changed_total = 0
        total_reason_code_occurrences = 0
        reason_totals: dict[str, int] = {}
        rows = self.db.execute(
            select(AISystemGovernancePolicyResolutionSimulationDiffReport).where(
                AISystemGovernancePolicyResolutionSimulationDiffReport.organization_id == organization_id,
            )
        ).scalars().all()
        for row in rows:
            diff_json = row.diff_json if isinstance(row.diff_json, dict) else {}
            policy_changed_total += int(diff_json.get("policy_changed_count") or 0)
            guardrail_changed_total += int(diff_json.get("guardrail_changed_count") or 0)
            total_reason_code_occurrences += int(row.reason_code_count or 0)
            reason_summary = row.reason_code_summary_json if isinstance(row.reason_code_summary_json, dict) else {}
            for code, count in reason_summary.items():
                if not isinstance(code, str):
                    continue
                reason_totals[code] = int(reason_totals.get(code, 0)) + int(count or 0)

        top_reason_codes = [
            {"reason_code": code, "count": count}
            for code, count in sorted(reason_totals.items(), key=lambda item: (-item[1], item[0]))
        ]

        return {
            "total_diff_reports": total_diff_reports,
            "active_diff_reports": active_diff_reports,
            "archived_diff_reports": archived_diff_reports,
            "total_changed_contexts": int(totals[0] or 0),
            "total_added_contexts": int(totals[1] or 0),
            "total_removed_contexts": int(totals[2] or 0),
            "total_policy_changed_contexts": int(policy_changed_total),
            "total_guardrail_changed_contexts": int(guardrail_changed_total),
            "total_reason_code_occurrences": int(total_reason_code_occurrences),
            "top_reason_codes": top_reason_codes,
            "latest_diff_report_at": totals[3],
        }

    def create_policy_diff_gating_profile(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        status_value: str,
        default_severity: str,
        review_required_threshold: str,
        reason_code_rules_json: dict | list | None,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingProfile:
        normalized_default, normalized_threshold, normalized_rules = self._normalize_gating_profile_inputs(
            default_severity=default_severity,
            review_required_threshold=review_required_threshold,
            reason_code_rules_json=reason_code_rules_json,
        )
        row = AISystemGovernancePolicyDiffGatingProfile(
            organization_id=organization_id,
            name=name,
            description=description,
            status=status_value,
            default_severity=normalized_default,
            review_required_threshold=normalized_threshold,
            reason_code_rules_json=normalized_rules,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_policy_diff_gating_profiles(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePolicyDiffGatingProfile]:
        stmt = select(AISystemGovernancePolicyDiffGatingProfile).where(
            AISystemGovernancePolicyDiffGatingProfile.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingProfile.status == status_filter)
        if not include_archived:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingProfile.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePolicyDiffGatingProfile.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def update_policy_diff_gating_profile(
        self,
        *,
        row: AISystemGovernancePolicyDiffGatingProfile,
        updates: dict[str, Any],
    ) -> AISystemGovernancePolicyDiffGatingProfile:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived policy diff gating profiles cannot be updated")

        next_default = updates.get("default_severity", row.default_severity)
        next_threshold = updates.get("review_required_threshold", row.review_required_threshold)
        next_rules = updates.get("reason_code_rules_json", row.reason_code_rules_json)
        normalized_default, normalized_threshold, normalized_rules = self._normalize_gating_profile_inputs(
            default_severity=next_default,
            review_required_threshold=next_threshold,
            reason_code_rules_json=next_rules,
        )

        if "name" in updates:
            row.name = updates["name"]
        if "description" in updates:
            row.description = updates["description"]
        if "status" in updates:
            row.status = updates["status"]
        row.default_severity = normalized_default
        row.review_required_threshold = normalized_threshold
        row.reason_code_rules_json = normalized_rules
        self.db.flush()
        return row

    def archive_policy_diff_gating_profile(
        self,
        *,
        row: AISystemGovernancePolicyDiffGatingProfile,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingProfile:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    @staticmethod
    def _extract_reason_code_occurrences(
        diff_report: AISystemGovernancePolicyResolutionSimulationDiffReport,
    ) -> dict[str, int]:
        reason_counts: dict[str, int] = {}
        if isinstance(diff_report.reason_code_summary_json, dict):
            for code, count in diff_report.reason_code_summary_json.items():
                if not isinstance(code, str):
                    continue
                reason_counts[code] = int(count or 0)
            return reason_counts

        diff_json = diff_report.diff_json if isinstance(diff_report.diff_json, dict) else {}
        context_diffs = diff_json.get("context_diffs")
        if isinstance(context_diffs, list):
            for row in context_diffs:
                if not isinstance(row, dict):
                    continue
                codes = row.get("reason_codes")
                if not isinstance(codes, list):
                    continue
                for code in codes:
                    if isinstance(code, str):
                        reason_counts[code] = int(reason_counts.get(code, 0)) + 1
        return reason_counts

    def classify_policy_resolution_diff(
        self,
        *,
        organization_id: uuid.UUID,
        diff_report_id: uuid.UUID,
        gating_profile_id: uuid.UUID,
        persist_report: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        diff_report = self.require_simulation_diff_report(organization_id=organization_id, diff_report_id=diff_report_id)
        profile = self.require_policy_diff_gating_profile(organization_id=organization_id, profile_id=gating_profile_id)
        if profile.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Policy diff gating profile must be active")

        reason_counts = self._extract_reason_code_occurrences(diff_report)
        reason_code_count = int(sum(int(v or 0) for v in reason_counts.values()))
        rules = profile.reason_code_rules_json if isinstance(profile.reason_code_rules_json, dict) else {}

        severity_rank = {value: idx for idx, value in enumerate(POLICY_DIFF_GATING_SEVERITY_ORDER)}
        threshold_rank = severity_rank[profile.review_required_threshold]
        max_rank = severity_rank["info"]
        explicit_review_required_hit = False
        reason_code_classifications: list[dict[str, Any]] = []
        severity_summary = {key: 0 for key in POLICY_DIFF_GATING_SEVERITY_ORDER}

        for reason_code in sorted(reason_counts.keys()):
            count = int(reason_counts[reason_code] or 0)
            if count <= 0:
                continue
            rule = rules.get(reason_code) if isinstance(rules.get(reason_code), dict) else None
            severity_value = profile.default_severity
            review_required_flag = False
            notes_value = None
            if rule is not None:
                severity_value = str(rule.get("severity", profile.default_severity))
                self._validate_gating_severity(severity_value, field_name=f"reason_code_rules_json.{reason_code}.severity")
                review_required_flag = bool(rule.get("review_required", False))
                notes_value = rule.get("notes")
            severity_summary[severity_value] = int(severity_summary.get(severity_value, 0)) + count
            max_rank = max(max_rank, severity_rank[severity_value])
            if review_required_flag:
                explicit_review_required_hit = True
            reason_code_classifications.append(
                {
                    "reason_code": reason_code,
                    "count": count,
                    "severity": severity_value,
                    "review_required": review_required_flag,
                    "notes": notes_value if isinstance(notes_value, str) else None,
                    "rule_applied": rule is not None,
                }
            )

        if reason_code_count == 0:
            max_severity = "info"
            review_required = False
        else:
            max_severity = POLICY_DIFF_GATING_SEVERITY_ORDER[max_rank]
            review_required = explicit_review_required_hit or max_rank >= threshold_rank

        result = {
            "persisted": persist_report,
            "gating_report_id": None,
            "diff_report_id": diff_report.id,
            "gating_profile_id": profile.id,
            "max_severity": max_severity,
            "review_required": bool(review_required),
            "reason_code_count": reason_code_count,
            "severity_summary": severity_summary,
            "reason_code_classifications": reason_code_classifications,
            "caveat": POLICY_DIFF_GATING_CAVEAT,
        }
        if persist_report:
            row = AISystemGovernancePolicyDiffGatingReport(
                organization_id=organization_id,
                diff_report_id=diff_report.id,
                gating_profile_id=profile.id,
                status="generated",
                result_json=self.json_safe({**result, "persisted": True, "gating_report_id": None}),
                max_severity=max_severity,
                review_required=bool(review_required),
                reason_code_count=reason_code_count,
                created_by_user_id=actor_user_id,
            )
            self.db.add(row)
            self.db.flush()
            row.result_json["gating_report_id"] = str(row.id)
            self.db.flush()
            result["persisted"] = True
            result["gating_report_id"] = row.id
        return result

    def list_policy_diff_gating_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        diff_report_id: uuid.UUID | None,
        gating_profile_id: uuid.UUID | None,
        review_required: bool | None,
        max_severity: str | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePolicyDiffGatingReport]:
        stmt = select(AISystemGovernancePolicyDiffGatingReport).where(
            AISystemGovernancePolicyDiffGatingReport.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingReport.status == status_filter)
        if diff_report_id is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingReport.diff_report_id == diff_report_id)
        if gating_profile_id is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingReport.gating_profile_id == gating_profile_id)
        if review_required is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingReport.review_required == review_required)
        if max_severity is not None:
            self._validate_gating_severity(max_severity, field_name="max_severity")
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingReport.max_severity == max_severity)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePolicyDiffGatingReport.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_policy_diff_gating_report(
        self,
        *,
        row: AISystemGovernancePolicyDiffGatingReport,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingReport:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def policy_diff_gating_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        profile_counts = dict(
            self.db.execute(
                select(
                    AISystemGovernancePolicyDiffGatingProfile.status,
                    func.count(AISystemGovernancePolicyDiffGatingProfile.id),
                )
                .where(AISystemGovernancePolicyDiffGatingProfile.organization_id == organization_id)
                .group_by(AISystemGovernancePolicyDiffGatingProfile.status)
            ).all()
        )
        report_counts = dict(
            self.db.execute(
                select(
                    AISystemGovernancePolicyDiffGatingReport.status,
                    func.count(AISystemGovernancePolicyDiffGatingReport.id),
                )
                .where(AISystemGovernancePolicyDiffGatingReport.organization_id == organization_id)
                .group_by(AISystemGovernancePolicyDiffGatingReport.status)
            ).all()
        )
        review_required_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingReport.id)).where(
                    AISystemGovernancePolicyDiffGatingReport.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingReport.review_required.is_(True),
                )
            ).scalar_one()
        )
        by_max_severity = {
            str(key): int(value)
            for key, value in self.db.execute(
                select(
                    AISystemGovernancePolicyDiffGatingReport.max_severity,
                    func.count(AISystemGovernancePolicyDiffGatingReport.id),
                )
                .where(AISystemGovernancePolicyDiffGatingReport.organization_id == organization_id)
                .group_by(AISystemGovernancePolicyDiffGatingReport.max_severity)
            ).all()
            if key is not None
        }
        latest_gating_report_at = self.db.execute(
            select(func.max(AISystemGovernancePolicyDiffGatingReport.created_at)).where(
                AISystemGovernancePolicyDiffGatingReport.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "active_profiles": int(profile_counts.get("active", 0)),
            "inactive_profiles": int(profile_counts.get("inactive", 0)),
            "archived_profiles": int(profile_counts.get("archived", 0)),
            "total_gating_reports": int(sum(int(v or 0) for v in report_counts.values())),
            "active_gating_reports": int(report_counts.get("generated", 0)),
            "archived_gating_reports": int(report_counts.get("archived", 0)),
            "review_required_reports": int(review_required_reports),
            "by_max_severity": by_max_severity,
            "latest_gating_report_at": latest_gating_report_at,
            "caveat": POLICY_DIFF_GATING_CAVEAT,
        }

    def create_diagnostic_export_diff_gating_profile(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        status_value: str,
        default_severity: str,
        review_required_threshold: str,
        reason_code_rules_json: dict | list | None,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingProfile:
        normalized_default, normalized_threshold, normalized_rules = self._normalize_export_diff_gating_profile_inputs(
            default_severity=default_severity,
            review_required_threshold=review_required_threshold,
            reason_code_rules_json=reason_code_rules_json,
        )
        row = AISystemGovernanceDiagnosticExportDiffGatingProfile(
            organization_id=organization_id,
            name=name,
            description=description,
            status=status_value,
            default_severity=normalized_default,
            review_required_threshold=normalized_threshold,
            reason_code_rules_json=normalized_rules,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_diagnostic_export_diff_gating_profiles(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceDiagnosticExportDiffGatingProfile]:
        stmt = select(AISystemGovernanceDiagnosticExportDiffGatingProfile).where(
            AISystemGovernanceDiagnosticExportDiffGatingProfile.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingProfile.status == status_filter)
        if not include_archived:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingProfile.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceDiagnosticExportDiffGatingProfile.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def update_diagnostic_export_diff_gating_profile(
        self,
        *,
        row: AISystemGovernanceDiagnosticExportDiffGatingProfile,
        updates: dict[str, Any],
    ) -> AISystemGovernanceDiagnosticExportDiffGatingProfile:
        if row.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived diagnostic export diff gating profiles cannot be updated",
            )

        next_default = updates.get("default_severity", row.default_severity)
        next_threshold = updates.get("review_required_threshold", row.review_required_threshold)
        next_rules = updates.get("reason_code_rules_json", row.reason_code_rules_json)
        normalized_default, normalized_threshold, normalized_rules = self._normalize_export_diff_gating_profile_inputs(
            default_severity=next_default,
            review_required_threshold=next_threshold,
            reason_code_rules_json=next_rules,
        )

        if "name" in updates:
            row.name = updates["name"]
        if "description" in updates:
            row.description = updates["description"]
        if "status" in updates:
            row.status = updates["status"]
        row.default_severity = normalized_default
        row.review_required_threshold = normalized_threshold
        row.reason_code_rules_json = normalized_rules
        self.db.flush()
        return row

    def archive_diagnostic_export_diff_gating_profile(
        self,
        *,
        row: AISystemGovernanceDiagnosticExportDiffGatingProfile,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingProfile:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    @staticmethod
    def _extract_export_diff_reason_code_occurrences(
        export_diff_report: AISystemGovernancePresetAssignmentDiagnosticExportDiffReport,
    ) -> dict[str, int]:
        reason_counts: dict[str, int] = {}
        if isinstance(export_diff_report.reason_code_summary_json, dict):
            for code, count in export_diff_report.reason_code_summary_json.items():
                if not isinstance(code, str):
                    continue
                reason_counts[code] = int(count or 0)
            return reason_counts

        diff_json = export_diff_report.diff_json if isinstance(export_diff_report.diff_json, dict) else {}
        rows = diff_json.get("path_diffs")
        if not isinstance(rows, list):
            return reason_counts
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = row.get("reason_code")
            if isinstance(code, str):
                reason_counts[code] = int(reason_counts.get(code, 0)) + 1
        return reason_counts

    def classify_diagnostic_export_diff(
        self,
        *,
        organization_id: uuid.UUID,
        export_diff_report_id: uuid.UUID,
        gating_profile_id: uuid.UUID,
        persist_report: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        export_diff_report = self.require_preset_assignment_diagnostic_export_diff_report(
            organization_id=organization_id,
            export_diff_report_id=export_diff_report_id,
        )
        profile = self.require_diagnostic_export_diff_gating_profile(
            organization_id=organization_id,
            profile_id=gating_profile_id,
        )
        if profile.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Diagnostic export diff gating profile must be active",
            )

        reason_counts = self._extract_export_diff_reason_code_occurrences(export_diff_report)
        reason_code_count = int(sum(int(v or 0) for v in reason_counts.values()))
        rules = profile.reason_code_rules_json if isinstance(profile.reason_code_rules_json, dict) else {}

        severity_rank = {value: idx for idx, value in enumerate(POLICY_DIFF_GATING_SEVERITY_ORDER)}
        threshold_rank = severity_rank[profile.review_required_threshold]
        max_rank = severity_rank["info"]
        explicit_review_required_hit = False
        reason_code_classifications: list[dict[str, Any]] = []
        severity_summary = {key: 0 for key in POLICY_DIFF_GATING_SEVERITY_ORDER}

        for reason_code in sorted(reason_counts.keys()):
            count = int(reason_counts[reason_code] or 0)
            if count <= 0:
                continue
            rule = rules.get(reason_code) if isinstance(rules.get(reason_code), dict) else None
            severity_value = profile.default_severity
            review_required_flag = False
            notes_value = None
            if rule is not None:
                severity_value = str(rule.get("severity", profile.default_severity))
                self._validate_gating_severity(
                    severity_value,
                    field_name=f"reason_code_rules_json.{reason_code}.severity",
                )
                review_required_flag = bool(rule.get("review_required", False))
                notes_value = rule.get("notes")
            severity_summary[severity_value] = int(severity_summary.get(severity_value, 0)) + count
            max_rank = max(max_rank, severity_rank[severity_value])
            if review_required_flag:
                explicit_review_required_hit = True
            reason_code_classifications.append(
                {
                    "reason_code": reason_code,
                    "count": count,
                    "severity": severity_value,
                    "review_required": review_required_flag,
                    "notes": notes_value if isinstance(notes_value, str) else None,
                    "rule_applied": rule is not None,
                }
            )

        if reason_code_count == 0:
            max_severity = "info"
            review_required = False
        else:
            max_severity = POLICY_DIFF_GATING_SEVERITY_ORDER[max_rank]
            review_required = explicit_review_required_hit or max_rank >= threshold_rank

        result = {
            "persisted": persist_report,
            "gating_report_id": None,
            "export_diff_report_id": export_diff_report.id,
            "gating_profile_id": profile.id,
            "max_severity": max_severity,
            "review_required": bool(review_required),
            "reason_code_count": reason_code_count,
            "severity_summary": severity_summary,
            "reason_code_classifications": reason_code_classifications,
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_CAVEAT,
        }
        if persist_report:
            row = AISystemGovernanceDiagnosticExportDiffGatingReport(
                organization_id=organization_id,
                export_diff_report_id=export_diff_report.id,
                gating_profile_id=profile.id,
                status="generated",
                result_json=self.json_safe({**result, "persisted": True, "gating_report_id": None}),
                max_severity=max_severity,
                review_required=bool(review_required),
                reason_code_count=reason_code_count,
                created_by_user_id=actor_user_id,
            )
            self.db.add(row)
            self.db.flush()
            row.result_json["gating_report_id"] = str(row.id)
            self.db.flush()
            result["persisted"] = True
            result["gating_report_id"] = row.id
        return result

    def list_diagnostic_export_diff_gating_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        export_diff_report_id: uuid.UUID | None,
        gating_profile_id: uuid.UUID | None,
        review_required: bool | None,
        max_severity: str | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceDiagnosticExportDiffGatingReport]:
        stmt = select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingReport.status == status_filter)
        if export_diff_report_id is not None:
            stmt = stmt.where(
                AISystemGovernanceDiagnosticExportDiffGatingReport.export_diff_report_id == export_diff_report_id
            )
        if gating_profile_id is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingReport.gating_profile_id == gating_profile_id)
        if review_required is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingReport.review_required == review_required)
        if max_severity is not None:
            self._validate_gating_severity(max_severity, field_name="max_severity")
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingReport.max_severity == max_severity)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceDiagnosticExportDiffGatingReport.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_diagnostic_export_diff_gating_report(
        self,
        *,
        row: AISystemGovernanceDiagnosticExportDiffGatingReport,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingReport:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def diagnostic_export_diff_gating_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        profile_counts = dict(
            self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingProfile.status,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingProfile.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingProfile.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingProfile.status)
            ).all()
        )
        report_counts = dict(
            self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingReport.status,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingReport.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingReport.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingReport.status)
            ).all()
        )
        review_required_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernanceDiagnosticExportDiffGatingReport.id)).where(
                    AISystemGovernanceDiagnosticExportDiffGatingReport.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingReport.review_required.is_(True),
                )
            ).scalar_one()
        )
        by_max_severity = {
            str(key): int(value)
            for key, value in self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingReport.max_severity,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingReport.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingReport.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingReport.max_severity)
            ).all()
            if key is not None
        }
        latest_gating_report_at = self.db.execute(
            select(func.max(AISystemGovernanceDiagnosticExportDiffGatingReport.created_at)).where(
                AISystemGovernanceDiagnosticExportDiffGatingReport.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "active_profiles": int(profile_counts.get("active", 0)),
            "inactive_profiles": int(profile_counts.get("inactive", 0)),
            "archived_profiles": int(profile_counts.get("archived", 0)),
            "total_gating_reports": int(sum(int(v or 0) for v in report_counts.values())),
            "active_gating_reports": int(report_counts.get("generated", 0)),
            "archived_gating_reports": int(report_counts.get("archived", 0)),
            "review_required_reports": int(review_required_reports),
            "by_max_severity": by_max_severity,
            "latest_gating_report_at": latest_gating_report_at,
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_CAVEAT,
        }

    def compare_diagnostic_export_diff_gating_reports(
        self,
        *,
        organization_id: uuid.UUID,
        base_gating_report_id: uuid.UUID,
        compare_gating_report_id: uuid.UUID,
        title: str | None,
        persist_compare: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        base_report = self.require_diagnostic_export_diff_gating_report(
            organization_id=organization_id,
            gating_report_id=base_gating_report_id,
        )
        compare_report = self.require_diagnostic_export_diff_gating_report(
            organization_id=organization_id,
            gating_report_id=compare_gating_report_id,
        )

        max_severity_drift = self._gating_severity_direction(
            base_report.max_severity,
            compare_report.max_severity,
        )
        review_required_drift = self._review_required_drift(
            bool(base_report.review_required),
            bool(compare_report.review_required),
        )

        base_codes = self._extract_diagnostic_export_diff_gating_reason_classifications(base_report)
        compare_codes = self._extract_diagnostic_export_diff_gating_reason_classifications(compare_report)
        all_codes = sorted(set(base_codes.keys()).union(compare_codes.keys()))
        added_reason_codes: list[str] = []
        removed_reason_codes: list[str] = []
        changed_reason_codes: list[dict[str, Any]] = []
        severity_changes_count = 0

        for code in all_codes:
            base_item = base_codes.get(code)
            compare_item = compare_codes.get(code)
            if base_item is None and compare_item is not None:
                added_reason_codes.append(code)
                continue
            if base_item is not None and compare_item is None:
                removed_reason_codes.append(code)
                continue
            assert base_item is not None and compare_item is not None
            if base_item["severity"] != compare_item["severity"]:
                severity_changes_count += 1
                changed_reason_codes.append(
                    {
                        "reason_code": code,
                        "change_type": "severity_changed",
                        "before": base_item["severity"],
                        "after": compare_item["severity"],
                    }
                )
            if bool(base_item["review_required"]) != bool(compare_item["review_required"]):
                changed_reason_codes.append(
                    {
                        "reason_code": code,
                        "change_type": "review_required_changed",
                        "before": bool(base_item["review_required"]),
                        "after": bool(compare_item["review_required"]),
                    }
                )
            if int(base_item["count"]) != int(compare_item["count"]):
                changed_reason_codes.append(
                    {
                        "reason_code": code,
                        "change_type": "count_changed",
                        "before": int(base_item["count"]),
                        "after": int(compare_item["count"]),
                    }
                )

        changed_reason_codes = sorted(
            changed_reason_codes,
            key=lambda item: (str(item.get("reason_code") or ""), str(item.get("change_type") or "")),
        )
        reason_code_changes_count = len(added_reason_codes) + len(removed_reason_codes) + len(changed_reason_codes)

        base_severity_summary = self._extract_diagnostic_export_diff_gating_severity_summary(base_report)
        compare_severity_summary = self._extract_diagnostic_export_diff_gating_severity_summary(compare_report)
        aggregate_delta = {
            "reason_code_count_delta": int(compare_report.reason_code_count - base_report.reason_code_count),
            "severity_summary_delta": {
                severity: int(compare_severity_summary.get(severity, 0)) - int(base_severity_summary.get(severity, 0))
                for severity in POLICY_DIFF_GATING_SEVERITY_ORDER
            },
        }

        result = {
            "persisted": persist_compare,
            "compare_report_id": None,
            "base_gating_report_id": base_report.id,
            "compare_gating_report_id": compare_report.id,
            "max_severity_drift": max_severity_drift,
            "review_required_drift": review_required_drift,
            "reason_code_changes_count": reason_code_changes_count,
            "severity_changes_count": severity_changes_count,
            "added_reason_codes": added_reason_codes,
            "removed_reason_codes": removed_reason_codes,
            "changed_reason_codes": changed_reason_codes,
            "aggregate_delta": aggregate_delta,
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_CAVEAT,
        }

        if persist_compare:
            row = AISystemGovernanceDiagnosticExportDiffGatingCompareReport(
                organization_id=organization_id,
                base_gating_report_id=base_report.id,
                compare_gating_report_id=compare_report.id,
                title=title.strip() if isinstance(title, str) and title.strip() else None,
                status="generated",
                result_json=self.json_safe({**result, "persisted": True, "compare_report_id": None}),
                max_severity_drift=max_severity_drift,
                review_required_drift=review_required_drift,
                reason_code_changes_count=reason_code_changes_count,
                severity_changes_count=severity_changes_count,
                created_by_user_id=actor_user_id,
            )
            self.db.add(row)
            self.db.flush()
            row.result_json["compare_report_id"] = str(row.id)
            self.db.flush()
            result["persisted"] = True
            result["compare_report_id"] = row.id
        return result

    def list_diagnostic_export_diff_gating_compare_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        base_gating_report_id: uuid.UUID | None,
        compare_gating_report_id: uuid.UUID | None,
        max_severity_drift: str | None,
        review_required_drift: str | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceDiagnosticExportDiffGatingCompareReport]:
        stmt = select(AISystemGovernanceDiagnosticExportDiffGatingCompareReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingCompareReport.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.status == status_filter)
        if base_gating_report_id is not None:
            stmt = stmt.where(
                AISystemGovernanceDiagnosticExportDiffGatingCompareReport.base_gating_report_id == base_gating_report_id
            )
        if compare_gating_report_id is not None:
            stmt = stmt.where(
                AISystemGovernanceDiagnosticExportDiffGatingCompareReport.compare_gating_report_id
                == compare_gating_report_id
            )
        if max_severity_drift is not None:
            if max_severity_drift not in {"increased", "decreased", "unchanged"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="max_severity_drift must be one of: increased, decreased, unchanged",
                )
            stmt = stmt.where(
                AISystemGovernanceDiagnosticExportDiffGatingCompareReport.max_severity_drift == max_severity_drift
            )
        if review_required_drift is not None:
            if review_required_drift not in {"became_required", "became_not_required", "unchanged"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="review_required_drift must be one of: became_required, became_not_required, unchanged",
                )
            stmt = stmt.where(
                AISystemGovernanceDiagnosticExportDiffGatingCompareReport.review_required_drift == review_required_drift
            )
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_diagnostic_export_diff_gating_compare_report(
        self,
        *,
        row: AISystemGovernanceDiagnosticExportDiffGatingCompareReport,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingCompareReport:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def diagnostic_export_diff_gating_compare_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        counts_by_status = dict(
            self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingCompareReport.status,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.status)
            ).all()
        )
        counts_by_severity_drift = dict(
            self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingCompareReport.max_severity_drift,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.max_severity_drift)
            ).all()
        )
        counts_by_review_required_drift = dict(
            self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingCompareReport.review_required_drift,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.review_required_drift)
            ).all()
        )
        total_reason_code_changes = int(
            self.db.execute(
                select(
                    func.coalesce(
                        func.sum(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.reason_code_changes_count),
                        0,
                    )
                ).where(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.organization_id == organization_id)
            ).scalar_one()
        )
        total_severity_changes = int(
            self.db.execute(
                select(
                    func.coalesce(
                        func.sum(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.severity_changes_count),
                        0,
                    )
                ).where(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.organization_id == organization_id)
            ).scalar_one()
        )
        latest_compare_report_at = self.db.execute(
            select(func.max(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.created_at)).where(
                AISystemGovernanceDiagnosticExportDiffGatingCompareReport.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "total_compare_reports": int(sum(int(v or 0) for v in counts_by_status.values())),
            "active_compare_reports": int(counts_by_status.get("generated", 0)),
            "archived_compare_reports": int(counts_by_status.get("archived", 0)),
            "severity_increased_reports": int(counts_by_severity_drift.get("increased", 0)),
            "severity_decreased_reports": int(counts_by_severity_drift.get("decreased", 0)),
            "severity_unchanged_reports": int(counts_by_severity_drift.get("unchanged", 0)),
            "review_required_became_required_reports": int(counts_by_review_required_drift.get("became_required", 0)),
            "review_required_became_not_required_reports": int(
                counts_by_review_required_drift.get("became_not_required", 0)
            ),
            "review_required_unchanged_reports": int(counts_by_review_required_drift.get("unchanged", 0)),
            "total_reason_code_changes": total_reason_code_changes,
            "total_severity_changes": total_severity_changes,
            "latest_compare_report_at": latest_compare_report_at,
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_CAVEAT,
        }

    def create_diagnostic_export_diff_gating_compare_preset(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        watched_reason_codes_json: dict | list | None,
        ignored_reason_codes_json: dict | list | None,
        interpretation_rules_json: dict | list | None,
        default_interpretation_band: str,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePreset:
        normalized_watched, normalized_ignored, normalized_rules, normalized_default_band = (
            self._normalize_diagnostic_export_diff_gating_compare_preset_inputs(
                watched_reason_codes_json=watched_reason_codes_json,
                ignored_reason_codes_json=ignored_reason_codes_json,
                interpretation_rules_json=interpretation_rules_json,
                default_interpretation_band=default_interpretation_band,
            )
        )
        row = AISystemGovernanceDiagnosticExportDiffGatingComparePreset(
            organization_id=organization_id,
            name=name,
            description=description,
            status=status_value,
            watched_reason_codes_json=normalized_watched,
            ignored_reason_codes_json=normalized_ignored,
            interpretation_rules_json=normalized_rules,
            default_interpretation_band=normalized_default_band,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_diagnostic_export_diff_gating_compare_presets(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePreset]:
        stmt = select(AISystemGovernanceDiagnosticExportDiffGatingComparePreset).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.status == status_filter)
        if not include_archived:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def update_diagnostic_export_diff_gating_compare_preset(
        self,
        *,
        row: AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
        updates: dict[str, Any],
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePreset:
        if row.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived diagnostic export diff gating compare presets cannot be updated",
            )
        normalized_watched, normalized_ignored, normalized_rules, normalized_default_band = (
            self._normalize_diagnostic_export_diff_gating_compare_preset_inputs(
                watched_reason_codes_json=updates.get("watched_reason_codes_json", row.watched_reason_codes_json),
                ignored_reason_codes_json=updates.get("ignored_reason_codes_json", row.ignored_reason_codes_json),
                interpretation_rules_json=updates.get("interpretation_rules_json", row.interpretation_rules_json),
                default_interpretation_band=updates.get(
                    "default_interpretation_band",
                    row.default_interpretation_band,
                ),
            )
        )
        if "name" in updates:
            row.name = updates["name"]
        if "description" in updates:
            row.description = updates["description"]
        if "status" in updates:
            row.status = updates["status"]
        if "version_selection_mode" in updates and updates["version_selection_mode"] is not None:
            row.version_selection_mode = self._validate_preset_version_selection_mode(
                str(updates["version_selection_mode"]),
                field_name="version_selection_mode",
            )
        if "allow_explicit_version_override" in updates and updates["allow_explicit_version_override"] is not None:
            row.allow_explicit_version_override = bool(updates["allow_explicit_version_override"])
        row.watched_reason_codes_json = normalized_watched
        row.ignored_reason_codes_json = normalized_ignored
        row.interpretation_rules_json = normalized_rules
        row.default_interpretation_band = normalized_default_band
        self.db.flush()
        return row

    def archive_diagnostic_export_diff_gating_compare_preset(
        self,
        *,
        row: AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePreset:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def create_diagnostic_export_diff_gating_compare_preset_version(
        self,
        *,
        organization_id: uuid.UUID,
        preset: AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
        change_reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion:
        if preset.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived diagnostic export diff gating compare presets cannot accept new versions",
            )
        snapshot = self._diagnostic_export_diff_gating_compare_preset_snapshot_from_row(preset)
        max_version = self.db.execute(
            select(func.max(AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.version_number)).where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.organization_id == organization_id,
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.preset_id == preset.id,
            )
        ).scalar_one()
        next_version = int(max_version or 0) + 1
        row = AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion(
            organization_id=organization_id,
            preset_id=preset.id,
            version_number=next_version,
            status="draft",
            snapshot_json=self.json_safe(snapshot),
            change_reason=change_reason,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_diagnostic_export_diff_gating_compare_preset_versions(
        self,
        *,
        organization_id: uuid.UUID,
        preset_id: uuid.UUID,
    ) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion]:
        return (
            self.db.execute(
                select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion)
                .where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.preset_id == preset_id,
                )
                .order_by(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.version_number.desc(),
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.created_at.desc(),
                )
            )
            .scalars()
            .all()
        )

    def activate_diagnostic_export_diff_gating_compare_preset_version(
        self,
        *,
        organization_id: uuid.UUID,
        preset: AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
        version: AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion:
        if version.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived diagnostic export diff gating compare preset versions cannot be activated",
            )
        existing_active = None
        if preset.active_version_id is not None:
            existing_active = self.db.execute(
                select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.preset_id == preset.id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.id == preset.active_version_id,
                )
            ).scalar_one_or_none()
        if existing_active is not None and existing_active.id != version.id:
            existing_active.status = "deprecated"
        version.status = "active"
        version.activated_by_user_id = actor_user_id
        version.activated_at = self.now()
        preset.active_version_id = version.id
        self.db.flush()
        return version

    def archive_diagnostic_export_diff_gating_compare_preset_version(
        self,
        *,
        preset: AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
        version: AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion:
        if version.status == "active" and preset.active_version_id == version.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Active diagnostic export diff gating compare preset version cannot be archived",
            )
        if preset.pinned_version_id == version.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pinned diagnostic export diff gating compare preset version cannot be archived",
            )
        version.status = "archived"
        if version.archived_at is None:
            version.archived_at = self.now()
        version.archived_by_user_id = actor_user_id
        self.db.flush()
        return version

    def pin_diagnostic_export_diff_gating_compare_preset_version(
        self,
        *,
        preset: AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
        version: AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion,
        version_selection_mode: str,
        allow_explicit_version_override: bool,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePreset:
        if preset.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived diagnostic export diff gating compare presets cannot be pinned",
            )
        if version.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived diagnostic export diff gating compare preset versions cannot be pinned",
            )
        preset.pinned_version_id = version.id
        preset.version_selection_mode = self._validate_preset_version_selection_mode(version_selection_mode)
        preset.allow_explicit_version_override = bool(allow_explicit_version_override)
        preset.pinned_at = self.now()
        preset.pinned_by_user_id = actor_user_id
        preset.pin_reason = reason
        preset.unpinned_at = None
        preset.unpinned_by_user_id = None
        preset.unpin_reason = None
        self.db.flush()
        return preset

    def unpin_diagnostic_export_diff_gating_compare_preset_version(
        self,
        *,
        preset: AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePreset:
        if preset.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived diagnostic export diff gating compare presets cannot be unpinned",
            )
        if preset.pinned_version_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Diagnostic export diff gating compare preset is not pinned",
            )
        preset.pinned_version_id = None
        preset.version_selection_mode = "active_then_mutable"
        preset.pinned_at = None
        preset.pinned_by_user_id = None
        preset.pin_reason = None
        preset.unpinned_at = self.now()
        preset.unpinned_by_user_id = actor_user_id
        preset.unpin_reason = reason
        self.db.flush()
        return preset

    @staticmethod
    def _collect_diag_export_diff_gating_compare_reason_code_events(
        compare_report: AISystemGovernanceDiagnosticExportDiffGatingCompareReport,
    ) -> list[dict[str, str]]:
        result_json = compare_report.result_json if isinstance(compare_report.result_json, dict) else {}
        events: list[dict[str, str]] = []
        added = result_json.get("added_reason_codes")
        if isinstance(added, list):
            for code in added:
                if isinstance(code, str):
                    events.append({"reason_code": code, "change_type": "reason_code_added"})
        removed = result_json.get("removed_reason_codes")
        if isinstance(removed, list):
            for code in removed:
                if isinstance(code, str):
                    events.append({"reason_code": code, "change_type": "reason_code_removed"})
        changed = result_json.get("changed_reason_codes")
        if isinstance(changed, list):
            for item in changed:
                if not isinstance(item, dict):
                    continue
                code = item.get("reason_code")
                change_type = item.get("change_type")
                if isinstance(code, str) and isinstance(change_type, str):
                    events.append({"reason_code": code, "change_type": change_type})
        return events

    def evaluate_diagnostic_export_diff_gating_compare_preset(
        self,
        *,
        organization_id: uuid.UUID,
        compare_report_id: uuid.UUID,
        preset_id: uuid.UUID,
        preset_version_id: uuid.UUID | None,
        version_override_reason: str | None,
        persist_report: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        compare_report = self.require_diagnostic_export_diff_gating_compare_report(
            organization_id=organization_id,
            compare_report_id=compare_report_id,
        )
        preset = self.require_diagnostic_export_diff_gating_compare_preset(
            organization_id=organization_id,
            preset_id=preset_id,
        )
        if preset.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Diagnostic export diff gating compare preset must be active",
            )

        mode = self._validate_preset_version_selection_mode(
            str(preset.version_selection_mode or "active_then_mutable"),
            field_name="version_selection_mode",
        )
        explicit_override_used = False
        cleaned_override_reason = (version_override_reason or "").strip() or None
        if (
            preset_version_id is not None
            and preset.pinned_version_id is not None
            and preset_version_id != preset.pinned_version_id
        ):
            if not preset.allow_explicit_version_override:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Explicit preset_version_id override is not allowed for this preset",
                )
            if cleaned_override_reason is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="version_override_reason is required when overriding pinned_version_id",
                )
            explicit_override_used = True

        selected_version: AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion | None = None
        version_resolution_source = "mutable_preset"
        if mode == "active_then_mutable":
            if preset_version_id is not None:
                selected_version = self.require_diagnostic_export_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset_version_id,
                )
                version_resolution_source = "explicit_version"
            elif preset.active_version_id is not None:
                selected_version = self.require_diagnostic_export_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset.active_version_id,
                )
                version_resolution_source = "active_version"
        elif mode == "pinned_preferred":
            if preset_version_id is not None:
                if not preset.allow_explicit_version_override and (
                    preset.pinned_version_id is not None and preset_version_id != preset.pinned_version_id
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Explicit preset_version_id override is not allowed for this preset",
                    )
                selected_version = self.require_diagnostic_export_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset_version_id,
                )
                version_resolution_source = "explicit_version"
            elif preset.pinned_version_id is not None:
                selected_version = self.require_diagnostic_export_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset.pinned_version_id,
                )
                version_resolution_source = "pinned_version"
            elif preset.active_version_id is not None:
                selected_version = self.require_diagnostic_export_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset.active_version_id,
                )
                version_resolution_source = "active_version"
        else:  # pinned_required
            if preset.pinned_version_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Pinned preset version is required when version_selection_mode is pinned_required",
                )
            if preset_version_id is not None:
                if not preset.allow_explicit_version_override and (
                    preset.pinned_version_id is not None and preset_version_id != preset.pinned_version_id
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Explicit preset_version_id override is not allowed for this preset",
                    )
                if (
                    preset.pinned_version_id is not None
                    and preset_version_id != preset.pinned_version_id
                    and cleaned_override_reason is None
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="version_override_reason is required when overriding pinned_version_id",
                    )
                selected_version = self.require_diagnostic_export_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset_version_id,
                )
                version_resolution_source = "explicit_version"
            elif preset.pinned_version_id is not None:
                selected_version = self.require_diagnostic_export_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset.pinned_version_id,
                )
                version_resolution_source = "pinned_version"

        if selected_version is not None:
            resolved_snapshot = self._normalize_diagnostic_export_diff_gating_compare_preset_snapshot(
                snapshot_json=selected_version.snapshot_json,
            )
        else:
            resolved_snapshot = self._diagnostic_export_diff_gating_compare_preset_snapshot_from_row(preset)

        rules = (
            resolved_snapshot["interpretation_rules_json"]
            if isinstance(resolved_snapshot.get("interpretation_rules_json"), dict)
            else {}
        )
        watched_codes = set(
            code
            for code in (
                resolved_snapshot.get("watched_reason_codes_json")
                if isinstance(resolved_snapshot.get("watched_reason_codes_json"), list)
                else []
            )
            if isinstance(code, str)
        )
        ignored_codes = set(
            code
            for code in (
                resolved_snapshot.get("ignored_reason_codes_json")
                if isinstance(resolved_snapshot.get("ignored_reason_codes_json"), list)
                else []
            )
            if isinstance(code, str)
        )
        ignore_for_band = bool(rules.get("ignored_reason_codes_do_not_affect_band", False))
        watched_overrides_ignored = bool(rules.get("watched_reason_codes_override_ignored", False))

        all_events = self._collect_diag_export_diff_gating_compare_reason_code_events(compare_report)
        effective_events: list[dict[str, str]] = []
        for event in all_events:
            code = event["reason_code"]
            if ignore_for_band and code in ignored_codes and not (watched_overrides_ignored and code in watched_codes):
                continue
            effective_events.append(event)

        raw_watched_hits = [event for event in all_events if event["reason_code"] in watched_codes]
        effective_watched_hits = [event for event in effective_events if event["reason_code"] in watched_codes]
        ignored_hits = [event for event in all_events if event["reason_code"] in ignored_codes]

        effective_reason_code_changes_count = len(effective_events)
        effective_severity_changes_count = len(
            [event for event in effective_events if event.get("change_type") == "severity_changed"]
        )

        matched_rules: list[dict[str, Any]] = []
        band_candidates = [str(resolved_snapshot["default_interpretation_band"])]

        if compare_report.max_severity_drift == "increased" and isinstance(rules.get("severity_increase_band"), str):
            band_candidates.append(rules["severity_increase_band"])
            matched_rules.append({"rule": "severity_increase_band", "band": rules["severity_increase_band"]})
        if compare_report.max_severity_drift == "decreased" and isinstance(rules.get("severity_decrease_band"), str):
            band_candidates.append(rules["severity_decrease_band"])
            matched_rules.append({"rule": "severity_decrease_band", "band": rules["severity_decrease_band"]})

        if (
            compare_report.review_required_drift == "became_required"
            and isinstance(rules.get("review_required_flip_to_required_band"), str)
        ):
            band_candidates.append(rules["review_required_flip_to_required_band"])
            matched_rules.append(
                {
                    "rule": "review_required_flip_to_required_band",
                    "band": rules["review_required_flip_to_required_band"],
                }
            )
        if (
            compare_report.review_required_drift == "became_not_required"
            and isinstance(rules.get("review_required_flip_to_not_required_band"), str)
        ):
            band_candidates.append(rules["review_required_flip_to_not_required_band"])
            matched_rules.append(
                {
                    "rule": "review_required_flip_to_not_required_band",
                    "band": rules["review_required_flip_to_not_required_band"],
                }
            )

        if effective_watched_hits and isinstance(rules.get("watched_reason_code_band"), str):
            band_candidates.append(rules["watched_reason_code_band"])
            matched_rules.append(
                {
                    "rule": "watched_reason_code_band",
                    "band": rules["watched_reason_code_band"],
                    "hit_count": len(effective_watched_hits),
                }
            )

        reason_thresholds = rules.get("reason_code_changes_thresholds")
        if isinstance(reason_thresholds, list):
            winning_reason_threshold: dict[str, Any] | None = None
            for threshold in reason_thresholds:
                if not isinstance(threshold, dict):
                    continue
                min_changes = int(threshold.get("min_changes") or 0)
                band = threshold.get("band")
                if isinstance(band, str) and effective_reason_code_changes_count >= min_changes:
                    winning_reason_threshold = {"min_changes": min_changes, "band": band}
            if winning_reason_threshold is not None:
                band_candidates.append(winning_reason_threshold["band"])
                matched_rules.append(
                    {
                        "rule": "reason_code_changes_threshold",
                        "band": winning_reason_threshold["band"],
                        "min_changes": winning_reason_threshold["min_changes"],
                        "actual_changes": effective_reason_code_changes_count,
                    }
                )

        severity_thresholds = rules.get("severity_changes_thresholds")
        if isinstance(severity_thresholds, list):
            winning_severity_threshold: dict[str, Any] | None = None
            for threshold in severity_thresholds:
                if not isinstance(threshold, dict):
                    continue
                min_changes = int(threshold.get("min_changes") or 0)
                band = threshold.get("band")
                if isinstance(band, str) and effective_severity_changes_count >= min_changes:
                    winning_severity_threshold = {"min_changes": min_changes, "band": band}
            if winning_severity_threshold is not None:
                band_candidates.append(winning_severity_threshold["band"])
                matched_rules.append(
                    {
                        "rule": "severity_changes_threshold",
                        "band": winning_severity_threshold["band"],
                        "min_changes": winning_severity_threshold["min_changes"],
                        "actual_changes": effective_severity_changes_count,
                    }
                )

        interpretation_band = self._max_interpretation_band(*band_candidates)
        review_required = interpretation_band in {"review_required", "critical_review"}
        matched_rules_sorted = sorted(
            matched_rules,
            key=lambda item: (
                str(item.get("rule") or ""),
                str(item.get("band") or ""),
                int(item.get("min_changes") or 0),
            ),
        )

        result = {
            "persisted": persist_report,
            "preset_report_id": None,
            "compare_report_id": compare_report.id,
            "preset_id": preset.id,
            "preset_version_id": selected_version.id if selected_version else None,
            "preset_version_number": selected_version.version_number if selected_version else None,
            "preset_snapshot_used": self.json_safe(resolved_snapshot),
            "version_resolution_source": version_resolution_source,
            "pinned_version_id": preset.pinned_version_id,
            "explicit_version_override_used": bool(explicit_override_used),
            "version_override_reason": cleaned_override_reason if explicit_override_used else None,
            "interpretation_band": interpretation_band,
            "review_required": bool(review_required),
            "matched_rules": matched_rules_sorted,
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_CAVEAT,
        }
        result_for_storage = {
            **result,
            "watched_reason_codes_hit_count": len(raw_watched_hits),
            "ignored_reason_codes_hit_count": len(ignored_hits),
            "effective_watched_reason_codes_hit_count": len(effective_watched_hits),
            "effective_reason_code_changes_count": effective_reason_code_changes_count,
            "effective_severity_changes_count": effective_severity_changes_count,
            "watched_reason_codes_override_ignored": watched_overrides_ignored,
            "ignored_reason_codes_do_not_affect_band": ignore_for_band,
        }
        if persist_report:
            row = AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport(
                organization_id=organization_id,
                compare_report_id=compare_report.id,
                preset_id=preset.id,
                preset_version_id=selected_version.id if selected_version else None,
                preset_version_number=selected_version.version_number if selected_version else None,
                preset_snapshot_json=self.json_safe(resolved_snapshot),
                version_resolution_source=version_resolution_source,
                pinned_version_id=preset.pinned_version_id,
                explicit_version_override_used=bool(explicit_override_used),
                version_override_reason=cleaned_override_reason if explicit_override_used else None,
                status="generated",
                result_json=self.json_safe({**result_for_storage, "persisted": True, "preset_report_id": None}),
                interpretation_band=interpretation_band,
                review_required=bool(review_required),
                matched_rules_json=self.json_safe(matched_rules_sorted),
                created_by_user_id=actor_user_id,
            )
            self.db.add(row)
            self.db.flush()
            row.result_json["preset_report_id"] = str(row.id)
            self.db.flush()
            result["persisted"] = True
            result["preset_report_id"] = row.id
        return result

    def list_diagnostic_export_diff_gating_compare_preset_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        compare_report_id: uuid.UUID | None,
        preset_id: uuid.UUID | None,
        interpretation_band: str | None,
        review_required: bool | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport]:
        stmt = select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.status == status_filter)
        if compare_report_id is not None:
            stmt = stmt.where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.compare_report_id == compare_report_id
            )
        if preset_id is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.preset_id == preset_id)
        if interpretation_band is not None:
            self._validate_interpretation_band(interpretation_band, field_name="interpretation_band")
            stmt = stmt.where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.interpretation_band == interpretation_band
            )
        if review_required is not None:
            stmt = stmt.where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.review_required == review_required
            )
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_diagnostic_export_diff_gating_compare_preset_report(
        self,
        *,
        row: AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def diagnostic_export_diff_gating_compare_preset_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        preset_counts = dict(
            self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.status,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.status)
            ).all()
        )
        version_counts = dict(
            self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.status,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.id),
                )
                .where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.organization_id == organization_id
                )
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.status)
            ).all()
        )
        report_counts = dict(
            self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.status,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.status)
            ).all()
        )
        by_interpretation_band = {
            str(key): int(value)
            for key, value in self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.interpretation_band,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.interpretation_band)
            ).all()
            if key is not None
        }
        review_required_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.id)).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.review_required.is_(True),
                )
            ).scalar_one()
        )
        latest_preset_report_at = self.db.execute(
            select(func.max(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.created_at)).where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.organization_id == organization_id
            )
        ).scalar_one()
        presets_without_active_version = int(
            self.db.execute(
                select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id)).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.active_version_id.is_(None),
                )
            ).scalar_one()
        )
        pinned_presets = int(
            self.db.execute(
                select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id)).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.pinned_version_id.is_not(None),
                )
            ).scalar_one()
        )
        pinned_required_presets = int(
            self.db.execute(
                select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id)).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.version_selection_mode == "pinned_required",
                )
            ).scalar_one()
        )
        pinned_preferred_presets = int(
            self.db.execute(
                select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id)).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.version_selection_mode == "pinned_preferred",
                )
            ).scalar_one()
        )
        presets_allowing_explicit_override = int(
            self.db.execute(
                select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id)).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.allow_explicit_version_override.is_(True),
                )
            ).scalar_one()
        )
        presets_blocking_explicit_override = int(
            self.db.execute(
                select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id)).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.allow_explicit_version_override.is_(False),
                )
            ).scalar_one()
        )
        return {
            "active_presets": int(preset_counts.get("active", 0)),
            "inactive_presets": int(preset_counts.get("inactive", 0)),
            "archived_presets": int(preset_counts.get("archived", 0)),
            "total_preset_versions": int(sum(int(v or 0) for v in version_counts.values())),
            "active_preset_versions": int(version_counts.get("active", 0)),
            "draft_preset_versions": int(version_counts.get("draft", 0)),
            "deprecated_preset_versions": int(version_counts.get("deprecated", 0)),
            "archived_preset_versions": int(version_counts.get("archived", 0)),
            "presets_without_active_version": presets_without_active_version,
            "pinned_presets": pinned_presets,
            "pinned_required_presets": pinned_required_presets,
            "pinned_preferred_presets": pinned_preferred_presets,
            "presets_allowing_explicit_override": presets_allowing_explicit_override,
            "presets_blocking_explicit_override": presets_blocking_explicit_override,
            "total_preset_reports": int(sum(int(v or 0) for v in report_counts.values())),
            "active_preset_reports": int(report_counts.get("generated", 0)),
            "archived_preset_reports": int(report_counts.get("archived", 0)),
            "by_interpretation_band": by_interpretation_band,
            "review_required_reports": int(review_required_reports),
            "latest_preset_report_at": latest_preset_report_at,
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_CAVEAT,
        }

    def create_diagnostic_export_diff_gating_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        preset_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        scope_json: dict | list | None,
        priority: int,
        reason: str,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment:
        preset = self.require_diagnostic_export_diff_gating_compare_preset(
            organization_id=organization_id,
            preset_id=preset_id,
        )
        if preset.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived presets cannot be assigned")
        normalized_scope_id, normalized_scope_json = self._validate_diag_export_diff_compare_preset_assignment_scope(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            scope_json=scope_json,
        )
        if status_value == "active":
            self._assert_no_duplicate_active_diag_export_diff_compare_preset_assignment(
                organization_id=organization_id,
                scope_type=scope_type,
                scope_id=normalized_scope_id,
                scope_json=normalized_scope_json,
            )
        row = AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment(
            organization_id=organization_id,
            preset_id=preset_id,
            scope_type=scope_type,
            scope_id=normalized_scope_id,
            scope_json=normalized_scope_json,
            priority=priority,
            status=status_value,
            reason=reason,
            assigned_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        self._create_diag_export_diff_compare_preset_assignment_history(
            organization_id=organization_id,
            assignment_id=row.id,
            event_type="created",
            before_json=None,
            after_json=self._diag_export_diff_compare_preset_assignment_snapshot(row),
            reason=reason,
            actor_user_id=actor_user_id,
        )
        return row

    def list_diagnostic_export_diff_gating_compare_preset_assignments(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        scope_type: str | None,
        preset_id: uuid.UUID | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment]:
        stmt = select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.organization_id == organization_id,
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.status == status_filter)
        if scope_type is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.scope_type == scope_type)
        if preset_id is not None:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.preset_id == preset_id)
        if not include_archived:
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.priority.desc(),
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.updated_at.desc(),
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id.asc(),
                )
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def update_diagnostic_export_diff_gating_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        row: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment,
        updates: dict[str, Any],
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment:
        if row.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived diagnostic export diff gating compare preset assignments cannot be updated",
            )
        before = self._diag_export_diff_compare_preset_assignment_snapshot(row)
        effective_preset_id = updates.get("preset_id", row.preset_id)
        preset = self.require_diagnostic_export_diff_gating_compare_preset(
            organization_id=organization_id,
            preset_id=effective_preset_id,
        )
        if preset.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived presets cannot be assigned")
        effective_scope_type = updates.get("scope_type", row.scope_type)
        effective_scope_id = updates["scope_id"] if "scope_id" in updates else row.scope_id
        effective_scope_json = updates["scope_json"] if "scope_json" in updates else row.scope_json
        normalized_scope_id, normalized_scope_json = self._validate_diag_export_diff_compare_preset_assignment_scope(
            organization_id=organization_id,
            scope_type=effective_scope_type,
            scope_id=effective_scope_id,
            scope_json=effective_scope_json,
        )
        effective_status = updates.get("status", row.status)
        if effective_status == "active":
            self._assert_no_duplicate_active_diag_export_diff_compare_preset_assignment(
                organization_id=organization_id,
                scope_type=effective_scope_type,
                scope_id=normalized_scope_id,
                scope_json=normalized_scope_json,
                exclude_assignment_id=row.id,
            )
        row.preset_id = effective_preset_id
        row.scope_type = effective_scope_type
        row.scope_id = normalized_scope_id
        row.scope_json = normalized_scope_json
        if "priority" in updates:
            row.priority = int(updates["priority"])
        row.status = effective_status
        if "reason" in updates and updates["reason"] is not None:
            row.reason = str(updates["reason"])
        self.db.flush()
        self._create_diag_export_diff_compare_preset_assignment_history(
            organization_id=organization_id,
            assignment_id=row.id,
            event_type="updated",
            before_json=before,
            after_json=self._diag_export_diff_compare_preset_assignment_snapshot(row),
            reason=str(updates.get("reason") or row.reason),
            actor_user_id=actor_user_id,
        )
        return row

    def archive_diagnostic_export_diff_gating_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        row: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment:
        before = self._diag_export_diff_compare_preset_assignment_snapshot(row)
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        self._create_diag_export_diff_compare_preset_assignment_history(
            organization_id=organization_id,
            assignment_id=row.id,
            event_type="archived",
            before_json=before,
            after_json=self._diag_export_diff_compare_preset_assignment_snapshot(row),
            reason=reason,
            actor_user_id=actor_user_id,
        )
        return row

    def list_diagnostic_export_diff_gating_compare_preset_assignment_history(
        self,
        *,
        organization_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory]:
        return (
            self.db.execute(
                select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory)
                .where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory.assignment_id == assignment_id,
                )
                .order_by(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory.created_at.desc())
            )
            .scalars()
            .all()
        )

    def _diagnostic_export_diff_gating_compare_preset_assignment_candidates_for_scope(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        compare_report_id: uuid.UUID | None,
        gating_profile_id: uuid.UUID | None,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID],
        review_types: list[str],
        rollout_class: str | None,
        export_type: str | None,
        status_values: set[str] | None = None,
    ) -> list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment]:
        values = status_values or {"active"}
        stmt = select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.organization_id == organization_id,
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.status.in_(values),
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.scope_type == scope_type,
        )
        if scope_type == "diagnostic_export_diff_gating_compare_report":
            if compare_report_id is None:
                return []
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.scope_id == compare_report_id)
        elif scope_type == "diagnostic_export_diff_gating_profile":
            if gating_profile_id is None:
                return []
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.scope_id == gating_profile_id)
        elif scope_type == "sequence_pack":
            if sequence_pack_id is None:
                return []
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.scope_id == sequence_pack_id)
        elif scope_type == "ai_system":
            if not ai_system_ids:
                return []
            stmt = stmt.where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.scope_id.in_(ai_system_ids))
        elif scope_type in {"review_type", "rollout_class", "export_type", "all_ai_governance"}:
            pass
        else:
            return []
        rows = self.db.execute(
            stmt.order_by(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.priority.desc(),
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.updated_at.desc(),
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id.asc(),
            )
        ).scalars().all()
        if scope_type == "review_type":
            return [
                row
                for row in rows
                if self._extract_scope_value(scope_type=scope_type, scope_id=row.scope_id, scope_json=row.scope_json)
                in review_types
            ]
        if scope_type == "rollout_class":
            if not rollout_class:
                return []
            return [
                row
                for row in rows
                if self._extract_scope_value(scope_type=scope_type, scope_id=row.scope_id, scope_json=row.scope_json)
                == rollout_class
            ]
        if scope_type == "export_type":
            if not export_type:
                return []
            return [
                row
                for row in rows
                if self._extract_scope_value(scope_type=scope_type, scope_id=row.scope_id, scope_json=row.scope_json)
                == export_type
            ]
        return rows

    def resolve_diagnostic_export_diff_gating_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        explicit_preset_id: uuid.UUID | None,
        compare_report_id: uuid.UUID | None,
        gating_profile_id: uuid.UUID | None,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID] | None,
        review_types: list[str] | None,
        rollout_class: str | None,
        export_type: str | None,
    ) -> dict[str, Any]:
        ai_ids = sorted({item for item in (ai_system_ids or [])}, key=lambda item: str(item))
        review_type_values = sorted({item for item in (review_types or [])})
        normalized_rollout_class = rollout_class.strip() if isinstance(rollout_class, str) and rollout_class.strip() else None
        normalized_export_type = export_type.strip() if isinstance(export_type, str) and export_type.strip() else None
        if compare_report_id is not None:
            self.require_diagnostic_export_diff_gating_compare_report(
                organization_id=organization_id,
                compare_report_id=compare_report_id,
            )
        if gating_profile_id is not None:
            self.require_diagnostic_export_diff_gating_profile(
                organization_id=organization_id,
                profile_id=gating_profile_id,
            )
        if sequence_pack_id is not None:
            self.require_pack(organization_id=organization_id, pack_id=sequence_pack_id)
        if ai_ids:
            found = self.db.execute(
                select(AISystem.id).where(
                    AISystem.organization_id == organization_id,
                    AISystem.id.in_(ai_ids),
                )
            ).scalars().all()
            if len(found) != len(ai_ids):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more ai_system_ids not found")
        if any(item not in REVIEW_TYPES for item in review_type_values):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="review_types contains invalid review type")
        if normalized_export_type is not None and normalized_export_type not in {"diagnostic_report", "diagnostic_diff_report"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="export_type is invalid")

        precedence_trace: list[dict[str, Any]] = []
        if explicit_preset_id is not None:
            preset = self.require_diagnostic_export_diff_gating_compare_preset(
                organization_id=organization_id,
                preset_id=explicit_preset_id,
            )
            if preset.status != "active":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Resolved preset must be active",
                )
            precedence_trace.append(
                {
                    "scope_type": "explicit_request",
                    "matched": True,
                    "preset_id": str(preset.id),
                }
            )
            return {
                "resolved_preset_id": preset.id,
                "resolution_source": "explicit_request",
                "assignment_id": None,
                "precedence_trace": precedence_trace,
                "active_version_id": preset.active_version_id,
                "pinned_version_id": preset.pinned_version_id,
                "version_selection_mode": preset.version_selection_mode,
                "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_CAVEAT,
            }

        for scope_type, source in DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_SCOPE_PRECEDENCE:
            candidates = self._diagnostic_export_diff_gating_compare_preset_assignment_candidates_for_scope(
                organization_id=organization_id,
                scope_type=scope_type,
                compare_report_id=compare_report_id,
                gating_profile_id=gating_profile_id,
                sequence_pack_id=sequence_pack_id,
                ai_system_ids=ai_ids,
                review_types=review_type_values,
                rollout_class=normalized_rollout_class,
                export_type=normalized_export_type,
            )
            precedence_trace.append(
                {
                    "scope_type": scope_type,
                    "source": source,
                    "candidate_assignment_ids": [str(item.id) for item in candidates],
                    "matched": bool(candidates),
                }
            )
            if not candidates:
                continue
            selected = candidates[0]
            preset = self.require_diagnostic_export_diff_gating_compare_preset(
                organization_id=organization_id,
                preset_id=selected.preset_id,
            )
            if preset.status != "active":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Resolved mapped preset must be active",
                )
            precedence_trace[-1]["selected_assignment_id"] = str(selected.id)
            precedence_trace[-1]["selected_preset_id"] = str(preset.id)
            return {
                "resolved_preset_id": preset.id,
                "resolution_source": source,
                "assignment_id": selected.id,
                "precedence_trace": precedence_trace,
                "active_version_id": preset.active_version_id,
                "pinned_version_id": preset.pinned_version_id,
                "version_selection_mode": preset.version_selection_mode,
                "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_CAVEAT,
            }

        return {
            "resolved_preset_id": None,
            "resolution_source": "none",
            "assignment_id": None,
            "precedence_trace": precedence_trace,
            "active_version_id": None,
            "pinned_version_id": None,
            "version_selection_mode": None,
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_CAVEAT,
        }

    def evaluate_diagnostic_export_diff_gating_compare_preset_default(
        self,
        *,
        organization_id: uuid.UUID,
        compare_report_id: uuid.UUID,
        explicit_preset_id: uuid.UUID | None,
        gating_profile_id: uuid.UUID | None,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID] | None,
        review_types: list[str] | None,
        rollout_class: str | None,
        export_type: str | None,
        preset_version_id: uuid.UUID | None,
        version_override_reason: str | None,
        persist_report: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        preset_resolution = self.resolve_diagnostic_export_diff_gating_compare_preset_assignment(
            organization_id=organization_id,
            explicit_preset_id=explicit_preset_id,
            compare_report_id=compare_report_id,
            gating_profile_id=gating_profile_id,
            sequence_pack_id=sequence_pack_id,
            ai_system_ids=ai_system_ids,
            review_types=review_types,
            rollout_class=rollout_class,
            export_type=export_type,
        )
        resolved_preset_id = preset_resolution["resolved_preset_id"]
        if resolved_preset_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No preset could be resolved. Provide explicit_preset_id or configure preset assignments.",
            )
        result = self.evaluate_diagnostic_export_diff_gating_compare_preset(
            organization_id=organization_id,
            compare_report_id=compare_report_id,
            preset_id=resolved_preset_id,
            preset_version_id=preset_version_id,
            version_override_reason=version_override_reason,
            persist_report=persist_report,
            actor_user_id=actor_user_id,
        )
        merged = {
            **result,
            "preset_resolution": {
                "resolved_preset_id": preset_resolution["resolved_preset_id"],
                "resolution_source": preset_resolution["resolution_source"],
                "assignment_id": preset_resolution["assignment_id"],
                "precedence_trace": preset_resolution["precedence_trace"],
                "active_version_id": preset_resolution["active_version_id"],
                "pinned_version_id": preset_resolution["pinned_version_id"],
                "version_selection_mode": preset_resolution["version_selection_mode"],
                "caveat": preset_resolution["caveat"],
            },
        }
        if persist_report and result.get("preset_report_id") is not None:
            report = self.require_diagnostic_export_diff_gating_compare_preset_report(
                organization_id=organization_id,
                preset_report_id=result["preset_report_id"],
            )
            report.result_json = self.json_safe(merged)
            self.db.flush()
        return merged

    def diagnostic_export_diff_gating_compare_preset_assignment_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        counts = dict(
            self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.status,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.status)
            ).all()
        )
        by_scope_type = {
            str(key): int(value)
            for key, value in self.db.execute(
                select(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.scope_type,
                    func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id),
                )
                .where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.organization_id == organization_id)
                .group_by(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.scope_type)
            ).all()
            if key is not None
        }
        highest_priority = self.db.execute(
            select(func.max(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.priority)).where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.organization_id == organization_id
            )
        ).scalar_one()
        archived_preset_ids = set(
            self.db.execute(
                select(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.status == "archived",
                )
            ).scalars().all()
        )
        inactive_preset_ids = set(
            self.db.execute(
                select(AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.status == "inactive",
                )
            ).scalars().all()
        )
        assignments = self.db.execute(
            select(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id,
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.preset_id,
            ).where(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.organization_id == organization_id)
        ).all()
        assignments_to_archived = sum(1 for _, pid in assignments if pid in archived_preset_ids)
        assignments_to_inactive = sum(1 for _, pid in assignments if pid in inactive_preset_ids)
        return {
            "active_assignments": int(counts.get("active", 0)),
            "inactive_assignments": int(counts.get("inactive", 0)),
            "archived_assignments": int(counts.get("archived", 0)),
            "by_scope_type": by_scope_type,
            "assignments_to_archived_presets": int(assignments_to_archived),
            "assignments_to_inactive_presets": int(assignments_to_inactive),
            "highest_priority": int(highest_priority or 0),
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_CAVEAT,
        }

    def _validate_diag_export_diff_compare_preset_assignment_context_inputs(
        self,
        *,
        organization_id: uuid.UUID,
        explicit_preset_id: uuid.UUID | None,
        compare_report_id: uuid.UUID | None,
        gating_profile_id: uuid.UUID | None,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID] | None,
        review_types: list[str] | None,
        export_type: str | None,
    ) -> tuple[list[uuid.UUID], list[str], str | None]:
        ai_ids = sorted({item for item in (ai_system_ids or [])}, key=lambda item: str(item))
        review_type_values = sorted({item for item in (review_types or [])})
        normalized_export_type = export_type.strip() if isinstance(export_type, str) and export_type.strip() else None
        if explicit_preset_id is not None:
            self.require_diagnostic_export_diff_gating_compare_preset(
                organization_id=organization_id,
                preset_id=explicit_preset_id,
            )
        if compare_report_id is not None:
            self.require_diagnostic_export_diff_gating_compare_report(
                organization_id=organization_id,
                compare_report_id=compare_report_id,
            )
        if gating_profile_id is not None:
            self.require_diagnostic_export_diff_gating_profile(
                organization_id=organization_id,
                profile_id=gating_profile_id,
            )
        if sequence_pack_id is not None:
            self.require_pack(organization_id=organization_id, pack_id=sequence_pack_id)
        if ai_ids:
            found = self.db.execute(
                select(AISystem.id).where(
                    AISystem.organization_id == organization_id,
                    AISystem.id.in_(ai_ids),
                )
            ).scalars().all()
            if len(found) != len(ai_ids):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more ai_system_ids not found")
        if any(item not in REVIEW_TYPES for item in review_type_values):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="review_types contains invalid review type")
        if normalized_export_type is not None and normalized_export_type not in {"diagnostic_report", "diagnostic_diff_report"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="export_type is invalid")
        return ai_ids, review_type_values, normalized_export_type

    def _resolve_diag_export_diff_compare_preset_assignment_with_diagnostics(
        self,
        *,
        organization_id: uuid.UUID,
        explicit_preset_id: uuid.UUID | None,
        compare_report_id: uuid.UUID | None,
        gating_profile_id: uuid.UUID | None,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID],
        review_types: list[str],
        rollout_class: str | None,
        export_type: str | None,
        include_inactive_assignments: bool,
        include_archived_assignments: bool,
        include_version_diagnostics: bool,
    ) -> dict[str, Any]:
        precedence_trace: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        normalized_rollout_class = rollout_class.strip() if isinstance(rollout_class, str) and rollout_class.strip() else None

        def _append_diag(code: str, severity: str, details: dict[str, Any] | None = None) -> None:
            entry = {"code": code, "severity": severity}
            if details:
                entry["details"] = details
            diagnostics.append(entry)

        if explicit_preset_id is not None:
            preset = self.require_diagnostic_export_diff_gating_compare_preset(
                organization_id=organization_id,
                preset_id=explicit_preset_id,
            )
            _append_diag("EXPLICIT_PRESET_USED", "info")
            if preset.status == "inactive":
                _append_diag("ASSIGNMENT_TARGET_PRESET_INACTIVE", "critical", {"preset_id": str(preset.id)})
            elif preset.status == "archived":
                _append_diag("ASSIGNMENT_TARGET_PRESET_ARCHIVED", "critical", {"preset_id": str(preset.id)})
            else:
                _append_diag("RESOLVED", "info")
            if include_version_diagnostics:
                if preset.active_version_id is None:
                    _append_diag(
                        "ASSIGNMENT_TARGET_PRESET_MISSING_ACTIVE_VERSION",
                        "warning",
                        {"preset_id": str(preset.id)},
                    )
                if preset.version_selection_mode == "pinned_required" and preset.pinned_version_id is None:
                    _append_diag("PINNED_REQUIRED_WITHOUT_PIN", "critical", {"preset_id": str(preset.id)})
                if preset.pinned_version_id is not None:
                    pinned = self.db.execute(
                        select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion).where(
                            AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.organization_id == organization_id,
                            AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.id == preset.pinned_version_id,
                            AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.preset_id == preset.id,
                        )
                    ).scalar_one_or_none()
                    if pinned is None:
                        _append_diag("PINNED_VERSION_MISSING", "critical", {"preset_id": str(preset.id)})
                    elif pinned.status == "archived":
                        _append_diag("PINNED_VERSION_ARCHIVED", "critical", {"preset_id": str(preset.id)})
            return {
                "resolution_source": "explicit_request",
                "resolved_preset_id": preset.id,
                "resolved_assignment_id": None,
                "precedence_trace": precedence_trace,
                "diagnostics": diagnostics,
                "severity": self._max_diagnostic_severity(diagnostics),
                "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
            }

        selected_scope_type: str | None = None
        selected_source: str = "none"
        selected_assignment: AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment | None = None
        selected_preset: AISystemGovernanceDiagnosticExportDiffGatingComparePreset | None = None
        scopes_with_active_candidates = 0

        for scope_type, source in DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_SCOPE_PRECEDENCE:
            active_candidates = self._diagnostic_export_diff_gating_compare_preset_assignment_candidates_for_scope(
                organization_id=organization_id,
                scope_type=scope_type,
                compare_report_id=compare_report_id,
                gating_profile_id=gating_profile_id,
                sequence_pack_id=sequence_pack_id,
                ai_system_ids=ai_system_ids,
                review_types=review_types,
                rollout_class=normalized_rollout_class,
                export_type=export_type,
                status_values={"active"},
            )
            inactive_candidates: list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment] = []
            archived_candidates: list[AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment] = []
            if include_inactive_assignments:
                inactive_candidates = self._diagnostic_export_diff_gating_compare_preset_assignment_candidates_for_scope(
                    organization_id=organization_id,
                    scope_type=scope_type,
                    compare_report_id=compare_report_id,
                    gating_profile_id=gating_profile_id,
                    sequence_pack_id=sequence_pack_id,
                    ai_system_ids=ai_system_ids,
                    review_types=review_types,
                    rollout_class=normalized_rollout_class,
                    export_type=export_type,
                    status_values={"inactive"},
                )
            if include_archived_assignments:
                archived_candidates = self._diagnostic_export_diff_gating_compare_preset_assignment_candidates_for_scope(
                    organization_id=organization_id,
                    scope_type=scope_type,
                    compare_report_id=compare_report_id,
                    gating_profile_id=gating_profile_id,
                    sequence_pack_id=sequence_pack_id,
                    ai_system_ids=ai_system_ids,
                    review_types=review_types,
                    rollout_class=normalized_rollout_class,
                    export_type=export_type,
                    status_values={"archived"},
                )
            trace_item: dict[str, Any] = {
                "scope_type": scope_type,
                "source": source,
                "candidate_assignment_ids": [str(item.id) for item in active_candidates],
                "matched": bool(active_candidates),
            }
            if include_inactive_assignments:
                trace_item["inactive_assignment_ids"] = [str(item.id) for item in inactive_candidates]
            if include_archived_assignments:
                trace_item["archived_assignment_ids"] = [str(item.id) for item in archived_candidates]
            precedence_trace.append(trace_item)
            if active_candidates:
                scopes_with_active_candidates += 1
                if len(active_candidates) > 1:
                    _append_diag(
                        "CONFLICTING_ASSIGNMENTS_SAME_SCOPE",
                        "warning",
                        {"scope_type": scope_type, "candidate_assignment_ids": [str(item.id) for item in active_candidates]},
                    )
            if selected_assignment is not None or not active_candidates:
                continue
            selected_assignment = active_candidates[0]
            selected_scope_type = scope_type
            selected_source = source
            trace_item["selected_assignment_id"] = str(selected_assignment.id)
            selected_preset = self.db.execute(
                select(AISystemGovernanceDiagnosticExportDiffGatingComparePreset).where(
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id == selected_assignment.preset_id,
                )
            ).scalar_one_or_none()
            if selected_preset is not None:
                trace_item["selected_preset_id"] = str(selected_preset.id)

        if scopes_with_active_candidates > 1:
            _append_diag("MULTIPLE_ASSIGNMENTS_DIFFERENT_SCOPE", "warning", {"matched_scope_count": scopes_with_active_candidates})

        if selected_assignment is None:
            _append_diag("NO_ASSIGNMENT_FOUND", "critical")
            return {
                "resolution_source": "none",
                "resolved_preset_id": None,
                "resolved_assignment_id": None,
                "precedence_trace": precedence_trace,
                "diagnostics": diagnostics,
                "severity": self._max_diagnostic_severity(diagnostics),
                "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
            }

        highest_scope = DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_SCOPE_PRECEDENCE[0][0]
        if selected_scope_type is not None and selected_scope_type != highest_scope:
            _append_diag("CROSS_SCOPE_FALLBACK_USED", "info", {"selected_scope_type": selected_scope_type})

        if selected_preset is None:
            _append_diag(
                "ASSIGNMENT_TARGET_PRESET_ARCHIVED",
                "critical",
                {"assignment_id": str(selected_assignment.id), "preset_id": str(selected_assignment.preset_id)},
            )
            return {
                "resolution_source": selected_source,
                "resolved_preset_id": selected_assignment.preset_id,
                "resolved_assignment_id": selected_assignment.id,
                "precedence_trace": precedence_trace,
                "diagnostics": diagnostics,
                "severity": self._max_diagnostic_severity(diagnostics),
                "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
            }

        if selected_preset.status == "inactive":
            _append_diag("ASSIGNMENT_TARGET_PRESET_INACTIVE", "critical", {"preset_id": str(selected_preset.id)})
        elif selected_preset.status == "archived":
            _append_diag("ASSIGNMENT_TARGET_PRESET_ARCHIVED", "critical", {"preset_id": str(selected_preset.id)})
        else:
            _append_diag("RESOLVED", "info")

        if include_version_diagnostics:
            if selected_preset.active_version_id is None:
                _append_diag(
                    "ASSIGNMENT_TARGET_PRESET_MISSING_ACTIVE_VERSION",
                    "warning",
                    {"preset_id": str(selected_preset.id)},
                )
            if selected_preset.version_selection_mode == "pinned_required" and selected_preset.pinned_version_id is None:
                _append_diag("PINNED_REQUIRED_WITHOUT_PIN", "critical", {"preset_id": str(selected_preset.id)})
            if selected_preset.pinned_version_id is not None:
                pinned = self.db.execute(
                    select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion).where(
                        AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.organization_id == organization_id,
                        AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.id == selected_preset.pinned_version_id,
                        AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion.preset_id == selected_preset.id,
                    )
                ).scalar_one_or_none()
                if pinned is None:
                    _append_diag("PINNED_VERSION_MISSING", "critical", {"preset_id": str(selected_preset.id)})
                elif pinned.status == "archived":
                    _append_diag("PINNED_VERSION_ARCHIVED", "critical", {"preset_id": str(selected_preset.id)})

        return {
            "resolution_source": selected_source,
            "resolved_preset_id": selected_preset.id,
            "resolved_assignment_id": selected_assignment.id,
            "precedence_trace": precedence_trace,
            "diagnostics": diagnostics,
            "severity": self._max_diagnostic_severity(diagnostics),
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
        }

    def diagnostic_export_diff_gating_compare_preset_assignment_coverage_diagnostics(
        self,
        *,
        organization_id: uuid.UUID,
        contexts: list[dict[str, Any]],
        include_inactive_assignments: bool,
        include_archived_assignments: bool,
        include_version_diagnostics: bool,
    ) -> dict[str, Any]:
        context_results: list[dict[str, Any]] = []
        aggregate_counts: dict[str, int] = {}
        for idx, item in enumerate(contexts):
            explicit_preset_id = item.get("explicit_preset_id")
            compare_report_id = item.get("compare_report_id")
            gating_profile_id = item.get("gating_profile_id")
            sequence_pack_id = item.get("sequence_pack_id")
            ai_system_ids = item.get("ai_system_ids")
            review_types = item.get("review_types")
            rollout_class = item.get("rollout_class")
            export_type = item.get("export_type")
            ai_ids, review_type_values, normalized_export_type = self._validate_diag_export_diff_compare_preset_assignment_context_inputs(
                organization_id=organization_id,
                explicit_preset_id=explicit_preset_id,
                compare_report_id=compare_report_id,
                gating_profile_id=gating_profile_id,
                sequence_pack_id=sequence_pack_id,
                ai_system_ids=ai_system_ids,
                review_types=review_types,
                export_type=export_type,
            )
            resolved = self._resolve_diag_export_diff_compare_preset_assignment_with_diagnostics(
                organization_id=organization_id,
                explicit_preset_id=explicit_preset_id,
                compare_report_id=compare_report_id,
                gating_profile_id=gating_profile_id,
                sequence_pack_id=sequence_pack_id,
                ai_system_ids=ai_ids,
                review_types=review_type_values,
                rollout_class=rollout_class,
                export_type=normalized_export_type,
                include_inactive_assignments=include_inactive_assignments,
                include_archived_assignments=include_archived_assignments,
                include_version_diagnostics=include_version_diagnostics,
            )
            for diag in resolved["diagnostics"]:
                code = str(diag.get("code"))
                aggregate_counts[code] = int(aggregate_counts.get(code, 0) + 1)
            context_results.append(
                {
                    "context_key": item.get("context_key"),
                    "context_index": idx,
                    "resolution_source": resolved["resolution_source"],
                    "resolved_preset_id": resolved["resolved_preset_id"],
                    "resolved_assignment_id": resolved["resolved_assignment_id"],
                    "precedence_trace": resolved["precedence_trace"],
                    "diagnostics": resolved["diagnostics"],
                    "severity": resolved["severity"],
                    "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
                }
            )
        unresolved_count = sum(1 for item in context_results if item["resolved_preset_id"] is None)
        warning_count = sum(1 for item in context_results if item["severity"] == "warning")
        critical_count = sum(1 for item in context_results if item["severity"] == "critical")
        return {
            "context_count": len(context_results),
            "resolved_contexts_count": len(context_results) - unresolved_count,
            "unresolved_contexts_count": unresolved_count,
            "warning_contexts_count": warning_count,
            "critical_contexts_count": critical_count,
            "contexts": context_results,
            "aggregate_diagnostics": {key: int(value) for key, value in sorted(aggregate_counts.items())},
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
        }

    def diagnostic_export_diff_gating_compare_preset_assignment_health_diagnostics(
        self,
        *,
        organization_id: uuid.UUID,
    ) -> dict[str, Any]:
        rows = self.db.execute(
            select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment).where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.organization_id == organization_id
            )
        ).scalars().all()
        active = [row for row in rows if row.status == "active"]
        inactive = [row for row in rows if row.status == "inactive"]
        archived = [row for row in rows if row.status == "archived"]
        preset_ids = sorted({row.preset_id for row in rows}, key=lambda item: str(item))
        preset_map = (
            {
                row.id: row
                for row in self.db.execute(
                    select(AISystemGovernanceDiagnosticExportDiffGatingComparePreset).where(
                        AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
                        AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id.in_(preset_ids),
                    )
                )
                .scalars()
                .all()
            }
            if preset_ids
            else {}
        )
        assignments_to_inactive_presets = 0
        assignments_to_archived_presets = 0
        assignments_with_missing_preset = 0
        assignments_with_pinned_required_without_pin = 0
        for row in rows:
            preset = preset_map.get(row.preset_id)
            if preset is None:
                assignments_with_missing_preset += 1
                continue
            if preset.status == "inactive":
                assignments_to_inactive_presets += 1
            elif preset.status == "archived":
                assignments_to_archived_presets += 1
            if preset.version_selection_mode == "pinned_required" and preset.pinned_version_id is None:
                assignments_with_pinned_required_without_pin += 1
        exact_scope_groups: dict[tuple[str, str | None], int] = {}
        for row in active:
            scope_value = self._extract_scope_value(scope_type=row.scope_type, scope_id=row.scope_id, scope_json=row.scope_json)
            key = (row.scope_type, scope_value)
            exact_scope_groups[key] = int(exact_scope_groups.get(key, 0) + 1)
        duplicate_active_exact_scope_groups = sum(1 for count in exact_scope_groups.values() if count > 1)
        scope_type_counts: dict[str, int] = {}
        for row in active:
            scope_type_counts[row.scope_type] = int(scope_type_counts.get(row.scope_type, 0) + 1)
        same_scope_conflict_groups = sum(1 for count in scope_type_counts.values() if count > 1)
        return {
            "active_assignments": len(active),
            "inactive_assignments": len(inactive),
            "archived_assignments": len(archived),
            "assignments_to_inactive_presets": int(assignments_to_inactive_presets),
            "assignments_to_archived_presets": int(assignments_to_archived_presets),
            "assignments_with_missing_preset": int(assignments_with_missing_preset),
            "assignments_with_pinned_required_without_pin": int(assignments_with_pinned_required_without_pin),
            "duplicate_active_exact_scope_groups": int(duplicate_active_exact_scope_groups),
            "same_scope_conflict_groups": int(same_scope_conflict_groups),
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
        }

    def diagnostic_export_diff_gating_compare_preset_assignment_coverage_summary(
        self,
        *,
        organization_id: uuid.UUID,
    ) -> dict[str, Any]:
        rows = self.db.execute(
            select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment).where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.organization_id == organization_id
            )
        ).scalars().all()
        by_scope: dict[str, int] = {}
        for row in rows:
            by_scope[row.scope_type] = int(by_scope.get(row.scope_type, 0) + 1)
        active_rows = [row for row in rows if row.status == "active"]
        inactive_rows = [row for row in rows if row.status == "inactive"]
        archived_rows = [row for row in rows if row.status == "archived"]
        preset_ids = sorted({row.preset_id for row in rows}, key=lambda item: str(item))
        preset_rows = self.db.execute(
            select(AISystemGovernanceDiagnosticExportDiffGatingComparePreset).where(
                AISystemGovernanceDiagnosticExportDiffGatingComparePreset.organization_id == organization_id,
            )
        ).scalars().all()
        preset_map = {row.id: row for row in preset_rows}
        assignments_to_archived_presets = 0
        assignments_to_inactive_presets = 0
        assignments_with_missing_preset = 0
        assignments_with_pinned_required_without_pin = 0
        for row in rows:
            preset = preset_map.get(row.preset_id)
            if preset is None:
                assignments_with_missing_preset += 1
                continue
            if preset.status == "archived":
                assignments_to_archived_presets += 1
            elif preset.status == "inactive":
                assignments_to_inactive_presets += 1
            if preset.version_selection_mode == "pinned_required" and preset.pinned_version_id is None:
                assignments_with_pinned_required_without_pin += 1
        total_problem_assignments = (
            assignments_to_archived_presets
            + assignments_to_inactive_presets
            + assignments_with_missing_preset
            + assignments_with_pinned_required_without_pin
        )
        non_archived_assignment_preset_ids = {row.preset_id for row in rows if row.status in {"active", "inactive"}}
        active_presets_without_assignments = sum(
            1
            for preset in preset_rows
            if preset.status == "active" and preset.id not in non_archived_assignment_preset_ids
        )
        pinned_presets_with_assignment_count = sum(
            1
            for preset in preset_rows
            if preset.pinned_version_id is not None and preset.id in non_archived_assignment_preset_ids
        )
        return {
            "total_active_assignments": len(active_rows),
            "total_inactive_assignments": len(inactive_rows),
            "total_archived_assignments": len(archived_rows),
            "total_problem_assignments": int(total_problem_assignments),
            "assignments_by_scope_type": {str(key): int(value) for key, value in sorted(by_scope.items())},
            "presets_referenced_by_assignments": len(preset_ids),
            "active_presets_without_assignments": int(active_presets_without_assignments),
            "pinned_presets_with_assignment_count": int(pinned_presets_with_assignment_count),
            "caveat": DIAGNOSTIC_EXPORT_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
        }

    @staticmethod
    def _gating_severity_rank(value: str) -> int:
        rank = {severity: idx for idx, severity in enumerate(POLICY_DIFF_GATING_SEVERITY_ORDER)}
        return rank.get(value, rank["info"])

    @classmethod
    def _gating_severity_direction(cls, base_severity: str, compare_severity: str) -> str:
        base_rank = cls._gating_severity_rank(base_severity)
        compare_rank = cls._gating_severity_rank(compare_severity)
        if compare_rank > base_rank:
            return "increased"
        if compare_rank < base_rank:
            return "decreased"
        return "unchanged"

    @staticmethod
    def _review_required_drift(base_review_required: bool, compare_review_required: bool) -> str:
        if not base_review_required and compare_review_required:
            return "became_required"
        if base_review_required and not compare_review_required:
            return "became_not_required"
        return "unchanged"

    @staticmethod
    def _extract_gating_reason_classifications(gating_report: AISystemGovernancePolicyDiffGatingReport) -> dict[str, dict[str, Any]]:
        result_json = gating_report.result_json if isinstance(gating_report.result_json, dict) else {}
        rows = result_json.get("reason_code_classifications")
        out: dict[str, dict[str, Any]] = {}
        if not isinstance(rows, list):
            return out
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = row.get("reason_code")
            if not isinstance(code, str) or not code:
                continue
            out[code] = {
                "count": int(row.get("count") or 0),
                "severity": row.get("severity") if isinstance(row.get("severity"), str) else "info",
                "review_required": bool(row.get("review_required", False)),
            }
        return out

    @staticmethod
    def _extract_gating_severity_summary(gating_report: AISystemGovernancePolicyDiffGatingReport) -> dict[str, int]:
        result_json = gating_report.result_json if isinstance(gating_report.result_json, dict) else {}
        summary = result_json.get("severity_summary")
        out = {severity: 0 for severity in POLICY_DIFF_GATING_SEVERITY_ORDER}
        if isinstance(summary, dict):
            for key, value in summary.items():
                if key in out:
                    out[key] = int(value or 0)
        return out

    @staticmethod
    def _extract_diagnostic_export_diff_gating_reason_classifications(
        gating_report: AISystemGovernanceDiagnosticExportDiffGatingReport,
    ) -> dict[str, dict[str, Any]]:
        result_json = gating_report.result_json if isinstance(gating_report.result_json, dict) else {}
        rows = result_json.get("reason_code_classifications")
        out: dict[str, dict[str, Any]] = {}
        if not isinstance(rows, list):
            return out
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = row.get("reason_code")
            if not isinstance(code, str) or not code:
                continue
            out[code] = {
                "count": int(row.get("count") or 0),
                "severity": row.get("severity") if isinstance(row.get("severity"), str) else "info",
                "review_required": bool(row.get("review_required", False)),
            }
        return out

    @staticmethod
    def _extract_diagnostic_export_diff_gating_severity_summary(
        gating_report: AISystemGovernanceDiagnosticExportDiffGatingReport,
    ) -> dict[str, int]:
        result_json = gating_report.result_json if isinstance(gating_report.result_json, dict) else {}
        summary = result_json.get("severity_summary")
        out = {severity: 0 for severity in POLICY_DIFF_GATING_SEVERITY_ORDER}
        if isinstance(summary, dict):
            for key, value in summary.items():
                if key in out:
                    out[key] = int(value or 0)
        return out

    def compare_policy_diff_gating_reports(
        self,
        *,
        organization_id: uuid.UUID,
        base_gating_report_id: uuid.UUID,
        compare_gating_report_id: uuid.UUID,
        title: str | None,
        persist_compare: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        base_report = self.require_policy_diff_gating_report(
            organization_id=organization_id,
            gating_report_id=base_gating_report_id,
        )
        compare_report = self.require_policy_diff_gating_report(
            organization_id=organization_id,
            gating_report_id=compare_gating_report_id,
        )

        severity_direction = self._gating_severity_direction(
            base_report.max_severity,
            compare_report.max_severity,
        )
        review_required_changed = bool(base_report.review_required != compare_report.review_required)

        base_codes = self._extract_gating_reason_classifications(base_report)
        compare_codes = self._extract_gating_reason_classifications(compare_report)
        all_codes = sorted(set(base_codes.keys()).union(compare_codes.keys()))
        reason_code_changes: list[dict[str, Any]] = []

        for code in all_codes:
            base_item = base_codes.get(code)
            compare_item = compare_codes.get(code)
            if base_item is None and compare_item is not None:
                reason_code_changes.append(
                    {
                        "reason_code": code,
                        "change_type": "reason_code_added",
                        "before": None,
                        "after": compare_item,
                    }
                )
                continue
            if base_item is not None and compare_item is None:
                reason_code_changes.append(
                    {
                        "reason_code": code,
                        "change_type": "reason_code_removed",
                        "before": base_item,
                        "after": None,
                    }
                )
                continue
            assert base_item is not None and compare_item is not None
            if base_item["severity"] != compare_item["severity"]:
                reason_code_changes.append(
                    {
                        "reason_code": code,
                        "change_type": "severity_changed",
                        "before": base_item["severity"],
                        "after": compare_item["severity"],
                    }
                )
            if bool(base_item["review_required"]) != bool(compare_item["review_required"]):
                reason_code_changes.append(
                    {
                        "reason_code": code,
                        "change_type": "review_required_changed",
                        "before": bool(base_item["review_required"]),
                        "after": bool(compare_item["review_required"]),
                    }
                )
            if int(base_item["count"]) != int(compare_item["count"]):
                reason_code_changes.append(
                    {
                        "reason_code": code,
                        "change_type": "count_changed",
                        "before": int(base_item["count"]),
                        "after": int(compare_item["count"]),
                    }
                )

        base_severity_summary = self._extract_gating_severity_summary(base_report)
        compare_severity_summary = self._extract_gating_severity_summary(compare_report)
        aggregate_deltas = {
            "reason_code_count_delta": int(compare_report.reason_code_count - base_report.reason_code_count),
            "severity_summary_delta": {
                severity: int(compare_severity_summary.get(severity, 0)) - int(base_severity_summary.get(severity, 0))
                for severity in POLICY_DIFF_GATING_SEVERITY_ORDER
            },
        }
        result = {
            "persisted": persist_compare,
            "compare_report_id": None,
            "base_gating_report_id": base_report.id,
            "compare_gating_report_id": compare_report.id,
            "base_max_severity": base_report.max_severity,
            "compare_max_severity": compare_report.max_severity,
            "severity_direction": severity_direction,
            "base_review_required": bool(base_report.review_required),
            "compare_review_required": bool(compare_report.review_required),
            "review_required_changed": review_required_changed,
            "reason_code_changes_count": len(reason_code_changes),
            "reason_code_changes": reason_code_changes,
            "aggregate_deltas": aggregate_deltas,
            "caveat": POLICY_DIFF_GATING_COMPARE_CAVEAT,
        }

        if persist_compare:
            row = AISystemGovernancePolicyDiffGatingCompareReport(
                organization_id=organization_id,
                base_gating_report_id=base_report.id,
                compare_gating_report_id=compare_report.id,
                title=title.strip() if isinstance(title, str) and title.strip() else None,
                status="generated",
                result_json=self.json_safe({**result, "persisted": True, "compare_report_id": None}),
                base_max_severity=base_report.max_severity,
                compare_max_severity=compare_report.max_severity,
                severity_direction=severity_direction,
                review_required_changed=review_required_changed,
                base_review_required=bool(base_report.review_required),
                compare_review_required=bool(compare_report.review_required),
                reason_code_changes_count=len(reason_code_changes),
                created_by_user_id=actor_user_id,
            )
            self.db.add(row)
            self.db.flush()
            row.result_json["compare_report_id"] = str(row.id)
            self.db.flush()
            result["persisted"] = True
            result["compare_report_id"] = row.id
        return result

    def list_policy_diff_gating_compare_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        base_gating_report_id: uuid.UUID | None,
        compare_gating_report_id: uuid.UUID | None,
        severity_direction: str | None,
        review_required_changed: bool | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePolicyDiffGatingCompareReport]:
        stmt = select(AISystemGovernancePolicyDiffGatingCompareReport).where(
            AISystemGovernancePolicyDiffGatingCompareReport.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingCompareReport.status == status_filter)
        if base_gating_report_id is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingCompareReport.base_gating_report_id == base_gating_report_id)
        if compare_gating_report_id is not None:
            stmt = stmt.where(
                AISystemGovernancePolicyDiffGatingCompareReport.compare_gating_report_id == compare_gating_report_id
            )
        if severity_direction is not None:
            if severity_direction not in {"increased", "decreased", "unchanged"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="severity_direction must be one of: increased, decreased, unchanged",
                )
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingCompareReport.severity_direction == severity_direction)
        if review_required_changed is not None:
            stmt = stmt.where(
                AISystemGovernancePolicyDiffGatingCompareReport.review_required_changed == review_required_changed
            )
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePolicyDiffGatingCompareReport.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_policy_diff_gating_compare_report(
        self,
        *,
        row: AISystemGovernancePolicyDiffGatingCompareReport,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingCompareReport:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def policy_diff_gating_compare_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        counts_by_status = dict(
            self.db.execute(
                select(
                    AISystemGovernancePolicyDiffGatingCompareReport.status,
                    func.count(AISystemGovernancePolicyDiffGatingCompareReport.id),
                )
                .where(AISystemGovernancePolicyDiffGatingCompareReport.organization_id == organization_id)
                .group_by(AISystemGovernancePolicyDiffGatingCompareReport.status)
            ).all()
        )
        counts_by_direction = dict(
            self.db.execute(
                select(
                    AISystemGovernancePolicyDiffGatingCompareReport.severity_direction,
                    func.count(AISystemGovernancePolicyDiffGatingCompareReport.id),
                )
                .where(AISystemGovernancePolicyDiffGatingCompareReport.organization_id == organization_id)
                .group_by(AISystemGovernancePolicyDiffGatingCompareReport.severity_direction)
            ).all()
        )
        review_required_changed_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingCompareReport.id)).where(
                    AISystemGovernancePolicyDiffGatingCompareReport.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingCompareReport.review_required_changed.is_(True),
                )
            ).scalar_one()
        )
        total_reason_code_changes = int(
            self.db.execute(
                select(func.coalesce(func.sum(AISystemGovernancePolicyDiffGatingCompareReport.reason_code_changes_count), 0)).where(
                    AISystemGovernancePolicyDiffGatingCompareReport.organization_id == organization_id,
                )
            ).scalar_one()
        )
        latest_compare_report_at = self.db.execute(
            select(func.max(AISystemGovernancePolicyDiffGatingCompareReport.created_at)).where(
                AISystemGovernancePolicyDiffGatingCompareReport.organization_id == organization_id,
            )
        ).scalar_one()
        return {
            "total_compare_reports": int(sum(int(v or 0) for v in counts_by_status.values())),
            "active_compare_reports": int(counts_by_status.get("generated", 0)),
            "archived_compare_reports": int(counts_by_status.get("archived", 0)),
            "severity_increased_reports": int(counts_by_direction.get("increased", 0)),
            "severity_decreased_reports": int(counts_by_direction.get("decreased", 0)),
            "severity_unchanged_reports": int(counts_by_direction.get("unchanged", 0)),
            "review_required_changed_reports": int(review_required_changed_reports),
            "total_reason_code_changes": total_reason_code_changes,
            "latest_compare_report_at": latest_compare_report_at,
            "caveat": POLICY_DIFF_GATING_COMPARE_CAVEAT,
        }

    @staticmethod
    def _interpretation_band_rank(value: str) -> int:
        rank = {band: idx for idx, band in enumerate(POLICY_DIFF_GATING_INTERPRETATION_BANDS)}
        return rank.get(value, rank["stable"])

    @classmethod
    def _max_interpretation_band(cls, *bands: str) -> str:
        ranked = sorted((band for band in bands if band), key=cls._interpretation_band_rank)
        return ranked[-1] if ranked else "stable"

    def create_policy_diff_gating_compare_preset(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        status_value: str,
        baseline_gating_report_id: uuid.UUID | None,
        baseline_gating_profile_id: uuid.UUID | None,
        watched_reason_codes_json: dict | list | None,
        ignored_reason_codes_json: dict | list | None,
        interpretation_rules_json: dict | list | None,
        default_interpretation_band: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePreset:
        (
            normalized_baseline_report_id,
            normalized_baseline_profile_id,
            normalized_watched,
            normalized_ignored,
            normalized_rules,
            normalized_default_band,
        ) = self._normalize_gating_compare_preset_inputs(
            organization_id=organization_id,
            baseline_gating_report_id=baseline_gating_report_id,
            baseline_gating_profile_id=baseline_gating_profile_id,
            watched_reason_codes_json=watched_reason_codes_json,
            ignored_reason_codes_json=ignored_reason_codes_json,
            interpretation_rules_json=interpretation_rules_json,
            default_interpretation_band=default_interpretation_band,
        )
        row = AISystemGovernancePolicyDiffGatingComparePreset(
            organization_id=organization_id,
            name=name,
            description=description,
            status=status_value,
            baseline_gating_report_id=normalized_baseline_report_id,
            baseline_gating_profile_id=normalized_baseline_profile_id,
            watched_reason_codes_json=normalized_watched,
            ignored_reason_codes_json=normalized_ignored,
            interpretation_rules_json=normalized_rules,
            default_interpretation_band=normalized_default_band,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_policy_diff_gating_compare_presets(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePolicyDiffGatingComparePreset]:
        stmt = select(AISystemGovernancePolicyDiffGatingComparePreset).where(
            AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePreset.status == status_filter)
        if not include_archived:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePreset.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePolicyDiffGatingComparePreset.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def update_policy_diff_gating_compare_preset(
        self,
        *,
        row: AISystemGovernancePolicyDiffGatingComparePreset,
        updates: dict[str, Any],
    ) -> AISystemGovernancePolicyDiffGatingComparePreset:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived policy diff gating compare presets cannot be updated")

        (
            normalized_baseline_report_id,
            normalized_baseline_profile_id,
            normalized_watched,
            normalized_ignored,
            normalized_rules,
            normalized_default_band,
        ) = self._normalize_gating_compare_preset_inputs(
            organization_id=row.organization_id,
            baseline_gating_report_id=updates.get("baseline_gating_report_id", row.baseline_gating_report_id),
            baseline_gating_profile_id=updates.get("baseline_gating_profile_id", row.baseline_gating_profile_id),
            watched_reason_codes_json=updates.get("watched_reason_codes_json", row.watched_reason_codes_json),
            ignored_reason_codes_json=updates.get("ignored_reason_codes_json", row.ignored_reason_codes_json),
            interpretation_rules_json=updates.get("interpretation_rules_json", row.interpretation_rules_json),
            default_interpretation_band=updates.get("default_interpretation_band", row.default_interpretation_band),
        )
        if "name" in updates:
            row.name = updates["name"]
        if "description" in updates:
            row.description = updates["description"]
        if "status" in updates:
            row.status = updates["status"]
        row.baseline_gating_report_id = normalized_baseline_report_id
        row.baseline_gating_profile_id = normalized_baseline_profile_id
        row.watched_reason_codes_json = normalized_watched
        row.ignored_reason_codes_json = normalized_ignored
        row.interpretation_rules_json = normalized_rules
        row.default_interpretation_band = normalized_default_band
        if "version_selection_mode" in updates and updates["version_selection_mode"] is not None:
            row.version_selection_mode = self._validate_preset_version_selection_mode(
                str(updates["version_selection_mode"]),
                field_name="version_selection_mode",
            )
        if "allow_explicit_version_override" in updates and updates["allow_explicit_version_override"] is not None:
            row.allow_explicit_version_override = bool(updates["allow_explicit_version_override"])
        self.db.flush()
        return row

    def archive_policy_diff_gating_compare_preset(
        self,
        *,
        row: AISystemGovernancePolicyDiffGatingComparePreset,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePreset:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def pin_policy_diff_gating_compare_preset_version(
        self,
        *,
        preset: AISystemGovernancePolicyDiffGatingComparePreset,
        version: AISystemGovernancePolicyDiffGatingComparePresetVersion,
        version_selection_mode: str,
        allow_explicit_version_override: bool,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePreset:
        if preset.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived policy diff gating compare presets cannot be pinned",
            )
        if version.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived policy diff gating compare preset versions cannot be pinned",
            )
        preset.pinned_version_id = version.id
        preset.version_selection_mode = self._validate_preset_version_selection_mode(version_selection_mode)
        preset.allow_explicit_version_override = bool(allow_explicit_version_override)
        preset.pinned_at = self.now()
        preset.pinned_by_user_id = actor_user_id
        preset.pin_reason = reason
        preset.unpinned_at = None
        preset.unpinned_by_user_id = None
        preset.unpin_reason = None
        self.db.flush()
        return preset

    def unpin_policy_diff_gating_compare_preset_version(
        self,
        *,
        preset: AISystemGovernancePolicyDiffGatingComparePreset,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePreset:
        if preset.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived policy diff gating compare presets cannot be unpinned",
            )
        if preset.pinned_version_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Policy diff gating compare preset is not pinned",
            )
        preset.pinned_version_id = None
        preset.version_selection_mode = "active_then_mutable"
        preset.pinned_at = None
        preset.pinned_by_user_id = None
        preset.pin_reason = None
        preset.unpinned_at = self.now()
        preset.unpinned_by_user_id = actor_user_id
        preset.unpin_reason = reason
        self.db.flush()
        return preset

    def create_policy_diff_gating_compare_preset_version(
        self,
        *,
        organization_id: uuid.UUID,
        preset: AISystemGovernancePolicyDiffGatingComparePreset,
        change_reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetVersion:
        if preset.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived policy diff gating compare presets cannot accept new versions",
            )
        snapshot = self._preset_snapshot_from_row(preset)
        max_version = self.db.execute(
            select(func.max(AISystemGovernancePolicyDiffGatingComparePresetVersion.version_number)).where(
                AISystemGovernancePolicyDiffGatingComparePresetVersion.organization_id == organization_id,
                AISystemGovernancePolicyDiffGatingComparePresetVersion.preset_id == preset.id,
            )
        ).scalar_one()
        next_version = int(max_version or 0) + 1
        row = AISystemGovernancePolicyDiffGatingComparePresetVersion(
            organization_id=organization_id,
            preset_id=preset.id,
            version_number=next_version,
            status="draft",
            snapshot_json=self.json_safe(snapshot),
            change_reason=change_reason,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_policy_diff_gating_compare_preset_versions(
        self,
        *,
        organization_id: uuid.UUID,
        preset_id: uuid.UUID,
    ) -> list[AISystemGovernancePolicyDiffGatingComparePresetVersion]:
        return (
            self.db.execute(
                select(AISystemGovernancePolicyDiffGatingComparePresetVersion)
                .where(
                    AISystemGovernancePolicyDiffGatingComparePresetVersion.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePresetVersion.preset_id == preset_id,
                )
                .order_by(
                    AISystemGovernancePolicyDiffGatingComparePresetVersion.version_number.desc(),
                    AISystemGovernancePolicyDiffGatingComparePresetVersion.created_at.desc(),
                )
            )
            .scalars()
            .all()
        )

    def activate_policy_diff_gating_compare_preset_version(
        self,
        *,
        organization_id: uuid.UUID,
        preset: AISystemGovernancePolicyDiffGatingComparePreset,
        version: AISystemGovernancePolicyDiffGatingComparePresetVersion,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetVersion:
        existing_active = None
        if preset.active_version_id is not None:
            existing_active = self.db.execute(
                select(AISystemGovernancePolicyDiffGatingComparePresetVersion).where(
                    AISystemGovernancePolicyDiffGatingComparePresetVersion.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePresetVersion.preset_id == preset.id,
                    AISystemGovernancePolicyDiffGatingComparePresetVersion.id == preset.active_version_id,
                )
            ).scalar_one_or_none()
        if existing_active is not None and existing_active.id != version.id:
            existing_active.status = "deprecated"
        version.status = "active"
        version.activated_by_user_id = actor_user_id
        version.activated_at = self.now()
        preset.active_version_id = version.id
        self.db.flush()
        return version

    def archive_policy_diff_gating_compare_preset_version(
        self,
        *,
        preset: AISystemGovernancePolicyDiffGatingComparePreset,
        version: AISystemGovernancePolicyDiffGatingComparePresetVersion,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetVersion:
        if version.status == "active" and preset.active_version_id == version.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Active policy diff gating compare preset version cannot be archived",
            )
        version.status = "archived"
        if version.archived_at is None:
            version.archived_at = self.now()
        self.db.flush()
        return version

    def evaluate_policy_diff_gating_compare_preset(
        self,
        *,
        organization_id: uuid.UUID,
        preset_id: uuid.UUID,
        preset_version_id: uuid.UUID | None,
        version_override_reason: str | None,
        base_gating_report_id: uuid.UUID | None,
        compare_gating_report_id: uuid.UUID,
        persist_report: bool,
        persist_compare_report: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        preset = self.require_policy_diff_gating_compare_preset(
            organization_id=organization_id,
            preset_id=preset_id,
        )
        if preset.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Policy diff gating compare preset must be active")
        mode = self._validate_preset_version_selection_mode(
            str(preset.version_selection_mode or "active_then_mutable"),
            field_name="version_selection_mode",
        )
        explicit_override_used = False
        cleaned_override_reason = (version_override_reason or "").strip() or None
        if preset_version_id is not None and preset.pinned_version_id is not None and preset_version_id != preset.pinned_version_id:
            if not preset.allow_explicit_version_override:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Explicit preset_version_id override is not allowed for this preset",
                )
            if cleaned_override_reason is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="version_override_reason is required when overriding pinned_version_id",
                )
            explicit_override_used = True
        selected_version: AISystemGovernancePolicyDiffGatingComparePresetVersion | None = None
        version_resolution_source = "mutable_preset"
        if mode == "active_then_mutable":
            if preset_version_id is not None:
                selected_version = self.require_policy_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset_version_id,
                )
                version_resolution_source = "explicit_version"
            elif preset.active_version_id is not None:
                selected_version = self.require_policy_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset.active_version_id,
                )
                version_resolution_source = "active_version"
        elif mode == "pinned_preferred":
            if preset_version_id is not None:
                if not preset.allow_explicit_version_override and (
                    preset.pinned_version_id is not None and preset_version_id != preset.pinned_version_id
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Explicit preset_version_id override is not allowed for this preset",
                    )
                selected_version = self.require_policy_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset_version_id,
                )
                version_resolution_source = "explicit_version"
            elif preset.pinned_version_id is not None:
                selected_version = self.require_policy_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset.pinned_version_id,
                )
                version_resolution_source = "pinned_version"
            elif preset.active_version_id is not None:
                selected_version = self.require_policy_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset.active_version_id,
                )
                version_resolution_source = "active_version"
        else:  # pinned_required
            if preset.pinned_version_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Pinned preset version is required when version_selection_mode is pinned_required",
                )
            if preset_version_id is not None:
                if not preset.allow_explicit_version_override and (
                    preset.pinned_version_id is not None and preset_version_id != preset.pinned_version_id
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Explicit preset_version_id override is not allowed for this preset",
                    )
                if preset.pinned_version_id is not None and preset_version_id != preset.pinned_version_id and cleaned_override_reason is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="version_override_reason is required when overriding pinned_version_id",
                    )
                selected_version = self.require_policy_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset_version_id,
                )
                version_resolution_source = "explicit_version"
            elif preset.pinned_version_id is not None:
                selected_version = self.require_policy_diff_gating_compare_preset_version(
                    organization_id=organization_id,
                    preset_id=preset.id,
                    version_id=preset.pinned_version_id,
                )
                version_resolution_source = "pinned_version"

        if selected_version is not None:
            resolved_snapshot = self._normalize_gating_compare_preset_snapshot(
                organization_id=organization_id,
                snapshot_json=selected_version.snapshot_json,
            )
        else:
            (
                normalized_baseline_report_id,
                normalized_baseline_profile_id,
                normalized_watched,
                normalized_ignored,
                normalized_rules,
                normalized_default_band,
            ) = self._normalize_gating_compare_preset_inputs(
                organization_id=organization_id,
                baseline_gating_report_id=preset.baseline_gating_report_id,
                baseline_gating_profile_id=preset.baseline_gating_profile_id,
                watched_reason_codes_json=preset.watched_reason_codes_json,
                ignored_reason_codes_json=preset.ignored_reason_codes_json,
                interpretation_rules_json=preset.interpretation_rules_json,
                default_interpretation_band=preset.default_interpretation_band,
            )
            resolved_snapshot = {
                "name": preset.name,
                "description": preset.description,
                "baseline_gating_report_id": normalized_baseline_report_id,
                "baseline_gating_profile_id": normalized_baseline_profile_id,
                "watched_reason_codes_json": normalized_watched,
                "ignored_reason_codes_json": normalized_ignored,
                "interpretation_rules_json": normalized_rules,
                "default_interpretation_band": normalized_default_band,
            }

        resolved_base_gating_report_id = base_gating_report_id or resolved_snapshot["baseline_gating_report_id"]
        if resolved_base_gating_report_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="base_gating_report_id is required when preset has no baseline_gating_report_id",
            )
        compare_result = self.compare_policy_diff_gating_reports(
            organization_id=organization_id,
            base_gating_report_id=resolved_base_gating_report_id,
            compare_gating_report_id=compare_gating_report_id,
            title=None,
            persist_compare=persist_compare_report,
            actor_user_id=actor_user_id,
        )
        watched_codes = set(resolved_snapshot["watched_reason_codes_json"])
        ignored_codes = set(resolved_snapshot["ignored_reason_codes_json"])
        rules = resolved_snapshot["interpretation_rules_json"]
        ignore_for_band = bool(rules.get("ignored_reason_codes_do_not_affect_band", False))
        reason_changes = compare_result.get("reason_code_changes")
        reason_change_rows = reason_changes if isinstance(reason_changes, list) else []

        watched_hits_count = 0
        ignored_hits_count = 0
        watched_hits_for_band = 0
        for change in reason_change_rows:
            if not isinstance(change, dict):
                continue
            code = change.get("reason_code")
            if not isinstance(code, str):
                continue
            if code in watched_codes:
                watched_hits_count += 1
                if not (ignore_for_band and code in ignored_codes):
                    watched_hits_for_band += 1
            if code in ignored_codes:
                ignored_hits_count += 1

        matched_rules: list[str] = []
        band_candidates = [resolved_snapshot["default_interpretation_band"]]
        severity_direction = str(compare_result.get("severity_direction") or "unchanged")
        if severity_direction == "increased" and isinstance(rules.get("severity_increase_band"), str):
            band_candidates.append(rules["severity_increase_band"])
            matched_rules.append("severity_increase_band")
        if bool(compare_result.get("review_required_changed")) and isinstance(rules.get("review_required_flip_band"), str):
            band_candidates.append(rules["review_required_flip_band"])
            matched_rules.append("review_required_flip_band")
        if watched_hits_for_band > 0 and isinstance(rules.get("watched_reason_code_band"), str):
            band_candidates.append(rules["watched_reason_code_band"])
            matched_rules.append("watched_reason_code_band")

        interpretation_band = self._max_interpretation_band(*band_candidates)
        review_required = interpretation_band in {"review_required", "critical_review"}

        result = {
            "persisted": persist_report,
            "preset_report_id": None,
            "preset_id": preset.id,
            "preset_version_id": selected_version.id if selected_version is not None else None,
            "preset_version_number": selected_version.version_number if selected_version is not None else None,
            "version_resolution_source": version_resolution_source,
            "pinned_version_id": preset.pinned_version_id,
            "explicit_version_override_used": explicit_override_used,
            "version_override_reason": cleaned_override_reason,
            "preset_snapshot_used": self.json_safe(
                {
                    "name": resolved_snapshot["name"],
                    "description": resolved_snapshot["description"],
                    "baseline_gating_report_id": str(resolved_snapshot["baseline_gating_report_id"])
                    if resolved_snapshot["baseline_gating_report_id"]
                    else None,
                    "baseline_gating_profile_id": str(resolved_snapshot["baseline_gating_profile_id"])
                    if resolved_snapshot["baseline_gating_profile_id"]
                    else None,
                    "watched_reason_codes_json": resolved_snapshot["watched_reason_codes_json"],
                    "ignored_reason_codes_json": resolved_snapshot["ignored_reason_codes_json"],
                    "interpretation_rules_json": resolved_snapshot["interpretation_rules_json"],
                    "default_interpretation_band": resolved_snapshot["default_interpretation_band"],
                }
            ),
            "base_gating_report_id": compare_result["base_gating_report_id"],
            "compare_gating_report_id": compare_result["compare_gating_report_id"],
            "compare_report_id": compare_result.get("compare_report_id"),
            "interpretation_band": interpretation_band,
            "review_required": bool(review_required),
            "watched_reason_codes_hit_count": int(watched_hits_count),
            "ignored_reason_codes_hit_count": int(ignored_hits_count),
            "matched_rules": sorted(set(matched_rules)),
            "compare_result": compare_result,
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_CAVEAT,
        }
        if persist_report:
            row = AISystemGovernancePolicyDiffGatingComparePresetReport(
                organization_id=organization_id,
                preset_id=preset.id,
                base_gating_report_id=compare_result["base_gating_report_id"],
                compare_gating_report_id=compare_result["compare_gating_report_id"],
                compare_report_id=compare_result.get("compare_report_id"),
                preset_version_id=selected_version.id if selected_version is not None else None,
                preset_version_number=selected_version.version_number if selected_version is not None else None,
                preset_snapshot_json=result["preset_snapshot_used"],
                status="generated",
                result_json=self.json_safe({**result, "persisted": True, "preset_report_id": None}),
                interpretation_band=interpretation_band,
                review_required=bool(review_required),
                watched_reason_codes_hit_count=int(watched_hits_count),
                ignored_reason_codes_hit_count=int(ignored_hits_count),
                created_by_user_id=actor_user_id,
            )
            self.db.add(row)
            self.db.flush()
            row.result_json["preset_report_id"] = str(row.id)
            self.db.flush()
            result["persisted"] = True
            result["preset_report_id"] = row.id
        return result

    def list_policy_diff_gating_compare_preset_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        preset_id: uuid.UUID | None,
        interpretation_band: str | None,
        review_required: bool | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePolicyDiffGatingComparePresetReport]:
        stmt = select(AISystemGovernancePolicyDiffGatingComparePresetReport).where(
            AISystemGovernancePolicyDiffGatingComparePresetReport.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetReport.status == status_filter)
        if preset_id is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetReport.preset_id == preset_id)
        if interpretation_band is not None:
            self._validate_interpretation_band(interpretation_band, field_name="interpretation_band")
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetReport.interpretation_band == interpretation_band)
        if review_required is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetReport.review_required == review_required)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePolicyDiffGatingComparePresetReport.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_policy_diff_gating_compare_preset_report(
        self,
        *,
        row: AISystemGovernancePolicyDiffGatingComparePresetReport,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetReport:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def policy_diff_gating_compare_preset_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        preset_counts = dict(
            self.db.execute(
                select(
                    AISystemGovernancePolicyDiffGatingComparePreset.status,
                    func.count(AISystemGovernancePolicyDiffGatingComparePreset.id),
                )
                .where(AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id)
                .group_by(AISystemGovernancePolicyDiffGatingComparePreset.status)
            ).all()
        )
        version_counts = dict(
            self.db.execute(
                select(
                    AISystemGovernancePolicyDiffGatingComparePresetVersion.status,
                    func.count(AISystemGovernancePolicyDiffGatingComparePresetVersion.id),
                )
                .where(AISystemGovernancePolicyDiffGatingComparePresetVersion.organization_id == organization_id)
                .group_by(AISystemGovernancePolicyDiffGatingComparePresetVersion.status)
            ).all()
        )
        report_counts = dict(
            self.db.execute(
                select(
                    AISystemGovernancePolicyDiffGatingComparePresetReport.status,
                    func.count(AISystemGovernancePolicyDiffGatingComparePresetReport.id),
                )
                .where(AISystemGovernancePolicyDiffGatingComparePresetReport.organization_id == organization_id)
                .group_by(AISystemGovernancePolicyDiffGatingComparePresetReport.status)
            ).all()
        )
        review_required_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingComparePresetReport.id)).where(
                    AISystemGovernancePolicyDiffGatingComparePresetReport.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePresetReport.review_required.is_(True),
                )
            ).scalar_one()
        )
        presets_without_active_version = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingComparePreset.id)).where(
                    AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePreset.active_version_id.is_(None),
                )
            ).scalar_one()
        )
        pinned_presets = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingComparePreset.id)).where(
                    AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePreset.pinned_version_id.is_not(None),
                )
            ).scalar_one()
        )
        pinned_required_presets = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingComparePreset.id)).where(
                    AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePreset.version_selection_mode == "pinned_required",
                )
            ).scalar_one()
        )
        pinned_preferred_presets = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingComparePreset.id)).where(
                    AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePreset.version_selection_mode == "pinned_preferred",
                )
            ).scalar_one()
        )
        presets_allowing_explicit_override = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingComparePreset.id)).where(
                    AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePreset.allow_explicit_version_override.is_(True),
                )
            ).scalar_one()
        )
        presets_blocking_explicit_override = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingComparePreset.id)).where(
                    AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePreset.allow_explicit_version_override.is_(False),
                )
            ).scalar_one()
        )
        by_interpretation_band = {
            str(key): int(value)
            for key, value in self.db.execute(
                select(
                    AISystemGovernancePolicyDiffGatingComparePresetReport.interpretation_band,
                    func.count(AISystemGovernancePolicyDiffGatingComparePresetReport.id),
                )
                .where(AISystemGovernancePolicyDiffGatingComparePresetReport.organization_id == organization_id)
                .group_by(AISystemGovernancePolicyDiffGatingComparePresetReport.interpretation_band)
            ).all()
            if key is not None
        }
        latest_preset_report_at = self.db.execute(
            select(func.max(AISystemGovernancePolicyDiffGatingComparePresetReport.created_at)).where(
                AISystemGovernancePolicyDiffGatingComparePresetReport.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "active_presets": int(preset_counts.get("active", 0)),
            "inactive_presets": int(preset_counts.get("inactive", 0)),
            "archived_presets": int(preset_counts.get("archived", 0)),
            "total_preset_reports": int(sum(int(v or 0) for v in report_counts.values())),
            "active_preset_reports": int(report_counts.get("generated", 0)),
            "archived_preset_reports": int(report_counts.get("archived", 0)),
            "review_required_reports": int(review_required_reports),
            "by_interpretation_band": by_interpretation_band,
            "total_preset_versions": int(sum(int(v or 0) for v in version_counts.values())),
            "active_preset_versions": int(version_counts.get("active", 0)),
            "draft_preset_versions": int(version_counts.get("draft", 0)),
            "deprecated_preset_versions": int(version_counts.get("deprecated", 0)),
            "archived_preset_versions": int(version_counts.get("archived", 0)),
            "presets_without_active_version": int(presets_without_active_version),
            "pinned_presets": int(pinned_presets),
            "pinned_required_presets": int(pinned_required_presets),
            "pinned_preferred_presets": int(pinned_preferred_presets),
            "presets_allowing_explicit_override": int(presets_allowing_explicit_override),
            "presets_blocking_explicit_override": int(presets_blocking_explicit_override),
            "latest_preset_report_at": latest_preset_report_at,
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_CAVEAT,
        }

    def create_policy_diff_gating_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        preset_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        scope_json: dict | list | None,
        priority: int,
        reason: str,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetAssignment:
        preset = self.require_policy_diff_gating_compare_preset(organization_id=organization_id, preset_id=preset_id)
        if preset.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived presets cannot be assigned")
        normalized_scope_id, normalized_scope_json = self._validate_policy_assignment_scope(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            scope_json=scope_json,
        )
        if status_value == "active":
            self._assert_no_duplicate_active_preset_assignment(
                organization_id=organization_id,
                scope_type=scope_type,
                scope_id=normalized_scope_id,
                scope_json=normalized_scope_json,
            )
        row = AISystemGovernancePolicyDiffGatingComparePresetAssignment(
            organization_id=organization_id,
            preset_id=preset_id,
            scope_type=scope_type,
            scope_id=normalized_scope_id,
            scope_json=normalized_scope_json,
            priority=priority,
            status=status_value,
            reason=reason,
            assigned_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        self._create_preset_assignment_history(
            organization_id=organization_id,
            assignment_id=row.id,
            event_type="created",
            before_json=None,
            after_json=self._preset_assignment_snapshot(row),
            reason=reason,
            actor_user_id=actor_user_id,
        )
        return row

    def list_policy_diff_gating_compare_preset_assignments(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        scope_type: str | None,
        preset_id: uuid.UUID | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePolicyDiffGatingComparePresetAssignment]:
        stmt = select(AISystemGovernancePolicyDiffGatingComparePresetAssignment).where(
            AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id,
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetAssignment.status == status_filter)
        if scope_type is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetAssignment.scope_type == scope_type)
        if preset_id is not None:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetAssignment.preset_id == preset_id)
        if not include_archived:
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetAssignment.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(
                    AISystemGovernancePolicyDiffGatingComparePresetAssignment.priority.desc(),
                    AISystemGovernancePolicyDiffGatingComparePresetAssignment.updated_at.desc(),
                    AISystemGovernancePolicyDiffGatingComparePresetAssignment.id.asc(),
                )
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def update_policy_diff_gating_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        row: AISystemGovernancePolicyDiffGatingComparePresetAssignment,
        updates: dict[str, Any],
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetAssignment:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived preset assignments cannot be updated")
        before = self._preset_assignment_snapshot(row)
        effective_preset_id = updates.get("preset_id", row.preset_id)
        preset = self.require_policy_diff_gating_compare_preset(organization_id=organization_id, preset_id=effective_preset_id)
        if preset.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived presets cannot be assigned")
        effective_scope_type = updates.get("scope_type", row.scope_type)
        effective_scope_id = updates["scope_id"] if "scope_id" in updates else row.scope_id
        effective_scope_json = updates["scope_json"] if "scope_json" in updates else row.scope_json
        normalized_scope_id, normalized_scope_json = self._validate_policy_assignment_scope(
            organization_id=organization_id,
            scope_type=effective_scope_type,
            scope_id=effective_scope_id,
            scope_json=effective_scope_json,
        )
        effective_status = updates.get("status", row.status)
        if effective_status == "active":
            self._assert_no_duplicate_active_preset_assignment(
                organization_id=organization_id,
                scope_type=effective_scope_type,
                scope_id=normalized_scope_id,
                scope_json=normalized_scope_json,
                exclude_assignment_id=row.id,
            )
        row.preset_id = effective_preset_id
        row.scope_type = effective_scope_type
        row.scope_id = normalized_scope_id
        row.scope_json = normalized_scope_json
        if "priority" in updates:
            row.priority = int(updates["priority"])
        row.status = effective_status
        if "reason" in updates and updates["reason"] is not None:
            row.reason = str(updates["reason"])
        self.db.flush()
        self._create_preset_assignment_history(
            organization_id=organization_id,
            assignment_id=row.id,
            event_type="updated",
            before_json=before,
            after_json=self._preset_assignment_snapshot(row),
            reason=str(updates.get("reason") or row.reason),
            actor_user_id=actor_user_id,
        )
        return row

    def archive_policy_diff_gating_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        row: AISystemGovernancePolicyDiffGatingComparePresetAssignment,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePolicyDiffGatingComparePresetAssignment:
        before = self._preset_assignment_snapshot(row)
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        self._create_preset_assignment_history(
            organization_id=organization_id,
            assignment_id=row.id,
            event_type="archived",
            before_json=before,
            after_json=self._preset_assignment_snapshot(row),
            reason=reason,
            actor_user_id=actor_user_id,
        )
        return row

    def list_policy_diff_gating_compare_preset_assignment_history(
        self,
        *,
        organization_id: uuid.UUID,
        assignment_id: uuid.UUID,
    ) -> list[AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory]:
        return (
            self.db.execute(
                select(AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory)
                .where(
                    AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory.assignment_id == assignment_id,
                )
                .order_by(AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory.created_at.desc())
            )
            .scalars()
            .all()
        )

    def _preset_assignment_candidates_for_scope(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID],
        review_types: list[str],
        rollout_class: str | None,
        status_values: set[str] | None = None,
    ) -> list[AISystemGovernancePolicyDiffGatingComparePresetAssignment]:
        values = status_values or {"active"}
        stmt = select(AISystemGovernancePolicyDiffGatingComparePresetAssignment).where(
            AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id,
            AISystemGovernancePolicyDiffGatingComparePresetAssignment.status.in_(values),
            AISystemGovernancePolicyDiffGatingComparePresetAssignment.scope_type == scope_type,
        )
        if scope_type == "sequence_pack":
            if sequence_pack_id is None:
                return []
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetAssignment.scope_id == sequence_pack_id)
        elif scope_type == "ai_system":
            if not ai_system_ids:
                return []
            stmt = stmt.where(AISystemGovernancePolicyDiffGatingComparePresetAssignment.scope_id.in_(ai_system_ids))
        elif scope_type in {"review_type", "rollout_class", "all_ai_governance"}:
            pass
        else:
            return []
        rows = self.db.execute(
            stmt.order_by(
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.priority.desc(),
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.updated_at.desc(),
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.id.asc(),
            )
        ).scalars().all()
        if scope_type == "review_type":
            return [
                row
                for row in rows
                if self._extract_scope_value(scope_type=scope_type, scope_id=row.scope_id, scope_json=row.scope_json)
                in review_types
            ]
        if scope_type == "rollout_class":
            if not rollout_class:
                return []
            return [
                row
                for row in rows
                if self._extract_scope_value(scope_type=scope_type, scope_id=row.scope_id, scope_json=row.scope_json)
                == rollout_class
            ]
        return rows

    @staticmethod
    def _diagnostic_severity_rank(value: str) -> int:
        if value == "critical":
            return 3
        if value == "warning":
            return 2
        return 1

    @classmethod
    def _max_diagnostic_severity(cls, diagnostics: list[dict[str, Any]]) -> str:
        if not diagnostics:
            return "info"
        best = max(cls._diagnostic_severity_rank(str(item.get("severity") or "info")) for item in diagnostics)
        if best >= 3:
            return "critical"
        if best >= 2:
            return "warning"
        return "info"

    def _validate_preset_assignment_context_inputs(
        self,
        *,
        organization_id: uuid.UUID,
        explicit_preset_id: uuid.UUID | None,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID] | None,
        review_types: list[str] | None,
    ) -> tuple[list[uuid.UUID], list[str]]:
        ai_ids = sorted({item for item in (ai_system_ids or [])}, key=lambda item: str(item))
        review_type_values = sorted({item for item in (review_types or [])})
        if explicit_preset_id is not None:
            self.require_policy_diff_gating_compare_preset(
                organization_id=organization_id,
                preset_id=explicit_preset_id,
            )
        if sequence_pack_id is not None:
            self.require_pack(organization_id=organization_id, pack_id=sequence_pack_id)
        if ai_ids:
            found = self.db.execute(
                select(AISystem.id).where(
                    AISystem.organization_id == organization_id,
                    AISystem.id.in_(ai_ids),
                )
            ).scalars().all()
            if len(found) != len(ai_ids):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more ai_system_ids not found")
        if any(item not in REVIEW_TYPES for item in review_type_values):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="review_types contains invalid review type")
        return ai_ids, review_type_values

    def _resolve_preset_assignment_with_diagnostics(
        self,
        *,
        organization_id: uuid.UUID,
        explicit_preset_id: uuid.UUID | None,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID],
        review_types: list[str],
        rollout_class: str | None,
        include_inactive_assignments: bool,
        include_archived_assignments: bool,
        include_preset_version_diagnostics: bool,
    ) -> dict[str, Any]:
        precedence_trace: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        normalized_rollout_class = rollout_class.strip() if isinstance(rollout_class, str) and rollout_class.strip() else None

        def _append_diag(code: str, severity: str, details: dict[str, Any] | None = None) -> None:
            entry = {"code": code, "severity": severity}
            if details:
                entry["details"] = details
            diagnostics.append(entry)

        if explicit_preset_id is not None:
            preset = self.require_policy_diff_gating_compare_preset(
                organization_id=organization_id,
                preset_id=explicit_preset_id,
            )
            _append_diag("EXPLICIT_PRESET_USED", "info")
            if preset.status == "inactive":
                _append_diag("ASSIGNMENT_TARGET_PRESET_INACTIVE", "critical", {"preset_id": str(preset.id)})
            elif preset.status == "archived":
                _append_diag("ASSIGNMENT_TARGET_PRESET_ARCHIVED", "critical", {"preset_id": str(preset.id)})
            else:
                _append_diag("RESOLVED", "info")
            if include_preset_version_diagnostics:
                if preset.active_version_id is None:
                    _append_diag(
                        "ASSIGNMENT_TARGET_PRESET_MISSING_ACTIVE_VERSION",
                        "warning",
                        {"preset_id": str(preset.id)},
                    )
                if preset.version_selection_mode == "pinned_required" and preset.pinned_version_id is None:
                    _append_diag("PINNED_REQUIRED_WITHOUT_PIN", "critical", {"preset_id": str(preset.id)})
                if preset.pinned_version_id is not None:
                    pinned = self.db.execute(
                        select(AISystemGovernancePolicyDiffGatingComparePresetVersion).where(
                            AISystemGovernancePolicyDiffGatingComparePresetVersion.organization_id == organization_id,
                            AISystemGovernancePolicyDiffGatingComparePresetVersion.id == preset.pinned_version_id,
                            AISystemGovernancePolicyDiffGatingComparePresetVersion.preset_id == preset.id,
                        )
                    ).scalar_one_or_none()
                    if pinned is None:
                        _append_diag("PINNED_VERSION_MISSING", "critical", {"preset_id": str(preset.id)})
                    elif pinned.status == "archived":
                        _append_diag("PINNED_VERSION_ARCHIVED", "critical", {"preset_id": str(preset.id)})
            return {
                "resolution_source": "explicit_request",
                "resolved_preset_id": preset.id,
                "resolved_assignment_id": None,
                "precedence_trace": precedence_trace,
                "diagnostics": diagnostics,
                "severity": self._max_diagnostic_severity(diagnostics),
                "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
            }

        selected_scope_type: str | None = None
        selected_source: str = "none"
        selected_assignment: AISystemGovernancePolicyDiffGatingComparePresetAssignment | None = None
        selected_preset: AISystemGovernancePolicyDiffGatingComparePreset | None = None
        scopes_with_active_candidates = 0

        for scope_type, source in POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_SCOPE_PRECEDENCE:
            active_candidates = self._preset_assignment_candidates_for_scope(
                organization_id=organization_id,
                scope_type=scope_type,
                sequence_pack_id=sequence_pack_id,
                ai_system_ids=ai_system_ids,
                review_types=review_types,
                rollout_class=normalized_rollout_class,
                status_values={"active"},
            )
            inactive_candidates: list[AISystemGovernancePolicyDiffGatingComparePresetAssignment] = []
            archived_candidates: list[AISystemGovernancePolicyDiffGatingComparePresetAssignment] = []
            if include_inactive_assignments:
                inactive_candidates = self._preset_assignment_candidates_for_scope(
                    organization_id=organization_id,
                    scope_type=scope_type,
                    sequence_pack_id=sequence_pack_id,
                    ai_system_ids=ai_system_ids,
                    review_types=review_types,
                    rollout_class=normalized_rollout_class,
                    status_values={"inactive"},
                )
            if include_archived_assignments:
                archived_candidates = self._preset_assignment_candidates_for_scope(
                    organization_id=organization_id,
                    scope_type=scope_type,
                    sequence_pack_id=sequence_pack_id,
                    ai_system_ids=ai_system_ids,
                    review_types=review_types,
                    rollout_class=normalized_rollout_class,
                    status_values={"archived"},
                )
            trace_item: dict[str, Any] = {
                "scope_type": scope_type,
                "source": source,
                "candidate_assignment_ids": [str(item.id) for item in active_candidates],
                "matched": bool(active_candidates),
            }
            if include_inactive_assignments:
                trace_item["inactive_assignment_ids"] = [str(item.id) for item in inactive_candidates]
            if include_archived_assignments:
                trace_item["archived_assignment_ids"] = [str(item.id) for item in archived_candidates]
            precedence_trace.append(trace_item)
            if active_candidates:
                scopes_with_active_candidates += 1
                if len(active_candidates) > 1:
                    _append_diag(
                        "CONFLICTING_ASSIGNMENTS_SAME_SCOPE",
                        "warning",
                        {"scope_type": scope_type, "candidate_assignment_ids": [str(item.id) for item in active_candidates]},
                    )
            if selected_assignment is not None or not active_candidates:
                continue
            selected_assignment = active_candidates[0]
            selected_scope_type = scope_type
            selected_source = source
            trace_item["selected_assignment_id"] = str(selected_assignment.id)
            selected_preset = self.db.execute(
                select(AISystemGovernancePolicyDiffGatingComparePreset).where(
                    AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePreset.id == selected_assignment.preset_id,
                )
            ).scalar_one_or_none()
            if selected_preset is not None:
                trace_item["selected_preset_id"] = str(selected_preset.id)

        if scopes_with_active_candidates > 1:
            _append_diag("MULTIPLE_ASSIGNMENTS_DIFFERENT_SCOPE", "warning", {"matched_scope_count": scopes_with_active_candidates})

        if selected_assignment is None:
            _append_diag("NO_ASSIGNMENT_FOUND", "critical")
            return {
                "resolution_source": "none",
                "resolved_preset_id": None,
                "resolved_assignment_id": None,
                "precedence_trace": precedence_trace,
                "diagnostics": diagnostics,
                "severity": self._max_diagnostic_severity(diagnostics),
                "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
            }

        if selected_scope_type is not None and selected_scope_type != "sequence_pack":
            _append_diag("CROSS_SCOPE_FALLBACK_USED", "info", {"selected_scope_type": selected_scope_type})

        if selected_preset is None:
            _append_diag(
                "ASSIGNMENT_TARGET_PRESET_ARCHIVED",
                "critical",
                {"assignment_id": str(selected_assignment.id), "preset_id": str(selected_assignment.preset_id)},
            )
            return {
                "resolution_source": selected_source,
                "resolved_preset_id": selected_assignment.preset_id,
                "resolved_assignment_id": selected_assignment.id,
                "precedence_trace": precedence_trace,
                "diagnostics": diagnostics,
                "severity": self._max_diagnostic_severity(diagnostics),
                "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
            }

        if selected_preset.status == "inactive":
            _append_diag("ASSIGNMENT_TARGET_PRESET_INACTIVE", "critical", {"preset_id": str(selected_preset.id)})
        elif selected_preset.status == "archived":
            _append_diag("ASSIGNMENT_TARGET_PRESET_ARCHIVED", "critical", {"preset_id": str(selected_preset.id)})
        else:
            _append_diag("RESOLVED", "info")

        if include_preset_version_diagnostics:
            if selected_preset.active_version_id is None:
                _append_diag(
                    "ASSIGNMENT_TARGET_PRESET_MISSING_ACTIVE_VERSION",
                    "warning",
                    {"preset_id": str(selected_preset.id)},
                )
            if selected_preset.version_selection_mode == "pinned_required" and selected_preset.pinned_version_id is None:
                _append_diag("PINNED_REQUIRED_WITHOUT_PIN", "critical", {"preset_id": str(selected_preset.id)})
            if selected_preset.pinned_version_id is not None:
                pinned = self.db.execute(
                    select(AISystemGovernancePolicyDiffGatingComparePresetVersion).where(
                        AISystemGovernancePolicyDiffGatingComparePresetVersion.organization_id == organization_id,
                        AISystemGovernancePolicyDiffGatingComparePresetVersion.id == selected_preset.pinned_version_id,
                        AISystemGovernancePolicyDiffGatingComparePresetVersion.preset_id == selected_preset.id,
                    )
                ).scalar_one_or_none()
                if pinned is None:
                    _append_diag("PINNED_VERSION_MISSING", "critical", {"preset_id": str(selected_preset.id)})
                elif pinned.status == "archived":
                    _append_diag("PINNED_VERSION_ARCHIVED", "critical", {"preset_id": str(selected_preset.id)})

        return {
            "resolution_source": selected_source,
            "resolved_preset_id": selected_preset.id,
            "resolved_assignment_id": selected_assignment.id,
            "precedence_trace": precedence_trace,
            "diagnostics": diagnostics,
            "severity": self._max_diagnostic_severity(diagnostics),
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
        }

    def resolve_policy_diff_gating_compare_preset_assignment(
        self,
        *,
        organization_id: uuid.UUID,
        explicit_preset_id: uuid.UUID | None,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID] | None,
        review_types: list[str] | None,
        rollout_class: str | None,
    ) -> dict[str, Any]:
        ai_ids = sorted({item for item in (ai_system_ids or [])}, key=lambda item: str(item))
        review_type_values = sorted({item for item in (review_types or [])})
        if sequence_pack_id is not None:
            self.require_pack(organization_id=organization_id, pack_id=sequence_pack_id)
        if ai_ids:
            found = self.db.execute(
                select(AISystem.id).where(
                    AISystem.organization_id == organization_id,
                    AISystem.id.in_(ai_ids),
                )
            ).scalars().all()
            if len(found) != len(ai_ids):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more ai_system_ids not found")
        if any(item not in REVIEW_TYPES for item in review_type_values):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="review_types contains invalid review type")

        precedence_trace: list[dict[str, Any]] = []
        if explicit_preset_id is not None:
            preset = self.require_policy_diff_gating_compare_preset(
                organization_id=organization_id,
                preset_id=explicit_preset_id,
            )
            if preset.status != "active":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Resolved preset must be active",
                )
            precedence_trace.append(
                {
                    "scope_type": "explicit_request",
                    "matched": True,
                    "preset_id": str(preset.id),
                }
            )
            return {
                "resolved_preset_id": preset.id,
                "resolution_source": "explicit_request",
                "assignment_id": None,
                "precedence_trace": precedence_trace,
                "pinned_version_id": preset.pinned_version_id,
                "version_selection_mode": preset.version_selection_mode,
                "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_CAVEAT,
            }

        for scope_type, source in POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_SCOPE_PRECEDENCE:
            candidates = self._preset_assignment_candidates_for_scope(
                organization_id=organization_id,
                scope_type=scope_type,
                sequence_pack_id=sequence_pack_id,
                ai_system_ids=ai_ids,
                review_types=review_type_values,
                rollout_class=rollout_class.strip() if isinstance(rollout_class, str) else None,
            )
            precedence_trace.append(
                {
                    "scope_type": scope_type,
                    "source": source,
                    "candidate_assignment_ids": [str(item.id) for item in candidates],
                    "matched": bool(candidates),
                }
            )
            if not candidates:
                continue
            selected = candidates[0]
            preset = self.require_policy_diff_gating_compare_preset(
                organization_id=organization_id,
                preset_id=selected.preset_id,
            )
            if preset.status != "active":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Resolved mapped preset must be active",
                )
            precedence_trace[-1]["selected_assignment_id"] = str(selected.id)
            precedence_trace[-1]["selected_preset_id"] = str(preset.id)
            return {
                "resolved_preset_id": preset.id,
                "resolution_source": source,
                "assignment_id": selected.id,
                "precedence_trace": precedence_trace,
                "pinned_version_id": preset.pinned_version_id,
                "version_selection_mode": preset.version_selection_mode,
                "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_CAVEAT,
            }

        return {
            "resolved_preset_id": None,
            "resolution_source": "none",
            "assignment_id": None,
            "precedence_trace": precedence_trace,
            "pinned_version_id": None,
            "version_selection_mode": None,
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_CAVEAT,
        }

    def evaluate_policy_diff_gating_compare_preset_default(
        self,
        *,
        organization_id: uuid.UUID,
        explicit_preset_id: uuid.UUID | None,
        base_gating_report_id: uuid.UUID | None,
        compare_gating_report_id: uuid.UUID,
        sequence_pack_id: uuid.UUID | None,
        ai_system_ids: list[uuid.UUID] | None,
        review_types: list[str] | None,
        rollout_class: str | None,
        preset_version_id: uuid.UUID | None,
        version_override_reason: str | None,
        persist_report: bool,
        persist_compare_report: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        preset_resolution = self.resolve_policy_diff_gating_compare_preset_assignment(
            organization_id=organization_id,
            explicit_preset_id=explicit_preset_id,
            sequence_pack_id=sequence_pack_id,
            ai_system_ids=ai_system_ids,
            review_types=review_types,
            rollout_class=rollout_class,
        )
        resolved_preset_id = preset_resolution["resolved_preset_id"]
        if resolved_preset_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No preset could be resolved. Provide explicit_preset_id or configure preset assignments.",
            )
        result = self.evaluate_policy_diff_gating_compare_preset(
            organization_id=organization_id,
            preset_id=resolved_preset_id,
            preset_version_id=preset_version_id,
            version_override_reason=version_override_reason,
            base_gating_report_id=base_gating_report_id,
            compare_gating_report_id=compare_gating_report_id,
            persist_report=persist_report,
            persist_compare_report=persist_compare_report,
            actor_user_id=actor_user_id,
        )
        merged = {
            **result,
            "preset_resolution": {
                "resolved_preset_id": preset_resolution["resolved_preset_id"],
                "resolution_source": preset_resolution["resolution_source"],
                "assignment_id": preset_resolution["assignment_id"],
                "precedence_trace": preset_resolution["precedence_trace"],
                "pinned_version_id": preset_resolution["pinned_version_id"],
                "version_selection_mode": preset_resolution["version_selection_mode"],
                "caveat": preset_resolution["caveat"],
            },
        }
        if persist_report and result.get("preset_report_id") is not None:
            report = self.require_policy_diff_gating_compare_preset_report(
                organization_id=organization_id,
                preset_report_id=result["preset_report_id"],
            )
            report.result_json = self.json_safe(merged)
            self.db.flush()
        return merged

    def policy_diff_gating_compare_preset_assignment_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        active_assignments = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id)).where(
                    AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePresetAssignment.status == "active",
                )
            ).scalar_one()
        )
        inactive_assignments = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id)).where(
                    AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePresetAssignment.status == "inactive",
                )
            ).scalar_one()
        )
        archived_assignments = int(
            self.db.execute(
                select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id)).where(
                    AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePresetAssignment.status == "archived",
                )
            ).scalar_one()
        )
        by_scope_rows = self.db.execute(
            select(
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.scope_type,
                func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id),
            )
            .where(AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id)
            .group_by(AISystemGovernancePolicyDiffGatingComparePresetAssignment.scope_type)
        ).all()
        assignment_rows = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingComparePresetAssignment).where(
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id,
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.status != "archived",
            )
        ).scalars().all()
        assignments_to_archived_presets = 0
        assignments_to_inactive_presets = 0
        for row in assignment_rows:
            preset = self.require_policy_diff_gating_compare_preset(
                organization_id=organization_id,
                preset_id=row.preset_id,
            )
            if preset.status == "archived":
                assignments_to_archived_presets += 1
            elif preset.status == "inactive":
                assignments_to_inactive_presets += 1
        highest_priority_raw = self.db.execute(
            select(func.max(AISystemGovernancePolicyDiffGatingComparePresetAssignment.priority)).where(
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id,
            )
        ).scalar_one()
        return {
            "active_assignments": active_assignments,
            "inactive_assignments": inactive_assignments,
            "archived_assignments": archived_assignments,
            "by_scope_type": {str(key): int(count) for key, count in by_scope_rows if key is not None},
            "assignments_to_archived_presets": int(assignments_to_archived_presets),
            "assignments_to_inactive_presets": int(assignments_to_inactive_presets),
            "highest_priority": int(highest_priority_raw or 0),
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_CAVEAT,
        }

    def policy_diff_gating_compare_preset_assignment_coverage_diagnostics(
        self,
        *,
        organization_id: uuid.UUID,
        contexts: list[dict[str, Any]],
        title: str | None,
        description: str | None,
        persist_report: bool,
        include_inactive_assignments: bool,
        include_archived_assignments: bool,
        include_preset_version_diagnostics: bool,
        actor_user_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        context_results: list[dict[str, Any]] = []
        aggregate_counts: dict[str, int] = {}
        for idx, item in enumerate(contexts):
            explicit_preset_id = item.get("explicit_preset_id")
            sequence_pack_id = item.get("sequence_pack_id")
            ai_system_ids = item.get("ai_system_ids")
            review_types = item.get("review_types")
            rollout_class = item.get("rollout_class")
            ai_ids, review_type_values = self._validate_preset_assignment_context_inputs(
                organization_id=organization_id,
                explicit_preset_id=explicit_preset_id,
                sequence_pack_id=sequence_pack_id,
                ai_system_ids=ai_system_ids,
                review_types=review_types,
            )
            resolved = self._resolve_preset_assignment_with_diagnostics(
                organization_id=organization_id,
                explicit_preset_id=explicit_preset_id,
                sequence_pack_id=sequence_pack_id,
                ai_system_ids=ai_ids,
                review_types=review_type_values,
                rollout_class=rollout_class,
                include_inactive_assignments=include_inactive_assignments,
                include_archived_assignments=include_archived_assignments,
                include_preset_version_diagnostics=include_preset_version_diagnostics,
            )
            for diag in resolved["diagnostics"]:
                code = str(diag.get("code"))
                aggregate_counts[code] = int(aggregate_counts.get(code, 0) + 1)
            context_results.append(
                {
                    "context_key": item.get("context_key"),
                    "context_index": idx,
                    "resolution_source": resolved["resolution_source"],
                    "resolved_preset_id": resolved["resolved_preset_id"],
                    "resolved_assignment_id": resolved["resolved_assignment_id"],
                    "precedence_trace": resolved["precedence_trace"],
                    "diagnostics": resolved["diagnostics"],
                    "severity": resolved["severity"],
                    "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
                }
            )
        unresolved_count = sum(1 for item in context_results if item["resolved_preset_id"] is None)
        warning_count = sum(1 for item in context_results if item["severity"] == "warning")
        critical_count = sum(1 for item in context_results if item["severity"] == "critical")
        payload: dict[str, Any] = {
            "persisted": persist_report,
            "report_id": None,
            "context_count": len(context_results),
            "resolved_contexts_count": len(context_results) - unresolved_count,
            "unresolved_contexts_count": unresolved_count,
            "warning_contexts_count": warning_count,
            "critical_contexts_count": critical_count,
            "contexts": context_results,
            "aggregate_diagnostics": {key: int(value) for key, value in sorted(aggregate_counts.items())},
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_REPORTS_CAVEAT,
        }
        if persist_report:
            row = AISystemGovernancePresetAssignmentDiagnosticReport(
                organization_id=organization_id,
                title=title.strip() if isinstance(title, str) and title.strip() else None,
                description=description.strip() if isinstance(description, str) and description.strip() else None,
                status="generated",
                input_contexts_json=self.json_safe(contexts),
                result_json=self.json_safe({**payload, "persisted": True, "report_id": None}),
                context_count=int(payload["context_count"]),
                resolved_contexts_count=int(payload["resolved_contexts_count"]),
                unresolved_contexts_count=int(payload["unresolved_contexts_count"]),
                warning_contexts_count=int(payload["warning_contexts_count"]),
                critical_contexts_count=int(payload["critical_contexts_count"]),
                aggregate_diagnostics_json=self.json_safe(payload["aggregate_diagnostics"]),
                created_by_user_id=actor_user_id,
            )
            self.db.add(row)
            self.db.flush()
            row.result_json["report_id"] = str(row.id)
            self.db.flush()
            payload["report_id"] = row.id
        return payload

    def policy_diff_gating_compare_preset_assignment_health_diagnostics(
        self,
        *,
        organization_id: uuid.UUID,
    ) -> dict[str, Any]:
        rows = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingComparePresetAssignment).where(
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id
            )
        ).scalars().all()
        active = [row for row in rows if row.status == "active"]
        inactive = [row for row in rows if row.status == "inactive"]
        archived = [row for row in rows if row.status == "archived"]
        preset_ids = sorted({row.preset_id for row in rows}, key=lambda item: str(item))
        preset_map = {
            row.id: row
            for row in self.db.execute(
                select(AISystemGovernancePolicyDiffGatingComparePreset).where(
                    AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id,
                    AISystemGovernancePolicyDiffGatingComparePreset.id.in_(preset_ids),
                )
            )
            .scalars()
            .all()
        } if preset_ids else {}
        assignments_to_inactive_presets = 0
        assignments_to_archived_presets = 0
        assignments_with_missing_preset = 0
        assignments_with_pinned_required_without_pin = 0
        for row in rows:
            preset = preset_map.get(row.preset_id)
            if preset is None:
                assignments_with_missing_preset += 1
                continue
            if preset.status == "inactive":
                assignments_to_inactive_presets += 1
            elif preset.status == "archived":
                assignments_to_archived_presets += 1
            if preset.version_selection_mode == "pinned_required" and preset.pinned_version_id is None:
                assignments_with_pinned_required_without_pin += 1
        exact_scope_groups: dict[tuple[str, str | None], int] = {}
        for row in active:
            scope_value = self._extract_scope_value(scope_type=row.scope_type, scope_id=row.scope_id, scope_json=row.scope_json)
            key = (row.scope_type, scope_value)
            exact_scope_groups[key] = int(exact_scope_groups.get(key, 0) + 1)
        duplicate_active_exact_scope_groups = sum(1 for count in exact_scope_groups.values() if count > 1)
        scope_type_counts: dict[str, int] = {}
        for row in active:
            scope_type_counts[row.scope_type] = int(scope_type_counts.get(row.scope_type, 0) + 1)
        same_scope_conflict_groups = sum(1 for count in scope_type_counts.values() if count > 1)
        return {
            "active_assignments": len(active),
            "inactive_assignments": len(inactive),
            "archived_assignments": len(archived),
            "assignments_to_inactive_presets": int(assignments_to_inactive_presets),
            "assignments_to_archived_presets": int(assignments_to_archived_presets),
            "assignments_with_missing_preset": int(assignments_with_missing_preset),
            "assignments_with_pinned_required_without_pin": int(assignments_with_pinned_required_without_pin),
            "duplicate_active_exact_scope_groups": int(duplicate_active_exact_scope_groups),
            "same_scope_conflict_groups": int(same_scope_conflict_groups),
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
        }

    def policy_diff_gating_compare_preset_assignment_coverage_summary(
        self,
        *,
        organization_id: uuid.UUID,
    ) -> dict[str, Any]:
        rows = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingComparePresetAssignment).where(
                AISystemGovernancePolicyDiffGatingComparePresetAssignment.organization_id == organization_id
            )
        ).scalars().all()
        by_scope: dict[str, int] = {}
        for row in rows:
            by_scope[row.scope_type] = int(by_scope.get(row.scope_type, 0) + 1)
        active_rows = [row for row in rows if row.status == "active"]
        inactive_rows = [row for row in rows if row.status == "inactive"]
        archived_rows = [row for row in rows if row.status == "archived"]
        preset_ids = sorted({row.preset_id for row in rows}, key=lambda item: str(item))
        preset_rows = self.db.execute(
            select(AISystemGovernancePolicyDiffGatingComparePreset).where(
                AISystemGovernancePolicyDiffGatingComparePreset.organization_id == organization_id,
            )
        ).scalars().all()
        preset_map = {row.id: row for row in preset_rows}
        assignments_to_archived_presets = 0
        assignments_to_inactive_presets = 0
        assignments_with_missing_preset = 0
        assignments_with_pinned_required_without_pin = 0
        for row in rows:
            preset = preset_map.get(row.preset_id)
            if preset is None:
                assignments_with_missing_preset += 1
                continue
            if preset.status == "archived":
                assignments_to_archived_presets += 1
            elif preset.status == "inactive":
                assignments_to_inactive_presets += 1
            if preset.version_selection_mode == "pinned_required" and preset.pinned_version_id is None:
                assignments_with_pinned_required_without_pin += 1
        total_problem_assignments = (
            assignments_to_archived_presets
            + assignments_to_inactive_presets
            + assignments_with_missing_preset
            + assignments_with_pinned_required_without_pin
        )
        non_archived_assignment_preset_ids = {
            row.preset_id for row in rows if row.status in {"active", "inactive"}
        }
        active_presets_without_assignments = sum(
            1 for preset in preset_rows if preset.status == "active" and preset.id not in non_archived_assignment_preset_ids
        )
        pinned_presets_with_assignment_count = sum(
            1
            for preset in preset_rows
            if preset.pinned_version_id is not None and preset.id in non_archived_assignment_preset_ids
        )
        return {
            "total_active_assignments": len(active_rows),
            "total_inactive_assignments": len(inactive_rows),
            "total_archived_assignments": len(archived_rows),
            "total_problem_assignments": int(total_problem_assignments),
            "assignments_by_scope_type": {str(key): int(value) for key, value in sorted(by_scope.items())},
            "presets_referenced_by_assignments": len(preset_ids),
            "active_presets_without_assignments": int(active_presets_without_assignments),
            "pinned_presets_with_assignment_count": int(pinned_presets_with_assignment_count),
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTICS_CAVEAT,
        }

    @staticmethod
    def _preset_assignment_diagnostic_report_contexts(
        report: AISystemGovernancePresetAssignmentDiagnosticReport,
    ) -> list[dict[str, Any]]:
        result_json = report.result_json if isinstance(report.result_json, dict) else {}
        contexts = result_json.get("contexts")
        if not isinstance(contexts, list):
            return []
        return [item for item in contexts if isinstance(item, dict)]

    def list_preset_assignment_diagnostic_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePresetAssignmentDiagnosticReport]:
        stmt = select(AISystemGovernancePresetAssignmentDiagnosticReport).where(
            AISystemGovernancePresetAssignmentDiagnosticReport.organization_id == organization_id,
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePresetAssignmentDiagnosticReport.status == status_filter)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePresetAssignmentDiagnosticReport.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_preset_assignment_diagnostic_report(
        self,
        *,
        row: AISystemGovernancePresetAssignmentDiagnosticReport,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePresetAssignmentDiagnosticReport:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def diff_preset_assignment_diagnostic_reports(
        self,
        *,
        organization_id: uuid.UUID,
        base_report_id: uuid.UUID,
        compare_report_id: uuid.UUID,
        title: str | None,
        persist_diff: bool,
        context_match_strategy: str,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        if context_match_strategy not in {"context_key_then_index", "context_key_only"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid context_match_strategy")

        base_report = self.require_preset_assignment_diagnostic_report(
            organization_id=organization_id,
            report_id=base_report_id,
        )
        compare_report = self.require_preset_assignment_diagnostic_report(
            organization_id=organization_id,
            report_id=compare_report_id,
        )
        base_contexts = self._preset_assignment_diagnostic_report_contexts(base_report)
        compare_contexts = self._preset_assignment_diagnostic_report_contexts(compare_report)
        pairs, base_unmatched, compare_unmatched = self._match_simulation_context_pairs(
            base_contexts=base_contexts,
            compare_contexts=compare_contexts,
            context_match_strategy=context_match_strategy,
        )

        context_diffs: list[dict[str, Any]] = []
        changed_count = 0
        unchanged_count = 0
        diagnostic_code_changes_count = 0

        for b_idx, c_idx in pairs:
            base_ctx = base_contexts[b_idx]
            compare_ctx = compare_contexts[c_idx]
            base_codes = sorted(
                {
                    str(item.get("code"))
                    for item in (base_ctx.get("diagnostics") or [])
                    if isinstance(item, dict) and item.get("code") is not None
                }
            )
            compare_codes = sorted(
                {
                    str(item.get("code"))
                    for item in (compare_ctx.get("diagnostics") or [])
                    if isinstance(item, dict) and item.get("code") is not None
                }
            )
            field_changes: list[dict[str, Any]] = []

            def add_field_change(field_path: str, before_value: Any, after_value: Any) -> None:
                if before_value == after_value:
                    return
                field_changes.append(
                    {
                        "field_path": field_path,
                        "before_value": before_value,
                        "after_value": after_value,
                    }
                )

            add_field_change("resolution_source", base_ctx.get("resolution_source"), compare_ctx.get("resolution_source"))
            add_field_change("resolved_preset_id", base_ctx.get("resolved_preset_id"), compare_ctx.get("resolved_preset_id"))
            add_field_change("severity", base_ctx.get("severity"), compare_ctx.get("severity"))
            add_field_change("diagnostic_codes", base_codes, compare_codes)
            add_field_change("precedence_trace", base_ctx.get("precedence_trace"), compare_ctx.get("precedence_trace"))

            if base_codes != compare_codes:
                diagnostic_code_changes_count += 1

            changed = bool(field_changes)
            if changed:
                changed_count += 1
            else:
                unchanged_count += 1

            context_diffs.append(
                {
                    "match_type": "matched",
                    "base_index": b_idx,
                    "compare_index": c_idx,
                    "context_key": self._context_key(compare_ctx) or self._context_key(base_ctx) or f"index_{b_idx}",
                    "changed": changed,
                    "base_context": base_ctx,
                    "compare_context": compare_ctx,
                    "field_changes": field_changes,
                }
            )

        for idx in base_unmatched:
            context_diffs.append(
                {
                    "match_type": "removed",
                    "base_index": idx,
                    "compare_index": None,
                    "context_key": self._context_key(base_contexts[idx]) or f"index_{idx}",
                    "changed": True,
                    "base_context": base_contexts[idx],
                    "compare_context": None,
                    "field_changes": [],
                }
            )
        for idx in compare_unmatched:
            context_diffs.append(
                {
                    "match_type": "added",
                    "base_index": None,
                    "compare_index": idx,
                    "context_key": self._context_key(compare_contexts[idx]) or f"index_{idx}",
                    "changed": True,
                    "base_context": None,
                    "compare_context": compare_contexts[idx],
                    "field_changes": [],
                }
            )
        context_diffs.sort(key=lambda item: (item["context_key"], str(item.get("match_type")), int(item.get("base_index") or 0)))

        resolved_delta = int(compare_report.resolved_contexts_count - base_report.resolved_contexts_count)
        unresolved_delta = int(compare_report.unresolved_contexts_count - base_report.unresolved_contexts_count)
        warning_delta = int(compare_report.warning_contexts_count - base_report.warning_contexts_count)
        critical_delta = int(compare_report.critical_contexts_count - base_report.critical_contexts_count)
        diff_payload: dict[str, Any] = {
            "persisted": persist_diff,
            "diff_report_id": None,
            "base_report_id": base_report.id,
            "compare_report_id": compare_report.id,
            "context_match_strategy": context_match_strategy,
            "added_contexts_count": len(compare_unmatched),
            "removed_contexts_count": len(base_unmatched),
            "changed_contexts_count": changed_count,
            "unchanged_contexts_count": unchanged_count,
            "resolved_delta": resolved_delta,
            "unresolved_delta": unresolved_delta,
            "warning_delta": warning_delta,
            "critical_delta": critical_delta,
            "diagnostic_code_changes_count": int(diagnostic_code_changes_count),
            "context_diffs": context_diffs,
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_REPORTS_CAVEAT,
        }
        if persist_diff:
            row = AISystemGovernancePresetAssignmentDiagnosticDiffReport(
                organization_id=organization_id,
                base_report_id=base_report.id,
                compare_report_id=compare_report.id,
                title=title.strip() if isinstance(title, str) and title.strip() else None,
                status="generated",
                diff_json=self.json_safe({**diff_payload, "persisted": True, "diff_report_id": None}),
                added_contexts_count=int(diff_payload["added_contexts_count"]),
                removed_contexts_count=int(diff_payload["removed_contexts_count"]),
                changed_contexts_count=int(diff_payload["changed_contexts_count"]),
                unchanged_contexts_count=int(diff_payload["unchanged_contexts_count"]),
                resolved_delta=int(diff_payload["resolved_delta"]),
                unresolved_delta=int(diff_payload["unresolved_delta"]),
                warning_delta=int(diff_payload["warning_delta"]),
                critical_delta=int(diff_payload["critical_delta"]),
                diagnostic_code_changes_count=int(diff_payload["diagnostic_code_changes_count"]),
                created_by_user_id=actor_user_id,
            )
            self.db.add(row)
            self.db.flush()
            row.diff_json["diff_report_id"] = str(row.id)
            self.db.flush()
            diff_payload["diff_report_id"] = row.id
        return diff_payload

    def list_preset_assignment_diagnostic_diff_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        base_report_id: uuid.UUID | None,
        compare_report_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePresetAssignmentDiagnosticDiffReport]:
        stmt = select(AISystemGovernancePresetAssignmentDiagnosticDiffReport).where(
            AISystemGovernancePresetAssignmentDiagnosticDiffReport.organization_id == organization_id,
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePresetAssignmentDiagnosticDiffReport.status == status_filter)
        if base_report_id is not None:
            stmt = stmt.where(AISystemGovernancePresetAssignmentDiagnosticDiffReport.base_report_id == base_report_id)
        if compare_report_id is not None:
            stmt = stmt.where(AISystemGovernancePresetAssignmentDiagnosticDiffReport.compare_report_id == compare_report_id)
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePresetAssignmentDiagnosticDiffReport.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_preset_assignment_diagnostic_diff_report(
        self,
        *,
        row: AISystemGovernancePresetAssignmentDiagnosticDiffReport,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePresetAssignmentDiagnosticDiffReport:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def preset_assignment_diagnostic_report_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        total_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticReport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticReport.organization_id == organization_id,
                )
            ).scalar_one()
        )
        active_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticReport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticReport.organization_id == organization_id,
                    AISystemGovernancePresetAssignmentDiagnosticReport.status == "generated",
                )
            ).scalar_one()
        )
        archived_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticReport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticReport.organization_id == organization_id,
                    AISystemGovernancePresetAssignmentDiagnosticReport.status == "archived",
                )
            ).scalar_one()
        )
        total_diff_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticDiffReport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticDiffReport.organization_id == organization_id,
                )
            ).scalar_one()
        )
        active_diff_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticDiffReport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticDiffReport.organization_id == organization_id,
                    AISystemGovernancePresetAssignmentDiagnosticDiffReport.status == "generated",
                )
            ).scalar_one()
        )
        archived_diff_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticDiffReport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticDiffReport.organization_id == organization_id,
                    AISystemGovernancePresetAssignmentDiagnosticDiffReport.status == "archived",
                )
            ).scalar_one()
        )
        report_totals = self.db.execute(
            select(
                func.coalesce(func.sum(AISystemGovernancePresetAssignmentDiagnosticReport.unresolved_contexts_count), 0),
                func.coalesce(func.sum(AISystemGovernancePresetAssignmentDiagnosticReport.warning_contexts_count), 0),
                func.coalesce(func.sum(AISystemGovernancePresetAssignmentDiagnosticReport.critical_contexts_count), 0),
                func.max(AISystemGovernancePresetAssignmentDiagnosticReport.created_at),
            ).where(AISystemGovernancePresetAssignmentDiagnosticReport.organization_id == organization_id)
        ).one()
        diff_totals = self.db.execute(
            select(
                func.coalesce(func.sum(AISystemGovernancePresetAssignmentDiagnosticDiffReport.diagnostic_code_changes_count), 0),
                func.max(AISystemGovernancePresetAssignmentDiagnosticDiffReport.created_at),
            ).where(AISystemGovernancePresetAssignmentDiagnosticDiffReport.organization_id == organization_id)
        ).one()
        return {
            "total_reports": total_reports,
            "active_reports": active_reports,
            "archived_reports": archived_reports,
            "total_diff_reports": total_diff_reports,
            "active_diff_reports": active_diff_reports,
            "archived_diff_reports": archived_diff_reports,
            "unresolved_contexts_total": int(report_totals[0] or 0),
            "warning_contexts_total": int(report_totals[1] or 0),
            "critical_contexts_total": int(report_totals[2] or 0),
            "diagnostic_code_changes_total": int(diff_totals[0] or 0),
            "latest_report_at": report_totals[3],
            "latest_diff_report_at": diff_totals[1],
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_REPORTS_CAVEAT,
        }

    @staticmethod
    def _derived_signing_key_material(
        *,
        organization_id: uuid.UUID,
        key_id: str,
        purpose: str,
    ) -> bytes:
        secret = get_settings().SECRET_KEY.encode("utf-8")
        seed = f"{organization_id}:{purpose}:{key_id}".encode("utf-8")
        return hmac.new(secret, seed, hashlib.sha256).digest()

    @staticmethod
    def _legacy_hmac_signature(checksum_sha256: str) -> str:
        secret = get_settings().SECRET_KEY.encode("utf-8")
        return hmac.new(secret, checksum_sha256.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def _hmac_signature_with_key_material(checksum_sha256: str, *, key_material: bytes) -> str:
        return hmac.new(key_material, checksum_sha256.encode("utf-8"), hashlib.sha256).hexdigest()

    def _active_signing_key_for_diagnostic_export(
        self,
        *,
        organization_id: uuid.UUID,
    ) -> OrganizationInternalSigningKey | None:
        return self.db.execute(
            select(OrganizationInternalSigningKey).where(
                OrganizationInternalSigningKey.organization_id == organization_id,
                OrganizationInternalSigningKey.purpose == POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_PURPOSE,
                OrganizationInternalSigningKey.status == "active",
            )
        ).scalar_one_or_none()

    def _signing_key_by_key_id_for_diagnostic_export(
        self,
        *,
        organization_id: uuid.UUID,
        key_id: str,
    ) -> OrganizationInternalSigningKey | None:
        return self.db.execute(
            select(OrganizationInternalSigningKey).where(
                OrganizationInternalSigningKey.organization_id == organization_id,
                OrganizationInternalSigningKey.purpose == POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_PURPOSE,
                OrganizationInternalSigningKey.key_id == key_id,
            )
        ).scalar_one_or_none()

    def _diagnostic_report_export_payload(
        self,
        *,
        organization_id: uuid.UUID,
        report: AISystemGovernancePresetAssignmentDiagnosticReport,
        generated_at: datetime,
    ) -> dict[str, Any]:
        return {
            "export_type": "diagnostic_report",
            "organization_id": str(organization_id),
            "source_report_id": str(report.id),
            "report_metadata": {
                "status": report.status,
                "title": report.title,
                "description": report.description,
                "created_at": self.as_utc(report.created_at).isoformat() if report.created_at else None,
                "updated_at": self.as_utc(report.updated_at).isoformat() if report.updated_at else None,
                "archived_at": self.as_utc(report.archived_at).isoformat() if report.archived_at else None,
            },
            "input_contexts_json": self.json_safe(report.input_contexts_json),
            "result_json": self.json_safe(report.result_json),
            "counters": {
                "context_count": int(report.context_count),
                "resolved_contexts_count": int(report.resolved_contexts_count),
                "unresolved_contexts_count": int(report.unresolved_contexts_count),
                "warning_contexts_count": int(report.warning_contexts_count),
                "critical_contexts_count": int(report.critical_contexts_count),
            },
            "generated_at": generated_at.isoformat(),
            # Validity window is part of the signed canonical payload -> tamper-evident,
            # and enforced at verify (mirrors the export/attestation fix for consistency;
            # this path already enforces revocation + per-key-id signing).
            "valid_from": generated_at.isoformat(),
            "not_after": (generated_at + timedelta(days=DIAGNOSTIC_EXPORT_VALIDITY_DAYS)).isoformat(),
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_CAVEAT,
        }

    def _diagnostic_diff_report_export_payload(
        self,
        *,
        organization_id: uuid.UUID,
        report: AISystemGovernancePresetAssignmentDiagnosticDiffReport,
        generated_at: datetime,
    ) -> dict[str, Any]:
        return {
            "export_type": "diagnostic_diff_report",
            "organization_id": str(organization_id),
            "source_diff_report_id": str(report.id),
            "diff_metadata": {
                "status": report.status,
                "title": report.title,
                "base_report_id": str(report.base_report_id),
                "compare_report_id": str(report.compare_report_id),
                "created_at": self.as_utc(report.created_at).isoformat() if report.created_at else None,
                "updated_at": self.as_utc(report.updated_at).isoformat() if report.updated_at else None,
                "archived_at": self.as_utc(report.archived_at).isoformat() if report.archived_at else None,
            },
            "diff_json": self.json_safe(report.diff_json),
            "counters": {
                "added_contexts_count": int(report.added_contexts_count),
                "removed_contexts_count": int(report.removed_contexts_count),
                "changed_contexts_count": int(report.changed_contexts_count),
                "unchanged_contexts_count": int(report.unchanged_contexts_count),
                "resolved_delta": int(report.resolved_delta),
                "unresolved_delta": int(report.unresolved_delta),
                "warning_delta": int(report.warning_delta),
                "critical_delta": int(report.critical_delta),
                "diagnostic_code_changes_count": int(report.diagnostic_code_changes_count),
            },
            "generated_at": generated_at.isoformat(),
            "valid_from": generated_at.isoformat(),
            "not_after": (generated_at + timedelta(days=DIAGNOSTIC_EXPORT_VALIDITY_DAYS)).isoformat(),
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_CAVEAT,
        }

    def _sign_diagnostic_export_payload(
        self,
        *,
        organization_id: uuid.UUID,
        canonical_payload_sha256: str,
    ) -> tuple[str, str | None]:
        active_key = self._active_signing_key_for_diagnostic_export(organization_id=organization_id)
        if active_key is None:
            return self._legacy_hmac_signature(canonical_payload_sha256), None
        key_material = self._derived_signing_key_material(
            organization_id=organization_id,
            key_id=active_key.key_id,
            purpose=POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_PURPOSE,
        )
        return (
            self._hmac_signature_with_key_material(canonical_payload_sha256, key_material=key_material),
            active_key.key_id,
        )

    def export_preset_assignment_diagnostic_report(
        self,
        *,
        organization_id: uuid.UUID,
        report_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePresetAssignmentDiagnosticExport:
        report = self.require_preset_assignment_diagnostic_report(organization_id=organization_id, report_id=report_id)
        generated_at = self.now()
        payload = self._diagnostic_report_export_payload(
            organization_id=organization_id,
            report=report,
            generated_at=generated_at,
        )
        canonical_payload_sha256 = self.canonical_sha256(payload)
        internal_signature, signing_key_id = self._sign_diagnostic_export_payload(
            organization_id=organization_id,
            canonical_payload_sha256=canonical_payload_sha256,
        )
        row = AISystemGovernancePresetAssignmentDiagnosticExport(
            organization_id=organization_id,
            export_type="diagnostic_report",
            source_report_id=report.id,
            source_diff_report_id=None,
            status="generated",
            export_payload_json=self.json_safe(payload),
            canonical_payload_sha256=canonical_payload_sha256,
            signature_algorithm=POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_SIGNATURE_ALGORITHM,
            internal_signature=internal_signature,
            signing_key_id=signing_key_id,
            exported_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def export_preset_assignment_diagnostic_diff_report(
        self,
        *,
        organization_id: uuid.UUID,
        diff_report_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePresetAssignmentDiagnosticExport:
        report = self.require_preset_assignment_diagnostic_diff_report(
            organization_id=organization_id,
            diff_report_id=diff_report_id,
        )
        generated_at = self.now()
        payload = self._diagnostic_diff_report_export_payload(
            organization_id=organization_id,
            report=report,
            generated_at=generated_at,
        )
        canonical_payload_sha256 = self.canonical_sha256(payload)
        internal_signature, signing_key_id = self._sign_diagnostic_export_payload(
            organization_id=organization_id,
            canonical_payload_sha256=canonical_payload_sha256,
        )
        row = AISystemGovernancePresetAssignmentDiagnosticExport(
            organization_id=organization_id,
            export_type="diagnostic_diff_report",
            source_report_id=None,
            source_diff_report_id=report.id,
            status="generated",
            export_payload_json=self.json_safe(payload),
            canonical_payload_sha256=canonical_payload_sha256,
            signature_algorithm=POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_SIGNATURE_ALGORITHM,
            internal_signature=internal_signature,
            signing_key_id=signing_key_id,
            exported_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_preset_assignment_diagnostic_exports(
        self,
        *,
        organization_id: uuid.UUID,
        export_type: str | None,
        status_filter: str | None,
        source_report_id: uuid.UUID | None,
        source_diff_report_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePresetAssignmentDiagnosticExport]:
        stmt = select(AISystemGovernancePresetAssignmentDiagnosticExport).where(
            AISystemGovernancePresetAssignmentDiagnosticExport.organization_id == organization_id
        )
        if export_type is not None:
            stmt = stmt.where(AISystemGovernancePresetAssignmentDiagnosticExport.export_type == export_type)
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePresetAssignmentDiagnosticExport.status == status_filter)
        if source_report_id is not None:
            stmt = stmt.where(AISystemGovernancePresetAssignmentDiagnosticExport.source_report_id == source_report_id)
        if source_diff_report_id is not None:
            stmt = stmt.where(
                AISystemGovernancePresetAssignmentDiagnosticExport.source_diff_report_id == source_diff_report_id
            )
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePresetAssignmentDiagnosticExport.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def verify_preset_assignment_diagnostic_export(
        self,
        *,
        organization_id: uuid.UUID,
        row: AISystemGovernancePresetAssignmentDiagnosticExport,
    ) -> dict[str, Any]:
        if row.signature_algorithm != POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_SIGNATURE_ALGORITHM:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported signature_algorithm: {row.signature_algorithm}",
            )
        payload = row.export_payload_json if isinstance(row.export_payload_json, dict) else {}
        recomputed_sha256 = self.canonical_sha256(payload)
        valid_hash = recomputed_sha256 == row.canonical_payload_sha256

        key_status = "legacy"
        if row.signing_key_id:
            key = self._signing_key_by_key_id_for_diagnostic_export(
                organization_id=organization_id,
                key_id=row.signing_key_id,
            )
            if key is None:
                key_status = "missing"
                recomputed_signature = ""
                valid_signature = False
            else:
                key_status = key.status
                key_material = self._derived_signing_key_material(
                    organization_id=organization_id,
                    key_id=key.key_id,
                    purpose=POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_PURPOSE,
                )
                recomputed_signature = self._hmac_signature_with_key_material(
                    recomputed_sha256,
                    key_material=key_material,
                )
                valid_signature = recomputed_signature == row.internal_signature
        else:
            recomputed_signature = self._legacy_hmac_signature(recomputed_sha256)
            valid_signature = recomputed_signature == row.internal_signature

        # Validity-window enforcement (consistency with the export/attestation fix). The
        # window lives in the signed canonical payload, so it is tamper-evident; an
        # expired diagnostic export is no longer trusted, with a distinct "expired" flag
        # separate from the existing revocation ("revoked") and key states.
        not_after_raw = payload.get("not_after") if isinstance(payload, dict) else None
        expired = False
        if isinstance(not_after_raw, str) and not_after_raw:
            try:
                not_after = datetime.fromisoformat(not_after_raw)
                if not_after.tzinfo is None:
                    not_after = not_after.replace(tzinfo=UTC)
                expired = self.now() > not_after
            except ValueError:
                expired = False

        trusted = (
            valid_hash
            and valid_signature
            and row.status == "generated"
            and key_status not in {"revoked", "missing"}
            and not expired
        )
        return {
            "valid_hash": bool(valid_hash),
            "valid_signature": bool(valid_signature),
            "trusted": bool(trusted),
            "expired": bool(expired),
            "canonical_payload_sha256": row.canonical_payload_sha256,
            "recomputed_sha256": recomputed_sha256,
            "signature_algorithm": row.signature_algorithm,
            "signing_key_id": row.signing_key_id,
            "status": row.status,
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_VERIFY_CAVEAT,
        }

    def revoke_preset_assignment_diagnostic_export(
        self,
        *,
        row: AISystemGovernancePresetAssignmentDiagnosticExport,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePresetAssignmentDiagnosticExport:
        if not reason.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason is required")
        if row.status == "revoked":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Diagnostic export is already revoked")
        row.status = "revoked"
        if row.revoked_at is None:
            row.revoked_at = self.now()
        row.revoked_by_user_id = actor_user_id
        row.revocation_reason = reason
        self.db.flush()
        return row

    @classmethod
    def _json_path_append(cls, base: str, key: str) -> str:
        if key.isidentifier():
            return f"{base}.{key}"
        escaped = key.replace("\\", "\\\\").replace('"', '\\"')
        return f'{base}["{escaped}"]'

    @classmethod
    def _flatten_json_paths(cls, value: Any, *, path: str = "$") -> dict[str, Any]:
        output: dict[str, Any] = {}
        if isinstance(value, dict):
            if not value:
                output[path] = {}
                return output
            for key in sorted(value.keys(), key=lambda item: str(item)):
                next_path = cls._json_path_append(path, str(key))
                output.update(cls._flatten_json_paths(value[key], path=next_path))
            return output
        if isinstance(value, list):
            if not value:
                output[path] = []
                return output
            for idx, item in enumerate(value):
                output.update(cls._flatten_json_paths(item, path=f"{path}[{idx}]"))
            return output
        output[path] = cls.json_safe(value)
        return output

    def diff_preset_assignment_diagnostic_exports(
        self,
        *,
        organization_id: uuid.UUID,
        base_export_id: uuid.UUID,
        compare_export_id: uuid.UUID,
        title: str | None,
        persist_diff: bool,
        actor_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        base_export = self.require_preset_assignment_diagnostic_export(
            organization_id=organization_id,
            export_id=base_export_id,
        )
        compare_export = self.require_preset_assignment_diagnostic_export(
            organization_id=organization_id,
            export_id=compare_export_id,
        )
        if base_export.export_type != compare_export.export_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Export types must match")

        base_verification = self.verify_preset_assignment_diagnostic_export(
            organization_id=organization_id,
            row=base_export,
        )
        compare_verification = self.verify_preset_assignment_diagnostic_export(
            organization_id=organization_id,
            row=compare_export,
        )

        base_payload = base_export.export_payload_json if isinstance(base_export.export_payload_json, dict) else {}
        compare_payload = compare_export.export_payload_json if isinstance(compare_export.export_payload_json, dict) else {}
        base_flat = self._flatten_json_paths(base_payload)
        compare_flat = self._flatten_json_paths(compare_payload)

        base_paths = set(base_flat.keys())
        compare_paths = set(compare_flat.keys())
        added_paths = sorted(compare_paths - base_paths)
        removed_paths = sorted(base_paths - compare_paths)
        shared_paths = sorted(base_paths.intersection(compare_paths))
        changed_paths = [path for path in shared_paths if base_flat[path] != compare_flat[path]]
        unchanged_paths_count = len(shared_paths) - len(changed_paths)
        reason_meta_map = self._preset_assignment_diagnostic_export_diff_reason_code_map()

        def severity_for(code: str) -> str:
            meta = reason_meta_map.get(code)
            return str(meta["severity_hint"]) if isinstance(meta, dict) and isinstance(meta.get("severity_hint"), str) else "info"

        reason_code_summary: dict[str, int] = {}

        def add_reason(code: str, count: int = 1) -> None:
            if count <= 0:
                return
            reason_code_summary[code] = int(reason_code_summary.get(code, 0)) + int(count)

        path_diffs: list[dict[str, Any]] = []
        for path in added_paths:
            path_diffs.append(
                {
                    "path": path,
                    "change_type": "added",
                    "reason_code": "EXPORT_PATH_ADDED",
                    "severity_hint": severity_for("EXPORT_PATH_ADDED"),
                    "before_value": None,
                    "after_value": compare_flat[path],
                }
            )
        add_reason("EXPORT_PATH_ADDED", len(added_paths))
        for path in removed_paths:
            path_diffs.append(
                {
                    "path": path,
                    "change_type": "removed",
                    "reason_code": "EXPORT_PATH_REMOVED",
                    "severity_hint": severity_for("EXPORT_PATH_REMOVED"),
                    "before_value": base_flat[path],
                    "after_value": None,
                }
            )
        add_reason("EXPORT_PATH_REMOVED", len(removed_paths))
        for path in changed_paths:
            path_diffs.append(
                {
                    "path": path,
                    "change_type": "changed",
                    "reason_code": "EXPORT_PATH_CHANGED",
                    "severity_hint": severity_for("EXPORT_PATH_CHANGED"),
                    "before_value": base_flat[path],
                    "after_value": compare_flat[path],
                }
            )
        add_reason("EXPORT_PATH_CHANGED", len(changed_paths))
        add_reason("EXPORT_PATH_UNCHANGED", int(unchanged_paths_count))
        path_diffs.sort(key=lambda item: (item["path"], item["change_type"]))

        payload_hash_changed = base_export.canonical_payload_sha256 != compare_export.canonical_payload_sha256
        add_reason("EXPORT_PAYLOAD_HASH_CHANGED" if payload_hash_changed else "EXPORT_PAYLOAD_HASH_UNCHANGED")
        add_reason("EXPORT_TYPE_MATCHED")
        if base_export.source_report_id != compare_export.source_report_id:
            add_reason("EXPORT_SOURCE_REPORT_CHANGED")
        if base_export.source_diff_report_id != compare_export.source_diff_report_id:
            add_reason("EXPORT_SOURCE_DIFF_REPORT_CHANGED")
        if base_verification.get("status") == "revoked":
            add_reason("SOURCE_EXPORT_REVOKED")
        if compare_verification.get("status") == "revoked":
            add_reason("SOURCE_EXPORT_REVOKED")
        if not bool(base_verification.get("valid_signature")):
            add_reason("BASE_EXPORT_SIGNATURE_INVALID")
        if not bool(compare_verification.get("valid_signature")):
            add_reason("COMPARE_EXPORT_SIGNATURE_INVALID")
        if not bool(base_verification.get("trusted")):
            add_reason("BASE_EXPORT_UNTRUSTED")
        if not bool(compare_verification.get("trusted")):
            add_reason("COMPARE_EXPORT_UNTRUSTED")
        reason_code_count = int(sum(int(v or 0) for v in reason_code_summary.values()))

        result: dict[str, Any] = {
            "persisted": persist_diff,
            "export_diff_report_id": None,
            "base_export_id": base_export.id,
            "compare_export_id": compare_export.id,
            "export_type": base_export.export_type,
            "payload_hash_changed": bool(payload_hash_changed),
            "base_verification": {
                "valid_hash": bool(base_verification["valid_hash"]),
                "valid_signature": bool(base_verification["valid_signature"]),
                "trusted": bool(base_verification["trusted"]),
                "status": base_verification["status"],
            },
            "compare_verification": {
                "valid_hash": bool(compare_verification["valid_hash"]),
                "valid_signature": bool(compare_verification["valid_signature"]),
                "trusted": bool(compare_verification["trusted"]),
                "status": compare_verification["status"],
            },
            "added_paths_count": len(added_paths),
            "removed_paths_count": len(removed_paths),
            "changed_paths_count": len(changed_paths),
            "unchanged_paths_count": int(unchanged_paths_count),
            "path_diffs": path_diffs,
            "reason_code_summary": reason_code_summary,
            "reason_code_count": reason_code_count,
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_DIFF_CAVEAT,
        }
        if persist_diff:
            row = AISystemGovernancePresetAssignmentDiagnosticExportDiffReport(
                organization_id=organization_id,
                base_export_id=base_export.id,
                compare_export_id=compare_export.id,
                export_type=base_export.export_type,
                title=title.strip() if isinstance(title, str) and title.strip() else None,
                status="generated",
                diff_json=self.json_safe({**result, "persisted": True, "export_diff_report_id": None}),
                base_canonical_payload_sha256=base_export.canonical_payload_sha256,
                compare_canonical_payload_sha256=compare_export.canonical_payload_sha256,
                payload_hash_changed=bool(payload_hash_changed),
                base_valid_signature=bool(base_verification["valid_signature"]),
                compare_valid_signature=bool(compare_verification["valid_signature"]),
                base_trusted=bool(base_verification["trusted"]),
                compare_trusted=bool(compare_verification["trusted"]),
                added_paths_count=len(added_paths),
                removed_paths_count=len(removed_paths),
                changed_paths_count=len(changed_paths),
                unchanged_paths_count=int(unchanged_paths_count),
                reason_code_summary_json=reason_code_summary,
                reason_code_count=reason_code_count,
                created_by_user_id=actor_user_id,
            )
            self.db.add(row)
            self.db.flush()
            row.diff_json["export_diff_report_id"] = str(row.id)
            self.db.flush()
            result["export_diff_report_id"] = row.id
        return result

    def list_preset_assignment_diagnostic_export_diff_reports(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        export_type: str | None,
        base_export_id: uuid.UUID | None,
        compare_export_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[AISystemGovernancePresetAssignmentDiagnosticExportDiffReport]:
        stmt = select(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport).where(
            AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.organization_id == organization_id
        )
        if status_filter is not None:
            stmt = stmt.where(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.status == status_filter)
        if export_type is not None:
            stmt = stmt.where(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.export_type == export_type)
        if base_export_id is not None:
            stmt = stmt.where(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.base_export_id == base_export_id)
        if compare_export_id is not None:
            stmt = stmt.where(
                AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.compare_export_id == compare_export_id
            )
        return (
            self.db.execute(
                stmt.order_by(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def archive_preset_assignment_diagnostic_export_diff_report(
        self,
        *,
        row: AISystemGovernancePresetAssignmentDiagnosticExportDiffReport,
        actor_user_id: uuid.UUID,
    ) -> AISystemGovernancePresetAssignmentDiagnosticExportDiffReport:
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def preset_assignment_diagnostic_export_diff_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        total_export_diff_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.organization_id == organization_id,
                )
            ).scalar_one()
        )
        active_export_diff_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.organization_id == organization_id,
                    AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.status == "generated",
                )
            ).scalar_one()
        )
        archived_export_diff_reports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.organization_id == organization_id,
                    AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.status == "archived",
                )
            ).scalar_one()
        )
        rows = self.db.execute(
            select(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport).where(
                AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.organization_id == organization_id,
            )
        ).scalars().all()
        payload_hash_changed_reports = sum(1 for row in rows if row.payload_hash_changed)
        total_added_paths = sum(int(row.added_paths_count or 0) for row in rows)
        total_removed_paths = sum(int(row.removed_paths_count or 0) for row in rows)
        total_changed_paths = sum(int(row.changed_paths_count or 0) for row in rows)
        untrusted_source_export_comparisons = sum(
            1 for row in rows if (not bool(row.base_trusted) or not bool(row.compare_trusted))
        )
        total_reason_code_occurrences = 0
        reason_totals: dict[str, int] = {}
        for row in rows:
            total_reason_code_occurrences += int(row.reason_code_count or 0)
            reason_summary = row.reason_code_summary_json if isinstance(row.reason_code_summary_json, dict) else {}
            for code, count in reason_summary.items():
                if not isinstance(code, str):
                    continue
                reason_totals[code] = int(reason_totals.get(code, 0)) + int(count or 0)
        top_reason_codes = [
            {"reason_code": code, "count": count}
            for code, count in sorted(reason_totals.items(), key=lambda item: (-item[1], item[0]))
        ]
        latest_export_diff_report_at = max((row.created_at for row in rows), default=None)
        return {
            "total_export_diff_reports": total_export_diff_reports,
            "active_export_diff_reports": active_export_diff_reports,
            "archived_export_diff_reports": archived_export_diff_reports,
            "payload_hash_changed_reports": int(payload_hash_changed_reports),
            "total_added_paths": int(total_added_paths),
            "total_removed_paths": int(total_removed_paths),
            "total_changed_paths": int(total_changed_paths),
            "untrusted_source_export_comparisons": int(untrusted_source_export_comparisons),
            "total_reason_code_occurrences": int(total_reason_code_occurrences),
            "top_reason_codes": top_reason_codes,
            "latest_export_diff_report_at": latest_export_diff_report_at,
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_DIFF_CAVEAT,
        }

    def preset_assignment_diagnostic_export_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        total_exports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticExport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticExport.organization_id == organization_id,
                )
            ).scalar_one()
        )
        generated_exports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticExport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticExport.organization_id == organization_id,
                    AISystemGovernancePresetAssignmentDiagnosticExport.status == "generated",
                )
            ).scalar_one()
        )
        revoked_exports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticExport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticExport.organization_id == organization_id,
                    AISystemGovernancePresetAssignmentDiagnosticExport.status == "revoked",
                )
            ).scalar_one()
        )
        diagnostic_report_exports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticExport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticExport.organization_id == organization_id,
                    AISystemGovernancePresetAssignmentDiagnosticExport.export_type == "diagnostic_report",
                )
            ).scalar_one()
        )
        diagnostic_diff_report_exports = int(
            self.db.execute(
                select(func.count(AISystemGovernancePresetAssignmentDiagnosticExport.id)).where(
                    AISystemGovernancePresetAssignmentDiagnosticExport.organization_id == organization_id,
                    AISystemGovernancePresetAssignmentDiagnosticExport.export_type == "diagnostic_diff_report",
                )
            ).scalar_one()
        )
        latest = self.db.execute(
            select(
                func.max(AISystemGovernancePresetAssignmentDiagnosticExport.created_at),
                func.max(AISystemGovernancePresetAssignmentDiagnosticExport.revoked_at),
            ).where(
                AISystemGovernancePresetAssignmentDiagnosticExport.organization_id == organization_id,
            )
        ).one()
        return {
            "total_exports": total_exports,
            "generated_exports": generated_exports,
            "revoked_exports": revoked_exports,
            "diagnostic_report_exports": diagnostic_report_exports,
            "diagnostic_diff_report_exports": diagnostic_diff_report_exports,
            "latest_export_at": latest[0],
            "latest_revocation_at": latest[1],
            "caveat": POLICY_DIFF_GATING_COMPARE_PRESET_ASSIGNMENT_DIAGNOSTIC_EXPORT_CAVEAT,
        }

    def summary(self, *, organization_id: uuid.UUID) -> dict[str, int]:
        now = self.now()
        since = now - timedelta(days=30)

        active_packs = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewSequencePack.id)).where(
                    AISystemGovernanceReviewSequencePack.organization_id == organization_id,
                    AISystemGovernanceReviewSequencePack.status == "active",
                )
            ).scalar_one()
        )
        inactive_packs = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewSequencePack.id)).where(
                    AISystemGovernanceReviewSequencePack.organization_id == organization_id,
                    AISystemGovernanceReviewSequencePack.status == "inactive",
                )
            ).scalar_one()
        )
        archived_packs = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewSequencePack.id)).where(
                    AISystemGovernanceReviewSequencePack.organization_id == organization_id,
                    AISystemGovernanceReviewSequencePack.status == "archived",
                )
            ).scalar_one()
        )
        active_steps = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewSequenceStep.id)).where(
                    AISystemGovernanceReviewSequenceStep.organization_id == organization_id,
                    AISystemGovernanceReviewSequenceStep.status == "active",
                )
            ).scalar_one()
        )
        sequence_runs = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewSequenceRun.id)).where(
                    AISystemGovernanceReviewSequenceRun.organization_id == organization_id,
                )
            ).scalar_one()
        )
        previewed_runs = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewSequenceRun.id)).where(
                    AISystemGovernanceReviewSequenceRun.organization_id == organization_id,
                    AISystemGovernanceReviewSequenceRun.status == "previewed",
                )
            ).scalar_one()
        )
        applied_runs = int(
            self.db.execute(
                select(func.count(AISystemGovernanceReviewSequenceRun.id)).where(
                    AISystemGovernanceReviewSequenceRun.organization_id == organization_id,
                    AISystemGovernanceReviewSequenceRun.status == "applied",
                )
            ).scalar_one()
        )

        recent_runs = (
            self.db.execute(
                select(AISystemGovernanceReviewSequenceRun).where(
                    AISystemGovernanceReviewSequenceRun.organization_id == organization_id,
                    AISystemGovernanceReviewSequenceRun.created_at >= since,
                )
            )
            .scalars()
            .all()
        )

        return {
            "active_packs": active_packs,
            "inactive_packs": inactive_packs,
            "archived_packs": archived_packs,
            "active_steps": active_steps,
            "sequence_runs": sequence_runs,
            "previewed_runs": previewed_runs,
            "applied_runs": applied_runs,
            "generated_reviews_last_30d": int(sum(row.generated_reviews_count for row in recent_runs)),
            "skipped_reviews_last_30d": int(sum(row.skipped_reviews_count for row in recent_runs)),
        }
