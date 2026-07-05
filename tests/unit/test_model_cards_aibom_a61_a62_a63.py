from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
SYSTEMS_BASE = "/api/v1/ai-governance/systems"
THIRD_PARTY_BASE = "/api/v1/ai-governance/third-party-assessments"


def _create_vendor(client, headers: dict[str, str], owner_id: str, name: str = "TP Vendor") -> str:
    resp = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_id,
            "risk_tier": "not_assessed",
            "status": "active",
            "data_access": True,
            "processes_personal_data": True,
            "sub_processor": True,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_system(client, headers: dict[str, str], owner_id: str, name: str = "A61 System") -> str:
    resp = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": "limited",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_a61_third_party_ai_assessment_workflow(client):
    org = bootstrap_org_user(client, email_prefix="a61-org")
    vendor_id = _create_vendor(client, org["org_headers"], org["user_id"], name="A61 Vendor")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="A61 System")

    # Create third-party AI assessment.
    created = client.post(
        f"{VENDORS_BASE}/{vendor_id}/ai-model-assessments",
        headers=org["org_headers"],
        json={
            "ai_system_id": system_id,
            "model_name": "Vendor Model X",
            "model_version": "1.0",
            "data_egress_type": "identified",
            "model_card_provided": False,
            "bias_testing_documented": False,
            "explainability_level": "none",
            "contractual_ai_terms_reviewed": False,
            "eu_act_compliance_status": "non_compliant",
        },
    )
    assert created.status_code == 201
    assessment_id = created.json()["id"]

    # Complete: deterministic risk scoring should yield critical for this payload.
    completed = client.post(
        f"{THIRD_PARTY_BASE}/{assessment_id}/complete",
        headers=org["org_headers"],
    )
    assert completed.status_code == 200
    assert completed.json()["overall_risk_level"] == "critical"
    assert completed.json()["status"] == "completed"

    # Linked AI system risk_tier updated from critical -> high.
    system_after = client.get(f"{SYSTEMS_BASE}/{system_id}", headers=org["org_headers"])
    assert system_after.status_code == 200
    assert system_after.json()["risk_tier"] == "high"

    # Block updates after completed.
    blocked_update = client.patch(
        f"{THIRD_PARTY_BASE}/{assessment_id}",
        headers=org["org_headers"],
        json={"model_version": "1.1"},
    )
    assert blocked_update.status_code == 422

    # Favorable flags => low risk.
    favorable = client.post(
        f"{VENDORS_BASE}/{vendor_id}/ai-model-assessments",
        headers=org["org_headers"],
        json={
            "model_name": "Vendor Model Safe",
            "data_egress_type": "none",
            "model_card_provided": True,
            "bias_testing_documented": True,
            "explainability_level": "full",
            "contractual_ai_terms_reviewed": True,
            "eu_act_compliance_status": "compliant",
        },
    )
    assert favorable.status_code == 201
    favorable_id = favorable.json()["id"]

    favorable_done = client.post(
        f"{THIRD_PARTY_BASE}/{favorable_id}/complete",
        headers=org["org_headers"],
    )
    assert favorable_done.status_code == 200
    assert favorable_done.json()["overall_risk_level"] == "low"

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="a61-org-b")
    forbidden = client.get(f"{THIRD_PARTY_BASE}/{assessment_id}", headers=org_b["org_headers"])
    assert forbidden.status_code == 404


def test_third_party_assessment_never_downgrades_system_risk_tier(client):
    org = bootstrap_org_user(client, email_prefix="tpa-tier-guard")
    vendor_id = _create_vendor(client, org["org_headers"], org["user_id"], name="Tier Guard Vendor")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="Tier Guard System")

    # Authoritative EU AI Act classification marks the system high risk.
    classified = client.post(
        f"{SYSTEMS_BASE}/{system_id}/eu-act-classification",
        headers=org["org_headers"],
        json={"article_category": "high_risk_annex3"},
    )
    assert classified.status_code == 200
    assert client.get(f"{SYSTEMS_BASE}/{system_id}", headers=org["org_headers"]).json()["risk_tier"] == "high"

    # A favorable (low-risk) third-party assessment must NOT downgrade the tier.
    favorable = client.post(
        f"{VENDORS_BASE}/{vendor_id}/ai-model-assessments",
        headers=org["org_headers"],
        json={
            "ai_system_id": system_id,
            "model_name": "Benign Vendor Model",
            "data_egress_type": "none",
            "model_card_provided": True,
            "bias_testing_documented": True,
            "explainability_level": "full",
            "contractual_ai_terms_reviewed": True,
            "eu_act_compliance_status": "compliant",
        },
    )
    assert favorable.status_code == 201
    done = client.post(
        f"{THIRD_PARTY_BASE}/{favorable.json()['id']}/complete",
        headers=org["org_headers"],
    )
    assert done.status_code == 200
    assert done.json()["overall_risk_level"] == "low"

    system_after = client.get(f"{SYSTEMS_BASE}/{system_id}", headers=org["org_headers"])
    assert system_after.json()["risk_tier"] == "high", (
        "low-risk vendor assessment silently downgraded an EU AI Act high-risk system"
    )


