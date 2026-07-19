from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.organization_obligation_state import OrganizationObligationState
from tests.unit.test_applicability_phase35 import (
    _activate_framework,
    _create_question,
    _create_rule,
    _framework_with_obligation,
    _headers,
    _org_id,
    _register,
)

import pytest

# The framework catalogue and starter obligations used to be seeded lazily by the
# framework/obligation GET handlers -- a read endpoint that wrote rows. Those handlers
# are now side-effect-free, so these tests request the reference data explicitly.
pytestmark = pytest.mark.usefixtures("seeded_reference_data")


def test_phase100_obligation_detail_surfaces_suggestion_conflict_and_context(client, db_session):
    owner = _register(client, "p100-owner-detail@example.com", "Pass1234!@", "P100 Obligation Detail")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    question = _create_question(client, owner, org, framework["id"], obligation["id"], "p100-q-detail")
    _create_rule(client, owner, org, obligation["id"], question["id"], "p100-rule-detail", "applicable")

    submit = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner, org),
        json={"answers": [{"question_id": question["id"], "answer_value_json": True}]},
    )
    assert submit.status_code == 201

    evaluate = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability/evaluate",
        headers=_headers(owner, org),
        json={"dry_run": False, "update_obligation_states": False},
    )
    assert evaluate.status_code == 200

    override = client.patch(
        f"/api/v1/obligations/{obligation['id']}/state",
        headers=_headers(owner, org),
        json={
            "applicability_status": "not_applicable",
            "implementation_status": "blocked",
            "justification": "Manual legal override",
        },
    )
    assert override.status_code == 200

    detail = client.get(f"/api/v1/obligations/{obligation['id']}", headers=_headers(owner, org))
    assert detail.status_code == 200
    body = detail.json()
    assert body["latest_suggested_applicability"] == "applicable"
    assert body["suggestion_conflicts_with_org_state"] is True
    assert body["latest_suggestion_stale_inputs"] >= 0
    assert body["linked_controls_count"] == 0
    assert "org_state_overrides_suggestion" in body["context_flags"]

    state_row = db_session.execute(
        select(OrganizationObligationState).where(
            OrganizationObligationState.organization_id == uuid.UUID(org),
            OrganizationObligationState.obligation_id == uuid.UUID(obligation["id"]),
        )
    ).scalar_one()
    assert state_row.applicability_status == "not_applicable"
    assert state_row.implementation_status == "blocked"


def test_phase100_obligation_state_guardrails_require_justification_and_consistent_status(client, db_session):
    owner = _register(client, "p100-owner-guard@example.com", "Pass1234!@", "P100 Obligation Guardrails")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])

    blocked_without_reason = client.patch(
        f"/api/v1/obligations/{obligation['id']}/state",
        headers=_headers(owner, org),
        json={"applicability_status": "applicable", "implementation_status": "blocked"},
    )
    assert blocked_without_reason.status_code == 400
    assert "implementation_status is blocked" in blocked_without_reason.json()["detail"]

    implemented_non_applicable = client.patch(
        f"/api/v1/obligations/{obligation['id']}/state",
        headers=_headers(owner, org),
        json={
            "applicability_status": "needs_review",
            "implementation_status": "implemented",
            "justification": "inconsistent state",
        },
    )
    assert implemented_non_applicable.status_code == 400
    assert "implemented requires applicability_status applicable" in implemented_non_applicable.json()["detail"]

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org),
            AuditLog.action == "obligation.state_updated",
        )
    ).scalars().all()
    assert audit == []
