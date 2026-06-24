import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_noop_runner_event import GovernanceAutopilotNoopRunnerEvent
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_noop_runner_events_phase80 import _phase8_router_paths_in_order
from tests.unit.test_ai_system_autopilot_noop_runner_observability_phase81 import _seed_phase81_events

PHASE8_CONTRACT = "/api/v1/ai-governance/contracts/phase8"
NOOP_REPORT_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/contract"
NOOP_MANIFEST = "/api/v1/ai-governance/autopilot/noop-runner/reports/diagnostics-manifest"
NOOP_CLIENT_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/client-contract"
NOOP_FILTER_OPTIONS = "/api/v1/ai-governance/autopilot/noop-runner/reports/filter-options"
NOOP_PAGINATION_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/pagination-contract"
NOOP_BOUNDED_EXPORT = "/api/v1/ai-governance/autopilot/noop-runner/reports/bounded-export"


def _assert_shape_keys(payload: dict, expected_keys: set[str]) -> None:
    assert expected_keys.issubset(set(payload.keys()))


def test_phase84_noop_runner_client_integration_route_ordering_static_before_dynamic():
    paths = _phase8_router_paths_in_order()
    assert "/autopilot/noop-runner/reports/client-contract" in paths
    assert "/autopilot/noop-runner/reports/filter-options" in paths
    assert "/autopilot/noop-runner/reports/pagination-contract" in paths
    assert "/autopilot/noop-runner/events/{event_id}" in paths
    assert paths.index("/autopilot/noop-runner/reports/client-contract") < paths.index("/autopilot/noop-runner/events/{event_id}")
    assert paths.index("/autopilot/noop-runner/reports/filter-options") < paths.index("/autopilot/noop-runner/events/{event_id}")
    assert paths.index("/autopilot/noop-runner/reports/pagination-contract") < paths.index("/autopilot/noop-runner/events/{event_id}")


