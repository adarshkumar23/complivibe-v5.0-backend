import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.applicability_evaluation_result import ApplicabilityEvaluationResult
from app.models.applicability_evaluation_run import ApplicabilityEvaluationRun
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.obligation_applicability_rule import ObligationApplicabilityRule
from app.models.organization_applicability_answer import OrganizationApplicabilityAnswer
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.role import Role
from app.models.user import User


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str, password: str = "Pass1234!@") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash(password),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def _framework_with_obligation(client, token: str) -> tuple[dict, dict]:
    frameworks = client.get("/api/v1/frameworks", headers=_headers(token))
    assert frameworks.status_code == 200
    for framework in frameworks.json():
        obligations = client.get(f"/api/v1/frameworks/{framework['id']}/obligations", headers=_headers(token))
        assert obligations.status_code == 200
        if obligations.json():
            return framework, obligations.json()[0]
    raise AssertionError("No framework with obligations found")


def _activate_framework(client, token: str, org_id: str, framework_id: str) -> None:
    response = client.post(
        f"/api/v1/frameworks/{framework_id}/activate",
        headers=_headers(token, org_id),
        json={},
    )
    assert response.status_code == 200


def _create_question(client, token: str, org_id: str, framework_id: str, obligation_id: str, key: str) -> dict:
    response = client.post(
        f"/api/v1/frameworks/{framework_id}/applicability-questions",
        headers=_headers(token, org_id),
        json={
            "obligation_id": obligation_id,
            "question_key": key,
            "question_text": f"Question {key}",
            "answer_type": "boolean",
            "required": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_rule(
    client,
    token: str,
    org_id: str,
    obligation_id: str,
    question_id: str,
    rule_key: str,
    result: str,
) -> dict:
    response = client.post(
        f"/api/v1/obligations/{obligation_id}/applicability-rules",
        headers=_headers(token, org_id),
        json={
            "question_id": question_id,
            "rule_key": rule_key,
            "operator": "equals",
            "expected_value_json": True,
            "result_applicability": result,
            "rationale": "deterministic rule",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_submit_answers_supersedes_history_and_list_is_tenant_scoped(client, db_session):
    owner1 = _register(client, "p35-owner1@example.com", "Pass1234!@", "P35 Org1")
    org1 = _org_id(client, owner1)
    framework, obligation = _framework_with_obligation(client, owner1)
    _activate_framework(client, owner1, org1, framework["id"])
    question = _create_question(client, owner1, org1, framework["id"], obligation["id"], "p35-q1")

    first = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner1, org1),
        json={"answers": [{"question_id": question["id"], "answer_value_json": True}]},
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner1, org1),
        json={"answers": [{"question_id": question["id"], "answer_value_json": False}]},
    )
    assert second.status_code == 201

    active_only = client.get(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner1, org1),
    )
    assert active_only.status_code == 200
    assert len(active_only.json()) == 1
    assert active_only.json()[0]["answer_value_json"] is False

    with_history = client.get(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers?active_only=false",
        headers=_headers(owner1, org1),
    )
    assert with_history.status_code == 200
    assert len(with_history.json()) == 2
    statuses = {item["status"] for item in with_history.json()}
    assert "active" in statuses and "superseded" in statuses

    owner2 = _register(client, "p35-owner2@example.com", "Pass1234!@", "P35 Org2")
    org2 = _org_id(client, owner2)
    _activate_framework(client, owner2, org2, framework["id"])

    tenant_scoped = client.get(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner2, org2),
    )
    assert tenant_scoped.status_code == 200
    assert tenant_scoped.json() == []

    answers = db_session.query(OrganizationApplicabilityAnswer).filter(
        OrganizationApplicabilityAnswer.organization_id == uuid.UUID(org1),
        OrganizationApplicabilityAnswer.framework_id == uuid.UUID(framework["id"]),
        OrganizationApplicabilityAnswer.question_id == uuid.UUID(question["id"]),
    ).all()
    assert len(answers) == 2


