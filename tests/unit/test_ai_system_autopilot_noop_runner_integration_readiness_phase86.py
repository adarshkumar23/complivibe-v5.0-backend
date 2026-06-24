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
NOOP_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/contract"
RUNNER_HANDSHAKES = "/api/v1/ai-governance/autopilot/runner-handshakes"
NOOP_EVENTS = "/api/v1/ai-governance/autopilot/noop-runner/events"
NOOP_LEDGER = "/api/v1/ai-governance/autopilot/noop-runner/ledger"
NOOP_TIMELINE = "/api/v1/ai-governance/autopilot/noop-runner/reports/timeline"
NOOP_BLOCKERS = "/api/v1/ai-governance/autopilot/noop-runner/reports/blockers"
NOOP_READINESS = "/api/v1/ai-governance/autopilot/noop-runner/reports/readiness"
NOOP_IDEMPOTENCY = "/api/v1/ai-governance/autopilot/noop-runner/reports/idempotency"
NOOP_HEALTH = "/api/v1/ai-governance/autopilot/noop-runner/reports/control-plane-health"
NOOP_REPORT_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/contract"
NOOP_MANIFEST = "/api/v1/ai-governance/autopilot/noop-runner/reports/diagnostics-manifest"
NOOP_BOUNDED_EXPORT = "/api/v1/ai-governance/autopilot/noop-runner/reports/bounded-export"
NOOP_CHECKSUM = "/api/v1/ai-governance/autopilot/noop-runner/reports/checksum"
NOOP_COMPATIBILITY = "/api/v1/ai-governance/autopilot/noop-runner/reports/compatibility-policy"
NOOP_CLIENT_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/client-contract"
NOOP_FILTER_OPTIONS = "/api/v1/ai-governance/autopilot/noop-runner/reports/filter-options"
NOOP_PAGINATION_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/pagination-contract"
NOOP_FIELD_DOCS = "/api/v1/ai-governance/autopilot/noop-runner/reports/field-docs"
NOOP_DISPLAY_METADATA = "/api/v1/ai-governance/autopilot/noop-runner/reports/display-metadata"
NOOP_LOCALIZATION_MAP = "/api/v1/ai-governance/autopilot/noop-runner/reports/localization-map"
NOOP_CLIENT_HINTS = "/api/v1/ai-governance/autopilot/noop-runner/reports/client-hints"


def _assert_has_keys(payload: dict, required_keys: set[str]) -> None:
    assert required_keys.issubset(set(payload.keys()))


def test_phase86_noop_runner_endpoint_inventory_and_route_ordering():
    paths = _phase8_router_paths_in_order()

    expected_paths = {
        "/contracts/phase8",
        "/autopilot/noop-runner/contract",
        "/autopilot/runner-handshakes/{handshake_id}/noop-runner/preview",
        "/autopilot/runner-handshakes/{handshake_id}/noop-runner/events",
        "/autopilot/noop-runner/events",
        "/autopilot/noop-runner/events/{event_id}",
        "/autopilot/noop-runner/events/{event_id}/verify",
        "/autopilot/noop-runner/events/{event_id}/archive",
        "/autopilot/noop-runner/events/summary",
        "/autopilot/noop-runner/ledger",
        "/autopilot/noop-runner/reports/timeline",
        "/autopilot/noop-runner/reports/blockers",
        "/autopilot/noop-runner/reports/readiness",
        "/autopilot/noop-runner/reports/idempotency",
        "/autopilot/noop-runner/reports/control-plane-health",
        "/autopilot/noop-runner/reports/contract",
        "/autopilot/noop-runner/reports/diagnostics-manifest",
        "/autopilot/noop-runner/reports/bounded-export",
        "/autopilot/noop-runner/reports/checksum",
        "/autopilot/noop-runner/reports/compatibility-policy",
        "/autopilot/noop-runner/reports/client-contract",
        "/autopilot/noop-runner/reports/filter-options",
        "/autopilot/noop-runner/reports/pagination-contract",
        "/autopilot/noop-runner/reports/field-docs",
        "/autopilot/noop-runner/reports/display-metadata",
        "/autopilot/noop-runner/reports/localization-map",
        "/autopilot/noop-runner/reports/client-hints",
    }
    assert expected_paths.issubset(set(paths))

    event_detail = "/autopilot/noop-runner/events/{event_id}"
    assert paths.index("/autopilot/noop-runner/events/summary") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/contract") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/contract") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/diagnostics-manifest") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/bounded-export") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/checksum") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/compatibility-policy") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/client-contract") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/filter-options") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/pagination-contract") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/field-docs") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/display-metadata") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/localization-map") < paths.index(event_detail)
    assert paths.index("/autopilot/noop-runner/reports/client-hints") < paths.index(event_detail)


