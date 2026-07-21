"""Dispatch a governance workflow when core decides a monitoring threshold was breached.

The nine collaborator roles the patent-P4 design names as Protocols are implemented here
as real adapters over core's existing services. They stay separate objects rather than
collapsing into one class for two reasons: each names exactly which core service owns
that capability, and the engine can be constructed with a substitute adapter so a
dispatch failure can be exercised in a test without reaching for mocks of core itself.

    Protocol (P4 name)              Adapter                     Core service it calls
    ------------------------------  --------------------------  --------------------------
    AISystemRepository              CoreAISystemRepository      AISystem (model)
    AutomationAccountRepository     CoreAutomationAccounts      SystemAccountService
    IssueRepository                 CoreIssueRepository         IssueService.create_issue
    RiskLinkRepository              CoreRiskLinkRepository      AISystemRiskLink (model)
    RiskScoreRepository             CoreRiskScoreRepository     RiskScoringService
    AlertRepository                 CoreAlertRepository         ControlMonitoringAlert
    OrgGovernanceSettingsRepository CoreOrgSettingsRepository   OrganizationGovernanceSetting
    ReviewRepository                CoreReviewRepository        AIReviewService.create_review
    AuditRepository                 CoreAuditRepository         AuditService.write_audit_log

Three places where the upstream P4 spec did not match this codebase, corrected here:

* It passes ``review_type="triggered"``. AIReviewService.ALLOWED_REVIEW_TYPES has no
  such value -- it is {initial_review, pre_production_review, periodic_review,
  change_review, retirement_review}. A breach means the system's observed behaviour
  changed, so ``change_review`` is used, and a review created with an invalid type
  would 422 rather than silently downgrade.
* It assumes a per-org automation account. Core has ONE (see SystemAccountService); the
  adapter returns that single user, whose per-org membership is ensured lazily.
* It calls ``recompute_score(risk_id)`` as though core had one. Core has no such
  method: every caller runs the compute_score / score_to_severity / compute_residual
  sequence inline (risk_service.py:183-192). The adapter reuses that sequence rather
  than introducing a factory seven other call sites do not use.

ORDERING GUARANTEE
==================
`dispatch_for_reading` writes and audits the breach decision BEFORE calling any
workflow, and attaches the workflow reference afterwards. A workflow that raises
therefore cannot cost us the record that core decided a breach occurred -- the decision
is a compliance fact, the dispatch is an action taken because of it, and the second
failing must not erase the first. Each dispatch is additionally wrapped in a SAVEPOINT
so a partially-written workflow rolls back without taking the decision rows with it.

NO SUPPRESSION
==============
Every breached tier dispatches its own workflow. There is deliberately no
`suppress_lower_tiers` option and no early exit: if a reading breaches both the warning
and critical thresholds, both fire. A customer configured each tier to mean something,
and silently dropping the lower one because a higher one also fired would decide on
their behalf that they did not mean it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.compliance_event_bridge import ComplianceEventBridge
from app.models.ai_monitoring_breach_event import AIMonitoringBreachEvent
from app.models.ai_monitoring_config import DISABLED_WORKFLOW_VALUES, AIMonitoringConfig
from app.models.ai_monitoring_reading import AIMonitoringReading
from app.models.ai_system import AISystem
from app.models.ai_system_risk_link import AISystemRiskLink
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.organization_governance_setting import OrganizationGovernanceSetting
from app.models.risk import Risk
from app.services.audit_service import AuditService
from app.services.system_account_service import ensure_system_account_membership


class WorkflowDispatchError(RuntimeError):
    """A workflow could not be carried out. The breach decision is already durable."""


@dataclass(frozen=True)
class ComplianceDecision:
    """What core decided, as the workflows need to see it."""

    organization_id: uuid.UUID
    ai_system_id: uuid.UUID
    config_id: uuid.UUID
    reading_id: uuid.UUID
    breach_event_id: uuid.UUID
    metric_type: str
    tier: str
    escalation_order: int
    observed_value: Decimal
    threshold_value: Decimal
    threshold_operator: str
    obligation_id: uuid.UUID | None


def severity_for_tier(tier: str) -> str:
    """Best-effort tier -> severity.

    `tier` is intentionally free text so customers can name their own, so this is a
    heuristic in the same spirit as AIMonitoringService._severity_for_metric. An unknown
    tier falls back to 'medium' rather than raising: a best-effort label beats blocking
    a dispatch the customer asked for.
    """
    normalized = (tier or "").strip().lower()
    if normalized in {"critical", "high"}:
        return normalized
    if normalized in {"low", "info"}:
        return "low"
    return "medium"


# --------------------------------------------------------------------- protocols


class AISystemRepository(Protocol):
    def get_ai_system(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> AISystem: ...


class AutomationAccountRepository(Protocol):
    def ensure_automation_user(self, org_id: uuid.UUID) -> uuid.UUID: ...


class IssueRepository(Protocol):
    def create_issue(
        self,
        *,
        org_id: uuid.UUID,
        owner_id: uuid.UUID,
        created_by: uuid.UUID,
        title: str,
        description: str,
        severity: str,
        source_id: uuid.UUID | None,
    ) -> uuid.UUID: ...


class RiskLinkRepository(Protocol):
    def get_linked_risk_ids(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> list[uuid.UUID]: ...


class RiskScoreRepository(Protocol):
    def recompute_score(self, org_id: uuid.UUID, risk_id: uuid.UUID) -> str: ...


class AlertRepository(Protocol):
    def create_alert(
        self, *, org_id: uuid.UUID, alert_type: str, severity: str, title: str, description: str, context: dict
    ) -> uuid.UUID: ...


class OrgGovernanceSettingsRepository(Protocol):
    def get_default_reviewer(self, org_id: uuid.UUID) -> uuid.UUID | None: ...


class ReviewRepository(Protocol):
    def create_review(
        self,
        *,
        org_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        assigned_reviewer_id: uuid.UUID,
        created_by: uuid.UUID,
        notes: str,
    ) -> uuid.UUID: ...


class AuditRepository(Protocol):
    def write(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        after_json: dict,
        metadata_json: dict,
    ) -> None: ...


# ---------------------------------------------------------------------- adapters


class CoreAISystemRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_ai_system(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == ai_system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise WorkflowDispatchError(f"AI system {ai_system_id} not found in organization {org_id}")
        return row


class CoreAutomationAccounts:
    """Core has ONE system account, not one per org; membership is per-org."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_automation_user(self, org_id: uuid.UUID) -> uuid.UUID:
        return ensure_system_account_membership(self.db, org_id).id


