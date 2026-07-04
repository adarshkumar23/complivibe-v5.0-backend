from datetime import UTC, date, datetime, timedelta
import uuid

from app.compliance.services.technical_control_service import TechnicalControlEvaluator
from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.control_test_run import ControlTestRun
from app.models.membership import Membership
from app.models.role import Role
from app.models.technical_control_agent import TechnicalControlAgent
from app.models.technical_control_result import TechnicalControlResult
from app.models.technical_control_rule import TechnicalControlRule
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

AGENTS_BASE = "/api/v1/compliance/technical-control-agents"
RULES_BASE = "/api/v1/compliance/technical-control-rules"
RESULTS_BASE = "/api/v1/compliance/technical-control-results"
INGEST_URL = "/api/v1/technical-control-results/ingest"


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str = "admin") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def _create_control(client, headers: dict[str, str], *, title: str) -> dict:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "technical", "criticality": "medium"},
    )
    assert response.status_code == 201
    return response.json()


def _register_agent(client, org_headers_map: dict[str, str], *, name: str, description: str | None = None) -> dict:
    response = client.post(
        AGENTS_BASE,
        headers=org_headers_map,
        json={"name": name, "description": description},
    )
    assert response.status_code == 201
    return response.json()


def _create_rule(
    client,
    org_headers_map: dict[str, str],
    *,
    control_id: str,
    name: str = "S3 Encryption Rule",
    target_resource_type: str = "aws_s3",
    expected_config_key: str = "encryption.enabled",
    expected_config_value: str = "true",
    evaluation_operator: str = "equals",
    severity: str = "warning",
) -> dict:
    response = client.post(
        RULES_BASE,
        headers=org_headers_map,
        json={
            "control_id": control_id,
            "name": name,
            "description": "rule desc",
            "target_resource_type": target_resource_type,
            "expected_config_key": expected_config_key,
            "expected_config_value": expected_config_value,
            "evaluation_operator": evaluation_operator,
            "severity": severity,
        },
    )
    assert response.status_code == 201
    return response.json()