def test_phase86_noop_runner_integration_readiness_lint_and_boundaries(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p86-readiness")
    headers = org["org_headers"]
    seeded = _seed_phase81_events(client, headers)

    org_id = uuid.UUID(org["organization_id"])

    reports_dir = Path("reports")
    before_report_files = (
        sorted(str(path.relative_to(reports_dir)) for path in reports_dir.glob("**/*") if path.is_file())
        if reports_dir.exists()
        else []
    )

    before_event_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == org_id
            )
        ).scalar_one()
    )
    before_event_statuses = {
        row.id: row.event_status
        for row in db_session.execute(
            select(GovernanceAutopilotNoopRunnerEvent).where(GovernanceAutopilotNoopRunnerEvent.organization_id == org_id)
        ).scalars()
    }
    before_audit_rows = int(
        db_session.execute(select(func.count(AuditLog.id)).where(AuditLog.organization_id == org_id)).scalar_one()
    )
    before_signals = {
        row.id: row.status
        for row in db_session.execute(select(GovernanceSignal).where(GovernanceSignal.organization_id == org_id)).scalars()
    }
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())

    # Endpoint inventory reachability + response-shape lint for read-only surfaces.
    phase8 = client.get(PHASE8_CONTRACT, headers=headers)
    assert phase8.status_code == 200
    p8 = phase8.json()
    _assert_has_keys(
        p8,
        {
            "phase",
            "status",
            "group_count",
            "groups",
            "execution_allowed",
            "real_runner_present",
            "job_queue_present",
            "noop_runner_only",
            "caveat",
        },
    )
    assert p8["execution_allowed"] is False
    assert p8["real_runner_present"] is False
    assert p8["job_queue_present"] is False
    assert p8["noop_runner_only"] is True
    group_keys = {group["group_key"] for group in p8["groups"]}
    expected_group_keys = {
        "governance_noop_runner_events",
        "governance_noop_runner_observability",
        "governance_noop_runner_operator_diagnostics",
        "governance_noop_runner_diagnostics_compatibility",
        "governance_noop_runner_client_integration",
        "governance_noop_runner_client_field_docs",
    }
    assert expected_group_keys.issubset(group_keys)
    for group in p8["groups"]:
        _assert_has_keys(
            group,
            {
                "group_key",
                "title",
                "description",
                "route_prefix",
                "critical_endpoints",
                "endpoints",
                "response_contract_fields",
                "protected_fields",
                "read_write_semantics",
                "invariants",
                "non_execution_guarantee",
                "no_legal_regulatory_determination",
                "caveats",
            },
        )
        assert len(group["critical_endpoints"]) >= 1
        assert len(group["response_contract_fields"]) >= 1
        assert len(group["read_write_semantics"]) >= 1
        assert len(group["caveats"]) >= 1
        non_execution = group["non_execution_guarantee"].lower()
        assert "non-executing" in non_execution
        assert ("does not execute" in non_execution) or ("does not run automation" in non_execution)
        assert "does not make legal" in group["no_legal_regulatory_determination"].lower()

    noop_contract = client.get(NOOP_CONTRACT, headers=headers)
    assert noop_contract.status_code == 200
    _assert_has_keys(noop_contract.json(), {"noop_only", "dry_run", "execution_allowed", "caveat"})

    preview = client.post(
        f"{RUNNER_HANDSHAKES}/{seeded['ready_handshake_id']}/noop-runner/preview",
        headers=headers,
        json={},
    )
    assert preview.status_code == 200
    _assert_has_keys(
        preview.json(),
        {
            "would_log_event",
            "proposed_event_status",
            "event_payload_json",
            "noop_result_json",
            "blocked_reasons",
            "idempotency_key",
            "caveat",
        },
    )

    events_list = client.get(NOOP_EVENTS, headers=headers)
    assert events_list.status_code == 200
    assert isinstance(events_list.json(), list)
    assert len(events_list.json()) >= 1

    detail = client.get(f"{NOOP_EVENTS}/{seeded['logged_event_id']}", headers=headers)
    assert detail.status_code == 200
    _assert_has_keys(detail.json(), {"event_id", "event_status", "event_type", "event_sha256", "caveat"})

    summary = client.get(f"{NOOP_EVENTS}/summary", headers=headers)
    assert summary.status_code == 200
    _assert_has_keys(
        summary.json(),
        {
            "total_events",
            "by_status",
            "logged_count",
            "blocked_count",
            "archived_count",
            "latest_event_at",
            "caveat",
        },
    )

    verify_event = client.post(f"{NOOP_EVENTS}/{seeded['logged_event_id']}/verify", headers=headers, json={})
    assert verify_event.status_code == 200
    _assert_has_keys(verify_event.json(), {"valid", "validation_errors", "caveat"})

    ledger = client.get(NOOP_LEDGER, headers=headers)
    assert ledger.status_code == 200
    assert isinstance(ledger.json(), list)
    assert len(ledger.json()) >= 1

    timeline = client.get(NOOP_TIMELINE, headers=headers)
    assert timeline.status_code == 200
    _assert_has_keys(timeline.json(), {"report_schema_version", "generated_at", "timeline_buckets", "caveat"})

    blockers = client.get(NOOP_BLOCKERS, headers=headers)
    assert blockers.status_code == 200
    _assert_has_keys(
        blockers.json(),
        {
            "report_schema_version",
            "generated_at",
            "total_blocked_events",
            "blocker_counts",
            "top_blockers",
            "affected_execution_intents",
            "caveat",
        },
    )

    readiness = client.get(NOOP_READINESS, headers=headers)
    assert readiness.status_code == 200
    _assert_has_keys(
        readiness.json(),
        {
            "report_schema_version",
            "generated_at",
            "ready_handshake_count",
            "no_op_logged_count",
            "blocked_event_count",
            "no_event_for_ready_handshake_count",
            "caveat",
        },
    )

    idempotency = client.get(NOOP_IDEMPOTENCY, headers=headers)
    assert idempotency.status_code == 200
    _assert_has_keys(
        idempotency.json(),
        {
            "report_schema_version",
            "generated_at",
            "total_events",
            "unique_idempotency_key_count",
            "duplicate_key_attempts_inferred_count",
            "active_duplicate_records_count",
            "idempotency_keys_with_multiple_records",
            "caveat",
        },
    )

    health = client.get(NOOP_HEALTH, headers=headers)
    assert health.status_code == 200
    h = health.json()
    _assert_has_keys(
        h,
        {
            "report_schema_version",
            "generated_at",
            "execution_allowed",
            "real_runner_present",
            "job_queue_present",
            "noop_runner_only",
            "external_side_effects_enabled",
            "health_status",
            "health_reasons",
            "caveat",
        },
    )
    assert h["execution_allowed"] is False
    assert h["real_runner_present"] is False
    assert h["job_queue_present"] is False
    assert h["noop_runner_only"] is True

    reports_contract = client.get(NOOP_REPORT_CONTRACT, headers=headers)
    assert reports_contract.status_code == 200
    rc = reports_contract.json()
    _assert_has_keys(
        rc,
        {
            "report_schema_version",
            "supported_report_types",
            "common_metadata_fields",
            "bounded_export_limits",
            "safety_flags",
            "compatibility_policy_version",
            "filter_options_endpoint",
            "pagination_contract_endpoint",
            "client_contract_endpoint",
            "field_docs_endpoint",
            "display_metadata_endpoint",
            "localization_map_endpoint",
            "client_hints_endpoint",
            "caveat",
        },
    )

    manifest = client.get(NOOP_MANIFEST, headers=headers)
    assert manifest.status_code == 200
    mf = manifest.json()
    _assert_has_keys(
        mf,
        {
            "report_schema_version",
            "available_reports",
            "endpoint_map",
            "safety_flags",
            "known_limitations",
            "compatibility_policy_version",
            "filter_options_endpoint",
            "pagination_contract_endpoint",
            "client_contract_endpoint",
            "field_docs_endpoint",
            "display_metadata_endpoint",
            "localization_map_endpoint",
            "client_hints_endpoint",
            "caveat",
        },
    )

    bounded_export = client.get(
        NOOP_BOUNDED_EXPORT,
        headers=headers,
        params={"report_type": "ledger", "limit": 2, "offset": 0},
    )
    assert bounded_export.status_code == 200
    be = bounded_export.json()
    _assert_has_keys(
        be,
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
            "pagination",
            "safety_flags",
            "caveat",
        },
    )
    assert be["report_schema_version"] == "noop_runner_reports.v1"
    assert be["limit"] == 2
    assert be["offset"] == 0
    assert be["pagination"]["pagination_contract_version"] == "noop_runner_pagination.v1"
    assert be["pagination"]["max_limit"] == 500

    checksum = client.get(
        NOOP_CHECKSUM,
        headers=headers,
        params={"report_type": "ledger", "limit": 2, "offset": 0},
    )
    assert checksum.status_code == 200
    cs = checksum.json()
    _assert_has_keys(cs, {"report_type", "query_hash", "result_hash", "row_count", "generated_at", "caveat"})

    compatibility = client.get(NOOP_COMPATIBILITY, headers=headers)
    assert compatibility.status_code == 200
    cp = compatibility.json()
    _assert_has_keys(
        cp,
        {
            "report_schema_version",
            "compatibility_policy_version",
            "additive_fields_allowed",
            "breaking_changes_require_new_schema_version",
            "deprecated_fields_policy",
            "minimum_supported_schema_version",
            "current_supported_schema_version",
            "stable_endpoint_families",
            "safety_flags",
            "caveat",
        },
    )
    assert cp["report_schema_version"] == "noop_runner_reports.v1"
    assert cp["compatibility_policy_version"] == "noop_runner_compatibility.v1"
    assert cp["additive_fields_allowed"] is True
    assert cp["breaking_changes_require_new_schema_version"] is True

    client_contract = client.get(NOOP_CLIENT_CONTRACT, headers=headers)
    assert client_contract.status_code == 200
    cc = client_contract.json()
    _assert_has_keys(
        cc,
        {
            "client_contract_version",
            "report_schema_version",
            "compatibility_policy_version",
            "supported_filters_by_endpoint",
            "pagination_contract",
            "enum_values",
            "default_limits",
            "max_limits",
            "field_docs_endpoint",
            "display_metadata_endpoint",
            "localization_map_endpoint",
            "client_hints_endpoint",
            "safety_flags",
            "caveat",
        },
    )
    assert cc["client_contract_version"] == "noop_runner_client_contract.v1"

    filter_options = client.get(NOOP_FILTER_OPTIONS, headers=headers)
    assert filter_options.status_code == 200
    fo = filter_options.json()
    _assert_has_keys(
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
            "field_docs_endpoint",
            "display_metadata_endpoint",
            "client_hints_endpoint",
            "safety_flags",
            "caveat",
        },
    )

    pagination_contract = client.get(NOOP_PAGINATION_CONTRACT, headers=headers)
    assert pagination_contract.status_code == 200
    pg = pagination_contract.json()
    _assert_has_keys(
        pg,
        {
            "pagination_contract_version",
            "supported_style",
            "default_limit",
            "max_limit",
            "offset_base",
            "response_fields",
            "truncation_behavior",
            "field_docs_endpoint",
            "display_metadata_endpoint",
            "client_hints_endpoint",
            "safety_flags",
            "caveat",
        },
    )
    assert pg["pagination_contract_version"] == "noop_runner_pagination.v1"

    field_docs = client.get(NOOP_FIELD_DOCS, headers=headers)
    assert field_docs.status_code == 200
    fd = field_docs.json()
    _assert_has_keys(
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

    display_metadata = client.get(NOOP_DISPLAY_METADATA, headers=headers)
    assert display_metadata.status_code == 200
    dm = display_metadata.json()
    _assert_has_keys(
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

    localization_map = client.get(NOOP_LOCALIZATION_MAP, headers=headers)
    assert localization_map.status_code == 200
    lm = localization_map.json()
    _assert_has_keys(
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

    client_hints = client.get(NOOP_CLIENT_HINTS, headers=headers)
    assert client_hints.status_code == 200
    ch = client_hints.json()
    _assert_has_keys(
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

    # Read-only/no-audit/no-file and no-mutation guarantees.
    after_read_event_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == org_id
            )
        ).scalar_one()
    )
    after_read_event_statuses = {
        row.id: row.event_status
        for row in db_session.execute(
            select(GovernanceAutopilotNoopRunnerEvent).where(GovernanceAutopilotNoopRunnerEvent.organization_id == org_id)
        ).scalars()
    }
    after_read_audit_rows = int(
        db_session.execute(select(func.count(AuditLog.id)).where(AuditLog.organization_id == org_id)).scalar_one()
    )
    after_read_signals = {
        row.id: row.status
        for row in db_session.execute(select(GovernanceSignal).where(GovernanceSignal.organization_id == org_id)).scalars()
    }
    after_read_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_read_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    after_read_report_files = (
        sorted(str(path.relative_to(reports_dir)) for path in reports_dir.glob("**/*") if path.is_file())
        if reports_dir.exists()
        else []
    )

    assert after_read_event_rows == before_event_rows
    assert after_read_event_statuses == before_event_statuses
    assert after_read_audit_rows == before_audit_rows
    assert after_read_signals == before_signals
    assert after_read_tasks == before_tasks
    assert after_read_reviews == before_reviews
    assert after_read_report_files == before_report_files

    # Write endpoint behavior remains constrained to create/archive with audit.
    create_write = client.post(
        f"{RUNNER_HANDSHAKES}/{seeded['ready_handshake_id']}/noop-runner/events",
        headers=headers,
        json={"idempotency_key": "p86-write-event"},
    )
    assert create_write.status_code == 201
    created_event_id = create_write.json()["event_id"]

    archive_write = client.post(
        f"{NOOP_EVENTS}/{created_event_id}/archive",
        headers=headers,
        json={"reason": "phase86 archive"},
    )
    assert archive_write.status_code == 200
    assert archive_write.json()["event_status"] == "archived"

    after_write_audit_rows = int(
        db_session.execute(select(func.count(AuditLog.id)).where(AuditLog.organization_id == org_id)).scalar_one()
    )
    assert after_write_audit_rows > after_read_audit_rows

    noop_actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(
                AuditLog.organization_id == org_id,
                AuditLog.action.like("governance_autopilot_noop_runner_event.%"),
            )
        ).all()
    }
    assert noop_actions.issubset(
        {
            "governance_autopilot_noop_runner_event.created",
            "governance_autopilot_noop_runner_event.archived",
        }
    )
    assert "governance_autopilot_noop_runner_event.created" in noop_actions
    assert "governance_autopilot_noop_runner_event.archived" in noop_actions

    caveat = p8["caveat"].lower()
    assert "no real runner exists" in caveat
    assert "does not execute automation" in caveat
    assert "does not create file exports" in caveat
    assert "does not make legal or regulatory determinations" in caveat
