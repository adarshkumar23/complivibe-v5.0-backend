import uuid
from datetime import UTC, datetime, timedelta

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


def _create_active_policy(client, headers: dict[str, str], *, review_type: str = "periodic_review") -> dict:
    response = client.post(
        "/api/v1/ai-governance/review-reminder-policies",
        headers=headers,
        json={
            "name": "Default policy",
            "review_type": review_type,
            "days_before_due": 2,
            "overdue_after_days": 0,
            "escalation_after_days": 1,
            "notify_assignee": False,
            "status": "active",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_template(
    client,
    headers: dict[str, str],
    *,
    policy_id: str | None = None,
    assignee_id: str | None = None,
    cadence_type: str = "months",
    interval_value: int = 1,
    status: str = "active",
) -> dict:
    payload = {
        "name": "Quarterly Governance Review",
        "review_type": "periodic_review",
        "cadence_type": cadence_type,
        "interval_value": interval_value,
        "status": status,
        "default_description": "Generated from recurrence template",
        "default_checklist_json": {"items": [{"key": "check-1", "done": False}]},
    }
    if policy_id is not None:
        payload["default_reminder_policy_id"] = policy_id
    if assignee_id is not None:
        payload["default_assigned_to_user_id"] = assignee_id
    response = client.post(
        "/api/v1/ai-governance/review-recurrence-templates",
        headers=headers,
        json=payload,
    )
    return response


def test_phase54_template_create_validation_list_update_archive_and_tenant_scope(client):
    org1 = bootstrap_org_user(client, email_prefix="p54-org1")
    org2 = bootstrap_org_user(client, email_prefix="p54-org2")
    headers1 = org1["org_headers"]

    policy = _create_active_policy(client, headers1)

    invalid_cadence = _create_template(client, headers1, cadence_type="invalid", interval_value=1)
    assert invalid_cadence.status_code == 422

    invalid_interval = _create_template(client, headers1, cadence_type="weeks", interval_value=0)
    assert invalid_interval.status_code in {400, 422}

    cross_org_policy = _create_active_policy(client, org2["org_headers"])
    cross_org_template = _create_template(client, headers1, policy_id=cross_org_policy["id"])
    assert cross_org_template.status_code == 404

    inactive_policy = client.post(
        "/api/v1/ai-governance/review-reminder-policies",
        headers=headers1,
        json={
            "name": "Inactive policy",
            "review_type": "periodic_review",
            "days_before_due": 1,
            "overdue_after_days": 0,
            "escalation_after_days": 1,
            "notify_assignee": False,
            "status": "inactive",
        },
    )
    assert inactive_policy.status_code == 201
    bad_policy_state = _create_template(client, headers1, policy_id=inactive_policy.json()["id"])
    assert bad_policy_state.status_code == 400

    bad_assignee = _create_template(client, headers1, assignee_id=org2["user_id"])
    assert bad_assignee.status_code == 400

    created = _create_template(client, headers1, policy_id=policy["id"], assignee_id=org1["user_id"])
    assert created.status_code == 201
    template = created.json()

    listed_org1 = client.get("/api/v1/ai-governance/review-recurrence-templates", headers=headers1)
    assert listed_org1.status_code == 200
    assert any(row["id"] == template["id"] for row in listed_org1.json())

    listed_org2 = client.get("/api/v1/ai-governance/review-recurrence-templates", headers=org2["org_headers"])
    assert listed_org2.status_code == 200
    assert all(row["id"] != template["id"] for row in listed_org2.json())

    updated = client.patch(
        f"/api/v1/ai-governance/review-recurrence-templates/{template['id']}",
        headers=headers1,
        json={"interval_value": 2, "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["interval_value"] == 2
    assert updated.json()["status"] == "inactive"

    archived = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template['id']}/archive",
        headers=headers1,
        json={"reason": "retired template"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    cannot_update_archived = client.patch(
        f"/api/v1/ai-governance/review-recurrence-templates/{template['id']}",
        headers=headers1,
        json={"interval_value": 3},
    )
    assert cannot_update_archived.status_code == 400


def test_phase54_preview_is_deterministic_and_creates_no_reviews(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p54-preview")
    headers = owner["org_headers"]
    org_id = uuid.UUID(owner["organization_id"])

    ai1 = _create_ai_system(client, headers, name="AI-1")
    _create_ai_system(client, headers, name="AI-2")
    archived_ai = _create_ai_system(client, headers, name="AI-Archived")
    archive_resp = client.post(
        f"/api/v1/ai-systems/{archived_ai['id']}/archive",
        headers=headers,
        json={"reason": "retired"},
    )
    assert archive_resp.status_code == 200

    policy = _create_active_policy(client, headers)
    template_resp = _create_template(client, headers, policy_id=policy["id"], assignee_id=owner["user_id"], cadence_type="months")
    assert template_resp.status_code == 201
    template_id = template_resp.json()["id"]

    before_count = db_session.query(AISystemGovernanceReview).filter_by(organization_id=org_id).count()
    start_from = datetime(2026, 1, 1, tzinfo=UTC).isoformat()

    preview1 = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template_id}/generate-plan",
        headers=headers,
        json={"dry_run": True, "horizon_days": 120, "start_from": start_from},
    )
    assert preview1.status_code == 200
    body1 = preview1.json()
    assert body1["dry_run"] is True
    assert body1["planned_count"] > 0
    assert body1["created_count"] == 0
    assert body1["run_id"] is not None
    assert "manually triggered" in body1["caveat"]
    assert all(item["ai_system_id"] != archived_ai["id"] for item in body1["planned_reviews"])

    preview2 = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template_id}/generate-plan",
        headers=headers,
        json={"dry_run": True, "horizon_days": 120, "start_from": start_from},
    )
    assert preview2.status_code == 200
    body2 = preview2.json()
    assert body2["planned_reviews"] == body1["planned_reviews"]
    assert body2["skipped_reviews"] == body1["skipped_reviews"]

    after_count = db_session.query(AISystemGovernanceReview).filter_by(organization_id=org_id).count()
    assert after_count == before_count

    # Explicit subset targeting remains tenant-scoped and deterministic.
    subset_preview = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template_id}/generate-plan",
        headers=headers,
        json={
            "dry_run": True,
            "horizon_days": 120,
            "start_from": start_from,
            "ai_system_ids": [ai1["id"]],
        },
    )
    assert subset_preview.status_code == 200
    assert all(item["ai_system_id"] == ai1["id"] for item in subset_preview.json()["planned_reviews"])


