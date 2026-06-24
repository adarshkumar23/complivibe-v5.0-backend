import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_noop_runner_event import GovernanceAutopilotNoopRunnerEvent
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_noop_runner_events_phase80 import _create_handshake, _phase8_router_paths_in_order
from tests.unit.test_ai_system_autopilot_policies_phase70 import _seed

PHASE8_CONTRACT = "/api/v1/ai-governance/contracts/phase8"
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


def _seed_phase81_events(client, headers: dict[str, str]) -> dict:
    ai, assessment, _ = _seed(client, headers, name="P81-Seed")
    ready = _create_handshake(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])
    ready_handshake_id = ready["handshake"]["handshake_id"]

    logged = client.post(
        f"{RUNNER_HANDSHAKES}/{ready_handshake_id}/noop-runner/events",
        headers=headers,
        json={"idempotency_key": "p81-logged"},
    )
    assert logged.status_code == 201
    logged_id = logged.json()["event_id"]

    first_dup = client.post(
        f"{RUNNER_HANDSHAKES}/{ready_handshake_id}/noop-runner/events",
        headers=headers,
        json={"idempotency_key": "p81-dup"},
    )
    assert first_dup.status_code == 201
    dup_event_id = first_dup.json()["event_id"]
    archived = client.post(
        f"{NOOP_EVENTS}/{dup_event_id}/archive",
        headers=headers,
        json={"reason": "phase81 duplicate test"},
    )
    assert archived.status_code == 200
    second_dup = client.post(
        f"{RUNNER_HANDSHAKES}/{ready_handshake_id}/noop-runner/events",
        headers=headers,
        json={"idempotency_key": "p81-dup"},
    )
    assert second_dup.status_code == 201
    assert second_dup.json()["event_id"] != dup_event_id

    blocked_seed = _create_handshake(client, headers, assessment_id=assessment["id"], ai_system_id=ai["id"])
    blocked_handshake_id = blocked_seed["handshake"]["handshake_id"]
    revoked = client.post(
        f"{RUNNER_HANDSHAKES}/{blocked_handshake_id}/revoke",
        headers=headers,
        json={"revoke_reason": "phase81 blocked test"},
    )
    assert revoked.status_code == 200
    blocked = client.post(
        f"{RUNNER_HANDSHAKES}/{blocked_handshake_id}/noop-runner/events",
        headers=headers,
        json={"idempotency_key": "p81-blocked"},
    )
    assert blocked.status_code == 201
    blocked_body = blocked.json()
    assert blocked_body["event_status"] == "blocked"

    return {
        "ready_handshake_id": ready_handshake_id,
        "blocked_handshake_id": blocked_handshake_id,
        "logged_event_id": logged_id,
        "blocked_event_id": blocked_body["event_id"],
        "logged_execution_intent_id": logged.json()["execution_intent_id"],
        "blocked_execution_intent_id": blocked_body["execution_intent_id"],
    }


def test_phase81_noop_runner_observability_route_ordering_static_before_dynamic():
    paths = _phase8_router_paths_in_order()
    assert "/autopilot/noop-runner/reports/contract" in paths
    assert "/autopilot/noop-runner/reports/diagnostics-manifest" in paths
    assert "/autopilot/noop-runner/reports/bounded-export" in paths
    assert "/autopilot/noop-runner/reports/checksum" in paths
    assert "/autopilot/noop-runner/ledger" in paths
    assert "/autopilot/noop-runner/reports/timeline" in paths
    assert "/autopilot/noop-runner/reports/blockers" in paths
    assert "/autopilot/noop-runner/reports/readiness" in paths
    assert "/autopilot/noop-runner/reports/idempotency" in paths
    assert "/autopilot/noop-runner/reports/control-plane-health" in paths
    assert "/autopilot/noop-runner/events/{event_id}" in paths
    assert paths.index("/autopilot/noop-runner/reports/contract") < paths.index("/autopilot/noop-runner/events/{event_id}")
    assert paths.index("/autopilot/noop-runner/reports/diagnostics-manifest") < paths.index(
        "/autopilot/noop-runner/events/{event_id}"
    )
    assert paths.index("/autopilot/noop-runner/reports/bounded-export") < paths.index(
        "/autopilot/noop-runner/events/{event_id}"
    )
    assert paths.index("/autopilot/noop-runner/reports/checksum") < paths.index("/autopilot/noop-runner/events/{event_id}")
    assert paths.index("/autopilot/noop-runner/ledger") < paths.index("/autopilot/noop-runner/events/{event_id}")
    assert paths.index("/autopilot/noop-runner/reports/timeline") < paths.index(
        "/autopilot/noop-runner/events/{event_id}"
    )
    assert paths.index("/autopilot/noop-runner/reports/control-plane-health") < paths.index(
        "/autopilot/noop-runner/events/{event_id}"
    )


