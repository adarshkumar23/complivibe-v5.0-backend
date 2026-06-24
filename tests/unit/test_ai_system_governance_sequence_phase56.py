import uuid
from datetime import UTC, datetime

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.ai_system_governance_review_sequence_pack import AISystemGovernanceReviewSequencePack
from app.models.ai_system_governance_review_sequence_step import AISystemGovernanceReviewSequenceStep
from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={"name": name, "system_type": "agent"},
    )
    assert response.status_code == 201
    return response.json()


def _create_policy(client, headers: dict[str, str], *, review_type: str = "initial_review", status: str = "active") -> dict:
    response = client.post(
        "/api/v1/ai-governance/review-reminder-policies",
        headers=headers,
        json={
            "name": f"Policy {review_type}",
            "review_type": review_type,
            "days_before_due": 1,
            "overdue_after_days": 0,
            "escalation_after_days": 1,
            "notify_assignee": False,
            "status": status,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_pack(client, headers: dict[str, str], *, name: str = "Rollout Pack") -> dict:
    response = client.post(
        "/api/v1/ai-governance/review-sequence-packs",
        headers=headers,
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 201
    return response.json()


def _create_step(
    client,
    headers: dict[str, str],
    pack_id: str,
    *,
    step_order: int,
    review_type: str,
    offset_days: int,
    assignee_id: str | None = None,
    policy_id: str | None = None,
    require_previous_step_planned: bool = True,
) -> dict:
    payload = {
        "step_order": step_order,
        "review_type": review_type,
        "offset_days_from_start": offset_days,
        "require_previous_step_planned": require_previous_step_planned,
        "status": "active",
    }
    if assignee_id is not None:
        payload["default_assigned_to_user_id"] = assignee_id
    if policy_id is not None:
        payload["default_reminder_policy_id"] = policy_id
    response = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack_id}/steps",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def _create_and_complete_review(client, headers: dict[str, str], ai_system_id: str, review_type: str) -> None:
    created = client.post(
        f"/api/v1/ai-systems/{ai_system_id}/governance-reviews",
        headers=headers,
        json={"review_type": review_type, "title": f"{review_type} complete"},
    )
    assert created.status_code == 201
    completed = client.post(
        f"/api/v1/ai-systems/{ai_system_id}/governance-reviews/{created.json()['id']}/complete",
        headers=headers,
        json={"outcome": "approved"},
    )
    assert completed.status_code == 200


def test_phase56_sequence_pack_and_step_crud_validation_and_audit(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p56-org1")
    org2 = bootstrap_org_user(client, email_prefix="p56-org2")
    headers1 = org1["org_headers"]

    pack = _create_pack(client, headers1, name="Pack A")

    listed = client.get("/api/v1/ai-governance/review-sequence-packs", headers=headers1)
    assert listed.status_code == 200
    assert any(item["id"] == pack["id"] for item in listed.json())

    updated = client.patch(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}",
        headers=headers1,
        json={"name": "Pack A Updated", "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Pack A Updated"
    assert updated.json()["status"] == "inactive"

    reactivated = client.patch(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}",
        headers=headers1,
        json={"status": "active"},
    )
    assert reactivated.status_code == 200

    policy = _create_policy(client, headers1, review_type="initial_review", status="active")

    step1 = _create_step(
        client,
        headers1,
        pack["id"],
        step_order=1,
        review_type="initial_review",
        offset_days=0,
        assignee_id=org1["user_id"],
        policy_id=policy["id"],
    )

    dup_order = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/steps",
        headers=headers1,
        json={"step_order": 1, "review_type": "change_review", "offset_days_from_start": 5},
    )
    assert dup_order.status_code == 400

    invalid_review_type = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/steps",
        headers=headers1,
        json={"step_order": 2, "review_type": "bad_review", "offset_days_from_start": 1},
    )
    assert invalid_review_type.status_code == 422

    invalid_offset = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/steps",
        headers=headers1,
        json={"step_order": 2, "review_type": "change_review", "offset_days_from_start": -1},
    )
    assert invalid_offset.status_code == 422

    other_policy = _create_policy(client, org2["org_headers"], review_type="initial_review", status="active")
    cross_policy = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/steps",
        headers=headers1,
        json={
            "step_order": 2,
            "review_type": "change_review",
            "offset_days_from_start": 2,
            "default_reminder_policy_id": other_policy["id"],
        },
    )
    assert cross_policy.status_code == 404

    cross_assignee = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/steps",
        headers=headers1,
        json={
            "step_order": 2,
            "review_type": "change_review",
            "offset_days_from_start": 2,
            "default_assigned_to_user_id": org2["user_id"],
        },
    )
    assert cross_assignee.status_code == 400

    step2 = _create_step(
        client,
        headers1,
        pack["id"],
        step_order=2,
        review_type="change_review",
        offset_days=2,
    )

    steps = client.get(f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/steps", headers=headers1)
    assert steps.status_code == 200
    assert [item["step_order"] for item in steps.json()][:2] == [1, 2]

    updated_step = client.patch(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/steps/{step2['id']}",
        headers=headers1,
        json={"offset_days_from_start": 3},
    )
    assert updated_step.status_code == 200
    assert updated_step.json()["offset_days_from_start"] == 3

    archived_step = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/steps/{step2['id']}/archive",
        headers=headers1,
        json={"reason": "obsolete"},
    )
    assert archived_step.status_code == 200
    assert archived_step.json()["status"] == "archived"

    cannot_update_archived_step = client.patch(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/steps/{step2['id']}",
        headers=headers1,
        json={"offset_days_from_start": 4},
    )
    assert cannot_update_archived_step.status_code == 400

    archived_pack = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/archive",
        headers=headers1,
        json={"reason": "retired"},
    )
    assert archived_pack.status_code == 200
    assert archived_pack.json()["status"] == "archived"

    cannot_update_archived_pack = client.patch(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}",
        headers=headers1,
        json={"name": "Nope"},
    )
    assert cannot_update_archived_pack.status_code == 400

    pack_row = (
        db_session.query(AISystemGovernanceReviewSequencePack)
        .filter(AISystemGovernanceReviewSequencePack.id == uuid.UUID(pack["id"]))
        .one()
    )
    assert pack_row.archived_at is not None

    step_row = (
        db_session.query(AISystemGovernanceReviewSequenceStep)
        .filter(AISystemGovernanceReviewSequenceStep.id == uuid.UUID(step1["id"]))
        .one()
    )
    assert step_row.status == "active"

    logs = client.get("/api/v1/audit-logs", headers=headers1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_review_sequence_pack.created" in actions
    assert "ai_system_governance_review_sequence_pack.updated" in actions
    assert "ai_system_governance_review_sequence_pack.archived" in actions
    assert "ai_system_governance_review_sequence_step.created" in actions
    assert "ai_system_governance_review_sequence_step.updated" in actions
    assert "ai_system_governance_review_sequence_step.archived" in actions


def test_phase56_sequence_generation_dry_run_live_constraints_runs_summary_and_audit(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p56-generate")
    headers = owner["org_headers"]
    org_id = uuid.UUID(owner["organization_id"])

    ai_ok = _create_ai_system(client, headers, name="AI OK")
    ai_warn = _create_ai_system(client, headers, name="AI WARN")
    ai_block = _create_ai_system(client, headers, name="AI BLOCK")
    ai_archived = _create_ai_system(client, headers, name="AI ARCHIVED")

    archive_ai = client.post(
        f"/api/v1/ai-systems/{ai_archived['id']}/archive",
        headers=headers,
        json={"reason": "retired"},
    )
    assert archive_ai.status_code == 200

    _create_and_complete_review(client, headers, ai_ok["id"], "periodic_review")

    pack = _create_pack(client, headers, name="Sequence Pack")
    policy_step1 = _create_policy(client, headers, review_type="initial_review", status="active")

    step1 = _create_step(
        client,
        headers,
        pack["id"],
        step_order=1,
        review_type="initial_review",
        offset_days=0,
        policy_id=policy_step1["id"],
    )
    step2 = _create_step(
        client,
        headers,
        pack["id"],
        step_order=2,
        review_type="pre_production_review",
        offset_days=10,
        require_previous_step_planned=True,
    )

    start_from = datetime.now(UTC).replace(microsecond=0)

    existing_r = client.post(
        f"/api/v1/ai-systems/{ai_ok['id']}/governance-reviews",
        headers=headers,
        json={"review_type": "initial_review", "title": "existing duplicate"},
    )
    assert existing_r.status_code == 201
    existing_sched = client.post(
        f"/api/v1/ai-systems/{ai_ok['id']}/governance-reviews/{existing_r.json()['id']}/schedule",
        headers=headers,
        json={"due_at": start_from.isoformat()},
    )
    assert existing_sched.status_code == 200

    warn_constraint = client.post(
        "/api/v1/ai-governance/review-plan-constraints",
        headers=headers,
        json={
            "name": "Warn initial",
            "target_review_type": "initial_review",
            "prerequisite_review_type": "retirement_review",
            "constraint_type": "prerequisite_completed",
            "enforcement_mode": "warn",
            "status": "active",
        },
    )
    assert warn_constraint.status_code == 201

    block_constraint = client.post(
        "/api/v1/ai-governance/review-plan-constraints",
        headers=headers,
        json={
            "name": "Block preprod",
            "target_review_type": "pre_production_review",
            "prerequisite_review_type": "periodic_review",
            "constraint_type": "prerequisite_completed",
            "enforcement_mode": "block",
            "status": "active",
        },
    )
    assert block_constraint.status_code == 201

    dry_run = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={
            "dry_run": True,
            "start_from": start_from.isoformat(),
            "apply_constraints": True,
        },
    )
    assert dry_run.status_code == 200
    dry_body = dry_run.json()
    assert dry_body["created_count"] == 0
    assert dry_body["planned_count"] > 0
    assert dry_body["run_id"] is not None
    assert "manually triggered" in dry_body["caveat"]
    assert all(item["ai_system_id"] != ai_archived["id"] for item in dry_body["planned_reviews"])

    skipped_reasons = {item["reason"] for item in dry_body["skipped_reviews"]}
    assert "duplicate_existing_review" in skipped_reasons
    assert "constraint_blocked" in skipped_reasons

    warn_items = [
        item
        for item in dry_body["planned_reviews"]
        if item["review_type"] == "initial_review" and item["ai_system_id"] in {ai_warn["id"], ai_block["id"]}
    ]
    assert warn_items
    assert any(any(result["warning"] is True for result in item["constraint_results"]) for item in warn_items)

    before_live = db_session.query(AISystemGovernanceReview).filter(AISystemGovernanceReview.organization_id == org_id).count()
    live = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={
            "dry_run": False,
            "start_from": start_from.isoformat(),
            "apply_constraints": True,
        },
    )
    assert live.status_code == 200
    live_body = live.json()
    assert live_body["created_count"] > 0
    assert live_body["created_count"] < live_body["planned_count"] + live_body["skipped_count"] + 1

    after_live = db_session.query(AISystemGovernanceReview).filter(AISystemGovernanceReview.organization_id == org_id).count()
    assert after_live > before_live

    created_rows = (
        db_session.query(AISystemGovernanceReview)
        .filter(
            AISystemGovernanceReview.organization_id == org_id,
            AISystemGovernanceReview.review_type.in_(["initial_review", "pre_production_review"]),
            AISystemGovernanceReview.requested_by_user_id == uuid.UUID(owner["user_id"]),
        )
        .all()
    )
    assert all(row.status == "pending" for row in created_rows)
    assert all(row.started_at is None for row in created_rows)

    by_ai_ok = [row for row in created_rows if str(row.ai_system_id) == ai_ok["id"]]
    if len(by_ai_ok) >= 2:
        sorted_due = sorted(row.due_at for row in by_ai_ok if row.due_at is not None)
        assert sorted_due == [row.due_at for row in sorted(by_ai_ok, key=lambda r: r.due_at)]

    no_constraints = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={
            "dry_run": True,
            "start_from": start_from.isoformat(),
            "apply_constraints": False,
            "ai_system_ids": [ai_warn["id"]],
        },
    )
    assert no_constraints.status_code == 200
    assert all(item["reason"] != "constraint_blocked" for item in no_constraints.json()["skipped_reviews"])

    runs = client.get(
        f"/api/v1/ai-governance/review-sequence-runs?sequence_pack_id={pack['id']}",
        headers=headers,
    )
    assert runs.status_code == 200
    assert len(runs.json()) >= 3

    run_detail = client.get(
        f"/api/v1/ai-governance/review-sequence-runs/{live_body['run_id']}",
        headers=headers,
    )
    assert run_detail.status_code == 200
    assert run_detail.json()["status"] == "applied"

    summary = client.get("/api/v1/ai-governance/review-sequence-summary", headers=headers)
    assert summary.status_code == 200
    sum_body = summary.json()
    assert sum_body["active_packs"] >= 1
    assert sum_body["active_steps"] >= 2
    assert sum_body["sequence_runs"] >= 3
    assert sum_body["previewed_runs"] >= 1
    assert sum_body["applied_runs"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_review_sequence.previewed" in actions
    assert "ai_system_governance_review_sequence.applied" in actions

    # Ensure archived AI did not receive generated reviews from sequence apply.
    archived_rows = [row for row in created_rows if str(row.ai_system_id) == ai_archived["id"]]
    assert archived_rows == []

    # Keep references so lints don't remove variables in assertions context.
    assert step1["step_order"] == 1
    assert step2["step_order"] == 2