def test_cannot_submit_answer_for_question_from_another_framework(client):
    owner = _register(client, "p35-owner3@example.com", "Pass1234!@", "P35 Org3")
    org = _org_id(client, owner)

    frameworks = client.get("/api/v1/frameworks", headers=_headers(owner)).json()
    assert len(frameworks) >= 2
    fw1, _ = _framework_with_obligation(client, owner)
    fw2 = next(item for item in frameworks if item["id"] != fw1["id"])

    _activate_framework(client, owner, org, fw1["id"])
    _activate_framework(client, owner, org, fw2["id"])

    question_fw2_resp = client.post(
        f"/api/v1/frameworks/{fw2['id']}/applicability-questions",
        headers=_headers(owner, org),
        json={
            "question_key": "p35-q-fw2",
            "question_text": "Question for framework 2",
            "answer_type": "boolean",
            "required": True,
        },
    )
    assert question_fw2_resp.status_code == 201
    question_fw2 = question_fw2_resp.json()

    invalid = client.post(
        f"/api/v1/frameworks/{fw1['id']}/applicability-answers",
        headers=_headers(owner, org),
        json={"answers": [{"question_id": question_fw2["id"], "answer_value_json": True}]},
    )
    assert invalid.status_code == 400


def test_rule_create_archive_validate_and_permissions(client, db_session):
    owner = _register(client, "p35-owner4@example.com", "Pass1234!@", "P35 Org4")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    question = _create_question(client, owner, org, framework["id"], obligation["id"], "p35-q-rule")

    readonly = _create_active_user_with_role(db_session, org, "p35-readonly@example.com", "readonly")
    readonly_token = _login(client, readonly.email, "Pass1234!@")

    readonly_forbidden = client.post(
        f"/api/v1/obligations/{obligation['id']}/applicability-rules",
        headers=_headers(readonly_token, org),
        json={
            "question_id": question["id"],
            "rule_key": "deny",
            "operator": "equals",
            "expected_value_json": True,
            "result_applicability": "applicable",
            "rationale": "x",
        },
    )
    assert readonly_forbidden.status_code == 403

    invalid_operator = client.post(
        f"/api/v1/obligations/{obligation['id']}/applicability-rules",
        headers=_headers(owner, org),
        json={
            "question_id": question["id"],
            "rule_key": "bad-op",
            "operator": "bad",
            "expected_value_json": True,
            "result_applicability": "applicable",
            "rationale": "x",
        },
    )
    assert invalid_operator.status_code == 400

    invalid_result = client.post(
        f"/api/v1/obligations/{obligation['id']}/applicability-rules",
        headers=_headers(owner, org),
        json={
            "question_id": question["id"],
            "rule_key": "bad-result",
            "operator": "equals",
            "expected_value_json": True,
            "result_applicability": "not_real",
            "rationale": "x",
        },
    )
    assert invalid_result.status_code == 400

    created = _create_rule(client, owner, org, obligation["id"], question["id"], "good-rule", "applicable")

    listed = client.get(f"/api/v1/obligations/{obligation['id']}/applicability-rules", headers=_headers(owner, org))
    assert listed.status_code == 200
    assert any(item["id"] == created["id"] for item in listed.json())

    archived = client.post(
        f"/api/v1/obligations/{obligation['id']}/applicability-rules/{created['id']}/archive",
        headers=_headers(owner, org),
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_dry_run_evaluation_does_not_persist_runs_or_results(client, db_session):
    owner = _register(client, "p35-owner5@example.com", "Pass1234!@", "P35 Org5")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    question = _create_question(client, owner, org, framework["id"], obligation["id"], "p35-q-dry")
    _create_rule(client, owner, org, obligation["id"], question["id"], "dry-rule", "applicable")

    response = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability/evaluate",
        headers=_headers(owner, org),
        json={"dry_run": True, "update_obligation_states": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["run"] is None

    run_count = db_session.query(ApplicabilityEvaluationRun).filter(
        ApplicabilityEvaluationRun.organization_id == uuid.UUID(org),
        ApplicabilityEvaluationRun.framework_id == uuid.UUID(framework["id"]),
    ).count()
    result_count = db_session.query(ApplicabilityEvaluationResult).filter(
        ApplicabilityEvaluationResult.organization_id == uuid.UUID(org),
        ApplicabilityEvaluationResult.framework_id == uuid.UUID(framework["id"]),
    ).count()
    assert run_count == 0
    assert result_count == 0


def test_live_evaluation_persists_results_updates_state_and_exposes_status_summary(client, db_session):
    owner = _register(client, "p35-owner6@example.com", "Pass1234!@", "P35 Org6")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    question = _create_question(client, owner, org, framework["id"], obligation["id"], "p35-q-live")

    _create_rule(client, owner, org, obligation["id"], question["id"], "conflict-a", "applicable")
    _create_rule(client, owner, org, obligation["id"], question["id"], "conflict-b", "not_applicable")

    submit = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner, org),
        json={"answers": [{"question_id": question["id"], "answer_value_json": True}]},
    )
    assert submit.status_code == 201

    evaluate = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability/evaluate",
        headers=_headers(owner, org),
        json={"dry_run": False, "update_obligation_states": True},
    )
    assert evaluate.status_code == 200
    body = evaluate.json()
    assert body["run"] is not None
    assert body["run"]["id"]

    run_id = body["run"]["id"]
    detail = client.get(
        f"/api/v1/frameworks/{framework['id']}/applicability/evaluations/{run_id}",
        headers=_headers(owner, org),
    )
    assert detail.status_code == 200
    assert detail.json()["caveat"]

    obligation_result = next(item for item in detail.json()["results"] if item["obligation_id"] == obligation["id"])
    assert obligation_result["suggested_applicability"] == "needs_review"

    state = db_session.query(OrganizationObligationState).filter(
        OrganizationObligationState.organization_id == uuid.UUID(org),
        OrganizationObligationState.obligation_id == uuid.UUID(obligation["id"]),
    ).one()
    assert state.applicability_status == "needs_review"

    status = client.get(
        f"/api/v1/obligations/{obligation['id']}/applicability-status",
        headers=_headers(owner, org),
    )
    assert status.status_code == 200
    assert status.json()["organization_applicability"] == "needs_review"
    assert status.json()["suggested_applicability"] == "needs_review"
    assert "not legal advice" in status.json()["caveat"]

    summary = client.get(
        f"/api/v1/frameworks/{framework['id']}/applicability/summary",
        headers=_headers(owner, org),
    )
    assert summary.status_code == 200
    assert summary.json()["total_obligations"] >= 1
    assert summary.json()["latest_evaluation_at"] is not None

    actions = {
        row.action
        for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()
    }
    assert "applicability_answer.submitted" in actions
    assert "obligation_applicability_rule.created" in actions
    assert "applicability_evaluation.completed" in actions


