from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_system import AISystem
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
from app.models.governance_autopilot_runner_session import GovernanceAutopilotRunnerSession
from app.models.governance_autopilot_runner_handshake import GovernanceAutopilotRunnerHandshake
from app.models.governance_autopilot_noop_runner_event import GovernanceAutopilotNoopRunnerEvent
from app.models.governance_recommendation_snapshot import GovernanceRecommendationSnapshot
from app.models.governance_recommendation_action_disposition import GovernanceRecommendationActionDisposition
from app.models.governance_copilot_draft_snapshot import GovernanceCopilotDraftSnapshot
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.risk import Risk
from app.models.task import Task
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.models.organization_governance_setting import OrganizationGovernanceSetting
from app.services.ai_system_service import AISystemService
from app.services.email_service import EmailService
from app.services.seed_service import SeedService
from app.core.validation import validate_choice

AI_RISK_ASSESSMENT_CAVEAT = (
    "AI risk assessments are manual governance records. CompliVibe does not make legal determinations "
    "or automatically classify regulatory status in this phase."
)

RISK_LEVEL_WEIGHTS: dict[str, int] = {
    "unknown": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
RISK_VALUES: tuple[str, ...] = ("unknown", "low", "medium", "high", "critical")
PROFILE_STATUSES: tuple[str, ...] = ("active", "inactive", "archived")
DIMENSION_TEMPLATE_STATUSES: tuple[str, ...] = ("active", "inactive", "archived")
DEFAULT_PROFILE_METHODOLOGY_VERSION = "manual-configurable-v1"
DEFAULT_DIMENSION_TEMPLATE_METHODOLOGY_VERSION = "manual-dimension-v1"
RISK_LEVEL_CALCULABLE_VALUES: tuple[str, ...] = ("low", "medium", "high", "critical")
DIMENSION_LEVEL_VALUES: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
RISK_DIMENSION_KEYS: tuple[str, ...] = (
    "safety",
    "privacy",
    "security",
    "fairness",
    "transparency",
    "human_oversight",
    "reliability",
    "data_quality",
    "legal_regulatory",
    "third_party",
    "operational",
    "reputational",
)
DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    "safety": 1.5,
    "privacy": 1.2,
    "security": 1.2,
    "fairness": 1.0,
    "transparency": 0.8,
    "human_oversight": 1.0,
    "reliability": 1.1,
    "data_quality": 1.0,
    "legal_regulatory": 1.3,
    "third_party": 0.9,
    "operational": 0.8,
    "reputational": 0.7,
}
DEFAULT_DIMENSION_THRESHOLDS: list[dict[str, float | str]] = [
    {"min_score": 1.0, "max_score": 1.75, "risk_level": "low"},
    {"min_score": 1.76, "max_score": 2.5, "risk_level": "medium"},
    {"min_score": 2.51, "max_score": 3.25, "risk_level": "high"},
    {"min_score": 3.26, "max_score": 4.0, "risk_level": "critical"},
]
DEFAULT_LIKELIHOOD_WEIGHTS: dict[str, int | None] = {
    "unknown": None,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
DEFAULT_IMPACT_WEIGHTS: dict[str, int | None] = {
    "unknown": None,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
DEFAULT_RISK_LEVEL_THRESHOLDS: list[dict[str, int | str]] = [
    {"min_score": 1, "max_score": 3, "risk_level": "low"},
    {"min_score": 4, "max_score": 6, "risk_level": "medium"},
    {"min_score": 7, "max_score": 11, "risk_level": "high"},
    {"min_score": 12, "max_score": 16, "risk_level": "critical"},
]
AI_RISK_SCORING_CAVEAT = (
    "Calculated risk level is deterministic presentation output from manual inputs and a configured "
    "scoring profile. It is not legal or regulatory classification."
)
AI_RISK_DIMENSION_CAVEAT = (
    "Dimension and residual risk outputs are deterministic presentation values from manual inputs and configured "
    "templates. They are not legal or regulatory classifications."
)
AI_RISK_CLASSIFICATION_CAVEAT = (
    "Classification records are manual governance assertions entered by users. They are not automatic legal "
    "or regulatory determinations."
)

CLASSIFICATION_TAXONOMY_STATUSES: tuple[str, ...] = ("active", "inactive", "archived")
CLASSIFICATION_RECORD_STATUSES: tuple[str, ...] = ("active", "superseded", "archived")
CLASSIFICATION_CONFIDENCE_VALUES: tuple[str, ...] = ("unknown", "low", "medium", "high")
CLASSIFICATION_SOURCE_TYPES: tuple[str, ...] = (
    "operator_attestation",
    "customer_input",
    "internal_review",
    "external_counsel",
    "other",
)
DEFAULT_CLASSIFICATION_METHODOLOGY_VERSION = "manual-classification-v1"
CLASSIFICATION_REVIEW_STATUSES: tuple[str, ...] = (
    "not_submitted",
    "in_review",
    "changes_requested",
    "reviewed",
    "rejected",
)
CLASSIFICATION_SNAPSHOT_TYPES: tuple[str, ...] = (
    "manual_snapshot",
    "review_snapshot",
    "changes_requested_snapshot",
    "rejection_snapshot",
    "archive_snapshot",
)
GOVERNANCE_SIGNAL_DOMAIN_VALUES: tuple[str, ...] = ("ai_risk",)
GOVERNANCE_SIGNAL_ENTITY_TYPE_VALUES: tuple[str, ...] = ("ai_system", "risk_assessment", "risk_classification")
GOVERNANCE_SIGNAL_STATUS_VALUES: tuple[str, ...] = ("open", "resolved", "dismissed", "archived")
GOVERNANCE_SIGNAL_SEVERITY_VALUES: tuple[str, ...] = ("info", "warning", "critical")
AI_RISK_GOVERNANCE_SIGNAL_CAVEAT = (
    "Governance signals are deterministic indicators for human attention. They do not approve, reject, certify, "
    "classify legally, or trigger automation."
)
AI_RISK_GOVERNANCE_SIGNAL_PRIORITY_CAVEAT = (
    "Signal priority is deterministic presentation logic for human attention ordering. "
    "It does not create tasks, trigger automation, or make legal/regulatory determinations."
)
AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT = (
    "Candidate actions are deterministic suggestions for human operators. They do not create tasks, trigger "
    "automation, approve, reject, or mutate governance records."
)
AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT = (
    "Recommendation snapshots preserve deterministic candidate actions at a point in time. "
    "They do not create tasks, trigger automation, approve, reject, or mutate governance records."
)
GOVERNANCE_RECOMMENDATION_SCOPE_TYPES: tuple[str, ...] = ("organization", "ai_system", "risk_assessment")
GOVERNANCE_RECOMMENDATION_SOURCE_TYPES: tuple[str, ...] = ("candidate_actions",)
GOVERNANCE_RECOMMENDATION_DISPOSITION_STATUS_VALUES: tuple[str, ...] = (
    "acknowledged",
    "dismissed",
    "deferred",
    "accepted_for_manual_work",
)
AUTOPILOT_POLICY_STATUS_VALUES: tuple[str, ...] = ("active", "inactive", "archived")
AUTOPILOT_POLICY_MODE_VALUES: tuple[str, ...] = (
    "disabled",
    "observe_only",
    "suggest_only",
    "draft_only",
    "require_approval",
    "execute_safe_later",
)
AUTOPILOT_PRIORITY_BANDS: tuple[str, ...] = ("low", "medium", "high", "urgent")
AUTOPILOT_ACTION_RISK_TIERS: tuple[str, ...] = ("low", "medium", "high")
AUTOPILOT_DEFAULT_CONFIDENCE_SCORE = 0.5
AUTOPILOT_DEFAULT_AUTO_EXECUTE_THRESHOLD = 0.95
AUTOPILOT_DEFAULT_REVERSAL_WINDOW_HOURS = 24
AUTOPILOT_CIRCUIT_BREAKER_REVERSAL_RATE_THRESHOLD = 0.2
AUTOPILOT_CIRCUIT_BREAKER_MIN_SAMPLE_SIZE = 3
AUTOPILOT_CIRCUIT_BREAKER_ABSOLUTE_REVERSAL_MIN_SAMPLE_SIZE = 2
AUTOPILOT_CIRCUIT_BREAKER_WINDOW_HOURS = 24
AUTOPILOT_CIRCUIT_BREAKER_SPIKE_WINDOW_HOURS = 1
AUTOPILOT_CIRCUIT_BREAKER_SPIKE_MULTIPLIER = 3.0
AUTOPILOT_CIRCUIT_BREAKER_SPIKE_MIN_EXECUTIONS = 10
AUTOPILOT_SAFE_FALLBACK_MODE = "suggest_only"
AUTOPILOT_SAFE_FALLBACK_CAVEAT = (
    "Autopilot policies define deterministic guardrails and evaluation decisions. "
    "Phase 7.0 does not execute automation, create tasks, create reviews, approve, publish, "
    "or mutate governance records."
)
AUTOPILOT_EXECUTION_INTENT_SOURCE_TYPES: tuple[str, ...] = (
    "candidate_action",
    "recommendation_snapshot",
    "copilot_draft_snapshot",
)
AUTOPILOT_EXECUTION_INTENT_STATUS_VALUES: tuple[str, ...] = (
    "planned",
    "approval_required",
    "blocked",
    "archived",
)
AUTOPILOT_EXECUTION_APPROVAL_STATUS_VALUES: tuple[str, ...] = (
    "requested",
    "approved",
    "rejected",
    "cancelled",
)
AUTOPILOT_APPROVAL_POLICY_STATUS_VALUES: tuple[str, ...] = ("active", "inactive", "archived")
AUTOPILOT_EXECUTION_APPROVAL_VOTE_STATUS_VALUES: tuple[str, ...] = ("approved", "rejected")
AUTOPILOT_EXECUTION_READINESS_STATES: tuple[str, ...] = (
    "not_ready",
    "approval_required",
    "ready_for_runner",
    "blocked",
    "cancelled",
    "rejected",
)
AUTOPILOT_EXECUTION_INTENT_CAVEAT = (
    "Execution intents are dry-run planning artifacts. Phase 7.1 does not execute actions, create tasks, "
    "create reviews, send notifications, approve, publish, or mutate governance records."
)
AUTOPILOT_EXECUTION_APPROVAL_CAVEAT = (
    "Execution approvals record human authorization metadata only. Phase 7.2 does not execute actions, create "
    "tasks, create reviews, send notifications, approve compliance, publish, or mutate governance records."
)
AUTOPILOT_EXECUTION_QUORUM_CAVEAT = (
    "Approval quorum and dual-control rules determine human authorization readiness only. "
    "Phase 7.3 does not execute actions, create tasks, create reviews, send notifications, "
    "approve compliance, publish, or mutate source governance records."
)
AUTOPILOT_RUNNER_SIMULATION_STATUS_VALUES: tuple[str, ...] = (
    "ready_for_runner",
    "not_ready",
    "blocked",
    "approval_required",
    "policy_denied",
    "capability_denied",
    "archived",
)
AUTOPILOT_RUNNER_HANDOFF_VERSION = "autopilot_runner_handoff_v1"
AUTOPILOT_RUNNER_INTERFACE_CAVEAT = (
    "Runner interface and runner simulations are dry-run-only in Phase 7.4. "
    "They do not execute actions, queue jobs, create tasks, create reviews, call external services, "
    "send notifications, publish, approve compliance, or mutate governance records."
)
AUTOPILOT_RUNNER_ADMISSION_STATUS_VALUES: tuple[str, ...] = (
    "admitted",
    "blocked",
    "revoked",
    "expired",
    "archived",
)
AUTOPILOT_RUNNER_ADMISSION_TOKEN_TTL_HOURS = 24
AUTOPILOT_RUNNER_ADMISSION_CAVEAT = (
    "Runner admissions and handoff tokens are non-executing guardrail artifacts. "
    "Phase 7.5 does not execute actions, queue jobs, create tasks, create reviews, call external services, "
    "send notifications, publish, approve compliance, or mutate governance records."
)
AUTOPILOT_RUNNER_SESSION_STATUS_VALUES: tuple[str, ...] = (
    "active",
    "expired",
    "locked",
    "revoked",
    "archived",
)
AUTOPILOT_RUNNER_SESSION_DEFAULT_TTL_MINUTES = 10
AUTOPILOT_RUNNER_SESSION_DEFAULT_MAX_ATTEMPTS = 3
AUTOPILOT_RUNNER_SESSION_DEFAULT_REPLAY_WINDOW_SECONDS = 600
AUTOPILOT_RUNNER_SESSION_CAVEAT = (
    "Runner sessions and leases are non-executing guardrail artifacts. "
    "Phase 7.6 does not execute actions, queue jobs, create tasks, create reviews, call external services, "
    "send notifications, publish, approve compliance, or mutate source governance records."
)
AUTOPILOT_RUNNER_HANDSHAKE_VERSION = "autopilot_runner_handshake_v1"
AUTOPILOT_RUNNER_HANDSHAKE_STATUS_VALUES: tuple[str, ...] = (
    "ready_for_future_runner",
    "blocked",
    "session_expired",
    "session_locked",
    "session_revoked",
    "admission_revoked",
    "revoked",
    "archived",
)
AUTOPILOT_RUNNER_HANDSHAKE_CAVEAT = (
    "Runner handshakes are non-executing future-runner contract artifacts. "
    "Phase 7.7 does not execute actions, queue jobs, create tasks, create reviews, call external services, "
    "send notifications, publish, approve compliance, or mutate source governance records."
)
AUTOPILOT_NOOP_RUNNER_EVENT_VERSION = "autopilot_noop_runner_event_v1"
AUTOPILOT_NOOP_RUNNER_EVENT_TYPE = "noop_runner_control_plane_check"
AUTOPILOT_NOOP_RUNNER_EVENT_STATUS_VALUES: tuple[str, ...] = (
    "logged",
    "blocked",
    "archived",
)
AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION = "noop_runner_reports.v1"
AUTOPILOT_NOOP_RUNNER_REPORT_TYPES: tuple[str, ...] = (
    "ledger",
    "timeline",
    "blockers",
    "readiness",
    "idempotency",
    "control_plane_health",
)
AUTOPILOT_NOOP_RUNNER_CLIENT_CONTRACT_VERSION = "noop_runner_client_contract.v1"
AUTOPILOT_NOOP_RUNNER_PAGINATION_CONTRACT_VERSION = "noop_runner_pagination.v1"
AUTOPILOT_NOOP_RUNNER_DEFAULT_LIMIT = 100
AUTOPILOT_NOOP_RUNNER_MAX_LIMIT = 500
AUTOPILOT_NOOP_RUNNER_COMPATIBILITY_POLICY_VERSION = "noop_runner_compatibility.v1"
AUTOPILOT_NOOP_RUNNER_COMPATIBILITY_POLICY_ENDPOINT = (
    "/api/v1/ai-governance/autopilot/noop-runner/reports/compatibility-policy"
)
AUTOPILOT_NOOP_RUNNER_CLIENT_CONTRACT_ENDPOINT = (
    "/api/v1/ai-governance/autopilot/noop-runner/reports/client-contract"
)
AUTOPILOT_NOOP_RUNNER_FILTER_OPTIONS_ENDPOINT = (
    "/api/v1/ai-governance/autopilot/noop-runner/reports/filter-options"
)
AUTOPILOT_NOOP_RUNNER_PAGINATION_CONTRACT_ENDPOINT = (
    "/api/v1/ai-governance/autopilot/noop-runner/reports/pagination-contract"
)
AUTOPILOT_NOOP_RUNNER_FIELD_DOCS_ENDPOINT = "/api/v1/ai-governance/autopilot/noop-runner/reports/field-docs"
AUTOPILOT_NOOP_RUNNER_DISPLAY_METADATA_ENDPOINT = (
    "/api/v1/ai-governance/autopilot/noop-runner/reports/display-metadata"
)
AUTOPILOT_NOOP_RUNNER_LOCALIZATION_MAP_ENDPOINT = (
    "/api/v1/ai-governance/autopilot/noop-runner/reports/localization-map"
)
AUTOPILOT_NOOP_RUNNER_CLIENT_HINTS_ENDPOINT = "/api/v1/ai-governance/autopilot/noop-runner/reports/client-hints"
AUTOPILOT_NOOP_RUNNER_FIELD_DOCS_VERSION = "noop_runner_field_docs.v1"
AUTOPILOT_NOOP_RUNNER_DISPLAY_METADATA_VERSION = "noop_runner_display_metadata.v1"
AUTOPILOT_NOOP_RUNNER_LOCALIZATION_MAP_VERSION = "noop_runner_localization_map.v1"
AUTOPILOT_NOOP_RUNNER_CLIENT_HINTS_VERSION = "noop_runner_client_hints.v1"
AUTOPILOT_NOOP_RUNNER_DEPRECATED_FIELDS_POLICY = (
    "Fields in v1 must remain available until a future v2 contract is introduced."
)
AUTOPILOT_NOOP_RUNNER_STABLE_ENDPOINT_FAMILIES: tuple[str, ...] = (
    "report_contract",
    "diagnostics_manifest",
    "bounded_export",
    "checksum",
    "ledger",
    "timeline",
    "blockers",
    "readiness",
    "idempotency",
    "control_plane_health",
    "no_op_runner_events",
)
AUTOPILOT_NOOP_RUNNER_CAVEAT = (
    "No-op runner control-plane logging and observability are non-executing artifacts only. "
    "No real runner exists and no job queue is present. "
    "Phase 8.5 does not execute actions, queue jobs, create tasks, create reviews, create files, call external services, "
    "send notifications, publish, approve compliance, or mutate source governance records. "
    "Diagnostics and bounded exports are JSON-only API responses with no PDF/ZIP or external storage artifacts."
)
AUTOPILOT_CAPABILITY_MATRIX: tuple[dict[str, Any], ...] = (
    {
        "capability_key": "refresh_signal_preview",
        "action_type": "refresh_signals",
        "description": "Preview signal refresh behavior without persistence.",
        "default_allowed": True,
        "requires_policy_allow": False,
        "requires_human_approval": False,
        "external_effects": False,
        "creates_task": False,
        "creates_review": False,
        "mutates_source_record": False,
        "allowed_in_phase_7_1": True,
    },
    {
        "capability_key": "create_recommendation_snapshot_intent",
        "action_type": "create_record",
        "description": "Plan a recommendation snapshot creation path for future gated execution.",
        "default_allowed": False,
        "requires_policy_allow": True,
        "requires_human_approval": True,
        "external_effects": False,
        "creates_task": False,
        "creates_review": False,
        "mutates_source_record": False,
        "allowed_in_phase_7_1": False,
    },
    {
        "capability_key": "create_copilot_draft_snapshot_intent",
        "action_type": "create_snapshot",
        "description": "Plan a copilot draft snapshot creation path for future gated execution.",
        "default_allowed": False,
        "requires_policy_allow": True,
        "requires_human_approval": True,
        "external_effects": False,
        "creates_task": False,
        "creates_review": False,
        "mutates_source_record": False,
        "allowed_in_phase_7_1": False,
    },
    {
        "capability_key": "acknowledge_recommendation_intent",
        "action_type": "resolve_issue",
        "description": "Plan recommendation acknowledgement workflow metadata only.",
        "default_allowed": False,
        "requires_policy_allow": True,
        "requires_human_approval": True,
        "external_effects": False,
        "creates_task": False,
        "creates_review": False,
        "mutates_source_record": False,
        "allowed_in_phase_7_1": False,
    },
    {
        "capability_key": "create_task",
        "action_type": "create_task",
        "description": "Potential task creation capability (not executable in Phase 7.1).",
        "default_allowed": False,
        "requires_policy_allow": True,
        "requires_human_approval": True,
        "external_effects": False,
        "creates_task": True,
        "creates_review": False,
        "mutates_source_record": False,
        "allowed_in_phase_7_1": False,
    },
    {
        "capability_key": "create_review",
        "action_type": "create_review",
        "description": "Potential review creation capability (not executable in Phase 7.1).",
        "default_allowed": False,
        "requires_policy_allow": True,
        "requires_human_approval": True,
        "external_effects": False,
        "creates_task": False,
        "creates_review": True,
        "mutates_source_record": False,
        "allowed_in_phase_7_1": False,
    },
    {
        "capability_key": "mutate_risk_assessment",
        "action_type": "mutate_risk_assessment",
        "description": "Potential risk assessment mutation capability (blocked in Phase 7.1).",
        "default_allowed": False,
        "requires_policy_allow": True,
        "requires_human_approval": True,
        "external_effects": False,
        "creates_task": False,
        "creates_review": False,
        "mutates_source_record": True,
        "allowed_in_phase_7_1": False,
    },
    {
        "capability_key": "mutate_classification",
        "action_type": "mutate_classification",
        "description": "Potential classification mutation capability (blocked in Phase 7.1).",
        "default_allowed": False,
        "requires_policy_allow": True,
        "requires_human_approval": True,
        "external_effects": False,
        "creates_task": False,
        "creates_review": False,
        "mutates_source_record": True,
        "allowed_in_phase_7_1": False,
    },
    {
        "capability_key": "external_notification",
        "action_type": "external_notification",
        "description": "Potential external notification capability (blocked in Phase 7.1).",
        "default_allowed": False,
        "requires_policy_allow": True,
        "requires_human_approval": True,
        "external_effects": True,
        "creates_task": False,
        "creates_review": False,
        "mutates_source_record": False,
        "allowed_in_phase_7_1": False,
    },
)

GOVERNANCE_CANDIDATE_ACTION_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "action_key": "create_classification_record",
        "title": "Create classification record",
        "description": "Create an active manual classification record for this assessment.",
        "action_type": "create_record",
        "source_reason_codes": ["assessment_missing_classification"],
        "default_priority_band": "high",
        "recommended_owner_type": "risk_owner",
        "target_entity_type": "risk_assessment",
        "target_route_hint": "/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/classifications",
        "human_approval_required": True,
        "automation_allowed": False,
    },
    {
        "action_key": "review_classification",
        "title": "Review classification",
        "description": "Review the submitted classification and set an explicit manual review status.",
        "action_type": "review_record",
        "source_reason_codes": ["classification_needs_review"],
        "default_priority_band": "high",
        "recommended_owner_type": "reviewer",
        "target_entity_type": "risk_classification",
        "target_route_hint": "/api/v1/ai-governance/ai-risk/classifications/{classification_id}",
        "human_approval_required": True,
        "automation_allowed": False,
    },
    {
        "action_key": "improve_classification_justification",
        "title": "Improve classification justification",
        "description": "Update classification rationale and confidence support details.",
        "action_type": "update_record",
        "source_reason_codes": ["classification_low_confidence"],
        "default_priority_band": "medium",
        "recommended_owner_type": "risk_owner",
        "target_entity_type": "risk_classification",
        "target_route_hint": "/api/v1/ai-governance/ai-risk/classifications/{classification_id}",
        "human_approval_required": True,
        "automation_allowed": False,
    },
    {
        "action_key": "address_classification_change_request",
        "title": "Address requested classification changes",
        "description": "Apply requested changes and resubmit classification for review.",
        "action_type": "update_record",
        "source_reason_codes": ["classification_changes_requested"],
        "default_priority_band": "high",
        "recommended_owner_type": "risk_owner",
        "target_entity_type": "risk_classification",
        "target_route_hint": "/api/v1/ai-governance/ai-risk/classifications/{classification_id}/submit-for-review",
        "human_approval_required": True,
        "automation_allowed": False,
    },
    {
        "action_key": "revise_or_replace_classification",
        "title": "Revise or replace rejected classification",
        "description": "Revise the rejected classification or create a replacement record.",
        "action_type": "prepare_draft",
        "source_reason_codes": ["classification_rejected"],
        "default_priority_band": "urgent",
        "recommended_owner_type": "risk_owner",
        "target_entity_type": "risk_classification",
        "target_route_hint": "/api/v1/ai-governance/ai-risk/classifications/{classification_id}",
        "human_approval_required": True,
        "automation_allowed": False,
    },
    {
        "action_key": "attach_classification_evidence",
        "title": "Attach supporting evidence",
        "description": "Attach relevant evidence references to the classification record.",
        "action_type": "attach_evidence",
        "source_reason_codes": ["classification_has_unlinked_evidence"],
        "default_priority_band": "medium",
        "recommended_owner_type": "risk_owner",
        "target_entity_type": "risk_classification",
        "target_route_hint": "/api/v1/ai-governance/ai-risk/classifications/{classification_id}",
        "human_approval_required": True,
        "automation_allowed": False,
    },
    {
        "action_key": "create_current_classification",
        "title": "Create current active classification",
        "description": "Create a current active classification when only superseded records exist.",
        "action_type": "create_record",
        "source_reason_codes": ["assessment_has_superseded_classification_only"],
        "default_priority_band": "high",
        "recommended_owner_type": "risk_owner",
        "target_entity_type": "risk_assessment",
        "target_route_hint": "/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/classifications",
        "human_approval_required": True,
        "automation_allowed": False,
    },
)


class AISystemRiskAssessmentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.ai_system_service = AISystemService(db)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def canonical_json(payload: dict) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @staticmethod
    def to_json_compatible(payload: Any) -> Any:
        return json.loads(json.dumps(payload, default=str, sort_keys=True, ensure_ascii=True))

    @classmethod
    def sha256_hexdigest(cls, payload: dict) -> str:
        return hashlib.sha256(cls.canonical_json(payload).encode("utf-8")).hexdigest()

    @classmethod
    def deterministic_score(cls, *, likelihood: str, impact: str) -> int | None:
        if likelihood == "unknown" or impact == "unknown":
            return None
        return RISK_LEVEL_WEIGHTS[likelihood] * RISK_LEVEL_WEIGHTS[impact]

    @staticmethod
    def _normalize_weights(weights: dict | None, *, field_name: str) -> dict[str, int | None]:
        payload = dict(weights or {})
        if not payload:
            payload = (
                dict(DEFAULT_LIKELIHOOD_WEIGHTS)
                if field_name == "likelihood_weights_json"
                else dict(DEFAULT_IMPACT_WEIGHTS)
            )

        keys = set(payload.keys())
        required = set(RISK_VALUES)
        if keys != required:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field_name} must include exactly: {', '.join(sorted(required))}",
            )

        normalized: dict[str, int | None] = {}
        for key in RISK_VALUES:
            value = payload.get(key)
            if key == "unknown":
                if value is not None and not isinstance(value, int):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{field_name}.unknown must be null or integer",
                    )
                normalized[key] = value
                continue
            if not isinstance(value, int) or value <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field_name}.{key} must be a positive integer",
                )
            normalized[key] = value
        return normalized

    @staticmethod
    def _normalize_thresholds(thresholds: list | None) -> list[dict[str, int | str]]:
        payload = list(thresholds or [])
        if not payload:
            payload = [dict(item) for item in DEFAULT_RISK_LEVEL_THRESHOLDS]

        normalized: list[dict[str, int | str]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="risk_level_thresholds_json must be an array of objects")
            min_score = item.get("min_score")
            max_score = item.get("max_score")
            risk_level = item.get("risk_level")
            if not isinstance(min_score, int) or not isinstance(max_score, int):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Threshold min_score/max_score must be integers")
            if min_score < 0 or max_score < 0 or min_score > max_score:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Threshold ranges must satisfy 0 <= min_score <= max_score")
            if risk_level not in RISK_VALUES:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Threshold risk_level must be a valid risk value")
            normalized.append({"min_score": min_score, "max_score": max_score, "risk_level": str(risk_level)})

        normalized.sort(key=lambda item: int(item["min_score"]))
        for index in range(1, len(normalized)):
            prev_max = int(normalized[index - 1]["max_score"])
            current_min = int(normalized[index]["min_score"])
            if current_min <= prev_max:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="risk_level_thresholds_json ranges must not overlap")
        return normalized

    def normalize_scoring_profile_inputs(
        self,
        *,
        likelihood_weights_json: dict | None,
        impact_weights_json: dict | None,
        risk_level_thresholds_json: list | None,
    ) -> tuple[dict[str, int | None], dict[str, int | None], list[dict[str, int | str]]]:
        return (
            self._normalize_weights(likelihood_weights_json, field_name="likelihood_weights_json"),
            self._normalize_weights(impact_weights_json, field_name="impact_weights_json"),
            self._normalize_thresholds(risk_level_thresholds_json),
        )

    @staticmethod
    def _normalize_dimension_weights(weights: dict | None) -> dict[str, float]:
        payload = dict(weights or {})
        if not payload:
            payload = dict(DEFAULT_DIMENSION_WEIGHTS)

        keys = set(payload.keys())
        required = set(RISK_DIMENSION_KEYS)
        if keys != required:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"dimension_weights_json must include exactly: {', '.join(sorted(required))}",
            )

        normalized: dict[str, float] = {}
        for key in RISK_DIMENSION_KEYS:
            value = payload.get(key)
            if not isinstance(value, int | float) or float(value) <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"dimension_weights_json.{key} must be a positive number",
                )
            normalized[key] = float(value)
        return normalized

    @staticmethod
    def _normalize_dimension_thresholds(thresholds: list | None) -> list[dict[str, float | str]]:
        payload = list(thresholds or [])
        if not payload:
            payload = [dict(item) for item in DEFAULT_DIMENSION_THRESHOLDS]

        normalized: list[dict[str, float | str]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="dimension_thresholds_json must be an array of objects",
                )
            min_score = item.get("min_score")
            max_score = item.get("max_score")
            risk_level = item.get("risk_level")
            if not isinstance(min_score, int | float) or not isinstance(max_score, int | float):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Dimension threshold min_score/max_score must be numbers",
                )
            min_value = float(min_score)
            max_value = float(max_score)
            if min_value < 0 or max_value < 0 or min_value > max_value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Dimension threshold ranges must satisfy 0 <= min_score <= max_score",
                )
            if risk_level not in RISK_LEVEL_CALCULABLE_VALUES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Dimension threshold risk_level must be one of: low, medium, high, critical",
                )
            normalized.append(
                {"min_score": round(min_value, 6), "max_score": round(max_value, 6), "risk_level": str(risk_level)}
            )

        normalized.sort(key=lambda item: float(item["min_score"]))
        for index in range(1, len(normalized)):
            prev_max = float(normalized[index - 1]["max_score"])
            current_min = float(normalized[index]["min_score"])
            if current_min <= prev_max:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="dimension_thresholds_json ranges must not overlap",
                )
        return normalized

    def normalize_dimension_template_inputs(
        self,
        *,
        dimension_weights_json: dict | None,
        dimension_thresholds_json: list | None,
    ) -> tuple[dict[str, float], list[dict[str, float | str]]]:
        return (
            self._normalize_dimension_weights(dimension_weights_json),
            self._normalize_dimension_thresholds(dimension_thresholds_json),
        )

    @staticmethod
    def normalize_classification_taxonomy_json(taxonomy_json: dict | None) -> dict:
        if not isinstance(taxonomy_json, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="taxonomy_json must be an object")
        label_groups = taxonomy_json.get("label_groups")
        if not isinstance(label_groups, list) or not label_groups:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="taxonomy_json.label_groups must be a non-empty array")

        seen_group_keys: set[str] = set()
        normalized_groups: list[dict] = []
        for raw_group in label_groups:
            if not isinstance(raw_group, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Each taxonomy label group must be an object")
            group_key = raw_group.get("group_key")
            title = raw_group.get("title")
            labels = raw_group.get("labels")
            if not isinstance(group_key, str) or not group_key.strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="label_groups[].group_key is required")
            if group_key in seen_group_keys:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate taxonomy group_key")
            seen_group_keys.add(group_key)
            if not isinstance(title, str) or not title.strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"label_groups[{group_key}].title is required")
            if not isinstance(labels, list) or not labels:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"label_groups[{group_key}].labels must be a non-empty array",
                )

            seen_label_keys: set[str] = set()
            normalized_labels: list[dict] = []
            for raw_label in labels:
                if not isinstance(raw_label, dict):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="labels[] entries must be objects")
                label_key = raw_label.get("label_key")
                label_title = raw_label.get("title")
                if not isinstance(label_key, str) or not label_key.strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"label_groups[{group_key}].labels[].label_key is required",
                    )
                if label_key in seen_label_keys:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Duplicate label_key in taxonomy group '{group_key}'",
                    )
                seen_label_keys.add(label_key)
                if not isinstance(label_title, str) or not label_title.strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"label_groups[{group_key}].labels[{label_key}].title is required",
                    )
                normalized_labels.append({"label_key": label_key, "title": label_title})

            normalized_groups.append({"group_key": group_key, "title": title, "labels": normalized_labels})

        return {"label_groups": normalized_groups}

    @staticmethod
    def normalize_classification_json(classification_json: dict | None) -> dict:
        if not isinstance(classification_json, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="classification_json must be an object")
        labels = classification_json.get("labels")
        if not isinstance(labels, list) or not labels:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="classification_json.labels must be a non-empty array")

        normalized_labels: list[dict] = []
        for label in labels:
            if not isinstance(label, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="classification_json.labels[] must be objects")
            group_key = label.get("group_key")
            label_key = label.get("label_key")
            notes = label.get("notes")
            if not isinstance(group_key, str) or not group_key.strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="classification_json.labels[].group_key is required")
            if not isinstance(label_key, str) or not label_key.strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="classification_json.labels[].label_key is required")
            if notes is not None and not isinstance(notes, str):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="classification_json.labels[].notes must be a string")
            normalized_label = {"group_key": group_key, "label_key": label_key}
            if notes is not None:
                normalized_label["notes"] = notes
            normalized_labels.append(normalized_label)
        return {"labels": normalized_labels}

    @staticmethod
    def _taxonomy_lookup(taxonomy_json: dict | None) -> dict[str, set[str]]:
        lookup: dict[str, set[str]] = {}
        if not isinstance(taxonomy_json, dict):
            return lookup
        for group in taxonomy_json.get("label_groups", []):
            if not isinstance(group, dict):
                continue
            group_key = group.get("group_key")
            if not isinstance(group_key, str):
                continue
            labels: set[str] = set()
            for label in group.get("labels", []):
                if isinstance(label, dict) and isinstance(label.get("label_key"), str):
                    labels.add(label["label_key"])
            lookup[group_key] = labels
        return lookup

    def _validate_classification_ids(
        self,
        *,
        organization_id: uuid.UUID,
        evidence_ids_json: list | None,
        control_ids_json: list | None,
        risk_ids_json: list | None,
    ) -> tuple[list[str] | None, list[str] | None, list[str] | None]:
        def _normalize_uuid_list(values: list | None, *, field_name: str) -> list[uuid.UUID] | None:
            if values is None:
                return None
            if not isinstance(values, list):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} must be an array")
            normalized: list[uuid.UUID] = []
            for value in values:
                if isinstance(value, uuid.UUID):
                    normalized.append(value)
                    continue
                if not isinstance(value, str):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} entries must be UUID strings")
                try:
                    normalized.append(uuid.UUID(value))
                except ValueError as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} contains invalid UUID") from exc
            return normalized

        evidence_ids = _normalize_uuid_list(evidence_ids_json, field_name="evidence_ids_json")
        control_ids = _normalize_uuid_list(control_ids_json, field_name="control_ids_json")
        risk_ids = _normalize_uuid_list(risk_ids_json, field_name="risk_ids_json")

        if evidence_ids is not None and evidence_ids:
            found = set(
                self.db.execute(
                    select(EvidenceItem.id).where(
                        EvidenceItem.organization_id == organization_id,
                        EvidenceItem.id.in_(evidence_ids),
                    )
                )
                .scalars()
                .all()
            )
            if len(found) != len(set(evidence_ids)):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="evidence_ids_json must contain same-org evidence IDs")

        if control_ids is not None and control_ids:
            found = set(
                self.db.execute(
                    select(Control.id).where(
                        Control.organization_id == organization_id,
                        Control.id.in_(control_ids),
                    )
                )
                .scalars()
                .all()
            )
            if len(found) != len(set(control_ids)):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="control_ids_json must contain same-org control IDs")

        if risk_ids is not None and risk_ids:
            found = set(
                self.db.execute(
                    select(Risk.id).where(
                        Risk.organization_id == organization_id,
                        Risk.id.in_(risk_ids),
                    )
                )
                .scalars()
                .all()
            )
            if len(found) != len(set(risk_ids)):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="risk_ids_json must contain same-org risk IDs")

        evidence_out = [str(item) for item in evidence_ids] if evidence_ids is not None else None
        control_out = [str(item) for item in control_ids] if control_ids is not None else None
        risk_out = [str(item) for item in risk_ids] if risk_ids is not None else None
        return evidence_out, control_out, risk_out

    @staticmethod
    def build_classification_summary(*, row: AISystemRiskClassificationRecord) -> dict:
        labels = row.classification_json.get("labels", []) if isinstance(row.classification_json, dict) else []
        by_label_group: dict[str, int] = {}
        label_pairs: list[dict] = []
        for label in labels:
            if not isinstance(label, dict):
                continue
            group_key = label.get("group_key")
            label_key = label.get("label_key")
            if not isinstance(group_key, str) or not isinstance(label_key, str):
                continue
            by_label_group[group_key] = by_label_group.get(group_key, 0) + 1
            label_pairs.append({"group_key": group_key, "label_key": label_key})
        label_pairs.sort(key=lambda item: (item["group_key"], item["label_key"]))
        return {
            "classification_id": str(row.id),
            "status": row.status,
            "review_status": row.review_status,
            "confidence_level": row.confidence_level,
            "source_type": row.source_type,
            "label_count": len(label_pairs),
            "by_label_group": by_label_group,
            "labels": label_pairs,
        }

    @staticmethod
    def calculate_with_profile(
        *,
        likelihood: str,
        impact: str,
        likelihood_weights_json: dict[str, int | None],
        impact_weights_json: dict[str, int | None],
        risk_level_thresholds_json: list[dict[str, int | str]],
    ) -> tuple[int | None, str | None, dict]:
        likelihood_weight = likelihood_weights_json.get(likelihood)
        impact_weight = impact_weights_json.get(impact)
        if likelihood_weight is None or impact_weight is None:
            explanation = {
                "algorithm": "manual_profile_weighted_v1",
                "likelihood": likelihood,
                "impact": impact,
                "likelihood_weight": likelihood_weight,
                "impact_weight": impact_weight,
                "score": None,
                "calculated_risk_level": None,
                "unknown_input": True,
                "thresholds": risk_level_thresholds_json,
            }
            return None, None, explanation

        score = int(likelihood_weight) * int(impact_weight)
        calculated_risk_level: str | None = None
        for threshold in risk_level_thresholds_json:
            min_score = int(threshold["min_score"])
            max_score = int(threshold["max_score"])
            if min_score <= score <= max_score:
                calculated_risk_level = str(threshold["risk_level"])
                break
        explanation = {
            "algorithm": "manual_profile_weighted_v1",
            "likelihood": likelihood,
            "impact": impact,
            "likelihood_weight": likelihood_weight,
            "impact_weight": impact_weight,
            "score": score,
            "calculated_risk_level": calculated_risk_level,
            "unknown_input": False,
            "thresholds": risk_level_thresholds_json,
        }
        return score, calculated_risk_level, explanation

    @staticmethod
    def profile_snapshot_json(profile: AISystemRiskScoringProfile) -> dict:
        return {
            "profile_id": str(profile.id),
            "name": profile.name,
            "status": profile.status,
            "methodology_version": profile.methodology_version,
            "likelihood_weights_json": profile.likelihood_weights_json,
            "impact_weights_json": profile.impact_weights_json,
            "risk_level_thresholds_json": profile.risk_level_thresholds_json,
            "is_default": profile.is_default,
        }

    @staticmethod
    def dimension_template_snapshot_json(template: AISystemRiskDimensionTemplate) -> dict:
        return {
            "template_id": str(template.id),
            "name": template.name,
            "status": template.status,
            "methodology_version": template.methodology_version,
            "dimension_weights_json": template.dimension_weights_json,
            "dimension_thresholds_json": template.dimension_thresholds_json,
            "is_default": template.is_default,
        }

    @staticmethod
    def classification_taxonomy_snapshot_json(template: AISystemRiskClassificationTaxonomyTemplate) -> dict:
        return {
            "taxonomy_template_id": str(template.id),
            "name": template.name,
            "status": template.status,
            "methodology_version": template.methodology_version,
            "taxonomy_json": template.taxonomy_json,
            "is_default": template.is_default,
        }

    def require_assessment(
        self,
        *,
        organization_id: uuid.UUID,
        assessment_id: uuid.UUID,
    ) -> AISystemRiskAssessment:
        row = self.db.execute(
            select(AISystemRiskAssessment).where(
                AISystemRiskAssessment.id == assessment_id,
                AISystemRiskAssessment.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk assessment not found")
        return row

    def require_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> AISystemRiskAssessmentSnapshot:
        row = self.db.execute(
            select(AISystemRiskAssessmentSnapshot).where(
                AISystemRiskAssessmentSnapshot.id == snapshot_id,
                AISystemRiskAssessmentSnapshot.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk assessment snapshot not found")
        return row

    def require_scoring_profile(
        self,
        *,
        organization_id: uuid.UUID,
        profile_id: uuid.UUID,
    ) -> AISystemRiskScoringProfile:
        row = self.db.execute(
            select(AISystemRiskScoringProfile).where(
                AISystemRiskScoringProfile.id == profile_id,
                AISystemRiskScoringProfile.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk scoring profile not found")
        return row

    def require_dimension_template(
        self,
        *,
        organization_id: uuid.UUID,
        template_id: uuid.UUID,
    ) -> AISystemRiskDimensionTemplate:
        row = self.db.execute(
            select(AISystemRiskDimensionTemplate).where(
                AISystemRiskDimensionTemplate.id == template_id,
                AISystemRiskDimensionTemplate.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk dimension template not found")
        return row

    def require_classification_taxonomy_template(
        self,
        *,
        organization_id: uuid.UUID,
        taxonomy_id: uuid.UUID,
    ) -> AISystemRiskClassificationTaxonomyTemplate:
        row = self.db.execute(
            select(AISystemRiskClassificationTaxonomyTemplate).where(
                AISystemRiskClassificationTaxonomyTemplate.id == taxonomy_id,
                AISystemRiskClassificationTaxonomyTemplate.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk classification taxonomy not found")
        return row

    def require_classification_record(
        self,
        *,
        organization_id: uuid.UUID,
        classification_id: uuid.UUID,
    ) -> AISystemRiskClassificationRecord:
        row = self.db.execute(
            select(AISystemRiskClassificationRecord).where(
                AISystemRiskClassificationRecord.id == classification_id,
                AISystemRiskClassificationRecord.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk classification record not found")
        return row

    def _unset_default_profiles(self, *, organization_id: uuid.UUID, exclude_profile_id: uuid.UUID | None) -> None:
        rows = (
            self.db.execute(
                select(AISystemRiskScoringProfile).where(
                    AISystemRiskScoringProfile.organization_id == organization_id,
                    AISystemRiskScoringProfile.is_default.is_(True),
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if exclude_profile_id is not None and row.id == exclude_profile_id:
                continue
            if row.status == "active":
                row.is_default = False

    def _unset_default_dimension_templates(
        self,
        *,
        organization_id: uuid.UUID,
        exclude_template_id: uuid.UUID | None,
    ) -> None:
        rows = (
            self.db.execute(
                select(AISystemRiskDimensionTemplate).where(
                    AISystemRiskDimensionTemplate.organization_id == organization_id,
                    AISystemRiskDimensionTemplate.is_default.is_(True),
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if exclude_template_id is not None and row.id == exclude_template_id:
                continue
            if row.status == "active":
                row.is_default = False

    def _unset_default_classification_taxonomies(
        self,
        *,
        organization_id: uuid.UUID,
        exclude_taxonomy_id: uuid.UUID | None,
    ) -> None:
        rows = (
            self.db.execute(
                select(AISystemRiskClassificationTaxonomyTemplate).where(
                    AISystemRiskClassificationTaxonomyTemplate.organization_id == organization_id,
                    AISystemRiskClassificationTaxonomyTemplate.is_default.is_(True),
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if exclude_taxonomy_id is not None and row.id == exclude_taxonomy_id:
                continue
            if row.status == "active":
                row.is_default = False

    def _require_active_profile_for_scoring(self, *, profile: AISystemRiskScoringProfile) -> None:
        if profile.status != "active" or profile.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scoring profile must be active and not archived")

    def _require_active_dimension_template(self, *, template: AISystemRiskDimensionTemplate) -> None:
        if template.status != "active" or template.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dimension template must be active and not archived")

    def _require_active_classification_taxonomy_template(
        self,
        *,
        template: AISystemRiskClassificationTaxonomyTemplate,
    ) -> None:
        if template.status != "active" or template.archived_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Classification taxonomy template must be active and not archived",
            )

    def resolve_default_scoring_profile(self, *, organization_id: uuid.UUID) -> AISystemRiskScoringProfile:
        row = self.db.execute(
            select(AISystemRiskScoringProfile).where(
                AISystemRiskScoringProfile.organization_id == organization_id,
                AISystemRiskScoringProfile.is_default.is_(True),
                AISystemRiskScoringProfile.status == "active",
                AISystemRiskScoringProfile.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active default scoring profile configured")
        return row

    def resolve_default_dimension_template(self, *, organization_id: uuid.UUID) -> AISystemRiskDimensionTemplate:
        row = self.db.execute(
            select(AISystemRiskDimensionTemplate).where(
                AISystemRiskDimensionTemplate.organization_id == organization_id,
                AISystemRiskDimensionTemplate.is_default.is_(True),
                AISystemRiskDimensionTemplate.status == "active",
                AISystemRiskDimensionTemplate.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active default dimension template configured")
        return row

    def resolve_default_classification_taxonomy_template(
        self,
        *,
        organization_id: uuid.UUID,
    ) -> AISystemRiskClassificationTaxonomyTemplate:
        row = self.db.execute(
            select(AISystemRiskClassificationTaxonomyTemplate).where(
                AISystemRiskClassificationTaxonomyTemplate.organization_id == organization_id,
                AISystemRiskClassificationTaxonomyTemplate.is_default.is_(True),
                AISystemRiskClassificationTaxonomyTemplate.status == "active",
                AISystemRiskClassificationTaxonomyTemplate.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active default classification taxonomy configured")
        return row

    def require_active_ai_system(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID,
    ) -> AISystem:
        ai_system = self.ai_system_service.require_ai_system_in_org(organization_id=organization_id, ai_system_id=ai_system_id)
        if ai_system.lifecycle_status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived AI systems cannot be risk-assessed")
        return ai_system

    def validate_owner_member(self, *, organization_id: uuid.UUID, owner_user_id: uuid.UUID | None) -> None:
        self.ai_system_service.ensure_active_member(
            organization_id=organization_id,
            user_id=owner_user_id,
            field_name="owner_user_id",
        )

    def create_assessment(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        title: str,
        description: str | None,
        assessment_type: str,
        status_value: str,
        owner_user_id: uuid.UUID | None,
        risk_level: str,
        likelihood: str,
        impact: str,
        risk_dimensions_json: dict | list | None,
        risk_factors_json: dict | list | None,
        mitigation_summary: str | None,
        assumptions: str | None,
        limitations: str | None,
        methodology_version: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskAssessment:
        self.require_active_ai_system(organization_id=organization_id, ai_system_id=ai_system_id)
        self.validate_owner_member(organization_id=organization_id, owner_user_id=owner_user_id)
        score = self.deterministic_score(likelihood=likelihood, impact=impact)

        row = AISystemRiskAssessment(
            organization_id=organization_id,
            ai_system_id=ai_system_id,
            title=title,
            description=description,
            assessment_type=assessment_type,
            status=status_value,
            owner_user_id=owner_user_id,
            risk_level=risk_level,
            likelihood=likelihood,
            impact=impact,
            inherent_risk_score=score,
            residual_risk_score=score,
            risk_dimensions_json=risk_dimensions_json,
            risk_factors_json=risk_factors_json,
            mitigation_summary=mitigation_summary,
            assumptions=assumptions,
            limitations=limitations,
            methodology_version=methodology_version,
            created_by_user_id=actor_user_id,
            scoring_profile_id=None,
            scoring_profile_snapshot_json=None,
            score_explanation_json=None,
            calculated_risk_level=None,
            dimension_template_id=None,
            latest_classification_id=None,
            classification_status=None,
            classification_summary_json=None,
            latest_classification_review_status=None,
            open_signal_count=0,
            dimension_template_snapshot_json=None,
            dimension_inputs_json=None,
            dimension_score_json=None,
            dimension_weighted_score=None,
            calculated_dimension_risk_level=None,
            residual_likelihood=None,
            residual_impact=None,
            calculated_residual_risk_level=None,
            residual_score_explanation_json=None,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def create_scoring_profile(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        likelihood_weights_json: dict | None,
        impact_weights_json: dict | None,
        risk_level_thresholds_json: list | None,
        methodology_version: str,
        is_default: bool,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskScoringProfile:
        status_value = validate_choice(status_value, PROFILE_STATUSES, "scoring profile status", status_code=status.HTTP_400_BAD_REQUEST)
        if is_default and status_value != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default scoring profile must be active")
        likelihood_weights, impact_weights, thresholds = self.normalize_scoring_profile_inputs(
            likelihood_weights_json=likelihood_weights_json,
            impact_weights_json=impact_weights_json,
            risk_level_thresholds_json=risk_level_thresholds_json,
        )

        row = AISystemRiskScoringProfile(
            organization_id=organization_id,
            name=name,
            description=description,
            status=status_value,
            is_default=is_default,
            likelihood_weights_json=likelihood_weights,
            impact_weights_json=impact_weights,
            risk_level_thresholds_json=thresholds,
            methodology_version=methodology_version or DEFAULT_PROFILE_METHODOLOGY_VERSION,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        if is_default:
            self._unset_default_profiles(organization_id=organization_id, exclude_profile_id=row.id)
        return row

    def list_scoring_profiles(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        include_archived: bool,
        is_default: bool | None,
        limit: int,
        offset: int,
    ) -> list[AISystemRiskScoringProfile]:
        stmt = select(AISystemRiskScoringProfile).where(AISystemRiskScoringProfile.organization_id == organization_id)
        if status_filter:
            stmt = stmt.where(AISystemRiskScoringProfile.status == status_filter)
        if is_default is not None:
            stmt = stmt.where(AISystemRiskScoringProfile.is_default.is_(is_default))
        if not include_archived:
            stmt = stmt.where(AISystemRiskScoringProfile.status != "archived")
        return (
            self.db.execute(stmt.order_by(AISystemRiskScoringProfile.created_at.desc()).offset(offset).limit(limit))
            .scalars()
            .all()
        )

    def update_scoring_profile(
        self,
        *,
        row: AISystemRiskScoringProfile,
        updates: dict,
    ) -> AISystemRiskScoringProfile:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived scoring profiles cannot be updated")

        new_status = str(updates.get("status", row.status))
        new_is_default = bool(updates.get("is_default", row.is_default))
        if new_status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use archive endpoint for scoring profiles")
        new_status = validate_choice(new_status, PROFILE_STATUSES, "scoring profile status", status_code=status.HTTP_400_BAD_REQUEST)
        if new_is_default and new_status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default scoring profile must be active")

        if "name" in updates:
            row.name = updates["name"]
        if "description" in updates:
            row.description = updates["description"]
        if "status" in updates:
            row.status = updates["status"]
        if "methodology_version" in updates:
            row.methodology_version = updates["methodology_version"]

        if (
            "likelihood_weights_json" in updates
            or "impact_weights_json" in updates
            or "risk_level_thresholds_json" in updates
        ):
            likelihood_weights, impact_weights, thresholds = self.normalize_scoring_profile_inputs(
                likelihood_weights_json=updates.get("likelihood_weights_json", row.likelihood_weights_json),
                impact_weights_json=updates.get("impact_weights_json", row.impact_weights_json),
                risk_level_thresholds_json=updates.get("risk_level_thresholds_json", row.risk_level_thresholds_json),
            )
            row.likelihood_weights_json = likelihood_weights
            row.impact_weights_json = impact_weights
            row.risk_level_thresholds_json = thresholds

        if "is_default" in updates:
            row.is_default = bool(updates["is_default"])
        if row.status != "active":
            row.is_default = False
        if row.is_default:
            self._unset_default_profiles(organization_id=row.organization_id, exclude_profile_id=row.id)

        self.db.flush()
        return row

    def archive_scoring_profile(
        self,
        *,
        row: AISystemRiskScoringProfile,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskScoringProfile:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scoring profile is already archived")
        if row.is_default:
            active_count = int(
                self.db.execute(
                    select(func.count(AISystemRiskScoringProfile.id)).where(
                        AISystemRiskScoringProfile.organization_id == row.organization_id,
                        AISystemRiskScoringProfile.status == "active",
                        AISystemRiskScoringProfile.archived_at.is_(None),
                        AISystemRiskScoringProfile.id != row.id,
                    )
                ).scalar_one()
            )
            if active_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Default scoring profile cannot be archived while other active profiles exist; set another default first",
                )
        row.status = "archived"
        row.is_default = False
        row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def set_default_scoring_profile(self, *, row: AISystemRiskScoringProfile) -> AISystemRiskScoringProfile:
        self._require_active_profile_for_scoring(profile=row)
        row.is_default = True
        self._unset_default_profiles(organization_id=row.organization_id, exclude_profile_id=row.id)
        self.db.flush()
        return row

    def preview_with_scoring_profile(
        self,
        *,
        profile: AISystemRiskScoringProfile,
        likelihood: str,
        impact: str,
    ) -> tuple[int | None, str | None, dict]:
        return self.calculate_with_profile(
            likelihood=likelihood,
            impact=impact,
            likelihood_weights_json=profile.likelihood_weights_json,
            impact_weights_json=profile.impact_weights_json,
            risk_level_thresholds_json=profile.risk_level_thresholds_json,
        )

    def recalculate_assessment_score(
        self,
        *,
        assessment: AISystemRiskAssessment,
        scoring_profile_id: uuid.UUID | None,
        apply_calculated_to_manual: bool,
    ) -> AISystemRiskAssessment:
        if assessment.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived risk assessments cannot be recalculated")

        profile = (
            self.resolve_default_scoring_profile(organization_id=assessment.organization_id)
            if scoring_profile_id is None
            else self.require_scoring_profile(organization_id=assessment.organization_id, profile_id=scoring_profile_id)
        )
        self._require_active_profile_for_scoring(profile=profile)

        score, calculated_level, explanation = self.preview_with_scoring_profile(
            profile=profile,
            likelihood=assessment.likelihood,
            impact=assessment.impact,
        )
        explanation["profile"] = self.profile_snapshot_json(profile)
        explanation["manual_risk_level"] = assessment.risk_level
        explanation["caveat"] = AI_RISK_SCORING_CAVEAT

        assessment.scoring_profile_id = profile.id
        assessment.scoring_profile_snapshot_json = self.profile_snapshot_json(profile)
        assessment.score_explanation_json = explanation
        assessment.calculated_risk_level = calculated_level
        assessment.inherent_risk_score = score
        if apply_calculated_to_manual and calculated_level is not None:
            assessment.risk_level = calculated_level
        self.db.flush()
        return assessment

    def create_dimension_template(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        dimension_weights_json: dict | None,
        dimension_thresholds_json: list | None,
        methodology_version: str,
        is_default: bool,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskDimensionTemplate:
        status_value = validate_choice(status_value, DIMENSION_TEMPLATE_STATUSES, "dimension template status", status_code=status.HTTP_400_BAD_REQUEST)
        if is_default and status_value != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default dimension template must be active")
        weights, thresholds = self.normalize_dimension_template_inputs(
            dimension_weights_json=dimension_weights_json,
            dimension_thresholds_json=dimension_thresholds_json,
        )

        row = AISystemRiskDimensionTemplate(
            organization_id=organization_id,
            name=name,
            description=description,
            status=status_value,
            is_default=is_default,
            dimension_weights_json=weights,
            dimension_thresholds_json=thresholds,
            methodology_version=methodology_version or DEFAULT_DIMENSION_TEMPLATE_METHODOLOGY_VERSION,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        if is_default:
            self._unset_default_dimension_templates(organization_id=organization_id, exclude_template_id=row.id)
        return row

    def list_dimension_templates(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        include_archived: bool,
        is_default: bool | None,
        limit: int,
        offset: int,
    ) -> list[AISystemRiskDimensionTemplate]:
        stmt = select(AISystemRiskDimensionTemplate).where(AISystemRiskDimensionTemplate.organization_id == organization_id)
        if status_filter:
            stmt = stmt.where(AISystemRiskDimensionTemplate.status == status_filter)
        if is_default is not None:
            stmt = stmt.where(AISystemRiskDimensionTemplate.is_default.is_(is_default))
        if not include_archived:
            stmt = stmt.where(AISystemRiskDimensionTemplate.status != "archived")
        return (
            self.db.execute(stmt.order_by(AISystemRiskDimensionTemplate.created_at.desc()).offset(offset).limit(limit))
            .scalars()
            .all()
        )

    def update_dimension_template(
        self,
        *,
        row: AISystemRiskDimensionTemplate,
        updates: dict,
    ) -> AISystemRiskDimensionTemplate:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived dimension templates cannot be updated")

        new_status = str(updates.get("status", row.status))
        new_is_default = bool(updates.get("is_default", row.is_default))
        if new_status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use archive endpoint for dimension templates")
        new_status = validate_choice(new_status, DIMENSION_TEMPLATE_STATUSES, "dimension template status", status_code=status.HTTP_400_BAD_REQUEST)
        if new_is_default and new_status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default dimension template must be active")

        if "name" in updates:
            row.name = updates["name"]
        if "description" in updates:
            row.description = updates["description"]
        if "status" in updates:
            row.status = updates["status"]
        if "methodology_version" in updates:
            row.methodology_version = updates["methodology_version"]

        if "dimension_weights_json" in updates or "dimension_thresholds_json" in updates:
            weights, thresholds = self.normalize_dimension_template_inputs(
                dimension_weights_json=updates.get("dimension_weights_json", row.dimension_weights_json),
                dimension_thresholds_json=updates.get("dimension_thresholds_json", row.dimension_thresholds_json),
            )
            row.dimension_weights_json = weights
            row.dimension_thresholds_json = thresholds

        if "is_default" in updates:
            row.is_default = bool(updates["is_default"])
        if row.status != "active":
            row.is_default = False
        if row.is_default:
            self._unset_default_dimension_templates(organization_id=row.organization_id, exclude_template_id=row.id)

        self.db.flush()
        return row

    def archive_dimension_template(
        self,
        *,
        row: AISystemRiskDimensionTemplate,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskDimensionTemplate:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dimension template is already archived")
        row.status = "archived"
        row.is_default = False
        row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def set_default_dimension_template(self, *, row: AISystemRiskDimensionTemplate) -> AISystemRiskDimensionTemplate:
        self._require_active_dimension_template(template=row)
        row.is_default = True
        self._unset_default_dimension_templates(organization_id=row.organization_id, exclude_template_id=row.id)
        self.db.flush()
        return row

    def create_classification_taxonomy_template(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        taxonomy_json: dict,
        methodology_version: str,
        is_default: bool,
        status_value: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskClassificationTaxonomyTemplate:
        status_value = validate_choice(status_value, CLASSIFICATION_TAXONOMY_STATUSES, "classification taxonomy status", status_code=status.HTTP_400_BAD_REQUEST)
        if is_default and status_value != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default taxonomy template must be active")
        normalized_taxonomy = self.normalize_classification_taxonomy_json(taxonomy_json)
        row = AISystemRiskClassificationTaxonomyTemplate(
            organization_id=organization_id,
            name=name,
            description=description,
            status=status_value,
            is_default=is_default,
            taxonomy_json=normalized_taxonomy,
            methodology_version=methodology_version or DEFAULT_CLASSIFICATION_METHODOLOGY_VERSION,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        if is_default:
            self._unset_default_classification_taxonomies(organization_id=organization_id, exclude_taxonomy_id=row.id)
        return row

    def list_classification_taxonomy_templates(
        self,
        *,
        organization_id: uuid.UUID,
        status_filter: str | None,
        include_archived: bool,
        is_default: bool | None,
        limit: int,
        offset: int,
    ) -> list[AISystemRiskClassificationTaxonomyTemplate]:
        stmt = select(AISystemRiskClassificationTaxonomyTemplate).where(
            AISystemRiskClassificationTaxonomyTemplate.organization_id == organization_id
        )
        if status_filter:
            stmt = stmt.where(AISystemRiskClassificationTaxonomyTemplate.status == status_filter)
        if is_default is not None:
            stmt = stmt.where(AISystemRiskClassificationTaxonomyTemplate.is_default.is_(is_default))
        if not include_archived:
            stmt = stmt.where(AISystemRiskClassificationTaxonomyTemplate.status != "archived")
        return (
            self.db.execute(
                stmt.order_by(AISystemRiskClassificationTaxonomyTemplate.created_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )

    def update_classification_taxonomy_template(
        self,
        *,
        row: AISystemRiskClassificationTaxonomyTemplate,
        updates: dict,
    ) -> AISystemRiskClassificationTaxonomyTemplate:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived classification taxonomies cannot be updated")

        new_status = str(updates.get("status", row.status))
        new_is_default = bool(updates.get("is_default", row.is_default))
        if new_status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use archive endpoint for classification taxonomies")
        new_status = validate_choice(new_status, CLASSIFICATION_TAXONOMY_STATUSES, "classification taxonomy status", status_code=status.HTTP_400_BAD_REQUEST)
        if new_is_default and new_status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default taxonomy template must be active")

        if "name" in updates:
            row.name = updates["name"]
        if "description" in updates:
            row.description = updates["description"]
        if "status" in updates:
            row.status = updates["status"]
        if "methodology_version" in updates:
            row.methodology_version = updates["methodology_version"]
        if "taxonomy_json" in updates:
            row.taxonomy_json = self.normalize_classification_taxonomy_json(updates["taxonomy_json"])
        if "is_default" in updates:
            row.is_default = bool(updates["is_default"])

        if row.status != "active":
            row.is_default = False
        if row.is_default:
            self._unset_default_classification_taxonomies(
                organization_id=row.organization_id,
                exclude_taxonomy_id=row.id,
            )
        self.db.flush()
        return row

    def archive_classification_taxonomy_template(
        self,
        *,
        row: AISystemRiskClassificationTaxonomyTemplate,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskClassificationTaxonomyTemplate:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Classification taxonomy is already archived")
        row.status = "archived"
        row.is_default = False
        row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def set_default_classification_taxonomy_template(
        self,
        *,
        row: AISystemRiskClassificationTaxonomyTemplate,
    ) -> AISystemRiskClassificationTaxonomyTemplate:
        self._require_active_classification_taxonomy_template(template=row)
        row.is_default = True
        self._unset_default_classification_taxonomies(organization_id=row.organization_id, exclude_taxonomy_id=row.id)
        self.db.flush()
        return row

    def preview_dimension_score(
        self,
        *,
        template: AISystemRiskDimensionTemplate,
        dimension_inputs_json: dict,
    ) -> tuple[float | None, str | None, dict]:
        self._require_active_dimension_template(template=template)
        weights = template.dimension_weights_json or {}
        thresholds = template.dimension_thresholds_json or []
        if not isinstance(dimension_inputs_json, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="dimension_inputs_json must be an object")

        details: list[dict] = []
        weighted_sum = 0.0
        included_weight = 0.0

        for dimension_key in sorted(dimension_inputs_json.keys()):
            if dimension_key not in RISK_DIMENSION_KEYS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown dimension key: {dimension_key}",
                )
            raw_value = dimension_inputs_json[dimension_key]
            level: str | None = None
            if isinstance(raw_value, dict):
                raw_level = raw_value.get("level")
                if raw_level is not None and not isinstance(raw_level, str):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"dimension_inputs_json.{dimension_key}.level must be a risk value string",
                    )
                level = raw_level
            elif isinstance(raw_value, str):
                level = raw_value
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"dimension_inputs_json.{dimension_key} must be an object with level or a level string",
                )
            if level not in RISK_VALUES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"dimension_inputs_json.{dimension_key}.level must be one of: {', '.join(RISK_VALUES)}",
                )

            dimension_weight = float(weights.get(dimension_key, 0))
            level_value = DIMENSION_LEVEL_VALUES.get(level) if level in DIMENSION_LEVEL_VALUES else None
            included = level_value is not None and dimension_weight > 0
            weighted_value: float | None = None
            if included and level_value is not None:
                weighted_value = round(level_value * dimension_weight, 6)
                weighted_sum += weighted_value
                included_weight += dimension_weight

            details.append(
                {
                    "dimension": dimension_key,
                    "level": level,
                    "level_value": level_value,
                    "weight": dimension_weight,
                    "weighted_value": weighted_value,
                    "included": included,
                }
            )

        weighted_score = round(weighted_sum / included_weight, 6) if included_weight > 0 else None
        calculated_level: str | None = None
        if weighted_score is not None:
            for threshold in thresholds:
                min_score = float(threshold["min_score"])
                max_score = float(threshold["max_score"])
                if min_score <= weighted_score <= max_score:
                    calculated_level = str(threshold["risk_level"])
                    break

        explanation = {
            "algorithm": "manual_dimension_weighted_v1",
            "dimension_count": len(dimension_inputs_json),
            "scored_dimension_count": sum(1 for item in details if item["included"]),
            "weighted_sum": round(weighted_sum, 6),
            "included_weight_sum": round(included_weight, 6),
            "dimension_weighted_score": weighted_score,
            "calculated_dimension_risk_level": calculated_level,
            "dimension_details": details,
            "thresholds": thresholds,
        }
        return weighted_score, calculated_level, explanation

    def apply_dimension_template(
        self,
        *,
        assessment: AISystemRiskAssessment,
        dimension_template_id: uuid.UUID | None,
        dimension_inputs_json: dict,
    ) -> AISystemRiskAssessment:
        if assessment.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived risk assessments cannot be updated")
        template = (
            self.resolve_default_dimension_template(organization_id=assessment.organization_id)
            if dimension_template_id is None
            else self.require_dimension_template(organization_id=assessment.organization_id, template_id=dimension_template_id)
        )
        self._require_active_dimension_template(template=template)

        weighted_score, calculated_level, explanation = self.preview_dimension_score(
            template=template,
            dimension_inputs_json=dimension_inputs_json,
        )
        explanation["template"] = self.dimension_template_snapshot_json(template)
        explanation["manual_risk_level"] = assessment.risk_level
        explanation["caveat"] = AI_RISK_DIMENSION_CAVEAT

        assessment.dimension_template_id = template.id
        assessment.dimension_template_snapshot_json = self.dimension_template_snapshot_json(template)
        assessment.dimension_inputs_json = dimension_inputs_json
        assessment.dimension_score_json = explanation
        assessment.dimension_weighted_score = weighted_score
        assessment.calculated_dimension_risk_level = calculated_level
        self.db.flush()
        return assessment

    def preview_residual_risk(
        self,
        *,
        assessment: AISystemRiskAssessment,
        residual_likelihood: str,
        residual_impact: str,
        scoring_profile_id: uuid.UUID | None,
    ) -> tuple[int | None, str | None, dict]:
        if scoring_profile_id is None and assessment.scoring_profile_id is not None:
            profile = self.require_scoring_profile(
                organization_id=assessment.organization_id,
                profile_id=assessment.scoring_profile_id,
            )
        elif scoring_profile_id is not None:
            profile = self.require_scoring_profile(
                organization_id=assessment.organization_id,
                profile_id=scoring_profile_id,
            )
        else:
            profile = self.resolve_default_scoring_profile(organization_id=assessment.organization_id)
        self._require_active_profile_for_scoring(profile=profile)

        score, calculated_level, explanation = self.preview_with_scoring_profile(
            profile=profile,
            likelihood=residual_likelihood,
            impact=residual_impact,
        )
        explanation["profile"] = self.profile_snapshot_json(profile)
        explanation["manual_risk_level"] = assessment.risk_level
        explanation["kind"] = "residual"
        explanation["caveat"] = AI_RISK_DIMENSION_CAVEAT
        return score, calculated_level, explanation

    def apply_residual_risk(
        self,
        *,
        assessment: AISystemRiskAssessment,
        residual_likelihood: str,
        residual_impact: str,
        scoring_profile_id: uuid.UUID | None,
    ) -> AISystemRiskAssessment:
        if assessment.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived risk assessments cannot be updated")

        score, calculated_level, explanation = self.preview_residual_risk(
            assessment=assessment,
            residual_likelihood=residual_likelihood,
            residual_impact=residual_impact,
            scoring_profile_id=scoring_profile_id,
        )
        assessment.residual_likelihood = residual_likelihood
        assessment.residual_impact = residual_impact
        assessment.residual_risk_score = score
        assessment.calculated_residual_risk_level = calculated_level
        assessment.residual_score_explanation_json = explanation
        self.db.flush()
        return assessment

    def create_classification_record(
        self,
        *,
        assessment: AISystemRiskAssessment,
        taxonomy_template_id: uuid.UUID | None,
        classification_json: dict,
        confidence_level: str,
        justification: str,
        source_type: str | None,
        source_reference: str | None,
        evidence_ids_json: list | None,
        control_ids_json: list | None,
        risk_ids_json: list | None,
        supersede_previous: bool,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskClassificationRecord:
        if assessment.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived risk assessments cannot accept classifications")

        confidence_level = validate_choice(confidence_level, CLASSIFICATION_CONFIDENCE_VALUES, "confidence_level", status_code=status.HTTP_400_BAD_REQUEST)
        if source_type is not None:
            source_type = validate_choice(source_type, CLASSIFICATION_SOURCE_TYPES, "source_type", status_code=status.HTTP_400_BAD_REQUEST)
        normalized_classification_json = self.normalize_classification_json(classification_json)
        normalized_evidence_ids, normalized_control_ids, normalized_risk_ids = self._validate_classification_ids(
            organization_id=assessment.organization_id,
            evidence_ids_json=evidence_ids_json,
            control_ids_json=control_ids_json,
            risk_ids_json=risk_ids_json,
        )

        taxonomy_template: AISystemRiskClassificationTaxonomyTemplate | None = None
        if taxonomy_template_id is None:
            taxonomy_template = self.db.execute(
                select(AISystemRiskClassificationTaxonomyTemplate).where(
                    AISystemRiskClassificationTaxonomyTemplate.organization_id == assessment.organization_id,
                    AISystemRiskClassificationTaxonomyTemplate.is_default.is_(True),
                    AISystemRiskClassificationTaxonomyTemplate.status == "active",
                    AISystemRiskClassificationTaxonomyTemplate.archived_at.is_(None),
                )
            ).scalar_one_or_none()
        else:
            taxonomy_template = self.require_classification_taxonomy_template(
                organization_id=assessment.organization_id,
                taxonomy_id=taxonomy_template_id,
            )

        taxonomy_snapshot_json: dict | None = None
        if taxonomy_template is not None:
            self._require_active_classification_taxonomy_template(template=taxonomy_template)
            taxonomy_lookup = self._taxonomy_lookup(taxonomy_template.taxonomy_json)
            for label in normalized_classification_json.get("labels", []):
                group_key = label["group_key"]
                label_key = label["label_key"]
                if group_key not in taxonomy_lookup or label_key not in taxonomy_lookup[group_key]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Classification label '{group_key}:{label_key}' is not defined in the taxonomy",
                    )
            taxonomy_snapshot_json = self.classification_taxonomy_snapshot_json(taxonomy_template)

        if supersede_previous:
            previous_active = (
                self.db.execute(
                    select(AISystemRiskClassificationRecord).where(
                        AISystemRiskClassificationRecord.organization_id == assessment.organization_id,
                        AISystemRiskClassificationRecord.risk_assessment_id == assessment.id,
                        AISystemRiskClassificationRecord.status == "active",
                    )
                )
                .scalars()
                .all()
            )
            for row in previous_active:
                row.status = "superseded"

        row = AISystemRiskClassificationRecord(
            organization_id=assessment.organization_id,
            ai_system_id=assessment.ai_system_id,
            risk_assessment_id=assessment.id,
            taxonomy_template_id=taxonomy_template.id if taxonomy_template is not None else None,
            taxonomy_template_snapshot_json=taxonomy_snapshot_json,
            classification_json=normalized_classification_json,
            status="active",
            review_status="not_submitted",
            confidence_level=confidence_level,
            justification=justification,
            source_type=source_type,
            source_reference=source_reference,
            evidence_ids_json=normalized_evidence_ids,
            control_ids_json=normalized_control_ids,
            risk_ids_json=normalized_risk_ids,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()

        assessment.latest_classification_id = row.id
        assessment.classification_status = row.status
        assessment.latest_classification_review_status = row.review_status
        assessment.classification_summary_json = self.build_classification_summary(row=row)
        assessment.open_signal_count = self.count_open_signals_for_assessment(assessment_id=assessment.id)
        self.db.flush()
        return row

    def list_classification_records(
        self,
        *,
        organization_id: uuid.UUID,
        assessment_id: uuid.UUID,
        status_filter: str | None,
        include_archived: bool,
        confidence_level: str | None,
    ) -> list[AISystemRiskClassificationRecord]:
        stmt = select(AISystemRiskClassificationRecord).where(
            AISystemRiskClassificationRecord.organization_id == organization_id,
            AISystemRiskClassificationRecord.risk_assessment_id == assessment_id,
        )
        if status_filter:
            stmt = stmt.where(AISystemRiskClassificationRecord.status == status_filter)
        if confidence_level:
            stmt = stmt.where(AISystemRiskClassificationRecord.confidence_level == confidence_level)
        if not include_archived:
            stmt = stmt.where(AISystemRiskClassificationRecord.status != "archived")
        return (
            self.db.execute(stmt.order_by(AISystemRiskClassificationRecord.created_at.desc()))
            .scalars()
            .all()
        )

    def _refresh_assessment_classification_metadata(self, *, assessment: AISystemRiskAssessment) -> None:
        latest = self.db.execute(
            select(AISystemRiskClassificationRecord)
            .where(
                AISystemRiskClassificationRecord.organization_id == assessment.organization_id,
                AISystemRiskClassificationRecord.risk_assessment_id == assessment.id,
            )
            .order_by(AISystemRiskClassificationRecord.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            assessment.latest_classification_id = None
            assessment.classification_status = None
            assessment.latest_classification_review_status = None
            assessment.classification_summary_json = None
        else:
            assessment.latest_classification_id = latest.id
            assessment.classification_status = latest.status
            assessment.latest_classification_review_status = latest.review_status
            assessment.classification_summary_json = self.build_classification_summary(row=latest)
        assessment.open_signal_count = self.count_open_signals_for_assessment(assessment_id=assessment.id)
        self.db.flush()

    def count_open_signals_for_assessment(self, *, assessment_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count(GovernanceSignal.id)).where(
                    GovernanceSignal.related_risk_assessment_id == assessment_id,
                    GovernanceSignal.status == "open",
                )
            ).scalar_one()
        )

    def count_open_signals_for_classification(self, *, classification_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count(GovernanceSignal.id)).where(
                    GovernanceSignal.entity_type == "risk_classification",
                    GovernanceSignal.entity_id == classification_id,
                    GovernanceSignal.status == "open",
                )
            ).scalar_one()
        )

    def archive_classification_record(
        self,
        *,
        row: AISystemRiskClassificationRecord,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskClassificationRecord:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Classification record is already archived")
        row.status = "archived"
        row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()

        assessment = self.require_assessment(organization_id=row.organization_id, assessment_id=row.risk_assessment_id)
        self._refresh_assessment_classification_metadata(assessment=assessment)
        return row

    def _next_classification_snapshot_version(self, *, organization_id: uuid.UUID, classification_id: uuid.UUID) -> int:
        current = self.db.execute(
            select(func.count(AISystemRiskClassificationRecordSnapshot.id)).where(
                AISystemRiskClassificationRecordSnapshot.organization_id == organization_id,
                AISystemRiskClassificationRecordSnapshot.classification_id == classification_id,
            )
        ).scalar_one()
        return int(current) + 1

    @staticmethod
    def _classification_snapshot_payload(
        *,
        row: AISystemRiskClassificationRecord,
        snapshot_type: str,
        snapshot_version: int,
        generated_at: datetime,
    ) -> dict:
        return {
            "snapshot_type": snapshot_type,
            "snapshot_version": snapshot_version,
            "generated_at": generated_at.isoformat(),
            "classification_record": {
                "id": str(row.id),
                "organization_id": str(row.organization_id),
                "ai_system_id": str(row.ai_system_id),
                "risk_assessment_id": str(row.risk_assessment_id),
                "taxonomy_template_id": str(row.taxonomy_template_id) if row.taxonomy_template_id else None,
                "taxonomy_template_snapshot_json": row.taxonomy_template_snapshot_json,
                "classification_json": row.classification_json,
                "status": row.status,
                "review_status": row.review_status,
                "confidence_level": row.confidence_level,
                "justification": row.justification,
                "source_type": row.source_type,
                "source_reference": row.source_reference,
                "evidence_ids_json": row.evidence_ids_json,
                "control_ids_json": row.control_ids_json,
                "risk_ids_json": row.risk_ids_json,
                "review_requested_at": row.review_requested_at.isoformat() if row.review_requested_at else None,
                "review_requested_by_user_id": str(row.review_requested_by_user_id)
                if row.review_requested_by_user_id
                else None,
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                "reviewed_by_user_id": str(row.reviewed_by_user_id) if row.reviewed_by_user_id else None,
                "review_note": row.review_note,
                "change_request_note": row.change_request_note,
                "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
                "rejected_by_user_id": str(row.rejected_by_user_id) if row.rejected_by_user_id else None,
                "rejection_reason": row.rejection_reason,
                "archived_at": row.archived_at.isoformat() if row.archived_at else None,
                "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
                "created_by_user_id": str(row.created_by_user_id) if row.created_by_user_id else None,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            },
            "taxonomy_snapshot": row.taxonomy_template_snapshot_json,
            "assessment_reference": {
                "risk_assessment_id": str(row.risk_assessment_id),
                "ai_system_id": str(row.ai_system_id),
            },
            "ai_system_reference": {
                "ai_system_id": str(row.ai_system_id),
            },
            "review_state": {
                "review_status": row.review_status,
                "review_requested_at": row.review_requested_at.isoformat() if row.review_requested_at else None,
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
            },
            "caveat": AI_RISK_CLASSIFICATION_CAVEAT,
        }

    def create_classification_snapshot(
        self,
        *,
        row: AISystemRiskClassificationRecord,
        snapshot_type: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskClassificationRecordSnapshot:
        snapshot_type = validate_choice(snapshot_type, CLASSIFICATION_SNAPSHOT_TYPES, "classification snapshot_type", status_code=status.HTTP_400_BAD_REQUEST)
        generated_at = self.now()
        snapshot_version = self._next_classification_snapshot_version(
            organization_id=row.organization_id,
            classification_id=row.id,
        )
        payload = self._classification_snapshot_payload(
            row=row,
            snapshot_type=snapshot_type,
            snapshot_version=snapshot_version,
            generated_at=generated_at,
        )
        snapshot = AISystemRiskClassificationRecordSnapshot(
            organization_id=row.organization_id,
            classification_id=row.id,
            risk_assessment_id=row.risk_assessment_id,
            ai_system_id=row.ai_system_id,
            snapshot_type=snapshot_type,
            snapshot_version=snapshot_version,
            snapshot_json=payload,
            snapshot_sha256=self.sha256_hexdigest(payload),
            created_by_user_id=actor_user_id,
        )
        self.db.add(snapshot)
        self.db.flush()
        return snapshot

    def list_classification_snapshots(
        self,
        *,
        organization_id: uuid.UUID,
        classification_id: uuid.UUID,
    ) -> list[AISystemRiskClassificationRecordSnapshot]:
        return (
            self.db.execute(
                select(AISystemRiskClassificationRecordSnapshot)
                .where(
                    AISystemRiskClassificationRecordSnapshot.organization_id == organization_id,
                    AISystemRiskClassificationRecordSnapshot.classification_id == classification_id,
                )
                .order_by(AISystemRiskClassificationRecordSnapshot.snapshot_version.desc())
            )
            .scalars()
            .all()
        )

    def require_classification_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> AISystemRiskClassificationRecordSnapshot:
        row = self.db.execute(
            select(AISystemRiskClassificationRecordSnapshot).where(
                AISystemRiskClassificationRecordSnapshot.id == snapshot_id,
                AISystemRiskClassificationRecordSnapshot.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI risk classification snapshot not found")
        return row

    def _create_signal(
        self,
        *,
        organization_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        related_ai_system_id: uuid.UUID | None,
        related_risk_assessment_id: uuid.UUID | None,
        signal_type: str,
        reason_code: str,
        severity: str,
        title: str,
        message: str,
        source_json: dict,
    ) -> GovernanceSignal:
        entity_type = validate_choice(entity_type, GOVERNANCE_SIGNAL_ENTITY_TYPE_VALUES, "governance signal entity_type", status_code=status.HTTP_400_BAD_REQUEST)
        severity = validate_choice(severity, GOVERNANCE_SIGNAL_SEVERITY_VALUES, "governance signal severity", status_code=status.HTTP_400_BAD_REQUEST)
        row = GovernanceSignal(
            organization_id=organization_id,
            domain="ai_risk",
            entity_type=entity_type,
            entity_id=entity_id,
            related_ai_system_id=related_ai_system_id,
            related_risk_assessment_id=related_risk_assessment_id,
            signal_type=signal_type,
            reason_code=reason_code,
            severity=severity,
            status="open",
            title=title,
            message=message,
            source_json=source_json,
            created_by_system=True,
        )
        self.db.add(row)
        self.db.flush()

        if related_risk_assessment_id:
            assessment = self.require_assessment(
                organization_id=organization_id,
                assessment_id=related_risk_assessment_id,
            )
            assessment.open_signal_count = self.count_open_signals_for_assessment(assessment_id=related_risk_assessment_id)
            self.db.flush()
        return row

    def _refresh_classification_signal_metadata(self, *, row: AISystemRiskClassificationRecord) -> None:
        assessment = self.require_assessment(organization_id=row.organization_id, assessment_id=row.risk_assessment_id)
        assessment.latest_classification_review_status = row.review_status
        assessment.open_signal_count = self.count_open_signals_for_assessment(assessment_id=assessment.id)
        self.db.flush()

    def submit_classification_for_review(
        self,
        *,
        row: AISystemRiskClassificationRecord,
        note: str | None,
        actor_user_id: uuid.UUID,
    ) -> tuple[AISystemRiskClassificationRecord, AISystemRiskClassificationRecordSnapshot, GovernanceSignal]:
        if row.status in ("archived", "superseded"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived or superseded classification records cannot be submitted for review",
            )
        if row.review_status not in ("not_submitted", "changes_requested"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Classification review_status must be not_submitted or changes_requested",
            )

        row.review_status = "in_review"
        row.review_requested_at = self.now()
        row.review_requested_by_user_id = actor_user_id
        row.review_note = note
        row.rejection_reason = None
        row.rejected_at = None
        row.rejected_by_user_id = None
        self.db.flush()

        snapshot = self.create_classification_snapshot(row=row, snapshot_type="review_snapshot", actor_user_id=actor_user_id)
        signal = self._create_signal(
            organization_id=row.organization_id,
            entity_type="risk_classification",
            entity_id=row.id,
            related_ai_system_id=row.ai_system_id,
            related_risk_assessment_id=row.risk_assessment_id,
            signal_type="classification_needs_review",
            reason_code="classification_needs_review",
            severity="warning",
            title="Classification requires review",
            message="Classification was submitted for manual governance review.",
            source_json={
                "classification_id": str(row.id),
                "risk_assessment_id": str(row.risk_assessment_id),
                "review_status": row.review_status,
                "rule": "submit_for_review",
                "note": note,
                "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
            },
        )
        self._refresh_classification_signal_metadata(row=row)
        return row, snapshot, signal

    def request_classification_changes(
        self,
        *,
        row: AISystemRiskClassificationRecord,
        change_request_note: str,
        actor_user_id: uuid.UUID,
    ) -> tuple[AISystemRiskClassificationRecord, AISystemRiskClassificationRecordSnapshot, GovernanceSignal]:
        if row.status in ("archived", "superseded"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived or superseded classification records cannot request changes",
            )
        row.review_status = "changes_requested"
        row.change_request_note = change_request_note
        row.reviewed_at = None
        row.reviewed_by_user_id = None
        row.rejection_reason = None
        row.rejected_at = None
        row.rejected_by_user_id = None
        self.db.flush()

        snapshot = self.create_classification_snapshot(
            row=row,
            snapshot_type="changes_requested_snapshot",
            actor_user_id=actor_user_id,
        )
        signal = self._create_signal(
            organization_id=row.organization_id,
            entity_type="risk_classification",
            entity_id=row.id,
            related_ai_system_id=row.ai_system_id,
            related_risk_assessment_id=row.risk_assessment_id,
            signal_type="classification_changes_requested",
            reason_code="classification_changes_requested",
            severity="warning",
            title="Classification changes requested",
            message="Classification has requested changes and requires follow-up.",
            source_json={
                "classification_id": str(row.id),
                "risk_assessment_id": str(row.risk_assessment_id),
                "review_status": row.review_status,
                "rule": "request_changes",
                "change_request_note": change_request_note,
                "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
            },
        )
        self._refresh_classification_signal_metadata(row=row)
        return row, snapshot, signal

    def mark_classification_reviewed(
        self,
        *,
        row: AISystemRiskClassificationRecord,
        review_note: str | None,
        actor_user_id: uuid.UUID,
    ) -> tuple[AISystemRiskClassificationRecord, AISystemRiskClassificationRecordSnapshot, GovernanceSignal]:
        if row.status in ("archived", "superseded"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived or superseded classification records cannot be reviewed",
            )
        row.review_status = "reviewed"
        row.reviewed_at = self.now()
        row.reviewed_by_user_id = actor_user_id
        row.review_note = review_note
        row.rejection_reason = None
        row.rejected_at = None
        row.rejected_by_user_id = None
        self.db.flush()

        snapshot = self.create_classification_snapshot(row=row, snapshot_type="review_snapshot", actor_user_id=actor_user_id)
        signal = self._create_signal(
            organization_id=row.organization_id,
            entity_type="risk_classification",
            entity_id=row.id,
            related_ai_system_id=row.ai_system_id,
            related_risk_assessment_id=row.risk_assessment_id,
            signal_type="classification_reviewed",
            reason_code="classification_reviewed",
            severity="info",
            title="Classification marked reviewed",
            message="Classification was manually marked reviewed.",
            source_json={
                "classification_id": str(row.id),
                "risk_assessment_id": str(row.risk_assessment_id),
                "review_status": row.review_status,
                "rule": "mark_reviewed",
                "review_note": review_note,
                "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
            },
        )
        self._refresh_classification_signal_metadata(row=row)
        return row, snapshot, signal

    def reject_classification(
        self,
        *,
        row: AISystemRiskClassificationRecord,
        rejection_reason: str,
        actor_user_id: uuid.UUID,
    ) -> tuple[AISystemRiskClassificationRecord, AISystemRiskClassificationRecordSnapshot, GovernanceSignal]:
        if row.status in ("archived", "superseded"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived or superseded classification records cannot be rejected",
            )
        row.review_status = "rejected"
        row.rejected_at = self.now()
        row.rejected_by_user_id = actor_user_id
        row.rejection_reason = rejection_reason
        self.db.flush()

        snapshot = self.create_classification_snapshot(row=row, snapshot_type="rejection_snapshot", actor_user_id=actor_user_id)
        signal = self._create_signal(
            organization_id=row.organization_id,
            entity_type="risk_classification",
            entity_id=row.id,
            related_ai_system_id=row.ai_system_id,
            related_risk_assessment_id=row.risk_assessment_id,
            signal_type="classification_rejected",
            reason_code="classification_rejected",
            severity="critical",
            title="Classification rejected",
            message="Classification was manually rejected and needs remediation.",
            source_json={
                "classification_id": str(row.id),
                "risk_assessment_id": str(row.risk_assessment_id),
                "review_status": row.review_status,
                "rule": "reject",
                "rejection_reason": rejection_reason,
                "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
            },
        )
        self._refresh_classification_signal_metadata(row=row)
        return row, snapshot, signal

    def list_governance_signals(
        self,
        *,
        organization_id: uuid.UUID,
        domain: str | None,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        related_ai_system_id: uuid.UUID | None,
        related_risk_assessment_id: uuid.UUID | None,
        signal_type: str | None,
        reason_code: str | None,
        severity: str | None,
        status_filter: str | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceSignal]:
        stmt = select(GovernanceSignal).where(GovernanceSignal.organization_id == organization_id)
        if domain:
            stmt = stmt.where(GovernanceSignal.domain == domain)
        if entity_type:
            stmt = stmt.where(GovernanceSignal.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(GovernanceSignal.entity_id == entity_id)
        if related_ai_system_id:
            stmt = stmt.where(GovernanceSignal.related_ai_system_id == related_ai_system_id)
        if related_risk_assessment_id:
            stmt = stmt.where(GovernanceSignal.related_risk_assessment_id == related_risk_assessment_id)
        if signal_type:
            stmt = stmt.where(GovernanceSignal.signal_type == signal_type)
        if reason_code:
            stmt = stmt.where(GovernanceSignal.reason_code == reason_code)
        if severity:
            stmt = stmt.where(GovernanceSignal.severity == severity)
        if status_filter:
            stmt = stmt.where(GovernanceSignal.status == status_filter)
        return (
            self.db.execute(stmt.order_by(GovernanceSignal.created_at.desc()).offset(offset).limit(limit))
            .scalars()
            .all()
        )

    def require_governance_signal(self, *, organization_id: uuid.UUID, signal_id: uuid.UUID) -> GovernanceSignal:
        row = self.db.execute(
            select(GovernanceSignal).where(
                GovernanceSignal.id == signal_id,
                GovernanceSignal.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Governance signal not found")
        return row

    def resolve_governance_signal(
        self,
        *,
        row: GovernanceSignal,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> GovernanceSignal:
        if row.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only open signals can be resolved")
        row.status = "resolved"
        row.resolved_at = self.now()
        row.resolved_by_user_id = actor_user_id
        row.resolve_reason = reason
        self.db.flush()
        if row.related_risk_assessment_id:
            assessment = self.require_assessment(organization_id=row.organization_id, assessment_id=row.related_risk_assessment_id)
            assessment.open_signal_count = self.count_open_signals_for_assessment(assessment_id=assessment.id)
            self.db.flush()
        return row

    def dismiss_governance_signal(
        self,
        *,
        row: GovernanceSignal,
        reason: str,
        actor_user_id: uuid.UUID,
    ) -> GovernanceSignal:
        if row.status != "open":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only open signals can be dismissed")
        row.status = "dismissed"
        row.dismissed_at = self.now()
        row.dismissed_by_user_id = actor_user_id
        row.dismiss_reason = reason
        self.db.flush()
        if row.related_risk_assessment_id:
            assessment = self.require_assessment(organization_id=row.organization_id, assessment_id=row.related_risk_assessment_id)
            assessment.open_signal_count = self.count_open_signals_for_assessment(assessment_id=assessment.id)
            self.db.flush()
        return row

    def governance_signal_summary(self, *, organization_id: uuid.UUID) -> dict:
        total_signals = int(
            self.db.execute(select(func.count(GovernanceSignal.id)).where(GovernanceSignal.organization_id == organization_id)).scalar_one()
        )
        open_signals = int(
            self.db.execute(
                select(func.count(GovernanceSignal.id)).where(
                    GovernanceSignal.organization_id == organization_id,
                    GovernanceSignal.status == "open",
                )
            ).scalar_one()
        )
        resolved_signals = int(
            self.db.execute(
                select(func.count(GovernanceSignal.id)).where(
                    GovernanceSignal.organization_id == organization_id,
                    GovernanceSignal.status == "resolved",
                )
            ).scalar_one()
        )
        dismissed_signals = int(
            self.db.execute(
                select(func.count(GovernanceSignal.id)).where(
                    GovernanceSignal.organization_id == organization_id,
                    GovernanceSignal.status == "dismissed",
                )
            ).scalar_one()
        )
        by_severity = {
            str(k): int(v)
            for k, v in self.db.execute(
                select(GovernanceSignal.severity, func.count(GovernanceSignal.id))
                .where(GovernanceSignal.organization_id == organization_id)
                .group_by(GovernanceSignal.severity)
            ).all()
        }
        by_signal_type = {
            str(k): int(v)
            for k, v in self.db.execute(
                select(GovernanceSignal.signal_type, func.count(GovernanceSignal.id))
                .where(GovernanceSignal.organization_id == organization_id)
                .group_by(GovernanceSignal.signal_type)
            ).all()
        }
        by_entity_type = {
            str(k): int(v)
            for k, v in self.db.execute(
                select(GovernanceSignal.entity_type, func.count(GovernanceSignal.id))
                .where(GovernanceSignal.organization_id == organization_id)
                .group_by(GovernanceSignal.entity_type)
            ).all()
        }
        latest_signal_at = self.db.execute(
            select(func.max(GovernanceSignal.created_at)).where(GovernanceSignal.organization_id == organization_id)
        ).scalar_one_or_none()
        return {
            "total_signals": total_signals,
            "open_signals": open_signals,
            "resolved_signals": resolved_signals,
            "dismissed_signals": dismissed_signals,
            "by_severity": by_severity,
            "by_signal_type": by_signal_type,
            "by_entity_type": by_entity_type,
            "latest_signal_at": latest_signal_at,
            "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
        }

    def _build_refresh_classification_signal_candidates(
        self,
        *,
        assessment: AISystemRiskAssessment,
    ) -> list[dict]:
        records = (
            self.db.execute(
                select(AISystemRiskClassificationRecord)
                .where(
                    AISystemRiskClassificationRecord.organization_id == assessment.organization_id,
                    AISystemRiskClassificationRecord.risk_assessment_id == assessment.id,
                    AISystemRiskClassificationRecord.status != "archived",
                )
                .order_by(AISystemRiskClassificationRecord.created_at.desc())
            )
            .scalars()
            .all()
        )
        active = [row for row in records if row.status == "active"]
        superseded = [row for row in records if row.status == "superseded"]

        candidates: list[dict] = []

        if not active:
            candidates.append(
                {
                    "entity_type": "risk_assessment",
                    "entity_id": str(assessment.id),
                    "signal_type": "assessment_missing_classification",
                    "reason_code": "assessment_missing_classification",
                    "severity": "warning",
                    "title": "Assessment missing active classification",
                    "message": "Risk assessment has no active classification record.",
                    "source_json": {
                        "risk_assessment_id": str(assessment.id),
                        "rule": "no_active_classification",
                        "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
                    },
                    "related_ai_system_id": str(assessment.ai_system_id),
                    "related_risk_assessment_id": str(assessment.id),
                }
            )

        if superseded and not active:
            candidates.append(
                {
                    "entity_type": "risk_assessment",
                    "entity_id": str(assessment.id),
                    "signal_type": "assessment_has_superseded_classification_only",
                    "reason_code": "assessment_has_superseded_classification_only",
                    "severity": "warning",
                    "title": "Assessment has only superseded classifications",
                    "message": "All classification records for this assessment are superseded.",
                    "source_json": {
                        "risk_assessment_id": str(assessment.id),
                        "rule": "superseded_only",
                        "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
                    },
                    "related_ai_system_id": str(assessment.ai_system_id),
                    "related_risk_assessment_id": str(assessment.id),
                }
            )

        for record in active:
            if record.review_status == "not_submitted":
                candidates.append(
                    {
                        "entity_type": "risk_classification",
                        "entity_id": str(record.id),
                        "signal_type": "classification_needs_review",
                        "reason_code": "classification_needs_review",
                        "severity": "warning",
                        "title": "Classification not submitted for review",
                        "message": "Active classification has review_status not_submitted.",
                        "source_json": {
                            "classification_id": str(record.id),
                            "review_status": record.review_status,
                            "rule": "review_not_submitted",
                            "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
                        },
                        "related_ai_system_id": str(record.ai_system_id),
                        "related_risk_assessment_id": str(record.risk_assessment_id),
                    }
                )
            if record.confidence_level == "low":
                candidates.append(
                    {
                        "entity_type": "risk_classification",
                        "entity_id": str(record.id),
                        "signal_type": "classification_low_confidence",
                        "reason_code": "classification_low_confidence",
                        "severity": "warning",
                        "title": "Classification confidence is low",
                        "message": "Active classification confidence level is low.",
                        "source_json": {
                            "classification_id": str(record.id),
                            "confidence_level": record.confidence_level,
                            "rule": "low_confidence",
                            "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
                        },
                        "related_ai_system_id": str(record.ai_system_id),
                        "related_risk_assessment_id": str(record.risk_assessment_id),
                    }
                )
            if record.review_status == "changes_requested":
                candidates.append(
                    {
                        "entity_type": "risk_classification",
                        "entity_id": str(record.id),
                        "signal_type": "classification_changes_requested",
                        "reason_code": "classification_changes_requested",
                        "severity": "warning",
                        "title": "Classification changes requested",
                        "message": "Active classification has changes requested.",
                        "source_json": {
                            "classification_id": str(record.id),
                            "review_status": record.review_status,
                            "rule": "changes_requested",
                            "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
                        },
                        "related_ai_system_id": str(record.ai_system_id),
                        "related_risk_assessment_id": str(record.risk_assessment_id),
                    }
                )
            if record.review_status == "rejected":
                candidates.append(
                    {
                        "entity_type": "risk_classification",
                        "entity_id": str(record.id),
                        "signal_type": "classification_rejected",
                        "reason_code": "classification_rejected",
                        "severity": "critical",
                        "title": "Classification rejected",
                        "message": "Active classification has review_status rejected.",
                        "source_json": {
                            "classification_id": str(record.id),
                            "review_status": record.review_status,
                            "rule": "rejected",
                            "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
                        },
                        "related_ai_system_id": str(record.ai_system_id),
                        "related_risk_assessment_id": str(record.risk_assessment_id),
                    }
                )
            if not (record.evidence_ids_json and len(record.evidence_ids_json) > 0):
                candidates.append(
                    {
                        "entity_type": "risk_classification",
                        "entity_id": str(record.id),
                        "signal_type": "classification_has_unlinked_evidence",
                        "reason_code": "classification_has_unlinked_evidence",
                        "severity": "info",
                        "title": "Classification has no evidence references",
                        "message": "Active classification does not reference evidence IDs.",
                        "source_json": {
                            "classification_id": str(record.id),
                            "evidence_count": 0,
                            "rule": "no_evidence_links",
                            "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
                        },
                        "related_ai_system_id": str(record.ai_system_id),
                        "related_risk_assessment_id": str(record.risk_assessment_id),
                    }
                )

        candidates.sort(key=lambda item: (item["reason_code"], item["entity_type"], item["entity_id"]))
        return candidates

    def _governance_signal_query(
        self,
        *,
        organization_id: uuid.UUID,
        domain: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        related_ai_system_id: uuid.UUID | None = None,
        related_risk_assessment_id: uuid.UUID | None = None,
        signal_type: str | None = None,
        reason_code: str | None = None,
        severity: str | None = None,
        status_filter: str | None = None,
    ):
        stmt = select(GovernanceSignal).where(GovernanceSignal.organization_id == organization_id)
        if domain:
            stmt = stmt.where(GovernanceSignal.domain == domain)
        if entity_type:
            stmt = stmt.where(GovernanceSignal.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(GovernanceSignal.entity_id == entity_id)
        if related_ai_system_id:
            stmt = stmt.where(GovernanceSignal.related_ai_system_id == related_ai_system_id)
        if related_risk_assessment_id:
            stmt = stmt.where(GovernanceSignal.related_risk_assessment_id == related_risk_assessment_id)
        if signal_type:
            stmt = stmt.where(GovernanceSignal.signal_type == signal_type)
        if reason_code:
            stmt = stmt.where(GovernanceSignal.reason_code == reason_code)
        if severity:
            stmt = stmt.where(GovernanceSignal.severity == severity)
        if status_filter:
            stmt = stmt.where(GovernanceSignal.status == status_filter)
        return stmt

    @staticmethod
    def _priority_base_severity_weight(severity: str) -> int:
        return {"info": 10, "warning": 40, "critical": 80}.get(severity, 0)

    @staticmethod
    def _priority_age_weight(age_days: int) -> int:
        if age_days <= 0:
            return 0
        if age_days <= 3:
            return 5
        if age_days <= 7:
            return 10
        if age_days <= 14:
            return 20
        return 30

    @staticmethod
    def _priority_risk_context_weight(assessment: AISystemRiskAssessment | None) -> int:
        if assessment is None:
            return 0
        weight = 0
        weight += {
            "critical": 25,
            "high": 18,
            "medium": 10,
            "low": 3,
        }.get(assessment.risk_level, 0)
        weight += {
            "critical": 25,
            "high": 18,
        }.get(assessment.calculated_residual_risk_level or "", 0)
        weight += {
            "critical": 15,
            "high": 10,
        }.get(assessment.calculated_dimension_risk_level or "", 0)
        return weight

    @staticmethod
    def _priority_band(priority_score: float) -> str:
        if priority_score <= 24:
            return "low"
        if priority_score <= 59:
            return "medium"
        if priority_score <= 99:
            return "high"
        return "urgent"

    @staticmethod
    def _signal_group_key(row: GovernanceSignal) -> str:
        if row.related_ai_system_id is not None:
            return f"ai_system:{row.related_ai_system_id}"
        return f"{row.entity_type}:{row.entity_id}"

    def _signal_density_open_counts(
        self,
        *,
        organization_id: uuid.UUID,
    ) -> dict[uuid.UUID, int]:
        rows = self.db.execute(
            select(GovernanceSignal.related_ai_system_id, func.count(GovernanceSignal.id))
            .where(
                GovernanceSignal.organization_id == organization_id,
                GovernanceSignal.status == "open",
                GovernanceSignal.related_ai_system_id.is_not(None),
            )
            .group_by(GovernanceSignal.related_ai_system_id)
        ).all()
        return {ai_system_id: int(count) for ai_system_id, count in rows if ai_system_id is not None}

    def _assessment_context_map(
        self,
        *,
        organization_id: uuid.UUID,
        assessment_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, AISystemRiskAssessment]:
        if not assessment_ids:
            return {}
        rows = (
            self.db.execute(
                select(AISystemRiskAssessment).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.id.in_(assessment_ids),
                )
            )
            .scalars()
            .all()
        )
        return {row.id: row for row in rows}

    def _priority_payload_for_signal(
        self,
        *,
        row: GovernanceSignal,
        now: datetime,
        assessment: AISystemRiskAssessment | None,
        open_density_count: int,
    ) -> dict:
        created_at = row.created_at
        effective_now = now if created_at.tzinfo else now.replace(tzinfo=None)
        age_days = max(0, int((effective_now - created_at).total_seconds() // 86400))
        base_weight = self._priority_base_severity_weight(row.severity)
        age_weight = self._priority_age_weight(age_days)
        risk_context_weight = self._priority_risk_context_weight(assessment)
        density_weight = min(open_density_count * 3, 20) if open_density_count > 1 else 0
        total = min(float(base_weight + age_weight + risk_context_weight + density_weight), 150.0)
        band = self._priority_band(total)
        explanation = {
            "base_severity_weight": base_weight,
            "age_weight": age_weight,
            "entity_risk_context_weight": risk_context_weight,
            "signal_density_weight": density_weight,
            "source_fields": {
                "severity": row.severity,
                "created_at": created_at.isoformat() if created_at else None,
                "related_risk_assessment_id": str(row.related_risk_assessment_id) if row.related_risk_assessment_id else None,
                "assessment_manual_risk_level": assessment.risk_level if assessment else None,
                "assessment_calculated_residual_risk_level": assessment.calculated_residual_risk_level if assessment else None,
                "assessment_calculated_dimension_risk_level": assessment.calculated_dimension_risk_level if assessment else None,
                "related_ai_system_open_signal_count": open_density_count,
            },
            "algorithm": "governance_signal_priority_v1",
        }
        return {
            "signal_id": row.id,
            "signal_type": row.signal_type,
            "reason_code": row.reason_code,
            "severity": row.severity,
            "status": row.status,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "related_ai_system_id": row.related_ai_system_id,
            "related_risk_assessment_id": row.related_risk_assessment_id,
            "priority_score": total,
            "priority_band": band,
            "priority_explanation_json": explanation,
            "age_days": age_days,
            "group_key": self._signal_group_key(row),
            "created_at": row.created_at,
            "caveat": AI_RISK_GOVERNANCE_SIGNAL_PRIORITY_CAVEAT,
        }

    def _compute_prioritized_governance_signals(
        self,
        *,
        organization_id: uuid.UUID,
        domain: str | None = None,
        entity_type: str | None = None,
        related_ai_system_id: uuid.UUID | None = None,
        related_risk_assessment_id: uuid.UUID | None = None,
        signal_type: str | None = None,
        reason_code: str | None = None,
        severity: str | None = None,
        status_filter: str | None = "open",
        priority_band: str | None = None,
    ) -> list[dict]:
        rows = (
            self.db.execute(
                self._governance_signal_query(
                    organization_id=organization_id,
                    domain=domain,
                    entity_type=entity_type,
                    related_ai_system_id=related_ai_system_id,
                    related_risk_assessment_id=related_risk_assessment_id,
                    signal_type=signal_type,
                    reason_code=reason_code,
                    severity=severity,
                    status_filter=status_filter,
                )
            )
            .scalars()
            .all()
        )
        density_counts = self._signal_density_open_counts(organization_id=organization_id)
        assessment_ids = [row.related_risk_assessment_id for row in rows if row.related_risk_assessment_id is not None]
        assessment_map = self._assessment_context_map(organization_id=organization_id, assessment_ids=assessment_ids)
        now = self.now()

        prioritized = [
            self._priority_payload_for_signal(
                row=row,
                now=now,
                assessment=assessment_map.get(row.related_risk_assessment_id) if row.related_risk_assessment_id else None,
                open_density_count=density_counts.get(row.related_ai_system_id, 0) if row.related_ai_system_id else 0,
            )
            for row in rows
        ]
        if priority_band:
            prioritized = [row for row in prioritized if row["priority_band"] == priority_band]
        prioritized.sort(
            key=lambda item: (
                -float(item["priority_score"]),
                item["created_at"],
                str(item["signal_id"]),
            )
        )
        return prioritized

    def list_prioritized_governance_signals(
        self,
        *,
        organization_id: uuid.UUID,
        domain: str | None,
        entity_type: str | None,
        related_ai_system_id: uuid.UUID | None,
        related_risk_assessment_id: uuid.UUID | None,
        signal_type: str | None,
        reason_code: str | None,
        severity: str | None,
        status_filter: str | None,
        priority_band: str | None,
        limit: int,
        offset: int,
    ) -> list[dict]:
        prioritized = self._compute_prioritized_governance_signals(
            organization_id=organization_id,
            domain=domain,
            entity_type=entity_type,
            related_ai_system_id=related_ai_system_id,
            related_risk_assessment_id=related_risk_assessment_id,
            signal_type=signal_type,
            reason_code=reason_code,
            severity=severity,
            status_filter=status_filter,
            priority_band=priority_band,
        )
        return prioritized[offset : offset + limit]

    def governance_signal_groups(
        self,
        *,
        organization_id: uuid.UUID,
        domain: str | None,
        related_ai_system_id: uuid.UUID | None,
        related_risk_assessment_id: uuid.UUID | None,
        status_filter: str | None,
        limit: int,
        offset: int,
    ) -> list[dict]:
        prioritized = self._compute_prioritized_governance_signals(
            organization_id=organization_id,
            domain=domain,
            related_ai_system_id=related_ai_system_id,
            related_risk_assessment_id=related_risk_assessment_id,
            status_filter=status_filter,
        )
        grouped: dict[str, dict] = {}
        for item in prioritized:
            key = str(item["group_key"])
            if key not in grouped:
                group_title = (
                    f"AI System {item['related_ai_system_id']}"
                    if item["related_ai_system_id"] is not None
                    else f"{item['entity_type']} {item['entity_id']}"
                )
                grouped[key] = {
                    "group_key": key,
                    "group_title": group_title,
                    "related_ai_system_id": item["related_ai_system_id"],
                    "related_risk_assessment_id": item["related_risk_assessment_id"],
                    "signal_count": 0,
                    "highest_priority_score": float(item["priority_score"]),
                    "highest_priority_band": item["priority_band"],
                    "severities_count": {},
                    "reason_codes_count": {},
                    "signals": [],
                    "caveat": AI_RISK_GOVERNANCE_SIGNAL_PRIORITY_CAVEAT,
                }
            group = grouped[key]
            group["signal_count"] += 1
            severity_key = str(item["severity"])
            reason_key = str(item["reason_code"])
            group["severities_count"][severity_key] = int(group["severities_count"].get(severity_key, 0) + 1)
            group["reason_codes_count"][reason_key] = int(group["reason_codes_count"].get(reason_key, 0) + 1)
            group["signals"].append(item)
        ordered = sorted(
            grouped.values(),
            key=lambda item: (-float(item["highest_priority_score"]), -int(item["signal_count"]), str(item["group_key"])),
        )
        return ordered[offset : offset + limit]

    def ai_system_attention_view(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID,
    ) -> dict:
        self.ai_system_service.require_ai_system_in_org(organization_id=organization_id, ai_system_id=ai_system_id)
        prioritized = self._compute_prioritized_governance_signals(
            organization_id=organization_id,
            related_ai_system_id=ai_system_id,
            status_filter="open",
        )
        latest_assessment = self.db.execute(
            select(AISystemRiskAssessment)
            .where(
                AISystemRiskAssessment.organization_id == organization_id,
                AISystemRiskAssessment.ai_system_id == ai_system_id,
            )
            .order_by(AISystemRiskAssessment.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        by_band: dict[str, int] = {}
        by_reason: dict[str, int] = {}
        for item in prioritized:
            band = str(item["priority_band"])
            by_band[band] = int(by_band.get(band, 0) + 1)
            reason = str(item["reason_code"])
            by_reason[reason] = int(by_reason.get(reason, 0) + 1)
        top_reasons = sorted(by_reason.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[:5]
        return {
            "ai_system_id": ai_system_id,
            "open_signal_count": len(prioritized),
            "highest_priority_score": float(prioritized[0]["priority_score"]) if prioritized else 0.0,
            "highest_priority_band": str(prioritized[0]["priority_band"]) if prioritized else "low",
            "top_signals": prioritized[:10],
            "latest_risk_assessment_id": latest_assessment.id if latest_assessment else None,
            "latest_manual_risk_level": latest_assessment.risk_level if latest_assessment else None,
            "latest_calculated_residual_risk_level": (
                latest_assessment.calculated_residual_risk_level if latest_assessment else None
            ),
            "attention_summary": {
                "by_priority_band": by_band,
                "top_reason_codes": [{"reason_code": key, "count": value} for key, value in top_reasons],
                "algorithm": "governance_signal_priority_v1",
            },
            "caveat": AI_RISK_GOVERNANCE_SIGNAL_PRIORITY_CAVEAT,
        }

    def governance_signal_priority_summary(self, *, organization_id: uuid.UUID) -> dict:
        prioritized = self._compute_prioritized_governance_signals(
            organization_id=organization_id,
            status_filter="open",
        )
        by_priority_band: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        grouped_ai: dict[uuid.UUID, list[dict]] = {}
        for item in prioritized:
            band = str(item["priority_band"])
            by_priority_band[band] = int(by_priority_band.get(band, 0) + 1)
            sev = str(item["severity"])
            by_severity[sev] = int(by_severity.get(sev, 0) + 1)
            ai_system_id = item.get("related_ai_system_id")
            if ai_system_id is not None:
                grouped_ai.setdefault(ai_system_id, []).append(item)
        top_ai = []
        for ai_system_id, signals in grouped_ai.items():
            top_ai.append(
                {
                    "ai_system_id": str(ai_system_id),
                    "open_signal_count": len(signals),
                    "highest_priority_score": float(signals[0]["priority_score"]),
                    "highest_priority_band": signals[0]["priority_band"],
                }
            )
        top_ai.sort(
            key=lambda item: (
                -float(item["highest_priority_score"]),
                -int(item["open_signal_count"]),
                str(item["ai_system_id"]),
            )
        )
        oldest_open_signal_at = prioritized[-1]["created_at"] if prioritized else None
        return {
            "total_open_signals": len(prioritized),
            "by_priority_band": by_priority_band,
            "by_severity": by_severity,
            "urgent_signal_count": int(by_priority_band.get("urgent", 0)),
            "high_signal_count": int(by_priority_band.get("high", 0)),
            "top_ai_systems_by_attention": top_ai[:10],
            "oldest_open_signal_at": oldest_open_signal_at,
            "caveat": AI_RISK_GOVERNANCE_SIGNAL_PRIORITY_CAVEAT,
        }

    def governance_signal_priority_explanation(
        self,
        *,
        organization_id: uuid.UUID,
        signal_id: uuid.UUID,
    ) -> dict:
        signal = self.require_governance_signal(organization_id=organization_id, signal_id=signal_id)
        prioritized = self._compute_prioritized_governance_signals(
            organization_id=organization_id,
            domain=signal.domain,
            entity_type=signal.entity_type,
            related_ai_system_id=signal.related_ai_system_id,
            related_risk_assessment_id=signal.related_risk_assessment_id,
            signal_type=signal.signal_type,
            reason_code=signal.reason_code,
            severity=signal.severity,
            status_filter=signal.status,
        )
        payload = next((item for item in prioritized if item["signal_id"] == signal.id), None)
        if payload is None:
            payload = self._priority_payload_for_signal(
                row=signal,
                now=self.now(),
                assessment=None,
                open_density_count=0,
            )
        explanation = payload["priority_explanation_json"]
        return {
            "signal_id": signal.id,
            "base_severity_weight": int(explanation["base_severity_weight"]),
            "age_weight": int(explanation["age_weight"]),
            "entity_risk_context_weight": int(explanation["entity_risk_context_weight"]),
            "signal_density_weight": int(explanation["signal_density_weight"]),
            "total_priority_score": float(payload["priority_score"]),
            "priority_band": str(payload["priority_band"]),
            "source_fields": explanation["source_fields"],
            "caveat": AI_RISK_GOVERNANCE_SIGNAL_PRIORITY_CAVEAT,
        }

    @classmethod
    def governance_action_template_catalog(cls) -> list[dict[str, Any]]:
        rows = []
        for item in GOVERNANCE_CANDIDATE_ACTION_TEMPLATES:
            payload = dict(item)
            payload["source_reason_codes"] = sorted(str(code) for code in payload["source_reason_codes"])
            payload["caveat"] = AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT
            rows.append(payload)
        rows.sort(key=lambda row: str(row["action_key"]))
        return rows

    @classmethod
    def _action_template_by_reason_code(cls) -> dict[str, dict[str, Any]]:
        mapping: dict[str, dict[str, Any]] = {}
        for template in GOVERNANCE_CANDIDATE_ACTION_TEMPLATES:
            for reason_code in template["source_reason_codes"]:
                mapping[str(reason_code)] = dict(template)
        return mapping

    @staticmethod
    def _candidate_priority_band_rank(priority_band: str) -> int:
        return {"low": 1, "medium": 2, "high": 3, "urgent": 4}.get(priority_band, 0)

    @staticmethod
    def _candidate_target_id_for_sort(value: uuid.UUID | None) -> tuple[int, str]:
        if value is None:
            return (1, "")
        return (0, str(value))

    @classmethod
    def classify_candidate_action_risk_tier(
        cls,
        *,
        action_key: str,
        action_type: str,
    ) -> str:
        key = str(action_key or "").strip().lower()
        action_type_normalized = str(action_type or "").strip().lower()
        low_keys = {"flag_stale_evidence", "send_reminder", "refresh_signals"}
        high_keys = {
            "close_risk",
            "delete_evidence",
            "delete_control",
            "delete_record",
            "purge_record",
            "archive_record",
            "revoke_access",
        }
        destructive_tokens = ("delete", "remove", "purge", "revoke", "destroy", "close")
        if key in low_keys:
            return "low"
        if key in high_keys or any(token in key for token in destructive_tokens):
            return "high"
        if action_type_normalized in {"attach_evidence", "review_record", "refresh_signals"}:
            return "low"
        if action_type_normalized in {"update_record", "create_record"}:
            return "medium"
        if action_type_normalized in {"resolve_issue", "create_snapshot", "prepare_draft"}:
            return "medium"
        return "high"

    def _candidate_actions_from_prioritized_signals(
        self,
        *,
        prioritized_signals: list[dict[str, Any]],
        reason_code_filter: str | None,
        action_type_filter: str | None,
    ) -> list[dict[str, Any]]:
        template_map = self._action_template_by_reason_code()
        grouped: dict[tuple[str, str, uuid.UUID | None], dict[str, Any]] = {}
        for signal in prioritized_signals:
            reason_code = str(signal["reason_code"])
            template = template_map.get(reason_code)
            if template is None:
                continue
            target_entity_type = str(template["target_entity_type"])
            if target_entity_type == "risk_assessment":
                target_entity_id = signal.get("related_risk_assessment_id")
            elif target_entity_type == "ai_system":
                target_entity_id = signal.get("related_ai_system_id")
            else:
                target_entity_id = signal.get("entity_id")
            group_key = (str(template["action_key"]), target_entity_type, target_entity_id)

            if group_key not in grouped:
                grouped[group_key] = {
                    "action_key": str(template["action_key"]),
                    "title": str(template["title"]),
                    "description": str(template["description"]),
                    "action_type": str(template["action_type"]),
                    "priority_score": float(signal["priority_score"]),
                    "priority_band": str(signal["priority_band"]),
                    "source_signal_ids": [signal["signal_id"]],
                    "source_reason_codes": {reason_code},
                    "target_entity_type": target_entity_type,
                    "target_entity_id": target_entity_id,
                    "related_ai_system_id": signal.get("related_ai_system_id"),
                    "related_risk_assessment_id": signal.get("related_risk_assessment_id"),
                    "human_approval_required": bool(template["human_approval_required"]),
                    "automation_allowed": bool(template["automation_allowed"]),
                    "risk_tier": self.classify_candidate_action_risk_tier(
                        action_key=str(template["action_key"]),
                        action_type=str(template["action_type"]),
                    ),
                    "confidence_score": AUTOPILOT_DEFAULT_CONFIDENCE_SCORE,
                    "target_route_hint": template.get("target_route_hint"),
                    "caveat": AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT,
                }
            group = grouped[group_key]
            group["source_signal_ids"].append(signal["signal_id"])
            group["source_reason_codes"].add(reason_code)

            if float(signal["priority_score"]) > float(group["priority_score"]):
                group["priority_score"] = float(signal["priority_score"])
                group["priority_band"] = str(signal["priority_band"])

        rows: list[dict[str, Any]] = []
        for group in grouped.values():
            source_signal_ids = sorted({str(signal_id) for signal_id in group["source_signal_ids"]})
            source_reason_codes = sorted(str(code) for code in group["source_reason_codes"])
            rationale_json = {
                "source_signal_count": len(source_signal_ids),
                "source_signal_ids": source_signal_ids,
                "source_reason_codes": source_reason_codes,
                "highest_source_priority_score": float(group["priority_score"]),
                "algorithm": "governance_candidate_actions_v1",
            }
            rationale = (
                f"Derived from {len(source_signal_ids)} open signal(s): {', '.join(source_reason_codes)}. "
                "Suggested as deterministic next-best-attention action."
            )
            rows.append(
                {
                    "action_key": group["action_key"],
                    "title": group["title"],
                    "description": group["description"],
                    "action_type": group["action_type"],
                    "priority_score": float(group["priority_score"]),
                    "priority_band": str(group["priority_band"]),
                    "source_signal_ids": [uuid.UUID(signal_id) for signal_id in source_signal_ids],
                    "source_reason_codes": source_reason_codes,
                    "target_entity_type": group["target_entity_type"],
                    "target_entity_id": group["target_entity_id"],
                    "related_ai_system_id": group["related_ai_system_id"],
                    "related_risk_assessment_id": group["related_risk_assessment_id"],
                    "rationale": rationale,
                    "rationale_json": rationale_json,
                    "human_approval_required": bool(group["human_approval_required"]),
                    "automation_allowed": bool(group["automation_allowed"]),
                    "risk_tier": str(group["risk_tier"]),
                    "confidence_score": float(group["confidence_score"]),
                    "target_route_hint": group.get("target_route_hint"),
                    "caveat": AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT,
                }
            )

        if reason_code_filter:
            rows = [row for row in rows if reason_code_filter in row["source_reason_codes"]]
        if action_type_filter:
            rows = [row for row in rows if row["action_type"] == action_type_filter]

        rows.sort(
            key=lambda item: (
                -float(item["priority_score"]),
                -int(self._candidate_priority_band_rank(str(item["priority_band"]))),
                str(item["action_key"]),
                self._candidate_target_id_for_sort(item.get("target_entity_id")),
            )
        )
        return rows

    def list_candidate_actions(
        self,
        *,
        organization_id: uuid.UUID,
        related_ai_system_id: uuid.UUID | None,
        related_risk_assessment_id: uuid.UUID | None,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        priority_band: str | None,
        action_type: str | None,
        reason_code: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        prioritized = self._compute_prioritized_governance_signals(
            organization_id=organization_id,
            entity_type=entity_type,
            related_ai_system_id=related_ai_system_id,
            related_risk_assessment_id=related_risk_assessment_id,
            status_filter="open",
            priority_band=priority_band,
        )
        if entity_id is not None:
            prioritized = [row for row in prioritized if row["entity_id"] == entity_id]

        candidates = self._candidate_actions_from_prioritized_signals(
            prioritized_signals=prioritized,
            reason_code_filter=reason_code,
            action_type_filter=action_type,
        )
        return candidates[offset : offset + limit]

    def ai_system_candidate_actions(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID,
    ) -> dict[str, Any]:
        self.ai_system_service.require_ai_system_in_org(organization_id=organization_id, ai_system_id=ai_system_id)
        actions = self.list_candidate_actions(
            organization_id=organization_id,
            related_ai_system_id=ai_system_id,
            related_risk_assessment_id=None,
            entity_type=None,
            entity_id=None,
            priority_band=None,
            action_type=None,
            reason_code=None,
            limit=500,
            offset=0,
        )
        highest_priority_band = str(actions[0]["priority_band"]) if actions else "low"
        return {
            "ai_system_id": ai_system_id,
            "candidate_action_count": len(actions),
            "highest_priority_band": highest_priority_band,
            "actions": actions,
            "caveat": AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT,
        }

    def risk_assessment_candidate_actions(
        self,
        *,
        organization_id: uuid.UUID,
        assessment_id: uuid.UUID,
    ) -> dict[str, Any]:
        self.require_assessment(organization_id=organization_id, assessment_id=assessment_id)
        actions = self.list_candidate_actions(
            organization_id=organization_id,
            related_ai_system_id=None,
            related_risk_assessment_id=assessment_id,
            entity_type=None,
            entity_id=None,
            priority_band=None,
            action_type=None,
            reason_code=None,
            limit=500,
            offset=0,
        )
        highest_priority_band = str(actions[0]["priority_band"]) if actions else "low"
        return {
            "assessment_id": assessment_id,
            "candidate_action_count": len(actions),
            "highest_priority_band": highest_priority_band,
            "actions": actions,
            "caveat": AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT,
        }

    def candidate_action_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        actions = self.list_candidate_actions(
            organization_id=organization_id,
            related_ai_system_id=None,
            related_risk_assessment_id=None,
            entity_type=None,
            entity_id=None,
            priority_band=None,
            action_type=None,
            reason_code=None,
            limit=2000,
            offset=0,
        )
        by_action_type: dict[str, int] = {}
        by_priority_band: dict[str, int] = {}
        by_action_key: dict[str, int] = {}
        ai_counts: dict[uuid.UUID, int] = {}
        for row in actions:
            action_type = str(row["action_type"])
            band = str(row["priority_band"])
            action_key = str(row["action_key"])
            by_action_type[action_type] = int(by_action_type.get(action_type, 0) + 1)
            by_priority_band[band] = int(by_priority_band.get(band, 0) + 1)
            by_action_key[action_key] = int(by_action_key.get(action_key, 0) + 1)
            ai_system_id = row.get("related_ai_system_id")
            if ai_system_id is not None:
                ai_counts[ai_system_id] = int(ai_counts.get(ai_system_id, 0) + 1)

        top_action_keys = [
            {"action_key": key, "count": count}
            for key, count in sorted(by_action_key.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[:10]
        ]
        top_ai_systems = [
            {"ai_system_id": str(ai_system_id), "action_count": count}
            for ai_system_id, count in sorted(ai_counts.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[:10]
        ]
        return {
            "total_candidate_actions": len(actions),
            "by_action_type": by_action_type,
            "by_priority_band": by_priority_band,
            "top_action_keys": top_action_keys,
            "top_ai_systems_by_action_count": top_ai_systems,
            "caveat": AI_RISK_GOVERNANCE_CANDIDATE_ACTION_CAVEAT,
        }

    @staticmethod
    def _serialize_json_value(value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [AISystemRiskAssessmentService._serialize_json_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): AISystemRiskAssessmentService._serialize_json_value(val) for key, val in value.items()}
        return value

    def _recommendation_scope_context(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        scope_type = validate_choice(scope_type, GOVERNANCE_RECOMMENDATION_SCOPE_TYPES, "scope_type", status_code=status.HTTP_400_BAD_REQUEST)
        if scope_type == "organization":
            if scope_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_id must be null for organization scope",
                )
            return (None, None)
        if scope_type == "ai_system":
            if scope_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_id is required for ai_system scope",
                )
            self.ai_system_service.require_ai_system_in_org(organization_id=organization_id, ai_system_id=scope_id)
            return (scope_id, None)
        if scope_type == "risk_assessment":
            if scope_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="scope_id is required for risk_assessment scope",
                )
            assessment = self.require_assessment(organization_id=organization_id, assessment_id=scope_id)
            return (assessment.ai_system_id, assessment.id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope_type")

    def _candidate_actions_for_recommendation_scope(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        priority_band: str | None,
        action_type: str | None,
        reason_code: str | None,
    ) -> list[dict[str, Any]]:
        related_ai_system_id, related_risk_assessment_id = self._recommendation_scope_context(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        return self.list_candidate_actions(
            organization_id=organization_id,
            related_ai_system_id=related_ai_system_id,
            related_risk_assessment_id=related_risk_assessment_id,
            entity_type=None,
            entity_id=None,
            priority_band=priority_band,
            action_type=action_type,
            reason_code=reason_code,
            limit=2000,
            offset=0,
        )

    def _recommendation_payload_and_hashes(
        self,
        *,
        scope_type: str,
        scope_id: uuid.UUID | None,
        actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        serialized_actions = [self._serialize_json_value(item) for item in actions]
        source_signal_ids = sorted(
            {
                str(signal_id)
                for item in serialized_actions
                for signal_id in item.get("source_signal_ids", [])
                if signal_id is not None
            }
        )
        by_priority_band: dict[str, int] = {}
        by_action_type: dict[str, int] = {}
        top_action_keys: dict[str, int] = {}
        for item in serialized_actions:
            band = str(item.get("priority_band") or "low")
            action_type = str(item.get("action_type") or "")
            action_key = str(item.get("action_key") or "")
            by_priority_band[band] = int(by_priority_band.get(band, 0) + 1)
            if action_type:
                by_action_type[action_type] = int(by_action_type.get(action_type, 0) + 1)
            if action_key:
                top_action_keys[action_key] = int(top_action_keys.get(action_key, 0) + 1)
        priority_summary = {
            "by_priority_band": by_priority_band,
            "by_action_type": by_action_type,
            "top_action_keys": [
                {"action_key": key, "count": count}
                for key, count in sorted(top_action_keys.items(), key=lambda kv: (-int(kv[1]), str(kv[0])))[:10]
            ],
        }
        generated_at = self.now().isoformat()
        recommendation_payload = {
            "generated_at": generated_at,
            "scope_type": scope_type,
            "scope_id": str(scope_id) if scope_id else None,
            "candidate_actions": serialized_actions,
            "priority_summary": priority_summary,
            "caveat": AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT,
        }
        source_candidate_hash = self.sha256_hexdigest(
            {
                "scope_type": scope_type,
                "scope_id": str(scope_id) if scope_id else None,
                "candidate_actions": serialized_actions,
            }
        )
        snapshot_sha256 = self.sha256_hexdigest(recommendation_payload)
        return {
            "recommendation_payload_json": recommendation_payload,
            "source_signal_ids_json": source_signal_ids,
            "source_candidate_hash": source_candidate_hash,
            "snapshot_sha256": snapshot_sha256,
        }

    @staticmethod
    def _candidate_action_identity(action: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(action.get("action_key") or ""),
            str(action.get("target_entity_type") or ""),
            str(action.get("target_entity_id") or ""),
        )

    def _recommendation_diff_from_payloads(
        self,
        *,
        base_payload: dict | list,
        compare_payload: dict | list,
    ) -> dict[str, Any]:
        base_actions = list((base_payload or {}).get("candidate_actions", [])) if isinstance(base_payload, dict) else []
        compare_actions = (
            list((compare_payload or {}).get("candidate_actions", [])) if isinstance(compare_payload, dict) else []
        )

        base_map = {self._candidate_action_identity(item): item for item in base_actions}
        compare_map = {self._candidate_action_identity(item): item for item in compare_actions}
        base_keys = set(base_map.keys())
        compare_keys = set(compare_map.keys())

        added_actions = [compare_map[key] for key in sorted(compare_keys - base_keys)]
        removed_actions = [base_map[key] for key in sorted(base_keys - compare_keys)]
        changed_actions: list[dict[str, Any]] = []
        unchanged_action_count = 0
        for key in sorted(base_keys & compare_keys):
            before = base_map[key]
            after = compare_map[key]
            if before == after:
                unchanged_action_count += 1
                continue
            changed_actions.append({"identity": {"action_key": key[0], "target_entity_type": key[1], "target_entity_id": key[2] or None}, "before": before, "after": after})

        return {
            "added_actions": added_actions,
            "removed_actions": removed_actions,
            "changed_actions": changed_actions,
            "unchanged_action_count": unchanged_action_count,
            "algorithm": "governance_recommendation_snapshot_diff_v1",
        }

    def preview_recommendation_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        priority_band: str | None,
        action_type: str | None,
        reason_code: str | None,
    ) -> dict[str, Any]:
        actions = self._candidate_actions_for_recommendation_scope(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            priority_band=priority_band,
            action_type=action_type,
            reason_code=reason_code,
        )
        payload = self._recommendation_payload_and_hashes(scope_type=scope_type, scope_id=scope_id, actions=actions)
        return {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "candidate_count": len(actions),
            "recommendation_payload_json": payload["recommendation_payload_json"],
            "source_signal_ids": [uuid.UUID(value) for value in payload["source_signal_ids_json"]],
            "source_candidate_hash": payload["source_candidate_hash"],
            "caveat": AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT,
        }

    def create_recommendation_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
        priority_band: str | None,
        action_type: str | None,
        reason_code: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceRecommendationSnapshot:
        actions = self._candidate_actions_for_recommendation_scope(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            priority_band=priority_band,
            action_type=action_type,
            reason_code=reason_code,
        )
        payload = self._recommendation_payload_and_hashes(scope_type=scope_type, scope_id=scope_id, actions=actions)

        previous = self.db.execute(
            select(GovernanceRecommendationSnapshot)
            .where(
                GovernanceRecommendationSnapshot.organization_id == organization_id,
                GovernanceRecommendationSnapshot.scope_type == scope_type,
                GovernanceRecommendationSnapshot.scope_id == scope_id,
            )
            .order_by(
                GovernanceRecommendationSnapshot.snapshot_version.desc(),
                GovernanceRecommendationSnapshot.created_at.desc(),
                GovernanceRecommendationSnapshot.id.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()

        snapshot_version = 1 if previous is None else int(previous.snapshot_version + 1)
        diff_from_previous_json = None
        if previous is not None:
            diff_from_previous_json = self._recommendation_diff_from_payloads(
                base_payload=previous.recommendation_payload_json,
                compare_payload=payload["recommendation_payload_json"],
            )

        row = GovernanceRecommendationSnapshot(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            source_type="candidate_actions",
            candidate_count=len(actions),
            recommendation_payload_json=payload["recommendation_payload_json"],
            source_signal_ids_json=payload["source_signal_ids_json"],
            source_candidate_hash=payload["source_candidate_hash"],
            snapshot_sha256=payload["snapshot_sha256"],
            snapshot_version=snapshot_version,
            previous_snapshot_id=previous.id if previous else None,
            diff_from_previous_json=diff_from_previous_json,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_recommendation_snapshots(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str | None,
        scope_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceRecommendationSnapshot]:
        query = select(GovernanceRecommendationSnapshot).where(
            GovernanceRecommendationSnapshot.organization_id == organization_id
        )
        if scope_type is not None:
            scope_type = validate_choice(scope_type, GOVERNANCE_RECOMMENDATION_SCOPE_TYPES, "scope_type", status_code=status.HTTP_400_BAD_REQUEST)
            query = query.where(GovernanceRecommendationSnapshot.scope_type == scope_type)
        if scope_id is not None:
            query = query.where(GovernanceRecommendationSnapshot.scope_id == scope_id)
        query = query.order_by(GovernanceRecommendationSnapshot.created_at.desc(), GovernanceRecommendationSnapshot.id.desc())
        query = query.offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def require_recommendation_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> GovernanceRecommendationSnapshot:
        row = self.db.execute(
            select(GovernanceRecommendationSnapshot).where(
                GovernanceRecommendationSnapshot.organization_id == organization_id,
                GovernanceRecommendationSnapshot.id == snapshot_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation snapshot not found")
        return row

    def diff_recommendation_snapshots(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        compare_to_snapshot_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        base = self.require_recommendation_snapshot(organization_id=organization_id, snapshot_id=snapshot_id)
        if compare_to_snapshot_id is not None:
            compare = self.require_recommendation_snapshot(
                organization_id=organization_id,
                snapshot_id=compare_to_snapshot_id,
            )
        else:
            if base.previous_snapshot_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No previous snapshot available for this scope",
                )
            compare = self.require_recommendation_snapshot(
                organization_id=organization_id,
                snapshot_id=base.previous_snapshot_id,
            )
        diff = self._recommendation_diff_from_payloads(
            base_payload=compare.recommendation_payload_json,
            compare_payload=base.recommendation_payload_json,
        )
        return {
            "base_snapshot_id": base.id,
            "compare_snapshot_id": compare.id,
            "added_actions": diff["added_actions"],
            "removed_actions": diff["removed_actions"],
            "changed_actions": diff["changed_actions"],
            "unchanged_action_count": int(diff["unchanged_action_count"]),
            "caveat": AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT,
        }

    def latest_recommendation_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID | None,
    ) -> GovernanceRecommendationSnapshot:
        _ = self._recommendation_scope_context(organization_id=organization_id, scope_type=scope_type, scope_id=scope_id)
        row = self.db.execute(
            select(GovernanceRecommendationSnapshot)
            .where(
                GovernanceRecommendationSnapshot.organization_id == organization_id,
                GovernanceRecommendationSnapshot.scope_type == scope_type,
                GovernanceRecommendationSnapshot.scope_id == scope_id,
            )
            .order_by(
                GovernanceRecommendationSnapshot.snapshot_version.desc(),
                GovernanceRecommendationSnapshot.created_at.desc(),
                GovernanceRecommendationSnapshot.id.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation snapshot not found")
        return row

    def recommendation_snapshot_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        rows = list(
            self.db.execute(
                select(
                    GovernanceRecommendationSnapshot.scope_type,
                    func.count(GovernanceRecommendationSnapshot.id),
                ).where(
                    GovernanceRecommendationSnapshot.organization_id == organization_id
                ).group_by(
                    GovernanceRecommendationSnapshot.scope_type
                )
            ).all()
        )
        by_scope_type = {str(scope): int(count) for scope, count in rows}
        total_snapshots = int(sum(by_scope_type.values()))
        latest_snapshot_at = self.db.execute(
            select(func.max(GovernanceRecommendationSnapshot.created_at)).where(
                GovernanceRecommendationSnapshot.organization_id == organization_id
            )
        ).scalar_one()
        distinct_scopes = {
            (row.scope_type, row.scope_id)
            for row in self.db.execute(
                select(GovernanceRecommendationSnapshot.scope_type, GovernanceRecommendationSnapshot.scope_id).where(
                    GovernanceRecommendationSnapshot.organization_id == organization_id
                )
            ).all()
        }
        scopes_with_snapshots = len(distinct_scopes)
        return {
            "total_snapshots": total_snapshots,
            "by_scope_type": by_scope_type,
            "latest_snapshot_at": latest_snapshot_at,
            "scopes_with_snapshots": scopes_with_snapshots,
            "caveat": AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT,
        }

    @classmethod
    def recommendation_action_identity_hash(cls, action: dict[str, Any]) -> str:
        identity = {
            "action_key": str(action.get("action_key") or ""),
            "target_entity_type": str(action.get("target_entity_type") or ""),
            "target_entity_id": str(action.get("target_entity_id")) if action.get("target_entity_id") else "",
            "related_ai_system_id": str(action.get("related_ai_system_id")) if action.get("related_ai_system_id") else "",
            "related_risk_assessment_id": str(action.get("related_risk_assessment_id"))
            if action.get("related_risk_assessment_id")
            else "",
        }
        return cls.sha256_hexdigest(identity)

    def _snapshot_candidate_actions_with_identity(
        self,
        *,
        snapshot: GovernanceRecommendationSnapshot,
    ) -> list[dict[str, Any]]:
        payload = snapshot.recommendation_payload_json if isinstance(snapshot.recommendation_payload_json, dict) else {}
        actions = payload.get("candidate_actions") if isinstance(payload, dict) else []
        rows: list[dict[str, Any]] = []
        for item in (actions or []):
            if not isinstance(item, dict):
                continue
            action = dict(item)
            action["action_identity_hash"] = self.recommendation_action_identity_hash(action)
            action["caveat"] = AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT
            rows.append(action)
        rows.sort(
            key=lambda row: (
                -float(row.get("priority_score") or 0.0),
                -int(self._candidate_priority_band_rank(str(row.get("priority_band") or "low"))),
                str(row.get("action_key") or ""),
                self._candidate_target_id_for_sort(row.get("target_entity_id")),
            )
        )
        return rows

    def _list_action_dispositions_for_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
    ) -> list[GovernanceRecommendationActionDisposition]:
        return list(
            self.db.execute(
                select(GovernanceRecommendationActionDisposition)
                .where(
                    GovernanceRecommendationActionDisposition.organization_id == organization_id,
                    GovernanceRecommendationActionDisposition.recommendation_snapshot_id == snapshot_id,
                )
                .order_by(
                    GovernanceRecommendationActionDisposition.updated_at.desc(),
                    GovernanceRecommendationActionDisposition.id.desc(),
                )
            )
            .scalars()
            .all()
        )

    def list_snapshot_actions(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        include_dispositions: bool,
    ) -> dict[str, Any]:
        snapshot = self.require_recommendation_snapshot(organization_id=organization_id, snapshot_id=snapshot_id)
        actions = self._snapshot_candidate_actions_with_identity(snapshot=snapshot)
        disposition_by_hash: dict[str, dict[str, Any]] = {}
        if include_dispositions:
            for row in self._list_action_dispositions_for_snapshot(
                organization_id=organization_id,
                snapshot_id=snapshot.id,
            ):
                disposition_by_hash[row.action_identity_hash] = self.recommendation_action_disposition_payload(row=row)

        out_actions: list[dict[str, Any]] = []
        for action in actions:
            payload = dict(action)
            if include_dispositions:
                payload["disposition"] = disposition_by_hash.get(payload["action_identity_hash"])
            out_actions.append(payload)
        return {
            "snapshot_id": snapshot.id,
            "action_count": len(out_actions),
            "actions": out_actions,
            "caveat": AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT,
        }

    @staticmethod
    def recommendation_action_disposition_payload(
        *,
        row: GovernanceRecommendationActionDisposition,
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "disposition_id": row.id,
            "recommendation_snapshot_id": row.recommendation_snapshot_id,
            "action_identity_hash": row.action_identity_hash,
            "action_key": row.action_key,
            "target_entity_type": row.target_entity_type,
            "target_entity_id": row.target_entity_id,
            "related_ai_system_id": row.related_ai_system_id,
            "related_risk_assessment_id": row.related_risk_assessment_id,
            "disposition_status": row.disposition_status,
            "note": row.note,
            "reason": row.reason,
            "deferred_until": row.deferred_until,
            "created_by_user_id": row.created_by_user_id,
            "updated_by_user_id": row.updated_by_user_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "caveat": AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT,
        }

    def _require_snapshot_action(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        action_identity_hash: str,
    ) -> tuple[GovernanceRecommendationSnapshot, dict[str, Any]]:
        snapshot = self.require_recommendation_snapshot(organization_id=organization_id, snapshot_id=snapshot_id)
        actions = self._snapshot_candidate_actions_with_identity(snapshot=snapshot)
        action = next((item for item in actions if item["action_identity_hash"] == action_identity_hash), None)
        if action is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation action not found in snapshot")
        return snapshot, action

    def upsert_recommendation_action_disposition(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        action_identity_hash: str,
        disposition_status: str,
        note: str | None,
        reason: str | None,
        deferred_until: datetime | None,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceRecommendationActionDisposition:
        disposition_status = validate_choice(disposition_status, GOVERNANCE_RECOMMENDATION_DISPOSITION_STATUS_VALUES, "disposition_status", status_code=status.HTTP_400_BAD_REQUEST)
        _, action = self._require_snapshot_action(
            organization_id=organization_id,
            snapshot_id=snapshot_id,
            action_identity_hash=action_identity_hash,
        )
        row = self.db.execute(
            select(GovernanceRecommendationActionDisposition).where(
                GovernanceRecommendationActionDisposition.organization_id == organization_id,
                GovernanceRecommendationActionDisposition.recommendation_snapshot_id == snapshot_id,
                GovernanceRecommendationActionDisposition.action_identity_hash == action_identity_hash,
            )
        ).scalar_one_or_none()
        if row is None:
            target_entity_id = action.get("target_entity_id")
            related_ai_system_id = action.get("related_ai_system_id")
            related_risk_assessment_id = action.get("related_risk_assessment_id")
            target_entity_uuid = uuid.UUID(target_entity_id) if target_entity_id else None
            related_ai_system_uuid = uuid.UUID(related_ai_system_id) if related_ai_system_id else None
            related_risk_assessment_uuid = (
                uuid.UUID(related_risk_assessment_id) if related_risk_assessment_id else None
            )
            row = GovernanceRecommendationActionDisposition(
                organization_id=organization_id,
                recommendation_snapshot_id=snapshot_id,
                action_identity_hash=action_identity_hash,
                action_key=str(action.get("action_key") or ""),
                target_entity_type=str(action.get("target_entity_type")) if action.get("target_entity_type") else None,
                target_entity_id=target_entity_uuid,
                related_ai_system_id=related_ai_system_uuid,
                related_risk_assessment_id=related_risk_assessment_uuid,
                disposition_status=disposition_status,
                note=note,
                reason=reason,
                deferred_until=deferred_until,
                created_by_user_id=actor_user_id,
                updated_by_user_id=actor_user_id,
            )
            self.db.add(row)
        else:
            row.disposition_status = disposition_status
            row.note = note
            row.reason = reason
            row.deferred_until = deferred_until
            row.updated_by_user_id = actor_user_id
        self.db.flush()
        return row

    def list_recommendation_action_dispositions(
        self,
        *,
        organization_id: uuid.UUID,
        snapshot_id: uuid.UUID | None,
        disposition_status: str | None,
        action_key: str | None,
        related_ai_system_id: uuid.UUID | None,
        related_risk_assessment_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceRecommendationActionDisposition]:
        if snapshot_id is not None:
            self.require_recommendation_snapshot(organization_id=organization_id, snapshot_id=snapshot_id)
        if disposition_status is not None:
            disposition_status = validate_choice(disposition_status, GOVERNANCE_RECOMMENDATION_DISPOSITION_STATUS_VALUES, "disposition_status", status_code=status.HTTP_400_BAD_REQUEST)
        query = select(GovernanceRecommendationActionDisposition).where(
            GovernanceRecommendationActionDisposition.organization_id == organization_id
        )
        if snapshot_id is not None:
            query = query.where(GovernanceRecommendationActionDisposition.recommendation_snapshot_id == snapshot_id)
        if disposition_status is not None:
            query = query.where(GovernanceRecommendationActionDisposition.disposition_status == disposition_status)
        if action_key is not None:
            query = query.where(GovernanceRecommendationActionDisposition.action_key == action_key)
        if related_ai_system_id is not None:
            query = query.where(GovernanceRecommendationActionDisposition.related_ai_system_id == related_ai_system_id)
        if related_risk_assessment_id is not None:
            query = query.where(
                GovernanceRecommendationActionDisposition.related_risk_assessment_id == related_risk_assessment_id
            )
        query = query.order_by(
            GovernanceRecommendationActionDisposition.updated_at.desc(),
            GovernanceRecommendationActionDisposition.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def recommendation_action_disposition_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        rows = list(
            self.db.execute(
                select(
                    GovernanceRecommendationActionDisposition.disposition_status,
                    func.count(GovernanceRecommendationActionDisposition.id),
                )
                .where(GovernanceRecommendationActionDisposition.organization_id == organization_id)
                .group_by(GovernanceRecommendationActionDisposition.disposition_status)
            ).all()
        )
        by_status = {str(k): int(v) for k, v in rows}
        rows_action_key = list(
            self.db.execute(
                select(
                    GovernanceRecommendationActionDisposition.action_key,
                    func.count(GovernanceRecommendationActionDisposition.id),
                )
                .where(GovernanceRecommendationActionDisposition.organization_id == organization_id)
                .group_by(GovernanceRecommendationActionDisposition.action_key)
            ).all()
        )
        by_action_key = {str(k): int(v) for k, v in rows_action_key}
        rows_ai = list(
            self.db.execute(
                select(
                    GovernanceRecommendationActionDisposition.related_ai_system_id,
                    func.count(GovernanceRecommendationActionDisposition.id),
                )
                .where(
                    GovernanceRecommendationActionDisposition.organization_id == organization_id,
                    GovernanceRecommendationActionDisposition.related_ai_system_id.is_not(None),
                )
                .group_by(GovernanceRecommendationActionDisposition.related_ai_system_id)
            ).all()
        )
        by_ai_system = [
            {"ai_system_id": str(ai_id), "count": int(count)}
            for ai_id, count in sorted(rows_ai, key=lambda item: (-int(item[1]), str(item[0])))
        ][:10]
        latest_disposition_at = self.db.execute(
            select(func.max(GovernanceRecommendationActionDisposition.updated_at)).where(
                GovernanceRecommendationActionDisposition.organization_id == organization_id
            )
        ).scalar_one()
        total_dispositions = int(sum(by_status.values()))
        return {
            "total_dispositions": total_dispositions,
            "by_status": by_status,
            "by_action_key": by_action_key,
            "by_ai_system": by_ai_system,
            "latest_disposition_at": latest_disposition_at,
            "caveat": AI_RISK_GOVERNANCE_RECOMMENDATION_SNAPSHOT_CAVEAT,
        }

    def refresh_assessment_classification_signals(
        self,
        *,
        assessment: AISystemRiskAssessment,
        persist_signals: bool,
    ) -> dict:
        candidates = self._build_refresh_classification_signal_candidates(assessment=assessment)
        if not persist_signals:
            return {
                "persist_signals": False,
                "created_count": 0,
                "candidate_count": len(candidates),
                "signals": candidates,
                "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
            }

        created_ids: list[str] = []
        for candidate in candidates:
            entity_id = uuid.UUID(candidate["entity_id"])
            exists = self.db.execute(
                select(GovernanceSignal.id).where(
                    GovernanceSignal.organization_id == assessment.organization_id,
                    GovernanceSignal.entity_type == candidate["entity_type"],
                    GovernanceSignal.entity_id == entity_id,
                    GovernanceSignal.reason_code == candidate["reason_code"],
                    GovernanceSignal.status == "open",
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue

            row = self._create_signal(
                organization_id=assessment.organization_id,
                entity_type=candidate["entity_type"],
                entity_id=entity_id,
                related_ai_system_id=uuid.UUID(candidate["related_ai_system_id"])
                if candidate.get("related_ai_system_id")
                else None,
                related_risk_assessment_id=uuid.UUID(candidate["related_risk_assessment_id"])
                if candidate.get("related_risk_assessment_id")
                else None,
                signal_type=candidate["signal_type"],
                reason_code=candidate["reason_code"],
                severity=candidate["severity"],
                title=candidate["title"],
                message=candidate["message"],
                source_json=candidate["source_json"],
            )
            created_ids.append(str(row.id))

        assessment.open_signal_count = self.count_open_signals_for_assessment(assessment_id=assessment.id)
        self.db.flush()
        return {
            "persist_signals": True,
            "created_count": len(created_ids),
            "candidate_count": len(candidates),
            "created_signal_ids": created_ids,
            "signals": candidates,
            "caveat": AI_RISK_GOVERNANCE_SIGNAL_CAVEAT,
        }

    def classification_summary(self, *, organization_id: uuid.UUID) -> dict:
        total_classifications = int(
            self.db.execute(
                select(func.count(AISystemRiskClassificationRecord.id)).where(
                    AISystemRiskClassificationRecord.organization_id == organization_id
                )
            ).scalar_one()
        )
        active_classifications = int(
            self.db.execute(
                select(func.count(AISystemRiskClassificationRecord.id)).where(
                    AISystemRiskClassificationRecord.organization_id == organization_id,
                    AISystemRiskClassificationRecord.status == "active",
                )
            ).scalar_one()
        )
        superseded_classifications = int(
            self.db.execute(
                select(func.count(AISystemRiskClassificationRecord.id)).where(
                    AISystemRiskClassificationRecord.organization_id == organization_id,
                    AISystemRiskClassificationRecord.status == "superseded",
                )
            ).scalar_one()
        )
        archived_classifications = int(
            self.db.execute(
                select(func.count(AISystemRiskClassificationRecord.id)).where(
                    AISystemRiskClassificationRecord.organization_id == organization_id,
                    AISystemRiskClassificationRecord.status == "archived",
                )
            ).scalar_one()
        )

        confidence_rows = self.db.execute(
            select(AISystemRiskClassificationRecord.confidence_level, func.count(AISystemRiskClassificationRecord.id))
            .where(AISystemRiskClassificationRecord.organization_id == organization_id)
            .group_by(AISystemRiskClassificationRecord.confidence_level)
        ).all()
        by_confidence_level = {str(level): int(count) for level, count in confidence_rows}

        source_rows = self.db.execute(
            select(AISystemRiskClassificationRecord.source_type, func.count(AISystemRiskClassificationRecord.id))
            .where(AISystemRiskClassificationRecord.organization_id == organization_id)
            .group_by(AISystemRiskClassificationRecord.source_type)
        ).all()
        by_source_type = {("null" if source is None else str(source)): int(count) for source, count in source_rows}

        rows = self.db.execute(
            select(AISystemRiskClassificationRecord.classification_json).where(
                AISystemRiskClassificationRecord.organization_id == organization_id
            )
        ).all()
        by_label_group: dict[str, int] = {}
        for (classification_json,) in rows:
            if not isinstance(classification_json, dict):
                continue
            labels = classification_json.get("labels")
            if not isinstance(labels, list):
                continue
            for label in labels:
                if isinstance(label, dict) and isinstance(label.get("group_key"), str):
                    group_key = label["group_key"]
                    by_label_group[group_key] = by_label_group.get(group_key, 0) + 1

        assessments_with_classifications = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.latest_classification_id.is_not(None),
                )
            ).scalar_one()
        )
        assessments_without_classifications = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.latest_classification_id.is_(None),
                )
            ).scalar_one()
        )

        default_taxonomy_id = self.db.execute(
            select(AISystemRiskClassificationTaxonomyTemplate.id).where(
                AISystemRiskClassificationTaxonomyTemplate.organization_id == organization_id,
                AISystemRiskClassificationTaxonomyTemplate.is_default.is_(True),
                AISystemRiskClassificationTaxonomyTemplate.status == "active",
                AISystemRiskClassificationTaxonomyTemplate.archived_at.is_(None),
            )
        ).scalar_one_or_none()

        return {
            "total_classifications": total_classifications,
            "active_classifications": active_classifications,
            "superseded_classifications": superseded_classifications,
            "archived_classifications": archived_classifications,
            "by_confidence_level": by_confidence_level,
            "by_source_type": by_source_type,
            "by_label_group": by_label_group,
            "assessments_with_classifications": assessments_with_classifications,
            "assessments_without_classifications": assessments_without_classifications,
            "default_taxonomy_id": default_taxonomy_id,
            "caveat": AI_RISK_CLASSIFICATION_CAVEAT,
        }

    def list_assessments(
        self,
        *,
        organization_id: uuid.UUID,
        ai_system_id: uuid.UUID | None,
        status_filter: str | None,
        risk_level: str | None,
        assessment_type: str | None,
        owner_user_id: uuid.UUID | None,
        include_archived: bool,
        limit: int,
        offset: int,
    ) -> list[AISystemRiskAssessment]:
        stmt = select(AISystemRiskAssessment).where(AISystemRiskAssessment.organization_id == organization_id)
        if ai_system_id is not None:
            stmt = stmt.where(AISystemRiskAssessment.ai_system_id == ai_system_id)
        if status_filter:
            stmt = stmt.where(AISystemRiskAssessment.status == status_filter)
        if risk_level:
            stmt = stmt.where(AISystemRiskAssessment.risk_level == risk_level)
        if assessment_type:
            stmt = stmt.where(AISystemRiskAssessment.assessment_type == assessment_type)
        if owner_user_id is not None:
            stmt = stmt.where(AISystemRiskAssessment.owner_user_id == owner_user_id)
        if not include_archived:
            stmt = stmt.where(AISystemRiskAssessment.status != "archived")
        return (
            self.db.execute(stmt.order_by(AISystemRiskAssessment.created_at.desc()).offset(offset).limit(limit))
            .scalars()
            .all()
        )

    def update_assessment(
        self,
        *,
        row: AISystemRiskAssessment,
        updates: dict,
    ) -> AISystemRiskAssessment:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived risk assessments cannot be updated")

        if "owner_user_id" in updates:
            self.validate_owner_member(organization_id=row.organization_id, owner_user_id=updates.get("owner_user_id"))

        if "title" in updates:
            row.title = updates["title"]
        if "description" in updates:
            row.description = updates["description"]
        if "assessment_type" in updates:
            row.assessment_type = updates["assessment_type"]
        if "owner_user_id" in updates:
            row.owner_user_id = updates["owner_user_id"]
        if "risk_level" in updates:
            row.risk_level = updates["risk_level"]
        if "likelihood" in updates:
            row.likelihood = updates["likelihood"]
        if "impact" in updates:
            row.impact = updates["impact"]
        if "risk_dimensions_json" in updates:
            row.risk_dimensions_json = updates["risk_dimensions_json"]
        if "risk_factors_json" in updates:
            row.risk_factors_json = updates["risk_factors_json"]
        if "mitigation_summary" in updates:
            row.mitigation_summary = updates["mitigation_summary"]
        if "assumptions" in updates:
            row.assumptions = updates["assumptions"]
        if "limitations" in updates:
            row.limitations = updates["limitations"]
        if "methodology_version" in updates:
            row.methodology_version = updates["methodology_version"]

        if "likelihood" in updates or "impact" in updates:
            score = self.deterministic_score(likelihood=row.likelihood, impact=row.impact)
            row.inherent_risk_score = score
            row.residual_risk_score = score

        self.db.flush()
        return row

    def submit_for_review(self, *, row: AISystemRiskAssessment) -> AISystemRiskAssessment:
        if row.status != "draft":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only draft assessments can be submitted for review")
        row.status = "in_review"
        self.db.flush()
        return row

    def complete(self, *, row: AISystemRiskAssessment) -> AISystemRiskAssessment:
        if row.status not in ("draft", "in_review"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only draft or in_review assessments can be completed",
            )
        row.status = "completed"
        if row.completed_at is None:
            row.completed_at = self.now()
        self.db.flush()
        return row

    def archive(self, *, row: AISystemRiskAssessment, actor_user_id: uuid.UUID) -> AISystemRiskAssessment:
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Risk assessment is already archived")
        row.status = "archived"
        if row.archived_at is None:
            row.archived_at = self.now()
        row.archived_by_user_id = actor_user_id
        self.db.flush()
        return row

    def _next_snapshot_version(self, *, organization_id: uuid.UUID, assessment_id: uuid.UUID) -> int:
        current = self.db.execute(
            select(func.count(AISystemRiskAssessmentSnapshot.id)).where(
                AISystemRiskAssessmentSnapshot.organization_id == organization_id,
                AISystemRiskAssessmentSnapshot.risk_assessment_id == assessment_id,
            )
        ).scalar_one()
        return int(current) + 1

    @staticmethod
    def _snapshot_payload(
        *,
        row: AISystemRiskAssessment,
        snapshot_type: str,
        snapshot_version: int,
    ) -> dict:
        return {
            "snapshot_type": snapshot_type,
            "snapshot_version": snapshot_version,
            "risk_assessment": {
                "id": str(row.id),
                "organization_id": str(row.organization_id),
                "ai_system_id": str(row.ai_system_id),
                "title": row.title,
                "description": row.description,
                "assessment_type": row.assessment_type,
                "status": row.status,
                "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
                "risk_level": row.risk_level,
                "likelihood": row.likelihood,
                "impact": row.impact,
                "inherent_risk_score": row.inherent_risk_score,
                "residual_risk_score": row.residual_risk_score,
                "scoring_profile_id": str(row.scoring_profile_id) if row.scoring_profile_id else None,
                "scoring_profile_snapshot_json": row.scoring_profile_snapshot_json,
                "score_explanation_json": row.score_explanation_json,
                "calculated_risk_level": row.calculated_risk_level,
                "dimension_template_id": str(row.dimension_template_id) if row.dimension_template_id else None,
                "latest_classification_id": str(row.latest_classification_id) if row.latest_classification_id else None,
                "classification_status": row.classification_status,
                "classification_summary_json": row.classification_summary_json,
                "latest_classification_review_status": row.latest_classification_review_status,
                "open_signal_count": row.open_signal_count,
                "dimension_template_snapshot_json": row.dimension_template_snapshot_json,
                "dimension_inputs_json": row.dimension_inputs_json,
                "dimension_score_json": row.dimension_score_json,
                "dimension_weighted_score": row.dimension_weighted_score,
                "calculated_dimension_risk_level": row.calculated_dimension_risk_level,
                "residual_likelihood": row.residual_likelihood,
                "residual_impact": row.residual_impact,
                "calculated_residual_risk_level": row.calculated_residual_risk_level,
                "residual_score_explanation_json": row.residual_score_explanation_json,
                "risk_dimensions_json": row.risk_dimensions_json,
                "risk_factors_json": row.risk_factors_json,
                "mitigation_summary": row.mitigation_summary,
                "assumptions": row.assumptions,
                "limitations": row.limitations,
                "methodology_version": row.methodology_version,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "archived_at": row.archived_at.isoformat() if row.archived_at else None,
                "archived_by_user_id": str(row.archived_by_user_id) if row.archived_by_user_id else None,
                "created_by_user_id": str(row.created_by_user_id) if row.created_by_user_id else None,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            },
            "classification_caveat": AI_RISK_CLASSIFICATION_CAVEAT,
            "caveat": AI_RISK_ASSESSMENT_CAVEAT,
        }

    def create_snapshot(
        self,
        *,
        row: AISystemRiskAssessment,
        snapshot_type: str,
        actor_user_id: uuid.UUID,
    ) -> AISystemRiskAssessmentSnapshot:
        snapshot_version = self._next_snapshot_version(organization_id=row.organization_id, assessment_id=row.id)
        payload = self._snapshot_payload(row=row, snapshot_type=snapshot_type, snapshot_version=snapshot_version)
        snapshot = AISystemRiskAssessmentSnapshot(
            organization_id=row.organization_id,
            risk_assessment_id=row.id,
            ai_system_id=row.ai_system_id,
            snapshot_type=snapshot_type,
            snapshot_version=snapshot_version,
            snapshot_json=payload,
            snapshot_sha256=self.sha256_hexdigest(payload),
            created_by_user_id=actor_user_id,
        )
        self.db.add(snapshot)
        self.db.flush()
        return snapshot

    def list_snapshots(
        self,
        *,
        organization_id: uuid.UUID,
        assessment_id: uuid.UUID,
    ) -> list[AISystemRiskAssessmentSnapshot]:
        return (
            self.db.execute(
                select(AISystemRiskAssessmentSnapshot)
                .where(
                    AISystemRiskAssessmentSnapshot.organization_id == organization_id,
                    AISystemRiskAssessmentSnapshot.risk_assessment_id == assessment_id,
                )
                .order_by(AISystemRiskAssessmentSnapshot.snapshot_version.desc())
            )
            .scalars()
            .all()
        )

    def scoring_profile_summary(self, *, organization_id: uuid.UUID) -> dict:
        total_profiles = int(
            self.db.execute(
                select(func.count(AISystemRiskScoringProfile.id)).where(
                    AISystemRiskScoringProfile.organization_id == organization_id
                )
            ).scalar_one()
        )
        active_profiles = int(
            self.db.execute(
                select(func.count(AISystemRiskScoringProfile.id)).where(
                    AISystemRiskScoringProfile.organization_id == organization_id,
                    AISystemRiskScoringProfile.status == "active",
                )
            ).scalar_one()
        )
        inactive_profiles = int(
            self.db.execute(
                select(func.count(AISystemRiskScoringProfile.id)).where(
                    AISystemRiskScoringProfile.organization_id == organization_id,
                    AISystemRiskScoringProfile.status == "inactive",
                )
            ).scalar_one()
        )
        archived_profiles = int(
            self.db.execute(
                select(func.count(AISystemRiskScoringProfile.id)).where(
                    AISystemRiskScoringProfile.organization_id == organization_id,
                    AISystemRiskScoringProfile.status == "archived",
                )
            ).scalar_one()
        )
        default_profile_id = self.db.execute(
            select(AISystemRiskScoringProfile.id).where(
                AISystemRiskScoringProfile.organization_id == organization_id,
                AISystemRiskScoringProfile.is_default.is_(True),
                AISystemRiskScoringProfile.status == "active",
            )
        ).scalar_one_or_none()
        assessments_with_scoring_profile = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.scoring_profile_id.is_not(None),
                )
            ).scalar_one()
        )
        assessments_without_scoring_profile = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.scoring_profile_id.is_(None),
                )
            ).scalar_one()
        )
        rows = self.db.execute(
            select(AISystemRiskAssessment.calculated_risk_level, func.count(AISystemRiskAssessment.id))
            .where(AISystemRiskAssessment.organization_id == organization_id)
            .group_by(AISystemRiskAssessment.calculated_risk_level)
        ).all()
        by_calculated_risk_level = {
            ("null" if level is None else str(level)): int(count)
            for level, count in rows
        }

        return {
            "total_profiles": total_profiles,
            "active_profiles": active_profiles,
            "inactive_profiles": inactive_profiles,
            "archived_profiles": archived_profiles,
            "default_profile_id": default_profile_id,
            "assessments_with_scoring_profile": assessments_with_scoring_profile,
            "assessments_without_scoring_profile": assessments_without_scoring_profile,
            "by_calculated_risk_level": by_calculated_risk_level,
            "caveat": AI_RISK_SCORING_CAVEAT,
        }

    def dimension_template_summary(self, *, organization_id: uuid.UUID) -> dict:
        total_templates = int(
            self.db.execute(
                select(func.count(AISystemRiskDimensionTemplate.id)).where(
                    AISystemRiskDimensionTemplate.organization_id == organization_id
                )
            ).scalar_one()
        )
        active_templates = int(
            self.db.execute(
                select(func.count(AISystemRiskDimensionTemplate.id)).where(
                    AISystemRiskDimensionTemplate.organization_id == organization_id,
                    AISystemRiskDimensionTemplate.status == "active",
                )
            ).scalar_one()
        )
        inactive_templates = int(
            self.db.execute(
                select(func.count(AISystemRiskDimensionTemplate.id)).where(
                    AISystemRiskDimensionTemplate.organization_id == organization_id,
                    AISystemRiskDimensionTemplate.status == "inactive",
                )
            ).scalar_one()
        )
        archived_templates = int(
            self.db.execute(
                select(func.count(AISystemRiskDimensionTemplate.id)).where(
                    AISystemRiskDimensionTemplate.organization_id == organization_id,
                    AISystemRiskDimensionTemplate.status == "archived",
                )
            ).scalar_one()
        )
        default_template_id = self.db.execute(
            select(AISystemRiskDimensionTemplate.id).where(
                AISystemRiskDimensionTemplate.organization_id == organization_id,
                AISystemRiskDimensionTemplate.is_default.is_(True),
                AISystemRiskDimensionTemplate.status == "active",
            )
        ).scalar_one_or_none()
        assessments_with_dimension_template = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.dimension_template_id.is_not(None),
                )
            ).scalar_one()
        )
        assessments_without_dimension_template = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.dimension_template_id.is_(None),
                )
            ).scalar_one()
        )
        by_dimension_rows = self.db.execute(
            select(AISystemRiskAssessment.calculated_dimension_risk_level, func.count(AISystemRiskAssessment.id))
            .where(AISystemRiskAssessment.organization_id == organization_id)
            .group_by(AISystemRiskAssessment.calculated_dimension_risk_level)
        ).all()
        by_calculated_dimension_risk_level = {
            ("null" if level is None else str(level)): int(count)
            for level, count in by_dimension_rows
        }
        by_residual_rows = self.db.execute(
            select(AISystemRiskAssessment.calculated_residual_risk_level, func.count(AISystemRiskAssessment.id))
            .where(AISystemRiskAssessment.organization_id == organization_id)
            .group_by(AISystemRiskAssessment.calculated_residual_risk_level)
        ).all()
        by_calculated_residual_risk_level = {
            ("null" if level is None else str(level)): int(count)
            for level, count in by_residual_rows
        }
        return {
            "total_templates": total_templates,
            "active_templates": active_templates,
            "inactive_templates": inactive_templates,
            "archived_templates": archived_templates,
            "default_template_id": default_template_id,
            "assessments_with_dimension_template": assessments_with_dimension_template,
            "assessments_without_dimension_template": assessments_without_dimension_template,
            "by_calculated_dimension_risk_level": by_calculated_dimension_risk_level,
            "by_calculated_residual_risk_level": by_calculated_residual_risk_level,
            "caveat": AI_RISK_DIMENSION_CAVEAT,
        }

    def summary(self, *, organization_id: uuid.UUID) -> dict:
        total_assessments = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(AISystemRiskAssessment.organization_id == organization_id)
            ).scalar_one()
        )
        draft_assessments = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.status == "draft",
                )
            ).scalar_one()
        )
        in_review_assessments = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.status == "in_review",
                )
            ).scalar_one()
        )
        completed_assessments = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.status == "completed",
                )
            ).scalar_one()
        )
        archived_assessments = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessment.id)).where(
                    AISystemRiskAssessment.organization_id == organization_id,
                    AISystemRiskAssessment.status == "archived",
                )
            ).scalar_one()
        )

        by_risk_level_rows = self.db.execute(
            select(AISystemRiskAssessment.risk_level, func.count(AISystemRiskAssessment.id))
            .where(AISystemRiskAssessment.organization_id == organization_id)
            .group_by(AISystemRiskAssessment.risk_level)
        ).all()
        by_risk_level = {str(level): int(count) for level, count in by_risk_level_rows}

        by_assessment_type_rows = self.db.execute(
            select(AISystemRiskAssessment.assessment_type, func.count(AISystemRiskAssessment.id))
            .where(AISystemRiskAssessment.organization_id == organization_id)
            .group_by(AISystemRiskAssessment.assessment_type)
        ).all()
        by_assessment_type = {str(atype): int(count) for atype, count in by_assessment_type_rows}

        by_ai_system_rows = self.db.execute(
            select(AISystemRiskAssessment.ai_system_id, func.count(AISystemRiskAssessment.id))
            .where(AISystemRiskAssessment.organization_id == organization_id)
            .group_by(AISystemRiskAssessment.ai_system_id)
        ).all()
        by_ai_system = {str(ai_system_id): int(count) for ai_system_id, count in by_ai_system_rows}

        by_calculated_dimension_rows = self.db.execute(
            select(AISystemRiskAssessment.calculated_dimension_risk_level, func.count(AISystemRiskAssessment.id))
            .where(AISystemRiskAssessment.organization_id == organization_id)
            .group_by(AISystemRiskAssessment.calculated_dimension_risk_level)
        ).all()
        by_calculated_dimension_risk_level = {
            ("null" if level is None else str(level)): int(count)
            for level, count in by_calculated_dimension_rows
        }

        by_calculated_residual_rows = self.db.execute(
            select(AISystemRiskAssessment.calculated_residual_risk_level, func.count(AISystemRiskAssessment.id))
            .where(AISystemRiskAssessment.organization_id == organization_id)
            .group_by(AISystemRiskAssessment.calculated_residual_risk_level)
        ).all()
        by_calculated_residual_risk_level = {
            ("null" if level is None else str(level)): int(count)
            for level, count in by_calculated_residual_rows
        }

        total_snapshots = int(
            self.db.execute(
                select(func.count(AISystemRiskAssessmentSnapshot.id)).where(
                    AISystemRiskAssessmentSnapshot.organization_id == organization_id
                )
            ).scalar_one()
        )
        latest_completed_at = self.db.execute(
            select(func.max(AISystemRiskAssessment.completed_at)).where(
                AISystemRiskAssessment.organization_id == organization_id
            )
        ).scalar_one()

        return {
            "total_assessments": total_assessments,
            "draft_assessments": draft_assessments,
            "in_review_assessments": in_review_assessments,
            "completed_assessments": completed_assessments,
            "archived_assessments": archived_assessments,
            "by_risk_level": by_risk_level,
            "by_assessment_type": by_assessment_type,
            "by_ai_system": by_ai_system,
            "by_calculated_dimension_risk_level": by_calculated_dimension_risk_level,
            "by_calculated_residual_risk_level": by_calculated_residual_risk_level,
            "total_snapshots": total_snapshots,
            "latest_completed_at": latest_completed_at,
            "caveat": AI_RISK_ASSESSMENT_CAVEAT,
        }

    @staticmethod
    def _autopilot_band_rank(band: str) -> int:
        return {"low": 1, "medium": 2, "high": 3, "urgent": 4}.get(str(band), 0)

    @classmethod
    def _normalize_string_array(
        cls,
        value: Any,
        *,
        field_name: str,
        allowed_values: set[str] | None = None,
    ) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} must be an array")
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field_name} entries must be non-empty strings",
                )
            entry = item.strip()
            if allowed_values is not None and entry not in allowed_values:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field_name} entry: {entry}")
            normalized.append(entry)
        return sorted(set(normalized))

    @classmethod
    def _safe_fallback_autopilot_policy(cls) -> dict[str, Any]:
        now = datetime.now(UTC)
        return {
            "policy_id": None,
            "organization_id": None,
            "name": "Safe Default Autopilot Policy",
            "description": "Deterministic fallback policy when no persisted default autopilot policy exists.",
            "status": "active",
            "is_default": False,
            "mode": AUTOPILOT_SAFE_FALLBACK_MODE,
            "allowed_action_types_json": [],
            "blocked_action_types_json": [],
            "allowed_draft_types_json": [],
            "blocked_draft_types_json": [],
            "allowed_signal_reason_codes_json": [],
            "blocked_signal_reason_codes_json": [],
            "approval_required_action_types_json": [],
            "approval_required_priority_bands_json": ["high", "urgent"],
            "max_allowed_priority_band_for_auto": "low",
            "external_effects_allowed": False,
            "task_creation_allowed": False,
            "review_creation_allowed": False,
            "source_record_mutation_allowed": False,
            "policy_json": {
                "mode": AUTOPILOT_SAFE_FALLBACK_MODE,
                "approval_required_priority_bands_json": ["high", "urgent"],
                "max_allowed_priority_band_for_auto": "low",
                "external_effects_allowed": False,
                "task_creation_allowed": False,
                "review_creation_allowed": False,
                "source_record_mutation_allowed": False,
                "automation_allowed": False,
            },
            "created_by_user_id": None,
            "updated_by_user_id": None,
            "archived_at": None,
            "created_at": now,
            "updated_at": now,
            "resolved_source": "safe_fallback_default",
            "caveat": AUTOPILOT_SAFE_FALLBACK_CAVEAT,
        }

    def _autopilot_policy_payload(self, row: GovernanceAutopilotPolicy, *, resolved_source: str | None = None) -> dict[str, Any]:
        return {
            "policy_id": row.id,
            "organization_id": row.organization_id,
            "name": row.name,
            "description": row.description,
            "status": row.status,
            "is_default": bool(row.is_default),
            "mode": row.mode,
            "allowed_action_types_json": list(row.allowed_action_types_json or []),
            "blocked_action_types_json": list(row.blocked_action_types_json or []),
            "allowed_draft_types_json": list(row.allowed_draft_types_json or []),
            "blocked_draft_types_json": list(row.blocked_draft_types_json or []),
            "allowed_signal_reason_codes_json": list(row.allowed_signal_reason_codes_json or []),
            "blocked_signal_reason_codes_json": list(row.blocked_signal_reason_codes_json or []),
            "approval_required_action_types_json": list(row.approval_required_action_types_json or []),
            "approval_required_priority_bands_json": list(row.approval_required_priority_bands_json or []),
            "max_allowed_priority_band_for_auto": row.max_allowed_priority_band_for_auto,
            "external_effects_allowed": bool(row.external_effects_allowed),
            "task_creation_allowed": bool(row.task_creation_allowed),
            "review_creation_allowed": bool(row.review_creation_allowed),
            "source_record_mutation_allowed": bool(row.source_record_mutation_allowed),
            "policy_json": dict(row.policy_json or {}),
            "created_by_user_id": row.created_by_user_id,
            "updated_by_user_id": row.updated_by_user_id,
            "archived_at": row.archived_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "resolved_source": resolved_source,
            "caveat": AUTOPILOT_SAFE_FALLBACK_CAVEAT,
        }

    @classmethod
    def _safe_fallback_autopilot_approval_policy(cls) -> dict[str, Any]:
        now = datetime.now(UTC)
        return {
            "approval_policy_id": None,
            "policy_id": None,
            "organization_id": None,
            "name": "Safe Default Autopilot Approval Policy",
            "description": "Deterministic fallback approval policy when no persisted default approval policy exists.",
            "status": "active",
            "is_default": False,
            "minimum_approvals": 1,
            "rejection_threshold": 1,
            "require_distinct_approvers": True,
            "block_requester_self_approval": True,
            "require_quorum_for_priority_bands_json": ["high", "urgent"],
            "require_quorum_for_source_types_json": [
                "candidate_action",
                "recommendation_snapshot",
                "copilot_draft_snapshot",
            ],
            "policy_json": {
                "minimum_approvals": 1,
                "rejection_threshold": 1,
                "require_distinct_approvers": True,
                "block_requester_self_approval": True,
                "require_quorum_for_priority_bands_json": ["high", "urgent"],
                "require_quorum_for_source_types_json": [
                    "candidate_action",
                    "recommendation_snapshot",
                    "copilot_draft_snapshot",
                ],
            },
            "created_by_user_id": None,
            "updated_by_user_id": None,
            "archived_at": None,
            "created_at": now,
            "updated_at": now,
            "resolved_source": "safe_fallback_default",
            "caveat": AUTOPILOT_EXECUTION_QUORUM_CAVEAT,
        }

    def _autopilot_approval_policy_payload(
        self,
        row: GovernanceAutopilotApprovalPolicy,
        *,
        resolved_source: str | None = None,
    ) -> dict[str, Any]:
        return {
            "approval_policy_id": row.id,
            "policy_id": row.id,
            "organization_id": row.organization_id,
            "name": row.name,
            "description": row.description,
            "status": row.status,
            "is_default": bool(row.is_default),
            "minimum_approvals": int(row.minimum_approvals),
            "rejection_threshold": int(row.rejection_threshold),
            "require_distinct_approvers": bool(row.require_distinct_approvers),
            "block_requester_self_approval": bool(row.block_requester_self_approval),
            "require_quorum_for_priority_bands_json": list(row.require_quorum_for_priority_bands_json or []),
            "require_quorum_for_source_types_json": list(row.require_quorum_for_source_types_json or []),
            "policy_json": dict(row.policy_json or {}),
            "created_by_user_id": row.created_by_user_id,
            "updated_by_user_id": row.updated_by_user_id,
            "archived_at": row.archived_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "resolved_source": resolved_source,
            "caveat": AUTOPILOT_EXECUTION_QUORUM_CAVEAT,
        }

    def _normalize_autopilot_approval_policy_inputs(
        self,
        *,
        name: str,
        description: str | None,
        status_value: str,
        is_default: bool,
        minimum_approvals: int,
        rejection_threshold: int,
        require_distinct_approvers: bool,
        block_requester_self_approval: bool,
        require_quorum_for_priority_bands_json: Any,
        require_quorum_for_source_types_json: Any,
        policy_json: Any,
    ) -> dict[str, Any]:
        status_value = validate_choice(status_value, AUTOPILOT_APPROVAL_POLICY_STATUS_VALUES, "approval policy status", status_code=status.HTTP_400_BAD_REQUEST)
        if minimum_approvals < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="minimum_approvals must be >= 1")
        if rejection_threshold < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rejection_threshold must be >= 1")

        normalized_bands = self._normalize_string_array(
            require_quorum_for_priority_bands_json,
            field_name="require_quorum_for_priority_bands_json",
            allowed_values=set(AUTOPILOT_PRIORITY_BANDS),
        )
        normalized_sources = self._normalize_string_array(
            require_quorum_for_source_types_json,
            field_name="require_quorum_for_source_types_json",
            allowed_values=set(AUTOPILOT_EXECUTION_INTENT_SOURCE_TYPES),
        )
        core = {
            "minimum_approvals": int(minimum_approvals),
            "rejection_threshold": int(rejection_threshold),
            "require_distinct_approvers": bool(require_distinct_approvers),
            "block_requester_self_approval": bool(block_requester_self_approval),
            "require_quorum_for_priority_bands_json": normalized_bands,
            "require_quorum_for_source_types_json": normalized_sources,
        }
        if policy_json is None:
            normalized_policy_json = dict(core)
        elif isinstance(policy_json, dict):
            normalized_policy_json = dict(policy_json)
            normalized_policy_json.update(core)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="policy_json must be an object when provided")
        return {
            "name": str(name).strip(),
            "description": description,
            "status": status_value,
            "is_default": bool(is_default),
            **core,
            "policy_json": normalized_policy_json,
        }

    def _set_default_autopilot_approval_policy(self, *, organization_id: uuid.UUID, policy_id: uuid.UUID) -> None:
        rows = self.db.execute(
            select(GovernanceAutopilotApprovalPolicy).where(
                GovernanceAutopilotApprovalPolicy.organization_id == organization_id,
                GovernanceAutopilotApprovalPolicy.is_default.is_(True),
            )
        ).scalars().all()
        for row in rows:
            if row.id != policy_id:
                row.is_default = False

    def _normalize_autopilot_policy_inputs(
        self,
        *,
        name: str,
        description: str | None,
        status_value: str,
        is_default: bool,
        mode: str,
        allowed_action_types_json: Any,
        blocked_action_types_json: Any,
        allowed_draft_types_json: Any,
        blocked_draft_types_json: Any,
        allowed_signal_reason_codes_json: Any,
        blocked_signal_reason_codes_json: Any,
        approval_required_action_types_json: Any,
        approval_required_priority_bands_json: Any,
        max_allowed_priority_band_for_auto: str,
        external_effects_allowed: bool,
        task_creation_allowed: bool,
        review_creation_allowed: bool,
        source_record_mutation_allowed: bool,
        policy_json: Any,
    ) -> dict[str, Any]:
        status_value = validate_choice(status_value, AUTOPILOT_POLICY_STATUS_VALUES, "policy status", status_code=status.HTTP_400_BAD_REQUEST)
        mode = validate_choice(mode, AUTOPILOT_POLICY_MODE_VALUES, "policy mode", status_code=status.HTTP_400_BAD_REQUEST)
        max_allowed_priority_band_for_auto = validate_choice(max_allowed_priority_band_for_auto, AUTOPILOT_PRIORITY_BANDS, "max_allowed_priority_band_for_auto", status_code=status.HTTP_400_BAD_REQUEST)
        action_types = {str(item["action_type"]) for item in GOVERNANCE_CANDIDATE_ACTION_TEMPLATES}
        draft_types = {
            "ai_system_attention_brief",
            "risk_assessment_review_brief",
            "recommendation_snapshot_summary",
            "classification_review_brief",
            "executive_risk_summary",
            "action_plan_brief",
        }

        normalized = {
            "name": name,
            "description": description,
            "status": status_value,
            "is_default": bool(is_default),
            "mode": mode,
            "allowed_action_types_json": self._normalize_string_array(
                allowed_action_types_json,
                field_name="allowed_action_types_json",
                allowed_values=action_types,
            ),
            "blocked_action_types_json": self._normalize_string_array(
                blocked_action_types_json,
                field_name="blocked_action_types_json",
                allowed_values=action_types,
            ),
            "allowed_draft_types_json": self._normalize_string_array(
                allowed_draft_types_json,
                field_name="allowed_draft_types_json",
                allowed_values=draft_types,
            ),
            "blocked_draft_types_json": self._normalize_string_array(
                blocked_draft_types_json,
                field_name="blocked_draft_types_json",
                allowed_values=draft_types,
            ),
            "allowed_signal_reason_codes_json": self._normalize_string_array(
                allowed_signal_reason_codes_json,
                field_name="allowed_signal_reason_codes_json",
            ),
            "blocked_signal_reason_codes_json": self._normalize_string_array(
                blocked_signal_reason_codes_json,
                field_name="blocked_signal_reason_codes_json",
            ),
            "approval_required_action_types_json": self._normalize_string_array(
                approval_required_action_types_json,
                field_name="approval_required_action_types_json",
                allowed_values=action_types,
            ),
            "approval_required_priority_bands_json": self._normalize_string_array(
                approval_required_priority_bands_json,
                field_name="approval_required_priority_bands_json",
                allowed_values=set(AUTOPILOT_PRIORITY_BANDS),
            ),
            "max_allowed_priority_band_for_auto": max_allowed_priority_band_for_auto,
            "external_effects_allowed": bool(external_effects_allowed),
            "task_creation_allowed": bool(task_creation_allowed),
            "review_creation_allowed": bool(review_creation_allowed),
            "source_record_mutation_allowed": bool(source_record_mutation_allowed),
        }
        policy_core = {
            "mode": normalized["mode"],
            "allowed_action_types_json": normalized["allowed_action_types_json"],
            "blocked_action_types_json": normalized["blocked_action_types_json"],
            "allowed_draft_types_json": normalized["allowed_draft_types_json"],
            "blocked_draft_types_json": normalized["blocked_draft_types_json"],
            "allowed_signal_reason_codes_json": normalized["allowed_signal_reason_codes_json"],
            "blocked_signal_reason_codes_json": normalized["blocked_signal_reason_codes_json"],
            "approval_required_action_types_json": normalized["approval_required_action_types_json"],
            "approval_required_priority_bands_json": normalized["approval_required_priority_bands_json"],
            "max_allowed_priority_band_for_auto": normalized["max_allowed_priority_band_for_auto"],
            "external_effects_allowed": normalized["external_effects_allowed"],
            "task_creation_allowed": normalized["task_creation_allowed"],
            "review_creation_allowed": normalized["review_creation_allowed"],
            "source_record_mutation_allowed": normalized["source_record_mutation_allowed"],
            "automation_allowed": False,
        }
        if policy_json is None:
            normalized["policy_json"] = policy_core
        elif isinstance(policy_json, dict):
            merged = dict(policy_json)
            merged.update(policy_core)
            normalized["policy_json"] = merged
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="policy_json must be an object when provided")
        return normalized

    def _set_default_autopilot_policy(self, *, organization_id: uuid.UUID, policy_id: uuid.UUID) -> None:
        rows = self.db.execute(
            select(GovernanceAutopilotPolicy).where(
                GovernanceAutopilotPolicy.organization_id == organization_id,
                GovernanceAutopilotPolicy.is_default.is_(True),
            )
        ).scalars().all()
        for row in rows:
            if row.id != policy_id:
                row.is_default = False

    def create_autopilot_policy(
        self,
        *,
        organization_id: uuid.UUID,
        payload: dict[str, Any],
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotPolicy:
        normalized_payload = dict(payload)
        normalized_payload["status_value"] = normalized_payload.pop("status")
        normalized = self._normalize_autopilot_policy_inputs(**normalized_payload)
        row = GovernanceAutopilotPolicy(
            organization_id=organization_id,
            name=normalized["name"],
            description=normalized["description"],
            status=normalized["status"],
            is_default=bool(normalized["is_default"]),
            mode=normalized["mode"],
            allowed_action_types_json=normalized["allowed_action_types_json"],
            blocked_action_types_json=normalized["blocked_action_types_json"],
            allowed_draft_types_json=normalized["allowed_draft_types_json"],
            blocked_draft_types_json=normalized["blocked_draft_types_json"],
            allowed_signal_reason_codes_json=normalized["allowed_signal_reason_codes_json"],
            blocked_signal_reason_codes_json=normalized["blocked_signal_reason_codes_json"],
            approval_required_action_types_json=normalized["approval_required_action_types_json"],
            approval_required_priority_bands_json=normalized["approval_required_priority_bands_json"],
            max_allowed_priority_band_for_auto=normalized["max_allowed_priority_band_for_auto"],
            external_effects_allowed=normalized["external_effects_allowed"],
            task_creation_allowed=normalized["task_creation_allowed"],
            review_creation_allowed=normalized["review_creation_allowed"],
            source_record_mutation_allowed=normalized["source_record_mutation_allowed"],
            policy_json=normalized["policy_json"],
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        if row.is_default and row.status == "active":
            self._set_default_autopilot_policy(organization_id=organization_id, policy_id=row.id)
        return row

    def list_autopilot_policies(
        self,
        *,
        organization_id: uuid.UUID,
        status_value: str | None,
        is_default: bool | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceAutopilotPolicy]:
        if status_value is not None:
            status_value = validate_choice(status_value, AUTOPILOT_POLICY_STATUS_VALUES, "policy status", status_code=status.HTTP_400_BAD_REQUEST)
        query = select(GovernanceAutopilotPolicy).where(
            GovernanceAutopilotPolicy.organization_id == organization_id
        )
        if status_value is not None:
            query = query.where(GovernanceAutopilotPolicy.status == status_value)
        if is_default is not None:
            query = query.where(GovernanceAutopilotPolicy.is_default.is_(is_default))
        query = query.order_by(GovernanceAutopilotPolicy.created_at.desc(), GovernanceAutopilotPolicy.id.desc())
        query = query.offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def require_autopilot_policy(
        self,
        *,
        organization_id: uuid.UUID,
        policy_id: uuid.UUID,
    ) -> GovernanceAutopilotPolicy:
        row = self.db.execute(
            select(GovernanceAutopilotPolicy).where(
                GovernanceAutopilotPolicy.organization_id == organization_id,
                GovernanceAutopilotPolicy.id == policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Autopilot policy not found")
        return row

    def update_autopilot_policy(
        self,
        *,
        organization_id: uuid.UUID,
        policy_id: uuid.UUID,
        payload: dict[str, Any],
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotPolicy:
        row = self.require_autopilot_policy(organization_id=organization_id, policy_id=policy_id)
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived autopilot policy cannot be updated")
        merged = {
            "name": row.name,
            "description": row.description,
            "status_value": row.status,
            "is_default": row.is_default,
            "mode": row.mode,
            "allowed_action_types_json": row.allowed_action_types_json,
            "blocked_action_types_json": row.blocked_action_types_json,
            "allowed_draft_types_json": row.allowed_draft_types_json,
            "blocked_draft_types_json": row.blocked_draft_types_json,
            "allowed_signal_reason_codes_json": row.allowed_signal_reason_codes_json,
            "blocked_signal_reason_codes_json": row.blocked_signal_reason_codes_json,
            "approval_required_action_types_json": row.approval_required_action_types_json,
            "approval_required_priority_bands_json": row.approval_required_priority_bands_json,
            "max_allowed_priority_band_for_auto": row.max_allowed_priority_band_for_auto,
            "external_effects_allowed": row.external_effects_allowed,
            "task_creation_allowed": row.task_creation_allowed,
            "review_creation_allowed": row.review_creation_allowed,
            "source_record_mutation_allowed": row.source_record_mutation_allowed,
            "policy_json": row.policy_json,
        }
        for key in list(merged.keys()):
            source_key = "status" if key == "status_value" else key
            if source_key in payload and payload[source_key] is not None:
                merged[key] = payload[source_key]
            if source_key in payload and payload[source_key] is None and key in {"description"}:
                merged[key] = None
        normalized = self._normalize_autopilot_policy_inputs(**merged)
        row.name = normalized["name"]
        row.description = normalized["description"]
        row.status = normalized["status"]
        row.is_default = bool(normalized["is_default"])
        row.mode = normalized["mode"]
        row.allowed_action_types_json = normalized["allowed_action_types_json"]
        row.blocked_action_types_json = normalized["blocked_action_types_json"]
        row.allowed_draft_types_json = normalized["allowed_draft_types_json"]
        row.blocked_draft_types_json = normalized["blocked_draft_types_json"]
        row.allowed_signal_reason_codes_json = normalized["allowed_signal_reason_codes_json"]
        row.blocked_signal_reason_codes_json = normalized["blocked_signal_reason_codes_json"]
        row.approval_required_action_types_json = normalized["approval_required_action_types_json"]
        row.approval_required_priority_bands_json = normalized["approval_required_priority_bands_json"]
        row.max_allowed_priority_band_for_auto = normalized["max_allowed_priority_band_for_auto"]
        row.external_effects_allowed = normalized["external_effects_allowed"]
        row.task_creation_allowed = normalized["task_creation_allowed"]
        row.review_creation_allowed = normalized["review_creation_allowed"]
        row.source_record_mutation_allowed = normalized["source_record_mutation_allowed"]
        row.policy_json = normalized["policy_json"]
        row.updated_by_user_id = actor_user_id
        if row.is_default and row.status == "active":
            self._set_default_autopilot_policy(organization_id=organization_id, policy_id=row.id)
        return row

    def archive_autopilot_policy(
        self,
        *,
        organization_id: uuid.UUID,
        policy_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotPolicy:
        row = self.require_autopilot_policy(organization_id=organization_id, policy_id=policy_id)
        if row.status != "archived":
            row.status = "archived"
            row.archived_at = self.now()
            row.is_default = False
            row.updated_by_user_id = actor_user_id
        return row

    def set_default_autopilot_policy(
        self,
        *,
        organization_id: uuid.UUID,
        policy_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotPolicy:
        row = self.require_autopilot_policy(organization_id=organization_id, policy_id=policy_id)
        if row.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only active autopilot policy can be default")
        row.is_default = True
        row.updated_by_user_id = actor_user_id
        self._set_default_autopilot_policy(organization_id=organization_id, policy_id=row.id)
        return row

    def resolved_autopilot_policy(
        self,
        *,
        organization_id: uuid.UUID,
        policy_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        if policy_id is not None:
            row = self.require_autopilot_policy(organization_id=organization_id, policy_id=policy_id)
            if row.status != "active" or row.archived_at is not None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Autopilot policy must be active")
            return self._autopilot_policy_payload(row, resolved_source="explicit_policy")

        default_row = self.db.execute(
            select(GovernanceAutopilotPolicy).where(
                GovernanceAutopilotPolicy.organization_id == organization_id,
                GovernanceAutopilotPolicy.is_default.is_(True),
                GovernanceAutopilotPolicy.status == "active",
                GovernanceAutopilotPolicy.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if default_row is not None:
            return self._autopilot_policy_payload(default_row, resolved_source="persisted_default")
        fallback = self._safe_fallback_autopilot_policy()
        fallback["organization_id"] = organization_id
        return fallback

    def create_autopilot_approval_policy(
        self,
        *,
        organization_id: uuid.UUID,
        payload: dict[str, Any],
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotApprovalPolicy:
        normalized_payload = dict(payload)
        normalized_payload["status_value"] = normalized_payload.pop("status")
        normalized = self._normalize_autopilot_approval_policy_inputs(**normalized_payload)
        row = GovernanceAutopilotApprovalPolicy(
            organization_id=organization_id,
            name=normalized["name"],
            description=normalized["description"],
            status=normalized["status"],
            is_default=normalized["is_default"],
            minimum_approvals=normalized["minimum_approvals"],
            rejection_threshold=normalized["rejection_threshold"],
            require_distinct_approvers=normalized["require_distinct_approvers"],
            block_requester_self_approval=normalized["block_requester_self_approval"],
            require_quorum_for_priority_bands_json=normalized["require_quorum_for_priority_bands_json"],
            require_quorum_for_source_types_json=normalized["require_quorum_for_source_types_json"],
            policy_json=normalized["policy_json"],
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        if row.is_default and row.status == "active":
            self._set_default_autopilot_approval_policy(organization_id=organization_id, policy_id=row.id)
        return row

    def list_autopilot_approval_policies(
        self,
        *,
        organization_id: uuid.UUID,
        status_value: str | None,
        is_default: bool | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceAutopilotApprovalPolicy]:
        if status_value is not None:
            status_value = validate_choice(status_value, AUTOPILOT_APPROVAL_POLICY_STATUS_VALUES, "approval policy status", status_code=status.HTTP_400_BAD_REQUEST)
        query = select(GovernanceAutopilotApprovalPolicy).where(
            GovernanceAutopilotApprovalPolicy.organization_id == organization_id
        )
        if status_value is not None:
            query = query.where(GovernanceAutopilotApprovalPolicy.status == status_value)
        if is_default is not None:
            query = query.where(GovernanceAutopilotApprovalPolicy.is_default.is_(is_default))
        query = query.order_by(GovernanceAutopilotApprovalPolicy.created_at.desc(), GovernanceAutopilotApprovalPolicy.id.desc())
        return list(self.db.execute(query.offset(offset).limit(limit)).scalars().all())

    def require_autopilot_approval_policy(
        self,
        *,
        organization_id: uuid.UUID,
        approval_policy_id: uuid.UUID,
    ) -> GovernanceAutopilotApprovalPolicy:
        row = self.db.execute(
            select(GovernanceAutopilotApprovalPolicy).where(
                GovernanceAutopilotApprovalPolicy.organization_id == organization_id,
                GovernanceAutopilotApprovalPolicy.id == approval_policy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Autopilot approval policy not found")
        return row

    def update_autopilot_approval_policy(
        self,
        *,
        organization_id: uuid.UUID,
        approval_policy_id: uuid.UUID,
        payload: dict[str, Any],
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotApprovalPolicy:
        row = self.require_autopilot_approval_policy(
            organization_id=organization_id,
            approval_policy_id=approval_policy_id,
        )
        if row.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived approval policy cannot be updated")
        merged = {
            "name": row.name,
            "description": row.description,
            "status_value": row.status,
            "is_default": row.is_default,
            "minimum_approvals": row.minimum_approvals,
            "rejection_threshold": row.rejection_threshold,
            "require_distinct_approvers": row.require_distinct_approvers,
            "block_requester_self_approval": row.block_requester_self_approval,
            "require_quorum_for_priority_bands_json": row.require_quorum_for_priority_bands_json,
            "require_quorum_for_source_types_json": row.require_quorum_for_source_types_json,
            "policy_json": row.policy_json,
        }
        for key in list(merged.keys()):
            source_key = "status" if key == "status_value" else key
            if source_key in payload and payload[source_key] is not None:
                merged[key] = payload[source_key]
            if source_key in payload and payload[source_key] is None and key in {"description"}:
                merged[key] = None
        normalized = self._normalize_autopilot_approval_policy_inputs(**merged)
        row.name = normalized["name"]
        row.description = normalized["description"]
        row.status = normalized["status"]
        row.is_default = normalized["is_default"]
        row.minimum_approvals = normalized["minimum_approvals"]
        row.rejection_threshold = normalized["rejection_threshold"]
        row.require_distinct_approvers = normalized["require_distinct_approvers"]
        row.block_requester_self_approval = normalized["block_requester_self_approval"]
        row.require_quorum_for_priority_bands_json = normalized["require_quorum_for_priority_bands_json"]
        row.require_quorum_for_source_types_json = normalized["require_quorum_for_source_types_json"]
        row.policy_json = normalized["policy_json"]
        row.updated_by_user_id = actor_user_id
        if row.is_default and row.status == "active":
            self._set_default_autopilot_approval_policy(organization_id=organization_id, policy_id=row.id)
        return row

    def archive_autopilot_approval_policy(
        self,
        *,
        organization_id: uuid.UUID,
        approval_policy_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotApprovalPolicy:
        row = self.require_autopilot_approval_policy(
            organization_id=organization_id,
            approval_policy_id=approval_policy_id,
        )
        if row.status != "archived":
            row.status = "archived"
            row.archived_at = self.now()
            row.is_default = False
            row.updated_by_user_id = actor_user_id
        return row

    def set_default_autopilot_approval_policy(
        self,
        *,
        organization_id: uuid.UUID,
        approval_policy_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotApprovalPolicy:
        row = self.require_autopilot_approval_policy(
            organization_id=organization_id,
            approval_policy_id=approval_policy_id,
        )
        if row.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only active approval policy can be default")
        row.is_default = True
        row.updated_by_user_id = actor_user_id
        self._set_default_autopilot_approval_policy(organization_id=organization_id, policy_id=row.id)
        return row

    def resolved_autopilot_approval_policy(
        self,
        *,
        organization_id: uuid.UUID,
        approval_policy_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        if approval_policy_id is not None:
            row = self.require_autopilot_approval_policy(
                organization_id=organization_id,
                approval_policy_id=approval_policy_id,
            )
            if row.status != "active" or row.archived_at is not None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Autopilot approval policy must be active")
            return self._autopilot_approval_policy_payload(row, resolved_source="explicit_policy")

        default_row = self.db.execute(
            select(GovernanceAutopilotApprovalPolicy).where(
                GovernanceAutopilotApprovalPolicy.organization_id == organization_id,
                GovernanceAutopilotApprovalPolicy.is_default.is_(True),
                GovernanceAutopilotApprovalPolicy.status == "active",
                GovernanceAutopilotApprovalPolicy.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if default_row is not None:
            return self._autopilot_approval_policy_payload(default_row, resolved_source="persisted_default")
        fallback = self._safe_fallback_autopilot_approval_policy()
        fallback["organization_id"] = organization_id
        return fallback

    def autopilot_approval_policy_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        total_policies = int(
            self.db.execute(
                select(func.count(GovernanceAutopilotApprovalPolicy.id)).where(
                    GovernanceAutopilotApprovalPolicy.organization_id == organization_id
                )
            ).scalar_one()
        )
        active_policies = int(
            self.db.execute(
                select(func.count(GovernanceAutopilotApprovalPolicy.id)).where(
                    GovernanceAutopilotApprovalPolicy.organization_id == organization_id,
                    GovernanceAutopilotApprovalPolicy.status == "active",
                )
            ).scalar_one()
        )
        archived_policies = int(
            self.db.execute(
                select(func.count(GovernanceAutopilotApprovalPolicy.id)).where(
                    GovernanceAutopilotApprovalPolicy.organization_id == organization_id,
                    GovernanceAutopilotApprovalPolicy.status == "archived",
                )
            ).scalar_one()
        )
        resolved = self.resolved_autopilot_approval_policy(organization_id=organization_id)
        return {
            "total_policies": total_policies,
            "active_policies": active_policies,
            "archived_policies": archived_policies,
            "default_policy_id": resolved.get("approval_policy_id"),
            "resolved_minimum_approvals": int(resolved.get("minimum_approvals") or 1),
            "resolved_rejection_threshold": int(resolved.get("rejection_threshold") or 1),
            "block_requester_self_approval": bool(resolved.get("block_requester_self_approval", True)),
            "caveat": AUTOPILOT_EXECUTION_QUORUM_CAVEAT,
        }

    def _validate_candidate_action_shape(self, *, candidate_action_json: Any) -> dict[str, Any]:
        if not isinstance(candidate_action_json, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="candidate_action_json must be an object")
        action_key = candidate_action_json.get("action_key")
        action_type = candidate_action_json.get("action_type")
        priority_band = candidate_action_json.get("priority_band")
        source_reason_codes = candidate_action_json.get("source_reason_codes")
        if not isinstance(action_key, str) or not action_key.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="candidate_action_json.action_key is required")
        if not isinstance(action_type, str) or not action_type.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="candidate_action_json.action_type is required")
        if priority_band not in AUTOPILOT_PRIORITY_BANDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="candidate_action_json.priority_band is invalid")
        if not isinstance(source_reason_codes, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="candidate_action_json.source_reason_codes must be an array",
            )
        normalized_reason_codes: list[str] = []
        for item in source_reason_codes:
            if not isinstance(item, str) or not item.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="candidate_action_json.source_reason_codes must contain strings",
                )
            normalized_reason_codes.append(item.strip())
        normalized = dict(candidate_action_json)
        normalized["action_key"] = action_key.strip()
        normalized["action_type"] = action_type.strip()
        normalized["priority_band"] = priority_band
        normalized["source_reason_codes"] = sorted(set(normalized_reason_codes))
        # SECURITY: risk_tier must never be trusted from client input. It is always
        # derived server-side from action_key/action_type so a caller cannot
        # self-declare a destructive action (e.g. delete_evidence) as low-risk to
        # bypass the human-approval gate. Any client-supplied risk_tier is ignored.
        normalized["risk_tier"] = self.classify_candidate_action_risk_tier(
            action_key=normalized["action_key"],
            action_type=normalized["action_type"],
        )
        # SECURITY: confidence_score is likewise never accepted from client input on
        # this path -- it is the value the internal candidate-generation pipeline
        # uses (AUTOPILOT_DEFAULT_CONFIDENCE_SCORE), never a caller-attested number,
        # since a self-declared 1.0 could otherwise force auto-execution.
        normalized["confidence_score"] = AUTOPILOT_DEFAULT_CONFIDENCE_SCORE
        return normalized

    def evaluate_candidate_action_against_policy(
        self,
        *,
        organization_id: uuid.UUID,
        candidate_action_json: dict[str, Any],
        policy_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        action = self._validate_candidate_action_shape(candidate_action_json=candidate_action_json)
        policy = self.resolved_autopilot_policy(organization_id=organization_id, policy_id=policy_id)
        blocked_reasons: list[str] = []
        requires_human_approval = False

        mode = str(policy["mode"])
        if mode == "disabled":
            blocked_reasons.append("policy_mode_disabled")
        if mode == "observe_only":
            blocked_reasons.append("policy_mode_observe_only")

        action_type = str(action["action_type"])
        action_band = str(action["priority_band"])
        action_risk_tier = str(action["risk_tier"])
        confidence_score = float(action["confidence_score"])
        reason_codes = set(str(code) for code in action.get("source_reason_codes", []))

        allowed_action_types = set(str(v) for v in policy.get("allowed_action_types_json", []))
        blocked_action_types = set(str(v) for v in policy.get("blocked_action_types_json", []))
        allowed_reason_codes = set(str(v) for v in policy.get("allowed_signal_reason_codes_json", []))
        blocked_reason_codes = set(str(v) for v in policy.get("blocked_signal_reason_codes_json", []))
        approval_action_types = set(str(v) for v in policy.get("approval_required_action_types_json", []))
        approval_bands = set(str(v) for v in policy.get("approval_required_priority_bands_json", []))
        max_auto_band = str(policy.get("max_allowed_priority_band_for_auto") or "low")

        if action_type in blocked_action_types:
            blocked_reasons.append("action_type_blocked")
        if allowed_action_types and action_type not in allowed_action_types:
            blocked_reasons.append("action_type_not_in_allowlist")
        if blocked_reason_codes.intersection(reason_codes):
            blocked_reasons.append("source_reason_code_blocked")
        if allowed_reason_codes and not allowed_reason_codes.intersection(reason_codes):
            blocked_reasons.append("source_reason_code_not_in_allowlist")

        if self._autopilot_band_rank(action_band) > self._autopilot_band_rank(max_auto_band):
            requires_human_approval = True
        if action_type in approval_action_types:
            requires_human_approval = True
        if action_band in approval_bands:
            requires_human_approval = True
        if action_risk_tier == "high":
            requires_human_approval = True

        if bool(action.get("automation_allowed")) and not bool(policy.get("external_effects_allowed", False)):
            blocked_reasons.append("external_effects_not_allowed")
        if not bool(policy.get("task_creation_allowed", False)) and action_type == "create_task":
            blocked_reasons.append("task_creation_not_allowed")
        if not bool(policy.get("review_creation_allowed", False)) and action_type == "create_review":
            blocked_reasons.append("review_creation_not_allowed")
        if not bool(policy.get("source_record_mutation_allowed", False)) and action_type == "update_record":
            blocked_reasons.append("source_record_mutation_not_allowed")

        allowed = len(blocked_reasons) == 0
        if not allowed:
            policy_decision = "blocked"
        elif requires_human_approval:
            policy_decision = "requires_approval"
        else:
            policy_decision = "allowed"

        return {
            "allowed_by_policy": allowed,
            "required_mode": mode,
            "requires_human_approval": requires_human_approval,
            "risk_tier": action_risk_tier,
            "confidence_score": confidence_score,
            "blocked_reasons": sorted(set(blocked_reasons)),
            "policy_decision": policy_decision,
            "policy_explanation_json": {
                "mode": mode,
                "resolved_policy_id": str(policy.get("policy_id")) if policy.get("policy_id") else None,
                "resolved_source": policy.get("resolved_source"),
                "checks": {
                    "action_type": action_type,
                    "priority_band": action_band,
                    "risk_tier": action_risk_tier,
                    "confidence_score": confidence_score,
                    "source_reason_codes": sorted(reason_codes),
                    "max_allowed_priority_band_for_auto": max_auto_band,
                    "approval_required_action_types_json": sorted(approval_action_types),
                    "approval_required_priority_bands_json": sorted(approval_bands),
                },
            },
            "caveat": AUTOPILOT_SAFE_FALLBACK_CAVEAT,
        }

    def evaluate_recommendation_snapshot_against_policy(
        self,
        *,
        organization_id: uuid.UUID,
        recommendation_snapshot_id: uuid.UUID,
        policy_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        snapshot = self.require_recommendation_snapshot(organization_id=organization_id, snapshot_id=recommendation_snapshot_id)
        actions = self._snapshot_candidate_actions_with_identity(snapshot=snapshot)
        decisions: list[dict[str, Any]] = []
        allowed_count = 0
        blocked_count = 0
        approval_required_count = 0
        for action in actions:
            decision = self.evaluate_candidate_action_against_policy(
                organization_id=organization_id,
                candidate_action_json=action,
                policy_id=policy_id,
            )
            decisions.append(
                {
                    "action_identity_hash": action["action_identity_hash"],
                    "action_key": action.get("action_key"),
                    "target_entity_type": action.get("target_entity_type"),
                    "target_entity_id": action.get("target_entity_id"),
                    "priority_band": action.get("priority_band"),
                    "decision": decision,
                }
            )
            if decision["allowed_by_policy"]:
                allowed_count += 1
            else:
                blocked_count += 1
            if decision["requires_human_approval"]:
                approval_required_count += 1
        return {
            "snapshot_id": snapshot.id,
            "total_actions": len(actions),
            "allowed_count": allowed_count,
            "blocked_count": blocked_count,
            "approval_required_count": approval_required_count,
            "decisions": decisions,
            "caveat": AUTOPILOT_SAFE_FALLBACK_CAVEAT,
        }

    def evaluate_copilot_draft_snapshot_against_policy(
        self,
        *,
        organization_id: uuid.UUID,
        copilot_draft_snapshot_id: uuid.UUID,
        policy_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        snapshot = self.db.execute(
            select(GovernanceCopilotDraftSnapshot).where(
                GovernanceCopilotDraftSnapshot.organization_id == organization_id,
                GovernanceCopilotDraftSnapshot.id == copilot_draft_snapshot_id,
            )
        ).scalar_one_or_none()
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copilot draft snapshot not found")
        policy = self.resolved_autopilot_policy(organization_id=organization_id, policy_id=policy_id)
        draft_type = str(snapshot.draft_type)
        blocked_reasons: list[str] = []
        mode = str(policy["mode"])
        requires_human_approval = False

        if mode == "disabled":
            blocked_reasons.append("policy_mode_disabled")
        if mode == "observe_only":
            blocked_reasons.append("policy_mode_observe_only")

        allowed_draft_types = set(str(v) for v in policy.get("allowed_draft_types_json", []))
        blocked_draft_types = set(str(v) for v in policy.get("blocked_draft_types_json", []))
        if draft_type in blocked_draft_types:
            blocked_reasons.append("draft_type_blocked")
        if allowed_draft_types and draft_type not in allowed_draft_types:
            blocked_reasons.append("draft_type_not_in_allowlist")
        if mode in {"require_approval", "execute_safe_later"}:
            requires_human_approval = True
        allowed = len(blocked_reasons) == 0

        return {
            "snapshot_id": snapshot.id,
            "draft_type": draft_type,
            "allowed_by_policy": allowed,
            "requires_human_approval": requires_human_approval,
            "blocked_reasons": sorted(set(blocked_reasons)),
            "policy_explanation_json": {
                "mode": mode,
                "resolved_policy_id": str(policy.get("policy_id")) if policy.get("policy_id") else None,
                "resolved_source": policy.get("resolved_source"),
                "checks": {
                    "draft_type": draft_type,
                    "allowed_draft_types_json": sorted(allowed_draft_types),
                    "blocked_draft_types_json": sorted(blocked_draft_types),
                },
            },
            "caveat": AUTOPILOT_SAFE_FALLBACK_CAVEAT,
        }

    def autopilot_policy_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        total_policies = int(
            self.db.execute(
                select(func.count(GovernanceAutopilotPolicy.id)).where(
                    GovernanceAutopilotPolicy.organization_id == organization_id
                )
            ).scalar_one()
        )
        active_policies = int(
            self.db.execute(
                select(func.count(GovernanceAutopilotPolicy.id)).where(
                    GovernanceAutopilotPolicy.organization_id == organization_id,
                    GovernanceAutopilotPolicy.status == "active",
                )
            ).scalar_one()
        )
        archived_policies = int(
            self.db.execute(
                select(func.count(GovernanceAutopilotPolicy.id)).where(
                    GovernanceAutopilotPolicy.organization_id == organization_id,
                    GovernanceAutopilotPolicy.status == "archived",
                )
            ).scalar_one()
        )
        resolved = self.resolved_autopilot_policy(organization_id=organization_id)
        return {
            "total_policies": total_policies,
            "active_policies": active_policies,
            "archived_policies": archived_policies,
            "default_policy_id": resolved.get("policy_id"),
            "resolved_mode": resolved["mode"],
            "external_effects_allowed": bool(resolved["external_effects_allowed"]),
            "task_creation_allowed": bool(resolved["task_creation_allowed"]),
            "review_creation_allowed": bool(resolved["review_creation_allowed"]),
            "source_record_mutation_allowed": bool(resolved["source_record_mutation_allowed"]),
            "caveat": AUTOPILOT_SAFE_FALLBACK_CAVEAT,
        }

    @classmethod
    def autopilot_capabilities(cls) -> dict[str, Any]:
        capabilities = []
        for item in AUTOPILOT_CAPABILITY_MATRIX:
            row = dict(item)
            row["caveat"] = AUTOPILOT_EXECUTION_INTENT_CAVEAT
            capabilities.append(row)
        capabilities.sort(key=lambda x: str(x["capability_key"]))
        return {"capabilities": capabilities, "caveat": AUTOPILOT_EXECUTION_INTENT_CAVEAT}

    @classmethod
    def _capability_by_action_type(cls) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for item in AUTOPILOT_CAPABILITY_MATRIX:
            out[str(item["action_type"])] = dict(item)
        return out

    @classmethod
    def _autopilot_source_hash(cls, payload: dict[str, Any]) -> str:
        return cls.sha256_hexdigest(payload)

    @classmethod
    def _autopilot_intent_hash(cls, payload: dict[str, Any]) -> str:
        return cls.sha256_hexdigest(payload)

    def _evaluate_capability_for_candidate_action(
        self,
        *,
        organization_id: uuid.UUID,
        candidate_action_json: dict[str, Any],
        policy_id: uuid.UUID | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        policy_eval = self.evaluate_candidate_action_against_policy(
            organization_id=organization_id,
            candidate_action_json=candidate_action_json,
            policy_id=policy_id,
        )
        action = self._validate_candidate_action_shape(candidate_action_json=candidate_action_json)
        capability = self._capability_by_action_type().get(
            str(action.get("action_type")),
            {
                "capability_key": "unknown_action_type",
                "action_type": str(action.get("action_type")),
                "description": "No explicit capability mapping defined; deny by default.",
                "default_allowed": False,
                "requires_policy_allow": True,
                "requires_human_approval": True,
                "external_effects": False,
                "creates_task": False,
                "creates_review": False,
                "mutates_source_record": False,
                "allowed_in_phase_7_1": False,
            },
        )
        blocked_reasons = list(policy_eval["blocked_reasons"])
        if not bool(capability.get("allowed_in_phase_7_1", False)):
            blocked_reasons.append("capability_not_allowed_in_phase_7_1")
        blocked = (not bool(policy_eval["allowed_by_policy"])) or (len(blocked_reasons) > 0)
        requires_human_approval = bool(policy_eval["requires_human_approval"]) or bool(
            capability.get("requires_human_approval", False)
        )
        decision = {
            "action_key": action.get("action_key"),
            "target_entity_type": action.get("target_entity_type"),
            "target_entity_id": action.get("target_entity_id"),
            "related_ai_system_id": action.get("related_ai_system_id"),
            "related_risk_assessment_id": action.get("related_risk_assessment_id"),
            "priority_band": action.get("priority_band"),
            "risk_tier": action.get("risk_tier"),
            "confidence_score": action.get("confidence_score"),
            "capability_key": capability.get("capability_key"),
            "allowed_in_phase_7_1": bool(capability.get("allowed_in_phase_7_1", False)),
            "allowed_by_policy": bool(policy_eval["allowed_by_policy"]) and not blocked,
            "approval_required": requires_human_approval,
            "blocked": blocked,
            "blocked_reasons": sorted(set(blocked_reasons)),
            "policy_decision": policy_eval["policy_decision"],
            "policy_explanation_json": dict(policy_eval["policy_explanation_json"]),
            "capability": {**capability, "caveat": AUTOPILOT_EXECUTION_INTENT_CAVEAT},
            "caveat": AUTOPILOT_EXECUTION_INTENT_CAVEAT,
        }
        return decision, policy_eval

    def preview_execution_intent_candidate_action(
        self,
        *,
        organization_id: uuid.UUID,
        candidate_action_json: dict[str, Any],
        policy_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        action = self._validate_candidate_action_shape(candidate_action_json=candidate_action_json)
        decision, _ = self._evaluate_capability_for_candidate_action(
            organization_id=organization_id,
            candidate_action_json=action,
            policy_id=policy_id,
        )
        source_hash = self._autopilot_source_hash(
            {
                "source_type": "candidate_action",
                "candidate_action": action,
            }
        )
        blocked_reasons = list(decision["blocked_reasons"])
        return {
            "source_type": "candidate_action",
            "source_id": None,
            "plan_payload_json": {
                "source_type": "candidate_action",
                "candidate_action": action,
                "decisions": [decision],
                "algorithm": "autopilot_execution_intent_preview_v1",
            },
            "capability_decisions_json": {"decisions": [decision]},
            "approval_required": bool(decision["approval_required"]),
            "blocked": bool(decision["blocked"]),
            "blocked_reasons": blocked_reasons,
            "source_entities_json": {
                "source_type": "candidate_action",
                "target_entity_type": action.get("target_entity_type"),
                "target_entity_id": action.get("target_entity_id"),
                "related_ai_system_id": action.get("related_ai_system_id"),
                "related_risk_assessment_id": action.get("related_risk_assessment_id"),
            },
            "source_hash": source_hash,
            "caveat": AUTOPILOT_EXECUTION_INTENT_CAVEAT,
        }

    def preview_execution_intent_recommendation_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        recommendation_snapshot_id: uuid.UUID,
        policy_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        snapshot = self.require_recommendation_snapshot(
            organization_id=organization_id, snapshot_id=recommendation_snapshot_id
        )
        actions = self._snapshot_candidate_actions_with_identity(snapshot=snapshot)
        decisions: list[dict[str, Any]] = []
        blocked_reasons: list[str] = []
        approval_required = False
        blocked = False
        for action in actions:
            decision, _ = self._evaluate_capability_for_candidate_action(
                organization_id=organization_id,
                candidate_action_json=action,
                policy_id=policy_id,
            )
            decisions.append(decision)
            blocked_reasons.extend(list(decision["blocked_reasons"]))
            approval_required = approval_required or bool(decision["approval_required"])
            blocked = blocked or bool(decision["blocked"])
        source_hash = self._autopilot_source_hash(
            {
                "source_type": "recommendation_snapshot",
                "source_id": str(snapshot.id),
                "source_candidate_hash": snapshot.source_candidate_hash,
                "actions": actions,
            }
        )
        return {
            "source_type": "recommendation_snapshot",
            "source_id": snapshot.id,
            "plan_payload_json": {
                "source_type": "recommendation_snapshot",
                "source_id": str(snapshot.id),
                "candidate_count": len(actions),
                "decisions": decisions,
                "algorithm": "autopilot_execution_intent_preview_v1",
            },
            "capability_decisions_json": {"decisions": decisions},
            "approval_required": approval_required,
            "blocked": blocked,
            "blocked_reasons": sorted(set(blocked_reasons)),
            "source_entities_json": {
                "source_type": "recommendation_snapshot",
                "recommendation_snapshot_id": str(snapshot.id),
                "scope_type": snapshot.scope_type,
                "scope_id": str(snapshot.scope_id) if snapshot.scope_id else None,
            },
            "source_hash": source_hash,
            "caveat": AUTOPILOT_EXECUTION_INTENT_CAVEAT,
        }

    def preview_execution_intent_copilot_draft_snapshot(
        self,
        *,
        organization_id: uuid.UUID,
        copilot_draft_snapshot_id: uuid.UUID,
        policy_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        eval_payload = self.evaluate_copilot_draft_snapshot_against_policy(
            organization_id=organization_id,
            copilot_draft_snapshot_id=copilot_draft_snapshot_id,
            policy_id=policy_id,
        )
        snapshot = self.db.execute(
            select(GovernanceCopilotDraftSnapshot).where(
                GovernanceCopilotDraftSnapshot.organization_id == organization_id,
                GovernanceCopilotDraftSnapshot.id == copilot_draft_snapshot_id,
            )
        ).scalar_one_or_none()
        if snapshot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copilot draft snapshot not found")
        source_hash = self._autopilot_source_hash(
            {
                "source_type": "copilot_draft_snapshot",
                "source_id": str(snapshot.id),
                "draft_type": snapshot.draft_type,
                "scope_type": snapshot.scope_type,
                "scope_id": str(snapshot.scope_id) if snapshot.scope_id else None,
                "source_context_hash": snapshot.source_context_hash,
            }
        )
        blocked_reasons = list(eval_payload.get("blocked_reasons", []))
        return {
            "source_type": "copilot_draft_snapshot",
            "source_id": snapshot.id,
            "plan_payload_json": {
                "source_type": "copilot_draft_snapshot",
                "source_id": str(snapshot.id),
                "draft_type": snapshot.draft_type,
                "scope_type": snapshot.scope_type,
                "scope_id": str(snapshot.scope_id) if snapshot.scope_id else None,
                "decision": eval_payload,
                "algorithm": "autopilot_execution_intent_preview_v1",
            },
            "capability_decisions_json": {"decision": eval_payload},
            "approval_required": bool(eval_payload["requires_human_approval"]),
            "blocked": not bool(eval_payload["allowed_by_policy"]),
            "blocked_reasons": blocked_reasons,
            "source_entities_json": {
                "source_type": "copilot_draft_snapshot",
                "copilot_draft_snapshot_id": str(snapshot.id),
                "draft_type": snapshot.draft_type,
                "scope_type": snapshot.scope_type,
                "scope_id": str(snapshot.scope_id) if snapshot.scope_id else None,
            },
            "source_hash": source_hash,
            "caveat": AUTOPILOT_EXECUTION_INTENT_CAVEAT,
        }

    def _governance_settings_for_org(self, *, organization_id: uuid.UUID) -> OrganizationGovernanceSetting:
        row = self.db.execute(
            select(OrganizationGovernanceSetting).where(OrganizationGovernanceSetting.organization_id == organization_id)
        ).scalar_one_or_none()
        if row is not None:
            return row
        row = OrganizationGovernanceSetting(
            organization_id=organization_id,
            batch_cancellation_requires_approval=False,
            batch_cancellation_policy_reason=None,
            autopilot_auto_execute_enabled=False,
            autopilot_auto_execute_confidence_threshold=AUTOPILOT_DEFAULT_AUTO_EXECUTE_THRESHOLD,
            autopilot_auto_execute_reversal_window_hours=AUTOPILOT_DEFAULT_REVERSAL_WINDOW_HOURS,
            updated_by_user_id=None,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _autopilot_admin_members(self, *, organization_id: uuid.UUID) -> list[tuple[User, str]]:
        rows = self.db.execute(
            select(User, Role.name)
            .join(Membership, Membership.user_id == User.id)
            .join(Role, Role.id == Membership.role_id)
            .where(
                Membership.organization_id == organization_id,
                Membership.status == "active",
                Role.name.in_(["owner", "admin"]),
                User.is_active.is_(True),
                User.status == "active",
            )
            .order_by(Role.name.asc(), User.created_at.asc())
        ).all()
        out: list[tuple[User, str]] = []
        seen_user_ids: set[uuid.UUID] = set()
        for user_row, role_name in rows:
            if user_row.id in seen_user_ids:
                continue
            seen_user_ids.add(user_row.id)
            out.append((user_row, str(role_name)))
        return out

    def _queue_autopilot_notification(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        subject_title: str,
        details_json: dict[str, Any],
    ) -> int:
        SeedService.ensure_global_email_templates(self.db)
        template = EmailService(self.db).resolve_template_for_org(
            organization_id=organization_id,
            template_id=None,
            template_key="task_assigned",
        )
        sent = 0
        for user_row, _role_name in self._autopilot_admin_members(organization_id=organization_id):
            if not user_row.email:
                continue
            EmailService(self.db).queue_email(
                organization_id=organization_id,
                template=template,
                event_type="autopilot.auto_execution",
                recipient_email=user_row.email,
                recipient_user_id=user_row.id,
                priority="high",
                scheduled_at=None,
                metadata_json={
                    "notification_type": "autopilot_auto_execution",
                    "severity": "high",
                    **details_json,
                },
                created_by_user_id=actor_user_id or user_row.id,
                variables_json={
                    "user_name": user_row.full_name or user_row.email,
                    "task_title": subject_title,
                },
                initial_status="queued",
            )
            sent += 1
        return sent

    def _execute_action_flag_stale_evidence(
        self,
        *,
        organization_id: uuid.UUID,
        action: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        target_entity_id = action.get("target_entity_id")
        if target_entity_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target_entity_id is required for flag_stale_evidence")
        assessment = self.require_assessment(organization_id=organization_id, assessment_id=uuid.UUID(str(target_entity_id)))
        old_value = assessment.mitigation_summary
        marker = "[AUTOPILOT] Evidence flagged stale for manual review."
        assessment.mitigation_summary = marker if not old_value else f"{old_value}\n{marker}"
        before = {"operation": "flag_stale_evidence", "assessment_id": str(assessment.id), "mitigation_summary": old_value}
        after = {"operation": "flag_stale_evidence", "assessment_id": str(assessment.id), "mitigation_summary": assessment.mitigation_summary}
        metadata = {"operation": "flag_stale_evidence", "assessment_id": str(assessment.id)}
        return before, after, metadata

    def _execute_action_send_reminder(
        self,
        *,
        organization_id: uuid.UUID,
        action: dict[str, Any],
        actor_user_id: uuid.UUID | None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        target_entity_type = str(action.get("target_entity_type") or "risk_assessment")
        target_entity_id = action.get("target_entity_id")
        linked_entity_id = uuid.UUID(str(target_entity_id)) if target_entity_id else None
        task = Task(
            organization_id=organization_id,
            title=str(action.get("title") or "Autopilot reminder"),
            description=str(action.get("description") or "Autopilot-generated reminder"),
            status="open",
            priority="high",
            task_type="governance_followup",
            owner_user_id=actor_user_id,
            created_by_user_id=actor_user_id,
            linked_entity_type=target_entity_type,
            linked_entity_id=linked_entity_id,
            source="autopilot",
            reminder_status="none",
            metadata_json={
                "autopilot": True,
                "action_key": action.get("action_key"),
                "risk_tier": action.get("risk_tier"),
                "confidence_score": action.get("confidence_score"),
            },
        )
        self.db.add(task)
        self.db.flush()
        before = {"operation": "send_reminder", "task_id": None}
        after = {
            "operation": "send_reminder",
            "task_id": str(task.id),
            "linked_entity_type": target_entity_type,
            "linked_entity_id": str(linked_entity_id) if linked_entity_id else None,
        }
        metadata = {"operation": "send_reminder", "task_id": str(task.id)}
        return before, after, metadata

    def _execute_action_refresh_signals(
        self,
        *,
        organization_id: uuid.UUID,
        action: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        target_entity_id = action.get("target_entity_id") or action.get("related_risk_assessment_id")
        if target_entity_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="target_entity_id is required for refresh_signals")
        assessment = self.require_assessment(organization_id=organization_id, assessment_id=uuid.UUID(str(target_entity_id)))
        before_risk_factors = dict(assessment.risk_factors_json or {}) if isinstance(assessment.risk_factors_json, dict) else {}
        updated = dict(before_risk_factors)
        updated["autopilot_last_refresh_at"] = self.now().isoformat()
        assessment.risk_factors_json = updated
        before = {"operation": "refresh_signals", "assessment_id": str(assessment.id), "risk_factors_json": before_risk_factors}
        after = {"operation": "refresh_signals", "assessment_id": str(assessment.id), "risk_factors_json": updated}
        metadata = {"operation": "refresh_signals", "assessment_id": str(assessment.id)}
        return before, after, metadata

    def _auto_execute_candidate_action(
        self,
        *,
        organization_id: uuid.UUID,
        intent: GovernanceAutopilotExecutionIntent,
        action: dict[str, Any],
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotExecution:
        settings = self._governance_settings_for_org(organization_id=organization_id)
        reversal_window_hours = int(
            settings.autopilot_auto_execute_reversal_window_hours
            if settings.autopilot_auto_execute_reversal_window_hours
            else AUTOPILOT_DEFAULT_REVERSAL_WINDOW_HOURS
        )
        # SECURITY: an auto-execution must never happen silently. If the org has no
        # active owner/admin to notify, block the auto-execution entirely (rather
        # than executing with notification_count == 0) so a human is guaranteed to
        # see it before it can happen unnoticed.
        if not self._autopilot_admin_members(organization_id=organization_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Autopilot auto-execution blocked: organization has no active owner/admin to notify",
            )
        action_key = str(action.get("action_key") or "").strip()
        action_type = str(action.get("action_type") or "").strip()
        if action_key == "flag_stale_evidence":
            before_snapshot, after_snapshot, op_meta = self._execute_action_flag_stale_evidence(
                organization_id=organization_id,
                action=action,
            )
        elif action_key == "send_reminder":
            before_snapshot, after_snapshot, op_meta = self._execute_action_send_reminder(
                organization_id=organization_id,
                action=action,
                actor_user_id=actor_user_id,
            )
        elif action_type == "refresh_signals":
            before_snapshot, after_snapshot, op_meta = self._execute_action_refresh_signals(
                organization_id=organization_id,
                action=action,
            )
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported auto-execution action")

        row = GovernanceAutopilotExecution(
            organization_id=organization_id,
            execution_intent_id=intent.id,
            action_key=action_key,
            action_type=action_type,
            risk_tier=str(action.get("risk_tier")),
            confidence_score=float(action.get("confidence_score") or AUTOPILOT_DEFAULT_CONFIDENCE_SCORE),
            target_entity_type=action.get("target_entity_type"),
            target_entity_id=uuid.UUID(str(action["target_entity_id"])) if action.get("target_entity_id") else None,
            execution_status="executed",
            before_snapshot_json=self.to_json_compatible(before_snapshot),
            after_snapshot_json=self.to_json_compatible(after_snapshot),
            reversal_deadline_at=self.now() + timedelta(hours=max(1, reversal_window_hours)),
            metadata_json=self.to_json_compatible(
                {
                    "mode": "auto_execute",
                    "operation": op_meta.get("operation"),
                    "intent_id": str(intent.id),
                }
            ),
        )
        self.db.add(row)
        self.db.flush()
        notification_count = self._queue_autopilot_notification(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            subject_title=f"Autopilot auto-executed: {action_key}",
            details_json={
                "execution_id": str(row.id),
                "intent_id": str(intent.id),
                "action_key": action_key,
                "risk_tier": row.risk_tier,
            },
        )
        row.metadata_json = self.to_json_compatible(
            {
                **dict(row.metadata_json or {}),
                "notification_count": notification_count,
            }
        )
        self._run_autopilot_circuit_breaker(organization_id=organization_id, actor_user_id=actor_user_id)
        return row

    def _should_auto_execute_action(
        self,
        *,
        organization_id: uuid.UUID,
        action: dict[str, Any],
        policy_preview: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        settings = self._governance_settings_for_org(organization_id=organization_id)
        risk_tier = str(action.get("risk_tier"))
        confidence_score = float(action.get("confidence_score") or AUTOPILOT_DEFAULT_CONFIDENCE_SCORE)
        threshold = float(
            settings.autopilot_auto_execute_confidence_threshold
            if settings.autopilot_auto_execute_confidence_threshold is not None
            else AUTOPILOT_DEFAULT_AUTO_EXECUTE_THRESHOLD
        )
        if risk_tier != "low":
            reasons.append("risk_tier_not_low")
        if risk_tier == "high":
            reasons.append("high_risk_requires_human_approval")
        if confidence_score < threshold:
            reasons.append("confidence_below_threshold")
        if not bool(action.get("automation_allowed", False)):
            reasons.append("action_not_marked_automation_allowed")
        if not bool(policy_preview.get("allowed_by_policy")):
            reasons.append("policy_denied")
        if bool(policy_preview.get("requires_human_approval", False)):
            reasons.append("policy_requires_human_approval")
        if not bool(settings.autopilot_auto_execute_enabled):
            reasons.append("organization_not_opted_in")
        return (len(reasons) == 0, sorted(set(reasons)))

    def _run_autopilot_circuit_breaker(self, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> None:
        settings = self._governance_settings_for_org(organization_id=organization_id)
        if not bool(settings.autopilot_auto_execute_enabled):
            return
        now = self.now()
        lookback_start = now - timedelta(hours=AUTOPILOT_CIRCUIT_BREAKER_WINDOW_HOURS)
        rows = list(
            self.db.execute(
                select(
                    GovernanceAutopilotExecution.created_at,
                    GovernanceAutopilotExecution.reversed_at,
                ).where(
                    GovernanceAutopilotExecution.organization_id == organization_id,
                    GovernanceAutopilotExecution.created_at >= lookback_start,
                )
            ).all()
        )
        total_window = len(rows)
        reversed_window = int(sum(1 for _created_at, reversed_at in rows if reversed_at is not None))
        reversal_rate = (reversed_window / total_window) if total_window else 0.0

        spike_start = now - timedelta(hours=AUTOPILOT_CIRCUIT_BREAKER_SPIKE_WINDOW_HOURS)
        current_window_count = int(
            sum(1 for created_at, _ in rows if (self.as_utc(created_at) or now) >= spike_start)
        )
        previous_span_hours = max(1, AUTOPILOT_CIRCUIT_BREAKER_WINDOW_HOURS - AUTOPILOT_CIRCUIT_BREAKER_SPIKE_WINDOW_HOURS)
        previous_window_count = int(
            sum(
                1
                for created_at, _ in rows
                if lookback_start <= (self.as_utc(created_at) or now) < spike_start
            )
        )
        baseline_per_hour = previous_window_count / previous_span_hours
        spike_threshold = max(
            AUTOPILOT_CIRCUIT_BREAKER_SPIKE_MIN_EXECUTIONS,
            int(round(baseline_per_hour * AUTOPILOT_CIRCUIT_BREAKER_SPIKE_MULTIPLIER)),
        )

        trip_reasons: list[str] = []
        if total_window >= AUTOPILOT_CIRCUIT_BREAKER_MIN_SAMPLE_SIZE and reversal_rate > AUTOPILOT_CIRCUIT_BREAKER_REVERSAL_RATE_THRESHOLD:
            trip_reasons.append("reversal_rate_threshold_breached")
        # SECURITY: a low absolute execution count must not be usable to stay under
        # AUTOPILOT_CIRCUIT_BREAKER_MIN_SAMPLE_SIZE while every single execution in
        # a smaller window is reversed. Trip unconditionally on a 100% reversal rate
        # once a minimal sample exists, regardless of total volume.
        if total_window >= AUTOPILOT_CIRCUIT_BREAKER_ABSOLUTE_REVERSAL_MIN_SAMPLE_SIZE and reversal_rate >= 1.0:
            trip_reasons.append("full_reversal_rate_detected")
        if current_window_count >= spike_threshold and current_window_count >= AUTOPILOT_CIRCUIT_BREAKER_SPIKE_MIN_EXECUTIONS:
            trip_reasons.append("execution_volume_spike_detected")
        if not trip_reasons:
            return

        settings.autopilot_auto_execute_enabled = False
        settings.updated_by_user_id = actor_user_id
        self.db.flush()
        self._queue_autopilot_notification(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            subject_title="Autopilot auto-execution disabled by circuit breaker",
            details_json={
                "reasons": trip_reasons,
                "total_window": total_window,
                "reversed_window": reversed_window,
                "reversal_rate": round(reversal_rate, 6),
                "current_window_count": current_window_count,
                "spike_threshold": spike_threshold,
            },
        )

    def require_autopilot_execution(
        self,
        *,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
    ) -> GovernanceAutopilotExecution:
        row = self.db.execute(
            select(GovernanceAutopilotExecution).where(
                GovernanceAutopilotExecution.organization_id == organization_id,
                GovernanceAutopilotExecution.id == execution_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Autopilot execution not found")
        return row

    def list_autopilot_executions(
        self,
        *,
        organization_id: uuid.UUID,
        execution_status: str | None,
        execution_intent_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceAutopilotExecution]:
        query = select(GovernanceAutopilotExecution).where(
            GovernanceAutopilotExecution.organization_id == organization_id
        )
        if execution_status is not None:
            query = query.where(GovernanceAutopilotExecution.execution_status == execution_status)
        if execution_intent_id is not None:
            query = query.where(GovernanceAutopilotExecution.execution_intent_id == execution_intent_id)
        query = query.order_by(
            GovernanceAutopilotExecution.created_at.desc(),
            GovernanceAutopilotExecution.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def reverse_autopilot_execution(
        self,
        *,
        organization_id: uuid.UUID,
        execution_id: uuid.UUID,
        reason: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotExecution:
        row = self.require_autopilot_execution(organization_id=organization_id, execution_id=execution_id)
        now = self.now()
        if row.reversed_at is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Execution has already been reversed")
        deadline = self.as_utc(row.reversal_deadline_at)
        if deadline is not None and now > deadline:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Reversal window has expired")

        operation = str((row.metadata_json or {}).get("operation") or "")
        before_snapshot = dict(row.before_snapshot_json or {}) if isinstance(row.before_snapshot_json, dict) else {}
        after_snapshot = dict(row.after_snapshot_json or {}) if isinstance(row.after_snapshot_json, dict) else {}

        if operation == "flag_stale_evidence":
            assessment = self.require_assessment(
                organization_id=organization_id,
                assessment_id=uuid.UUID(str(before_snapshot.get("assessment_id"))),
            )
            assessment.mitigation_summary = before_snapshot.get("mitigation_summary")
        elif operation == "refresh_signals":
            assessment = self.require_assessment(
                organization_id=organization_id,
                assessment_id=uuid.UUID(str(before_snapshot.get("assessment_id"))),
            )
            assessment.risk_factors_json = before_snapshot.get("risk_factors_json")
        elif operation == "send_reminder":
            task_id = after_snapshot.get("task_id")
            if task_id:
                task = self.db.get(Task, uuid.UUID(str(task_id)))
                if task is not None and task.organization_id == organization_id:
                    self.db.delete(task)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Execution cannot be reversed")

        row.execution_status = "reversed"
        row.reversed_at = now
        row.reversed_by_user_id = actor_user_id
        row.reversal_reason = reason
        row.reversal_snapshot_json = self.to_json_compatible(
            {
                "operation": operation,
                "reversed_at": now.isoformat(),
                "reason": reason,
            }
        )
        self.db.flush()
        self._run_autopilot_circuit_breaker(organization_id=organization_id, actor_user_id=actor_user_id)
        return row

    @staticmethod
    def autopilot_execution_payload(row: GovernanceAutopilotExecution) -> dict[str, Any]:
        return {
            "id": row.id,
            "execution_id": row.id,
            "organization_id": row.organization_id,
            "execution_intent_id": row.execution_intent_id,
            "action_key": row.action_key,
            "action_type": row.action_type,
            "risk_tier": row.risk_tier,
            "confidence_score": float(row.confidence_score),
            "target_entity_type": row.target_entity_type,
            "target_entity_id": row.target_entity_id,
            "execution_status": row.execution_status,
            "before_snapshot_json": row.before_snapshot_json,
            "after_snapshot_json": row.after_snapshot_json,
            "reversal_deadline_at": row.reversal_deadline_at,
            "reversed_at": row.reversed_at,
            "reversed_by_user_id": row.reversed_by_user_id,
            "reversal_reason": row.reversal_reason,
            "reversal_snapshot_json": row.reversal_snapshot_json,
            "metadata_json": row.metadata_json,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def create_execution_intent(
        self,
        *,
        organization_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID | None,
        candidate_action_json: dict[str, Any] | None,
        policy_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotExecutionIntent:
        source_type = validate_choice(source_type, AUTOPILOT_EXECUTION_INTENT_SOURCE_TYPES, "source_type", status_code=status.HTTP_400_BAD_REQUEST)
        if source_type == "candidate_action":
            if candidate_action_json is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="candidate_action_json is required for candidate_action source_type",
                )
            preview = self.preview_execution_intent_candidate_action(
                organization_id=organization_id,
                candidate_action_json=candidate_action_json,
                policy_id=policy_id,
            )
        elif source_type == "recommendation_snapshot":
            if source_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="source_id is required for recommendation_snapshot source_type",
                )
            preview = self.preview_execution_intent_recommendation_snapshot(
                organization_id=organization_id,
                recommendation_snapshot_id=source_id,
                policy_id=policy_id,
            )
        else:
            if source_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="source_id is required for copilot_draft_snapshot source_type",
                )
            preview = self.preview_execution_intent_copilot_draft_snapshot(
                organization_id=organization_id,
                copilot_draft_snapshot_id=source_id,
                policy_id=policy_id,
            )

        blocked = bool(preview["blocked"])
        approval_required = bool(preview["approval_required"])
        auto_execute_now = False
        auto_execute_reasons: list[str] = []
        candidate_action_for_auto: dict[str, Any] | None = None
        if source_type == "candidate_action" and isinstance(preview.get("plan_payload_json"), dict):
            candidate_payload = preview["plan_payload_json"].get("candidate_action")
            if isinstance(candidate_payload, dict):
                candidate_action_for_auto = self._validate_candidate_action_shape(candidate_action_json=candidate_payload)
                policy_preview = self.evaluate_candidate_action_against_policy(
                    organization_id=organization_id,
                    candidate_action_json=candidate_action_for_auto,
                    policy_id=policy_id,
                )
                if candidate_action_for_auto["risk_tier"] == "high":
                    approval_required = True
                settings = self._governance_settings_for_org(organization_id=organization_id)
                threshold = float(
                    settings.autopilot_auto_execute_confidence_threshold
                    if settings.autopilot_auto_execute_confidence_threshold is not None
                    else AUTOPILOT_DEFAULT_AUTO_EXECUTE_THRESHOLD
                )
                if candidate_action_for_auto["risk_tier"] == "low" and float(candidate_action_for_auto["confidence_score"]) < threshold:
                    approval_required = True
                auto_execute_now, auto_execute_reasons = self._should_auto_execute_action(
                    organization_id=organization_id,
                    action=candidate_action_for_auto,
                    policy_preview=policy_preview,
                )
                preview["plan_payload_json"]["candidate_action"] = candidate_action_for_auto
        if blocked:
            intent_status = "blocked"
        elif approval_required:
            intent_status = "approval_required"
        else:
            intent_status = "planned"

        source_hash = str(preview["source_hash"])
        intent_sha256 = self._autopilot_intent_hash(
            {
                "source_type": source_type,
                "source_id": str(source_id) if source_id else None,
                "policy_id": str(policy_id) if policy_id else None,
                "plan_payload_json": preview["plan_payload_json"],
                "capability_decisions_json": preview["capability_decisions_json"],
                "approval_required": approval_required,
                "blocked": blocked,
                "blocked_reasons": preview["blocked_reasons"],
                "source_hash": source_hash,
            }
        )
        row = GovernanceAutopilotExecutionIntent(
            organization_id=organization_id,
            source_type=source_type,
            source_id=source_id if source_type != "candidate_action" else None,
            policy_id=policy_id,
            intent_status=intent_status,
            plan_payload_json=preview["plan_payload_json"],
            capability_decisions_json=preview["capability_decisions_json"],
            approval_required=approval_required,
            blocked=blocked,
            blocked_reasons_json=list(preview["blocked_reasons"]),
            source_entities_json=preview["source_entities_json"],
            source_hash=source_hash,
            intent_sha256=intent_sha256,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        if auto_execute_now and candidate_action_for_auto is not None and row.intent_status == "planned":
            self._auto_execute_candidate_action(
                organization_id=organization_id,
                intent=row,
                action=candidate_action_for_auto,
                actor_user_id=actor_user_id,
            )
        elif source_type == "candidate_action":
            row.plan_payload_json = self.to_json_compatible(
                {
                    **dict(row.plan_payload_json or {}),
                    "auto_execute": {
                        "eligible": bool(auto_execute_now),
                        "reasons": auto_execute_reasons,
                    },
                }
            )
        return row

    def list_execution_intents(
        self,
        *,
        organization_id: uuid.UUID,
        source_type: str | None,
        intent_status: str | None,
        policy_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceAutopilotExecutionIntent]:
        if source_type is not None:
            source_type = validate_choice(source_type, AUTOPILOT_EXECUTION_INTENT_SOURCE_TYPES, "source_type", status_code=status.HTTP_400_BAD_REQUEST)
        if intent_status is not None:
            intent_status = validate_choice(intent_status, AUTOPILOT_EXECUTION_INTENT_STATUS_VALUES, "intent_status", status_code=status.HTTP_400_BAD_REQUEST)
        if policy_id is not None:
            self.require_autopilot_policy(organization_id=organization_id, policy_id=policy_id)
        query = select(GovernanceAutopilotExecutionIntent).where(
            GovernanceAutopilotExecutionIntent.organization_id == organization_id
        )
        if source_type is not None:
            query = query.where(GovernanceAutopilotExecutionIntent.source_type == source_type)
        if intent_status is not None:
            query = query.where(GovernanceAutopilotExecutionIntent.intent_status == intent_status)
        if policy_id is not None:
            query = query.where(GovernanceAutopilotExecutionIntent.policy_id == policy_id)
        query = query.order_by(
            GovernanceAutopilotExecutionIntent.created_at.desc(),
            GovernanceAutopilotExecutionIntent.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def require_execution_intent(
        self,
        *,
        organization_id: uuid.UUID,
        intent_id: uuid.UUID,
    ) -> GovernanceAutopilotExecutionIntent:
        row = self.db.execute(
            select(GovernanceAutopilotExecutionIntent).where(
                GovernanceAutopilotExecutionIntent.organization_id == organization_id,
                GovernanceAutopilotExecutionIntent.id == intent_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution intent not found")
        return row

    def archive_execution_intent(
        self,
        *,
        organization_id: uuid.UUID,
        intent_id: uuid.UUID,
        reason: str | None,
    ) -> GovernanceAutopilotExecutionIntent:
        row = self.require_execution_intent(organization_id=organization_id, intent_id=intent_id)
        if row.intent_status != "archived":
            row.intent_status = "archived"
            row.archived_at = self.now()
            row.archive_reason = reason
        return row

    @staticmethod
    def execution_intent_payload(row: GovernanceAutopilotExecutionIntent) -> dict[str, Any]:
        return {
            "id": row.id,
            "intent_id": row.id,
            "organization_id": row.organization_id,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "policy_id": row.policy_id,
            "intent_status": row.intent_status,
            "plan_payload_json": row.plan_payload_json,
            "capability_decisions_json": row.capability_decisions_json,
            "approval_required": row.approval_required,
            "blocked": row.blocked,
            "blocked_reasons_json": row.blocked_reasons_json,
            "source_entities_json": row.source_entities_json,
            "source_hash": row.source_hash,
            "intent_sha256": row.intent_sha256,
            "created_by_user_id": row.created_by_user_id,
            "archived_at": row.archived_at,
            "archive_reason": row.archive_reason,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "caveat": AUTOPILOT_EXECUTION_INTENT_CAVEAT,
        }

    def execution_intent_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        rows_status = list(
            self.db.execute(
                select(
                    GovernanceAutopilotExecutionIntent.intent_status,
                    func.count(GovernanceAutopilotExecutionIntent.id),
                )
                .where(GovernanceAutopilotExecutionIntent.organization_id == organization_id)
                .group_by(GovernanceAutopilotExecutionIntent.intent_status)
            ).all()
        )
        by_status = {str(k): int(v) for k, v in rows_status}
        rows_source = list(
            self.db.execute(
                select(
                    GovernanceAutopilotExecutionIntent.source_type,
                    func.count(GovernanceAutopilotExecutionIntent.id),
                )
                .where(GovernanceAutopilotExecutionIntent.organization_id == organization_id)
                .group_by(GovernanceAutopilotExecutionIntent.source_type)
            ).all()
        )
        by_source_type = {str(k): int(v) for k, v in rows_source}
        total_intents = int(sum(by_status.values()))
        blocked_count = int(by_status.get("blocked", 0))
        approval_required_count = int(by_status.get("approval_required", 0))
        latest_intent_at = self.db.execute(
            select(func.max(GovernanceAutopilotExecutionIntent.created_at)).where(
                GovernanceAutopilotExecutionIntent.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "total_intents": total_intents,
            "by_status": by_status,
            "by_source_type": by_source_type,
            "blocked_count": blocked_count,
            "approval_required_count": approval_required_count,
            "latest_intent_at": latest_intent_at,
            "caveat": AUTOPILOT_EXECUTION_INTENT_CAVEAT,
        }

    @staticmethod
    def autopilot_runner_interface_contract() -> dict[str, Any]:
        required_fields = [
            "handoff_version",
            "dry_run",
            "execution_allowed",
            "execution_intent_id",
            "idempotency_key",
            "operation_key",
            "source_type",
            "source_id",
            "intent_status",
            "readiness_state",
            "ready_for_runner",
            "policy_decision",
            "capability_decisions",
            "proposed_steps",
            "preconditions",
            "blocked_reasons",
            "approval_summary",
            "source_hash",
            "generated_at",
            "caveat",
        ]
        return {
            "handoff_schema_version": AUTOPILOT_RUNNER_HANDOFF_VERSION,
            "required_fields": required_fields,
            "supported_source_types": list(AUTOPILOT_EXECUTION_INTENT_SOURCE_TYPES),
            "supported_statuses": list(AUTOPILOT_RUNNER_SIMULATION_STATUS_VALUES),
            "idempotency_rules": {
                "algorithm": "sha256(canonical_json(operation_key+source_hash+readiness_state+policy_id))",
                "active_simulation_reuse": True,
            },
            "dry_run_only": True,
            "execution_allowed": False,
            "caveat": AUTOPILOT_RUNNER_INTERFACE_CAVEAT,
        }

    @staticmethod
    def _runner_operation_key(*, intent: GovernanceAutopilotExecutionIntent, approval_id: uuid.UUID | None) -> str:
        return (
            f"intent:{intent.id}:approval:{approval_id if approval_id else 'none'}"
            f":source:{intent.source_type}:{intent.source_id if intent.source_id else 'none'}"
        )

    @classmethod
    def _runner_idempotency_key(
        cls,
        *,
        operation_key: str,
        source_hash: str,
        readiness_state: str,
        policy_id: uuid.UUID | None,
    ) -> str:
        payload = {
            "operation_key": operation_key,
            "source_hash": source_hash,
            "readiness_state": readiness_state,
            "policy_id": str(policy_id) if policy_id else None,
        }
        return cls.sha256_hexdigest(payload)

    @staticmethod
    def _runner_simulation_status(
        *,
        intent: GovernanceAutopilotExecutionIntent,
        readiness_state: str,
        decisions: list[dict[str, Any]],
    ) -> str:
        blocked_reasons = set(intent.blocked_reasons_json or [])
        for item in decisions:
            for reason in list(item.get("blocked_reasons") or []):
                blocked_reasons.add(str(reason))
        if intent.intent_status == "archived" or intent.archived_at is not None:
            return "archived"
        if readiness_state == "ready_for_runner":
            return "ready_for_runner"
        if readiness_state == "approval_required":
            return "approval_required"
        if "capability_not_allowed_in_phase_7_1" in blocked_reasons:
            return "capability_denied"
        if any(str(item.get("policy_decision", "")).startswith("blocked_") for item in decisions):
            return "policy_denied"
        if readiness_state in {"blocked", "rejected", "cancelled"}:
            return "blocked"
        return "not_ready"

    def _runner_handoff_payload_for_intent(
        self,
        *,
        organization_id: uuid.UUID,
        intent: GovernanceAutopilotExecutionIntent,
        approval_id: uuid.UUID | None,
        provided_idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        approval_row: GovernanceAutopilotExecutionApproval | None = None
        if approval_id is not None:
            approval_row = self.require_execution_approval(organization_id=organization_id, approval_id=approval_id)
            if approval_row.execution_intent_id != intent.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="approval_id does not belong to execution intent",
                )

        readiness = self.execution_intent_readiness(organization_id=organization_id, intent_id=intent.id)
        decisions = self._extract_intent_decisions(intent.capability_decisions_json)
        policy_snapshot = self.resolved_autopilot_policy(organization_id=organization_id)

        blocked_reasons = sorted(
            set(list(readiness.get("blocked_reasons") or []) + list(intent.blocked_reasons_json or []))
        )
        policy_decision = "blocked" if blocked_reasons else "allow_with_guardrails"
        if readiness["readiness_state"] == "approval_required":
            policy_decision = "approval_required"
        if readiness["readiness_state"] == "ready_for_runner":
            policy_decision = "ready_for_runner"

        proposed_steps: list[dict[str, Any]] = []
        for idx, item in enumerate(decisions, start=1):
            proposed_steps.append(
                {
                    "step_order": idx,
                    "action_key": item.get("action_key"),
                    "action_type": item.get("capability", {}).get("action_type") or item.get("action_type"),
                    "would_execute": False,
                    "status": "dry_run_only",
                }
            )

        preconditions = [
            {"key": "dry_run_only", "met": True},
            {"key": "execution_allowed_false", "met": True},
            {"key": "intent_not_blocked", "met": readiness["readiness_state"] != "blocked"},
            {
                "key": "approval_if_required",
                "met": (not readiness["approval_required"]) or bool(readiness.get("ready_for_runner")),
            },
        ]

        operation_key = self._runner_operation_key(intent=intent, approval_id=approval_id)
        idempotency_key = provided_idempotency_key or self._runner_idempotency_key(
            operation_key=operation_key,
            source_hash=str(intent.source_hash),
            readiness_state=str(readiness["readiness_state"]),
            policy_id=intent.policy_id,
        )

        handoff_payload_json = {
            "handoff_version": AUTOPILOT_RUNNER_HANDOFF_VERSION,
            "dry_run": True,
            "execution_allowed": False,
            "execution_intent_id": str(intent.id),
            "approval_id": str(approval_row.id) if approval_row else None,
            "idempotency_key": idempotency_key,
            "operation_key": operation_key,
            "source_type": intent.source_type,
            "source_id": str(intent.source_id) if intent.source_id else None,
            "intent_status": intent.intent_status,
            "readiness_state": readiness["readiness_state"],
            "ready_for_runner": bool(readiness["ready_for_runner"]),
            "policy_decision": policy_decision,
            "capability_decisions": intent.capability_decisions_json,
            "proposed_steps": proposed_steps,
            "preconditions": preconditions,
            "blocked_reasons": blocked_reasons,
            "approval_summary": {
                "approval_required": bool(readiness["approval_required"]),
                "latest_approval_id": str(readiness["latest_approval_id"]) if readiness.get("latest_approval_id") else None,
                "latest_approval_status": readiness.get("latest_approval_status"),
                "approval_vote_count": int(readiness.get("approval_vote_count") or 0),
                "rejection_vote_count": int(readiness.get("rejection_vote_count") or 0),
                "quorum_met": bool(readiness.get("quorum_met")),
                "rejection_threshold_met": bool(readiness.get("rejection_threshold_met")),
            },
            "source_hash": intent.source_hash,
            "generated_at": self.now().isoformat(),
            "caveat": AUTOPILOT_RUNNER_INTERFACE_CAVEAT,
        }

        source_hash_payload = {
            "execution_intent_id": str(intent.id),
            "source_hash": intent.source_hash,
            "source_type": intent.source_type,
            "source_id": str(intent.source_id) if intent.source_id else None,
            "approval_id": str(approval_row.id) if approval_row else None,
            "policy_id": str(intent.policy_id) if intent.policy_id else None,
            "readiness_state": readiness["readiness_state"],
        }
        source_hash = self.sha256_hexdigest(source_hash_payload)

        simulation_status = self._runner_simulation_status(
            intent=intent,
            readiness_state=str(readiness["readiness_state"]),
            decisions=decisions,
        )

        return {
            "execution_intent_id": intent.id,
            "approval_id": approval_row.id if approval_row else None,
            "handoff_payload_json": handoff_payload_json,
            "readiness_snapshot_json": readiness,
            "policy_snapshot_json": policy_snapshot,
            "capability_snapshot_json": {"decisions": decisions},
            "source_hash": source_hash,
            "idempotency_key": idempotency_key,
            "simulation_status": simulation_status,
            "dry_run": True,
            "execution_allowed": False,
            "caveat": AUTOPILOT_RUNNER_INTERFACE_CAVEAT,
        }

    def preview_runner_handoff_for_execution_intent(
        self,
        *,
        organization_id: uuid.UUID,
        intent_id: uuid.UUID,
        approval_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        intent = self.require_execution_intent(organization_id=organization_id, intent_id=intent_id)
        payload = self._runner_handoff_payload_for_intent(
            organization_id=organization_id,
            intent=intent,
            approval_id=approval_id,
        )
        return {
            "simulation_id": None,
            **payload,
        }

    @classmethod
    def _runner_simulation_hash(cls, payload: dict[str, Any]) -> str:
        return cls.sha256_hexdigest(payload)

    def create_runner_simulation(
        self,
        *,
        organization_id: uuid.UUID,
        intent_id: uuid.UUID,
        approval_id: uuid.UUID | None,
        idempotency_key: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotRunnerSimulation:
        intent = self.require_execution_intent(organization_id=organization_id, intent_id=intent_id)
        preview = self._runner_handoff_payload_for_intent(
            organization_id=organization_id,
            intent=intent,
            approval_id=approval_id,
            provided_idempotency_key=idempotency_key,
        )

        existing = self.db.execute(
            select(GovernanceAutopilotRunnerSimulation).where(
                GovernanceAutopilotRunnerSimulation.organization_id == organization_id,
                GovernanceAutopilotRunnerSimulation.idempotency_key == preview["idempotency_key"],
                GovernanceAutopilotRunnerSimulation.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        simulation_sha256 = self._runner_simulation_hash(
            self.to_json_compatible(
                {
                    "execution_intent_id": str(preview["execution_intent_id"]),
                    "approval_id": str(preview["approval_id"]) if preview["approval_id"] else None,
                    "simulation_status": preview["simulation_status"],
                    "handoff_payload_json": preview["handoff_payload_json"],
                    "readiness_snapshot_json": preview["readiness_snapshot_json"],
                    "policy_snapshot_json": preview["policy_snapshot_json"],
                    "capability_snapshot_json": preview["capability_snapshot_json"],
                    "source_hash": preview["source_hash"],
                    "idempotency_key": preview["idempotency_key"],
                }
            )
        )
        row = GovernanceAutopilotRunnerSimulation(
            organization_id=organization_id,
            execution_intent_id=intent.id,
            approval_id=preview["approval_id"],
            simulation_status=preview["simulation_status"],
            handoff_payload_json=self.to_json_compatible(preview["handoff_payload_json"]),
            readiness_snapshot_json=self.to_json_compatible(preview["readiness_snapshot_json"]),
            policy_snapshot_json=self.to_json_compatible(preview["policy_snapshot_json"]),
            capability_snapshot_json=self.to_json_compatible(preview["capability_snapshot_json"]),
            source_hash=preview["source_hash"],
            idempotency_key=preview["idempotency_key"],
            simulation_sha256=simulation_sha256,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_runner_simulations(
        self,
        *,
        organization_id: uuid.UUID,
        execution_intent_id: uuid.UUID | None,
        simulation_status: str | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceAutopilotRunnerSimulation]:
        if execution_intent_id is not None:
            self.require_execution_intent(organization_id=organization_id, intent_id=execution_intent_id)
        if simulation_status is not None:
            simulation_status = validate_choice(simulation_status, AUTOPILOT_RUNNER_SIMULATION_STATUS_VALUES, "simulation_status", status_code=status.HTTP_400_BAD_REQUEST)
        query = select(GovernanceAutopilotRunnerSimulation).where(
            GovernanceAutopilotRunnerSimulation.organization_id == organization_id
        )
        if execution_intent_id is not None:
            query = query.where(GovernanceAutopilotRunnerSimulation.execution_intent_id == execution_intent_id)
        if simulation_status is not None:
            query = query.where(GovernanceAutopilotRunnerSimulation.simulation_status == simulation_status)
        query = query.order_by(
            GovernanceAutopilotRunnerSimulation.created_at.desc(),
            GovernanceAutopilotRunnerSimulation.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def require_runner_simulation(
        self,
        *,
        organization_id: uuid.UUID,
        simulation_id: uuid.UUID,
    ) -> GovernanceAutopilotRunnerSimulation:
        row = self.db.execute(
            select(GovernanceAutopilotRunnerSimulation).where(
                GovernanceAutopilotRunnerSimulation.organization_id == organization_id,
                GovernanceAutopilotRunnerSimulation.id == simulation_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runner simulation not found")
        return row

    def archive_runner_simulation(
        self,
        *,
        organization_id: uuid.UUID,
        simulation_id: uuid.UUID,
    ) -> GovernanceAutopilotRunnerSimulation:
        row = self.require_runner_simulation(organization_id=organization_id, simulation_id=simulation_id)
        if row.simulation_status != "archived":
            row.simulation_status = "archived"
            row.archived_at = self.now()
        return row

    def runner_simulation_payload(self, row: GovernanceAutopilotRunnerSimulation) -> dict[str, Any]:
        return {
            "id": row.id,
            "simulation_id": row.id,
            "organization_id": row.organization_id,
            "execution_intent_id": row.execution_intent_id,
            "approval_id": row.approval_id,
            "simulation_status": row.simulation_status,
            "handoff_payload_json": row.handoff_payload_json,
            "readiness_snapshot_json": row.readiness_snapshot_json,
            "policy_snapshot_json": row.policy_snapshot_json,
            "capability_snapshot_json": row.capability_snapshot_json,
            "source_hash": row.source_hash,
            "idempotency_key": row.idempotency_key,
            "simulation_sha256": row.simulation_sha256,
            "created_by_user_id": row.created_by_user_id,
            "archived_at": row.archived_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "caveat": AUTOPILOT_RUNNER_INTERFACE_CAVEAT,
        }

    def runner_simulation_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        rows = list(
            self.db.execute(
                select(
                    GovernanceAutopilotRunnerSimulation.simulation_status,
                    func.count(GovernanceAutopilotRunnerSimulation.id),
                )
                .where(GovernanceAutopilotRunnerSimulation.organization_id == organization_id)
                .group_by(GovernanceAutopilotRunnerSimulation.simulation_status)
            ).all()
        )
        by_status = {str(k): int(v) for k, v in rows}
        latest_simulation_at = self.db.execute(
            select(func.max(GovernanceAutopilotRunnerSimulation.created_at)).where(
                GovernanceAutopilotRunnerSimulation.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "total_simulations": int(sum(by_status.values())),
            "by_status": by_status,
            "ready_for_runner_count": int(by_status.get("ready_for_runner", 0)),
            "blocked_count": int(
                by_status.get("blocked", 0)
                + by_status.get("policy_denied", 0)
                + by_status.get("capability_denied", 0)
            ),
            "approval_required_count": int(by_status.get("approval_required", 0)),
            "latest_simulation_at": latest_simulation_at,
            "caveat": AUTOPILOT_RUNNER_INTERFACE_CAVEAT,
        }

    def verify_runner_handoff_payload(self, *, handoff_payload_json: dict[str, Any]) -> dict[str, Any]:
        payload = dict(handoff_payload_json or {})
        required_fields = set(self.autopilot_runner_interface_contract()["required_fields"])
        errors: list[str] = []
        for field in sorted(required_fields):
            if field not in payload:
                errors.append(f"missing_field:{field}")
        if payload.get("handoff_version") != AUTOPILOT_RUNNER_HANDOFF_VERSION:
            errors.append("unsupported_handoff_version")
        if payload.get("dry_run") is not True:
            errors.append("dry_run_must_be_true")
        if payload.get("execution_allowed") is not False:
            errors.append("execution_allowed_must_be_false")
        if not payload.get("idempotency_key"):
            errors.append("idempotency_key_required")
        if not payload.get("source_hash"):
            errors.append("source_hash_required")
        valid = len(errors) == 0
        return {
            "valid": valid,
            "validation_errors": errors,
            "caveat": AUTOPILOT_RUNNER_INTERFACE_CAVEAT,
        }

    def _runner_admission_default_expiration(self) -> datetime:
        return self.now() + timedelta(hours=AUTOPILOT_RUNNER_ADMISSION_TOKEN_TTL_HOURS)

    @staticmethod
    def _as_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    def _runner_admission_active_statuses(self) -> set[str]:
        return {"admitted", "blocked"}

    @classmethod
    def _runner_admission_token_hash(cls, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _runner_admission_token_fingerprint(token_hash: str) -> str:
        return token_hash[:12]

    def _runner_admission_consistency_checks(
        self,
        *,
        organization_id: uuid.UUID,
        simulation: GovernanceAutopilotRunnerSimulation,
        token_expires_at: datetime | None,
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add_check(check_key: str, passed: bool, detail: str) -> None:
            checks.append({"check_key": check_key, "passed": bool(passed), "detail": detail})

        simulation_not_archived = simulation.archived_at is None and simulation.simulation_status != "archived"
        add_check(
            "simulation_not_archived",
            simulation_not_archived,
            "runner simulation must not be archived",
        )

        intent = self.require_execution_intent(
            organization_id=organization_id,
            intent_id=simulation.execution_intent_id,
        )
        intent_not_archived = intent.archived_at is None and intent.intent_status != "archived"
        add_check(
            "execution_intent_not_archived",
            intent_not_archived,
            "execution intent must not be archived",
        )

        handoff = dict(simulation.handoff_payload_json or {})
        add_check(
            "handoff_dry_run_true",
            handoff.get("dry_run") is True,
            "handoff payload dry_run must be true",
        )
        add_check(
            "handoff_execution_allowed_false",
            handoff.get("execution_allowed") is False,
            "handoff payload execution_allowed must be false",
        )
        add_check(
            "simulation_status_ready_for_runner",
            simulation.simulation_status == "ready_for_runner",
            "runner simulation status must be ready_for_runner",
        )

        readiness_snapshot = dict(simulation.readiness_snapshot_json or {})
        add_check(
            "snapshot_ready_for_runner",
            bool(readiness_snapshot.get("ready_for_runner")),
            "simulation readiness snapshot must be ready_for_runner=true",
        )

        latest_readiness = self.execution_intent_readiness(
            organization_id=organization_id,
            intent_id=simulation.execution_intent_id,
        )
        add_check(
            "latest_readiness_still_ready",
            bool(latest_readiness.get("ready_for_runner")),
            "latest readiness must still be ready_for_runner",
        )

        approval_id = simulation.approval_id
        approval_row: GovernanceAutopilotExecutionApproval | None = None
        approval_required = bool(latest_readiness.get("approval_required"))
        if approval_required and approval_id is None:
            add_check(
                "approval_present_if_required",
                False,
                "approval is required for this execution intent",
            )
        else:
            add_check(
                "approval_present_if_required",
                True,
                "approval presence satisfied",
            )
            if approval_id is not None:
                approval_row = self.require_execution_approval(
                    organization_id=organization_id,
                    approval_id=approval_id,
                )
                add_check(
                    "approval_status_approved",
                    approval_row.approval_status == "approved",
                    "approval status must be approved",
                )
                quorum = self.execution_approval_quorum_status(
                    organization_id=organization_id,
                    approval_id=approval_id,
                )
                add_check(
                    "approval_quorum_met",
                    bool(quorum.get("quorum_met")),
                    "approval quorum must be met",
                )
                add_check(
                    "approval_rejection_threshold_not_met",
                    not bool(quorum.get("rejection_threshold_met")),
                    "approval rejection threshold must not be met",
                )
            else:
                add_check(
                    "approval_status_approved",
                    not approval_required,
                    "approval status check skipped when approval not required",
                )
                add_check(
                    "approval_quorum_met",
                    not approval_required,
                    "approval quorum check skipped when approval not required",
                )
                add_check(
                    "approval_rejection_threshold_not_met",
                    True,
                    "approval rejection threshold check skipped when approval not required",
                )

        recomputed = self._runner_handoff_payload_for_intent(
            organization_id=organization_id,
            intent=intent,
            approval_id=approval_id,
            provided_idempotency_key=simulation.idempotency_key,
        )
        add_check(
            "idempotency_key_matches",
            recomputed["idempotency_key"] == simulation.idempotency_key,
            "runner simulation idempotency key must match recomputed key",
        )
        add_check(
            "source_hash_matches",
            recomputed["source_hash"] == simulation.source_hash,
            "source hash must match recomputed source hash",
        )
        add_check(
            "handoff_payload_version_supported",
            handoff.get("handoff_version") == AUTOPILOT_RUNNER_HANDOFF_VERSION,
            "handoff payload version must be supported",
        )
        token_exp_utc = self._as_utc(token_expires_at)
        add_check(
            "token_expiration_in_future",
            token_exp_utc is None or token_exp_utc > self.now(),
            "token expiration must be in the future",
        )

        blocked_reasons = sorted(
            {
                str(item["check_key"])
                for item in checks
                if not bool(item.get("passed"))
            }
        )
        would_admit = len(blocked_reasons) == 0
        proposed_status = "admitted" if would_admit else "blocked"
        return {
            "execution_intent_id": simulation.execution_intent_id,
            "approval_id": approval_row.id if approval_row else approval_id,
            "would_admit": would_admit,
            "proposed_admission_status": proposed_status,
            "consistency_checks_json": {"checks": checks},
            "readiness_snapshot_json": latest_readiness,
            "blocked_reasons": blocked_reasons,
            "idempotency_key": simulation.idempotency_key,
        }

    def preview_runner_admission(
        self,
        *,
        organization_id: uuid.UUID,
        simulation_id: uuid.UUID,
        token_expires_at: datetime | None,
    ) -> dict[str, Any]:
        simulation = self.require_runner_simulation(
            organization_id=organization_id,
            simulation_id=simulation_id,
        )
        expires_at = token_expires_at or self._runner_admission_default_expiration()
        result = self._runner_admission_consistency_checks(
            organization_id=organization_id,
            simulation=simulation,
            token_expires_at=expires_at,
        )
        return {
            "simulation_id": simulation.id,
            **result,
            "token_expiration_preview": expires_at,
            "caveat": AUTOPILOT_RUNNER_ADMISSION_CAVEAT,
        }

    def create_runner_admission(
        self,
        *,
        organization_id: uuid.UUID,
        simulation_id: uuid.UUID,
        token_expires_at: datetime | None,
        actor_user_id: uuid.UUID | None,
    ) -> tuple[GovernanceAutopilotRunnerAdmission, str | None, bool]:
        simulation = self.require_runner_simulation(
            organization_id=organization_id,
            simulation_id=simulation_id,
        )
        expires_at = token_expires_at or self._runner_admission_default_expiration()
        preview = self._runner_admission_consistency_checks(
            organization_id=organization_id,
            simulation=simulation,
            token_expires_at=expires_at,
        )
        idempotency_key = str(preview["idempotency_key"])

        existing = self.db.execute(
            select(GovernanceAutopilotRunnerAdmission).where(
                GovernanceAutopilotRunnerAdmission.organization_id == organization_id,
                GovernanceAutopilotRunnerAdmission.idempotency_key == idempotency_key,
                GovernanceAutopilotRunnerAdmission.archived_at.is_(None),
                GovernanceAutopilotRunnerAdmission.admission_status.in_(self._runner_admission_active_statuses()),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, None, False

        admission_status = str(preview["proposed_admission_status"])
        token_plaintext: str | None = None
        token_hash: str | None = None
        token_fingerprint: str | None = None
        effective_expiry: datetime | None = None

        if admission_status == "admitted":
            token_plaintext = f"cv_rh_{secrets.token_urlsafe(32)}"
            token_hash = self._runner_admission_token_hash(token_plaintext)
            token_fingerprint = self._runner_admission_token_fingerprint(token_hash)
            effective_expiry = expires_at

        row = GovernanceAutopilotRunnerAdmission(
            organization_id=organization_id,
            runner_simulation_id=simulation.id,
            execution_intent_id=simulation.execution_intent_id,
            approval_id=preview["approval_id"],
            admission_status=admission_status,
            readiness_snapshot_json=self.to_json_compatible(preview["readiness_snapshot_json"]),
            consistency_checks_json=self.to_json_compatible(preview["consistency_checks_json"]),
            handoff_payload_json=self.to_json_compatible(simulation.handoff_payload_json),
            handoff_token_hash=token_hash,
            handoff_token_fingerprint=token_fingerprint,
            idempotency_key=idempotency_key,
            token_expires_at=effective_expiry,
            admitted_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row, token_plaintext, True

    def require_runner_admission(
        self,
        *,
        organization_id: uuid.UUID,
        admission_id: uuid.UUID,
    ) -> GovernanceAutopilotRunnerAdmission:
        row = self.db.execute(
            select(GovernanceAutopilotRunnerAdmission).where(
                GovernanceAutopilotRunnerAdmission.organization_id == organization_id,
                GovernanceAutopilotRunnerAdmission.id == admission_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runner admission not found")
        return row

    def list_runner_admissions(
        self,
        *,
        organization_id: uuid.UUID,
        runner_simulation_id: uuid.UUID | None,
        execution_intent_id: uuid.UUID | None,
        admission_status: str | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceAutopilotRunnerAdmission]:
        if runner_simulation_id is not None:
            self.require_runner_simulation(organization_id=organization_id, simulation_id=runner_simulation_id)
        if execution_intent_id is not None:
            self.require_execution_intent(organization_id=organization_id, intent_id=execution_intent_id)
        if admission_status is not None:
            admission_status = validate_choice(admission_status, AUTOPILOT_RUNNER_ADMISSION_STATUS_VALUES, "admission_status", status_code=status.HTTP_400_BAD_REQUEST)
        query = select(GovernanceAutopilotRunnerAdmission).where(
            GovernanceAutopilotRunnerAdmission.organization_id == organization_id
        )
        if runner_simulation_id is not None:
            query = query.where(GovernanceAutopilotRunnerAdmission.runner_simulation_id == runner_simulation_id)
        if execution_intent_id is not None:
            query = query.where(GovernanceAutopilotRunnerAdmission.execution_intent_id == execution_intent_id)
        if admission_status is not None:
            query = query.where(GovernanceAutopilotRunnerAdmission.admission_status == admission_status)
        query = query.order_by(
            GovernanceAutopilotRunnerAdmission.created_at.desc(),
            GovernanceAutopilotRunnerAdmission.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def runner_admission_payload(self, row: GovernanceAutopilotRunnerAdmission) -> dict[str, Any]:
        return {
            "id": row.id,
            "admission_id": row.id,
            "organization_id": row.organization_id,
            "runner_simulation_id": row.runner_simulation_id,
            "execution_intent_id": row.execution_intent_id,
            "approval_id": row.approval_id,
            "admission_status": row.admission_status,
            "readiness_snapshot_json": row.readiness_snapshot_json,
            "consistency_checks_json": row.consistency_checks_json,
            "handoff_payload_json": row.handoff_payload_json,
            "handoff_token_fingerprint": row.handoff_token_fingerprint,
            "idempotency_key": row.idempotency_key,
            "token_expires_at": row.token_expires_at,
            "admitted_by_user_id": row.admitted_by_user_id,
            "revoked_by_user_id": row.revoked_by_user_id,
            "revoked_at": row.revoked_at,
            "revoke_reason": row.revoke_reason,
            "archived_at": row.archived_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "caveat": AUTOPILOT_RUNNER_ADMISSION_CAVEAT,
        }

    def verify_runner_admission_token(
        self,
        *,
        organization_id: uuid.UUID,
        admission_id: uuid.UUID,
        handoff_token: str,
    ) -> dict[str, Any]:
        row = self.require_runner_admission(organization_id=organization_id, admission_id=admission_id)
        errors: list[str] = []
        if row.handoff_token_hash is None:
            errors.append("token_not_issued")
        presented_hash = self._runner_admission_token_hash(handoff_token)
        if row.handoff_token_hash is not None and not hmac.compare_digest(row.handoff_token_hash, presented_hash):
            errors.append("token_mismatch")
        expired = False
        token_expires_at = self._as_utc(row.token_expires_at)
        if token_expires_at is not None and token_expires_at <= self.now():
            expired = True
            errors.append("token_expired")
        if row.admission_status == "revoked":
            errors.append("admission_revoked")
        if row.admission_status == "archived":
            errors.append("admission_archived")
        if row.admission_status == "expired":
            expired = True
            errors.append("admission_expired")
        valid = len(errors) == 0 and row.admission_status == "admitted" and not expired
        return {
            "valid": valid,
            "expired": expired,
            "admission_status": row.admission_status,
            "validation_errors": sorted(set(errors)),
            "caveat": AUTOPILOT_RUNNER_ADMISSION_CAVEAT,
        }

    def revoke_runner_admission(
        self,
        *,
        organization_id: uuid.UUID,
        admission_id: uuid.UUID,
        revoke_reason: str,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotRunnerAdmission:
        row = self.require_runner_admission(organization_id=organization_id, admission_id=admission_id)
        if row.archived_at is not None or row.admission_status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived admission cannot be revoked")
        row.admission_status = "revoked"
        row.revoked_at = self.now()
        row.revoked_by_user_id = actor_user_id
        row.revoke_reason = revoke_reason
        return row

    def archive_runner_admission(
        self,
        *,
        organization_id: uuid.UUID,
        admission_id: uuid.UUID,
    ) -> GovernanceAutopilotRunnerAdmission:
        row = self.require_runner_admission(organization_id=organization_id, admission_id=admission_id)
        if row.admission_status != "archived":
            row.admission_status = "archived"
            row.archived_at = self.now()
        return row

    def runner_admission_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        rows = list(
            self.db.execute(
                select(
                    GovernanceAutopilotRunnerAdmission.admission_status,
                    func.count(GovernanceAutopilotRunnerAdmission.id),
                )
                .where(GovernanceAutopilotRunnerAdmission.organization_id == organization_id)
                .group_by(GovernanceAutopilotRunnerAdmission.admission_status)
            ).all()
        )
        by_status = {str(k): int(v) for k, v in rows}
        latest_admission_at = self.db.execute(
            select(func.max(GovernanceAutopilotRunnerAdmission.created_at)).where(
                GovernanceAutopilotRunnerAdmission.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "total_admissions": int(sum(by_status.values())),
            "by_status": by_status,
            "admitted_count": int(by_status.get("admitted", 0)),
            "blocked_count": int(by_status.get("blocked", 0)),
            "revoked_count": int(by_status.get("revoked", 0)),
            "expired_count": int(by_status.get("expired", 0)),
            "latest_admission_at": latest_admission_at,
            "caveat": AUTOPILOT_RUNNER_ADMISSION_CAVEAT,
        }

    def _runner_session_default_expiration(self) -> datetime:
        return self.now() + timedelta(minutes=AUTOPILOT_RUNNER_SESSION_DEFAULT_TTL_MINUTES)

    @classmethod
    def _runner_session_token_hash(cls, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _runner_session_token_fingerprint(token_hash: str) -> str:
        return token_hash[:12]

    def _runner_session_effective_expiration(self, *, expires_at: datetime | None) -> datetime:
        effective = self._as_utc(expires_at) or self._runner_session_default_expiration()
        if effective <= self.now():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="expires_at must be in the future")
        return effective

    @staticmethod
    def _runner_session_effective_max_attempts(*, max_attempts: int | None) -> int:
        return int(max_attempts or AUTOPILOT_RUNNER_SESSION_DEFAULT_MAX_ATTEMPTS)

    @staticmethod
    def _runner_session_effective_replay_window(*, replay_window_seconds: int | None) -> int:
        return int(replay_window_seconds or AUTOPILOT_RUNNER_SESSION_DEFAULT_REPLAY_WINDOW_SECONDS)

    def _runner_session_binding_context(
        self,
        *,
        admission: GovernanceAutopilotRunnerAdmission,
    ) -> dict[str, Any]:
        return {
            "runner_admission_id": str(admission.id),
            "runner_simulation_id": str(admission.runner_simulation_id),
            "execution_intent_id": str(admission.execution_intent_id),
            "admission_status": admission.admission_status,
            "admission_token_fingerprint": admission.handoff_token_fingerprint,
            "dry_run": True,
            "execution_allowed": False,
            "caveat": AUTOPILOT_RUNNER_SESSION_CAVEAT,
        }

    def preview_runner_session(
        self,
        *,
        organization_id: uuid.UUID,
        admission_id: uuid.UUID,
        handoff_token: str,
        expires_at: datetime | None,
        max_attempts: int | None,
        replay_window_seconds: int | None,
    ) -> dict[str, Any]:
        admission = self.require_runner_admission(organization_id=organization_id, admission_id=admission_id)
        verify = self.verify_runner_admission_token(
            organization_id=organization_id,
            admission_id=admission_id,
            handoff_token=handoff_token,
        )
        effective_expiration = self._runner_session_effective_expiration(expires_at=expires_at)
        effective_max_attempts = self._runner_session_effective_max_attempts(max_attempts=max_attempts)
        effective_replay_window = self._runner_session_effective_replay_window(
            replay_window_seconds=replay_window_seconds
        )

        blocked_reasons = sorted(set(verify["validation_errors"]))
        if admission.admission_status != "admitted":
            blocked_reasons.append("admission_not_admitted")
        blocked_reasons = sorted(set(blocked_reasons))
        would_create = len(blocked_reasons) == 0
        proposed_status = "active" if would_create else (
            admission.admission_status if admission.admission_status in AUTOPILOT_RUNNER_SESSION_STATUS_VALUES else "locked"
        )
        return {
            "runner_admission_id": admission.id,
            "runner_simulation_id": admission.runner_simulation_id,
            "execution_intent_id": admission.execution_intent_id,
            "would_create_session": would_create,
            "proposed_session_status": proposed_status,
            "binding_context_json": self._runner_session_binding_context(admission=admission),
            "expires_at": effective_expiration,
            "max_attempts": effective_max_attempts,
            "replay_window_seconds": effective_replay_window,
            "blocked_reasons": blocked_reasons,
            "caveat": AUTOPILOT_RUNNER_SESSION_CAVEAT,
        }

    def create_runner_session(
        self,
        *,
        organization_id: uuid.UUID,
        admission_id: uuid.UUID,
        handoff_token: str,
        expires_at: datetime | None,
        max_attempts: int | None,
        replay_window_seconds: int | None,
        actor_user_id: uuid.UUID | None,
    ) -> tuple[GovernanceAutopilotRunnerSession, str]:
        preview = self.preview_runner_session(
            organization_id=organization_id,
            admission_id=admission_id,
            handoff_token=handoff_token,
            expires_at=expires_at,
            max_attempts=max_attempts,
            replay_window_seconds=replay_window_seconds,
        )
        if not bool(preview["would_create_session"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Runner session cannot be created", "blocked_reasons": preview["blocked_reasons"]},
            )

        admission = self.require_runner_admission(organization_id=organization_id, admission_id=admission_id)
        session_token = f"cv_rs_{secrets.token_urlsafe(32)}"
        token_hash = self._runner_session_token_hash(session_token)
        token_fingerprint = self._runner_session_token_fingerprint(token_hash)
        row = GovernanceAutopilotRunnerSession(
            organization_id=organization_id,
            runner_admission_id=admission.id,
            runner_simulation_id=admission.runner_simulation_id,
            execution_intent_id=admission.execution_intent_id,
            session_status="active",
            admission_token_fingerprint=admission.handoff_token_fingerprint,
            session_token_hash=token_hash,
            session_token_fingerprint=token_fingerprint,
            lease_payload_json=self.to_json_compatible(
                {
                    "dry_run": True,
                    "execution_allowed": False,
                    "expires_at": preview["expires_at"].isoformat(),
                    "max_attempts": preview["max_attempts"],
                    "replay_window_seconds": preview["replay_window_seconds"],
                    "caveat": AUTOPILOT_RUNNER_SESSION_CAVEAT,
                }
            ),
            binding_context_json=self.to_json_compatible(preview["binding_context_json"]),
            attempt_count=0,
            max_attempts=int(preview["max_attempts"]),
            replay_window_seconds=int(preview["replay_window_seconds"]),
            expires_at=preview["expires_at"],
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row, session_token

    def require_runner_session(
        self,
        *,
        organization_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> GovernanceAutopilotRunnerSession:
        row = self.db.execute(
            select(GovernanceAutopilotRunnerSession).where(
                GovernanceAutopilotRunnerSession.organization_id == organization_id,
                GovernanceAutopilotRunnerSession.id == session_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runner session not found")
        return row

    def list_runner_sessions(
        self,
        *,
        organization_id: uuid.UUID,
        runner_admission_id: uuid.UUID | None,
        runner_simulation_id: uuid.UUID | None,
        execution_intent_id: uuid.UUID | None,
        session_status: str | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceAutopilotRunnerSession]:
        if runner_admission_id is not None:
            self.require_runner_admission(organization_id=organization_id, admission_id=runner_admission_id)
        if runner_simulation_id is not None:
            self.require_runner_simulation(organization_id=organization_id, simulation_id=runner_simulation_id)
        if execution_intent_id is not None:
            self.require_execution_intent(organization_id=organization_id, intent_id=execution_intent_id)
        if session_status is not None:
            session_status = validate_choice(session_status, AUTOPILOT_RUNNER_SESSION_STATUS_VALUES, "session_status", status_code=status.HTTP_400_BAD_REQUEST)
        query = select(GovernanceAutopilotRunnerSession).where(
            GovernanceAutopilotRunnerSession.organization_id == organization_id
        )
        if runner_admission_id is not None:
            query = query.where(GovernanceAutopilotRunnerSession.runner_admission_id == runner_admission_id)
        if runner_simulation_id is not None:
            query = query.where(GovernanceAutopilotRunnerSession.runner_simulation_id == runner_simulation_id)
        if execution_intent_id is not None:
            query = query.where(GovernanceAutopilotRunnerSession.execution_intent_id == execution_intent_id)
        if session_status is not None:
            query = query.where(GovernanceAutopilotRunnerSession.session_status == session_status)
        query = query.order_by(
            GovernanceAutopilotRunnerSession.created_at.desc(),
            GovernanceAutopilotRunnerSession.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def runner_session_payload(self, row: GovernanceAutopilotRunnerSession) -> dict[str, Any]:
        return {
            "id": row.id,
            "session_id": row.id,
            "organization_id": row.organization_id,
            "runner_admission_id": row.runner_admission_id,
            "runner_simulation_id": row.runner_simulation_id,
            "execution_intent_id": row.execution_intent_id,
            "session_status": row.session_status,
            "admission_token_fingerprint": row.admission_token_fingerprint,
            "session_token_fingerprint": row.session_token_fingerprint,
            "lease_payload_json": row.lease_payload_json,
            "binding_context_json": row.binding_context_json,
            "attempt_count": int(row.attempt_count),
            "max_attempts": int(row.max_attempts),
            "replay_window_seconds": int(row.replay_window_seconds),
            "expires_at": row.expires_at,
            "last_verified_at": row.last_verified_at,
            "revoked_at": row.revoked_at,
            "revoked_by_user_id": row.revoked_by_user_id,
            "revoke_reason": row.revoke_reason,
            "archived_at": row.archived_at,
            "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "caveat": AUTOPILOT_RUNNER_SESSION_CAVEAT,
        }

    def verify_runner_session_token(
        self,
        *,
        organization_id: uuid.UUID,
        session_id: uuid.UUID,
        session_token: str,
    ) -> dict[str, Any]:
        row = self.require_runner_session(organization_id=organization_id, session_id=session_id)
        row.attempt_count = int(row.attempt_count) + 1
        now_utc = self.now()
        validation_errors: list[str] = []

        expired = self._as_utc(row.expires_at) <= now_utc
        if expired:
            validation_errors.append("session_expired")
        if row.session_status == "revoked":
            validation_errors.append("session_revoked")
        if row.session_status == "archived":
            validation_errors.append("session_archived")
        if row.session_status == "locked":
            validation_errors.append("session_locked")
        if row.session_status != "active":
            validation_errors.append("session_not_active")
        if row.session_token_hash is None:
            validation_errors.append("session_token_not_issued")
        else:
            presented_hash = self._runner_session_token_hash(session_token)
            if not hmac.compare_digest(row.session_token_hash, presented_hash):
                validation_errors.append("session_token_mismatch")

        replay_blocked = False
        if row.last_verified_at is not None and int(row.replay_window_seconds) > 0:
            replay_deadline = self._as_utc(row.last_verified_at) + timedelta(seconds=int(row.replay_window_seconds))
            if now_utc <= replay_deadline:
                replay_blocked = True
                validation_errors.append("replay_window_active")

        locked_now = False
        if row.session_status == "active" and int(row.attempt_count) > int(row.max_attempts):
            row.session_status = "locked"
            locked_now = True
            validation_errors.append("max_attempts_exceeded")

        valid = len(validation_errors) == 0 and not replay_blocked and not expired and row.session_status == "active"
        verified_now = False
        if valid:
            row.last_verified_at = now_utc
            verified_now = True

        return {
            "valid": valid,
            "expired": expired,
            "session_status": row.session_status,
            "attempt_count": int(row.attempt_count),
            "max_attempts": int(row.max_attempts),
            "replay_window_seconds": int(row.replay_window_seconds),
            "validation_errors": sorted(set(validation_errors)),
            "last_verified_at": row.last_verified_at,
            "verified_now": verified_now,
            "verification_failed_now": not valid,
            "locked_now": locked_now,
            "caveat": AUTOPILOT_RUNNER_SESSION_CAVEAT,
        }

    def revoke_runner_session(
        self,
        *,
        organization_id: uuid.UUID,
        session_id: uuid.UUID,
        revoke_reason: str,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotRunnerSession:
        row = self.require_runner_session(organization_id=organization_id, session_id=session_id)
        if row.archived_at is not None or row.session_status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived session cannot be revoked")
        row.session_status = "revoked"
        row.revoked_at = self.now()
        row.revoked_by_user_id = actor_user_id
        row.revoke_reason = revoke_reason
        return row

    def archive_runner_session(
        self,
        *,
        organization_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> GovernanceAutopilotRunnerSession:
        row = self.require_runner_session(organization_id=organization_id, session_id=session_id)
        if row.session_status != "archived":
            row.session_status = "archived"
            row.archived_at = self.now()
        return row

    def expire_stale_runner_sessions(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        now_utc = self.now()
        rows = list(
            self.db.execute(
                select(GovernanceAutopilotRunnerSession).where(
                    GovernanceAutopilotRunnerSession.organization_id == organization_id,
                    GovernanceAutopilotRunnerSession.session_status == "active",
                    GovernanceAutopilotRunnerSession.expires_at < now_utc,
                )
            ).scalars().all()
        )
        expired_ids: list[uuid.UUID] = []
        for row in rows:
            row.session_status = "expired"
            expired_ids.append(row.id)
        return {
            "expired_count": len(expired_ids),
            "expired_session_ids": expired_ids,
            "caveat": AUTOPILOT_RUNNER_SESSION_CAVEAT,
        }

    def runner_session_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        rows = list(
            self.db.execute(
                select(
                    GovernanceAutopilotRunnerSession.session_status,
                    func.count(GovernanceAutopilotRunnerSession.id),
                )
                .where(GovernanceAutopilotRunnerSession.organization_id == organization_id)
                .group_by(GovernanceAutopilotRunnerSession.session_status)
            ).all()
        )
        by_status = {str(k): int(v) for k, v in rows}
        latest_session_at = self.db.execute(
            select(func.max(GovernanceAutopilotRunnerSession.created_at)).where(
                GovernanceAutopilotRunnerSession.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "total_sessions": int(sum(by_status.values())),
            "by_status": by_status,
            "active_count": int(by_status.get("active", 0)),
            "expired_count": int(by_status.get("expired", 0)),
            "locked_count": int(by_status.get("locked", 0)),
            "revoked_count": int(by_status.get("revoked", 0)),
            "latest_session_at": latest_session_at,
            "caveat": AUTOPILOT_RUNNER_SESSION_CAVEAT,
        }

    @staticmethod
    def autopilot_runner_handshake_contract() -> dict[str, Any]:
        required_fields = [
            "handshake_version",
            "dry_run",
            "execution_allowed",
            "future_runner_allowed",
            "runner_session_id",
            "runner_admission_id",
            "runner_simulation_id",
            "execution_intent_id",
            "readiness_state",
            "admission_status",
            "session_status",
            "idempotency_key",
            "source_hash",
            "handoff_payload_hash",
            "lease_context",
            "policy_snapshot",
            "capability_snapshot",
            "approval_quorum_snapshot",
            "preconditions",
            "blocked_reasons",
            "generated_at",
            "caveat",
        ]
        return {
            "handshake_schema_version": AUTOPILOT_RUNNER_HANDSHAKE_VERSION,
            "required_fields": required_fields,
            "supported_statuses": list(AUTOPILOT_RUNNER_HANDSHAKE_STATUS_VALUES),
            "token_requirements": {
                "session_token_required_on_create": True,
                "session_token_stored_plaintext": False,
                "admission_token_stored_plaintext": False,
            },
            "idempotency_rules": {
                "deterministic_default_when_omitted": True,
                "active_handshake_reuse": True,
            },
            "dry_run_only": True,
            "execution_allowed": False,
            "caveat": AUTOPILOT_RUNNER_HANDSHAKE_CAVEAT,
        }

    @staticmethod
    def _sha256_for_json_like(payload: Any) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _runner_handshake_fingerprint(handshake_sha256: str) -> str:
        return handshake_sha256[:12]

    @classmethod
    def _runner_handshake_nonce_hash(cls, *, runner_session_id: uuid.UUID, idempotency_key: str) -> str:
        return hashlib.sha256(f"{runner_session_id}:{idempotency_key}".encode("utf-8")).hexdigest()

    @staticmethod
    def _runner_handshake_active_statuses() -> set[str]:
        return {
            "ready_for_future_runner",
            "blocked",
            "session_expired",
            "session_locked",
            "session_revoked",
            "admission_revoked",
        }

    @classmethod
    def _runner_handshake_default_idempotency_key(
        cls,
        *,
        session: GovernanceAutopilotRunnerSession,
        admission: GovernanceAutopilotRunnerAdmission,
        simulation: GovernanceAutopilotRunnerSimulation,
        intent: GovernanceAutopilotExecutionIntent,
    ) -> str:
        payload = {
            "runner_session_id": str(session.id),
            "runner_admission_id": str(admission.id),
            "runner_simulation_id": str(simulation.id),
            "execution_intent_id": str(intent.id),
            "session_status": session.session_status,
            "admission_status": admission.admission_status,
            "simulation_status": simulation.simulation_status,
            "intent_status": intent.intent_status,
            "source_hash": simulation.source_hash,
            "intent_source_hash": intent.source_hash,
        }
        return cls.sha256_hexdigest(payload)

    def _runner_handshake_status(
        self,
        *,
        session: GovernanceAutopilotRunnerSession,
        admission: GovernanceAutopilotRunnerAdmission,
        simulation: GovernanceAutopilotRunnerSimulation,
        intent: GovernanceAutopilotExecutionIntent,
        blocked_reasons: list[str],
    ) -> str:
        session_expired = session.session_status == "expired" or self._as_utc(session.expires_at) <= self.now()
        if session.session_status == "archived" or session.archived_at is not None:
            return "archived"
        if session.session_status == "revoked":
            return "session_revoked"
        if session.session_status == "locked":
            return "session_locked"
        if session_expired:
            return "session_expired"
        if admission.admission_status == "revoked":
            return "admission_revoked"
        if blocked_reasons:
            return "blocked"
        if session.session_status != "active":
            return "blocked"
        return "ready_for_future_runner"

    def _runner_handshake_payload(
        self,
        *,
        session: GovernanceAutopilotRunnerSession,
        admission: GovernanceAutopilotRunnerAdmission,
        simulation: GovernanceAutopilotRunnerSimulation,
        intent: GovernanceAutopilotExecutionIntent,
        handshake_status: str,
        idempotency_key: str,
        blocked_reasons: list[str],
    ) -> dict[str, Any]:
        readiness_state = "not_ready"
        readiness_snapshot = simulation.readiness_snapshot_json if isinstance(simulation.readiness_snapshot_json, dict) else {}
        if isinstance(readiness_snapshot, dict):
            readiness_state = str(readiness_snapshot.get("readiness_state") or readiness_state)
        handoff_payload_hash = self._sha256_for_json_like(self.to_json_compatible(simulation.handoff_payload_json or {}))
        approval_summary = {}
        handoff_payload = simulation.handoff_payload_json if isinstance(simulation.handoff_payload_json, dict) else {}
        if isinstance(handoff_payload, dict):
            approval_summary = handoff_payload.get("approval_summary") or {}
        preconditions = [
            {"key": "dry_run_only", "met": True},
            {"key": "execution_allowed_false", "met": True},
            {"key": "session_active", "met": session.session_status == "active"},
            {"key": "session_unexpired", "met": self._as_utc(session.expires_at) > self.now()},
            {"key": "admission_admitted", "met": admission.admission_status == "admitted"},
            {"key": "simulation_non_archived", "met": simulation.archived_at is None and simulation.simulation_status != "archived"},
            {"key": "intent_non_archived", "met": intent.archived_at is None and intent.intent_status != "archived"},
        ]
        return {
            "handshake_version": AUTOPILOT_RUNNER_HANDSHAKE_VERSION,
            "dry_run": True,
            "execution_allowed": False,
            "future_runner_allowed": handshake_status == "ready_for_future_runner",
            "runner_session_id": str(session.id),
            "runner_admission_id": str(admission.id),
            "runner_simulation_id": str(simulation.id),
            "execution_intent_id": str(intent.id),
            "readiness_state": readiness_state,
            "admission_status": admission.admission_status,
            "session_status": session.session_status,
            "idempotency_key": idempotency_key,
            "source_hash": simulation.source_hash,
            "handoff_payload_hash": handoff_payload_hash,
            "lease_context": {
                "lease_payload_json": session.lease_payload_json,
                "binding_context_json": session.binding_context_json,
                "admission_token_fingerprint": session.admission_token_fingerprint,
                "session_token_fingerprint": session.session_token_fingerprint,
                "replay_window_seconds": int(session.replay_window_seconds),
                "max_attempts": int(session.max_attempts),
                "expires_at": session.expires_at.isoformat() if session.expires_at else None,
            },
            "policy_snapshot": simulation.policy_snapshot_json,
            "capability_snapshot": simulation.capability_snapshot_json,
            "approval_quorum_snapshot": approval_summary,
            "preconditions": preconditions,
            "blocked_reasons": blocked_reasons,
            "generated_at": self.now().isoformat(),
            "caveat": AUTOPILOT_RUNNER_HANDSHAKE_CAVEAT,
        }

    def _runner_handshake_preview_data(
        self,
        *,
        organization_id: uuid.UUID,
        session_id: uuid.UUID,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        session = self.require_runner_session(organization_id=organization_id, session_id=session_id)
        admission = self.require_runner_admission(
            organization_id=organization_id,
            admission_id=session.runner_admission_id,
        )
        simulation = self.require_runner_simulation(
            organization_id=organization_id,
            simulation_id=session.runner_simulation_id,
        )
        intent = self.require_execution_intent(
            organization_id=organization_id,
            intent_id=session.execution_intent_id,
        )

        blocked_reasons: list[str] = []
        if session.runner_admission_id != admission.id:
            blocked_reasons.append("session_admission_mismatch")
        if session.runner_simulation_id != simulation.id:
            blocked_reasons.append("session_simulation_mismatch")
        if session.execution_intent_id != intent.id:
            blocked_reasons.append("session_intent_mismatch")
        if admission.runner_simulation_id != simulation.id:
            blocked_reasons.append("admission_simulation_mismatch")
        if admission.execution_intent_id != intent.id:
            blocked_reasons.append("admission_intent_mismatch")
        if simulation.execution_intent_id != intent.id:
            blocked_reasons.append("simulation_intent_mismatch")
        if session.session_status != "active":
            blocked_reasons.append("session_not_active")
        if self._as_utc(session.expires_at) <= self.now():
            blocked_reasons.append("session_expired")
        if admission.admission_status != "admitted":
            blocked_reasons.append("admission_not_admitted")
        if simulation.archived_at is not None or simulation.simulation_status == "archived":
            blocked_reasons.append("simulation_archived")
        if intent.archived_at is not None or intent.intent_status == "archived":
            blocked_reasons.append("intent_archived")

        status = self._runner_handshake_status(
            session=session,
            admission=admission,
            simulation=simulation,
            intent=intent,
            blocked_reasons=blocked_reasons,
        )
        effective_idempotency_key = idempotency_key or self._runner_handshake_default_idempotency_key(
            session=session,
            admission=admission,
            simulation=simulation,
            intent=intent,
        )
        blocked_reasons = sorted(set(blocked_reasons))
        handshake_payload_json = self._runner_handshake_payload(
            session=session,
            admission=admission,
            simulation=simulation,
            intent=intent,
            handshake_status=status,
            idempotency_key=effective_idempotency_key,
            blocked_reasons=blocked_reasons,
        )
        return {
            "session": session,
            "admission": admission,
            "simulation": simulation,
            "intent": intent,
            "idempotency_key": effective_idempotency_key,
            "proposed_handshake_status": status,
            "blocked_reasons": blocked_reasons,
            "would_create_handshake": status == "ready_for_future_runner" and not blocked_reasons,
            "handshake_payload_json": handshake_payload_json,
        }

    def preview_runner_handshake(
        self,
        *,
        organization_id: uuid.UUID,
        session_id: uuid.UUID,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        preview = self._runner_handshake_preview_data(
            organization_id=organization_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
        )
        session: GovernanceAutopilotRunnerSession = preview["session"]
        return {
            "runner_session_id": session.id,
            "runner_admission_id": preview["admission"].id,
            "runner_simulation_id": preview["simulation"].id,
            "execution_intent_id": preview["intent"].id,
            "would_create_handshake": bool(preview["would_create_handshake"]),
            "proposed_handshake_status": preview["proposed_handshake_status"],
            "handshake_payload_json": self.to_json_compatible(preview["handshake_payload_json"]),
            "blocked_reasons": preview["blocked_reasons"],
            "idempotency_key": preview["idempotency_key"],
            "caveat": AUTOPILOT_RUNNER_HANDSHAKE_CAVEAT,
        }

    def _find_existing_runner_handshake(
        self,
        *,
        organization_id: uuid.UUID,
        idempotency_key: str,
    ) -> GovernanceAutopilotRunnerHandshake | None:
        return self.db.execute(
            select(GovernanceAutopilotRunnerHandshake).where(
                GovernanceAutopilotRunnerHandshake.organization_id == organization_id,
                GovernanceAutopilotRunnerHandshake.idempotency_key == idempotency_key,
                GovernanceAutopilotRunnerHandshake.handshake_status.in_(self._runner_handshake_active_statuses()),
                GovernanceAutopilotRunnerHandshake.archived_at.is_(None),
            )
        ).scalar_one_or_none()

    def create_runner_handshake(
        self,
        *,
        organization_id: uuid.UUID,
        session_id: uuid.UUID,
        session_token: str,
        idempotency_key: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> tuple[GovernanceAutopilotRunnerHandshake, bool]:
        preview = self._runner_handshake_preview_data(
            organization_id=organization_id,
            session_id=session_id,
            idempotency_key=idempotency_key,
        )
        existing = self._find_existing_runner_handshake(
            organization_id=organization_id,
            idempotency_key=preview["idempotency_key"],
        )
        verify = self.verify_runner_session_token(
            organization_id=organization_id,
            session_id=session_id,
            session_token=session_token,
        )
        if not bool(verify["valid"]):
            # Idempotent replay-safe readback for existing active handshake.
            if existing is not None and set(verify["validation_errors"]).issubset({"replay_window_active"}):
                return existing, False
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Runner handshake cannot be created",
                    "validation_errors": verify["validation_errors"],
                    "session_status": verify["session_status"],
                },
            )
        if existing is not None:
            return existing, False
        if not bool(preview["would_create_handshake"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Runner handshake cannot be created",
                    "blocked_reasons": preview["blocked_reasons"],
                    "proposed_handshake_status": preview["proposed_handshake_status"],
                },
            )

        session = preview["session"]
        admission = preview["admission"]
        simulation = preview["simulation"]
        intent = preview["intent"]
        handshake_payload_json = self.to_json_compatible(preview["handshake_payload_json"])
        handshake_sha256 = self._sha256_for_json_like(handshake_payload_json)
        row = GovernanceAutopilotRunnerHandshake(
            organization_id=organization_id,
            runner_session_id=session.id,
            runner_admission_id=admission.id,
            runner_simulation_id=simulation.id,
            execution_intent_id=intent.id,
            handshake_status=preview["proposed_handshake_status"],
            handshake_payload_json=handshake_payload_json,
            session_verification_snapshot_json=self.to_json_compatible(verify),
            admission_snapshot_json=self.to_json_compatible(self.runner_admission_payload(admission)),
            simulation_snapshot_json=self.to_json_compatible(self.runner_simulation_payload(simulation)),
            intent_snapshot_json=self.to_json_compatible(self.execution_intent_payload(intent)),
            idempotency_key=preview["idempotency_key"],
            handshake_nonce_hash=self._runner_handshake_nonce_hash(
                runner_session_id=session.id,
                idempotency_key=preview["idempotency_key"],
            ),
            handshake_fingerprint=self._runner_handshake_fingerprint(handshake_sha256),
            handshake_sha256=handshake_sha256,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row, True

    def require_runner_handshake(
        self,
        *,
        organization_id: uuid.UUID,
        handshake_id: uuid.UUID,
    ) -> GovernanceAutopilotRunnerHandshake:
        row = self.db.execute(
            select(GovernanceAutopilotRunnerHandshake).where(
                GovernanceAutopilotRunnerHandshake.organization_id == organization_id,
                GovernanceAutopilotRunnerHandshake.id == handshake_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runner handshake not found")
        return row

    def list_runner_handshakes(
        self,
        *,
        organization_id: uuid.UUID,
        runner_session_id: uuid.UUID | None,
        runner_admission_id: uuid.UUID | None,
        runner_simulation_id: uuid.UUID | None,
        execution_intent_id: uuid.UUID | None,
        handshake_status: str | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceAutopilotRunnerHandshake]:
        if runner_session_id is not None:
            self.require_runner_session(organization_id=organization_id, session_id=runner_session_id)
        if runner_admission_id is not None:
            self.require_runner_admission(organization_id=organization_id, admission_id=runner_admission_id)
        if runner_simulation_id is not None:
            self.require_runner_simulation(organization_id=organization_id, simulation_id=runner_simulation_id)
        if execution_intent_id is not None:
            self.require_execution_intent(organization_id=organization_id, intent_id=execution_intent_id)
        if handshake_status is not None:
            handshake_status = validate_choice(handshake_status, AUTOPILOT_RUNNER_HANDSHAKE_STATUS_VALUES, "handshake_status", status_code=status.HTTP_400_BAD_REQUEST)
        query = select(GovernanceAutopilotRunnerHandshake).where(
            GovernanceAutopilotRunnerHandshake.organization_id == organization_id
        )
        if runner_session_id is not None:
            query = query.where(GovernanceAutopilotRunnerHandshake.runner_session_id == runner_session_id)
        if runner_admission_id is not None:
            query = query.where(GovernanceAutopilotRunnerHandshake.runner_admission_id == runner_admission_id)
        if runner_simulation_id is not None:
            query = query.where(GovernanceAutopilotRunnerHandshake.runner_simulation_id == runner_simulation_id)
        if execution_intent_id is not None:
            query = query.where(GovernanceAutopilotRunnerHandshake.execution_intent_id == execution_intent_id)
        if handshake_status is not None:
            query = query.where(GovernanceAutopilotRunnerHandshake.handshake_status == handshake_status)
        query = query.order_by(
            GovernanceAutopilotRunnerHandshake.created_at.desc(),
            GovernanceAutopilotRunnerHandshake.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def runner_handshake_payload(self, row: GovernanceAutopilotRunnerHandshake) -> dict[str, Any]:
        return {
            "id": row.id,
            "handshake_id": row.id,
            "organization_id": row.organization_id,
            "runner_session_id": row.runner_session_id,
            "runner_admission_id": row.runner_admission_id,
            "runner_simulation_id": row.runner_simulation_id,
            "execution_intent_id": row.execution_intent_id,
            "handshake_status": row.handshake_status,
            "handshake_payload_json": row.handshake_payload_json,
            "session_verification_snapshot_json": row.session_verification_snapshot_json,
            "admission_snapshot_json": row.admission_snapshot_json,
            "simulation_snapshot_json": row.simulation_snapshot_json,
            "intent_snapshot_json": row.intent_snapshot_json,
            "idempotency_key": row.idempotency_key,
            "handshake_fingerprint": row.handshake_fingerprint,
            "handshake_sha256": row.handshake_sha256,
            "revoked_at": row.revoked_at,
            "revoked_by_user_id": row.revoked_by_user_id,
            "revoke_reason": row.revoke_reason,
            "archived_at": row.archived_at,
            "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "caveat": AUTOPILOT_RUNNER_HANDSHAKE_CAVEAT,
        }

    def verify_runner_handshake_envelope(
        self,
        *,
        organization_id: uuid.UUID,
        handshake_id: uuid.UUID,
        handshake_payload_json: dict | list | None,
    ) -> dict[str, Any]:
        row = self.require_runner_handshake(organization_id=organization_id, handshake_id=handshake_id)
        payload: dict | list = handshake_payload_json if handshake_payload_json is not None else row.handshake_payload_json
        errors: list[str] = []
        if not isinstance(payload, dict):
            errors.append("handshake_payload_must_be_object")
            return {"valid": False, "validation_errors": errors, "caveat": AUTOPILOT_RUNNER_HANDSHAKE_CAVEAT}

        required_fields = set(self.autopilot_runner_handshake_contract()["required_fields"])
        for field in sorted(required_fields):
            if field not in payload:
                errors.append(f"missing_field:{field}")
        if payload.get("handshake_version") != AUTOPILOT_RUNNER_HANDSHAKE_VERSION:
            errors.append("unsupported_handshake_version")
        if payload.get("dry_run") is not True:
            errors.append("dry_run_must_be_true")
        if payload.get("execution_allowed") is not False:
            errors.append("execution_allowed_must_be_false")
        if payload.get("idempotency_key") != row.idempotency_key:
            errors.append("idempotency_key_mismatch")
        if str(payload.get("runner_session_id")) != str(row.runner_session_id):
            errors.append("runner_session_id_mismatch")
        if str(payload.get("runner_admission_id")) != str(row.runner_admission_id):
            errors.append("runner_admission_id_mismatch")
        if str(payload.get("runner_simulation_id")) != str(row.runner_simulation_id):
            errors.append("runner_simulation_id_mismatch")
        if str(payload.get("execution_intent_id")) != str(row.execution_intent_id):
            errors.append("execution_intent_id_mismatch")

        recomputed_sha = self._sha256_for_json_like(self.to_json_compatible(payload))
        if recomputed_sha != row.handshake_sha256:
            errors.append("handshake_sha256_mismatch")
        if row.handshake_fingerprint and self._runner_handshake_fingerprint(row.handshake_sha256) != row.handshake_fingerprint:
            errors.append("handshake_fingerprint_mismatch")
        valid = len(errors) == 0
        return {
            "valid": valid,
            "validation_errors": sorted(set(errors)),
            "caveat": AUTOPILOT_RUNNER_HANDSHAKE_CAVEAT,
        }

    def revoke_runner_handshake(
        self,
        *,
        organization_id: uuid.UUID,
        handshake_id: uuid.UUID,
        revoke_reason: str,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotRunnerHandshake:
        row = self.require_runner_handshake(organization_id=organization_id, handshake_id=handshake_id)
        if row.archived_at is not None or row.handshake_status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived handshake cannot be revoked")
        row.handshake_status = "revoked"
        row.revoked_at = self.now()
        row.revoked_by_user_id = actor_user_id
        row.revoke_reason = revoke_reason
        return row

    def archive_runner_handshake(
        self,
        *,
        organization_id: uuid.UUID,
        handshake_id: uuid.UUID,
    ) -> GovernanceAutopilotRunnerHandshake:
        row = self.require_runner_handshake(organization_id=organization_id, handshake_id=handshake_id)
        if row.handshake_status != "archived":
            row.handshake_status = "archived"
            row.archived_at = self.now()
        return row

    def runner_handshake_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        rows = list(
            self.db.execute(
                select(
                    GovernanceAutopilotRunnerHandshake.handshake_status,
                    func.count(GovernanceAutopilotRunnerHandshake.id),
                )
                .where(GovernanceAutopilotRunnerHandshake.organization_id == organization_id)
                .group_by(GovernanceAutopilotRunnerHandshake.handshake_status)
            ).all()
        )
        by_status = {str(k): int(v) for k, v in rows}
        latest_handshake_at = self.db.execute(
            select(func.max(GovernanceAutopilotRunnerHandshake.created_at)).where(
                GovernanceAutopilotRunnerHandshake.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "total_handshakes": int(sum(by_status.values())),
            "by_status": by_status,
            "ready_for_future_runner_count": int(by_status.get("ready_for_future_runner", 0)),
            "blocked_count": int(
                by_status.get("blocked", 0)
                + by_status.get("session_expired", 0)
                + by_status.get("session_locked", 0)
                + by_status.get("session_revoked", 0)
                + by_status.get("admission_revoked", 0)
            ),
            "revoked_count": int(by_status.get("revoked", 0)),
            "archived_count": int(by_status.get("archived", 0)),
            "latest_handshake_at": latest_handshake_at,
            "caveat": AUTOPILOT_RUNNER_HANDSHAKE_CAVEAT,
        }

    @staticmethod
    def autopilot_noop_runner_contract() -> dict[str, Any]:
        required_fields = [
            "event_version",
            "noop_only",
            "dry_run",
            "execution_allowed",
            "runner_handshake_id",
            "runner_session_id",
            "runner_admission_id",
            "runner_simulation_id",
            "execution_intent_id",
            "handshake_status",
            "session_status",
            "admission_status",
            "simulation_status",
            "intent_status",
            "event_type",
            "idempotency_key",
            "preconditions",
            "blocked_reasons",
            "source_hash",
            "generated_at",
            "caveat",
        ]
        return {
            "noop_runner_schema_version": AUTOPILOT_NOOP_RUNNER_EVENT_VERSION,
            "noop_only": True,
            "dry_run": True,
            "execution_allowed": False,
            "real_runner_present": False,
            "job_queue_present": False,
            "safety_flags": AISystemRiskAssessmentService._noop_runner_safety_flags(),
            "supported_event_types": [AUTOPILOT_NOOP_RUNNER_EVENT_TYPE],
            "required_fields": required_fields,
            "idempotency_rules": {
                "deterministic_default_when_omitted": True,
                "active_event_reuse": True,
            },
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    @staticmethod
    def _noop_runner_active_statuses() -> set[str]:
        return {"logged", "blocked"}

    @classmethod
    def _noop_runner_default_idempotency_key(
        cls,
        *,
        handshake: GovernanceAutopilotRunnerHandshake,
        session: GovernanceAutopilotRunnerSession,
        admission: GovernanceAutopilotRunnerAdmission,
        simulation: GovernanceAutopilotRunnerSimulation,
        intent: GovernanceAutopilotExecutionIntent,
    ) -> str:
        return cls.sha256_hexdigest(
            {
                "runner_handshake_id": str(handshake.id),
                "runner_session_id": str(session.id),
                "runner_admission_id": str(admission.id),
                "runner_simulation_id": str(simulation.id),
                "execution_intent_id": str(intent.id),
                "handshake_status": handshake.handshake_status,
                "session_status": session.session_status,
                "admission_status": admission.admission_status,
                "simulation_status": simulation.simulation_status,
                "intent_status": intent.intent_status,
                "source_hash": str(handshake.handshake_sha256),
            }
        )

    @classmethod
    def _noop_runner_source_hash(
        cls,
        *,
        handshake: GovernanceAutopilotRunnerHandshake,
        session: GovernanceAutopilotRunnerSession,
        admission: GovernanceAutopilotRunnerAdmission,
        simulation: GovernanceAutopilotRunnerSimulation,
        intent: GovernanceAutopilotExecutionIntent,
    ) -> str:
        return cls.sha256_hexdigest(
            {
                "runner_handshake_sha256": handshake.handshake_sha256,
                "runner_handshake_fingerprint": handshake.handshake_fingerprint,
                "runner_session_id": str(session.id),
                "runner_admission_id": str(admission.id),
                "runner_simulation_id": str(simulation.id),
                "execution_intent_id": str(intent.id),
                "simulation_source_hash": simulation.source_hash,
                "intent_source_hash": intent.source_hash,
            }
        )

    @staticmethod
    def _noop_runner_result_payload() -> dict[str, Any]:
        return {
            "result_type": "noop",
            "action_executed": False,
            "side_effects_created": False,
            "source_records_mutated": False,
            "external_calls_made": False,
            "jobs_queued": False,
            "tasks_created": False,
            "reviews_created": False,
            "message": "No-op runner event recorded only. No execution occurred.",
        }

    @staticmethod
    def _noop_runner_blocked_reasons(event_payload_json: dict | list | None) -> list[str]:
        if not isinstance(event_payload_json, dict):
            return []
        raw = event_payload_json.get("blocked_reasons")
        if not isinstance(raw, list):
            return []
        reasons: list[str] = []
        for item in raw:
            if item is None:
                continue
            value = str(item).strip()
            if value:
                reasons.append(value)
        return sorted(set(reasons))

    @staticmethod
    def _noop_runner_safety_flags() -> dict[str, bool]:
        return {
            "execution_allowed": False,
            "real_runner_present": False,
            "job_queue_present": False,
            "noop_runner_only": True,
        }

    @staticmethod
    def autopilot_noop_runner_reports_contract() -> dict[str, Any]:
        return {
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "supported_report_types": list(AUTOPILOT_NOOP_RUNNER_REPORT_TYPES),
            "common_metadata_fields": [
                "report_schema_version",
                "report_type",
                "generated_at",
                "query_hash",
                "result_hash",
                "execution_allowed",
                "real_runner_present",
                "job_queue_present",
                "noop_runner_only",
                "caveat",
            ],
            "compatibility_policy_version": AUTOPILOT_NOOP_RUNNER_COMPATIBILITY_POLICY_VERSION,
            "compatibility_policy_endpoint": AUTOPILOT_NOOP_RUNNER_COMPATIBILITY_POLICY_ENDPOINT,
            "breaking_changes_require_new_schema_version": True,
            "additive_fields_allowed": True,
            "minimum_supported_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "current_supported_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "filter_options_endpoint": AUTOPILOT_NOOP_RUNNER_FILTER_OPTIONS_ENDPOINT,
            "pagination_contract_endpoint": AUTOPILOT_NOOP_RUNNER_PAGINATION_CONTRACT_ENDPOINT,
            "client_contract_endpoint": AUTOPILOT_NOOP_RUNNER_CLIENT_CONTRACT_ENDPOINT,
            "field_docs_endpoint": AUTOPILOT_NOOP_RUNNER_FIELD_DOCS_ENDPOINT,
            "display_metadata_endpoint": AUTOPILOT_NOOP_RUNNER_DISPLAY_METADATA_ENDPOINT,
            "localization_map_endpoint": AUTOPILOT_NOOP_RUNNER_LOCALIZATION_MAP_ENDPOINT,
            "client_hints_endpoint": AUTOPILOT_NOOP_RUNNER_CLIENT_HINTS_ENDPOINT,
            "bounded_export_limits": {
                "default_limit": AUTOPILOT_NOOP_RUNNER_DEFAULT_LIMIT,
                "max_limit": AUTOPILOT_NOOP_RUNNER_MAX_LIMIT,
                "offset_min": 0,
            },
            "safety_flags": AISystemRiskAssessmentService._noop_runner_safety_flags(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    @staticmethod
    def autopilot_noop_runner_compatibility_policy() -> dict[str, Any]:
        return {
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "compatibility_policy_version": AUTOPILOT_NOOP_RUNNER_COMPATIBILITY_POLICY_VERSION,
            "additive_fields_allowed": True,
            "breaking_changes_require_new_schema_version": True,
            "deprecated_fields_policy": AUTOPILOT_NOOP_RUNNER_DEPRECATED_FIELDS_POLICY,
            "minimum_supported_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "current_supported_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "stable_endpoint_families": list(AUTOPILOT_NOOP_RUNNER_STABLE_ENDPOINT_FAMILIES),
            "safety_flags": AISystemRiskAssessmentService._noop_runner_safety_flags(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    @staticmethod
    def autopilot_noop_runner_filter_options() -> dict[str, Any]:
        return {
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "supported_report_types": list(AUTOPILOT_NOOP_RUNNER_REPORT_TYPES),
            "supported_event_statuses": list(AUTOPILOT_NOOP_RUNNER_EVENT_STATUS_VALUES),
            "supported_event_types": [AUTOPILOT_NOOP_RUNNER_EVENT_TYPE],
            "supported_boolean_filters": ["blocked_only"],
            "supported_id_filters": [
                "runner_handshake_id",
                "runner_session_id",
                "runner_admission_id",
                "runner_simulation_id",
                "execution_intent_id",
            ],
            "supported_pagination_params": ["limit", "offset", "next_offset", "truncated"],
            "default_values": {
                "limit": AUTOPILOT_NOOP_RUNNER_DEFAULT_LIMIT,
                "offset": 0,
                "days": 30,
                "blocked_only": False,
            },
            "bounds": {
                "limit": {"min": 1, "max": AUTOPILOT_NOOP_RUNNER_MAX_LIMIT},
                "offset": {"min": 0},
                "days": {"min": 1, "max": 365},
            },
            "field_docs_endpoint": AUTOPILOT_NOOP_RUNNER_FIELD_DOCS_ENDPOINT,
            "display_metadata_endpoint": AUTOPILOT_NOOP_RUNNER_DISPLAY_METADATA_ENDPOINT,
            "client_hints_endpoint": AUTOPILOT_NOOP_RUNNER_CLIENT_HINTS_ENDPOINT,
            "safety_flags": AISystemRiskAssessmentService._noop_runner_safety_flags(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    @staticmethod
    def autopilot_noop_runner_pagination_contract() -> dict[str, Any]:
        return {
            "pagination_contract_version": AUTOPILOT_NOOP_RUNNER_PAGINATION_CONTRACT_VERSION,
            "supported_style": "offset_limit",
            "default_limit": AUTOPILOT_NOOP_RUNNER_DEFAULT_LIMIT,
            "max_limit": AUTOPILOT_NOOP_RUNNER_MAX_LIMIT,
            "offset_base": 0,
            "response_fields": ["limit", "offset", "truncated", "next_offset", "row_count"],
            "truncation_behavior": "truncated=true when offset + row_count < total_count; next_offset is null when not truncated",
            "field_docs_endpoint": AUTOPILOT_NOOP_RUNNER_FIELD_DOCS_ENDPOINT,
            "display_metadata_endpoint": AUTOPILOT_NOOP_RUNNER_DISPLAY_METADATA_ENDPOINT,
            "client_hints_endpoint": AUTOPILOT_NOOP_RUNNER_CLIENT_HINTS_ENDPOINT,
            "safety_flags": AISystemRiskAssessmentService._noop_runner_safety_flags(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    @staticmethod
    def autopilot_noop_runner_client_contract() -> dict[str, Any]:
        return {
            "client_contract_version": AUTOPILOT_NOOP_RUNNER_CLIENT_CONTRACT_VERSION,
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "compatibility_policy_version": AUTOPILOT_NOOP_RUNNER_COMPATIBILITY_POLICY_VERSION,
            "stable_endpoint_families": list(AUTOPILOT_NOOP_RUNNER_STABLE_ENDPOINT_FAMILIES),
            "supported_filters_by_endpoint": {
                "ledger": [
                    "event_status",
                    "runner_handshake_id",
                    "runner_session_id",
                    "runner_admission_id",
                    "runner_simulation_id",
                    "execution_intent_id",
                    "blocked_only",
                    "limit",
                    "offset",
                ],
                "bounded_export": [
                    "report_type",
                    "limit",
                    "offset",
                    "event_status",
                    "execution_intent_id",
                    "runner_handshake_id",
                ],
                "timeline": ["event_status", "days"],
                "checksum": [
                    "report_type",
                    "limit",
                    "offset",
                    "event_status",
                    "execution_intent_id",
                    "runner_handshake_id",
                ],
            },
            "pagination_contract": AISystemRiskAssessmentService.autopilot_noop_runner_pagination_contract(),
            "enum_values": {
                "report_types": list(AUTOPILOT_NOOP_RUNNER_REPORT_TYPES),
                "event_statuses": list(AUTOPILOT_NOOP_RUNNER_EVENT_STATUS_VALUES),
                "event_types": [AUTOPILOT_NOOP_RUNNER_EVENT_TYPE],
            },
            "default_limits": {"limit": AUTOPILOT_NOOP_RUNNER_DEFAULT_LIMIT, "offset": 0},
            "max_limits": {"limit": AUTOPILOT_NOOP_RUNNER_MAX_LIMIT},
            "field_docs_endpoint": AUTOPILOT_NOOP_RUNNER_FIELD_DOCS_ENDPOINT,
            "display_metadata_endpoint": AUTOPILOT_NOOP_RUNNER_DISPLAY_METADATA_ENDPOINT,
            "localization_map_endpoint": AUTOPILOT_NOOP_RUNNER_LOCALIZATION_MAP_ENDPOINT,
            "client_hints_endpoint": AUTOPILOT_NOOP_RUNNER_CLIENT_HINTS_ENDPOINT,
            "safety_flags": AISystemRiskAssessmentService._noop_runner_safety_flags(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    @staticmethod
    def _noop_runner_field_docs_catalog() -> dict[str, list[dict[str, Any]]]:
        return {
            "ledger": [
                {
                    "field_name": "event_status",
                    "label": "Event Status",
                    "description": "Lifecycle state for the no-op runner event.",
                    "data_type": "string",
                    "required": True,
                    "nullable": False,
                    "filterable": True,
                    "sortable": True,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "status_badge",
                    "localization_key": "noop_runner.fields.event_status",
                },
                {
                    "field_name": "execution_intent_id",
                    "label": "Execution Intent ID",
                    "description": "Execution-intent reference in the no-op control-plane chain.",
                    "data_type": "uuid",
                    "required": True,
                    "nullable": False,
                    "filterable": True,
                    "sortable": False,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "identifier",
                    "localization_key": "noop_runner.fields.execution_intent_id",
                },
                {
                    "field_name": "blocked_reasons",
                    "label": "Blocked Reasons",
                    "description": "Deterministic blocked reasons captured for blocked events.",
                    "data_type": "array[string]",
                    "required": True,
                    "nullable": False,
                    "filterable": False,
                    "sortable": False,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "pill_list",
                    "localization_key": "noop_runner.fields.blocked_reasons",
                },
                {
                    "field_name": "created_at",
                    "label": "Created At",
                    "description": "Creation timestamp for the no-op event record.",
                    "data_type": "datetime",
                    "required": True,
                    "nullable": False,
                    "filterable": False,
                    "sortable": True,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "timestamp",
                    "localization_key": "noop_runner.fields.created_at",
                },
            ],
            "timeline": [
                {
                    "field_name": "timeline_buckets",
                    "label": "Timeline Buckets",
                    "description": "Daily bucketed counts for no-op events over the requested horizon.",
                    "data_type": "array[object]",
                    "required": True,
                    "nullable": False,
                    "filterable": False,
                    "sortable": False,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "time_series",
                    "localization_key": "noop_runner.fields.timeline_buckets",
                }
            ],
            "blockers": [
                {
                    "field_name": "blocker_counts",
                    "label": "Blocker Counts",
                    "description": "Aggregate blocked events by blocker reason.",
                    "data_type": "object",
                    "required": True,
                    "nullable": False,
                    "filterable": False,
                    "sortable": False,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "reason_frequency",
                    "localization_key": "noop_runner.fields.blocker_counts",
                }
            ],
            "readiness": [
                {
                    "field_name": "no_event_for_ready_handshake_count",
                    "label": "Readiness Gap Count",
                    "description": "Count of ready handshakes without a no-op event.",
                    "data_type": "integer",
                    "required": True,
                    "nullable": False,
                    "filterable": False,
                    "sortable": False,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "metric",
                    "localization_key": "noop_runner.fields.no_event_for_ready_handshake_count",
                }
            ],
            "idempotency": [
                {
                    "field_name": "active_duplicate_records_count",
                    "label": "Active Duplicate Records",
                    "description": "Count of active duplicates for the same idempotency key.",
                    "data_type": "integer",
                    "required": True,
                    "nullable": False,
                    "filterable": False,
                    "sortable": False,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "metric_alert_on_nonzero",
                    "localization_key": "noop_runner.fields.active_duplicate_records_count",
                }
            ],
            "control_plane_health": [
                {
                    "field_name": "health_status",
                    "label": "Health Status",
                    "description": "Computed control-plane health label based on no-op diagnostics only.",
                    "data_type": "string",
                    "required": True,
                    "nullable": False,
                    "filterable": False,
                    "sortable": False,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "status_badge",
                    "localization_key": "noop_runner.fields.health_status",
                }
            ],
            "bounded_export": [
                {
                    "field_name": "result_hash",
                    "label": "Result Hash",
                    "description": "Deterministic hash over bounded-export response payload.",
                    "data_type": "string",
                    "required": True,
                    "nullable": False,
                    "filterable": False,
                    "sortable": False,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "hash",
                    "localization_key": "noop_runner.fields.result_hash",
                }
            ],
            "checksum": [
                {
                    "field_name": "query_hash",
                    "label": "Query Hash",
                    "description": "Deterministic hash for checksum query inputs.",
                    "data_type": "string",
                    "required": True,
                    "nullable": False,
                    "filterable": False,
                    "sortable": False,
                    "stable_since": "noop_runner_reports.v1",
                    "deprecated": False,
                    "replacement_field": None,
                    "display_hint": "hash",
                    "localization_key": "noop_runner.fields.query_hash",
                }
            ],
        }

    @staticmethod
    def autopilot_noop_runner_field_docs(*, report_type: str | None) -> dict[str, Any]:
        allowed = set(AUTOPILOT_NOOP_RUNNER_REPORT_TYPES) | {"bounded_export", "checksum"}
        if report_type is not None:
            report_type = validate_choice(report_type, allowed, "report_type", status_code=status.HTTP_400_BAD_REQUEST)
        catalog = AISystemRiskAssessmentService._noop_runner_field_docs_catalog()
        return {
            "field_docs_version": AUTOPILOT_NOOP_RUNNER_FIELD_DOCS_VERSION,
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "compatibility_policy_version": AUTOPILOT_NOOP_RUNNER_COMPATIBILITY_POLICY_VERSION,
            "report_type": report_type,
            "field_docs": catalog.get(report_type, catalog) if report_type else catalog,
            "safety_flags": AISystemRiskAssessmentService._noop_runner_safety_flags(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    @staticmethod
    def autopilot_noop_runner_display_metadata(*, report_type: str | None) -> dict[str, Any]:
        allowed = set(AUTOPILOT_NOOP_RUNNER_REPORT_TYPES) | {"bounded_export", "checksum"}
        if report_type is not None:
            report_type = validate_choice(report_type, allowed, "report_type", status_code=status.HTTP_400_BAD_REQUEST)
        display_catalog: dict[str, dict[str, Any]] = {
            "ledger": {
                "table_columns": ["event_status", "event_type", "execution_intent_id", "blocked_reasons", "created_at"],
                "default_sort": {"field": "created_at", "direction": "desc"},
                "recommended_grouping": ["event_status"],
            },
            "timeline": {
                "table_columns": ["day", "total_count", "logged_count", "blocked_count", "archived_count"],
                "default_sort": {"field": "day", "direction": "asc"},
                "recommended_grouping": ["day"],
            },
            "blockers": {
                "table_columns": ["reason", "count"],
                "default_sort": {"field": "count", "direction": "desc"},
                "recommended_grouping": ["reason"],
            },
            "readiness": {
                "table_columns": ["ready_handshake_count", "no_op_logged_count", "no_event_for_ready_handshake_count"],
                "default_sort": {"field": "no_event_for_ready_handshake_count", "direction": "desc"},
                "recommended_grouping": [],
            },
            "idempotency": {
                "table_columns": [
                    "unique_idempotency_key_count",
                    "duplicate_key_attempts_inferred_count",
                    "active_duplicate_records_count",
                ],
                "default_sort": {"field": "active_duplicate_records_count", "direction": "desc"},
                "recommended_grouping": [],
            },
            "control_plane_health": {
                "table_columns": ["health_status", "blocked_event_count", "readiness_gap_count", "health_reasons"],
                "default_sort": {"field": "health_status", "direction": "asc"},
                "recommended_grouping": ["health_status"],
            },
            "bounded_export": {
                "table_columns": ["report_type", "row_count", "truncated", "query_hash", "result_hash"],
                "default_sort": {"field": "report_type", "direction": "asc"},
                "recommended_grouping": ["report_type"],
            },
            "checksum": {
                "table_columns": ["report_type", "row_count", "query_hash", "result_hash", "generated_at"],
                "default_sort": {"field": "generated_at", "direction": "desc"},
                "recommended_grouping": ["report_type"],
            },
        }
        default_empty_state = {
            "title": "No no-op runner diagnostics available yet",
            "description": "No read-only diagnostics rows were found for the selected filters.",
            "recommended_action": "Create a no-op runner event from an eligible handshake.",
        }
        status_badges = {
            "logged": {"label": "Logged", "tone": "success"},
            "blocked": {"label": "Blocked", "tone": "warning"},
            "archived": {"label": "Archived", "tone": "muted"},
        }
        severity_mapping = {"healthy": "low", "warning": "medium", "attention_required": "high"}
        selected = display_catalog.get(report_type, {})
        return {
            "display_metadata_version": AUTOPILOT_NOOP_RUNNER_DISPLAY_METADATA_VERSION,
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "report_type": report_type,
            "table_columns": selected.get("table_columns", {key: value["table_columns"] for key, value in display_catalog.items()}),
            "default_sort": selected.get("default_sort", {"field": "created_at", "direction": "desc"}),
            "recommended_grouping": selected.get("recommended_grouping", []),
            "empty_state": default_empty_state,
            "severity_mapping": severity_mapping,
            "status_badges": status_badges,
            "safety_flags": AISystemRiskAssessmentService._noop_runner_safety_flags(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    @staticmethod
    def autopilot_noop_runner_localization_map() -> dict[str, Any]:
        keys = {
            "noop_runner.fields.event_status": "Event Status",
            "noop_runner.fields.execution_intent_id": "Execution Intent ID",
            "noop_runner.fields.blocked_reasons": "Blocked Reasons",
            "noop_runner.fields.created_at": "Created At",
            "noop_runner.fields.timeline_buckets": "Timeline Buckets",
            "noop_runner.fields.blocker_counts": "Blocker Counts",
            "noop_runner.fields.no_event_for_ready_handshake_count": "Readiness Gap Count",
            "noop_runner.fields.active_duplicate_records_count": "Active Duplicate Records",
            "noop_runner.fields.health_status": "Health Status",
            "noop_runner.fields.result_hash": "Result Hash",
            "noop_runner.fields.query_hash": "Query Hash",
            "noop_runner.empty_state.title": "No no-op runner diagnostics available yet",
            "noop_runner.empty_state.description": "No read-only diagnostics rows were found for the selected filters.",
            "noop_runner.empty_state.recommended_action": "Create a no-op runner event from an eligible handshake.",
            "noop_runner.status.logged": "Logged",
            "noop_runner.status.blocked": "Blocked",
            "noop_runner.status.archived": "Archived",
        }
        return {
            "localization_map_version": AUTOPILOT_NOOP_RUNNER_LOCALIZATION_MAP_VERSION,
            "default_locale": "en",
            "supported_locales": ["en"],
            "keys": keys,
            "safety_flags": AISystemRiskAssessmentService._noop_runner_safety_flags(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    @staticmethod
    def autopilot_noop_runner_client_hints() -> dict[str, Any]:
        return {
            "client_hints_version": AUTOPILOT_NOOP_RUNNER_CLIENT_HINTS_VERSION,
            "recommended_refresh_seconds": 60,
            "cache_policy": "client may cache metadata responses; report data should be refreshed on demand",
            "pagination_hints": {
                "style": "offset_limit",
                "default_limit": AUTOPILOT_NOOP_RUNNER_DEFAULT_LIMIT,
                "max_limit": AUTOPILOT_NOOP_RUNNER_MAX_LIMIT,
                "pagination_contract_endpoint": AUTOPILOT_NOOP_RUNNER_PAGINATION_CONTRACT_ENDPOINT,
            },
            "filter_hints": {
                "filter_options_endpoint": AUTOPILOT_NOOP_RUNNER_FILTER_OPTIONS_ENDPOINT,
                "supported_report_types": list(AUTOPILOT_NOOP_RUNNER_REPORT_TYPES),
            },
            "empty_state_hints": {
                "title_key": "noop_runner.empty_state.title",
                "description_key": "noop_runner.empty_state.description",
                "recommended_action_key": "noop_runner.empty_state.recommended_action",
            },
            "safety_flags": AISystemRiskAssessmentService._noop_runner_safety_flags(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def _noop_runner_build_report_payload(
        self,
        *,
        organization_id: uuid.UUID,
        report_type: str,
        event_status: str | None,
        execution_intent_id: uuid.UUID | None,
        runner_handshake_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Any, int]:
        if report_type == "ledger":
            rows = self.noop_runner_operator_ledger(
                organization_id=organization_id,
                event_status=event_status,
                runner_handshake_id=runner_handshake_id,
                runner_session_id=None,
                runner_admission_id=None,
                runner_simulation_id=None,
                execution_intent_id=execution_intent_id,
                blocked_only=False,
                limit=limit,
                offset=offset,
            )
            return rows, len(rows)
        if report_type == "timeline":
            payload = self.noop_runner_timeline_report(
                organization_id=organization_id,
                event_status=event_status,
                days=min(max(limit, 1), 365),
            )
            return payload, int(len(payload.get("timeline_buckets", [])))
        if report_type == "blockers":
            payload = self.noop_runner_blocker_report(organization_id=organization_id)
            return payload, int(payload.get("total_blocked_events", 0))
        if report_type == "readiness":
            payload = self.noop_runner_readiness_report(organization_id=organization_id)
            return payload, int(payload.get("ready_handshake_count", 0))
        if report_type == "idempotency":
            payload = self.noop_runner_idempotency_report(organization_id=organization_id)
            return payload, int(payload.get("total_events", 0))
        if report_type == "control_plane_health":
            payload = self.noop_runner_control_plane_health_report(organization_id=organization_id)
            return payload, int(payload.get("total_noop_events", 0))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid report_type")

    def _noop_runner_ledger_total_count(
        self,
        *,
        organization_id: uuid.UUID,
        event_status: str | None,
        execution_intent_id: uuid.UUID | None,
        runner_handshake_id: uuid.UUID | None,
    ) -> int:
        query = select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
            GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id
        )
        if event_status is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.event_status == event_status)
        if execution_intent_id is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.execution_intent_id == execution_intent_id)
        if runner_handshake_id is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.runner_handshake_id == runner_handshake_id)
        return int(self.db.execute(query).scalar_one())

    def noop_runner_diagnostics_manifest(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        latest_noop_event_at = self.db.execute(
            select(func.max(GovernanceAutopilotNoopRunnerEvent.created_at)).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id
            )
        ).scalar_one_or_none()
        total_noop_events = int(
            self.db.execute(
                select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                    GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id
                )
            ).scalar_one()
        )
        safety_flags = self._noop_runner_safety_flags()
        return {
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "compatibility_policy_version": AUTOPILOT_NOOP_RUNNER_COMPATIBILITY_POLICY_VERSION,
            "compatibility_policy_endpoint": AUTOPILOT_NOOP_RUNNER_COMPATIBILITY_POLICY_ENDPOINT,
            "minimum_supported_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "current_supported_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "filter_options_endpoint": AUTOPILOT_NOOP_RUNNER_FILTER_OPTIONS_ENDPOINT,
            "pagination_contract_endpoint": AUTOPILOT_NOOP_RUNNER_PAGINATION_CONTRACT_ENDPOINT,
            "client_contract_endpoint": AUTOPILOT_NOOP_RUNNER_CLIENT_CONTRACT_ENDPOINT,
            "field_docs_endpoint": AUTOPILOT_NOOP_RUNNER_FIELD_DOCS_ENDPOINT,
            "display_metadata_endpoint": AUTOPILOT_NOOP_RUNNER_DISPLAY_METADATA_ENDPOINT,
            "localization_map_endpoint": AUTOPILOT_NOOP_RUNNER_LOCALIZATION_MAP_ENDPOINT,
            "client_hints_endpoint": AUTOPILOT_NOOP_RUNNER_CLIENT_HINTS_ENDPOINT,
            "available_reports": list(AUTOPILOT_NOOP_RUNNER_REPORT_TYPES),
            "endpoint_map": {
                "ledger": "/api/v1/ai-governance/autopilot/noop-runner/ledger",
                "timeline": "/api/v1/ai-governance/autopilot/noop-runner/reports/timeline",
                "blockers": "/api/v1/ai-governance/autopilot/noop-runner/reports/blockers",
                "readiness": "/api/v1/ai-governance/autopilot/noop-runner/reports/readiness",
                "idempotency": "/api/v1/ai-governance/autopilot/noop-runner/reports/idempotency",
                "control_plane_health": "/api/v1/ai-governance/autopilot/noop-runner/reports/control-plane-health",
            },
            "safety_flags": safety_flags,
            **safety_flags,
            "latest_noop_event_at": latest_noop_event_at,
            "total_noop_events": total_noop_events,
            "known_limitations": [
                "read_only_json_only",
                "no_file_exports",
                "no_external_storage",
                "no_execution_side_effects",
            ],
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def noop_runner_bounded_export(
        self,
        *,
        organization_id: uuid.UUID,
        report_type: str,
        limit: int,
        offset: int,
        event_status: str | None,
        execution_intent_id: uuid.UUID | None,
        runner_handshake_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        report_type = validate_choice(report_type, AUTOPILOT_NOOP_RUNNER_REPORT_TYPES, "report_type", status_code=status.HTTP_400_BAD_REQUEST)
        bounded_limit = min(max(int(limit), 1), AUTOPILOT_NOOP_RUNNER_MAX_LIMIT)
        bounded_offset = max(int(offset), 0)
        query_payload = self.to_json_compatible(
            {
                "organization_id": str(organization_id),
                "report_type": report_type,
                "limit": bounded_limit,
                "offset": bounded_offset,
                "event_status": event_status,
                "execution_intent_id": str(execution_intent_id) if execution_intent_id else None,
                "runner_handshake_id": str(runner_handshake_id) if runner_handshake_id else None,
            }
        )
        query_hash = self._sha256_for_json_like(query_payload)
        generated_at = self.now()
        result_payload, row_count = self._noop_runner_build_report_payload(
            organization_id=organization_id,
            report_type=report_type,
            event_status=event_status,
            execution_intent_id=execution_intent_id,
            runner_handshake_id=runner_handshake_id,
            limit=bounded_limit,
            offset=bounded_offset,
        )
        total_count = row_count
        if report_type == "ledger":
            total_count = self._noop_runner_ledger_total_count(
                organization_id=organization_id,
                event_status=event_status,
                execution_intent_id=execution_intent_id,
                runner_handshake_id=runner_handshake_id,
            )
        truncated = bool(bounded_offset + row_count < total_count)
        next_offset = int(bounded_offset + row_count) if truncated else None
        body: dict[str, Any] = {
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "report_type": report_type,
            "generated_at": generated_at,
            "query": query_payload,
            "query_hash": query_hash,
            "limit": bounded_limit,
            "offset": bounded_offset,
            "truncated": truncated,
            "next_offset": next_offset,
            "row_count": int(row_count),
            "pagination": {
                "limit": bounded_limit,
                "offset": bounded_offset,
                "truncated": truncated,
                "next_offset": next_offset,
                "row_count": int(row_count),
                "max_limit": AUTOPILOT_NOOP_RUNNER_MAX_LIMIT,
                "pagination_contract_version": AUTOPILOT_NOOP_RUNNER_PAGINATION_CONTRACT_VERSION,
            },
            "safety_flags": self._noop_runner_safety_flags(),
            **self._noop_runner_safety_flags(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }
        if report_type == "ledger":
            body["rows"] = self.to_json_compatible(result_payload)
            result_hash_payload = {
                "report_type": report_type,
                "rows": body["rows"],
                "row_count": body["row_count"],
                "limit": bounded_limit,
                "offset": bounded_offset,
            }
        else:
            body["report_payload"] = self.to_json_compatible(result_payload)
            result_hash_payload = {
                "report_type": report_type,
                "report_payload": body["report_payload"],
                "row_count": body["row_count"],
                "limit": bounded_limit,
                "offset": bounded_offset,
            }
        body["result_hash"] = self._sha256_for_json_like(result_hash_payload)
        return body

    def noop_runner_report_checksum(
        self,
        *,
        organization_id: uuid.UUID,
        report_type: str,
        limit: int,
        offset: int,
        event_status: str | None,
        execution_intent_id: uuid.UUID | None,
        runner_handshake_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        export = self.noop_runner_bounded_export(
            organization_id=organization_id,
            report_type=report_type,
            limit=limit,
            offset=offset,
            event_status=event_status,
            execution_intent_id=execution_intent_id,
            runner_handshake_id=runner_handshake_id,
        )
        return {
            "report_type": report_type,
            "query_hash": export["query_hash"],
            "result_hash": export["result_hash"],
            "row_count": export["row_count"],
            "generated_at": export["generated_at"],
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def _noop_runner_preview_data(
        self,
        *,
        organization_id: uuid.UUID,
        handshake_id: uuid.UUID,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        handshake = self.require_runner_handshake(organization_id=organization_id, handshake_id=handshake_id)
        session = self.require_runner_session(organization_id=organization_id, session_id=handshake.runner_session_id)
        admission = self.require_runner_admission(organization_id=organization_id, admission_id=handshake.runner_admission_id)
        simulation = self.require_runner_simulation(
            organization_id=organization_id,
            simulation_id=handshake.runner_simulation_id,
        )
        intent = self.require_execution_intent(organization_id=organization_id, intent_id=handshake.execution_intent_id)

        blocked_reasons: list[str] = []
        if handshake.runner_session_id != session.id:
            blocked_reasons.append("handshake_session_mismatch")
        if handshake.runner_admission_id != admission.id:
            blocked_reasons.append("handshake_admission_mismatch")
        if handshake.runner_simulation_id != simulation.id:
            blocked_reasons.append("handshake_simulation_mismatch")
        if handshake.execution_intent_id != intent.id:
            blocked_reasons.append("handshake_intent_mismatch")
        if session.runner_admission_id != admission.id:
            blocked_reasons.append("session_admission_mismatch")
        if session.runner_simulation_id != simulation.id:
            blocked_reasons.append("session_simulation_mismatch")
        if session.execution_intent_id != intent.id:
            blocked_reasons.append("session_intent_mismatch")
        if admission.runner_simulation_id != simulation.id:
            blocked_reasons.append("admission_simulation_mismatch")
        if admission.execution_intent_id != intent.id:
            blocked_reasons.append("admission_intent_mismatch")
        if simulation.execution_intent_id != intent.id:
            blocked_reasons.append("simulation_intent_mismatch")
        if handshake.handshake_status != "ready_for_future_runner":
            blocked_reasons.append("handshake_not_ready_for_future_runner")
        if handshake.revoked_at is not None or handshake.handshake_status == "revoked":
            blocked_reasons.append("handshake_revoked")
        if handshake.archived_at is not None or handshake.handshake_status == "archived":
            blocked_reasons.append("handshake_archived")
        if session.session_status != "active":
            blocked_reasons.append("session_not_active")
        if self._as_utc(session.expires_at) <= self.now():
            blocked_reasons.append("session_expired")
        if admission.admission_status != "admitted":
            blocked_reasons.append("admission_not_admitted")
        if simulation.archived_at is not None or simulation.simulation_status == "archived":
            blocked_reasons.append("simulation_archived")
        if intent.archived_at is not None or intent.intent_status == "archived":
            blocked_reasons.append("intent_archived")

        status = "logged" if len(blocked_reasons) == 0 else "blocked"
        effective_idempotency_key = idempotency_key or self._noop_runner_default_idempotency_key(
            handshake=handshake,
            session=session,
            admission=admission,
            simulation=simulation,
            intent=intent,
        )
        blocked_reasons = sorted(set(blocked_reasons))
        source_hash = self._noop_runner_source_hash(
            handshake=handshake,
            session=session,
            admission=admission,
            simulation=simulation,
            intent=intent,
        )
        preconditions = [
            {"key": "noop_only_true", "met": True},
            {"key": "dry_run_true", "met": True},
            {"key": "execution_allowed_false", "met": True},
            {"key": "handshake_ready_for_future_runner", "met": handshake.handshake_status == "ready_for_future_runner"},
            {"key": "session_active", "met": session.session_status == "active"},
            {"key": "session_unexpired", "met": self._as_utc(session.expires_at) > self.now()},
            {"key": "admission_admitted", "met": admission.admission_status == "admitted"},
            {"key": "simulation_non_archived", "met": simulation.archived_at is None and simulation.simulation_status != "archived"},
            {"key": "intent_non_archived", "met": intent.archived_at is None and intent.intent_status != "archived"},
        ]
        event_payload_json = {
            "event_version": AUTOPILOT_NOOP_RUNNER_EVENT_VERSION,
            "noop_only": True,
            "dry_run": True,
            "execution_allowed": False,
            "runner_handshake_id": str(handshake.id),
            "runner_session_id": str(session.id),
            "runner_admission_id": str(admission.id),
            "runner_simulation_id": str(simulation.id),
            "execution_intent_id": str(intent.id),
            "handshake_status": handshake.handshake_status,
            "session_status": session.session_status,
            "admission_status": admission.admission_status,
            "simulation_status": simulation.simulation_status,
            "intent_status": intent.intent_status,
            "event_type": AUTOPILOT_NOOP_RUNNER_EVENT_TYPE,
            "idempotency_key": effective_idempotency_key,
            "preconditions": preconditions,
            "blocked_reasons": blocked_reasons,
            "source_hash": source_hash,
            "generated_at": self.now().isoformat(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }
        return {
            "handshake": handshake,
            "session": session,
            "admission": admission,
            "simulation": simulation,
            "intent": intent,
            "idempotency_key": effective_idempotency_key,
            "proposed_event_status": status,
            "would_log_event": status == "logged",
            "blocked_reasons": blocked_reasons,
            "source_hash": source_hash,
            "event_payload_json": event_payload_json,
            "noop_result_json": self._noop_runner_result_payload(),
        }

    def preview_noop_runner_event(
        self,
        *,
        organization_id: uuid.UUID,
        handshake_id: uuid.UUID,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        preview = self._noop_runner_preview_data(
            organization_id=organization_id,
            handshake_id=handshake_id,
            idempotency_key=idempotency_key,
        )
        handshake: GovernanceAutopilotRunnerHandshake = preview["handshake"]
        return {
            "runner_handshake_id": handshake.id,
            "runner_session_id": preview["session"].id,
            "runner_admission_id": preview["admission"].id,
            "runner_simulation_id": preview["simulation"].id,
            "execution_intent_id": preview["intent"].id,
            "would_log_event": bool(preview["would_log_event"]),
            "proposed_event_status": preview["proposed_event_status"],
            "event_payload_json": self.to_json_compatible(preview["event_payload_json"]),
            "noop_result_json": self.to_json_compatible(preview["noop_result_json"]),
            "blocked_reasons": preview["blocked_reasons"],
            "idempotency_key": preview["idempotency_key"],
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def _find_existing_noop_runner_event(
        self,
        *,
        organization_id: uuid.UUID,
        idempotency_key: str,
    ) -> GovernanceAutopilotNoopRunnerEvent | None:
        return self.db.execute(
            select(GovernanceAutopilotNoopRunnerEvent).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id,
                GovernanceAutopilotNoopRunnerEvent.idempotency_key == idempotency_key,
                GovernanceAutopilotNoopRunnerEvent.event_status.in_(self._noop_runner_active_statuses()),
                GovernanceAutopilotNoopRunnerEvent.archived_at.is_(None),
            )
        ).scalar_one_or_none()

    def create_noop_runner_event(
        self,
        *,
        organization_id: uuid.UUID,
        handshake_id: uuid.UUID,
        idempotency_key: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> tuple[GovernanceAutopilotNoopRunnerEvent, bool]:
        preview = self._noop_runner_preview_data(
            organization_id=organization_id,
            handshake_id=handshake_id,
            idempotency_key=idempotency_key,
        )
        existing = self._find_existing_noop_runner_event(
            organization_id=organization_id,
            idempotency_key=preview["idempotency_key"],
        )
        if existing is not None:
            return existing, False

        event_payload_json = self.to_json_compatible(preview["event_payload_json"])
        event_sha256 = self._sha256_for_json_like(event_payload_json)
        row = GovernanceAutopilotNoopRunnerEvent(
            organization_id=organization_id,
            runner_handshake_id=preview["handshake"].id,
            runner_session_id=preview["session"].id,
            runner_admission_id=preview["admission"].id,
            runner_simulation_id=preview["simulation"].id,
            execution_intent_id=preview["intent"].id,
            event_status=preview["proposed_event_status"],
            event_type=AUTOPILOT_NOOP_RUNNER_EVENT_TYPE,
            noop_only=True,
            dry_run=True,
            execution_allowed=False,
            idempotency_key=preview["idempotency_key"],
            event_payload_json=event_payload_json,
            noop_result_json=self.to_json_compatible(preview["noop_result_json"]),
            source_hash=str(preview["source_hash"]),
            event_sha256=event_sha256,
            created_by_user_id=actor_user_id,
        )
        self.db.add(row)
        self.db.flush()
        return row, True

    def require_noop_runner_event(
        self,
        *,
        organization_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> GovernanceAutopilotNoopRunnerEvent:
        row = self.db.execute(
            select(GovernanceAutopilotNoopRunnerEvent).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id,
                GovernanceAutopilotNoopRunnerEvent.id == event_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No-op runner event not found")
        return row

    def list_noop_runner_events(
        self,
        *,
        organization_id: uuid.UUID,
        runner_handshake_id: uuid.UUID | None,
        execution_intent_id: uuid.UUID | None,
        event_status: str | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceAutopilotNoopRunnerEvent]:
        if runner_handshake_id is not None:
            self.require_runner_handshake(organization_id=organization_id, handshake_id=runner_handshake_id)
        if execution_intent_id is not None:
            self.require_execution_intent(organization_id=organization_id, intent_id=execution_intent_id)
        if event_status is not None:
            event_status = validate_choice(event_status, AUTOPILOT_NOOP_RUNNER_EVENT_STATUS_VALUES, "event_status", status_code=status.HTTP_400_BAD_REQUEST)
        query = select(GovernanceAutopilotNoopRunnerEvent).where(
            GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id
        )
        if runner_handshake_id is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.runner_handshake_id == runner_handshake_id)
        if execution_intent_id is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.execution_intent_id == execution_intent_id)
        if event_status is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.event_status == event_status)
        query = query.order_by(
            GovernanceAutopilotNoopRunnerEvent.created_at.desc(),
            GovernanceAutopilotNoopRunnerEvent.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def noop_runner_operator_ledger(
        self,
        *,
        organization_id: uuid.UUID,
        event_status: str | None,
        runner_handshake_id: uuid.UUID | None,
        runner_session_id: uuid.UUID | None,
        runner_admission_id: uuid.UUID | None,
        runner_simulation_id: uuid.UUID | None,
        execution_intent_id: uuid.UUID | None,
        blocked_only: bool,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        if event_status is not None:
            event_status = validate_choice(event_status, AUTOPILOT_NOOP_RUNNER_EVENT_STATUS_VALUES, "event_status", status_code=status.HTTP_400_BAD_REQUEST)
        if runner_handshake_id is not None:
            self.require_runner_handshake(organization_id=organization_id, handshake_id=runner_handshake_id)
        if runner_session_id is not None:
            self.require_runner_session(organization_id=organization_id, session_id=runner_session_id)
        if runner_admission_id is not None:
            self.require_runner_admission(organization_id=organization_id, admission_id=runner_admission_id)
        if runner_simulation_id is not None:
            self.require_runner_simulation(organization_id=organization_id, simulation_id=runner_simulation_id)
        if execution_intent_id is not None:
            self.require_execution_intent(organization_id=organization_id, intent_id=execution_intent_id)

        query = select(GovernanceAutopilotNoopRunnerEvent).where(
            GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id
        )
        if event_status is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.event_status == event_status)
        if runner_handshake_id is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.runner_handshake_id == runner_handshake_id)
        if runner_session_id is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.runner_session_id == runner_session_id)
        if runner_admission_id is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.runner_admission_id == runner_admission_id)
        if runner_simulation_id is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.runner_simulation_id == runner_simulation_id)
        if execution_intent_id is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.execution_intent_id == execution_intent_id)
        if blocked_only:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.event_status == "blocked")

        rows = list(
            self.db.execute(
                query.order_by(
                    GovernanceAutopilotNoopRunnerEvent.created_at.desc(),
                    GovernanceAutopilotNoopRunnerEvent.id.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "event_id": row.id,
                "event_status": row.event_status,
                "event_type": row.event_type,
                "runner_handshake_id": row.runner_handshake_id,
                "runner_session_id": row.runner_session_id,
                "runner_admission_id": row.runner_admission_id,
                "runner_simulation_id": row.runner_simulation_id,
                "execution_intent_id": row.execution_intent_id,
                "noop_only": bool(row.noop_only),
                "dry_run": bool(row.dry_run),
                "execution_allowed": bool(row.execution_allowed),
                "idempotency_key": row.idempotency_key,
                "blocked_reasons": self._noop_runner_blocked_reasons(row.event_payload_json),
                "source_hash": row.source_hash,
                "event_sha256": row.event_sha256,
                "created_at": row.created_at,
                "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
            }
            for row in rows
        ]

    def noop_runner_timeline_report(
        self,
        *,
        organization_id: uuid.UUID,
        event_status: str | None,
        days: int,
    ) -> dict[str, Any]:
        if event_status is not None:
            event_status = validate_choice(event_status, AUTOPILOT_NOOP_RUNNER_EVENT_STATUS_VALUES, "event_status", status_code=status.HTTP_400_BAD_REQUEST)
        bounded_days = min(max(int(days), 1), 365)
        start_date = self.now().date() - timedelta(days=bounded_days - 1)
        start_at = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)

        query = select(GovernanceAutopilotNoopRunnerEvent).where(
            GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id,
            GovernanceAutopilotNoopRunnerEvent.created_at >= start_at,
        )
        if event_status is not None:
            query = query.where(GovernanceAutopilotNoopRunnerEvent.event_status == event_status)

        rows = list(
            self.db.execute(
                query.order_by(
                    GovernanceAutopilotNoopRunnerEvent.created_at.asc(),
                    GovernanceAutopilotNoopRunnerEvent.id.asc(),
                )
            )
            .scalars()
            .all()
        )

        day_buckets: dict[str, dict[str, int | str]] = {}
        for day_offset in range(bounded_days):
            day_value = (start_date + timedelta(days=day_offset)).isoformat()
            day_buckets[day_value] = {
                "day": day_value,
                "total_count": 0,
                "logged_count": 0,
                "blocked_count": 0,
                "archived_count": 0,
            }

        for row in rows:
            day_key = self._as_utc(row.created_at).date().isoformat()
            if day_key not in day_buckets:
                continue
            bucket = day_buckets[day_key]
            bucket["total_count"] = int(bucket["total_count"]) + 1
            if row.event_status == "logged":
                bucket["logged_count"] = int(bucket["logged_count"]) + 1
            elif row.event_status == "blocked":
                bucket["blocked_count"] = int(bucket["blocked_count"]) + 1
            elif row.event_status == "archived":
                bucket["archived_count"] = int(bucket["archived_count"]) + 1

        by_status = {"logged": 0, "blocked": 0, "archived": 0}
        for row in rows:
            if row.event_status in by_status:
                by_status[row.event_status] += 1

        return {
            "total_events": int(len(rows)),
            "timeline_buckets": list(day_buckets.values()),
            "logged_count": int(by_status["logged"]),
            "blocked_count": int(by_status["blocked"]),
            "archived_count": int(by_status["archived"]),
            "latest_event_at": max((row.created_at for row in rows), default=None),
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "generated_at": self.now(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def noop_runner_blocker_report(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        rows = list(
            self.db.execute(
                select(GovernanceAutopilotNoopRunnerEvent).where(
                    GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id,
                    GovernanceAutopilotNoopRunnerEvent.event_status == "blocked",
                )
            )
            .scalars()
            .all()
        )
        blocker_counts: dict[str, int] = {}
        affected_execution_intents: set[uuid.UUID] = set()
        for row in rows:
            affected_execution_intents.add(row.execution_intent_id)
            reasons = self._noop_runner_blocked_reasons(row.event_payload_json) or ["unknown_blocker"]
            for reason in reasons:
                blocker_counts[reason] = blocker_counts.get(reason, 0) + 1

        sorted_top = sorted(blocker_counts.items(), key=lambda item: (-item[1], item[0]))
        return {
            "total_blocked_events": int(len(rows)),
            "blocker_counts": blocker_counts,
            "top_blockers": [{"reason": reason, "count": int(count)} for reason, count in sorted_top[:10]],
            "affected_execution_intents": sorted(affected_execution_intents, key=str),
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "generated_at": self.now(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def noop_runner_readiness_report(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        ready_rows = list(
            self.db.execute(
                select(
                    GovernanceAutopilotRunnerHandshake.id,
                    GovernanceAutopilotRunnerHandshake.created_at,
                ).where(
                    GovernanceAutopilotRunnerHandshake.organization_id == organization_id,
                    GovernanceAutopilotRunnerHandshake.handshake_status == "ready_for_future_runner",
                )
            ).all()
        )
        ready_ids = {row[0] for row in ready_rows}
        latest_ready_handshake_at = max((row[1] for row in ready_rows), default=None)

        event_rows = list(
            self.db.execute(
                select(
                    GovernanceAutopilotNoopRunnerEvent.runner_handshake_id,
                    GovernanceAutopilotNoopRunnerEvent.event_status,
                    GovernanceAutopilotNoopRunnerEvent.created_at,
                ).where(
                    GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id,
                )
            ).all()
        )
        no_op_logged_count = sum(1 for _, status_value, _ in event_rows if status_value == "logged")
        blocked_event_count = sum(1 for _, status_value, _ in event_rows if status_value == "blocked")
        seen_ready_handshakes = {handshake_id for handshake_id, _, _ in event_rows if handshake_id in ready_ids}
        no_event_for_ready_handshake_count = int(len(ready_ids - seen_ready_handshakes))

        return {
            "ready_handshake_count": int(len(ready_ids)),
            "no_op_logged_count": int(no_op_logged_count),
            "blocked_event_count": int(blocked_event_count),
            "no_event_for_ready_handshake_count": no_event_for_ready_handshake_count,
            "latest_ready_handshake_at": latest_ready_handshake_at,
            "latest_noop_event_at": max((row[2] for row in event_rows), default=None),
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "generated_at": self.now(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def noop_runner_idempotency_report(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        grouped_rows = list(
            self.db.execute(
                select(
                    GovernanceAutopilotNoopRunnerEvent.idempotency_key,
                    func.count(GovernanceAutopilotNoopRunnerEvent.id),
                )
                .where(GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id)
                .group_by(GovernanceAutopilotNoopRunnerEvent.idempotency_key)
            ).all()
        )
        total_events = int(sum(int(count_value) for _, count_value in grouped_rows))
        unique_count = int(len(grouped_rows))
        duplicate_key_attempts_inferred_count = int(
            sum(max(int(count_value) - 1, 0) for _, count_value in grouped_rows)
        )
        keys_with_multiple_records = sorted(
            str(key) for key, count_value in grouped_rows if int(count_value) > 1 and key is not None
        )

        active_duplicate_rows = list(
            self.db.execute(
                select(
                    GovernanceAutopilotNoopRunnerEvent.idempotency_key,
                    func.count(GovernanceAutopilotNoopRunnerEvent.id),
                )
                .where(
                    GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id,
                    GovernanceAutopilotNoopRunnerEvent.archived_at.is_(None),
                    GovernanceAutopilotNoopRunnerEvent.event_status.in_(self._noop_runner_active_statuses()),
                )
                .group_by(GovernanceAutopilotNoopRunnerEvent.idempotency_key)
                .having(func.count(GovernanceAutopilotNoopRunnerEvent.id) > 1)
            ).all()
        )
        active_duplicate_records_count = int(
            sum(max(int(count_value) - 1, 0) for _, count_value in active_duplicate_rows)
        )
        return {
            "total_events": total_events,
            "unique_idempotency_key_count": unique_count,
            "duplicate_key_attempts_inferred_count": duplicate_key_attempts_inferred_count,
            "active_duplicate_records_count": active_duplicate_records_count,
            "idempotency_keys_with_multiple_records": keys_with_multiple_records,
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "generated_at": self.now(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def noop_runner_control_plane_health_report(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        total_noop_events = int(
            self.db.execute(
                select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                    GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id
                )
            ).scalar_one()
        )
        blocked_event_count = int(
            self.db.execute(
                select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                    GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id,
                    GovernanceAutopilotNoopRunnerEvent.event_status == "blocked",
                )
            ).scalar_one()
        )
        readiness = self.noop_runner_readiness_report(organization_id=organization_id)
        idempotency = self.noop_runner_idempotency_report(organization_id=organization_id)
        readiness_gap_count = int(readiness["no_event_for_ready_handshake_count"])

        health_reasons: list[str] = []
        health_status = "healthy"
        if int(idempotency["active_duplicate_records_count"]) > 0:
            health_status = "attention_required"
            health_reasons.append("active_duplicate_idempotency_records_detected")
        elif blocked_event_count > 0 or readiness_gap_count > 0:
            health_status = "warning"
            if blocked_event_count > 0:
                health_reasons.append("blocked_noop_events_present")
            if readiness_gap_count > 0:
                health_reasons.append("ready_handshakes_without_noop_event")
        else:
            health_reasons.append("control_plane_guardrails_healthy")

        return {
            "execution_allowed": False,
            "real_runner_present": False,
            "job_queue_present": False,
            "noop_runner_only": True,
            "total_noop_events": total_noop_events,
            "blocked_event_count": blocked_event_count,
            "readiness_gap_count": readiness_gap_count,
            "token_plaintext_storage_detected": False,
            "external_side_effects_enabled": False,
            "health_status": health_status,
            "health_reasons": health_reasons,
            "report_schema_version": AUTOPILOT_NOOP_RUNNER_REPORT_SCHEMA_VERSION,
            "generated_at": self.now(),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def noop_runner_event_payload(self, row: GovernanceAutopilotNoopRunnerEvent) -> dict[str, Any]:
        return {
            "id": row.id,
            "event_id": row.id,
            "organization_id": row.organization_id,
            "runner_handshake_id": row.runner_handshake_id,
            "runner_session_id": row.runner_session_id,
            "runner_admission_id": row.runner_admission_id,
            "runner_simulation_id": row.runner_simulation_id,
            "execution_intent_id": row.execution_intent_id,
            "event_status": row.event_status,
            "event_type": row.event_type,
            "noop_only": bool(row.noop_only),
            "dry_run": bool(row.dry_run),
            "execution_allowed": bool(row.execution_allowed),
            "idempotency_key": row.idempotency_key,
            "event_payload_json": row.event_payload_json,
            "noop_result_json": row.noop_result_json,
            "source_hash": row.source_hash,
            "event_sha256": row.event_sha256,
            "created_by_user_id": row.created_by_user_id,
            "archived_at": row.archived_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def verify_noop_runner_event(
        self,
        *,
        organization_id: uuid.UUID,
        event_id: uuid.UUID,
        event_payload_json: dict | list | None,
    ) -> dict[str, Any]:
        row = self.require_noop_runner_event(organization_id=organization_id, event_id=event_id)
        payload: dict | list = event_payload_json if event_payload_json is not None else row.event_payload_json
        errors: list[str] = []
        if not isinstance(payload, dict):
            errors.append("event_payload_must_be_object")
            return {"valid": False, "validation_errors": errors, "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT}

        required_fields = set(self.autopilot_noop_runner_contract()["required_fields"])
        for field in sorted(required_fields):
            if field not in payload:
                errors.append(f"missing_field:{field}")
        if payload.get("event_version") != AUTOPILOT_NOOP_RUNNER_EVENT_VERSION:
            errors.append("unsupported_event_version")
        if payload.get("event_type") != AUTOPILOT_NOOP_RUNNER_EVENT_TYPE:
            errors.append("unsupported_event_type")
        if payload.get("noop_only") is not True:
            errors.append("noop_only_must_be_true")
        if payload.get("dry_run") is not True:
            errors.append("dry_run_must_be_true")
        if payload.get("execution_allowed") is not False:
            errors.append("execution_allowed_must_be_false")
        if payload.get("idempotency_key") != row.idempotency_key:
            errors.append("idempotency_key_mismatch")
        if str(payload.get("runner_handshake_id")) != str(row.runner_handshake_id):
            errors.append("runner_handshake_id_mismatch")
        if str(payload.get("runner_session_id")) != str(row.runner_session_id):
            errors.append("runner_session_id_mismatch")
        if str(payload.get("runner_admission_id")) != str(row.runner_admission_id):
            errors.append("runner_admission_id_mismatch")
        if str(payload.get("runner_simulation_id")) != str(row.runner_simulation_id):
            errors.append("runner_simulation_id_mismatch")
        if str(payload.get("execution_intent_id")) != str(row.execution_intent_id):
            errors.append("execution_intent_id_mismatch")
        if payload.get("source_hash") != row.source_hash:
            errors.append("source_hash_mismatch")
        recomputed_sha = self._sha256_for_json_like(self.to_json_compatible(payload))
        if recomputed_sha != row.event_sha256:
            errors.append("event_sha256_mismatch")
        valid = len(errors) == 0
        return {
            "valid": valid,
            "validation_errors": sorted(set(errors)),
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    def archive_noop_runner_event(
        self,
        *,
        organization_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> GovernanceAutopilotNoopRunnerEvent:
        row = self.require_noop_runner_event(organization_id=organization_id, event_id=event_id)
        if row.event_status != "archived":
            row.event_status = "archived"
            row.archived_at = self.now()
        return row

    def noop_runner_event_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        rows = list(
            self.db.execute(
                select(
                    GovernanceAutopilotNoopRunnerEvent.event_status,
                    func.count(GovernanceAutopilotNoopRunnerEvent.id),
                )
                .where(GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id)
                .group_by(GovernanceAutopilotNoopRunnerEvent.event_status)
            ).all()
        )
        by_status = {str(k): int(v) for k, v in rows}
        latest_event_at = self.db.execute(
            select(func.max(GovernanceAutopilotNoopRunnerEvent.created_at)).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "total_events": int(sum(by_status.values())),
            "by_status": by_status,
            "logged_count": int(by_status.get("logged", 0)),
            "blocked_count": int(by_status.get("blocked", 0)),
            "archived_count": int(by_status.get("archived", 0)),
            "latest_event_at": latest_event_at,
            "caveat": AUTOPILOT_NOOP_RUNNER_CAVEAT,
        }

    @staticmethod
    def _extract_intent_decisions(capability_decisions_json: dict | list | None) -> list[dict[str, Any]]:
        payload = capability_decisions_json or {}
        if isinstance(payload, dict):
            if isinstance(payload.get("decisions"), list):
                return [dict(item) for item in payload["decisions"] if isinstance(item, dict)]
            if isinstance(payload.get("decision"), dict):
                return [dict(payload["decision"])]
        if isinstance(payload, list):
            return [dict(item) for item in payload if isinstance(item, dict)]
        return []

    def _approval_policy_requires_quorum(
        self,
        *,
        intent: GovernanceAutopilotExecutionIntent,
        decisions: list[dict[str, Any]],
        approval_policy: dict[str, Any],
    ) -> bool:
        if bool(intent.approval_required) or intent.intent_status == "approval_required":
            return True
        source_scope = {str(v) for v in approval_policy.get("require_quorum_for_source_types_json", [])}
        if str(intent.source_type) in source_scope:
            return True
        priority_scope = {str(v) for v in approval_policy.get("require_quorum_for_priority_bands_json", [])}
        for item in decisions:
            band = str(item.get("priority_band") or "")
            if band in priority_scope:
                return True
        return False

    def _autopilot_approval_policy_snapshot_for_intent(
        self,
        *,
        organization_id: uuid.UUID,
        intent: GovernanceAutopilotExecutionIntent,
    ) -> dict[str, Any]:
        snapshot = self.resolved_autopilot_approval_policy(organization_id=organization_id)
        # Backward-compatible alias: keep policy_id aligned with the execution intent policy.
        snapshot["policy_id"] = intent.policy_id
        return snapshot

    def _approval_policy_from_approval_row(
        self,
        *,
        organization_id: uuid.UUID,
        approval_row: GovernanceAutopilotExecutionApproval,
    ) -> dict[str, Any]:
        raw = approval_row.approval_policy_snapshot_json or {}
        if isinstance(raw, dict):
            required = {
                "minimum_approvals",
                "rejection_threshold",
                "require_distinct_approvers",
                "block_requester_self_approval",
                "require_quorum_for_priority_bands_json",
                "require_quorum_for_source_types_json",
            }
            if required.issubset(set(raw.keys())):
                out = dict(raw)
                out.setdefault("organization_id", organization_id)
                out.setdefault("resolved_source", "approval_request_snapshot")
                out.setdefault("caveat", AUTOPILOT_EXECUTION_QUORUM_CAVEAT)
                return out
        return self.resolved_autopilot_approval_policy(organization_id=organization_id)

    def _list_execution_approval_votes(
        self,
        *,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
    ) -> list[GovernanceAutopilotExecutionApprovalVote]:
        return list(
            self.db.execute(
                select(GovernanceAutopilotExecutionApprovalVote)
                .where(
                    GovernanceAutopilotExecutionApprovalVote.organization_id == organization_id,
                    GovernanceAutopilotExecutionApprovalVote.approval_id == approval_id,
                )
                .order_by(
                    GovernanceAutopilotExecutionApprovalVote.created_at.asc(),
                    GovernanceAutopilotExecutionApprovalVote.id.asc(),
                )
            ).scalars().all()
        )

    @staticmethod
    def _approval_vote_counts(votes: list[GovernanceAutopilotExecutionApprovalVote]) -> tuple[int, int]:
        approval_vote_count = int(sum(1 for row in votes if row.vote_status == "approved"))
        rejection_vote_count = int(sum(1 for row in votes if row.vote_status == "rejected"))
        return approval_vote_count, rejection_vote_count

    def _execution_approval_quorum_status(
        self,
        *,
        organization_id: uuid.UUID,
        approval_row: GovernanceAutopilotExecutionApproval,
        intent: GovernanceAutopilotExecutionIntent | None = None,
    ) -> dict[str, Any]:
        local_intent = intent or self.require_execution_intent(
            organization_id=organization_id,
            intent_id=approval_row.execution_intent_id,
        )
        approval_policy = self._approval_policy_from_approval_row(
            organization_id=organization_id,
            approval_row=approval_row,
        )
        votes = self._list_execution_approval_votes(
            organization_id=organization_id,
            approval_id=approval_row.id,
        )
        approval_vote_count, rejection_vote_count = self._approval_vote_counts(votes)
        minimum_approvals = int(approval_policy.get("minimum_approvals") or 1)
        rejection_threshold = int(approval_policy.get("rejection_threshold") or 1)
        quorum_met = approval_vote_count >= minimum_approvals
        rejection_threshold_met = rejection_vote_count >= rejection_threshold
        blocked_reasons = list(local_intent.blocked_reasons_json or [])
        if local_intent.intent_status == "archived" or local_intent.archived_at is not None:
            blocked_reasons.append("intent_archived")
        if local_intent.intent_status == "blocked" or bool(local_intent.blocked):
            blocked_reasons.append("intent_blocked")
        if rejection_threshold_met:
            blocked_reasons.append("rejection_threshold_met")
        ready_for_runner = (
            local_intent.intent_status != "archived"
            and local_intent.archived_at is None
            and not bool(local_intent.blocked)
            and local_intent.intent_status != "blocked"
            and approval_row.approval_status == "approved"
            and quorum_met
            and not rejection_threshold_met
        )
        return {
            "approval_id": approval_row.id,
            "execution_intent_id": approval_row.execution_intent_id,
            "approval_status": approval_row.approval_status,
            "minimum_approvals": minimum_approvals,
            "approval_vote_count": approval_vote_count,
            "rejection_vote_count": rejection_vote_count,
            "rejection_threshold": rejection_threshold,
            "quorum_met": quorum_met,
            "rejection_threshold_met": rejection_threshold_met,
            "ready_for_runner": ready_for_runner,
            "blocked_reasons": sorted(set(blocked_reasons)),
            "resolved_approval_policy": approval_policy,
            "caveat": AUTOPILOT_EXECUTION_QUORUM_CAVEAT,
        }

    def _compute_intent_readiness(
        self,
        *,
        intent: GovernanceAutopilotExecutionIntent,
        latest_approval: GovernanceAutopilotExecutionApproval | None,
    ) -> tuple[str, bool, dict[str, Any]]:
        if bool(intent.blocked) or intent.intent_status == "blocked":
            return "blocked", False, {
                "quorum_met": False,
                "rejection_threshold_met": False,
                "approval_vote_count": 0,
                "rejection_vote_count": 0,
            }

        decisions = self._extract_intent_decisions(intent.capability_decisions_json)
        approval_policy = self.resolved_autopilot_approval_policy(organization_id=intent.organization_id)
        requires_approval = self._approval_policy_requires_quorum(
            intent=intent,
            decisions=decisions,
            approval_policy=approval_policy,
        )
        if not requires_approval:
            if intent.intent_status == "planned":
                return "ready_for_runner", True, {
                    "quorum_met": True,
                    "rejection_threshold_met": False,
                    "approval_vote_count": 0,
                    "rejection_vote_count": 0,
                }
            return "not_ready", False, {
                "quorum_met": False,
                "rejection_threshold_met": False,
                "approval_vote_count": 0,
                "rejection_vote_count": 0,
            }

        if latest_approval is None:
            return "approval_required", False, {
                "quorum_met": False,
                "rejection_threshold_met": False,
                "approval_vote_count": 0,
                "rejection_vote_count": 0,
            }

        quorum = self._execution_approval_quorum_status(
            organization_id=intent.organization_id,
            approval_row=latest_approval,
            intent=intent,
        )
        extras = {
            "quorum_met": bool(quorum["quorum_met"]),
            "rejection_threshold_met": bool(quorum["rejection_threshold_met"]),
            "approval_vote_count": int(quorum["approval_vote_count"]),
            "rejection_vote_count": int(quorum["rejection_vote_count"]),
        }
        if latest_approval.approval_status == "cancelled":
            return "cancelled", False, extras
        if latest_approval.approval_status == "rejected" or bool(quorum["rejection_threshold_met"]):
            return "rejected", False, extras
        if latest_approval.approval_status == "approved" and bool(quorum["quorum_met"]) and not bool(quorum["rejection_threshold_met"]):
            return "ready_for_runner", True, extras
        return "approval_required", False, extras

    def execution_intent_approval_requirements(
        self,
        *,
        organization_id: uuid.UUID,
        intent_id: uuid.UUID,
    ) -> dict[str, Any]:
        intent = self.require_execution_intent(organization_id=organization_id, intent_id=intent_id)
        decisions = self._extract_intent_decisions(intent.capability_decisions_json)
        requirement_reasons: list[str] = []
        if intent.intent_status == "archived":
            requirement_reasons.append("intent_archived")
        if bool(intent.blocked) or intent.intent_status == "blocked":
            requirement_reasons.append("intent_blocked")
        approval_policy = self.resolved_autopilot_approval_policy(organization_id=organization_id)
        requires_approval = self._approval_policy_requires_quorum(
            intent=intent,
            decisions=decisions,
            approval_policy=approval_policy,
        )
        if requires_approval:
            requirement_reasons.append("intent_requires_approval")
        if any(bool(decision.get("approval_required")) for decision in decisions):
            requirement_reasons.append("capability_requires_approval")
        latest = self.latest_execution_approval_for_intent(organization_id=organization_id, intent_id=intent_id)
        readiness_state, ready_for_runner, readiness_extras = self._compute_intent_readiness(
            intent=intent,
            latest_approval=latest,
        )
        return {
            "intent_id": intent.id,
            "intent_status": intent.intent_status,
            "approval_required": requires_approval,
            "blocked": bool(intent.blocked),
            "approval_requirement_reasons": sorted(set(requirement_reasons)),
            "policy_snapshot": approval_policy,
            "capability_decisions": intent.capability_decisions_json,
            "readiness_state": readiness_state,
            "ready_for_runner": ready_for_runner,
            "quorum_met": bool(readiness_extras["quorum_met"]),
            "rejection_threshold_met": bool(readiness_extras["rejection_threshold_met"]),
            "approval_vote_count": int(readiness_extras["approval_vote_count"]),
            "rejection_vote_count": int(readiness_extras["rejection_vote_count"]),
            "caveat": AUTOPILOT_EXECUTION_APPROVAL_CAVEAT,
        }

    def latest_execution_approval_for_intent(
        self,
        *,
        organization_id: uuid.UUID,
        intent_id: uuid.UUID,
    ) -> GovernanceAutopilotExecutionApproval | None:
        return self.db.execute(
            select(GovernanceAutopilotExecutionApproval)
            .where(
                GovernanceAutopilotExecutionApproval.organization_id == organization_id,
                GovernanceAutopilotExecutionApproval.execution_intent_id == intent_id,
            )
            .order_by(
                GovernanceAutopilotExecutionApproval.requested_at.desc(),
                GovernanceAutopilotExecutionApproval.created_at.desc(),
                GovernanceAutopilotExecutionApproval.id.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()

    def request_execution_approval(
        self,
        *,
        organization_id: uuid.UUID,
        intent_id: uuid.UUID,
        approval_note: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotExecutionApproval:
        intent = self.require_execution_intent(organization_id=organization_id, intent_id=intent_id)
        if intent.intent_status == "archived" or intent.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived execution intent cannot request approval")
        if bool(intent.blocked) or intent.intent_status == "blocked":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Blocked execution intent cannot request approval")
        existing_requested = self.db.execute(
            select(GovernanceAutopilotExecutionApproval).where(
                GovernanceAutopilotExecutionApproval.organization_id == organization_id,
                GovernanceAutopilotExecutionApproval.execution_intent_id == intent_id,
                GovernanceAutopilotExecutionApproval.approval_status == "requested",
            )
        ).scalar_one_or_none()
        if existing_requested is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approval request already exists for execution intent")
        requirements = self.execution_intent_approval_requirements(
            organization_id=organization_id,
            intent_id=intent_id,
        )
        readiness = self.execution_intent_readiness(
            organization_id=organization_id,
            intent_id=intent_id,
        )
        row = GovernanceAutopilotExecutionApproval(
            organization_id=organization_id,
            execution_intent_id=intent_id,
            approval_status="requested",
            requested_by_user_id=actor_user_id,
            requested_at=self.now(),
            approval_note=approval_note,
            approval_policy_snapshot_json=self.to_json_compatible(
                self._autopilot_approval_policy_snapshot_for_intent(
                    organization_id=organization_id,
                    intent=intent,
                )
            ),
            approval_requirements_json=self.to_json_compatible(requirements),
            readiness_snapshot_json=self.to_json_compatible(readiness),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_execution_approvals_for_intent(
        self,
        *,
        organization_id: uuid.UUID,
        intent_id: uuid.UUID,
    ) -> list[GovernanceAutopilotExecutionApproval]:
        self.require_execution_intent(organization_id=organization_id, intent_id=intent_id)
        return list(
            self.db.execute(
                select(GovernanceAutopilotExecutionApproval)
                .where(
                    GovernanceAutopilotExecutionApproval.organization_id == organization_id,
                    GovernanceAutopilotExecutionApproval.execution_intent_id == intent_id,
                )
                .order_by(
                    GovernanceAutopilotExecutionApproval.requested_at.desc(),
                    GovernanceAutopilotExecutionApproval.id.desc(),
                )
            ).scalars().all()
        )

    def require_execution_approval(
        self,
        *,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
    ) -> GovernanceAutopilotExecutionApproval:
        row = self.db.execute(
            select(GovernanceAutopilotExecutionApproval).where(
                GovernanceAutopilotExecutionApproval.organization_id == organization_id,
                GovernanceAutopilotExecutionApproval.id == approval_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution approval not found")
        return row

    def _require_requested_approval(self, *, row: GovernanceAutopilotExecutionApproval) -> None:
        if row.approval_status != "requested":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approval is not in requested status")

    def approve_execution_approval(
        self,
        *,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
        decision_reason: str | None,
        approval_note: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotExecutionApproval:
        row = self.vote_approve_execution_approval(
            organization_id=organization_id,
            approval_id=approval_id,
            vote_reason=decision_reason,
            vote_note=approval_note,
            actor_user_id=actor_user_id,
            enforce_requester_self_block=False,
        )
        if approval_note is not None:
            row.approval_note = approval_note
        return row

    def reject_execution_approval(
        self,
        *,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
        decision_reason: str,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotExecutionApproval:
        return self.vote_reject_execution_approval(
            organization_id=organization_id,
            approval_id=approval_id,
            vote_reason=decision_reason,
            vote_note=None,
            actor_user_id=actor_user_id,
        )

    def cancel_execution_approval(
        self,
        *,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
        decision_reason: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotExecutionApproval:
        row = self.require_execution_approval(organization_id=organization_id, approval_id=approval_id)
        self._require_requested_approval(row=row)
        row.approval_status = "cancelled"
        row.decided_by_user_id = actor_user_id
        row.decided_at = self.now()
        row.cancelled_at = row.decided_at
        row.decision_reason = decision_reason
        row.readiness_snapshot_json = self.to_json_compatible(
            self.execution_intent_readiness(
                organization_id=organization_id,
                intent_id=row.execution_intent_id,
            )
        )
        return row

    def list_execution_approval_votes(
        self,
        *,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
    ) -> list[GovernanceAutopilotExecutionApprovalVote]:
        self.require_execution_approval(organization_id=organization_id, approval_id=approval_id)
        return self._list_execution_approval_votes(organization_id=organization_id, approval_id=approval_id)

    def execution_approval_vote_payload(self, row: GovernanceAutopilotExecutionApprovalVote) -> dict[str, Any]:
        return {
            "id": row.id,
            "vote_id": row.id,
            "approval_id": row.approval_id,
            "execution_intent_id": row.execution_intent_id,
            "organization_id": row.organization_id,
            "vote_status": row.vote_status,
            "voter_user_id": row.voter_user_id,
            "vote_reason": row.vote_reason,
            "vote_note": row.vote_note,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "caveat": AUTOPILOT_EXECUTION_QUORUM_CAVEAT,
        }

    def execution_approval_quorum_status(
        self,
        *,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
    ) -> dict[str, Any]:
        approval = self.require_execution_approval(organization_id=organization_id, approval_id=approval_id)
        intent = self.require_execution_intent(organization_id=organization_id, intent_id=approval.execution_intent_id)
        return self._execution_approval_quorum_status(
            organization_id=organization_id,
            approval_row=approval,
            intent=intent,
        )

    def _resolve_voter_user_id(
        self,
        *,
        approval_row: GovernanceAutopilotExecutionApproval,
        actor_user_id: uuid.UUID | None,
    ) -> uuid.UUID | None:
        return actor_user_id or approval_row.requested_by_user_id

    def vote_approve_execution_approval(
        self,
        *,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
        vote_reason: str | None,
        vote_note: str | None,
        actor_user_id: uuid.UUID | None,
        enforce_requester_self_block: bool = True,
    ) -> GovernanceAutopilotExecutionApproval:
        row = self.require_execution_approval(organization_id=organization_id, approval_id=approval_id)
        self._require_requested_approval(row=row)
        intent = self.require_execution_intent(organization_id=organization_id, intent_id=row.execution_intent_id)
        if intent.intent_status == "archived" or intent.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived execution intent cannot be approved")
        if bool(intent.blocked) or intent.intent_status == "blocked":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Blocked execution intent cannot be approved")

        approval_policy = self._approval_policy_from_approval_row(
            organization_id=organization_id,
            approval_row=row,
        )
        voter_user_id = self._resolve_voter_user_id(approval_row=row, actor_user_id=actor_user_id)
        if (
            enforce_requester_self_block
            and bool(approval_policy.get("block_requester_self_approval", True))
            and voter_user_id is not None
        ):
            if row.requested_by_user_id == voter_user_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requester cannot self-approve")

        existing_votes = self._list_execution_approval_votes(organization_id=organization_id, approval_id=row.id)
        if voter_user_id is None:
            if existing_votes:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Distinct voter identity is required")
        elif any(v.voter_user_id == voter_user_id for v in existing_votes):
            if bool(approval_policy.get("require_distinct_approvers", True)):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Distinct approver required")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Voter has already voted")

        vote = GovernanceAutopilotExecutionApprovalVote(
            organization_id=organization_id,
            approval_id=row.id,
            execution_intent_id=row.execution_intent_id,
            vote_status="approved",
            voter_user_id=voter_user_id,
            vote_reason=vote_reason,
            vote_note=vote_note,
        )
        self.db.add(vote)
        self.db.flush()

        quorum = self._execution_approval_quorum_status(
            organization_id=organization_id,
            approval_row=row,
            intent=intent,
        )
        row.decided_by_user_id = actor_user_id
        row.decided_at = self.now()
        row.decision_reason = vote_reason
        if vote_note is not None:
            row.approval_note = vote_note
        row.approval_status = "approved" if quorum["quorum_met"] and not quorum["rejection_threshold_met"] else "requested"
        row.readiness_snapshot_json = self.to_json_compatible(
            self.execution_intent_readiness(
                organization_id=organization_id,
                intent_id=row.execution_intent_id,
            )
        )
        return row

    def vote_reject_execution_approval(
        self,
        *,
        organization_id: uuid.UUID,
        approval_id: uuid.UUID,
        vote_reason: str,
        vote_note: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> GovernanceAutopilotExecutionApproval:
        if not vote_reason or not str(vote_reason).strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="vote_reason is required")
        row = self.require_execution_approval(organization_id=organization_id, approval_id=approval_id)
        self._require_requested_approval(row=row)
        voter_user_id = self._resolve_voter_user_id(approval_row=row, actor_user_id=actor_user_id)
        existing_votes = self._list_execution_approval_votes(organization_id=organization_id, approval_id=row.id)
        if voter_user_id is None:
            if existing_votes:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Distinct voter identity is required")
        elif any(v.voter_user_id == voter_user_id for v in existing_votes):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Voter has already voted")

        vote = GovernanceAutopilotExecutionApprovalVote(
            organization_id=organization_id,
            approval_id=row.id,
            execution_intent_id=row.execution_intent_id,
            vote_status="rejected",
            voter_user_id=voter_user_id,
            vote_reason=str(vote_reason).strip(),
            vote_note=vote_note,
        )
        self.db.add(vote)
        self.db.flush()
        quorum = self._execution_approval_quorum_status(
            organization_id=organization_id,
            approval_row=row,
        )
        row.decided_by_user_id = actor_user_id
        row.decided_at = self.now()
        row.decision_reason = str(vote_reason).strip()
        if vote_note is not None:
            row.approval_note = vote_note
        row.approval_status = "rejected" if quorum["rejection_threshold_met"] else "requested"
        row.readiness_snapshot_json = self.to_json_compatible(
            self.execution_intent_readiness(
                organization_id=organization_id,
                intent_id=row.execution_intent_id,
            )
        )
        return row

    def list_execution_approvals(
        self,
        *,
        organization_id: uuid.UUID,
        approval_status: str | None,
        execution_intent_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[GovernanceAutopilotExecutionApproval]:
        if approval_status is not None:
            approval_status = validate_choice(approval_status, AUTOPILOT_EXECUTION_APPROVAL_STATUS_VALUES, "approval_status", status_code=status.HTTP_400_BAD_REQUEST)
        if execution_intent_id is not None:
            self.require_execution_intent(organization_id=organization_id, intent_id=execution_intent_id)
        query = select(GovernanceAutopilotExecutionApproval).where(
            GovernanceAutopilotExecutionApproval.organization_id == organization_id
        )
        if approval_status is not None:
            query = query.where(GovernanceAutopilotExecutionApproval.approval_status == approval_status)
        if execution_intent_id is not None:
            query = query.where(GovernanceAutopilotExecutionApproval.execution_intent_id == execution_intent_id)
        query = query.order_by(
            GovernanceAutopilotExecutionApproval.requested_at.desc(),
            GovernanceAutopilotExecutionApproval.id.desc(),
        ).offset(offset).limit(limit)
        return list(self.db.execute(query).scalars().all())

    def execution_intent_readiness(
        self,
        *,
        organization_id: uuid.UUID,
        intent_id: uuid.UUID,
    ) -> dict[str, Any]:
        intent = self.require_execution_intent(organization_id=organization_id, intent_id=intent_id)
        latest = self.latest_execution_approval_for_intent(organization_id=organization_id, intent_id=intent_id)
        readiness_state, ready_for_runner, extras = self._compute_intent_readiness(
            intent=intent,
            latest_approval=latest,
        )
        decisions = self._extract_intent_decisions(intent.capability_decisions_json)
        approval_policy = self.resolved_autopilot_approval_policy(organization_id=organization_id)
        requires_approval = self._approval_policy_requires_quorum(
            intent=intent,
            decisions=decisions,
            approval_policy=approval_policy,
        )
        capability_summary = {
            "total_decisions": len(decisions),
            "blocked_decisions": int(sum(1 for item in decisions if bool(item.get("blocked")))),
            "approval_required_decisions": int(sum(1 for item in decisions if bool(item.get("approval_required")))),
        }
        return {
            "intent_id": intent.id,
            "intent_status": intent.intent_status,
            "latest_approval_id": latest.id if latest else None,
            "latest_approval_status": latest.approval_status if latest else None,
            "readiness_state": readiness_state,
            "ready_for_runner": ready_for_runner,
            "blocked_reasons": list(intent.blocked_reasons_json or []),
            "approval_required": requires_approval,
            "quorum_met": bool(extras["quorum_met"]),
            "rejection_threshold_met": bool(extras["rejection_threshold_met"]),
            "approval_vote_count": int(extras["approval_vote_count"]),
            "rejection_vote_count": int(extras["rejection_vote_count"]),
            "capability_summary": capability_summary,
            "caveat": AUTOPILOT_EXECUTION_APPROVAL_CAVEAT,
        }

    def execution_approval_payload(self, row: GovernanceAutopilotExecutionApproval) -> dict[str, Any]:
        intent = self.require_execution_intent(
            organization_id=row.organization_id,
            intent_id=row.execution_intent_id,
        )
        readiness_state, ready_for_runner, extras = self._compute_intent_readiness(
            intent=intent,
            latest_approval=row,
        )
        return {
            "id": row.id,
            "approval_id": row.id,
            "organization_id": row.organization_id,
            "execution_intent_id": row.execution_intent_id,
            "approval_status": row.approval_status,
            "requested_by_user_id": row.requested_by_user_id,
            "requested_at": row.requested_at,
            "decided_by_user_id": row.decided_by_user_id,
            "decided_at": row.decided_at,
            "decision_reason": row.decision_reason,
            "approval_note": row.approval_note,
            "approval_policy_snapshot_json": row.approval_policy_snapshot_json,
            "approval_requirements_json": row.approval_requirements_json,
            "readiness_snapshot_json": row.readiness_snapshot_json,
            "cancelled_at": row.cancelled_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "approval_vote_count": int(extras["approval_vote_count"]),
            "rejection_vote_count": int(extras["rejection_vote_count"]),
            "quorum_met": bool(extras["quorum_met"]),
            "rejection_threshold_met": bool(extras["rejection_threshold_met"]),
            "readiness_state": readiness_state,
            "ready_for_runner": ready_for_runner,
            "caveat": AUTOPILOT_EXECUTION_APPROVAL_CAVEAT,
        }

    def execution_approval_summary(self, *, organization_id: uuid.UUID) -> dict[str, Any]:
        rows_status = list(
            self.db.execute(
                select(
                    GovernanceAutopilotExecutionApproval.approval_status,
                    func.count(GovernanceAutopilotExecutionApproval.id),
                )
                .where(GovernanceAutopilotExecutionApproval.organization_id == organization_id)
                .group_by(GovernanceAutopilotExecutionApproval.approval_status)
            ).all()
        )
        by_status = {str(k): int(v) for k, v in rows_status}
        approvals = list(
            self.db.execute(
                select(GovernanceAutopilotExecutionApproval)
                .where(GovernanceAutopilotExecutionApproval.organization_id == organization_id)
            ).scalars().all()
        )
        ready_for_runner_count = 0
        approval_required_count = 0
        blocked_count = 0
        for row in approvals:
            intent = self.require_execution_intent(organization_id=organization_id, intent_id=row.execution_intent_id)
            readiness_state, ready_for_runner, _ = self._compute_intent_readiness(
                intent=intent,
                latest_approval=row,
            )
            if ready_for_runner:
                ready_for_runner_count += 1
            if readiness_state == "approval_required":
                approval_required_count += 1
            if readiness_state == "blocked":
                blocked_count += 1
        latest_approval_at = self.db.execute(
            select(func.max(GovernanceAutopilotExecutionApproval.created_at)).where(
                GovernanceAutopilotExecutionApproval.organization_id == organization_id
            )
        ).scalar_one()
        return {
            "total_approvals": int(sum(by_status.values())),
            "by_status": by_status,
            "ready_for_runner_count": ready_for_runner_count,
            "approval_required_count": approval_required_count,
            "blocked_count": blocked_count,
            "latest_approval_at": latest_approval_at,
            "caveat": AUTOPILOT_EXECUTION_APPROVAL_CAVEAT,
        }