def test_third_party_assessment_update_audits_and_validates_assessed_by(client, db_session):
    org = bootstrap_org_user(client, email_prefix="tpa-update-audit")
    vendor_id = _create_vendor(client, org["org_headers"], org["user_id"], name="Update Audit Vendor")
    created = client.post(
        f"{VENDORS_BASE}/{vendor_id}/ai-model-assessments",
        headers=org["org_headers"],
        json={
            "model_name": "Update Audit Model",
            "data_egress_type": "none",
            "model_card_provided": True,
            "bias_testing_documented": True,
            "explainability_level": "full",
            "contractual_ai_terms_reviewed": True,
            "eu_act_compliance_status": "compliant",
        },
    )
    assert created.status_code == 201
    assessment_id = created.json()["id"]

    updated = client.patch(
        f"{THIRD_PARTY_BASE}/{assessment_id}",
        headers=org["org_headers"],
        json={"model_version": "2.0", "status": "in_progress"},
    )
    assert updated.status_code == 200
    assert updated.json()["model_version"] == "2.0"
    assert updated.json()["status"] == "in_progress"

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_id == UUID(assessment_id),
            AuditLog.action == "third_party_ai.updated",
        )
    ).scalar_one()
    assert str(audit.actor_user_id) == org["user_id"]
    assert audit.before_json == {"model_version": None, "status": "draft"}
    assert audit.after_json == {"model_version": "2.0", "status": "in_progress"}

    other_org = bootstrap_org_user(client, email_prefix="tpa-update-foreign")
    foreign = client.patch(
        f"{THIRD_PARTY_BASE}/{assessment_id}",
        headers=org["org_headers"],
        json={"assessed_by": other_org["user_id"]},
    )
    assert foreign.status_code == 422
    assert foreign.json()["detail"] == "assessed_by must be an active member of the organization"


def test_third_party_assessment_update_rejects_null_required_fields(client):
    org = bootstrap_org_user(client, email_prefix="tpa-null-required")
    vendor_id = _create_vendor(client, org["org_headers"], org["user_id"], name="Null Required Vendor")
    created = client.post(
        f"{VENDORS_BASE}/{vendor_id}/ai-model-assessments",
        headers=org["org_headers"],
        json={
            "model_name": "Null Required Model",
            "data_egress_type": "none",
            "model_card_provided": True,
            "bias_testing_documented": True,
            "explainability_level": "full",
            "contractual_ai_terms_reviewed": True,
            "eu_act_compliance_status": "compliant",
        },
    )
    assert created.status_code == 201

    rejected = client.patch(
        f"{THIRD_PARTY_BASE}/{created.json()['id']}",
        headers=org["org_headers"],
        json={"data_egress_type": None},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "data_egress_type cannot be null"


def test_a62_model_card_versioning_and_publish(client):
    org = bootstrap_org_user(client, email_prefix="a62-org")
    org_b = bootstrap_org_user(client, email_prefix="a62-org-b")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="A62 System")

    foreign_owner = client.post(
        f"{SYSTEMS_BASE}/{system_id}/model-card",
        headers=org["org_headers"],
        json={
            "intended_purpose": "Assist support triage",
            "contact_owner_id": org_b["user_id"],
        },
    )
    assert foreign_owner.status_code == 422
    assert "contact_owner_id" in foreign_owner.json()["detail"]

    # Create v1 draft.
    v1 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/model-card",
        headers=org["org_headers"],
        json={
            "intended_purpose": "Assist support triage",
            "known_limitations": ["May miss context"],
            "approved_use_cases": ["Ticket routing"],
            "prohibited_use_cases": ["Medical diagnosis"],
            "contact_owner_id": org["user_id"],
        },
    )
    assert v1.status_code == 201
    v1_body = v1.json()
    assert v1_body["version"] == 1
    assert v1_body["status"] == "draft"
    assert v1_body["content_hash"] is not None

    foreign_owner_update = client.patch(
        f"{SYSTEMS_BASE}/{system_id}/model-cards/{v1_body['id']}",
        headers=org["org_headers"],
        json={"contact_owner_id": org_b["user_id"]},
    )
    assert foreign_owner_update.status_code == 422
    assert "contact_owner_id" in foreign_owner_update.json()["detail"]

    # Publish v1.
    publish_v1 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/model-cards/{v1_body['id']}/publish",
        headers=org["org_headers"],
    )
    assert publish_v1.status_code == 200
    assert publish_v1.json()["status"] == "published"
    assert publish_v1.json()["published_at"] is not None

    # Published cards are immutable.
    blocked_update = client.patch(
        f"{SYSTEMS_BASE}/{system_id}/model-cards/{v1_body['id']}",
        headers=org["org_headers"],
        json={"intended_purpose": "Updated purpose"},
    )
    assert blocked_update.status_code == 422

    # Create new version (v2) and publish it; previous published should be archived.
    v2 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/model-card",
        headers=org["org_headers"],
        json={
            "intended_purpose": "Assist support triage v2",
            "known_limitations": ["May miss context", "Needs monitoring"],
            "approved_use_cases": ["Ticket routing", "FAQ suggestions"],
            "prohibited_use_cases": ["Medical diagnosis"],
            "contact_owner_id": org["user_id"],
        },
    )
    assert v2.status_code == 201
    assert v2.json()["version"] == 2

    publish_v2 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/model-cards/{v2.json()['id']}/publish",
        headers=org["org_headers"],
    )
    assert publish_v2.status_code == 200
    assert publish_v2.json()["status"] == "published"

    all_versions = client.get(f"{SYSTEMS_BASE}/{system_id}/model-cards", headers=org["org_headers"])
    assert all_versions.status_code == 200
    versions = all_versions.json()
    assert len(versions) == 2
    by_version = {item["version"]: item for item in versions}
    assert by_version[1]["status"] == "archived"
    assert by_version[2]["status"] == "published"

    active = client.get(f"{SYSTEMS_BASE}/{system_id}/model-card", headers=org["org_headers"])
    assert active.status_code == 200
    assert active.json()["version"] == 2
    assert active.json()["status"] == "published"


