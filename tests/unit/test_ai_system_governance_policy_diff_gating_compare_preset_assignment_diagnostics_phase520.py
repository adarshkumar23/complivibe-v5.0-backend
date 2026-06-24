from uuid import UUID

from sqlalchemy import func, select

from app.models.ai_system_governance_policy_diff_gating_compare_preset_assignment import (
    AISystemGovernancePolicyDiffGatingComparePresetAssignment,
)
from app.models.ai_system_governance_policy_diff_gating_compare_preset_assignment_history import (
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory,
)
from app.models.ai_system_governance_policy_diff_gating_compare_preset import (
    AISystemGovernancePolicyDiffGatingComparePreset,
)
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_assignments_phase519 import _create_context
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_versions_phase517 import _create_preset
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_presets_phase516 import (
    _create_ai_system,
    _create_pack,
)


def _create_assignment(client, headers: dict[str, str], payload: dict) -> dict:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def test_phase520_bulk_coverage_diagnostics_and_read_only_behavior(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p520-bulk")
    headers = org["org_headers"]

    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset_global = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_explicit = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_inactive = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_archived = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_pinned_required = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_pinned_archived = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_ai_a = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_ai_b = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)

    pack_primary = _create_pack(client, headers, name="P520 Pack Primary")
    pack_inactive = _create_pack(client, headers, name="P520 Pack Inactive")
    pack_archived = _create_pack(client, headers, name="P520 Pack Archived")
    pack_pin_required = _create_pack(client, headers, name="P520 Pack Pin Required")
    pack_pin_archived = _create_pack(client, headers, name="P520 Pack Pin Archived")
    ai_one = _create_ai_system(client, headers, name="P520 AI One")
    ai_two = _create_ai_system(client, headers, name="P520 AI Two")

    set_inactive = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_inactive['id']}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert set_inactive.status_code == 200
    pin_required = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_pinned_required['id']}/pin-version",
        headers=headers,
        json={
            "version_id": client.post(
                f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_pinned_required['id']}/versions",
                headers=headers,
                json={"change_reason": "pin-required"},
            ).json()["id"],
            "version_selection_mode": "pinned_required",
            "allow_explicit_version_override": False,
            "reason": "pin-required",
        },
    )
    assert pin_required.status_code == 200
    unpin = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_pinned_required['id']}/unpin-version",
        headers=headers,
        json={"reason": "remove pin"},
    )
    assert unpin.status_code == 200
    pinned_required_row = db_session.execute(
        select(AISystemGovernancePolicyDiffGatingComparePreset).where(
            AISystemGovernancePolicyDiffGatingComparePreset.id == UUID(preset_pinned_required["id"])
        )
    ).scalar_one()
    pinned_required_row.version_selection_mode = "pinned_required"
    pinned_required_row.pinned_version_id = None
    db_session.commit()

    pin_archived_version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_pinned_archived['id']}/versions",
        headers=headers,
        json={"change_reason": "pin-archived"},
    )
    assert pin_archived_version.status_code == 201
    pin_archived = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_pinned_archived['id']}/pin-version",
        headers=headers,
        json={
            "version_id": pin_archived_version.json()["id"],
            "version_selection_mode": "pinned_preferred",
            "allow_explicit_version_override": True,
            "reason": "pin it",
        },
    )
    assert pin_archived.status_code == 200
    archive_pinned_version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_pinned_archived['id']}/versions/{pin_archived_version.json()['id']}/archive",
        headers=headers,
        json={"reason": "archive pinned version"},
    )
    assert archive_pinned_version.status_code == 200

    _create_assignment(
        client,
        headers,
        {"preset_id": preset_global["id"], "scope_type": "all_ai_governance", "reason": "global"},
    )
    _create_assignment(
        client,
        headers,
        {"preset_id": preset_global["id"], "scope_type": "sequence_pack", "scope_id": pack_primary["id"], "reason": "primary"},
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_explicit["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack_primary["id"],
            "reason": "inactive-inspect",
            "status": "inactive",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_explicit["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack_primary["id"],
            "reason": "archived-inspect",
            "status": "archived",
        },
    )
    _create_assignment(
        client,
        headers,
        {"preset_id": preset_inactive["id"], "scope_type": "sequence_pack", "scope_id": pack_inactive["id"], "reason": "inactive-preset"},
    )
    _create_assignment(
        client,
        headers,
        {"preset_id": preset_archived["id"], "scope_type": "sequence_pack", "scope_id": pack_archived["id"], "reason": "archived-preset"},
    )
    set_archived = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_archived['id']}",
        headers=headers,
        json={"status": "archived"},
    )
    assert set_archived.status_code == 200
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_pinned_required["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack_pin_required["id"],
            "reason": "pin-required",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_pinned_archived["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack_pin_archived["id"],
            "reason": "pin-archived",
        },
    )
    _create_assignment(
        client,
        headers,
        {"preset_id": preset_ai_a["id"], "scope_type": "ai_system", "scope_id": ai_one["id"], "reason": "ai-one"},
    )
    _create_assignment(
        client,
        headers,
        {"preset_id": preset_ai_b["id"], "scope_type": "ai_system", "scope_id": ai_two["id"], "reason": "ai-two"},
    )

    before_assignment_count = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id))
    ).scalar_one()
    before_history_count = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory.id))
    ).scalar_one()
    before_audit_count = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    diagnostics = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-diagnostics",
        headers=headers,
        json={
                "contexts": [
                    {"context_key": "mapped-pack", "sequence_pack_id": pack_primary["id"]},
                    {"context_key": "global-fallback", "rollout_class": "none"},
                    {"context_key": "explicit", "explicit_preset_id": preset_explicit["id"], "sequence_pack_id": pack_primary["id"]},
                {"context_key": "conflict-ai", "ai_system_ids": [ai_one["id"], ai_two["id"]]},
                {"context_key": "inactive-preset", "sequence_pack_id": pack_inactive["id"]},
                {"context_key": "archived-preset", "sequence_pack_id": pack_archived["id"]},
                {"context_key": "pin-required", "sequence_pack_id": pack_pin_required["id"]},
                {"context_key": "pin-archived", "sequence_pack_id": pack_pin_archived["id"]},
            ]
        },
    )
    assert diagnostics.status_code == 200
    body = diagnostics.json()
    assert body["context_count"] == 8
    by_key = {item["context_key"]: item for item in body["contexts"]}
    assert by_key["mapped-pack"]["resolution_source"] == "mapped_sequence_pack"
    mapped_codes = {item["code"] for item in by_key["mapped-pack"]["diagnostics"]}
    assert "RESOLVED" in mapped_codes
    assert any(
        trace["scope_type"] == "sequence_pack"
        and trace.get("inactive_assignment_ids")
        and trace.get("archived_assignment_ids")
        for trace in by_key["mapped-pack"]["precedence_trace"]
    )
    assert by_key["global-fallback"]["resolution_source"] == "mapped_all_ai_governance"
    assert any(item["code"] == "CROSS_SCOPE_FALLBACK_USED" for item in by_key["global-fallback"]["diagnostics"])
    assert by_key["explicit"]["resolution_source"] == "explicit_request"
    assert any(item["code"] == "EXPLICIT_PRESET_USED" for item in by_key["explicit"]["diagnostics"])
    assert any(item["code"] == "CONFLICTING_ASSIGNMENTS_SAME_SCOPE" for item in by_key["conflict-ai"]["diagnostics"])
    assert any(item["code"] == "CROSS_SCOPE_FALLBACK_USED" for item in by_key["conflict-ai"]["diagnostics"])
    assert any(item["code"] == "ASSIGNMENT_TARGET_PRESET_INACTIVE" for item in by_key["inactive-preset"]["diagnostics"])
    assert any(item["code"] == "ASSIGNMENT_TARGET_PRESET_ARCHIVED" for item in by_key["archived-preset"]["diagnostics"])
    assert any(item["code"] == "PINNED_REQUIRED_WITHOUT_PIN" for item in by_key["pin-required"]["diagnostics"])
    assert any(item["code"] == "PINNED_VERSION_ARCHIVED" for item in by_key["pin-archived"]["diagnostics"])
    assert body["aggregate_diagnostics"]["PINNED_VERSION_ARCHIVED"] >= 1

    after_assignment_count = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id))
    ).scalar_one()
    after_history_count = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory.id))
    ).scalar_one()
    after_audit_count = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_assignment_count == before_assignment_count
    assert after_history_count == before_history_count
    assert after_audit_count == before_audit_count