def test_phase81_noop_runner_observability_reports_and_boundaries(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p81-observe-1")
    org2 = bootstrap_org_user(client, email_prefix="p81-observe-2")
    headers = org1["org_headers"]
    seeded = _seed_phase81_events(client, headers)

    # Another tenant event to ensure tenant scoping.
    ai2, assessment2, _ = _seed(client, org2["org_headers"], name="P81-Tenant2")
    hs2 = _create_handshake(client, org2["org_headers"], assessment_id=assessment2["id"], ai_system_id=ai2["id"])
    tenant2_created = client.post(
        f"{RUNNER_HANDSHAKES}/{hs2['handshake']['handshake_id']}/noop-runner/events",
        headers=org2["org_headers"],
        json={"idempotency_key": "p81-tenant2"},
    )
    assert tenant2_created.status_code == 201

    phase8 = client.get(PHASE8_CONTRACT, headers=headers)
    assert phase8.status_code == 200
    groups = {group["group_key"] for group in phase8.json()["groups"]}
    assert "governance_noop_runner_events" in groups
    assert "governance_noop_runner_observability" in groups
    assert "governance_noop_runner_operator_diagnostics" in groups

    before_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == uuid.UUID(org1["organization_id"])
            )
        ).scalar_one()
    )
    before_audit = int(
        db_session.execute(
            select(func.count(AuditLog.id)).where(AuditLog.organization_id == uuid.UUID(org1["organization_id"]))
        ).scalar_one()
    )
    before_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org1["organization_id"]))
        ).scalars()
    }
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    reports_dir = Path("reports")
    before_report_files = sorted(
        [str(path.relative_to(reports_dir)) for path in reports_dir.glob("**/*") if path.is_file()]
    ) if reports_dir.exists() else []

    ledger = client.get(NOOP_LEDGER, headers=headers)
    assert ledger.status_code == 200
    ledger_rows = ledger.json()
    assert len(ledger_rows) >= 3
    assert all(row["execution_allowed"] is False for row in ledger_rows)
    assert all(row["dry_run"] is True for row in ledger_rows)
    assert all(row["noop_only"] is True for row in ledger_rows)
    assert seeded["blocked_event_id"] in {row["event_id"] for row in ledger_rows}
    assert tenant2_created.json()["event_id"] not in {row["event_id"] for row in ledger_rows}

    blocked_only = client.get(NOOP_LEDGER, headers=headers, params={"blocked_only": True})
    assert blocked_only.status_code == 200
    blocked_rows = blocked_only.json()
    assert len(blocked_rows) >= 1
    assert all(row["event_status"] == "blocked" for row in blocked_rows)
    assert any(len(row["blocked_reasons"]) >= 1 for row in blocked_rows)

    filtered = client.get(
        NOOP_LEDGER,
        headers=headers,
        params={"runner_handshake_id": seeded["ready_handshake_id"]},
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) >= 1
    assert all(row["runner_handshake_id"] == seeded["ready_handshake_id"] for row in filtered.json())

    cross_tenant_filter = client.get(
        NOOP_LEDGER,
        headers=headers,
        params={"runner_handshake_id": hs2["handshake"]["handshake_id"]},
    )
    assert cross_tenant_filter.status_code == 404

    timeline = client.get(NOOP_TIMELINE, headers=headers, params={"days": 30})
    assert timeline.status_code == 200
    timeline_body = timeline.json()
    assert timeline_body["total_events"] >= 3
    assert "timeline_buckets" in timeline_body
    assert timeline_body["logged_count"] >= 1
    assert timeline_body["blocked_count"] >= 1
    assert timeline_body["report_schema_version"] == "noop_runner_reports.v1"
    assert timeline_body["generated_at"] is not None

    blockers = client.get(NOOP_BLOCKERS, headers=headers)
    assert blockers.status_code == 200
    blockers_body = blockers.json()
    assert blockers_body["total_blocked_events"] >= 1
    assert len(blockers_body["blocker_counts"]) >= 1
    assert len(blockers_body["top_blockers"]) >= 1
    assert seeded["blocked_execution_intent_id"] in blockers_body["affected_execution_intents"]
    assert blockers_body["report_schema_version"] == "noop_runner_reports.v1"
    assert blockers_body["generated_at"] is not None

    readiness = client.get(NOOP_READINESS, headers=headers)
    assert readiness.status_code == 200
    readiness_body = readiness.json()
    assert readiness_body["ready_handshake_count"] >= 1
    assert readiness_body["no_op_logged_count"] >= 1
    assert readiness_body["blocked_event_count"] >= 1
    assert "no_event_for_ready_handshake_count" in readiness_body
    assert readiness_body["report_schema_version"] == "noop_runner_reports.v1"
    assert readiness_body["generated_at"] is not None

    idempotency = client.get(NOOP_IDEMPOTENCY, headers=headers)
    assert idempotency.status_code == 200
    idem_body = idempotency.json()
    assert idem_body["total_events"] >= 3
    assert idem_body["unique_idempotency_key_count"] >= 2
    assert idem_body["duplicate_key_attempts_inferred_count"] >= 1
    assert idem_body["active_duplicate_records_count"] == 0
    assert "p81-dup" in idem_body["idempotency_keys_with_multiple_records"]
    assert idem_body["report_schema_version"] == "noop_runner_reports.v1"
    assert idem_body["generated_at"] is not None

    health = client.get(NOOP_HEALTH, headers=headers)
    assert health.status_code == 200
    health_body = health.json()
    assert health_body["execution_allowed"] is False
    assert health_body["real_runner_present"] is False
    assert health_body["job_queue_present"] is False
    assert health_body["noop_runner_only"] is True
    assert health_body["token_plaintext_storage_detected"] is False
    assert health_body["external_side_effects_enabled"] is False
    assert health_body["health_status"] in {"healthy", "warning", "attention_required"}
    assert health_body["report_schema_version"] == "noop_runner_reports.v1"
    assert health_body["generated_at"] is not None

    reports_contract = client.get(NOOP_REPORT_CONTRACT, headers=headers)
    assert reports_contract.status_code == 200
    rc = reports_contract.json()
    assert rc["report_schema_version"] == "noop_runner_reports.v1"
    assert "ledger" in rc["supported_report_types"]
    assert "result_hash" in rc["common_metadata_fields"]
    assert rc["bounded_export_limits"]["max_limit"] == 500
    assert rc["safety_flags"]["execution_allowed"] is False

    manifest = client.get(NOOP_MANIFEST, headers=headers)
    assert manifest.status_code == 200
    mf = manifest.json()
    assert mf["report_schema_version"] == "noop_runner_reports.v1"
    assert "ledger" in mf["available_reports"]
    assert "control_plane_health" in mf["endpoint_map"]
    assert mf["execution_allowed"] is False
    assert mf["real_runner_present"] is False
    assert mf["job_queue_present"] is False
    assert mf["noop_runner_only"] is True
    assert mf["total_noop_events"] >= 3

    export_ledger = client.get(
        NOOP_BOUNDED_EXPORT,
        headers=headers,
        params={"report_type": "ledger", "limit": 2, "offset": 0},
    )
    assert export_ledger.status_code == 200
    el = export_ledger.json()
    assert el["report_schema_version"] == "noop_runner_reports.v1"
    assert el["report_type"] == "ledger"
    assert el["query_hash"]
    assert el["result_hash"]
    assert el["limit"] == 2
    assert el["offset"] == 0
    assert isinstance(el["truncated"], bool)
    assert isinstance(el["row_count"], int)
    assert isinstance(el["rows"], list)
    assert el["execution_allowed"] is False
    assert el["real_runner_present"] is False
    assert el["job_queue_present"] is False
    assert el["noop_runner_only"] is True

    export_limit_cap = client.get(
        NOOP_BOUNDED_EXPORT,
        headers=headers,
        params={"report_type": "ledger", "limit": 999, "offset": 0},
    )
    assert export_limit_cap.status_code == 200
    assert export_limit_cap.json()["limit"] == 500

    export_timeline = client.get(
        NOOP_BOUNDED_EXPORT,
        headers=headers,
        params={"report_type": "timeline", "limit": 30, "offset": 0},
    )
    assert export_timeline.status_code == 200
    et = export_timeline.json()
    assert et["report_type"] == "timeline"
    assert et["rows"] is None
    assert isinstance(et["report_payload"], dict)
    assert et["query_hash"]
    assert et["result_hash"]

    checksum_a = client.get(
        NOOP_CHECKSUM,
        headers=headers,
        params={"report_type": "ledger", "limit": 2, "offset": 0},
    )
    checksum_b = client.get(
        NOOP_CHECKSUM,
        headers=headers,
        params={"report_type": "ledger", "limit": 2, "offset": 0},
    )
    assert checksum_a.status_code == 200
    assert checksum_b.status_code == 200
    ca = checksum_a.json()
    cb = checksum_b.json()
    assert ca["report_type"] == "ledger"
    assert ca["query_hash"] == cb["query_hash"]
    assert ca["result_hash"] == cb["result_hash"]
    assert isinstance(ca["row_count"], int)

    after_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotNoopRunnerEvent.id)).where(
                GovernanceAutopilotNoopRunnerEvent.organization_id == uuid.UUID(org1["organization_id"])
            )
        ).scalar_one()
    )
    after_audit = int(
        db_session.execute(
            select(func.count(AuditLog.id)).where(AuditLog.organization_id == uuid.UUID(org1["organization_id"]))
        ).scalar_one()
    )
    after_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org1["organization_id"]))
        ).scalars()
    }
    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    after_report_files = sorted(
        [str(path.relative_to(reports_dir)) for path in reports_dir.glob("**/*") if path.is_file()]
    ) if reports_dir.exists() else []

    assert after_rows == before_rows
    assert after_audit == before_audit
    assert before_signals == after_signals
    assert before_tasks == after_tasks
    assert before_reviews == after_reviews
    assert after_report_files == before_report_files
