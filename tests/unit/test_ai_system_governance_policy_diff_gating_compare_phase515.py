from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.models.ai_system_governance_policy_diff_gating_report import AISystemGovernancePolicyDiffGatingReport
from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post("/api/v1/ai-systems", headers=headers, json={"name": name, "system_type": "agent"})
    assert response.status_code == 201
    return response.json()


def _create_pack(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        "/api/v1/ai-governance/review-sequence-packs",
        headers=headers,
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 201
    return response.json()


def _create_policy_set(client, headers: dict[str, str], *, name: str, ack_text: str) -> dict:
    policy = client.post("/api/v1/ai-governance/guardrails/policy-sets", headers=headers, json={"name": name})
    assert policy.status_code == 201
    policy_body = policy.json()
    version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_body['id']}/versions",
        headers=headers,
        json={
            "profile_json": {
                "resolution_strategy": "deterministic_precedence_v1",
                "acknowledgement_text": ack_text,
                "allow_operator_override": True,
                "require_override_reason": True,
                "include_info_windows": True,
                "include_warn_windows": True,
                "include_block_windows": True,
                "scope_precedence_order": ["ai_system", "sequence_pack", "review_type", "all_ai_governance"],
            },
            "change_reason": "init",
        },
    )
    assert version.status_code == 201
    version_body = version.json()
    activate = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_body['id']}/versions/{version_body['id']}/activate",
        headers=headers,
        json={"reason": "activate"},
    )
    assert activate.status_code == 200
    return policy_body


def _assign_policy(client, headers: dict[str, str], payload: dict) -> None:
    response = client.post("/api/v1/ai-governance/guardrails/policy-assignments", headers=headers, json=payload)
    assert response.status_code == 201


def _persist_sim(client, headers: dict[str, str], contexts: list[dict], *, title: str) -> str:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=headers,
        json={"persist_report": True, "title": title, "contexts": contexts},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    return body["report_id"]


def _create_diff_report(client, headers: dict[str, str]) -> str:
    ai = _create_ai_system(client, headers, name=f"P515 AI {uuid4()}")
    pack = _create_pack(client, headers, name=f"P515 Pack {uuid4()}")
    mapped_policy = _create_policy_set(client, headers, name=f"P515 Mapped {uuid4()}", ack_text="ACK_M")
    explicit_policy = _create_policy_set(client, headers, name=f"P515 Explicit {uuid4()}", ack_text="ACK_E")
    _assign_policy(
        client,
        headers,
        {"policy_set_id": mapped_policy["id"], "scope_type": "sequence_pack", "scope_id": pack["id"], "reason": "pack"},
    )
    now = datetime.now(UTC).replace(microsecond=0)
    base_report_id = _persist_sim(
        client,
        headers,
        [
            {
                "context_key": "ctx-1",
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai["id"]],
                "review_types": ["initial_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=1)).isoformat(),
            }
        ],
        title="base",
    )
    compare_report_id = _persist_sim(
        client,
        headers,
        [
            {
                "context_key": "ctx-1",
                "explicit_policy_set_id": explicit_policy["id"],
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai["id"]],
                "review_types": ["initial_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=1)).isoformat(),
            }
        ],
        title="compare",
    )
    diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=headers,
        json={
            "base_report_id": base_report_id,
            "compare_report_id": compare_report_id,
            "persist_diff": True,
            "context_match_strategy": "context_key_then_index",
        },
    )
    assert diff.status_code == 200
    return diff.json()["diff_report_id"]