def test_a63_aibom_versioning_and_diff(client):
    org = bootstrap_org_user(client, email_prefix="a63-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="A63 System")

    # Create v1.
    v1 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom",
        headers=org["org_headers"],
        json={"notes": "Initial inventory"},
    )
    assert v1.status_code == 201
    assert v1.json()["version"] == 1

    add_a1 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom/components",
        headers=org["org_headers"],
        json={
            "component_type": "base_model",
            "name": "gpt-base",
            "version": "1.0",
        },
    )
    assert add_a1.status_code == 201

    add_b1 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom/components",
        headers=org["org_headers"],
        json={
            "component_type": "training_data",
            "name": "dataset-v1",
            "version": "2026-01",
        },
    )
    assert add_b1.status_code == 201

    duplicate = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom/components",
        headers=org["org_headers"],
        json={
            "component_type": "base_model",
            "name": "gpt-base",
            "version": "1.1",
        },
    )
    assert duplicate.status_code == 409

    add_c1 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom/components",
        headers=org["org_headers"],
        json={
            "component_type": "third_party_api",
            "name": "toxicity-api",
            "version": "3",
        },
    )
    assert add_c1.status_code == 201

    # Create v2 with no explicit component payload: prior components carry forward.
    v2 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom",
        headers=org["org_headers"],
        json={"notes": "Second inventory"},
    )
    assert v2.status_code == 201
    assert v2.json()["version"] == 2

    no_change_diff = client.get(
        f"{SYSTEMS_BASE}/{system_id}/aibom/diff?v1=1&v2=2",
        headers=org["org_headers"],
    )
    assert no_change_diff.status_code == 200
    assert no_change_diff.json() == {"added": [], "removed": [], "changed": []}

    # Create v3 with an explicit modified baseline: dataset-v1 is genuinely removed
    # and gpt-base is changed, without deleting the v1/v2 component records.
    v3 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom",
        headers=org["org_headers"],
        json={
            "notes": "Third inventory",
            "components": [
                {
                    "component_type": "base_model",
                    "name": "gpt-base",
                    "version": "2.0",
                },
                {
                    "component_type": "third_party_api",
                    "name": "toxicity-api",
                    "version": "3",
                },
            ],
        },
    )
    assert v3.status_code == 201
    assert v3.json()["version"] == 3

    diff = client.get(
        f"{SYSTEMS_BASE}/{system_id}/aibom/diff?v2=2&v1=1",
        headers=org["org_headers"],
    )
    assert diff.status_code == 200
    assert diff.json() == {"added": [], "removed": [], "changed": []}

    modified_diff = client.get(
        f"{SYSTEMS_BASE}/{system_id}/aibom/diff?v1=2&v2=3",
        headers=org["org_headers"],
    )
    assert modified_diff.status_code == 200
    body = modified_diff.json()

    assert {item["name"] for item in body["removed"]} == {"dataset-v1"}
    changed_names = {item["name"] for item in body["changed"]}
    assert "gpt-base" in changed_names
    assert body["added"] == []

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="a63-org-b")
    forbidden = client.get(
        f"{SYSTEMS_BASE}/{system_id}/aibom/diff?v1=1&v2=2",
        headers=org_b["org_headers"],
    )
    assert forbidden.status_code == 404


def test_a63_aibom_invalid_component_type_lists_valid_options(client):
    org = bootstrap_org_user(client, email_prefix="a63-invalid-type")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="A63 Invalid Type System")

    create = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom",
        headers=org["org_headers"],
        json={"notes": "Initial inventory"},
    )
    assert create.status_code == 201

    bad = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom/components",
        headers=org["org_headers"],
        json={
            "component_type": "not_a_real_type",
            "name": "mystery-component",
        },
    )
    assert bad.status_code == 422
    body = bad.json()
    assert "not_a_real_type" in body["detail"]
    assert set(body["valid_options"]) == {
        "training_data",
        "base_model",
        "fine_tuning_dataset",
        "runtime_data_feed",
        "third_party_api",
        "framework_library",
    }
