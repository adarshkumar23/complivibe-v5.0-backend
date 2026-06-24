import uuid

from app.api.v1 import (
    compliance_contracts,
    compliance_dashboard,
    compliance_deadlines,
    compliance_policies,
    control_monitoring,
    control_monitoring_alerts,
    control_monitoring_rules,
    vendors,
)
from app.models.audit_log import AuditLog
from app.services.seed_service import PILLAR1_AUDIT_ACTION_REGISTRY
from tests.helpers.auth_org import bootstrap_org_user


def _route_keys(router) -> list[tuple[tuple[str, ...], str]]:
    rows: list[tuple[tuple[str, ...], str]] = []
    for route in router.routes:
        methods = tuple(sorted(getattr(route, "methods", set())))
        path = getattr(route, "path", "")
        rows.append((methods, path))
    return rows


def _path_order(router) -> list[str]:
    return [getattr(route, "path", "") for route in router.routes]


def _assert_before(paths: list[str], first: str, second: str) -> None:
    assert first in paths
    assert second in paths
    assert paths.index(first) < paths.index(second)


def test_phase912_contract_endpoint_returns_all_groups(client):
    org = bootstrap_org_user(client, email_prefix="p912-contract")

    response = client.get("/api/v1/compliance/contracts", headers=org["org_headers"])
    assert response.status_code == 200
    payload = response.json()

    groups = payload["contract_groups"]
    expected_groups = {
        "compliance_policies",
        "compliance_policy_versions",
        "compliance_policy_control_links",
        "vendors",
        "vendor_assessments",
        "vendor_risk_scores",
        "vendor_control_links",
        "control_monitoring_definitions",
        "control_monitoring_rules",
        "control_monitoring_alerts",
        "compliance_deadlines",
        "compliance_dashboard",
    }
    assert expected_groups.issubset(set(groups.keys()))

    for name in expected_groups:
        entry = groups[name]
        assert "endpoints" in entry
        assert "protected_response_fields" in entry
        assert "invariants" in entry


def test_phase912_route_ordering_and_no_duplicate_patterns():
    # Key family ordering checks: static/summaries before dynamic ids.
    policy_paths = _path_order(compliance_policies.router)
    _assert_before(policy_paths, "/compliance/policies/summary", "/compliance/policies/{policy_id}")

    vendor_paths = _path_order(vendors.router)
    _assert_before(vendor_paths, "/compliance/vendors/summary", "/compliance/vendors/{vendor_id}")
    _assert_before(
        vendor_paths,
        "/compliance/vendors/{vendor_id}/assessments/summary",
        "/compliance/vendors/{vendor_id}/assessments/{assessment_id}",
    )
    _assert_before(
        vendor_paths,
        "/compliance/vendors/{vendor_id}/risk-scores/latest",
        "/compliance/vendors/{vendor_id}/risk-scores/{score_id}",
    )

    deadline_paths = _path_order(compliance_deadlines.router)
    _assert_before(deadline_paths, "/compliance/deadlines/events", "/compliance/deadlines/{deadline_id}")
    _assert_before(deadline_paths, "/compliance/deadlines/summary", "/compliance/deadlines/{deadline_id}")
    _assert_before(deadline_paths, "/compliance/deadlines/evaluate-due", "/compliance/deadlines/{deadline_id}")

    monitoring_rule_paths = _path_order(control_monitoring_rules.router)
    _assert_before(monitoring_rule_paths, "/compliance/monitoring/rules/summary", "/compliance/monitoring/rules/{rule_id}")
    _assert_before(
        monitoring_rule_paths,
        "/compliance/monitoring/rules/executions",
        "/compliance/monitoring/rules/{rule_id}",
    )

    alert_paths = _path_order(control_monitoring_alerts.router)
    _assert_before(alert_paths, "/compliance/monitoring/alerts/summary", "/compliance/monitoring/alerts/{alert_id}")

    # No duplicate method+path patterns across Pillar 1 routers.
    all_routers = [
        compliance_contracts.router,
        compliance_dashboard.router,
        compliance_policies.router,
        vendors.router,
        control_monitoring.router,
        control_monitoring_rules.router,
        control_monitoring_alerts.router,
        compliance_deadlines.router,
    ]
    seen: set[tuple[tuple[str, ...], str]] = set()
    for router in all_routers:
        for key in _route_keys(router):
            assert key not in seen
            seen.add(key)


def test_phase912_contract_and_dashboard_endpoints_are_read_only_no_audit_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p912-ro")
    org_uuid = uuid.UUID(org["organization_id"])

    before_count = db_session.query(AuditLog).filter(AuditLog.organization_id == org_uuid).count()

    get_contracts = client.get("/api/v1/compliance/contracts", headers=org["org_headers"])
    assert get_contracts.status_code == 200

    get_dashboard = client.get("/api/v1/compliance/dashboard/posture-summary", headers=org["org_headers"])
    assert get_dashboard.status_code == 200

    post_contracts = client.post("/api/v1/compliance/contracts", headers=org["org_headers"], json={})
    assert post_contracts.status_code == 405

    post_dashboard = client.post("/api/v1/compliance/dashboard/posture-summary", headers=org["org_headers"], json={})
    assert post_dashboard.status_code == 405

    after_count = db_session.query(AuditLog).filter(AuditLog.organization_id == org_uuid).count()
    assert after_count == before_count


def test_phase912_seed_registry_includes_all_phase90_to_911_audit_actions():
    expected_actions = {
        "compliance_policy.created",
        "compliance_policy.updated",
        "compliance_policy.archived",
        "compliance_policy_version.created",
        "compliance_policy_version.submitted",
        "compliance_policy_approval.requested",
        "compliance_policy_approval.approved",
        "compliance_policy_approval.rejected",
        "compliance_policy_approval.cancelled",
        "compliance_policy.control_linked",
        "compliance_policy.control_unlinked",
        "vendor.created",
        "vendor.updated",
        "vendor.archived",
        "vendor_assessment.created",
        "vendor_assessment.started",
        "vendor_assessment.completed",
        "vendor_assessment.cancelled",
        "vendor_assessment_question.answered",
        "vendor_risk_score.created",
        "vendor.control_linked",
        "vendor.control_unlinked",
        "control_monitoring_definition.created",
        "control_monitoring_definition.updated",
        "control_monitoring_definition.archived",
        "control_monitoring_result.recorded",
        "control_monitoring_rule.created",
        "control_monitoring_rule.updated",
        "control_monitoring_rule.archived",
        "control_monitoring_rule.evaluated",
        "control_monitoring_alert.created",
        "control_monitoring_alert.acknowledged",
        "control_monitoring_alert.resolved",
        "control_monitoring_alert.dismissed",
        "control_monitoring_alert.assigned",
        "compliance_deadline.created",
        "compliance_deadline.updated",
        "compliance_deadline.completed",
        "compliance_deadline.waived",
        "compliance_deadline.cancelled",
        "compliance_deadline.evaluated",
    }

    flattened = {action for group in PILLAR1_AUDIT_ACTION_REGISTRY.values() for action in group}
    assert expected_actions.issubset(flattened)
