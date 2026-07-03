from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.inbound_questionnaire_session import InboundQuestionnaireSession
from app.models.membership import Membership
from app.models.organization_framework import OrganizationFramework
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/inbound-questionnaires/response-time-metrics"


def _create_inbound_session(
    db_session,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str,
    created_at: datetime,
    completed_at: datetime | None,
    status: str,
) -> InboundQuestionnaireSession:
    row = InboundQuestionnaireSession(
        organization_id=org_id,
        title=title,
        sender_name="Security Team",
        sender_email="security@example.com",
        description="Inbound questionnaire",
        due_date=None,
        status=status,
        total_questions=0,
        drafted_count=0,
        approved_count=0,
        sent_count=0,
        completed_at=completed_at,
        created_by=user_id,
        created_at=created_at,
        updated_at=completed_at or created_at,
        deleted_at=None,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_s5_p4_response_time_metrics_known_durations(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s5p4-metrics-known")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    now = datetime.now(UTC)
    _create_inbound_session(
        db_session,
        org_id=org_id,
        user_id=user_id,
        title="S1",
        created_at=now - timedelta(hours=30),
        completed_at=now - timedelta(hours=20),
        status="completed",
    )  # 10h
    _create_inbound_session(
        db_session,
        org_id=org_id,
        user_id=user_id,
        title="S2",
        created_at=now - timedelta(hours=20),
        completed_at=now - timedelta(hours=5),
        status="completed",
    )  # 15h
    _create_inbound_session(
        db_session,
        org_id=org_id,
        user_id=user_id,
        title="S3",
        created_at=now - timedelta(hours=9),
        completed_at=now - timedelta(hours=2),
        status="completed",
    )  # 7h
    db_session.commit()

    response = client.get(BASE, headers=org["org_headers"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["sessions_analyzed"] == 3
    assert body["sessions_still_pending"] == 0
    assert body["avg_response_time_hours"] == 10.67
    assert body["median_response_time_hours"] == 10.0
    assert body["fastest_response_time_hours"] == 7.0
    assert body["slowest_response_time_hours"] == 15.0


def test_s5_p4_response_time_pending_excluded_and_counted(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s5p4-metrics-pending")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    now = datetime.now(UTC)
    _create_inbound_session(
        db_session,
        org_id=org_id,
        user_id=user_id,
        title="Completed",
        created_at=now - timedelta(hours=12),
        completed_at=now - timedelta(hours=2),
        status="completed",
    )
    _create_inbound_session(
        db_session,
        org_id=org_id,
        user_id=user_id,
        title="Pending",
        created_at=now - timedelta(hours=4),
        completed_at=None,
        status="in_progress",
    )
    db_session.commit()

    response = client.get(BASE, headers=org["org_headers"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["sessions_analyzed"] == 1
    assert body["sessions_still_pending"] == 1
    assert body["avg_response_time_hours"] == 10.0
    assert body["median_response_time_hours"] == 10.0


def test_s5_p4_response_time_single_session_filter(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s5p4-metrics-one")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    now = datetime.now(UTC)
    s1 = _create_inbound_session(
        db_session,
        org_id=org_id,
        user_id=user_id,
        title="Filter 1",
        created_at=now - timedelta(hours=10),
        completed_at=now - timedelta(hours=5),
        status="completed",
    )  # 5h
    _create_inbound_session(
        db_session,
        org_id=org_id,
        user_id=user_id,
        title="Filter 2",
        created_at=now - timedelta(hours=12),
        completed_at=now - timedelta(hours=2),
        status="completed",
    )  # 10h
    db_session.commit()

    response = client.get(BASE, headers=org["org_headers"], params={"session_id": str(s1.id)})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["session_id"] == str(s1.id)
    assert body["sessions_analyzed"] == 1
    assert body["sessions_still_pending"] == 0
    assert body["avg_response_time_hours"] == 5.0
    assert body["median_response_time_hours"] == 5.0
    assert body["fastest_response_time_hours"] == 5.0
    assert body["slowest_response_time_hours"] == 5.0


def test_s5_p4_response_time_zero_sessions(client):
    org = bootstrap_org_user(client, email_prefix="s5p4-metrics-zero")

    response = client.get(BASE, headers=org["org_headers"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["sessions_analyzed"] == 0
    assert body["sessions_still_pending"] == 0
    assert body["avg_response_time_hours"] is None
    assert body["median_response_time_hours"] is None
    assert body["fastest_response_time_hours"] is None
    assert body["slowest_response_time_hours"] is None


def test_s5_p4_onboarding_checklist_evidence_signal_false(client):
    org = bootstrap_org_user(client, email_prefix="s5p4-onboarding-no-evidence")

    response = client.get("/api/v1/onboarding/checklist", headers=org["org_headers"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["checklist"]["evidence_uploaded"] is False
    evidence_item = next(item for item in body["checklist_items"] if item["id"] == "evidence_uploaded")
    assert evidence_item["completed"] is False
    assert evidence_item["completed_at"] is None


def test_s5_p4_onboarding_checklist_evidence_signal_true(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s5p4-onboarding-evidence")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    reviewed_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.add(
        EvidenceItem(
            organization_id=org_id,
            title="Verified Evidence",
            description="Verified proof",
            evidence_type="document",
            source="manual",
            status="active",
            review_status="verified",
            freshness_status="current",
            uploaded_by_user_id=user_id,
            reviewed_by_user_id=user_id,
            reviewed_at=reviewed_at,
            metadata_json={},
        )
    )
    db_session.commit()

    response = client.get("/api/v1/onboarding/checklist", headers=org["org_headers"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["checklist"]["evidence_uploaded"] is True
    evidence_item = next(item for item in body["checklist_items"] if item["id"] == "evidence_uploaded")
    assert evidence_item["completed"] is True
    assert evidence_item["completed_at"] is not None


def test_s5_p4_onboarding_existing_signals_unchanged_additive(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s5p4-onboarding-existing")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    framework = Framework(
        code="S5P4-FW",
        name="Sprint 5 P4 Framework",
        category="security",
        jurisdiction="global",
        status="active",
    )
    db_session.add(framework)
    db_session.flush()
    db_session.add(
        OrganizationFramework(
            organization_id=org_id,
            framework_id=framework.id,
            status="active",
            activated_by_user_id=user_id,
            activated_at=datetime.now(UTC),
        )
    )

    owner_membership = (
        db_session.query(Membership)
        .filter(Membership.organization_id == org_id, Membership.user_id == user_id)
        .one()
    )
    second_user = bootstrap_org_user(client, email_prefix="s5p4-onboarding-member")
    second_user_id = uuid.UUID(second_user["user_id"])
    db_session.add(
        Membership(
            organization_id=org_id,
            user_id=second_user_id,
            role_id=owner_membership.role_id,
            status="active",
            invited_by=user_id,
        )
    )

    db_session.add(
        Control(
            organization_id=org_id,
            title="Checklist Control",
            control_type="process",
            status="implemented",
            criticality="medium",
            source="custom",
        )
    )
    db_session.add(
        Risk(
            organization_id=org_id,
            title="Checklist Risk",
            category="security",
            severity="medium",
            likelihood=3,
            impact=3,
            inherent_score=9,
            status="identified",
            treatment_strategy="mitigate",
            composite_score_method="standard",
            created_by_user_id=user_id,
        )
    )
    db_session.commit()

    response = client.get("/api/v1/onboarding/checklist", headers=org["org_headers"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["checklist"]["org_created"] is True
    assert body["checklist"]["frameworks_selected"] is True
    assert body["checklist"]["team_invited_or_has_members"] is True
    assert body["checklist"]["has_controls"] is True
    assert body["checklist"]["has_risks"] is True

    checklist_item_ids = {item["id"] for item in body["checklist_items"]}
    assert {
        "org_created",
        "frameworks_selected",
        "team_invited_or_has_members",
        "has_controls",
        "has_risks",
        "evidence_uploaded",
    }.issubset(checklist_item_ids)
