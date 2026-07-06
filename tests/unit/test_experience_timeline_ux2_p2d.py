from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.compliance_deadline import ComplianceDeadline
from app.models.compliance_deadline_event import ComplianceDeadlineEvent
from app.models.control import Control
from app.models.control_test_definition import ControlTestDefinition
from app.models.control_test_run import ControlTestRun
from app.models.evidence_item import EvidenceItem
from app.models.issue import Issue
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user


def _seed_timeline_records(db_session, org_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, uuid.UUID]:
    now = datetime.now(UTC)

    control = Control(
        organization_id=org_id,
        title="Access review control",
        created_by_user_id=user_id,
    )
    db_session.add(control)
    db_session.flush()

    test_def = ControlTestDefinition(
        organization_id=org_id,
        control_id=control.id,
        name="Quarterly review check",
        test_type="manual",
        check_key="access_review",
        created_by_user_id=user_id,
    )
    db_session.add(test_def)
    db_session.flush()

    control_run = ControlTestRun(
        organization_id=org_id,
        control_test_definition_id=test_def.id,
        control_id=control.id,
        result="pass",
        check_key="access_review",
        execution_source="manual",
        created_at=now - timedelta(hours=2),
    )
    db_session.add(control_run)

    evidence = EvidenceItem(
        organization_id=org_id,
        title="Access review screenshot",
        evidence_type="screenshot",
        source="manual",
        status="active",
        review_status="approved",
        freshness_status="fresh",
        created_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
        collected_at=now - timedelta(hours=1),
        uploaded_by_user_id=user_id,
    )
    db_session.add(evidence)

    risk = Risk(
        organization_id=org_id,
        title="Unreviewed privileged access",
        severity="high",
        status="identified",
        created_by_user_id=user_id,
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    db_session.add(risk)

    issue = Issue(
        organization_id=org_id,
        title="Access drift incident",
        description="Access drift resolved with remediation",
        issue_type="security_incident",
        severity="high",
        status="resolved",
        source_type="manual",
        owner_id=user_id,
        created_by=user_id,
        resolved_at=now - timedelta(minutes=30),
    )
    db_session.add(issue)

    met_deadline = ComplianceDeadline(
        organization_id=org_id,
        title="Quarterly access review deadline",
        deadline_type="control_review",
        due_date=date.today(),
        status="completed",
        priority="medium",
        owner_user_id=user_id,
        linked_entity_type="control",
        linked_entity_id=control.id,
        completed_at=now - timedelta(minutes=15),
        completed_by_user_id=user_id,
        created_by_user_id=user_id,
    )
    db_session.add(met_deadline)
    db_session.flush()

    missed_deadline = ComplianceDeadline(
        organization_id=org_id,
        title="Missed evidence refresh deadline",
        deadline_type="evidence_refresh",
        due_date=date.today() - timedelta(days=2),
        status="overdue",
        priority="high",
        owner_user_id=user_id,
        linked_entity_type="evidence",
        linked_entity_id=evidence.id,
        created_by_user_id=user_id,
    )
    db_session.add(missed_deadline)
    db_session.flush()

    missed_event = ComplianceDeadlineEvent(
        organization_id=org_id,
        deadline_id=missed_deadline.id,
        event_type="overdue_detected",
        dry_run=False,
        outbox_queued=False,
        created_at=now - timedelta(minutes=10),
    )
    db_session.add(missed_event)
    db_session.commit()

    return {
        "risk_id": risk.id,
        "control_id": control.id,
    }


def test_ux2_compliance_timeline_aggregates_real_events(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="ux2-timeline")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    _seed_timeline_records(db_session, org_id, user_id)

    resp = client.get("/api/v1/compliance-timeline", headers=ctx["org_headers"])
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["total_events"] >= 6

    event_types = {row["event_type"] for row in payload["events"]}
    assert "evidence_collected" in event_types
    assert "control_tested" in event_types
    assert "risk_raised" in event_types
    assert "issue_resolved" in event_types
    assert "deadline_met" in event_types
    assert "deadline_missed" in event_types


def test_ux2_compliance_timeline_scoped_and_adversarial_filters(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="ux2-scope")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    ids = _seed_timeline_records(db_session, org_id, user_id)

    scoped = client.get(
        "/api/v1/compliance-timeline",
        params={"entity_type": "risk", "entity_id": str(ids["risk_id"])},
        headers=ctx["org_headers"],
    )
    assert scoped.status_code == 200, scoped.text
    scoped_payload = scoped.json()
    assert scoped_payload["total_events"] >= 1
    assert {row["event_type"] for row in scoped_payload["events"]} == {"risk_raised"}

    bad_filter = client.get(
        "/api/v1/compliance-timeline",
        params={"entity_type": "not_real"},
        headers=ctx["org_headers"],
    )
    assert bad_filter.status_code == 422
