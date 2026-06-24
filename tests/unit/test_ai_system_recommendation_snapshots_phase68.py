import hashlib
import json
import uuid

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
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

BASE = "/api/v1/ai-governance/recommendations/snapshots"


def _seed_candidate_actions_context(client, headers: dict[str, str], *, name: str = "P68-AI") -> tuple[dict, dict, dict]:
    ai = _create_ai_system(client, headers, name=name)
    assessment = _create_assessment(client, headers, ai["id"], risk_level="high")
    _create_taxonomy(client, headers, is_default=True)
    classification = _create_classification(client, headers, assessment["id"], confidence_level="low")
    _create_signal_flow(client, headers, classification["id"])
    return ai, assessment, classification


def _payload_sha256(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase68_preview_read_only_no_audit_no_rows(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p68-preview")
    _seed_candidate_actions_context(client, org["org_headers"], name="P68-Preview")

    before_rows = int(db_session.execute(select(func.count(GovernanceRecommendationSnapshot.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    preview = client.post(
        f"{BASE}/preview",
        headers=org["org_headers"],
        json={"scope_type": "organization", "filters": {"priority_band": "high"}},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["scope_type"] == "organization"
    assert body["scope_id"] is None
    assert body["candidate_count"] >= 1
    assert isinstance(body["source_signal_ids"], list)
    assert "deterministic candidate actions" in body["caveat"].lower()

    after_rows = int(db_session.execute(select(func.count(GovernanceRecommendationSnapshot.id))).scalar_one())
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_rows == before_rows
    assert after_audit == before_audit


def test_phase68_create_snapshot_version_hash_previous_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p68-create")
    _seed_candidate_actions_context(client, org["org_headers"], name="P68-Create")

    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())

    create_1 = client.post(f"{BASE}", headers=org["org_headers"], json={"scope_type": "organization"})
    assert create_1.status_code == 201
    s1 = create_1.json()
    assert s1["snapshot_version"] == 1
    assert s1["previous_snapshot_id"] is None
    assert s1["snapshot_sha256"] == _payload_sha256(s1["recommendation_payload_json"])

    create_2 = client.post(f"{BASE}", headers=org["org_headers"], json={"scope_type": "organization"})
    assert create_2.status_code == 201
    s2 = create_2.json()
    assert s2["snapshot_version"] == 2
    assert s2["previous_snapshot_id"] == s1["id"]
    assert s2["source_candidate_hash"] == s1["source_candidate_hash"]

    audit_actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        ).all()
    }
    assert "governance_recommendation_snapshot.created" in audit_actions

    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    assert after_tasks == before_tasks
    assert after_reviews == before_reviews


def test_phase68_scope_endpoints_and_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p68-scope-1")
    org2 = bootstrap_org_user(client, email_prefix="p68-scope-2")

    ai, assessment, _ = _seed_candidate_actions_context(client, org1["org_headers"], name="P68-Scope")

    org_scope = client.post(f"{BASE}", headers=org1["org_headers"], json={"scope_type": "organization"})
    ai_scope = client.post(
        f"{BASE}",
        headers=org1["org_headers"],
        json={"scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assessment_scope = client.post(
        f"{BASE}",
        headers=org1["org_headers"],
        json={"scope_type": "risk_assessment", "scope_id": assessment["id"]},
    )
    assert org_scope.status_code == 201
    assert ai_scope.status_code == 201
    assert assessment_scope.status_code == 201

    latest_ai = client.get(
        f"{BASE}/latest",
        headers=org1["org_headers"],
        params={"scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assert latest_ai.status_code == 200
    assert latest_ai.json()["scope_id"] == ai["id"]

    cross_latest = client.get(
        f"{BASE}/latest",
        headers=org2["org_headers"],
        params={"scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assert cross_latest.status_code == 404

    cross_detail = client.get(
        f"{BASE}/{ai_scope.json()['id']}",
        headers=org2["org_headers"],
    )
    assert cross_detail.status_code == 404


def test_phase68_diff_list_summary_and_no_signal_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p68-diff")
    ai, assessment, classification = _seed_candidate_actions_context(client, org["org_headers"], name="P68-Diff")

    create_1 = client.post(
        f"{BASE}",
        headers=org["org_headers"],
        json={"scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assert create_1.status_code == 201
    s1 = create_1.json()

    # Change open-signal set without mutating non-signal source records.
    to_dismiss = db_session.execute(
        select(GovernanceSignal.id).where(
            GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]),
            GovernanceSignal.entity_type == "risk_classification",
            GovernanceSignal.entity_id == uuid.UUID(classification["id"]),
            GovernanceSignal.status == "open",
        )
    ).scalars().first()
    assert to_dismiss is not None
    dismiss = client.post(
        f"/api/v1/ai-governance/signals/{to_dismiss}/dismiss",
        headers=org["org_headers"],
        json={"reason": "manual test change"},
    )
    assert dismiss.status_code == 200

    create_2 = client.post(
        f"{BASE}",
        headers=org["org_headers"],
        json={"scope_type": "ai_system", "scope_id": ai["id"]},
    )
    assert create_2.status_code == 201
    s2 = create_2.json()

    diff_default = client.get(f"{BASE}/{s2['id']}/diff", headers=org["org_headers"])
    assert diff_default.status_code == 200
    d1 = diff_default.json()
    assert d1["base_snapshot_id"] == s2["id"]
    assert d1["compare_snapshot_id"] == s1["id"]
    assert d1["added_actions"] or d1["removed_actions"] or d1["changed_actions"]

    diff_explicit = client.get(
        f"{BASE}/{s2['id']}/diff",
        headers=org["org_headers"],
        params={"compare_to_snapshot_id": s1["id"]},
    )
    assert diff_explicit.status_code == 200

    listed = client.get(f"{BASE}?scope_type=ai_system&scope_id={ai['id']}", headers=org["org_headers"])
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) >= 2

    detail = client.get(f"{BASE}/{s2['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["id"] == s2["id"]

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    sbody = summary.json()
    assert sbody["total_snapshots"] >= 2
    assert sbody["by_scope_type"].get("ai_system", 0) >= 2
    assert sbody["scopes_with_snapshots"] >= 1


def test_phase68_contract_group_and_read_only_endpoints_no_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p68-contract")
    ai, _, _ = _seed_candidate_actions_context(client, org["org_headers"], name="P68-Contract")

    contracts = client.get("/api/v1/ai-governance/contracts/phase6", headers=org["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"]: g for g in contracts.json()["groups"]}
    assert "governance_recommendation_snapshots" in groups

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    _ = client.post(
        f"{BASE}/preview",
        headers=org["org_headers"],
        json={"scope_type": "ai_system", "scope_id": ai["id"]},
    )
    _ = client.get(f"{BASE}/summary", headers=org["org_headers"])
    _ = client.get(
        f"{BASE}/latest",
        headers=org["org_headers"],
        params={"scope_type": "ai_system", "scope_id": ai["id"]},
    )
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert before_audit == after_audit
