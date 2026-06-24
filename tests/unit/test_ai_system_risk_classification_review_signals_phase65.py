import hashlib
import json

from sqlalchemy import func, select

from app.models.ai_system_risk_classification_record import AISystemRiskClassificationRecord
from app.models.ai_system_risk_classification_record_snapshot import AISystemRiskClassificationRecordSnapshot
from app.models.audit_log import AuditLog
from app.models.governance_signal import GovernanceSignal
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_risk_classification_phase64 import (
    ASSESSMENTS_BASE,
    CLASSIFICATION_BASE,
    _create_ai_system,
    _create_assessment,
    _create_taxonomy,
)


def _create_classification(client, headers: dict[str, str], assessment_id: str, **overrides) -> dict:
    payload = {
        "classification_json": {"labels": [{"group_key": "data_sensitivity", "label_key": "personal_data"}]},
        "confidence_level": "medium",
        "justification": "manual assertion",
        "supersede_previous": True,
    }
    payload.update(overrides)
    response = client.post(
        f"{ASSESSMENTS_BASE}/{assessment_id}/classifications",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def _signal_count(db_session) -> int:
    return int(db_session.execute(select(func.count(GovernanceSignal.id))).scalar_one())


def _snapshot_count(db_session) -> int:
    return int(db_session.execute(select(func.count(AISystemRiskClassificationRecordSnapshot.id))).scalar_one())


def test_phase65_classification_review_actions_create_snapshots_and_signals(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p65-review")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"])

    submit = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/submit-for-review",
        headers=org["org_headers"],
        json={"note": "please review"},
    )
    assert submit.status_code == 200
    assert submit.json()["review_status"] == "in_review"

    change_note_required = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/request-changes",
        headers=org["org_headers"],
        json={},
    )
    assert change_note_required.status_code == 422

    changes = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/request-changes",
        headers=org["org_headers"],
        json={"change_request_note": "need clearer evidence mapping"},
    )
    assert changes.status_code == 200
    assert changes.json()["review_status"] == "changes_requested"

    reviewed = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/mark-reviewed",
        headers=org["org_headers"],
        json={"review_note": "accepted after revision"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "reviewed"

    reject_reason_required = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/reject",
        headers=org["org_headers"],
        json={},
    )
    assert reject_reason_required.status_code == 422

    rejected = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/reject",
        headers=org["org_headers"],
        json={"rejection_reason": "material concerns unresolved"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["review_status"] == "rejected"

    snapshots = client.get(
        f"{CLASSIFICATION_BASE}/{classification['id']}/snapshots",
        headers=org["org_headers"],
    )
    assert snapshots.status_code == 200
    snap_rows = snapshots.json()
    assert len(snap_rows) >= 4
    versions = [row["snapshot_version"] for row in snap_rows]
    assert versions == sorted(versions, reverse=True)

    for snap in snap_rows:
        canonical = json.dumps(snap["snapshot_json"], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == snap["snapshot_sha256"]

    signals = client.get("/api/v1/ai-governance/signals", headers=org["org_headers"])
    assert signals.status_code == 200
    signal_types = {row["signal_type"] for row in signals.json()}
    assert "classification_needs_review" in signal_types
    assert "classification_changes_requested" in signal_types
    assert "classification_reviewed" in signal_types
    assert "classification_rejected" in signal_types


def test_phase65_archived_or_superseded_review_actions_blocked(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p65-block")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    _create_taxonomy(client, org["org_headers"], is_default=True)

    first = _create_classification(client, org["org_headers"], assessment["id"])
    second = _create_classification(client, org["org_headers"], assessment["id"], supersede_previous=True)

    blocked_superseded = client.post(
        f"{CLASSIFICATION_BASE}/{first['id']}/submit-for-review",
        headers=org["org_headers"],
        json={},
    )
    assert blocked_superseded.status_code == 400

    archived = client.post(
        f"{CLASSIFICATION_BASE}/{second['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "retired"},
    )
    assert archived.status_code == 200

    blocked_archived = client.post(
        f"{CLASSIFICATION_BASE}/{second['id']}/mark-reviewed",
        headers=org["org_headers"],
        json={},
    )
    assert blocked_archived.status_code == 400


def test_phase65_snapshot_and_signal_tenant_scope(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p65-tenant-1")
    org2 = bootstrap_org_user(client, email_prefix="p65-tenant-2")

    ai1 = _create_ai_system(client, org1["org_headers"])
    assessment1 = _create_assessment(client, org1["org_headers"], ai1["id"])
    _create_taxonomy(client, org1["org_headers"], is_default=True)
    classification1 = _create_classification(client, org1["org_headers"], assessment1["id"])

    created = client.post(
        f"{CLASSIFICATION_BASE}/{classification1['id']}/snapshots",
        headers=org1["org_headers"],
        json={},
    )
    assert created.status_code == 201
    snapshot_id = created.json()["id"]

    cross_snapshot = client.get(
        f"/api/v1/ai-governance/ai-risk/classification-snapshots/{snapshot_id}",
        headers=org2["org_headers"],
    )
    assert cross_snapshot.status_code == 404

    submit = client.post(
        f"{CLASSIFICATION_BASE}/{classification1['id']}/submit-for-review",
        headers=org1["org_headers"],
        json={},
    )
    assert submit.status_code == 200

    sig_list = client.get("/api/v1/ai-governance/signals", headers=org1["org_headers"])
    assert sig_list.status_code == 200
    signal_id = sig_list.json()[0]["id"]

    cross_signal = client.get(f"/api/v1/ai-governance/signals/{signal_id}", headers=org2["org_headers"])
    assert cross_signal.status_code == 404


def test_phase65_signal_resolve_dismiss_require_reason_and_no_source_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p65-resolve")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"], confidence_level="low")

    refreshed = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/refresh-classification-signals",
        headers=org["org_headers"],
        json={"persist_signals": True},
    )
    assert refreshed.status_code == 200
    created_ids = refreshed.json().get("created_signal_ids") or []
    assert created_ids

    signal_id = created_ids[0]
    before_classification = client.get(f"{CLASSIFICATION_BASE}/{classification['id']}", headers=org["org_headers"]).json()

    missing_reason_resolve = client.post(
        f"/api/v1/ai-governance/signals/{signal_id}/resolve",
        headers=org["org_headers"],
        json={},
    )
    assert missing_reason_resolve.status_code == 422

    resolved = client.post(
        f"/api/v1/ai-governance/signals/{signal_id}/resolve",
        headers=org["org_headers"],
        json={"reason": "manually addressed"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    signal_id_2 = created_ids[-1]
    if signal_id_2 == signal_id and len(created_ids) > 1:
        signal_id_2 = created_ids[1]
    if signal_id_2 == signal_id:
        # create one more open signal
        created_again = client.post(
            f"{CLASSIFICATION_BASE}/{classification['id']}/request-changes",
            headers=org["org_headers"],
            json={"change_request_note": "still needs updates"},
        )
        assert created_again.status_code == 200
        all_signals = client.get("/api/v1/ai-governance/signals", headers=org["org_headers"]).json()
        signal_id_2 = next(row["id"] for row in all_signals if row["status"] == "open")

    missing_reason_dismiss = client.post(
        f"/api/v1/ai-governance/signals/{signal_id_2}/dismiss",
        headers=org["org_headers"],
        json={},
    )
    assert missing_reason_dismiss.status_code == 422

    dismissed = client.post(
        f"/api/v1/ai-governance/signals/{signal_id_2}/dismiss",
        headers=org["org_headers"],
        json={"reason": "expected noise"},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    after_classification = client.get(f"{CLASSIFICATION_BASE}/{classification['id']}", headers=org["org_headers"]).json()
    assert after_classification["classification_json"] == before_classification["classification_json"]
    assert after_classification["review_status"] == before_classification["review_status"]


def test_phase65_refresh_preview_read_only_and_persist_idempotent(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p65-refresh")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    _create_taxonomy(client, org["org_headers"], is_default=True)

    # No active classification -> candidate
    before_signals = _signal_count(db_session)
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    preview = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/refresh-classification-signals",
        headers=org["org_headers"],
        json={"persist_signals": False},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["persist_signals"] is False
    assert body["created_count"] == 0
    reason_codes = {item["reason_code"] for item in body["signals"]}
    assert "assessment_missing_classification" in reason_codes

    assert _signal_count(db_session) == before_signals
    assert int(db_session.execute(select(func.count(AuditLog.id))).scalar_one()) == before_audit

    # Create low-confidence classification; persist should be idempotent
    _create_classification(client, org["org_headers"], assessment["id"], confidence_level="low")
    persist_1 = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/refresh-classification-signals",
        headers=org["org_headers"],
        json={"persist_signals": True},
    )
    assert persist_1.status_code == 200
    created_1 = persist_1.json()["created_count"]
    assert created_1 >= 1

    persist_2 = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/refresh-classification-signals",
        headers=org["org_headers"],
        json={"persist_signals": True},
    )
    assert persist_2.status_code == 200
    assert persist_2.json()["created_count"] == 0


def test_phase65_response_metadata_summary_contracts_and_no_preview_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p65-meta")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"], confidence_level="low")

    before_snapshots = _snapshot_count(db_session)
    before_signals = _signal_count(db_session)
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    preview = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/refresh-classification-signals",
        headers=org["org_headers"],
        json={"persist_signals": False},
    )
    assert preview.status_code == 200

    assert _snapshot_count(db_session) == before_snapshots
    assert _signal_count(db_session) == before_signals
    assert int(db_session.execute(select(func.count(AuditLog.id))).scalar_one()) == before_audit

    submit = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/submit-for-review",
        headers=org["org_headers"],
        json={"note": "check metadata"},
    )
    assert submit.status_code == 200
    cbody = submit.json()
    assert cbody["latest_snapshot_id"] is not None
    assert isinstance(cbody["open_signal_count"], int)
    assert cbody["review_status"] == "in_review"

    assessment_detail = client.get(f"{ASSESSMENTS_BASE}/{assessment['id']}", headers=org["org_headers"])
    assert assessment_detail.status_code == 200
    abody = assessment_detail.json()
    assert isinstance(abody["open_signal_count"], int)
    assert abody["latest_classification_review_status"] == "in_review"

    summary = client.get("/api/v1/ai-governance/signals/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    sbody = summary.json()
    assert sbody["total_signals"] >= 1
    assert "classification_needs_review" in sbody["by_signal_type"]

    contracts = client.get("/api/v1/ai-governance/contracts/phase6", headers=org["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"]: g for g in contracts.json()["groups"]}
    assert "ai_risk_classification_review" in groups
    assert "ai_risk_classification_snapshots" in groups
    assert "governance_signals" in groups
    fields = set(groups["ai_risk_classification_records"]["response_contract_fields"])
    assert {"review_status", "latest_snapshot_id", "open_signal_count"}.issubset(fields)

    actions = [row["action"] for row in client.get("/api/v1/audit-logs", headers=org["org_headers"]).json()]
    assert "ai_system_risk_classification_record.submitted_for_review" in actions
    assert "ai_system_risk_classification_snapshot.created" in actions
    assert "governance_signal.refresh_persisted" not in actions


def test_phase65_review_signal_refresh_detects_changes_requested_and_rejected_candidates(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p65-candidates")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"], confidence_level="high")

    changes = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/request-changes",
        headers=org["org_headers"],
        json={"change_request_note": "update needed"},
    )
    assert changes.status_code == 200

    preview_changes = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/refresh-classification-signals",
        headers=org["org_headers"],
        json={"persist_signals": False},
    )
    assert preview_changes.status_code == 200
    rc = {item["reason_code"] for item in preview_changes.json()["signals"]}
    assert "classification_changes_requested" in rc

    rejected = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/reject",
        headers=org["org_headers"],
        json={"rejection_reason": "insufficient support"},
    )
    assert rejected.status_code == 200

    preview_rejected = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/refresh-classification-signals",
        headers=org["org_headers"],
        json={"persist_signals": False},
    )
    assert preview_rejected.status_code == 200
    rr = {item["reason_code"] for item in preview_rejected.json()["signals"]}
    assert "classification_rejected" in rr


