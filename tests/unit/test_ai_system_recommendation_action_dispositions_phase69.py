import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.ai_system import AISystem
from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.ai_system_risk_classification_record import AISystemRiskClassificationRecord
from app.models.audit_log import AuditLog
from app.models.governance_recommendation_action_disposition import GovernanceRecommendationActionDisposition
from app.models.governance_recommendation_snapshot import GovernanceRecommendationSnapshot
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_candidate_actions_phase67 import _create_signal_flow
from tests.unit.test_ai_system_risk_classification_phase64 import (
    _create_ai_system,
    _create_assessment,
    _create_taxonomy,
)
from tests.unit.test_ai_system_risk_classification_review_signals_phase65 import _create_classification

SNAP_BASE = "/api/v1/ai-governance/recommendations/snapshots"
DISP_BASE = "/api/v1/ai-governance/recommendations/action-dispositions"


def _seed(client, headers: dict[str, str], *, name: str = "P69-AI") -> tuple[dict, dict, dict]:
    ai = _create_ai_system(client, headers, name=name)
    assessment = _create_assessment(client, headers, ai["id"], risk_level="high")
    _create_taxonomy(client, headers, is_default=True)
    classification = _create_classification(client, headers, assessment["id"], confidence_level="low")
    _create_signal_flow(client, headers, classification["id"])
    return ai, assessment, classification


def _create_snapshot(client, headers: dict[str, str], *, scope_type: str, scope_id: str | None = None) -> dict:
    payload = {"scope_type": scope_type}
    if scope_id:
        payload["scope_id"] = scope_id
    resp = client.post(SNAP_BASE, headers=headers, json=payload)
    assert resp.status_code == 201
    return resp.json()


def _identity_hash(action: dict) -> str:
    payload = {
        "action_key": str(action.get("action_key") or ""),
        "target_entity_type": str(action.get("target_entity_type") or ""),
        "target_entity_id": str(action.get("target_entity_id") or "") if action.get("target_entity_id") else "",
        "related_ai_system_id": str(action.get("related_ai_system_id") or "") if action.get("related_ai_system_id") else "",
        "related_risk_assessment_id": (
            str(action.get("related_risk_assessment_id") or "") if action.get("related_risk_assessment_id") else ""
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase69_snapshot_actions_hash_and_lifecycle_writes_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p69-actions")
    _, assessment, _ = _seed(client, org["org_headers"], name="P69-AI-1")
    snapshot = _create_snapshot(client, org["org_headers"], scope_type="risk_assessment", scope_id=assessment["id"])

    actions_resp = client.get(f"{SNAP_BASE}/{snapshot['id']}/actions", headers=org["org_headers"])
    assert actions_resp.status_code == 200
    actions_body = actions_resp.json()
    assert actions_body["snapshot_id"] == snapshot["id"]
    assert actions_body["action_count"] >= 1
    action = actions_body["actions"][0]
    assert action["action_identity_hash"] == _identity_hash(action)

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    ack = client.post(
        f"{SNAP_BASE}/{snapshot['id']}/actions/{action['action_identity_hash']}/acknowledge",
        headers=org["org_headers"],
        json={"note": "seen"},
    )
    assert ack.status_code == 200
    ack_body = ack.json()
    assert ack_body["disposition_status"] == "acknowledged"

    dism_422 = client.post(
        f"{SNAP_BASE}/{snapshot['id']}/actions/{action['action_identity_hash']}/dismiss",
        headers=org["org_headers"],
        json={"reason": ""},
    )
    assert dism_422.status_code == 422

    defer_until = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    defer = client.post(
        f"{SNAP_BASE}/{snapshot['id']}/actions/{action['action_identity_hash']}/defer",
        headers=org["org_headers"],
        json={"reason": "later", "deferred_until": defer_until},
    )
    assert defer.status_code == 200
    defer_body = defer.json()
    assert defer_body["disposition_status"] == "deferred"
    assert defer_body["deferred_until"] is not None

    accept = client.post(
        f"{SNAP_BASE}/{snapshot['id']}/actions/{action['action_identity_hash']}/accept-for-manual-work",
        headers=org["org_headers"],
        json={"note": "manual follow-up"},
    )
    assert accept.status_code == 200
    assert accept.json()["disposition_status"] == "accepted_for_manual_work"

    bad_action = client.post(
        f"{SNAP_BASE}/{snapshot['id']}/actions/{'0'*64}/acknowledge",
        headers=org["org_headers"],
        json={},
    )
    assert bad_action.status_code == 404

    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_audit > before_audit
    actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        ).all()
    }
    assert "governance_recommendation_action.acknowledged" in actions
    assert "governance_recommendation_action.deferred" in actions
    assert "governance_recommendation_action.accepted_for_manual_work" in actions