def _create_profile(client, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles",
        headers=headers,
        json={
            "name": f"P515 Profile {uuid4()}",
            "default_severity": "low",
            "review_required_threshold": "high",
            "reason_code_rules_json": {},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _insert_gating_report(
    db_session,
    *,
    organization_id: str,
    diff_report_id: str,
    profile_id: str,
    max_severity: str,
    review_required: bool,
    reason_code_count: int,
    reason_code_classifications: list[dict],
    severity_summary: dict[str, int] | None = None,
    status: str = "generated",
) -> str:
    row = AISystemGovernancePolicyDiffGatingReport(
        organization_id=UUID(organization_id),
        diff_report_id=UUID(diff_report_id),
        gating_profile_id=UUID(profile_id),
        status=status,
        result_json={
            "reason_code_classifications": reason_code_classifications,
            "severity_summary": severity_summary
            or {"info": 0, "low": 0, "medium": 0, "high": 0, "critical": 0},
        },
        max_severity=max_severity,
        review_required=review_required,
        reason_code_count=reason_code_count,
    )
    db_session.add(row)
    db_session.flush()
    return str(row.id)


def test_phase515_compare_preview_drift_detection_and_no_persist_no_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p515-preview")
    headers = org["org_headers"]
    diff_id = _create_diff_report(client, headers)
    profile_id = _create_profile(client, headers)

    base_gating_id = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="medium",
        review_required=False,
        reason_code_count=4,
        reason_code_classifications=[
            {"reason_code": "POLICY_SET_CHANGED", "count": 1, "severity": "low", "review_required": False},
            {"reason_code": "POLICY_VERSION_CHANGED", "count": 2, "severity": "medium", "review_required": True},
            {"reason_code": "CONTEXT_REMOVED", "count": 1, "severity": "low", "review_required": False},
        ],
    )
    compare_gating_id = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="critical",
        review_required=True,
        reason_code_count=6,
        reason_code_classifications=[
            {"reason_code": "POLICY_SET_CHANGED", "count": 3, "severity": "high", "review_required": True},
            {"reason_code": "POLICY_VERSION_CHANGED", "count": 2, "severity": "medium", "review_required": False},
            {"reason_code": "CONTEXT_ADDED", "count": 1, "severity": "low", "review_required": False},
        ],
    )

    preview = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/compare",
        headers=headers,
        json={
            "base_gating_report_id": base_gating_id,
            "compare_gating_report_id": compare_gating_id,
            "persist_compare": False,
        },
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["persisted"] is False
    assert body["compare_report_id"] is None
    assert body["severity_direction"] == "increased"
    assert body["base_review_required"] is False
    assert body["compare_review_required"] is True
    assert body["review_required_changed"] is True
    assert body["reason_code_changes_count"] >= 6
    assert body["aggregate_deltas"]["reason_code_count_delta"] == 2
    assert "read-only drift reports" in body["caveat"]

    change_map = {(row["reason_code"], row["change_type"]) for row in body["reason_code_changes"]}
    assert ("CONTEXT_ADDED", "reason_code_added") in change_map
    assert ("CONTEXT_REMOVED", "reason_code_removed") in change_map
    assert ("POLICY_SET_CHANGED", "severity_changed") in change_map
    assert ("POLICY_SET_CHANGED", "review_required_changed") in change_map
    assert ("POLICY_SET_CHANGED", "count_changed") in change_map
    assert ("POLICY_VERSION_CHANGED", "review_required_changed") in change_map

    compare_list = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports",
        headers=headers,
    )
    assert compare_list.status_code == 200
    assert compare_list.json() == []

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_diff_gating_compare.generated" not in actions


