import uuid
from datetime import UTC, datetime, timedelta

from app.models.ai_system_governance_operator_acknowledgement import AISystemGovernanceOperatorAcknowledgement
from app.models.ai_system_governance_review import AISystemGovernanceReview
from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={"name": name, "system_type": "agent"},
    )
    assert response.status_code == 201
    return response.json()


def _create_pack(client, headers: dict[str, str], *, name: str = "Guard Pack") -> dict:
    response = client.post(
        "/api/v1/ai-governance/review-sequence-packs",
        headers=headers,
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 201
    return response.json()


def _create_step(client, headers: dict[str, str], pack_id: str, *, step_order: int = 1, review_type: str = "initial_review") -> dict:
    response = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack_id}/steps",
        headers=headers,
        json={
            "step_order": step_order,
            "review_type": review_type,
            "offset_days_from_start": 0,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_phase57_freeze_windows_guardrail_check_and_summary(client):
    org1 = bootstrap_org_user(client, email_prefix="p57-org1")
    org2 = bootstrap_org_user(client, email_prefix="p57-org2")
    headers1 = org1["org_headers"]
    headers2 = org2["org_headers"]

    pack1 = _create_pack(client, headers1, name="Org1 Pack")
    pack2 = _create_pack(client, headers2, name="Org2 Pack")

    now = datetime.now(UTC).replace(microsecond=0)

    invalid_dates = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers1,
        json={
            "name": "Bad dates",
            "starts_at": (now + timedelta(days=1)).isoformat(),
            "ends_at": now.isoformat(),
            "reason": "bad",
        },
    )
    assert invalid_dates.status_code == 400

    invalid_scope = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers1,
        json={
            "name": "Cross tenant scope",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "sequence_pack",
            "scope_json": {"sequence_pack_ids": [pack2["id"]]},
            "reason": "cross tenant check",
        },
    )
    assert invalid_scope.status_code == 400

    created = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers1,
        json={
            "name": "Archived later",
            "starts_at": (now - timedelta(hours=2)).isoformat(),
            "ends_at": (now + timedelta(days=2)).isoformat(),
            "reason": "maintenance",
            "status": "active",
        },
    )
    assert created.status_code == 201
    freeze_archived = created.json()

    listing = client.get(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers1,
        params={"active_at": now.isoformat()},
    )
    assert listing.status_code == 200
    assert any(item["id"] == freeze_archived["id"] for item in listing.json())

    updated = client.patch(
        f"/api/v1/ai-governance/guardrails/freeze-windows/{freeze_archived['id']}",
        headers=headers1,
        json={"name": "Archived later updated", "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "inactive"

    archived = client.post(
        f"/api/v1/ai-governance/guardrails/freeze-windows/{freeze_archived['id']}/archive",
        headers=headers1,
        json={"reason": "completed"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    active_freeze = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers1,
        json={
            "name": "Global freeze",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "reason": "quarterly release lock",
            "scope_type": "all_ai_governance",
            "status": "active",
        },
    )
    assert active_freeze.status_code == 201

    inactive_freeze = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers1,
        json={
            "name": "Inactive freeze",
            "starts_at": (now - timedelta(days=1)).isoformat(),
            "ends_at": (now + timedelta(days=3)).isoformat(),
            "reason": "future optional",
            "scope_type": "all_ai_governance",
            "status": "inactive",
        },
    )
    assert inactive_freeze.status_code == 201

    check = client.post(
        "/api/v1/ai-governance/guardrails/check",
        headers=headers1,
        json={
            "action_type": "sequence_apply",
            "sequence_pack_id": pack1["id"],
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=1)).isoformat(),
        },
    )
    assert check.status_code == 200
    check_body = check.json()
    assert check_body["blocked"] is True
    assert check_body["matching_freeze_windows"]
    assert check_body["required_acknowledgement_text"] == "CONFIRM_SEQUENCE_APPLY_DURING_FREEZE"

    summary = client.get("/api/v1/ai-governance/guardrails/summary", headers=headers1)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["active_freeze_windows"] == 1
    assert summary_body["inactive_freeze_windows"] == 1
    assert summary_body["archived_freeze_windows"] == 1
    assert summary_body["active_now_freeze_windows"] == 1
    assert summary_body["acknowledgements_total"] == 0
    assert summary_body["freeze_overrides_total"] == 0