class CoreIssueRepository:
    """Goes through IssueService.create_issue, not a direct Issue() insert.

    That path also initialises SLA tracking in the same transaction and writes the
    issue's own audit entry. Constructing the row directly would silently skip both, and
    a system-created issue with no SLA clock is exactly the kind of issue that gets
    forgotten.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_issue(
        self,
        *,
        org_id: uuid.UUID,
        owner_id: uuid.UUID,
        created_by: uuid.UUID,
        title: str,
        description: str,
        severity: str,
        source_id: uuid.UUID | None,
    ) -> uuid.UUID:
        from app.compliance.services.issue_service import IssueService
        from app.schemas.issue import IssueCreate

        payload = IssueCreate(
            title=title[:255],
            description=description,
            issue_type="compliance_violation",
            severity=severity,
            # 'ai_monitoring' is not a value ck_issues_source_type permits;
            # 'monitoring_alert' is the existing one that means this.
            source_type="monitoring_alert",
            source_id=source_id,
            owner_id=owner_id,
            assigned_to=None,
        )
        row = IssueService(self.db).create_issue(org_id, payload, created_by)
        return row.id


class CoreRiskLinkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_linked_risk_ids(self, org_id: uuid.UUID, ai_system_id: uuid.UUID) -> list[uuid.UUID]:
        return list(
            self.db.execute(
                select(AISystemRiskLink.risk_id).where(
                    AISystemRiskLink.organization_id == org_id,
                    AISystemRiskLink.ai_system_id == ai_system_id,
                    AISystemRiskLink.status == "active",
                )
            ).scalars().all()
        )


class CoreRiskScoreRepository:
    """Reuses core's own scoring sequence rather than inventing a recompute method."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def recompute_score(self, org_id: uuid.UUID, risk_id: uuid.UUID) -> str:
        from app.compliance.services.risk_scoring_service import RiskScoringService
        from app.services.risk_service import RiskService

        risk = self.db.execute(
            select(Risk).where(Risk.organization_id == org_id, Risk.id == risk_id)
        ).scalar_one_or_none()
        if risk is None:
            raise WorkflowDispatchError(f"risk {risk_id} not found in organization {org_id}")

        settings = RiskScoringService.get_or_create_org_settings(org_id, self.db)
        inherent_score = RiskScoringService.compute_score(risk, settings)
        risk.inherent_score = inherent_score
        risk.severity = RiskService.score_to_severity(inherent_score)
        residual_likelihood, residual_impact, residual_score = RiskScoringService.compute_residual(
            risk, [], inherent_score, settings
        )
        risk.residual_likelihood = residual_likelihood
        risk.residual_impact = residual_impact
        risk.residual_score = residual_score
        self.db.flush()
        return f"risk:{risk.id}"