def test_phase54_live_apply_creates_pending_reviews_skips_duplicates_run_history_summary_and_audits(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="p54-live")
    headers = owner["org_headers"]
    org_id = uuid.UUID(owner["organization_id"])

    _create_ai_system(client, headers, name="Live AI-1")
    _create_ai_system(client, headers, name="Live AI-2")

    policy = _create_active_policy(client, headers)
    template_resp = _create_template(
        client,
        headers,
        policy_id=policy["id"],
        assignee_id=owner["user_id"],
        cadence_type="weeks",
        interval_value=2,
    )
    assert template_resp.status_code == 201
    template_id = template_resp.json()["id"]

    first_live = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template_id}/generate-plan",
        headers=headers,
        json={
            "dry_run": False,
            "horizon_days": 30,
            "start_from": datetime(2026, 2, 1, tzinfo=UTC).isoformat(),
        },
    )
    assert first_live.status_code == 200
    body1 = first_live.json()
    assert body1["dry_run"] is False
    assert body1["planned_count"] > 0
    assert body1["created_count"] == body1["planned_count"]
    assert body1["skipped_count"] == 0
    assert body1["run_id"] is not None

    rows = db_session.query(AISystemGovernanceReview).filter(AISystemGovernanceReview.organization_id == org_id).all()
    assert len(rows) == body1["created_count"]
    assert all(row.status == "pending" for row in rows)
    assert all(row.started_at is None for row in rows)
    assert all(row.completed_at is None for row in rows)

    second_live = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template_id}/generate-plan",
        headers=headers,
        json={
            "dry_run": False,
            "horizon_days": 30,
            "start_from": datetime(2026, 2, 1, tzinfo=UTC).isoformat(),
        },
    )
    assert second_live.status_code == 200
    body2 = second_live.json()
    assert body2["created_count"] == 0
    assert body2["skipped_count"] >= body1["planned_count"]

    runs = client.get(
        f"/api/v1/ai-governance/review-plan-runs?template_id={template_id}",
        headers=headers,
    )
    assert runs.status_code == 200
    assert len(runs.json()) >= 2

    run_detail = client.get(
        f"/api/v1/ai-governance/review-plan-runs/{body1['run_id']}",
        headers=headers,
    )
    assert run_detail.status_code == 200
    assert run_detail.json()["status"] == "applied"

    summary = client.get("/api/v1/ai-governance/review-recurrence-summary", headers=headers)
    assert summary.status_code == 200
    sum_body = summary.json()
    assert sum_body["active_templates"] >= 1
    assert sum_body["plan_runs"] >= 2
    assert sum_body["applied_plan_runs"] >= 2
    assert sum_body["previewed_plan_runs"] >= 0
    assert sum_body["generated_reviews_last_30d"] >= body1["created_count"]
    assert sum_body["skipped_reviews_last_30d"] >= body2["skipped_count"]

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_recurrence_template.created" in actions
    assert "ai_system_governance_review_plan.applied" in actions


def test_phase54_plan_run_tenant_scope_and_preview_audit(client):
    org1 = bootstrap_org_user(client, email_prefix="p54-scope-1")
    org2 = bootstrap_org_user(client, email_prefix="p54-scope-2")

    _create_ai_system(client, org1["org_headers"], name="Scope AI")
    policy = _create_active_policy(client, org1["org_headers"])
    template = _create_template(
        client,
        org1["org_headers"],
        policy_id=policy["id"],
        cadence_type="months",
        interval_value=1,
    )
    assert template.status_code == 201

    preview = client.post(
        f"/api/v1/ai-governance/review-recurrence-templates/{template.json()['id']}/generate-plan",
        headers=org1["org_headers"],
        json={"dry_run": True, "horizon_days": 60},
    )
    assert preview.status_code == 200
    run_id = preview.json()["run_id"]

    cross_tenant_run = client.get(
        f"/api/v1/ai-governance/review-plan-runs/{run_id}",
        headers=org2["org_headers"],
    )
    assert cross_tenant_run.status_code == 404

    logs = client.get("/api/v1/audit-logs", headers=org1["org_headers"])
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_review_plan.previewed" in actions