def _ingest(client, token: str, payload: dict) -> dict:
    response = client.post(
        INGEST_URL,
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    return {"status_code": response.status_code, "json": response.json()}


def _mk_rule(operator: str, expected: str) -> TechnicalControlRule:
    return TechnicalControlRule(
        organization_id=uuid.uuid4(),
        control_id=uuid.uuid4(),
        name="rule",
        description=None,
        target_resource_type="generic",
        expected_config_key="key",
        expected_config_value=expected,
        evaluation_operator=operator,
        severity="warning",
        is_active=True,
        created_by=None,
    )


def test_a24_agent_lifecycle_and_org_scoping(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a24-agent-a")
    org2 = bootstrap_org_user(client, email_prefix="a24-agent-b")

    created = _register_agent(client, org1["org_headers"], name="scanner-a", description="scanner")
    assert created["token"]

    stored = db_session.query(TechnicalControlAgent).filter_by(id=uuid.UUID(created["id"])).one()
    assert stored.token_hash != created["token"]
    assert len(stored.token_hash) == 64

    duplicate = client.post(
        AGENTS_BASE,
        headers=org1["org_headers"],
        json={"name": "scanner-a"},
    )
    assert duplicate.status_code == 409

    list_org1 = client.get(AGENTS_BASE, headers=org1["org_headers"])
    assert list_org1.status_code == 200
    assert len(list_org1.json()) == 1

    list_org2 = client.get(AGENTS_BASE, headers=org2["org_headers"])
    assert list_org2.status_code == 200
    assert len(list_org2.json()) == 0

    deleted = client.delete(f"{AGENTS_BASE}/{created['id']}", headers=org1["org_headers"])
    assert deleted.status_code == 200
    assert deleted.json()["is_active"] is False

    list_after = client.get(AGENTS_BASE, headers=org1["org_headers"])
    assert list_after.status_code == 200
    assert list_after.json() == []


def test_a24_rule_lifecycle_filters_and_cross_org_control_validation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a24-rule-a")
    org2 = bootstrap_org_user(client, email_prefix="a24-rule-b")

    control1 = _create_control(client, org1["org_headers"], title="a24 c1")
    control2 = _create_control(client, org2["org_headers"], title="a24 c2")

    rule = _create_rule(client, org1["org_headers"], control_id=control1["id"], name="r1", target_resource_type="aws_s3")

    bad = client.post(
        RULES_BASE,
        headers=org1["org_headers"],
        json={
            "control_id": control2["id"],
            "name": "bad",
            "target_resource_type": "aws_s3",
            "expected_config_key": "x",
            "expected_config_value": "y",
            "evaluation_operator": "equals",
            "severity": "warning",
        },
    )
    assert bad.status_code == 404

    filtered = client.get(
        RULES_BASE,
        headers=org1["org_headers"],
        params={"control_id": control1["id"], "resource_type": "aws_s3", "is_active": True},
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["id"] == rule["id"]

    deactivated = client.delete(f"{RULES_BASE}/{rule['id']}", headers=org1["org_headers"])
    assert deactivated.status_code == 200

    filtered_after = client.get(RULES_BASE, headers=org1["org_headers"], params={"is_active": True})
    assert filtered_after.status_code == 200
    assert all(item["id"] != rule["id"] for item in filtered_after.json())


def test_a24_evaluator_all_operators():
    evaluator = TechnicalControlEvaluator()

    assert evaluator.evaluate(_mk_rule("equals", "true"), "TRUE")[0] is True
    assert evaluator.evaluate(_mk_rule("equals", "true"), "false")[0] is False

    assert evaluator.evaluate(_mk_rule("not_equals", "abc"), "xyz")[0] is True

    assert evaluator.evaluate(_mk_rule("contains", "aes"), "AES256")[0] is True

    for value in ["true", "1", "yes", "enabled"]:
        assert evaluator.evaluate(_mk_rule("is_true", "ignored"), value)[0] is True

    for value in ["false", "0", "no", "disabled"]:
        assert evaluator.evaluate(_mk_rule("is_false", "ignored"), value)[0] is True

    assert evaluator.evaluate(_mk_rule("gte", "4.0"), "5.0")[0] is True
    assert evaluator.evaluate(_mk_rule("gte", "4.0"), "3.0")[0] is False

    assert evaluator.evaluate(_mk_rule("lte", "4.0"), "3.0")[0] is True
    assert evaluator.evaluate(_mk_rule("lte", "4.0"), "5.0")[0] is False

    assert evaluator.evaluate(_mk_rule("exists", "ignored"), "x")[0] is True
    assert evaluator.evaluate(_mk_rule("exists", "ignored"), None)[0] is False

    assert evaluator.evaluate(_mk_rule("not_exists", "ignored"), None)[0] is True
    assert evaluator.evaluate(_mk_rule("not_exists", "ignored"), "x")[0] is False

    passed, reason = evaluator.evaluate(_mk_rule("equals", "x"), None)
    assert passed is False
    assert reason == "key not found in agent payload"

    passed, reason = evaluator.evaluate(_mk_rule("gte", "4.0"), "abc")
    assert passed is False
    assert reason == "could not parse value as number"


def test_a24_ingest_endpoint_auth_scoping_and_payload_storage(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a24-ingest-a")
    org2 = bootstrap_org_user(client, email_prefix="a24-ingest-b")

    control1 = _create_control(client, org1["org_headers"], title="a24 ingest c1")
    control2 = _create_control(client, org2["org_headers"], title="a24 ingest c2")

    agent = _register_agent(client, org1["org_headers"], name="scanner-ingest")
    rule1 = _create_rule(client, org1["org_headers"], control_id=control1["id"], expected_config_value="true", evaluation_operator="equals")
    rule2 = _create_rule(client, org2["org_headers"], control_id=control2["id"], expected_config_value="true", evaluation_operator="equals")

    ok = _ingest(
        client,
        agent["token"],
        {
            "rule_id": rule1["id"],
            "resource_identifier": "arn:aws:s3:::bucket-a",
            "actual_config_key": "encryption.enabled",
            "actual_config_value": "true",
            "raw_payload": {"agent": "scanner", "value": "true"},
        },
    )
    assert ok["status_code"] == 200
    assert ok["json"]["passed"] is True
    assert ok["json"]["control_test_run_id"] is not None

    stored = db_session.query(TechnicalControlResult).filter_by(id=uuid.UUID(ok["json"]["result_id"])).one()
    assert stored.raw_payload == {"agent": "scanner", "value": "true"}

    ok_run = db_session.query(ControlTestRun).filter_by(id=uuid.UUID(ok["json"]["control_test_run_id"])).one()
    assert ok_run.result == "passed"

    fail = _ingest(
        client,
        agent["token"],
        {
            "rule_id": rule1["id"],
            "resource_identifier": "arn:aws:s3:::bucket-a",
            "actual_config_key": "encryption.enabled",
            "actual_config_value": "false",
            "raw_payload": {"actual": "false"},
        },
    )
    assert fail["status_code"] == 200
    assert fail["json"]["passed"] is False
    assert fail["json"]["control_test_run_id"] is not None

    run = db_session.query(ControlTestRun).filter_by(id=uuid.UUID(fail["json"]["control_test_run_id"])).one_or_none()
    assert run is not None
    assert run.result == "failed"
    assert run.control_test_definition_id == ok_run.control_test_definition_id

    wrong_org = _ingest(
        client,
        agent["token"],
        {
            "rule_id": rule2["id"],
            "actual_config_key": "encryption.enabled",
            "actual_config_value": "true",
            "raw_payload": {},
        },
    )
    assert wrong_org["status_code"] == 403

    unknown_rule = _ingest(
        client,
        agent["token"],
        {
            "rule_id": str(uuid.uuid4()),
            "actual_config_key": "encryption.enabled",
            "actual_config_value": "true",
            "raw_payload": {},
        },
    )
    assert unknown_rule["status_code"] == 404

    bad_token = client.post(
        INGEST_URL,
        headers={"Authorization": "Bearer not-a-real-token"},
        json={
            "rule_id": rule1["id"],
            "actual_config_key": "encryption.enabled",
            "actual_config_value": "true",
            "raw_payload": {},
        },
    )
    assert bad_token.status_code == 401


def test_a24_ingest_null_with_exists_operator_fails(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a24-exists")
    control = _create_control(client, org["org_headers"], title="a24 exists")
    agent = _register_agent(client, org["org_headers"], name="scanner-exists")
    rule = _create_rule(
        client,
        org["org_headers"],
        control_id=control["id"],
        name="exists-rule",
        target_resource_type="generic",
        expected_config_key="config.exists",
        expected_config_value="ignored",
        evaluation_operator="exists",
    )

    response = _ingest(
        client,
        agent["token"],
        {
            "rule_id": rule["id"],
            "actual_config_key": "config.exists",
            "actual_config_value": None,
            "raw_payload": {"config": {}},
        },
    )
    assert response["status_code"] == 200
    assert response["json"]["passed"] is False


def test_a24_rule_summary_pass_rate_and_results_filters(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a24-summary")
    control = _create_control(client, org["org_headers"], title="a24 summary ctrl")
    agent = _register_agent(client, org["org_headers"], name="scanner-summary")
    rule = _create_rule(client, org["org_headers"], control_id=control["id"], evaluation_operator="equals", expected_config_value="true")

    for i in range(8):
        actual = "true" if i < 6 else "false"
        ingested = _ingest(
            client,
            agent["token"],
            {
                "rule_id": rule["id"],
                "resource_identifier": f"resource-{i}",
                "actual_config_key": "encryption.enabled",
                "actual_config_value": actual,
                "raw_payload": {"i": i, "actual": actual},
            },
        )
        assert ingested["status_code"] == 200

    summary = client.get(f"{RULES_BASE}/{rule['id']}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_checks"] == 8
    assert body["pass_rate_7d"] == 75.0
    assert body["last_result"] in {"passed", "failed"}

    all_results = client.get(RESULTS_BASE, headers=org["org_headers"])
    assert all_results.status_code == 200
    assert len(all_results.json()) >= 8

    only_failed = client.get(RESULTS_BASE, headers=org["org_headers"], params={"passed": False})
    assert only_failed.status_code == 200
    assert len(only_failed.json()) == 2
    assert all(item["passed"] is False for item in only_failed.json())

    by_agent = client.get(RESULTS_BASE, headers=org["org_headers"], params={"agent_id": agent["id"]})
    assert by_agent.status_code == 200
    assert len(by_agent.json()) >= 8
    assert all(item["agent_id"] == agent["id"] for item in by_agent.json())


def test_a24_org_summary_failing_rules_and_empty_org(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a24-orgsum")

    empty = client.get(f"{RESULTS_BASE}/summary", headers=org["org_headers"])
    assert empty.status_code == 200
    assert empty.json()["total_rules"] == 0
    assert empty.json()["active_rules"] == 0
    assert empty.json()["checks_last_7d"] == 0
    assert empty.json()["failing_rules"] == []

    control = _create_control(client, org["org_headers"], title="a24 org summary ctrl")
    agent = _register_agent(client, org["org_headers"], name="scanner-org-summary")

    critical_rule = _create_rule(
        client,
        org["org_headers"],
        control_id=control["id"],
        name="critical-rule",
        severity="critical",
        evaluation_operator="equals",
        expected_config_value="true",
    )
    warning_rule = _create_rule(
        client,
        org["org_headers"],
        control_id=control["id"],
        name="warning-rule",
        severity="warning",
        evaluation_operator="equals",
        expected_config_value="true",
    )

    fail_critical = _ingest(
        client,
        agent["token"],
        {
            "rule_id": critical_rule["id"],
            "actual_config_key": "k",
            "actual_config_value": "false",
            "raw_payload": {"k": "false"},
        },
    )
    assert fail_critical["status_code"] == 200

    pass_warning = _ingest(
        client,
        agent["token"],
        {
            "rule_id": warning_rule["id"],
            "actual_config_key": "k",
            "actual_config_value": "true",
            "raw_payload": {"k": "true"},
        },
    )
    assert pass_warning["status_code"] == 200

    summary = client.get(f"{RESULTS_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_rules"] == 2
    assert body["active_rules"] == 2
    assert body["checks_last_7d"] == 2
    assert len(body["failing_rules"]) == 1
    assert body["failing_rules"][0]["rule_name"] == "critical-rule"


def test_a24_result_tenant_isolation_and_control_test_run_links(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a24-tenant-a")
    org2 = bootstrap_org_user(client, email_prefix="a24-tenant-b")

    control1 = _create_control(client, org1["org_headers"], title="a24 tenant c1")
    control2 = _create_control(client, org2["org_headers"], title="a24 tenant c2")

    agent1 = _register_agent(client, org1["org_headers"], name="scanner-a")
    agent2 = _register_agent(client, org2["org_headers"], name="scanner-b")

    rule1 = _create_rule(client, org1["org_headers"], control_id=control1["id"], expected_config_value="true")
    rule2 = _create_rule(client, org2["org_headers"], control_id=control2["id"], expected_config_value="true")

    passed = _ingest(
        client,
        agent1["token"],
        {
            "rule_id": rule1["id"],
            "actual_config_key": "k",
            "actual_config_value": "true",
            "raw_payload": {"k": "true"},
        },
    )
    assert passed["status_code"] == 200
    assert passed["json"]["control_test_run_id"] is not None

    failed = _ingest(
        client,
        agent1["token"],
        {
            "rule_id": rule1["id"],
            "actual_config_key": "k",
            "actual_config_value": "false",
            "raw_payload": {"k": "false"},
        },
    )
    assert failed["status_code"] == 200
    assert failed["json"]["control_test_run_id"] is not None

    org2_ingest = _ingest(
        client,
        agent2["token"],
        {
            "rule_id": rule2["id"],
            "actual_config_key": "k",
            "actual_config_value": "true",
            "raw_payload": {"k": "true"},
        },
    )
    assert org2_ingest["status_code"] == 200

    list_org1 = client.get(RESULTS_BASE, headers=org1["org_headers"])
    assert list_org1.status_code == 200
    assert all(item["organization_id"] == org1["organization_id"] for item in list_org1.json())

    list_org2 = client.get(RESULTS_BASE, headers=org2["org_headers"])
    assert list_org2.status_code == 200
    assert all(item["organization_id"] == org2["organization_id"] for item in list_org2.json())


def test_a24_ingest_updates_agent_last_seen_and_audits(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a24-audit")
    control = _create_control(client, org["org_headers"], title="a24 audit ctrl")
    agent = _register_agent(client, org["org_headers"], name="scanner-audit")
    rule = _create_rule(client, org["org_headers"], control_id=control["id"], expected_config_value="true")

    row_before = db_session.query(TechnicalControlAgent).filter_by(id=uuid.UUID(agent["id"])).one()
    assert row_before.last_seen_at is None

    result = _ingest(
        client,
        agent["token"],
        {
            "rule_id": rule["id"],
            "actual_config_key": "k",
            "actual_config_value": "false",
            "raw_payload": {"k": "false"},
        },
    )
    assert result["status_code"] == 200

    row_after = db_session.query(TechnicalControlAgent).filter_by(id=uuid.UUID(agent["id"])).one()
    assert row_after.last_seen_at is not None

    actions = {
        item.action
        for item in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    }
    assert "technical_control.agent_registered" in actions
    assert "technical_control.rule_created" in actions
    assert "technical_control.result_ingested" in actions
    assert "technical_control.result_failed" in actions
