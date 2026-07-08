from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.obligation_applicability_question import ObligationApplicabilityQuestion
from app.models.obligation_applicability_rule import ObligationApplicabilityRule
from tests.unit.test_applicability_phase35 import (
    _activate_framework,
    _create_question,
    _create_rule,
    _framework_with_obligation,
    _headers,
    _org_id,
    _register,
)


def test_phase99_reject_duplicate_question_ids_in_single_submit(client):
    owner = _register(client, "p99-owner-dup@example.com", "Pass1234!@", "P99 Applicability Dup")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    question = _create_question(client, owner, org, framework["id"], obligation["id"], "p99-q-dup")

    duplicate = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner, org),
        json={
            "answers": [
                {"question_id": question["id"], "answer_value_json": True},
                {"question_id": question["id"], "answer_value_json": False},
            ]
        },
    )
    assert duplicate.status_code == 400
    assert "Duplicate question_id" in duplicate.json()["detail"]


def test_phase99_reject_answer_for_inactive_question_and_missing_payload(client, db_session):
    owner = _register(client, "p99-owner-inactive@example.com", "Pass1234!@", "P99 Applicability Inactive")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    question = _create_question(client, owner, org, framework["id"], obligation["id"], "p99-q-inactive")

    row = db_session.query(ObligationApplicabilityQuestion).filter(
        ObligationApplicabilityQuestion.id == uuid.UUID(question["id"])
    ).one()
    row.status = "archived"
    db_session.add(row)
    db_session.commit()

    inactive_submit = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner, org),
        json={"answers": [{"question_id": question["id"], "answer_value_json": True}]},
    )
    assert inactive_submit.status_code == 400
    assert "not active" in inactive_submit.json()["detail"]

    # Create another active question and verify empty answer payload is rejected.
    active_question = _create_question(client, owner, org, framework["id"], obligation["id"], "p99-q-empty")
    empty_submit = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner, org),
        json={"answers": [{"question_id": active_question["id"]}]},
    )
    assert empty_submit.status_code == 400
    assert "answer_value_json or answer_text is required" in empty_submit.json()["detail"]


def test_phase99_summary_surfaces_required_completion_and_stale_answers(client, db_session):
    owner = _register(client, "p99-owner-summary@example.com", "Pass1234!@", "P99 Applicability Summary")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    question = _create_question(client, owner, org, framework["id"], obligation["id"], "p99-q-summary")
    rule = _create_rule(client, owner, org, obligation["id"], question["id"], "p99-rule-summary", "applicable")

    submit = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner, org),
        json={"answers": [{"question_id": question["id"], "answer_value_json": True}]},
    )
    assert submit.status_code == 201

    question_row = db_session.query(ObligationApplicabilityQuestion).filter(
        ObligationApplicabilityQuestion.id == uuid.UUID(question["id"])
    ).one()
    rule_row = db_session.query(ObligationApplicabilityRule).filter(
        ObligationApplicabilityRule.id == uuid.UUID(rule["id"])
    ).one()
    question_row.updated_at = datetime.now(UTC) + timedelta(minutes=10)
    rule_row.updated_at = datetime.now(UTC) + timedelta(minutes=12)
    db_session.add(question_row)
    db_session.add(rule_row)
    db_session.commit()

    summary = client.get(
        f"/api/v1/frameworks/{framework['id']}/applicability/summary",
        headers=_headers(owner, org),
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["required_questions_count"] >= 1
    assert body["answered_required_questions"] >= 1
    assert body["answer_completion_pct"] > 0
    assert body["latest_answer_at"] is not None
    assert body["latest_rule_or_question_change_at"] is not None
    assert body["answers_stale_since_latest_change"] is True
    assert body["stale_answers_count"] >= 1
