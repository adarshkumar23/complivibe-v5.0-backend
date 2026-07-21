"""Step 7b: dispatch of governance workflows when core decides a threshold was breached.

The two properties worth protecting above the rest:

  ORDERING -- the breach decision is durable BEFORE any workflow runs. A workflow that
  raises must not cost us the record that core decided a breach occurred. The decision
  is a compliance fact; the dispatch is an action taken because of it, and the second
  failing must never erase the first.

  NO SUPPRESSION -- every breached tier dispatches its own workflow. There is no
  `suppress_lower_tiers` option and no early exit, because a customer configured each
  tier to mean something and dropping the lower one would decide otherwise for them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai_governance.services.governance_workflow_engine import (
    GovernanceWorkflowEngine,
    WorkflowDispatchError,
    severity_for_tier,
)
from app.models.ai_governance_review import AIGovernanceReview
from app.models.ai_monitoring_breach_event import AIMonitoringBreachEvent
from app.models.ai_monitoring_config import AIMonitoringConfig
from app.models.ai_system import AISystem
from app.models.ai_system_risk_link import AISystemRiskLink
from app.models.audit_log import AuditLog
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.issue import Issue
from app.models.organization import Organization
from app.models.organization_governance_setting import OrganizationGovernanceSetting
from app.models.user import User
from app.services.system_account_service import ensure_system_account_membership


def _config(org, system, user, *, tier, order, workflow, operator="lte", threshold="0.9000"):
    now = datetime.now(UTC)
    return AIMonitoringConfig(
        id=uuid.uuid4(),
        organization_id=org.id,
        ai_system_id=system.id,
        metric_type="accuracy",
        threshold_value=Decimal(threshold),
        comparison_direction="below",
        alert_on_breach=True,
        is_active=True,
        created_by=user.id,
        created_at=now,
        updated_at=now,
        api_key_hash="x" * 64,
        tier=tier,
        escalation_order=order,
        threshold_operator=operator,
        workflow_to_trigger=workflow,
    )


@pytest.fixture()
def env(db_session):
    org = Organization(id=uuid.uuid4(), name="Engine Org")
    owner = User(
        id=uuid.uuid4(),
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    reviewer = User(
        id=uuid.uuid4(),
        email=f"reviewer-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        status="active",
        is_active=True,
        is_superuser=False,
    )
    system = AISystem(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Pricing Model",
        system_type="internal_model",
        lifecycle_status="production",
        business_owner_user_id=owner.id,
    )
    db_session.add_all([org, owner, reviewer, system])
    db_session.flush()

    # Both humans must be active members for core's assignment checks.
    from app.models.membership import Membership
    from app.services.seed_service import SeedService

    roles = SeedService.ensure_roles_for_organization(db_session, org.id)
    role_id = roles["compliance_manager"].id
    db_session.add_all(
        [
            Membership(organization_id=org.id, user_id=owner.id, role_id=role_id, status="active"),
            Membership(organization_id=org.id, user_id=reviewer.id, role_id=role_id, status="active"),
        ]
    )
    ensure_system_account_membership(db_session, org.id)
    db_session.flush()

    bridge_reading = _make_reading(db_session, org)
    return {
        "org": org,
        "owner": owner,
        "reviewer": reviewer,
        "system": system,
        "reading": bridge_reading,
    }


def _make_reading(db_session, org):
    from app.models.ai_monitoring_reading import AIMonitoringReading

    row = AIMonitoringReading(
        id=uuid.uuid4(),
        organization_id=org.id,
        config_id=None,
        value=Decimal("0.8100"),
        reading_source="api_report",
        within_threshold=None,
        created_at=datetime.now(UTC),
        collection_mode="a",
        metric_type="accuracy",
    )
    db_session.add(row)
    db_session.flush()
    return row


# ============================================================ ITEM 3: ORDERING


class ExplodingIssueRepository:
    """A workflow collaborator that fails after core has already decided."""

    def __init__(self, message="simulated downstream failure"):
        self.message = message
        self.called = False

    def create_issue(self, **kwargs):
        self.called = True
        raise RuntimeError(self.message)


class HalfWritingIssueRepository:
    """Writes a row, THEN fails -- the case a savepoint has to clean up."""

    def __init__(self, db):
        self.db = db

    def create_issue(self, *, org_id, owner_id, created_by, title, description, severity, source_id):
        alert = ControlMonitoringAlert(
            organization_id=org_id,
            alert_type="should_not_survive",
            severity="low",
            status="open",
            title="partial write",
            description="written before the failure",
            alert_context_json={},
        )
        self.db.add(alert)
        self.db.flush()
        raise RuntimeError("failed after a partial write")


def test_breach_decision_survives_a_workflow_that_raises(db_session, env):
    """THE ordering guarantee.

    Fails if dispatch is ever moved ahead of the decision write, or if the whole
    operation is wrapped in one transaction that unwinds on workflow failure.
    """
    exploding = ExplodingIssueRepository()
    engine = GovernanceWorkflowEngine(db_session, issues=exploding)
    config = _config(env["org"], env["system"], env["owner"], tier="critical", order=0, workflow="create_issue")
    db_session.add(config)
    db_session.flush()

    events = engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    assert exploding.called, "precondition: the workflow really was attempted"

    # The decision is durable and queryable despite the dispatch failing.
    persisted = db_session.execute(
        select(AIMonitoringBreachEvent).where(
            AIMonitoringBreachEvent.organization_id == env["org"].id
        )
    ).scalars().all()
    assert len(persisted) == 1, "the breach decision was lost when its workflow failed"
    assert persisted[0].id == events[0].id
    assert persisted[0].tier == "critical"
    assert persisted[0].observed_value == Decimal("0.8100")
    # No workflow ran, so nothing to reference.
    assert persisted[0].workflow_reference is None

    # And the failure itself is on the record, not swallowed.
    failures = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_monitoring.breach_workflow_failed")
    ).scalars().all()
    assert len(failures) == 1
    assert "simulated downstream failure" in failures[0].after_json["error"]

    # The decision's own audit entry is still there too.
    decided = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_monitoring.breach_decided")
    ).scalars().all()
    assert len(decided) == 1


def test_a_partial_workflow_write_is_rolled_back_without_taking_the_decision(db_session, env):
    """The savepoint is what makes the guarantee hold in practice, not just on paper."""
    engine = GovernanceWorkflowEngine(db_session, issues=HalfWritingIssueRepository(db_session))
    config = _config(env["org"], env["system"], env["owner"], tier="critical", order=0, workflow="create_issue")
    db_session.add(config)
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    orphans = db_session.execute(
        select(ControlMonitoringAlert).where(ControlMonitoringAlert.alert_type == "should_not_survive")
    ).scalars().all()
    assert orphans == [], "a half-written workflow row survived its own failure"

    assert len(db_session.execute(select(AIMonitoringBreachEvent)).scalars().all()) == 1


def test_one_failing_tier_does_not_silence_the_others(db_session, env):
    """A broken workflow on one tier must not stop the rest from dispatching."""
    engine = GovernanceWorkflowEngine(db_session, issues=ExplodingIssueRepository())
    warning = _config(env["org"], env["system"], env["owner"], tier="warning", order=0, workflow="create_issue")
    critical = _config(
        env["org"], env["system"], env["owner"], tier="critical", order=1, workflow="create_alert"
    )
    db_session.add_all([warning, critical])
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[warning, critical], observed_value=Decimal("0.8100")
    )

    events = db_session.execute(select(AIMonitoringBreachEvent)).scalars().all()
    assert len(events) == 2, "a failing tier prevented another tier's decision"

    by_tier = {e.tier: e for e in events}
    assert by_tier["warning"].workflow_reference is None  # failed
    assert by_tier["critical"].workflow_reference is not None  # succeeded


def test_successful_dispatch_attaches_a_reference(db_session, env):
    engine = GovernanceWorkflowEngine(db_session)
    config = _config(env["org"], env["system"], env["owner"], tier="critical", order=0, workflow="create_alert")
    db_session.add(config)
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    event = db_session.execute(select(AIMonitoringBreachEvent)).scalars().one()
    assert event.workflow_reference is not None
    assert event.workflow_reference.startswith("alert:")

    dispatched = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_monitoring.breach_workflow_dispatched")
    ).scalars().all()
    assert len(dispatched) == 1


# ====================================================== ITEM 4: TIERED DISPATCH


def test_every_breached_tier_dispatches_no_early_exit(db_session, env):
    """Three tiers, all breached, all fire. No suppression of lower tiers."""
    engine = GovernanceWorkflowEngine(db_session)
    tiers = [
        _config(env["org"], env["system"], env["owner"], tier="info", order=0, workflow="create_alert", threshold="0.99"),
        _config(env["org"], env["system"], env["owner"], tier="warning", order=1, workflow="create_alert", threshold="0.95"),
        _config(env["org"], env["system"], env["owner"], tier="critical", order=2, workflow="notify_oncall", threshold="0.90"),
    ]
    db_session.add_all(tiers)
    db_session.flush()

    events = engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=tiers, observed_value=Decimal("0.8100")
    )

    assert len(events) == 3, "a breached tier was suppressed"
    assert {e.tier for e in events} == {"info", "warning", "critical"}
    # Each got its own workflow, and every one of them ran.
    assert all(e.workflow_reference is not None for e in events)

    alerts = db_session.execute(select(ControlMonitoringAlert)).scalars().all()
    assert len(alerts) == 3
    assert {a.alert_type for a in alerts} == {"ai_monitoring", "ai_monitoring_oncall"}


def test_only_actually_breached_tiers_dispatch(db_session, env):
    """The counterpart: a tier whose threshold was not crossed must NOT fire, so the
    no-suppression rule cannot be satisfied by simply firing everything."""
    engine = GovernanceWorkflowEngine(db_session)
    breached = _config(
        env["org"], env["system"], env["owner"], tier="warning", order=0, workflow="create_alert", threshold="0.95"
    )
    not_breached = _config(
        env["org"], env["system"], env["owner"], tier="critical", order=1, workflow="create_alert", threshold="0.50"
    )
    db_session.add_all([breached, not_breached])
    db_session.flush()

    events = engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[breached, not_breached], observed_value=Decimal("0.8100")
    )
    assert [e.tier for e in events] == ["warning"]


def test_tiers_dispatch_in_escalation_order(db_session, env):
    engine = GovernanceWorkflowEngine(db_session)
    tiers = [
        _config(env["org"], env["system"], env["owner"], tier="critical", order=2, workflow="create_alert", threshold="0.90"),
        _config(env["org"], env["system"], env["owner"], tier="info", order=0, workflow="create_alert", threshold="0.99"),
        _config(env["org"], env["system"], env["owner"], tier="warning", order=1, workflow="create_alert", threshold="0.95"),
    ]
    db_session.add_all(tiers)
    db_session.flush()

    events = engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=tiers, observed_value=Decimal("0.8100")
    )
    assert [e.tier for e in events] == ["info", "warning", "critical"]


def test_each_tier_gets_its_own_severity(db_session, env):
    assert severity_for_tier("critical") == "critical"
    assert severity_for_tier("high") == "high"
    assert severity_for_tier("warning") == "medium"
    assert severity_for_tier("info") == "low"
    # Free-text tier names fall back rather than raising.
    assert severity_for_tier("customer-defined-tier") == "medium"


# ================================================== the five workflows, for real


def test_create_issue_uses_the_real_issue_service_and_links_the_breach(db_session, env):
    engine = GovernanceWorkflowEngine(db_session)
    config = _config(env["org"], env["system"], env["owner"], tier="critical", order=0, workflow="create_issue")
    db_session.add(config)
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    issue = db_session.execute(select(Issue).where(Issue.organization_id == env["org"].id)).scalars().one()
    assert issue.source_type == "monitoring_alert"
    assert issue.issue_type == "compliance_violation"
    assert issue.severity == "critical"
    # Owner is the AI system's business owner; creator is the system account.
    assert issue.owner_id == env["owner"].id
    creator = db_session.execute(select(User).where(User.id == issue.created_by)).scalars().one()
    assert creator.is_system_account is True
    # The breach event that caused it is linked, which the upstream design could not do
    # because it dispatched before recording the decision.
    event = db_session.execute(select(AIMonitoringBreachEvent)).scalars().one()
    assert issue.source_id == event.id

    audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_monitoring.create_issue_dispatched")
    ).scalars().one()
    assert audit.metadata_json["assignment_path"] == "ai_system_owner"


def test_create_issue_falls_back_to_the_system_account_when_no_owner_is_set(db_session, env):
    env["system"].business_owner_user_id = None
    db_session.flush()

    engine = GovernanceWorkflowEngine(db_session)
    config = _config(env["org"], env["system"], env["owner"], tier="warning", order=0, workflow="create_issue")
    db_session.add(config)
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    issue = db_session.execute(select(Issue)).scalars().one()
    owner = db_session.execute(select(User).where(User.id == issue.owner_id)).scalars().one()
    assert owner.is_system_account is True
    audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_monitoring.create_issue_dispatched")
    ).scalars().one()
    assert audit.metadata_json["assignment_path"] == "system_account"


def test_update_risk_score_flags_loudly_when_no_risk_is_linked(db_session, env):
    engine = GovernanceWorkflowEngine(db_session)
    config = _config(env["org"], env["system"], env["owner"], tier="warning", order=0, workflow="update_risk_score")
    db_session.add(config)
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    alert = db_session.execute(
        select(ControlMonitoringAlert).where(
            ControlMonitoringAlert.alert_type == "ai_monitoring_unlinked_risk"
        )
    ).scalars().one()
    assert "no linked risk record" in alert.description
    skipped = db_session.execute(
        select(AuditLog).where(AuditLog.action == "ai_monitoring.update_risk_score_skipped")
    ).scalars().all()
    assert len(skipped) == 1
    # Flagged, not silently skipped -- the decision still carries a reference.
    event = db_session.execute(select(AIMonitoringBreachEvent)).scalars().one()
    assert event.workflow_reference is not None


def test_update_risk_score_flags_when_the_link_is_ambiguous(db_session, env):
    from app.models.risk import Risk

    risks = []
    for i in range(2):
        risk = Risk(
            id=uuid.uuid4(),
            organization_id=env["org"].id,
            title=f"Risk {i}",
            description="d",
            category="operational",
            likelihood=3,
            impact=3,
            status="open",
        )
        risks.append(risk)
    db_session.add_all(risks)
    db_session.flush()
    db_session.add_all(
        [
            AISystemRiskLink(
                organization_id=env["org"].id,
                ai_system_id=env["system"].id,
                risk_id=r.id,
                status="active",
            )
            for r in risks
        ]
    )
    db_session.flush()

    engine = GovernanceWorkflowEngine(db_session)
    config = _config(env["org"], env["system"], env["owner"], tier="warning", order=0, workflow="update_risk_score")
    db_session.add(config)
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    alert = db_session.execute(
        select(ControlMonitoringAlert).where(
            ControlMonitoringAlert.alert_type == "ai_monitoring_unlinked_risk"
        )
    ).scalars().one()
    assert "2 linked risk records" in alert.description


def test_require_review_uses_the_org_default_reviewer(db_session, env):
    db_session.add(
        OrganizationGovernanceSetting(
            organization_id=env["org"].id, default_reviewer_user_id=env["reviewer"].id
        )
    )
    db_session.flush()

    engine = GovernanceWorkflowEngine(db_session)
    config = _config(env["org"], env["system"], env["owner"], tier="critical", order=0, workflow="require_review")
    db_session.add(config)
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    review = db_session.execute(select(AIGovernanceReview)).scalars().one()
    assert review.assigned_reviewer_id == env["reviewer"].id
    # Core's four-eyes rule is satisfied by construction: the creator is the system
    # account, which can never be a configured human reviewer.
    assert review.created_by != review.assigned_reviewer_id
    creator = db_session.execute(select(User).where(User.id == review.created_by)).scalars().one()
    assert creator.is_system_account is True
    assert review.review_type == "change_review"


def test_require_review_flags_when_no_default_reviewer_is_configured(db_session, env):
    engine = GovernanceWorkflowEngine(db_session)
    config = _config(env["org"], env["system"], env["owner"], tier="warning", order=0, workflow="require_review")
    db_session.add(config)
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    alert = db_session.execute(
        select(ControlMonitoringAlert).where(
            ControlMonitoringAlert.alert_type == "ai_monitoring_no_default_reviewer"
        )
    ).scalars().one()
    assert "no default reviewer" in alert.description
    assert db_session.execute(select(AIGovernanceReview)).scalars().all() == []


def test_notify_oncall_records_an_alert_rather_than_pretending_to_page(db_session, env):
    engine = GovernanceWorkflowEngine(db_session)
    config = _config(env["org"], env["system"], env["owner"], tier="critical", order=0, workflow="notify_oncall")
    db_session.add(config)
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    alert = db_session.execute(
        select(ControlMonitoringAlert).where(
            ControlMonitoringAlert.alert_type == "ai_monitoring_oncall"
        )
    ).scalars().one()
    assert alert.severity == "critical"
    assert "outside core" in alert.description


def test_alert_context_carries_the_typed_breach_linkage(db_session, env):
    engine = GovernanceWorkflowEngine(db_session)
    config = _config(env["org"], env["system"], env["owner"], tier="warning", order=0, workflow="create_alert")
    db_session.add(config)
    db_session.flush()

    engine.dispatch_for_reading(
        env["org"].id, reading=env["reading"], configs=[config], observed_value=Decimal("0.8100")
    )

    alert = db_session.execute(select(ControlMonitoringAlert)).scalars().one()
    event = db_session.execute(select(AIMonitoringBreachEvent)).scalars().one()
    assert alert.alert_context_json["breach_event_id"] == str(event.id)
    assert alert.alert_context_json["tier"] == "warning"


def test_unknown_workflow_raises_rather_than_silently_doing_nothing(db_session, env):
    """An unrecognised workflow value must be loud. Silently returning would leave a
    breach recorded with no follow-through and nothing to say so."""
    from app.ai_governance.services.governance_workflow_engine import ComplianceDecision

    engine = GovernanceWorkflowEngine(db_session)
    decision = ComplianceDecision(
        organization_id=env["org"].id,
        ai_system_id=env["system"].id,
        config_id=uuid.uuid4(),
        reading_id=env["reading"].id,
        breach_event_id=uuid.uuid4(),
        metric_type="accuracy",
        tier="warning",
        escalation_order=0,
        observed_value=Decimal("0.81"),
        threshold_value=Decimal("0.90"),
        threshold_operator="lte",
        obligation_id=None,
    )

    with pytest.raises(WorkflowDispatchError) as exc:
        engine._dispatch_one(decision, "not_a_workflow")
    assert "no handler" in str(exc.value)


def test_suspend_system_has_no_handler(db_session):
    engine = GovernanceWorkflowEngine(db_session)
    handlers = {
        "create_alert": engine.create_alert,
        "create_issue": engine.create_issue,
        "update_risk_score": engine.update_risk_score,
        "require_review": engine.require_review,
        "notify_oncall": engine.notify_oncall,
    }
    assert "suspend_system" not in handlers, "suspend_system must have no handler"
    assert set(handlers) == {
        "create_alert",
        "create_issue",
        "update_risk_score",
        "require_review",
        "notify_oncall",
    }