def test_phase84_noop_runner_client_integration_contracts_and_safety(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p84-client")
    headers = org["org_headers"]
    _seed_phase81_events(client, headers)

    before_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    before_audit = int(
        db_session.execute(select(func.count(AuditLog.id)).where(AuditLog.organization_id == uuid.UUID(org["organization_id"]))).scalar_one()
    )
    before_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    reports_dir = Path("reports")
    before_report_files = (
        sorted([str(path.relative_to(reports_dir)) for path in reports_dir.glob("**/*") if path.is_file()])
        if reports_dir.exists()
        else []
    )

    client_contract_resp = client.get(NOOP_CLIENT_CONTRACT, headers=headers)
    assert client_contract_resp.status_code == 200
    cc = client_contract_resp.json()
    _assert_shape_keys(
        cc,
        {
            "client_contract_version",
            "report_schema_version",
            "compatibility_policy_version",
            "stable_endpoint_families",
            "supported_filters_by_endpoint",
            "pagination_contract",
            "enum_values",
            "default_limits",
            "max_limits",
            "safety_flags",
            "caveat",
        },
    )
    assert cc["client_contract_version"] == "noop_runner_client_contract.v1"
    assert cc["report_schema_version"] == "noop_runner_reports.v1"
    assert cc["compatibility_policy_version"] == "noop_runner_compatibility.v1"
    assert "ledger" in cc["supported_filters_by_endpoint"]
    assert "report_types" in cc["enum_values"]
    assert cc["safety_flags"]["execution_allowed"] is False
    assert cc["safety_flags"]["real_runner_present"] is False
    assert cc["safety_flags"]["job_queue_present"] is False
    assert cc["safety_flags"]["noop_runner_only"] is True

    filter_options_resp = client.get(NOOP_FILTER_OPTIONS, headers=headers)
    assert filter_options_resp.status_code == 200
    fo = filter_options_resp.json()
    _assert_shape_keys(
        fo,
        {
            "report_schema_version",
            "supported_report_types",
            "supported_event_statuses",
            "supported_event_types",
            "supported_boolean_filters",
            "supported_id_filters",
            "supported_pagination_params",
            "default_values",
            "bounds",
            "safety_flags",
            "caveat",
        },
    )
    assert fo["report_schema_version"] == "noop_runner_reports.v1"
    assert sorted(fo["supported_event_statuses"]) == ["archived", "blocked", "logged"]
    assert fo["supported_event_types"] == ["noop_runner_control_plane_check"]
    assert "limit" in fo["supported_pagination_params"]
    assert fo["default_values"]["limit"] == 100
    assert fo["bounds"]["limit"]["max"] == 500

    pagination_contract_resp = client.get(NOOP_PAGINATION_CONTRACT, headers=headers)
    assert pagination_contract_resp.status_code == 200
    pc = pagination_contract_resp.json()
    _assert_shape_keys(
        pc,
        {
            "pagination_contract_version",
            "supported_style",
            "default_limit",
            "max_limit",
            "offset_base",
            "response_fields",
            "truncation_behavior",
            "caveat",
        },
    )
    assert pc["pagination_contract_version"] == "noop_runner_pagination.v1"
    assert pc["supported_style"] == "offset_limit"
    assert pc["default_limit"] == 100
    assert pc["max_limit"] == 500
    assert pc["offset_base"] == 0

    export_ledger = client.get(
        NOOP_BOUNDED_EXPORT,
        headers=headers,
        params={"report_type": "ledger", "limit": 2, "offset": 0},
    )
    assert export_ledger.status_code == 200
    el = export_ledger.json()
    assert el["limit"] == 2
    assert el["offset"] == 0
    assert isinstance(el["truncated"], bool)
    assert isinstance(el["row_count"], int)
    _assert_shape_keys(
        el["pagination"],
        {
            "limit",
            "offset",
            "truncated",
            "next_offset",
            "row_count",
            "max_limit",
            "pagination_contract_version",
        },
    )
    assert el["pagination"]["pagination_contract_version"] == "noop_runner_pagination.v1"
    assert el["pagination"]["max_limit"] == 500

    reports_contract = client.get(NOOP_REPORT_CONTRACT, headers=headers)
    assert reports_contract.status_code == 200
    rc = reports_contract.json()
    assert rc["filter_options_endpoint"] == NOOP_FILTER_OPTIONS
    assert rc["pagination_contract_endpoint"] == NOOP_PAGINATION_CONTRACT
    assert rc["client_contract_endpoint"] == NOOP_CLIENT_CONTRACT

    manifest = client.get(NOOP_MANIFEST, headers=headers)
    assert manifest.status_code == 200
    mf = manifest.json()
    assert mf["filter_options_endpoint"] == NOOP_FILTER_OPTIONS
    assert mf["pagination_contract_endpoint"] == NOOP_PAGINATION_CONTRACT
    assert mf["client_contract_endpoint"] == NOOP_CLIENT_CONTRACT

    phase8 = client.get(PHASE8_CONTRACT, headers=headers)
    assert phase8.status_code == 200
    p8 = phase8.json()
    assert p8["execution_allowed"] is False
    assert p8["real_runner_present"] is False
    assert p8["job_queue_present"] is False
    assert p8["noop_runner_only"] is True
    assert "governance_noop_runner_client_integration" in {group["group_key"] for group in p8["groups"]}

    after_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    after_audit = int(
        db_session.execute(select(func.count(AuditLog.id)).where(AuditLog.organization_id == uuid.UUID(org["organization_id"]))).scalar_one()
    )
    after_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    after_report_files = (
        sorted([str(path.relative_to(reports_dir)) for path in reports_dir.glob("**/*") if path.is_file()])
        if reports_dir.exists()
        else []
    )

    assert after_rows == before_rows
    assert after_audit == before_audit
    assert after_signals == before_signals
    assert after_tasks == before_tasks
    assert after_reviews == before_reviews
    assert after_report_files == before_report_files
