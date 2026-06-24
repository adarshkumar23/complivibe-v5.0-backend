import uuid
from datetime import UTC, datetime, timedelta

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.ai_system_governance_review_plan_constraint import AISystemGovernanceReviewPlanConstraint
from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={"name": name, "system_type": "agent"},
    )
    assert response.status_code == 201
    return response.json()


def _create_template(client, headers: dict[str, str], *, review_type: str = "pre_production_review") -> dict:
    response = client.post(
        "/api/v1/ai-governance/review-recurrence-templates",
        headers=headers,
        json={
            "name": f"Template {review_type}",
            "review_type": review_type,
            "cadence_type": "years",
            "interval_value": 1,
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_constraint(
    client,
    headers: dict[str, str],
    *,
    target_review_type: str = "pre_production_review",
    prerequisite_review_type: str = "initial_review",
    constraint_type: str = "prerequisite_completed",
    enforcement_mode: str = "block",
    min_gap_days: int | None = None,
    max_gap_days: int | None = None,
    status: str = "active",
) -> dict:
    payload = {
        "name": "Constraint-1",
        "target_review_type": target_review_type,
        "prerequisite_review_type": prerequisite_review_type,
        "constraint_type": constraint_type,
        "enforcement_mode": enforcement_mode,
        "status": status,
    }
    if min_gap_days is not None:
        payload["min_gap_days"] = min_gap_days
    if max_gap_days is not None:
        payload["max_gap_days"] = max_gap_days
    response = client.post("/api/v1/ai-governance/review-plan-constraints", headers=headers, json=payload)
    return response


def _create_and_complete_review(client, headers: dict[str, str], ai_system_id: str, *, review_type: str) -> dict:
    created = client.post(
        f"/api/v1/ai-systems/{ai_system_id}/governance-reviews",
        headers=headers,
        json={"review_type": review_type, "title": f"{review_type} review"},
    )
    assert created.status_code == 201
    complete = client.post(
        f"/api/v1/ai-systems/{ai_system_id}/governance-reviews/{created.json()['id']}/complete",
        headers=headers,
        json={"outcome": "approved"},
    )
    assert complete.status_code == 200
    return complete.json()


def test_phase55_constraint_crud_validation_summary_and_audit(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p55-org1")
    org2 = bootstrap_org_user(client, email_prefix="p55-org2")
    headers = org1["org_headers"]

    created = _create_constraint(client, headers)
    assert created.status_code == 201
    constraint = created.json()

    bad_review_type = client.post(
        "/api/v1/ai-governance/review-plan-constraints",
        headers=headers,
        json={
            "name": "bad",
            "target_review_type": "nope",
            "prerequisite_review_type": "initial_review",
            "constraint_type": "prerequisite_completed",
            "enforcement_mode": "block",
        },
    )
    assert bad_review_type.status_code == 422

    bad_type = _create_constraint(client, headers, constraint_type="bad_type")
    assert bad_type.status_code == 422

    bad_mode = _create_constraint(client, headers, enforcement_mode="bad_mode")
    assert bad_mode.status_code == 422

    bad_gap = _create_constraint(client, headers, constraint_type="prerequisite_window", min_gap_days=10, max_gap_days=2)
    assert bad_gap.status_code in {400, 422}

    listed_org1 = client.get("/api/v1/ai-governance/review-plan-constraints", headers=headers)
    assert listed_org1.status_code == 200
    assert any(item["id"] == constraint["id"] for item in listed_org1.json())

    listed_org2 = client.get("/api/v1/ai-governance/review-plan-constraints", headers=org2["org_headers"])
    assert listed_org2.status_code == 200
    assert all(item["id"] != constraint["id"] for item in listed_org2.json())

    updated = client.patch(
        f"/api/v1/ai-governance/review-plan-constraints/{constraint['id']}",
        headers=headers,
        json={"name": "Constraint updated", "enforcement_mode": "warn"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Constraint updated"
    assert updated.json()["enforcement_mode"] == "warn"

    archived = client.post(
        f"/api/v1/ai-governance/review-plan-constraints/{constraint['id']}/archive",
        headers=headers,
        json={"reason": "retired"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    row = (
        db_session.query(AISystemGovernanceReviewPlanConstraint)
        .filter(AISystemGovernanceReviewPlanConstraint.id == uuid.UUID(constraint["id"]))
        .one()
    )
    assert row.archived_at is not None

    cannot_update_archived = client.patch(
        f"/api/v1/ai-governance/review-plan-constraints/{constraint['id']}",
        headers=headers,
        json={"name": "nope"},
    )
    assert cannot_update_archived.status_code == 400

    summary = client.get("/api/v1/ai-governance/review-plan-constraints/summary", headers=headers)
    assert summary.status_code == 200
    sum_body = summary.json()
    assert sum_body["archived_constraints"] >= 1
    assert sum_body["warn_constraints"] >= 0
    assert "prerequisite_completed" in sum_body["by_constraint_type"]

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_review_plan_constraint.created" in actions
    assert "ai_system_governance_review_plan_constraint.updated" in actions
    assert "ai_system_governance_review_plan_constraint.archived" in actions


def test_phase55_generate_plan_constraints_block_warn_and_ignore(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p55-generate")
    headers = owner["org_headers"]
    org_id = uuid.UUID(owner["organization_id"])

    ai_pass = _create_ai_system(client, headers, name="AI pass")
    ai_fail = _create_ai_system(client, headers, name="AI fail")

    _create_and_complete_review(client, headers, ai_pass["id"], review_type="initial_review")

    template = _create_template(client, headers, review_type="pre_production_review")
    block_constraint = _create_constraint(client, headers, enforcement_mode="block")
    assert block_constraint.status_code == 201
    warn_constraint = _create_constraint(client, headers, enforcement_mode="warn")
    assert warn_constraint.status_code == 201

    start_from = (datetime.now(UTC).replace(microsecond=0) + timedelta(days=30)).isoformat()

    selected_warn_only = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template['id']}/generate-plan",
        headers=headers,
        json={
            "dry_run": True,
            "horizon_days": 1,
            "start_from": start_from,
            "apply_constraints": True,
            "constraint_ids": [warn_constraint.json()["id"]],
        },
    )
    assert selected_warn_only.status_code == 200
    selected_body = selected_warn_only.json()
    assert selected_body["planned_count"] == 2
    assert selected_body["skipped_count"] == 0
    fail_item = next(item for item in selected_body["planned_reviews"] if item["ai_system_id"] == ai_fail["id"])
    assert any(result["warning"] is True for result in fail_item["constraint_results"])

    blocked_preview = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template['id']}/generate-plan",
        headers=headers,
        json={
            "dry_run": True,
            "horizon_days": 1,
            "start_from": start_from,
            "apply_constraints": True,
            "constraint_ids": [block_constraint.json()["id"]],
        },
    )
    assert blocked_preview.status_code == 200
    blocked_body = blocked_preview.json()
    assert blocked_body["planned_count"] == 1
    assert blocked_body["skipped_count"] == 1
    assert blocked_body["skipped_reviews"][0]["reason"] == "constraint_blocked"
    assert "deterministic planning rules" in blocked_body["caveat"]

    ignored = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template['id']}/generate-plan",
        headers=headers,
        json={
            "dry_run": True,
            "horizon_days": 1,
            "start_from": start_from,
            "apply_constraints": False,
        },
    )
    assert ignored.status_code == 200
    ignored_body = ignored.json()
    assert ignored_body["planned_count"] == 2
    assert ignored_body["skipped_count"] == 0

    # Cross-tenant constraint id must fail validation.
    outsider = bootstrap_org_user(client, email_prefix="p55-outsider")
    outsider_constraint = _create_constraint(client, outsider["org_headers"], enforcement_mode="block")
    assert outsider_constraint.status_code == 201
    cross_tenant = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template['id']}/generate-plan",
        headers=headers,
        json={
            "dry_run": True,
            "horizon_days": 1,
            "start_from": start_from,
            "apply_constraints": True,
            "constraint_ids": [outsider_constraint.json()["id"]],
        },
    )
    assert cross_tenant.status_code == 404

    # Live apply creates only non-blocked review(s).
    live = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template['id']}/generate-plan",
        headers=headers,
        json={
            "dry_run": False,
            "horizon_days": 1,
            "start_from": start_from,
            "apply_constraints": True,
            "constraint_ids": [block_constraint.json()["id"]],
        },
    )
    assert live.status_code == 200
    live_body = live.json()
    assert live_body["created_count"] == 1
    assert live_body["skipped_count"] == 1

    rows = db_session.query(AISystemGovernanceReview).filter(AISystemGovernanceReview.organization_id == org_id).all()
    created_target_reviews = [row for row in rows if row.review_type == "pre_production_review"]
    assert len(created_target_reviews) == 1
    assert created_target_reviews[0].status == "pending"
    assert created_target_reviews[0].started_at is None

    run_detail = client.get(
        f"/api/v1/ai-governance/review-plan-runs/{live_body['run_id']}",
        headers=headers,
    )
    assert run_detail.status_code == 200
    result_json = run_detail.json()["result_json"]
    assert isinstance(result_json["planned_reviews"][0]["constraint_results"], list)
    assert isinstance(result_json["skipped_reviews"][0]["constraint_results"], list)

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_review_plan.previewed" in actions
    assert "ai_system_governance_review_plan.applied" in actions
