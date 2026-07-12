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
NOOP_REPORT_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/contract"
NOOP_MANIFEST = "/api/v1/ai-governance/autopilot/noop-runner/reports/diagnostics-manifest"
NOOP_BOUNDED_EXPORT = "/api/v1/ai-governance/autopilot/noop-runner/reports/bounded-export"
NOOP_COMPAT = "/api/v1/ai-governance/autopilot/noop-runner/reports/compatibility-policy"
NOOP_CLIENT_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/client-contract"
NOOP_FILTER_OPTIONS = "/api/v1/ai-governance/autopilot/noop-runner/reports/filter-options"
NOOP_PAGINATION_CONTRACT = "/api/v1/ai-governance/autopilot/noop-runner/reports/pagination-contract"
NOOP_FIELD_DOCS = "/api/v1/ai-governance/autopilot/noop-runner/reports/field-docs"
NOOP_DISPLAY_METADATA = "/api/v1/ai-governance/autopilot/noop-runner/reports/display-metadata"
NOOP_LOCALIZATION_MAP = "/api/v1/ai-governance/autopilot/noop-runner/reports/localization-map"
NOOP_CLIENT_HINTS = "/api/v1/ai-governance/autopilot/noop-runner/reports/client-hints"
NOOP_CHECKSUM = "/api/v1/ai-governance/autopilot/noop-runner/reports/checksum"


def test_phase87_route_ordering_and_docs_freeze_markers():
    paths = _phase8_router_paths_in_order()
    event_detail = "/autopilot/noop-runner/events/{event_id}"
    for route in [
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
        "/autopilot/noop-runner/events/summary",
    ]:
        assert route in paths
        assert paths.index(route) < paths.index(event_detail)

    readme = Path("README.md").read_text(encoding="utf-8")
    devlog = Path("DEVELOPMENT_LOG.md").read_text(encoding="utf-8")
    assert "Phase 8.7" in readme
    assert "Phase 8.7" in devlog


def test_phase87_closure_flags_versions_and_read_only_safety(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p87-closure")
    headers = org["org_headers"]
    _seed_phase81_events(client, headers, db_session=db_session, organization_id=org["organization_id"])
    org_id = uuid.UUID(org["organization_id"])

    reports_dir = Path("reports")
    before_report_files = (
        sorted(str(path.relative_to(reports_dir)) for path in reports_dir.glob("**/*") if path.is_file())
        if reports_dir.exists()
        else []
    )
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

    phase8 = client.get(PHASE8_CONTRACT, headers=headers)
    assert phase8.status_code == 200
    p8 = phase8.json()
    assert p8["execution_allowed"] is False
    assert p8["real_runner_present"] is False
    assert p8["job_queue_present"] is False
    assert p8["noop_runner_only"] is True
    assert {
        "governance_noop_runner_events",
        "governance_noop_runner_observability",
        "governance_noop_runner_operator_diagnostics",
        "governance_noop_runner_diagnostics_compatibility",
        "governance_noop_runner_client_integration",
        "governance_noop_runner_client_field_docs",
    }.issubset({g["group_key"] for g in p8["groups"]})

    noop_contract = client.get(NOOP_CONTRACT, headers=headers)
    assert noop_contract.status_code == 200
    nc = noop_contract.json()
    assert nc["execution_allowed"] is False
    assert nc["real_runner_present"] is False
    assert nc["job_queue_present"] is False
    assert nc["noop_only"] is True

    report_contract = client.get(NOOP_REPORT_CONTRACT, headers=headers)
    assert report_contract.status_code == 200
    rc = report_contract.json()
    assert rc["report_schema_version"] == "noop_runner_reports.v1"
    assert rc["compatibility_policy_version"] == "noop_runner_compatibility.v1"
    assert rc["additive_fields_allowed"] is True
    assert rc["breaking_changes_require_new_schema_version"] is True

    manifest = client.get(NOOP_MANIFEST, headers=headers)
    assert manifest.status_code == 200
    mf = manifest.json()
    assert mf["report_schema_version"] == "noop_runner_reports.v1"
    assert mf["compatibility_policy_version"] == "noop_runner_compatibility.v1"
    assert mf["current_supported_schema_version"] == "noop_runner_reports.v1"

    bounded = client.get(NOOP_BOUNDED_EXPORT, headers=headers, params={"report_type": "ledger", "limit": 10, "offset": 0})
    assert bounded.status_code == 200
    be = bounded.json()
    assert {"limit", "offset", "truncated", "next_offset", "row_count"}.issubset(set(be.keys()))
    assert {"limit", "offset", "truncated", "next_offset", "row_count", "max_limit", "pagination_contract_version"}.issubset(
        set(be["pagination"].keys())
    )

    checksum = client.get(NOOP_CHECKSUM, headers=headers, params={"report_type": "ledger", "limit": 10, "offset": 0})
    assert checksum.status_code == 200

    compat = client.get(NOOP_COMPAT, headers=headers)
    assert compat.status_code == 200
    cp = compat.json()
    assert cp["report_schema_version"] == "noop_runner_reports.v1"
    assert cp["compatibility_policy_version"] == "noop_runner_compatibility.v1"
    assert cp["additive_fields_allowed"] is True
    assert cp["breaking_changes_require_new_schema_version"] is True

    client_contract = client.get(NOOP_CLIENT_CONTRACT, headers=headers)
    assert client_contract.status_code == 200
    cc = client_contract.json()
    assert cc["client_contract_version"] == "noop_runner_client_contract.v1"

    filters = client.get(NOOP_FILTER_OPTIONS, headers=headers)
    assert filters.status_code == 200
    fo = filters.json()
    assert "noop_runner_control_plane_check" in fo["supported_event_types"]

    pagination = client.get(NOOP_PAGINATION_CONTRACT, headers=headers)
    assert pagination.status_code == 200
    assert pagination.json()["pagination_contract_version"] == "noop_runner_pagination.v1"

    field_docs = client.get(NOOP_FIELD_DOCS, headers=headers)
    assert field_docs.status_code == 200
    assert field_docs.json()["field_docs_version"] == "noop_runner_field_docs.v1"

    display = client.get(NOOP_DISPLAY_METADATA, headers=headers)
    assert display.status_code == 200
    assert display.json()["display_metadata_version"] == "noop_runner_display_metadata.v1"

    localization = client.get(NOOP_LOCALIZATION_MAP, headers=headers)
    assert localization.status_code == 200
    assert localization.json()["localization_map_version"] == "noop_runner_localization_map.v1"

    hints = client.get(NOOP_CLIENT_HINTS, headers=headers)
    assert hints.status_code == 200
    assert hints.json()["client_hints_version"] == "noop_runner_client_hints.v1"

    for payload in [rc, mf, be, cp, cc, fo, pagination.json(), field_docs.json(), display.json(), localization.json(), hints.json()]:
        assert "caveat" in payload

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
        sorted(str(path.relative_to(reports_dir)) for path in reports_dir.glob("**/*") if path.is_file())
        if reports_dir.exists()
        else []
    )

    assert after_rows == before_rows
    assert after_audit == before_audit
    assert after_signals == before_signals
    assert after_tasks == before_tasks
    assert after_reviews == before_reviews
    assert after_report_files == before_report_files