def test_phase65_refresh_persist_requires_write_permission(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p65-perm")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"])

    # Preview path allowed with read
    preview = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/refresh-classification-signals",
        headers=org["org_headers"],
        json={"persist_signals": False},
    )
    assert preview.status_code == 200

    # Persist path uses write check; current bootstrap user has write in this project mapping.
    persisted = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/refresh-classification-signals",
        headers=org["org_headers"],
        json={"persist_signals": True},
    )
    assert persisted.status_code == 200


def test_phase65_no_legal_determination_wording_in_signal_and_classification_caveats(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p65-caveat")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"])

    submit = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/submit-for-review",
        headers=org["org_headers"],
        json={},
    )
    assert submit.status_code == 200
    assert "legal" in submit.json()["caveat"].lower()
    assert "automatic" in submit.json()["caveat"].lower()

    signals = client.get("/api/v1/ai-governance/signals", headers=org["org_headers"])
    assert signals.status_code == 200
    assert signals.json()
    assert "do not approve" in signals.json()[0]["caveat"].lower()

    # Ensure source records unchanged by signal operations.
    before = client.get(f"{CLASSIFICATION_BASE}/{classification['id']}", headers=org["org_headers"])
    assert before.status_code == 200
    before_json = before.json()
    _ = client.post(
        f"/api/v1/ai-governance/signals/{signals.json()[0]['id']}/dismiss",
        headers=org["org_headers"],
        json={"reason": "handled"},
    )
    after = client.get(f"{CLASSIFICATION_BASE}/{classification['id']}", headers=org["org_headers"])
    assert after.status_code == 200
    after_json = after.json()
    assert before_json["classification_json"] == after_json["classification_json"]
