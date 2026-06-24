import hashlib
import json
import uuid

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_copilot_draft_snapshot import GovernanceCopilotDraftSnapshot
from app.models.governance_recommendation_action_disposition import GovernanceRecommendationActionDisposition
from app.models.governance_recommendation_snapshot import GovernanceRecommendationSnapshot
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_recommendation_action_dispositions_phase69 import _create_snapshot, _seed

BASE = "/api/v1/ai-governance/copilot/draft-snapshots"


def _canonical_sha(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _snapshot_hash_from_response(body: dict) -> str:
    payload = {
        "draft_type": body["draft_type"],
        "scope_type": body["scope_type"],
        "scope_id": body["scope_id"],
        "draft_payload_json": body["draft_payload_json"],
        "source_context_hash": body["source_context_hash"],
    }
    return _canonical_sha(payload)


def test_phase611_preview_read_only_no_rows_no_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p611-preview")
    ai, assessment, _ = _seed(client, org["org_headers"], name="P611-Preview")

    before_rows = int(db_session.execute(select(func.count(GovernanceCopilotDraftSnapshot.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    response = client.post(
        f"{BASE}/preview",
        headers=org["org_headers"],
        json={
            "draft_type": "risk_assessment_review_brief",
            "scope_type": "risk_assessment",
            "scope_id": assessment["id"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["draft_type"] == "risk_assessment_review_brief"
    assert body["scope_type"] == "risk_assessment"
    assert body["scope_id"] == assessment["id"]
    assert body["source_context_hash"]
    assert "deterministic draft previews" in body["draft_payload_json"]["caveat"].lower()

    after_rows = int(db_session.execute(select(func.count(GovernanceCopilotDraftSnapshot.id))).scalar_one())
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_rows == before_rows
    assert after_audit == before_audit


def test_phase611_create_snapshot_version_hash_previous_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p611-create")
    ai, _, _ = _seed(client, org["org_headers"], name="P611-Create")

    create_1 = client.post(
        BASE,
        headers=org["org_headers"],
        json={"draft_type": "ai_system_attention_brief", "scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assert create_1.status_code == 201
    s1 = create_1.json()
    assert s1["snapshot_version"] == 1
    assert s1["previous_snapshot_id"] is None
    assert s1["snapshot_sha256"] == _snapshot_hash_from_response(s1)

    create_2 = client.post(
        BASE,
        headers=org["org_headers"],
        json={"draft_type": "ai_system_attention_brief", "scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assert create_2.status_code == 201
    s2 = create_2.json()
    assert s2["snapshot_version"] == 2
    assert s2["previous_snapshot_id"] == s1["id"]
    assert s2["source_context_hash"] == s1["source_context_hash"]
    assert s2["snapshot_sha256"] == _snapshot_hash_from_response(s2)

    audit_actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        ).all()
    }
    assert "governance_copilot_draft_snapshot.created" in audit_actions


def test_phase611_scope_support_and_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p611-scope-1")
    org2 = bootstrap_org_user(client, email_prefix="p611-scope-2")

    ai, assessment, _ = _seed(client, org1["org_headers"], name="P611-Scope")
    reco_snapshot = _create_snapshot(client, org1["org_headers"], scope_type="risk_assessment", scope_id=assessment["id"])

    org_resp = client.post(BASE, headers=org1["org_headers"], json={"draft_type": "executive_risk_summary", "scope_type": "organization"})
    ai_resp = client.post(BASE, headers=org1["org_headers"], json={"draft_type": "ai_system_attention_brief", "scope_type": "ai_system", "scope_id": ai["id"]})
    assess_resp = client.post(BASE, headers=org1["org_headers"], json={"draft_type": "risk_assessment_review_brief", "scope_type": "risk_assessment", "scope_id": assessment["id"]})
    reco_resp = client.post(BASE, headers=org1["org_headers"], json={"draft_type": "recommendation_snapshot_summary", "scope_type": "recommendation_snapshot", "scope_id": reco_snapshot["id"]})
    assert org_resp.status_code == 201
    assert ai_resp.status_code == 201
    assert assess_resp.status_code == 201
    assert reco_resp.status_code == 201

    cross = client.post(
        BASE,
        headers=org2["org_headers"],
        json={"draft_type": "ai_system_attention_brief", "scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assert cross.status_code == 404

    cross_detail = client.get(f"{BASE}/{ai_resp.json()['id']}", headers=org2["org_headers"])
    assert cross_detail.status_code == 404


def test_phase611_diff_list_latest_summary_and_no_source_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p611-diff")
    ai, _, classification = _seed(client, org["org_headers"], name="P611-Diff")

    s1_resp = client.post(
        BASE,
        headers=org["org_headers"],
        json={"draft_type": "ai_system_attention_brief", "scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assert s1_resp.status_code == 201
    s1 = s1_resp.json()

    signal_id = db_session.execute(
        select(GovernanceSignal.id).where(
            GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]),
            GovernanceSignal.entity_type == "risk_classification",
            GovernanceSignal.entity_id == uuid.UUID(classification["id"]),
            GovernanceSignal.status == "open",
        )
    ).scalars().first()
    assert signal_id is not None
    dismiss = client.post(
        f"/api/v1/ai-governance/signals/{signal_id}/dismiss",
        headers=org["org_headers"],
        json={"reason": "diff-change"},
    )
    assert dismiss.status_code == 200

    before_signal_statuses = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        )
        .scalars()
        .all()
    }
    before_dispositions = int(
        db_session.execute(
            select(func.count(GovernanceRecommendationActionDisposition.id)).where(
                GovernanceRecommendationActionDisposition.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())

    s2_resp = client.post(
        BASE,
        headers=org["org_headers"],
        json={"draft_type": "ai_system_attention_brief", "scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assert s2_resp.status_code == 201
    s2 = s2_resp.json()
    assert s2["snapshot_version"] == 2
    assert isinstance(s2.get("diff_from_previous_json"), dict)

    diff_default = client.get(f"{BASE}/{s2['id']}/diff", headers=org["org_headers"])
    assert diff_default.status_code == 200
    d1 = diff_default.json()
    assert d1["base_snapshot_id"] == s2["id"]
    assert d1["compare_snapshot_id"] == s1["id"]
    assert (
        d1["executive_summary_changed"]
        or d1["added_key_findings"]
        or d1["removed_key_findings"]
        or d1["added_next_steps"]
        or d1["removed_next_steps"]
    )

    diff_explicit = client.get(
        f"{BASE}/{s2['id']}/diff",
        headers=org["org_headers"],
        params={"compare_to_snapshot_id": s1["id"]},
    )
    assert diff_explicit.status_code == 200

    listed = client.get(
        f"{BASE}?draft_type=ai_system_attention_brief&scope_type=ai_system&scope_id={ai['id']}",
        headers=org["org_headers"],
    )
    assert listed.status_code == 200
    assert len(listed.json()) >= 2

    latest = client.get(
        f"{BASE}/latest",
        headers=org["org_headers"],
        params={"draft_type": "ai_system_attention_brief", "scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == s2["id"]

    detail = client.get(f"{BASE}/{s2['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["id"] == s2["id"]

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    sbody = summary.json()
    assert sbody["total_snapshots"] >= 2
    assert sbody["by_draft_type"].get("ai_system_attention_brief", 0) >= 2
    assert sbody["by_scope_type"].get("ai_system", 0) >= 2

    after_signal_statuses = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        )
        .scalars()
        .all()
    }
    after_dispositions = int(
        db_session.execute(
            select(func.count(GovernanceRecommendationActionDisposition.id)).where(
                GovernanceRecommendationActionDisposition.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())

    assert after_signal_statuses == before_signal_statuses
    assert after_dispositions == before_dispositions
    assert after_tasks == before_tasks
    assert after_reviews == before_reviews


def test_phase611_contract_group_and_read_only_no_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p611-contract")
    ai, _, _ = _seed(client, org["org_headers"], name="P611-Contract")

    contracts = client.get("/api/v1/ai-governance/contracts/phase6", headers=org["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"]: g for g in contracts.json()["groups"]}
    assert "governance_copilot_draft_snapshots" in groups

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    _ = client.post(
        f"{BASE}/preview",
        headers=org["org_headers"],
        json={"draft_type": "ai_system_attention_brief", "scope_type": "ai_system", "scope_id": ai["id"]},
    )
    _ = client.get(f"{BASE}/summary", headers=org["org_headers"])
    _ = client.get(
        f"{BASE}/latest",
        headers=org["org_headers"],
        params={"draft_type": "ai_system_attention_brief", "scope_type": "ai_system", "scope_id": ai["id"]},
    )
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert before_audit == after_audit