def test_phase57_sequence_freeze_acknowledgements_and_audit(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p57-seq1")
    org2 = bootstrap_org_user(client, email_prefix="p57-seq2")
    headers1 = org1["org_headers"]
    headers2 = org2["org_headers"]

    ai1 = _create_ai_system(client, headers1, name="Freeze AI")
    _create_ai_system(client, headers2, name="Other Org AI")

    pack1 = _create_pack(client, headers1, name="Freeze Pack")
    _create_step(client, headers1, pack1["id"], step_order=1, review_type="initial_review")

    pack2 = _create_pack(client, headers2, name="No Freeze Pack")
    _create_step(client, headers2, pack2["id"], step_order=1, review_type="initial_review")

    now = datetime.now(UTC).replace(microsecond=0)
    create_freeze = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers1,
        json={
            "name": "Active sequence freeze",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "all_ai_governance",
            "reason": "release hold",
            "status": "active",
        },
    )
    assert create_freeze.status_code == 201

    dry_run = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack1['id']}/generate-sequence",
        headers=headers1,
        json={"dry_run": True, "ai_system_ids": [ai1["id"]], "start_from": now.isoformat()},
    )
    assert dry_run.status_code == 200
    dry_body = dry_run.json()
    assert dry_body["created_count"] == 0
    assert dry_body["guardrail_results"]["blocked"] is True
    assert dry_body["guardrail_results"]["matching_freeze_windows"]

    empty_acks = client.get("/api/v1/ai-governance/guardrails/operator-acknowledgements", headers=headers1)
    assert empty_acks.status_code == 200
    assert empty_acks.json() == []

    blocked_no_ack = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack1['id']}/generate-sequence",
        headers=headers1,
        json={"dry_run": False, "ai_system_ids": [ai1["id"]], "start_from": now.isoformat()},
    )
    assert blocked_no_ack.status_code == 400

    blocked_bad_ack = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack1['id']}/generate-sequence",
        headers=headers1,
        json={
            "dry_run": False,
            "ai_system_ids": [ai1["id"]],
            "start_from": now.isoformat(),
            "override_freeze": True,
            "override_reason": "urgent",
            "acknowledgement_text": "WRONG",
        },
    )
    assert blocked_bad_ack.status_code == 400

    blocked_no_reason = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack1['id']}/generate-sequence",
        headers=headers1,
        json={
            "dry_run": False,
            "ai_system_ids": [ai1["id"]],
            "start_from": now.isoformat(),
            "override_freeze": True,
            "acknowledgement_text": "CONFIRM_SEQUENCE_APPLY_DURING_FREEZE",
        },
    )
    assert blocked_no_reason.status_code == 400

    live_ok = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack1['id']}/generate-sequence",
        headers=headers1,
        json={
            "dry_run": False,
            "ai_system_ids": [ai1["id"]],
            "start_from": now.isoformat(),
            "override_freeze": True,
            "override_reason": "Emergency approved",
            "acknowledgement_text": "CONFIRM_SEQUENCE_APPLY_DURING_FREEZE",
        },
    )
    assert live_ok.status_code == 200
    assert live_ok.json()["created_count"] >= 1
    assert live_ok.json()["guardrail_results"]["blocked"] is True

    created_reviews = (
        db_session.query(AISystemGovernanceReview)
        .filter(
            AISystemGovernanceReview.organization_id == uuid.UUID(org1["organization_id"]),
            AISystemGovernanceReview.ai_system_id == uuid.UUID(ai1["id"]),
            AISystemGovernanceReview.review_type == "initial_review",
        )
        .all()
    )
    assert created_reviews
    assert all(item.status == "pending" for item in created_reviews)

    ack_rows = (
        db_session.query(AISystemGovernanceOperatorAcknowledgement)
        .filter(AISystemGovernanceOperatorAcknowledgement.organization_id == uuid.UUID(org1["organization_id"]))
        .all()
    )
    assert len(ack_rows) == 1
    assert ack_rows[0].override_freeze is True

    ack_list_org1 = client.get("/api/v1/ai-governance/guardrails/operator-acknowledgements", headers=headers1)
    ack_list_org2 = client.get("/api/v1/ai-governance/guardrails/operator-acknowledgements", headers=headers2)
    assert ack_list_org1.status_code == 200
    assert ack_list_org2.status_code == 200
    assert len(ack_list_org1.json()) == 1
    assert ack_list_org2.json() == []

    outside = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack2['id']}/generate-sequence",
        headers=headers2,
        json={"dry_run": False, "start_from": now.isoformat()},
    )
    assert outside.status_code == 200
    assert outside.json()["created_count"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=headers1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_freeze_window.created" in actions
    assert "ai_system_governance_operator_acknowledgement.created" in actions
    assert "ai_system_governance_review_sequence.previewed" in actions
    assert "ai_system_governance_review_sequence.applied" in actions

    summary = client.get("/api/v1/ai-governance/guardrails/summary", headers=headers1)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["acknowledgements_total"] == 1
    assert summary_body["freeze_overrides_total"] == 1