def test_phase69_disposition_read_endpoints_overlay_no_mutation_and_no_read_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p69-overlay")
    ai, assessment, classification = _seed(client, org["org_headers"], name="P69-AI-2")
    snapshot = _create_snapshot(client, org["org_headers"], scope_type="risk_assessment", scope_id=assessment["id"])

    actions_resp = client.get(f"{SNAP_BASE}/{snapshot['id']}/actions", headers=org["org_headers"])
    action = actions_resp.json()["actions"][0]

    before_sig_statuses = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    before_assessment = db_session.get(AISystemRiskAssessment, uuid.UUID(assessment["id"]))
    before_classification = db_session.get(AISystemRiskClassificationRecord, uuid.UUID(classification["id"]))
    before_ai = db_session.get(AISystem, uuid.UUID(ai["id"]))
    before_payload = db_session.get(GovernanceRecommendationSnapshot, uuid.UUID(snapshot["id"])).recommendation_payload_json
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    ack = client.post(
        f"{SNAP_BASE}/{snapshot['id']}/actions/{action['action_identity_hash']}/acknowledge",
        headers=org["org_headers"],
        json={},
    )
    assert ack.status_code == 200

    detail_plain = client.get(f"{SNAP_BASE}/{snapshot['id']}", headers=org["org_headers"])
    assert detail_plain.status_code == 200
    assert detail_plain.json().get("actions_overlay") is None

    detail_overlay = client.get(
        f"{SNAP_BASE}/{snapshot['id']}?include_dispositions=true",
        headers=org["org_headers"],
    )
    assert detail_overlay.status_code == 200
    overlay = detail_overlay.json()["actions_overlay"]
    assert isinstance(overlay, list)
    assert any(item.get("disposition") for item in overlay)

    actions_with_disp = client.get(
        f"{SNAP_BASE}/{snapshot['id']}/actions?include_dispositions=true",
        headers=org["org_headers"],
    )
    assert actions_with_disp.status_code == 200
    assert any(item.get("disposition") for item in actions_with_disp.json()["actions"])

    listed = client.get(f"{DISP_BASE}", headers=org["org_headers"])
    assert listed.status_code == 200
    assert listed.json()

    summary = client.get(f"{DISP_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    sb = summary.json()
    assert sb["total_dispositions"] >= 1
    assert isinstance(sb["by_status"], dict)

    # Read endpoints should not write audit rows.
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_audit == before_audit + 1  # only acknowledge write action

    after_sig_statuses = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    assert before_sig_statuses == after_sig_statuses

    after_assessment = db_session.get(AISystemRiskAssessment, uuid.UUID(assessment["id"]))
    after_classification = db_session.get(AISystemRiskClassificationRecord, uuid.UUID(classification["id"]))
    after_ai = db_session.get(AISystem, uuid.UUID(ai["id"]))
    assert before_assessment.status == after_assessment.status
    assert before_classification.status == after_classification.status
    assert before_ai.archived_at == after_ai.archived_at

    after_payload = db_session.get(GovernanceRecommendationSnapshot, uuid.UUID(snapshot["id"])).recommendation_payload_json
    assert before_payload == after_payload

    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    assert before_tasks == after_tasks
    assert before_reviews == after_reviews


def test_phase69_tenant_scope_and_filters_and_contract_group(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p69-tenant-1")
    org2 = bootstrap_org_user(client, email_prefix="p69-tenant-2")
    ai, assessment, _ = _seed(client, org1["org_headers"], name="P69-AI-3")
    snapshot = _create_snapshot(client, org1["org_headers"], scope_type="risk_assessment", scope_id=assessment["id"])

    actions_resp = client.get(f"{SNAP_BASE}/{snapshot['id']}/actions", headers=org1["org_headers"])
    action = actions_resp.json()["actions"][0]

    dismiss_cross = client.post(
        f"{SNAP_BASE}/{snapshot['id']}/actions/{action['action_identity_hash']}/dismiss",
        headers=org2["org_headers"],
        json={"reason": "cross"},
    )
    assert dismiss_cross.status_code == 404

    dismiss_ok = client.post(
        f"{SNAP_BASE}/{snapshot['id']}/actions/{action['action_identity_hash']}/dismiss",
        headers=org1["org_headers"],
        json={"reason": "not relevant"},
    )
    assert dismiss_ok.status_code == 200

    by_snapshot = client.get(f"{DISP_BASE}?snapshot_id={snapshot['id']}", headers=org1["org_headers"])
    assert by_snapshot.status_code == 200
    assert by_snapshot.json()

    by_status = client.get(f"{DISP_BASE}?disposition_status=dismissed", headers=org1["org_headers"])
    assert by_status.status_code == 200
    assert all(item["disposition_status"] == "dismissed" for item in by_status.json())

    by_ai = client.get(f"{DISP_BASE}?related_ai_system_id={ai['id']}", headers=org1["org_headers"])
    assert by_ai.status_code == 200

    cross_list = client.get(f"{DISP_BASE}?snapshot_id={snapshot['id']}", headers=org2["org_headers"])
    assert cross_list.status_code == 404

    contracts = client.get("/api/v1/ai-governance/contracts/phase6", headers=org1["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"]: g for g in contracts.json()["groups"]}
    assert "governance_recommendation_action_dispositions" in groups


def test_phase69_defer_requires_reason_and_accept_nonexecuting(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p69-defer")
    _, assessment, _ = _seed(client, org["org_headers"], name="P69-AI-4")
    snapshot = _create_snapshot(client, org["org_headers"], scope_type="risk_assessment", scope_id=assessment["id"])
    action = client.get(f"{SNAP_BASE}/{snapshot['id']}/actions", headers=org["org_headers"]).json()["actions"][0]

    invalid_defer = client.post(
        f"{SNAP_BASE}/{snapshot['id']}/actions/{action['action_identity_hash']}/defer",
        headers=org["org_headers"],
        json={"reason": ""},
    )
    assert invalid_defer.status_code == 422

    before_signal_ids = {
        str(row.id)
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }

    accept = client.post(
        f"{SNAP_BASE}/{snapshot['id']}/actions/{action['action_identity_hash']}/accept-for-manual-work",
        headers=org["org_headers"],
        json={"note": "manually planned"},
    )
    assert accept.status_code == 200
    assert accept.json()["disposition_status"] == "accepted_for_manual_work"

    after_signal_ids = {
        str(row.id)
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    assert before_signal_ids == after_signal_ids

    row_count = int(
        db_session.execute(
            select(func.count(GovernanceRecommendationActionDisposition.id)).where(
                GovernanceRecommendationActionDisposition.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    assert row_count >= 1