def test_phase515_compare_persist_list_detail_archive_summary_and_directions(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p515-persist")
    headers = org["org_headers"]
    diff_id = _create_diff_report(client, headers)
    profile_id = _create_profile(client, headers)

    report_high = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="critical",
        review_required=True,
        reason_code_count=5,
        reason_code_classifications=[{"reason_code": "POLICY_SET_CHANGED", "count": 5, "severity": "critical", "review_required": True}],
    )
    report_low = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="info",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "CONTEXT_UNCHANGED", "count": 1, "severity": "info", "review_required": False}],
    )
    report_same = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="info",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "CONTEXT_UNCHANGED", "count": 1, "severity": "info", "review_required": False}],
    )

    decreased = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/compare",
        headers=headers,
        json={
            "base_gating_report_id": report_high,
            "compare_gating_report_id": report_low,
            "persist_compare": True,
            "title": "decreased",
        },
    )
    assert decreased.status_code == 200
    dec_body = decreased.json()
    assert dec_body["persisted"] is True
    assert dec_body["compare_report_id"] is not None
    assert dec_body["severity_direction"] == "decreased"
    assert dec_body["base_review_required"] is True
    assert dec_body["compare_review_required"] is False
    assert dec_body["review_required_changed"] is True

    unchanged = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/compare",
        headers=headers,
        json={
            "base_gating_report_id": report_low,
            "compare_gating_report_id": report_same,
            "persist_compare": False,
        },
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["severity_direction"] == "unchanged"

    list_reports = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports"
        "?severity_direction=decreased&review_required_changed=true",
        headers=headers,
    )
    assert list_reports.status_code == 200
    assert any(item["id"] == dec_body["compare_report_id"] for item in list_reports.json())

    detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports/{dec_body['compare_report_id']}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == dec_body["compare_report_id"]

    archive = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports/{dec_body['compare_report_id']}/archive",
        headers=headers,
        json={"reason": "done"},
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    summary = client.get("/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-summary", headers=headers)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["total_compare_reports"] >= 1
    assert summary_body["active_compare_reports"] >= 0
    assert summary_body["archived_compare_reports"] >= 1
    assert summary_body["severity_decreased_reports"] >= 1
    assert summary_body["severity_unchanged_reports"] >= 0
    assert summary_body["review_required_changed_reports"] >= 1
    assert summary_body["total_reason_code_changes"] >= 0

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_diff_gating_compare.generated" in actions
    assert "ai_system_governance_policy_diff_gating_compare.archived" in actions


def test_phase515_compare_tenant_isolation_for_base_and_compare(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p515-tenant1")
    org2 = bootstrap_org_user(client, email_prefix="p515-tenant2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    diff1 = _create_diff_report(client, h1)
    profile1 = _create_profile(client, h1)
    r1 = _insert_gating_report(
        db_session,
        organization_id=org1["organization_id"],
        diff_report_id=diff1,
        profile_id=profile1,
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "CONTEXT_CHANGED", "count": 1, "severity": "low", "review_required": False}],
    )
    r2 = _insert_gating_report(
        db_session,
        organization_id=org1["organization_id"],
        diff_report_id=diff1,
        profile_id=profile1,
        max_severity="high",
        review_required=True,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "POLICY_SET_CHANGED", "count": 1, "severity": "high", "review_required": True}],
    )

    diff2 = _create_diff_report(client, h2)
    profile2 = _create_profile(client, h2)
    other = _insert_gating_report(
        db_session,
        organization_id=org2["organization_id"],
        diff_report_id=diff2,
        profile_id=profile2,
        max_severity="medium",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "POLICY_VERSION_CHANGED", "count": 1, "severity": "medium", "review_required": False}],
    )

    bad_base = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/compare",
        headers=h1,
        json={"base_gating_report_id": other, "compare_gating_report_id": r2},
    )
    assert bad_base.status_code == 404

    bad_compare = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/compare",
        headers=h1,
        json={"base_gating_report_id": r1, "compare_gating_report_id": other},
    )
    assert bad_compare.status_code == 404

    ok = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/compare",
        headers=h1,
        json={"base_gating_report_id": r1, "compare_gating_report_id": r2, "persist_compare": True},
    )
    assert ok.status_code == 200
    compare_report_id = ok.json()["compare_report_id"]

    cross_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports/{compare_report_id}",
        headers=h2,
    )
    assert cross_detail.status_code == 404

    list_h1 = client.get("/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports", headers=h1)
    list_h2 = client.get("/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-reports", headers=h2)
    assert list_h1.status_code == 200
    assert list_h2.status_code == 200
    ids1 = {item["id"] for item in list_h1.json()}
    ids2 = {item["id"] for item in list_h2.json()}
    assert compare_report_id in ids1
    assert compare_report_id not in ids2