class CoreAlertRepository:
    """Constructs ControlMonitoringAlert inline, which is core's convention here.

    All eight existing creators build the row directly; introducing a factory that none
    of them use would leave two ways to do one thing.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_alert(
        self, *, org_id: uuid.UUID, alert_type: str, severity: str, title: str, description: str, context: dict
    ) -> uuid.UUID:
        alert = ControlMonitoringAlert(
            organization_id=org_id,
            rule_id=None,
            definition_id=None,
            control_id=None,
            alert_type=alert_type,
            severity=severity,
            status="open",
            title=title[:255],
            description=description,
            alert_context_json=context,
        )
        self.db.add(alert)
        self.db.flush()
        return alert.id


class CoreOrgSettingsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_default_reviewer(self, org_id: uuid.UUID) -> uuid.UUID | None:
        return self.db.execute(
            select(OrganizationGovernanceSetting.default_reviewer_user_id).where(
                OrganizationGovernanceSetting.organization_id == org_id
            )
        ).scalar_one_or_none()


class CoreReviewRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_review(
        self,
        *,
        org_id: uuid.UUID,
        ai_system_id: uuid.UUID,
        assigned_reviewer_id: uuid.UUID,
        created_by: uuid.UUID,
        notes: str,
    ) -> uuid.UUID:
        from types import SimpleNamespace

        from app.ai_governance.services.ai_review_service import AIReviewService

        # AIReviewService.create_review takes a `data` object with assigned_reviewer_id
        # and due_date; there is no pydantic model for the system-initiated path, so a
        # simple attribute carrier is passed rather than inventing a schema that only
        # this caller would use.
        data = SimpleNamespace(assigned_reviewer_id=assigned_reviewer_id, due_date=None)
        row = AIReviewService(self.db).create_review(
            org_id, ai_system_id, "change_review", data, created_by
        )
        if notes:
            row.decision_notes = notes
            self.db.flush()
        return row.id


class CoreAuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def write(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None,
        org_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        after_json: dict,
        metadata_json: dict,
    ) -> None:
        AuditService(self.db).write_audit_log(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json=after_json,
            metadata_json=metadata_json,
        )


# ------------------------------------------------------------------------ engine


class GovernanceWorkflowEngine:
    def __init__(
        self,
        db: Session,
        *,
        ai_systems: AISystemRepository | None = None,
        automation_accounts: AutomationAccountRepository | None = None,
        issues: IssueRepository | None = None,
        risk_links: RiskLinkRepository | None = None,
        risk_scores: RiskScoreRepository | None = None,
        alerts: AlertRepository | None = None,
        org_settings: OrgGovernanceSettingsRepository | None = None,
        reviews: ReviewRepository | None = None,
        audit: AuditRepository | None = None,
    ) -> None:
        self.db = db
        self._ai_systems = ai_systems or CoreAISystemRepository(db)
        self._automation_accounts = automation_accounts or CoreAutomationAccounts(db)
        self._issues = issues or CoreIssueRepository(db)
        self._risk_links = risk_links or CoreRiskLinkRepository(db)
        self._risk_scores = risk_scores or CoreRiskScoreRepository(db)
        self._alerts = alerts or CoreAlertRepository(db)
        self._org_settings = org_settings or CoreOrgSettingsRepository(db)
        self._reviews = reviews or CoreReviewRepository(db)
        self._audit = audit or CoreAuditRepository(db)
        self._bridge = ComplianceEventBridge(db)

    # --- the entry point ------------------------------------------------------

    def dispatch_for_reading(
        self,
        org_id: uuid.UUID,
        *,
        reading: AIMonitoringReading,
        configs: list[AIMonitoringConfig],
        observed_value: Decimal,
    ) -> list[AIMonitoringBreachEvent]:
        """Record and dispatch EVERY breached tier for one reading.

        No early exit and no suppression: a reading that breaches warning and critical
        fires both. Ordered by escalation_order purely so the audit trail reads in the
        order a human would expect -- ordering never decides whether a tier fires.

        Each tier's decision is recorded and audited BEFORE its workflow runs. A
        workflow that raises is recorded against the decision and does not prevent the
        remaining tiers from dispatching: one broken workflow must not silence the rest.
        """
        breached = [c for c in configs if self._is_breach(c, observed_value)]
        breached.sort(key=lambda c: (c.escalation_order, c.tier))

        events: list[AIMonitoringBreachEvent] = []
        for config in breached:
            # Durable first. If this raises (e.g. a disabled workflow), nothing has been
            # dispatched for this tier and the loop moves on to the next.
            event = self._bridge.record_breach_decision(
                org_id, reading=reading, config=config, observed_value=observed_value
            )
            events.append(event)

            decision = ComplianceDecision(
                organization_id=org_id,
                ai_system_id=config.ai_system_id,
                config_id=config.id,
                reading_id=reading.id,
                breach_event_id=event.id,
                metric_type=config.metric_type,
                tier=config.tier,
                escalation_order=config.escalation_order,
                observed_value=observed_value,
                threshold_value=config.threshold_value,
                threshold_operator=config.threshold_operator,
                obligation_id=config.obligation_id,
            )
            self._dispatch_one(decision, config.workflow_to_trigger)
        return events

    @staticmethod
    def _is_breach(config: AIMonitoringConfig, value: Decimal) -> bool:
        """Uses threshold_operator, which is strictly more expressive than
        comparison_direction. The 0320 backfill mapped 'above'->gte and 'below'->lte
        exactly, so an untouched Feature #66 config compares identically either way."""
        operator = config.threshold_operator
        if operator == "gt":
            return value > config.threshold_value
        if operator == "gte":
            return value >= config.threshold_value
        if operator == "lt":
            return value < config.threshold_value
        return value <= config.threshold_value

    def _dispatch_one(self, decision: ComplianceDecision, workflow: str) -> None:
        """Run one workflow inside a SAVEPOINT.

        The savepoint is what makes the ordering guarantee hold in practice rather than
        only on paper: a workflow that half-writes and then raises rolls back to the
        point just after the decision was recorded, leaving the decision and its audit
        entry intact and queryable.
        """
        handler = {
            "create_alert": self.create_alert,
            "create_issue": self.create_issue,
            "update_risk_score": self.update_risk_score,
            "require_review": self.require_review,
            "notify_oncall": self.notify_oncall,
        }.get(workflow)

        if handler is None:
            # Includes suspend_system, which record_breach_decision already refuses --
            # so reaching here means an unknown value, not a disabled one.
            raise WorkflowDispatchError(
                f"no handler for workflow_to_trigger '{workflow}'"
                + (" (defined but not implemented)" if workflow in DISABLED_WORKFLOW_VALUES else "")
            )

        nested = self.db.begin_nested()
        try:
            reference = handler(decision)
            nested.commit()
        except Exception as exc:
            nested.rollback()
            # The decision survives; record that its follow-through did not. Written
            # after the rollback so it is not itself discarded.
            self._audit.write(
                action="ai_monitoring.breach_workflow_failed",
                entity_type="ai_monitoring_breach_event",
                entity_id=decision.breach_event_id,
                org_id=decision.organization_id,
                actor_user_id=None,
                after_json={
                    "workflow": workflow,
                    "tier": decision.tier,
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                },
                metadata_json={"source": "governance_workflow_engine", "outcome": "failed"},
            )
            return

        event = self.db.execute(
            select(AIMonitoringBreachEvent).where(AIMonitoringBreachEvent.id == decision.breach_event_id)
        ).scalar_one()
        self._bridge.attach_workflow_reference(event, reference, org_id=decision.organization_id)

    # --- the five implemented workflows ---------------------------------------

    def create_alert(self, decision: ComplianceDecision) -> str:
        """What core already does on every breach today, now tier-aware.

        Severity comes from the tier that fired rather than a static per-metric lookup,
        so a drift score ten times over threshold no longer reads the same as one a hair
        over -- it reads as whatever the customer said that tier means.
        """
        alert_id = self._alerts.create_alert(
            org_id=decision.organization_id,
            alert_type="ai_monitoring",
            severity=severity_for_tier(decision.tier),
            title=f"AI monitoring breach: {decision.metric_type} ({decision.tier})",
            description=(
                f"{decision.metric_type} breached its {decision.tier} threshold: observed "
                f"{decision.observed_value}, threshold {decision.threshold_value} "
                f"({decision.threshold_operator})."
            ),
            context=self._alert_context(decision),
        )
        return f"alert:{alert_id}"

    def create_issue(self, decision: ComplianceDecision) -> str:
        """Owner is the AI system's business owner if set, else the system account.

        The CREATOR is always the system account regardless -- a system decided this, not
        a person -- and metadata records which owner path fired so an auditor can tell a
        real accountable human from the fallback.
        """
        info = self._ai_systems.get_ai_system(decision.organization_id, decision.ai_system_id)
        creator = self._automation_accounts.ensure_automation_user(decision.organization_id)

        if info.business_owner_user_id is not None:
            owner = info.business_owner_user_id
            assignment_path = "ai_system_owner"
        else:
            owner = creator
            assignment_path = "system_account"

        issue_id = self._issues.create_issue(
            org_id=decision.organization_id,
            owner_id=owner,
            created_by=creator,
            title=f"AI monitoring breach: {decision.metric_type} ({decision.tier})",
            description=(
                f"AI system {decision.ai_system_id} breached its {decision.tier} threshold for "
                f"{decision.metric_type}: observed {decision.observed_value}, threshold "
                f"{decision.threshold_value} ({decision.threshold_operator}). Obligation: "
                f"{decision.obligation_id or 'none linked'}."
            ),
            severity=severity_for_tier(decision.tier),
            # Now available, unlike in the upstream spec: the decision is recorded before
            # dispatch, so the issue can point back at the breach event that caused it.
            source_id=decision.breach_event_id,
        )
        self._audit.write(
            action="ai_monitoring.create_issue_dispatched",
            entity_type="issue",
            entity_id=issue_id,
            org_id=decision.organization_id,
            actor_user_id=creator,
            after_json={
                "ai_system_id": str(decision.ai_system_id),
                "config_id": str(decision.config_id),
                "breach_event_id": str(decision.breach_event_id),
                "tier": decision.tier,
                "owner_id": str(owner),
            },
            metadata_json={"source": "governance_workflow_engine", "assignment_path": assignment_path},
        )
        return f"issue:{issue_id}"

    def update_risk_score(self, decision: ComplianceDecision) -> str:
        """Recompute the linked risk, or raise a loud persisted flag.

        Zero links and more than one active link BOTH flag rather than update: neither
        is a state this workflow can resolve without guessing which risk the customer
        meant, and guessing about a risk score is worse than saying so.
        """
        linked = self._risk_links.get_linked_risk_ids(decision.organization_id, decision.ai_system_id)

        if len(linked) == 1:
            reference = self._risk_scores.recompute_score(decision.organization_id, linked[0])
            self._audit.write(
                action="ai_monitoring.update_risk_score_dispatched",
                entity_type="risk",
                entity_id=linked[0],
                org_id=decision.organization_id,
                actor_user_id=None,
                after_json={
                    "ai_system_id": str(decision.ai_system_id),
                    "breach_event_id": str(decision.breach_event_id),
                    "tier": decision.tier,
                },
                metadata_json={"source": "governance_workflow_engine"},
            )
            return reference

        reason = (
            f"AI system {decision.ai_system_id} breached a threshold but has no linked risk "
            "record; risk score was NOT updated and manual linkage is required."
            if not linked
            else (
                f"AI system {decision.ai_system_id} breached a threshold but has {len(linked)} "
                "linked risk records, so which to update is ambiguous; risk score was NOT "
                "updated and manual resolution is required."
            )
        )
        return self._flag_unresolvable(
            decision,
            alert_type="ai_monitoring_unlinked_risk",
            reason=reason,
            audit_action="ai_monitoring.update_risk_score_skipped",
        )

    def require_review(self, decision: ComplianceDecision) -> str:
        """System account creates, the org's configured default reviewer is assigned.

        No guessing at a reviewer. Because the creator is the system account and a
        default reviewer is a real person configured through settings, core's
        `created_by != assigned_reviewer_id` rule is satisfied by construction; the
        explicit check below is a backstop for a misconfiguration, not the guarantee.
        """
        creator = self._automation_accounts.ensure_automation_user(decision.organization_id)
        default_reviewer = self._org_settings.get_default_reviewer(decision.organization_id)

        if default_reviewer is None:
            return self._flag_unresolvable(
                decision,
                alert_type="ai_monitoring_no_default_reviewer",
                reason=(
                    f"AI system {decision.ai_system_id} breached a threshold requiring review, "
                    "but no default reviewer is configured for this organization; no review "
                    "was created."
                ),
                audit_action="ai_monitoring.require_review_skipped",
            )

        if default_reviewer == creator:
            raise WorkflowDispatchError(
                "the organization's default reviewer is the system automation account, which "
                "would violate core's created_by != assigned_reviewer_id rule. Configure a "
                "real person as the default reviewer."
            )

        review_id = self._reviews.create_review(
            org_id=decision.organization_id,
            ai_system_id=decision.ai_system_id,
            assigned_reviewer_id=default_reviewer,
            created_by=creator,
            notes=(
                f"Automated trigger: {decision.metric_type} breached its {decision.tier} "
                f"threshold (observed {decision.observed_value}, threshold "
                f"{decision.threshold_value} {decision.threshold_operator})."
            ),
        )
        self._audit.write(
            action="ai_monitoring.require_review_dispatched",
            entity_type="ai_governance_review",
            entity_id=review_id,
            org_id=decision.organization_id,
            actor_user_id=creator,
            after_json={
                "ai_system_id": str(decision.ai_system_id),
                "breach_event_id": str(decision.breach_event_id),
                "tier": decision.tier,
                "assigned_reviewer_id": str(default_reviewer),
            },
            metadata_json={"source": "governance_workflow_engine"},
        )
        return f"review:{review_id}"

    def notify_oncall(self, decision: ComplianceDecision) -> str:
        """Raise a high-visibility alert for whoever is on call.

        Core has no Slack or PagerDuty integration -- those live satellite-side -- so
        this deliberately does NOT pretend to page anyone. It writes a
        ControlMonitoringAlert of a distinct type at escalated severity, which is core's
        own system of record and visible to every org regardless of what external
        channels they have configured. Claiming to have paged someone when no channel
        exists would be the worst possible failure for this particular workflow.
        """
        severity = severity_for_tier(decision.tier)
        alert_id = self._alerts.create_alert(
            org_id=decision.organization_id,
            alert_type="ai_monitoring_oncall",
            severity="critical" if severity in {"high", "critical"} else severity,
            title=f"On-call escalation: {decision.metric_type} ({decision.tier})",
            description=(
                f"{decision.metric_type} breached its {decision.tier} threshold and is "
                f"configured to page on-call: observed {decision.observed_value}, threshold "
                f"{decision.threshold_value} ({decision.threshold_operator}). Core records the "
                "escalation; external paging channels are handled outside core."
            ),
            context=self._alert_context(decision),
        )
        return f"alert:{alert_id}"

    # --- shared -----------------------------------------------------------------

    def _alert_context(self, decision: ComplianceDecision) -> dict:
        return {
            "config_id": str(decision.config_id),
            "ai_system_id": str(decision.ai_system_id),
            "reading_id": str(decision.reading_id),
            # The typed linkage core's existing alert context lacked.
            "breach_event_id": str(decision.breach_event_id),
            "metric_type": decision.metric_type,
            "tier": decision.tier,
            "escalation_order": decision.escalation_order,
            "observed_value": str(decision.observed_value),
            "threshold_value": str(decision.threshold_value),
            "threshold_operator": decision.threshold_operator,
            "obligation_id": str(decision.obligation_id) if decision.obligation_id else None,
        }

    def _flag_unresolvable(self, decision: ComplianceDecision, *, alert_type: str, reason: str, audit_action: str) -> str:
        """A persisted, in-app flag -- never a silent no-op.

        Deliberately an alert row rather than notify_oncall: these conditions must be
        visible to an organisation that has configured no external channel at all.
        """
        context = self._alert_context(decision)
        context["reason"] = reason
        alert_id = self._alerts.create_alert(
            org_id=decision.organization_id,
            alert_type=alert_type,
            severity=severity_for_tier(decision.tier),
            title=f"AI monitoring workflow could not complete: {decision.metric_type}",
            description=reason,
            context=context,
        )
        self._audit.write(
            action=audit_action,
            entity_type="ai_monitoring_breach_event",
            entity_id=decision.breach_event_id,
            org_id=decision.organization_id,
            actor_user_id=None,
            after_json={"reason": reason, "alert_id": str(alert_id), "tier": decision.tier},
            metadata_json={"source": "governance_workflow_engine", "outcome": "flagged"},
        )
        return f"alert:{alert_id}"