def test_phase520_health_diagnostics_and_coverage_summary(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p520-health")
    headers = org["org_headers"]

    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset_active = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_inactive = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    set_inactive = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_inactive['id']}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert set_inactive.status_code == 200
    pack = _create_pack(client, headers, name="P520 Health Pack")

    _create_assignment(
        client,
        headers,
        {"preset_id": preset_active["id"], "scope_type": "all_ai_governance", "reason": "global"},
    )
    _create_assignment(
        client,
        headers,
        {"preset_id": preset_inactive["id"], "scope_type": "sequence_pack", "scope_id": pack["id"], "reason": "inactive-target"},
    )

    health = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/health-diagnostics",
        headers=headers,
    )
    assert health.status_code == 200
    health_body = health.json()
    assert health_body["active_assignments"] >= 2
    assert health_body["assignments_to_inactive_presets"] >= 1
    assert "caveat" in health_body

    summary = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-summary",
        headers=headers,
    )
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["total_active_assignments"] >= 2
    assert summary_body["total_problem_assignments"] >= 1
    assert summary_body["presets_referenced_by_assignments"] >= 2
    assert "all_ai_governance" in summary_body["assignments_by_scope_type"]
    assert "caveat" in summary_body


def test_phase520_bulk_diagnostics_no_assignment_found(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p520-no-assignment")
    headers = org["org_headers"]
    _create_context(client, db_session, headers, org["organization_id"])

    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-diagnostics",
        headers=headers,
        json={"contexts": [{"context_key": "none"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["resolved_contexts_count"] == 0
    assert body["unresolved_contexts_count"] == 1
    assert body["critical_contexts_count"] == 1
    context = body["contexts"][0]
    assert context["context_key"] == "none"
    assert context["resolution_source"] == "none"
    assert any(item["code"] == "NO_ASSIGNMENT_FOUND" for item in context["diagnostics"])


def test_phase520_bulk_diagnostics_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p520-tenant-1")
    org2 = bootstrap_org_user(client, email_prefix="p520-tenant-2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    profile_id_1, base_id_1, _ = _create_context(client, db_session, h1, org1["organization_id"])
    profile_id_2, base_id_2, _ = _create_context(client, db_session, h2, org2["organization_id"])
    preset_1 = _create_preset(client, h1, baseline_report_id=base_id_1, profile_id=profile_id_1)
    _create_preset(client, h2, baseline_report_id=base_id_2, profile_id=profile_id_2)
    _create_assignment(
        client,
        h1,
        {"preset_id": preset_1["id"], "scope_type": "all_ai_governance", "reason": "global"},
    )
    pack_other = _create_pack(client, h2, name="P520 Other Pack")
    ai_other = _create_ai_system(client, h2, name="P520 Other AI")

    seq_scope_error = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-diagnostics",
        headers=h1,
        json={"contexts": [{"sequence_pack_id": pack_other["id"]}]},
    )
    assert seq_scope_error.status_code == 404

    ai_scope_error = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-diagnostics",
        headers=h1,
        json={"contexts": [{"ai_system_ids": [ai_other["id"]]}]},
    )
    assert ai_scope_error.status_code == 404