def test_missing_answers_results_in_unknown_and_run_is_persisted(client):
    owner = _register(client, "p35-owner7@example.com", "Pass1234!@", "P35 Org7")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    question = _create_question(client, owner, org, framework["id"], obligation["id"], "p35-q-missing")
    _create_rule(client, owner, org, obligation["id"], question["id"], "missing-rule", "applicable")

    evaluate = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability/evaluate",
        headers=_headers(owner, org),
        json={"dry_run": False, "update_obligation_states": False},
    )
    assert evaluate.status_code == 200

    results = evaluate.json()["results"]
    obligation_result = next(item for item in results if item["obligation_id"] == obligation["id"])
    assert obligation_result["suggested_applicability"] == "unknown"
    assert obligation_result["missing_answers_json"]


def test_evaluation_flags_stale_inputs_after_rule_change(client, db_session):
    owner = _register(client, "p35-owner8@example.com", "Pass1234!@", "P35 Org8")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)
    _activate_framework(client, owner, org, framework["id"])
    question = _create_question(client, owner, org, framework["id"], obligation["id"], "p35-q-stale")
    rule = _create_rule(client, owner, org, obligation["id"], question["id"], "stale-rule", "applicable")

    submit = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability-answers",
        headers=_headers(owner, org),
        json={"answers": [{"question_id": question["id"], "answer_value_json": True}]},
    )
    assert submit.status_code == 201

    fresh_eval = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability/evaluate",
        headers=_headers(owner, org),
        json={"dry_run": False, "update_obligation_states": False},
    )
    assert fresh_eval.status_code == 200
    fresh_result = next(item for item in fresh_eval.json()["results"] if item["obligation_id"] == obligation["id"])
    assert fresh_result["suggested_applicability"] == "applicable"

    row = db_session.query(ObligationApplicabilityRule).filter(ObligationApplicabilityRule.id == uuid.UUID(rule["id"])).one()
    row.updated_at = datetime.now(UTC) + timedelta(minutes=5)
    db_session.add(row)
    db_session.commit()

    stale_eval = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability/evaluate",
        headers=_headers(owner, org),
        json={"dry_run": False, "update_obligation_states": False},
    )
    assert stale_eval.status_code == 200
    stale_result = next(item for item in stale_eval.json()["results"] if item["obligation_id"] == obligation["id"])
    assert stale_result["suggested_applicability"] == "needs_review"
    assert "stale" in stale_result["rationale"].lower()
    assert stale_result["provenance_json"]["stale_input_count"] >= 1
