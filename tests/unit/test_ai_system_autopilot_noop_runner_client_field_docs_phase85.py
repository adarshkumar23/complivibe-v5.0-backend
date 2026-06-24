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
NOOP_CLIENT_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/client-contract"
NOOP_FILTER_OPTIONS = "/api/v1/ai-governance/autopilot/noop-runner/reports/filter-options"
NOOP_PAGINATION_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/pagination-contract"
NOOP_FIELD_DOCS = "/api/v1/ai-governance/autopilot/noop-runner/reports/field-docs"
NOOP_DISPLAY_METADATA = "/api/v1/ai-governance/autopilot/noop-runner/reports/display-metadata"
NOOP_LOCALIZATION_MAP = "/api/v1/ai-governance/autopilot/noop-runner/reports/localization-map"
NOOP_CLIENT_HINTS = "/api/v1/ai-governance/autopilot/noop-runner/reports/client-hints"


def _assert_shape_keys(payload: dict, expected_keys: set[str]) -> None:
    assert expected_keys.issubset(set(payload.keys()))


def test_phase85_noop_runner_client_field_docs_route_ordering_static_before_dynamic():
    paths = _phase8_router_paths_in_order()
    assert "/autopilot/noop-runner/reports/field-docs" in paths
    assert "/autopilot/noop-runner/reports/display-metadata" in paths
    assert "/autopilot/noop-runner/reports/localization-map" in paths
    assert "/autopilot/noop-runner/reports/client-hints" in paths
    assert "/autopilot/noop-runner/reports/client-contract" in paths
    assert "/autopilot/noop-runner/events/{event_id}" in paths
    assert paths.index("/autopilot/noop-runner/reports/field-docs") < paths.index("/autopilot/noop-runner/events/{event_id}")
    assert paths.index("/autopilot/noop-runner/reports/display-metadata") < paths.index(
        "/autopilot/noop-runner/events/{event_id}"
    )
    assert paths.index("/autopilot/noop-runner/reports/localization-map") < paths.index(
        "/autopilot/noop-runner/events/{event_id}"
    )
    assert paths.index("/autopilot/noop-runner/reports/client-hints") < paths.index(
        "/autopilot/noop-runner/events/{event_id}"
    )
    assert paths.index("/autopilot/noop-runner/reports/client-contract") < paths.index(
        "/autopilot/noop-runner/events/{event_id}"
    )


