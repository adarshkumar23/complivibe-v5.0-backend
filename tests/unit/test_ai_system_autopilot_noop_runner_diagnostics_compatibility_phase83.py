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
NOOP_COMPATIBILITY_POLICY = "/api/v1/ai-governance/autopilot/noop-runner/reports/compatibility-policy"
NOOP_BOUNDED_EXPORT = "/api/v1/ai-governance/autopilot/noop-runner/reports/bounded-export"
NOOP_CHECKSUM = "/api/v1/ai-governance/autopilot/noop-runner/reports/checksum"


def _assert_shape_keys(payload: dict, expected_keys: set[str]) -> None:
    assert expected_keys.issubset(set(payload.keys()))


def test_phase83_noop_runner_compatibility_route_ordering_static_before_dynamic():
    paths = _phase8_router_paths_in_order()
    assert "/autopilot/noop-runner/reports/compatibility-policy" in paths
    assert "/autopilot/noop-runner/events/{event_id}" in paths
    assert paths.index("/autopilot/noop-runner/reports/compatibility-policy") < paths.index(
        "/autopilot/noop-runner/events/{event_id}"
    )


def test_phase83_noop_runner_diagnostics_compatibility_golden_shapes_and_safety(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p83-compat")
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

    phase8 = client.get(PHASE8_CONTRACT, headers=headers)
    assert phase8.status_code == 200
    p8 = phase8.json()
    _assert_shape_keys(
        p8,
        {
            "phase",
            "execution_allowed",
            "real_runner_present",
            "job_queue_present",
            "noop_runner_only",
            "groups",
            "caveat",
        },
    )
    assert p8["phase"] == "phase8"
    assert p8["execution_allowed"] is False
    assert p8["real_runner_present"] is False
    assert p8["job_queue_present"] is False
    assert p8["noop_runner_only"] is True
    group_keys = {group["group_key"] for group in p8["groups"]}
    assert "governance_noop_runner_events" in group_keys
    assert "governance_noop_runner_observability" in group_keys
    assert "governance_noop_runner_operator_diagnostics" in group_keys
    assert "governance_noop_runner_diagnostics_compatibility" in group_keys

    contract_resp = client.get(NOOP_REPORT_CONTRACT, headers=headers)
    assert contract_resp.status_code == 200
    contract_body = contract_resp.json()
    _assert_shape_keys(
        contract_body,
        {
            "report_schema_version",
            "supported_report_types",
            "common_metadata_fields",
            "bounded_export_limits",
            "safety_flags",
            "compatibility_policy_version",
            "caveat",
        },
    )
    assert contract_body["report_schema_version"] == "noop_runner_reports.v1"
    assert contract_body["compatibility_policy_version"] == "noop_runner_compatibility.v1"
    assert contract_body["additive_fields_allowed"] is True
    assert contract_body["breaking_changes_require_new_schema_version"] is True

    manifest_resp = client.get(NOOP_MANIFEST, headers=headers)
    assert manifest_resp.status_code == 200
    manifest_body = manifest_resp.json()
    _assert_shape_keys(
        manifest_body,
        {
            "report_schema_version",
            "available_reports",
            "endpoint_map",
            "safety_flags",
            "known_limitations",
            "compatibility_policy_version",
            "caveat",
        },
    )
    assert manifest_body["report_schema_version"] == "noop_runner_reports.v1"
    assert manifest_body["compatibility_policy_version"] == "noop_runner_compatibility.v1"

    export_ledger = client.get(
        NOOP_BOUNDED_EXPORT,
        headers=headers,
        params={"report_type": "ledger", "limit": 2, "offset": 0},
    )
    assert export_ledger.status_code == 200
    el = export_ledger.json()
    _assert_shape_keys(
        el,
        {
            "report_schema_version",
            "report_type",
            "generated_at",
            "query",
            "query_hash",
            "result_hash",
            "limit",
            "offset",
            "truncated",
            "next_offset",
            "row_count",
            "safety_flags",
            "caveat",
            "rows",
        },
    )
    assert el["report_type"] == "ledger"
    assert isinstance(el["rows"], list)
    assert el["execution_allowed"] is False
    assert el["real_runner_present"] is False
    assert el["job_queue_present"] is False
    assert el["noop_runner_only"] is True

    export_agg = client.get(
        NOOP_BOUNDED_EXPORT,
        headers=headers,
        params={"report_type": "timeline", "limit": 30, "offset": 0},
    )
    assert export_agg.status_code == 200
    ea = export_agg.json()
    _assert_shape_keys(
        ea,
        {
            "report_schema_version",
            "report_type",
            "generated_at",
            "query_hash",
            "result_hash",
            "report_payload",
            "safety_flags",
            "caveat",
        },
    )
    assert ea["report_type"] == "timeline"
    assert isinstance(ea["report_payload"], dict)

    checksum_resp = client.get(
        NOOP_CHECKSUM,
        headers=headers,
        params={"report_type": "ledger", "limit": 2, "offset": 0},
    )
    assert checksum_resp.status_code == 200
    checksum_body = checksum_resp.json()
    _assert_shape_keys(
        checksum_body,
        {
            "report_type",
            "query_hash",
            "result_hash",
            "row_count",
            "generated_at",
            "caveat",
        },
    )

    checksum_resp_2 = client.get(
        NOOP_CHECKSUM,
        headers=headers,
        params={"report_type": "ledger", "limit": 2, "offset": 0},
    )
    assert checksum_resp_2.status_code == 200
    checksum_body_2 = checksum_resp_2.json()
    assert checksum_body["query_hash"] == checksum_body_2["query_hash"]
    assert checksum_body["result_hash"] == checksum_body_2["result_hash"]

    compatibility_resp = client.get(NOOP_COMPATIBILITY_POLICY, headers=headers)
    assert compatibility_resp.status_code == 200
    cp = compatibility_resp.json()
    _assert_shape_keys(
        cp,
        {
            "report_schema_version",
            "compatibility_policy_version",
            "additive_fields_allowed",
            "breaking_changes_require_new_schema_version",
            "deprecated_fields_policy",
            "stable_endpoint_families",
            "safety_flags",
            "caveat",
        },
    )
    assert cp["report_schema_version"] == "noop_runner_reports.v1"
    assert cp["compatibility_policy_version"] == "noop_runner_compatibility.v1"
    assert cp["additive_fields_allowed"] is True
    assert cp["breaking_changes_require_new_schema_version"] is True
    assert cp["minimum_supported_schema_version"] == "noop_runner_reports.v1"
    assert cp["current_supported_schema_version"] == "noop_runner_reports.v1"
    assert "no_op_runner_events" in cp["stable_endpoint_families"]
    assert cp["safety_flags"]["execution_allowed"] is False

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