def test_phase85_noop_runner_client_field_docs_and_safety(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p85-fielddocs")
    headers = org["org_headers"]
    _seed_phase81_events(client, headers)

    org_id = uuid.UUID(org["organization_id"])
    before_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == org_id
            )
        ).scalar_one()
    )
    before_audit = int(db_session.execute(select(func.count(AuditLog.id)).where(AuditLog.organization_id == org_id)).scalar_one())
    before_signals = {
        row.id: row.status
        for row in db_session.execute(select(GovernanceSignal).where(GovernanceSignal.organization_id == org_id)).scalars()
    }
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    reports_dir = Path("reports")
    before_report_files = (
        sorted([str(path.relative_to(reports_dir)) for path in reports_dir.glob("**/*") if path.is_file()])
        if reports_dir.exists()
        else []
    )

    field_docs_resp = client.get(NOOP_FIELD_DOCS, headers=headers, params={"report_type": "ledger"})
    assert field_docs_resp.status_code == 200
    fd = field_docs_resp.json()
    _assert_shape_keys(
        fd,
        {
            "field_docs_version",
            "report_schema_version",
            "compatibility_policy_version",
            "report_type",
            "field_docs",
            "safety_flags",
            "caveat",
        },
    )
    assert fd["field_docs_version"] == "noop_runner_field_docs.v1"
    assert fd["report_schema_version"] == "noop_runner_reports.v1"
    assert fd["compatibility_policy_version"] == "noop_runner_compatibility.v1"
    assert fd["report_type"] == "ledger"
    assert isinstance(fd["field_docs"], list)
    assert len(fd["field_docs"]) >= 1
    required_doc_keys = {
        "field_name",
        "label",
        "description",
        "data_type",
        "required",
        "nullable",
        "filterable",
        "sortable",
        "stable_since",
        "deprecated",
        "replacement_field",
        "display_hint",
        "localization_key",
    }
    for item in fd["field_docs"]:
        assert required_doc_keys.issubset(set(item.keys()))

    display_metadata_resp = client.get(NOOP_DISPLAY_METADATA, headers=headers, params={"report_type": "ledger"})
    assert display_metadata_resp.status_code == 200
    dm = display_metadata_resp.json()
    _assert_shape_keys(
        dm,
        {
            "display_metadata_version",
            "report_schema_version",
            "report_type",
            "table_columns",
            "default_sort",
            "recommended_grouping",
            "empty_state",
            "severity_mapping",
            "status_badges",
            "safety_flags",
            "caveat",
        },
    )
    assert dm["display_metadata_version"] == "noop_runner_display_metadata.v1"
    assert dm["report_type"] == "ledger"
    assert "event_status" in dm["table_columns"]
    assert dm["default_sort"]["field"] == "created_at"
    assert dm["default_sort"]["direction"] == "desc"
    assert {"logged", "blocked", "archived"}.issubset(set(dm["status_badges"].keys()))

    localization_map_resp = client.get(NOOP_LOCALIZATION_MAP, headers=headers)
    assert localization_map_resp.status_code == 200
    lm = localization_map_resp.json()
    _assert_shape_keys(
        lm,
        {
            "localization_map_version",
            "default_locale",
            "supported_locales",
            "keys",
            "safety_flags",
            "caveat",
        },
    )
    assert lm["localization_map_version"] == "noop_runner_localization_map.v1"
    assert lm["default_locale"] == "en"
    assert lm["supported_locales"] == ["en"]
    assert isinstance(lm["keys"], dict)
    assert len(lm["keys"]) >= 1
    assert all(isinstance(v, str) and len(v) >= 1 for v in lm["keys"].values())
    assert all(ord(ch) < 128 for value in lm["keys"].values() for ch in value)

    client_hints_resp = client.get(NOOP_CLIENT_HINTS, headers=headers)
    assert client_hints_resp.status_code == 200
    ch = client_hints_resp.json()
    _assert_shape_keys(
        ch,
        {
            "client_hints_version",
            "recommended_refresh_seconds",
            "cache_policy",
            "pagination_hints",
            "filter_hints",
            "empty_state_hints",
            "safety_flags",
            "caveat",
        },
    )
    assert ch["client_hints_version"] == "noop_runner_client_hints.v1"
    assert ch["recommended_refresh_seconds"] == 60
    assert ch["pagination_hints"]["style"] == "offset_limit"
    assert ch["pagination_hints"]["max_limit"] == 500

    client_contract_resp = client.get(NOOP_CLIENT_CONTRACT, headers=headers)
    assert client_contract_resp.status_code == 200
    cc = client_contract_resp.json()
    assert cc["field_docs_endpoint"] == NOOP_FIELD_DOCS
    assert cc["display_metadata_endpoint"] == NOOP_DISPLAY_METADATA
    assert cc["localization_map_endpoint"] == NOOP_LOCALIZATION_MAP
    assert cc["client_hints_endpoint"] == NOOP_CLIENT_HINTS

    filter_options_resp = client.get(NOOP_FILTER_OPTIONS, headers=headers)
    assert filter_options_resp.status_code == 200
    fo = filter_options_resp.json()
    assert fo["field_docs_endpoint"] == NOOP_FIELD_DOCS
    assert fo["display_metadata_endpoint"] == NOOP_DISPLAY_METADATA
    assert fo["client_hints_endpoint"] == NOOP_CLIENT_HINTS

    pagination_contract_resp = client.get(NOOP_PAGINATION_CONTRACT, headers=headers)
    assert pagination_contract_resp.status_code == 200
    pc = pagination_contract_resp.json()
    assert pc["field_docs_endpoint"] == NOOP_FIELD_DOCS
    assert pc["display_metadata_endpoint"] == NOOP_DISPLAY_METADATA
    assert pc["client_hints_endpoint"] == NOOP_CLIENT_HINTS

    phase8 = client.get(PHASE8_CONTRACT, headers=headers)
    assert phase8.status_code == 200
    p8 = phase8.json()
    assert p8["execution_allowed"] is False
    assert p8["real_runner_present"] is False
    assert p8["job_queue_present"] is False
    assert p8["noop_runner_only"] is True
    assert "governance_noop_runner_client_field_docs" in {group["group_key"] for group in p8["groups"]}

    after_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == org_id
            )
        ).scalar_one()
    )
    after_audit = int(db_session.execute(select(func.count(AuditLog.id)).where(AuditLog.organization_id == org_id)).scalar_one())
    after_signals = {
        row.id: row.status
        for row in db_session.execute(select(GovernanceSignal).where(GovernanceSignal.organization_id == org_id)).scalars()
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
