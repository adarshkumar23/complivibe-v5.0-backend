from sqlalchemy import func, select

from app.models.ai_system_risk_classification_record import AISystemRiskClassificationRecord
from app.models.ai_system_risk_classification_taxonomy_template import AISystemRiskClassificationTaxonomyTemplate
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user

ASSESSMENTS_BASE = "/api/v1/ai-governance/ai-risk/assessments"
TAXONOMY_BASE = "/api/v1/ai-governance/ai-risk/classification-taxonomies"
CLASSIFICATION_BASE = "/api/v1/ai-governance/ai-risk/classifications"


def _create_ai_system(client, headers: dict[str, str], *, name: str = "Risk-Classify AI") -> dict:
    response = client.post("/api/v1/ai-systems", headers=headers, json={"name": name, "system_type": "agent"})
    assert response.status_code == 201
    return response.json()


def _create_assessment(client, headers: dict[str, str], ai_system_id: str, **overrides) -> dict:
    payload = {
        "ai_system_id": ai_system_id,
        "title": "Risk Assessment",
        "assessment_type": "initial",
        "risk_level": "medium",
        "likelihood": "high",
        "impact": "medium",
    }
    payload.update(overrides)
    response = client.post(ASSESSMENTS_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _taxonomy_payload(name: str = "Default Taxonomy") -> dict:
    return {
        "name": name,
        "taxonomy_json": {
            "label_groups": [
                {
                    "group_key": "data_sensitivity",
                    "title": "Data Sensitivity",
                    "labels": [
                        {"label_key": "no_personal_data", "title": "No personal data"},
                        {"label_key": "personal_data", "title": "Personal data"},
                    ],
                },
                {
                    "group_key": "human_impact",
                    "title": "Human Impact",
                    "labels": [
                        {"label_key": "low_human_impact", "title": "Low human impact"},
                        {"label_key": "material_human_impact", "title": "Material human impact"},
                    ],
                },
            ]
        },
        "is_default": False,
    }


def _create_taxonomy(client, headers: dict[str, str], **overrides) -> dict:
    payload = _taxonomy_payload()
    payload.update(overrides)
    response = client.post(TAXONOMY_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_control(client, headers: dict[str, str], title: str = "Control") -> str:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "process", "criticality": "medium"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_evidence(client, headers: dict[str, str], title: str = "Evidence") -> str:
    response = client.post(
        "/api/v1/evidence",
        headers=headers,
        json={"title": title, "evidence_type": "policy_document"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_risk(client, headers: dict[str, str], title: str = "Risk") -> str:
    response = client.post(
        "/api/v1/risks",
        headers=headers,
        json={"title": title, "category": "ai_governance", "likelihood": 2, "impact": 2},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_phase64_taxonomy_crud_validation_default_and_tenant_scope(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p64-tax-org1")
    org2 = bootstrap_org_user(client, email_prefix="p64-tax-org2")

    t1 = _create_taxonomy(client, org1["org_headers"], is_default=True)
    assert t1["is_default"] is True

    duplicate_group = _taxonomy_payload("BadTax")
    duplicate_group["taxonomy_json"]["label_groups"].append(
        {
            "group_key": "data_sensitivity",
            "title": "Duplicate",
            "labels": [{"label_key": "x", "title": "X"}],
        }
    )
    bad_group = client.post(TAXONOMY_BASE, headers=org1["org_headers"], json=duplicate_group)
    assert bad_group.status_code == 400

    duplicate_label = _taxonomy_payload("BadTax2")
    duplicate_label["taxonomy_json"]["label_groups"][0]["labels"].append(
        {"label_key": "personal_data", "title": "Duplicate label"}
    )
    bad_label = client.post(TAXONOMY_BASE, headers=org1["org_headers"], json=duplicate_label)
    assert bad_label.status_code == 400

    t2 = _create_taxonomy(client, org1["org_headers"], name="T2")
    set_default = client.post(f"{TAXONOMY_BASE}/{t2['id']}/set-default", headers=org1["org_headers"], json={})
    assert set_default.status_code == 200
    assert set_default.json()["is_default"] is True

    t1_refetch = client.get(f"{TAXONOMY_BASE}/{t1['id']}", headers=org1["org_headers"])
    assert t1_refetch.status_code == 200
    assert t1_refetch.json()["is_default"] is False

    cross_get = client.get(f"{TAXONOMY_BASE}/{t1['id']}", headers=org2["org_headers"])
    assert cross_get.status_code == 404

    archived = client.post(
        f"{TAXONOMY_BASE}/{t1['id']}/archive",
        headers=org1["org_headers"],
        json={"reason": "retired"},
    )
    assert archived.status_code == 200

    cannot_update = client.patch(
        f"{TAXONOMY_BASE}/{t1['id']}",
        headers=org1["org_headers"],
        json={"description": "no"},
    )
    assert cannot_update.status_code == 400


def test_phase64_create_classification_validation_supersede_and_no_auto_risk_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p64-class")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"], risk_level="high")
    taxonomy = _create_taxonomy(client, org["org_headers"], is_default=True)

    c1 = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications",
        headers=org["org_headers"],
        json={
            "taxonomy_template_id": taxonomy["id"],
            "classification_json": {
                "labels": [
                    {"group_key": "data_sensitivity", "label_key": "personal_data"},
                    {"group_key": "human_impact", "label_key": "material_human_impact"},
                ]
            },
            "confidence_level": "medium",
            "justification": "Operator manual classification",
            "source_type": "internal_review",
        },
    )
    assert c1.status_code == 201
    c1_body = c1.json()
    assert c1_body["status"] == "active"
    assert "manual governance assertions" in c1_body["caveat"]

    detail = client.get(f"{ASSESSMENTS_BASE}/{assessment['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    dbody = detail.json()
    assert dbody["latest_classification_id"] == c1_body["id"]
    assert dbody["classification_status"] == "active"
    assert dbody["risk_level"] == "high"
    assert dbody["calculated_risk_level"] is None

    invalid_label = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications",
        headers=org["org_headers"],
        json={
            "taxonomy_template_id": taxonomy["id"],
            "classification_json": {"labels": [{"group_key": "human_impact", "label_key": "invalid"}]},
            "justification": "bad label",
        },
    )
    assert invalid_label.status_code == 400

    no_justification = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications",
        headers=org["org_headers"],
        json={
            "classification_json": {"labels": [{"group_key": "human_impact", "label_key": "low_human_impact"}]},
        },
    )
    assert no_justification.status_code == 422

    c2 = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications",
        headers=org["org_headers"],
        json={
            "classification_json": {"labels": [{"group_key": "human_impact", "label_key": "low_human_impact"}]},
            "justification": "supersedes prior",
            "supersede_previous": True,
        },
    )
    assert c2.status_code == 201

    all_rows = client.get(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications?include_archived=true",
        headers=org["org_headers"],
    )
    assert all_rows.status_code == 200
    statuses = {row["id"]: row["status"] for row in all_rows.json()}
    assert statuses[c1_body["id"]] == "superseded"

    c3 = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications",
        headers=org["org_headers"],
        json={
            "classification_json": {"labels": [{"group_key": "data_sensitivity", "label_key": "no_personal_data"}]},
            "justification": "parallel active",
            "supersede_previous": False,
        },
    )
    assert c3.status_code == 201

    active_rows = client.get(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications?status=active",
        headers=org["org_headers"],
    )
    assert active_rows.status_code == 200
    assert len(active_rows.json()) >= 2


def test_phase64_classification_links_tenant_scope_archive_and_archived_assessment_block(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p64-link-org1")
    org2 = bootstrap_org_user(client, email_prefix="p64-link-org2")

    ai1 = _create_ai_system(client, org1["org_headers"])
    assessment = _create_assessment(client, org1["org_headers"], ai1["id"])
    _create_taxonomy(client, org1["org_headers"], is_default=True)

    evidence1 = _create_evidence(client, org1["org_headers"], "Evidence 1")
    control1 = _create_control(client, org1["org_headers"], "Control 1")
    risk1 = _create_risk(client, org1["org_headers"], "Risk 1")

    evidence2 = _create_evidence(client, org2["org_headers"], "Evidence 2")

    ok = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications",
        headers=org1["org_headers"],
        json={
            "classification_json": {"labels": [{"group_key": "data_sensitivity", "label_key": "personal_data"}]},
            "justification": "with linked refs",
            "evidence_ids_json": [evidence1],
            "control_ids_json": [control1],
            "risk_ids_json": [risk1],
        },
    )
    assert ok.status_code == 201
    classification_id = ok.json()["id"]

    bad_cross_evidence = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications",
        headers=org1["org_headers"],
        json={
            "classification_json": {"labels": [{"group_key": "data_sensitivity", "label_key": "personal_data"}]},
            "justification": "bad refs",
            "evidence_ids_json": [evidence2],
        },
    )
    assert bad_cross_evidence.status_code == 400

    cross_detail = client.get(f"{CLASSIFICATION_BASE}/{classification_id}", headers=org2["org_headers"])
    assert cross_detail.status_code == 404

    no_reason = client.post(
        f"{CLASSIFICATION_BASE}/{classification_id}/archive",
        headers=org1["org_headers"],
        json={},
    )
    assert no_reason.status_code == 422

    archived = client.post(
        f"{CLASSIFICATION_BASE}/{classification_id}/archive",
        headers=org1["org_headers"],
        json={"reason": "retired"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    archived_assessment = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/archive",
        headers=org1["org_headers"],
        json={"reason": "end of life"},
    )
    assert archived_assessment.status_code == 200

    blocked = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications",
        headers=org1["org_headers"],
        json={
            "classification_json": {"labels": [{"group_key": "human_impact", "label_key": "low_human_impact"}]},
            "justification": "should fail",
        },
    )
    assert blocked.status_code == 400


def test_phase64_classification_summary_snapshot_contracts_and_read_only_wording(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p64-summary")
    ai1 = _create_ai_system(client, org["org_headers"], name="AI-1")
    ai2 = _create_ai_system(client, org["org_headers"], name="AI-2")
    a1 = _create_assessment(client, org["org_headers"], ai1["id"])
    _ = _create_assessment(client, org["org_headers"], ai2["id"])
    taxonomy = _create_taxonomy(client, org["org_headers"], is_default=True)

    c1 = client.post(
        f"{ASSESSMENTS_BASE}/{a1['id']}/classifications",
        headers=org["org_headers"],
        json={
            "taxonomy_template_id": taxonomy["id"],
            "classification_json": {
                "labels": [
                    {"group_key": "data_sensitivity", "label_key": "personal_data"},
                    {"group_key": "human_impact", "label_key": "material_human_impact"},
                ]
            },
            "confidence_level": "high",
            "justification": "initial manual assertion",
            "source_type": "operator_attestation",
        },
    )
    assert c1.status_code == 201

    snapshot = client.post(
        f"{ASSESSMENTS_BASE}/{a1['id']}/snapshots",
        headers=org["org_headers"],
        json={"note": "capture classification state"},
    )
    assert snapshot.status_code == 201
    snap_json = snapshot.json()["snapshot_json"]
    assert snap_json["risk_assessment"]["latest_classification_id"] == c1.json()["id"]
    assert snap_json["risk_assessment"]["classification_summary_json"] is not None
    assert "manual governance assertions" in snap_json["classification_caveat"]

    summary = client.get(f"{CLASSIFICATION_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    sbody = summary.json()
    assert sbody["total_classifications"] >= 1
    assert sbody["active_classifications"] >= 1
    assert sbody["default_taxonomy_id"] == taxonomy["id"]
    assert sbody["assessments_with_classifications"] >= 1
    assert sbody["assessments_without_classifications"] >= 1
    assert "manual governance assertions" in sbody["caveat"]

    contracts = client.get("/api/v1/ai-governance/contracts/phase6", headers=org["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"]: g for g in contracts.json()["groups"]}
    assert "ai_risk_classification_taxonomies" in groups
    assert "ai_risk_classification_records" in groups
    assessment_fields = set(groups["ai_risk_assessments"]["response_contract_fields"])
    assert {"latest_classification_id", "classification_status", "classification_summary_json"}.issubset(assessment_fields)

    assert "manual governance assertions" in c1.json()["caveat"]


def test_phase64_read_only_gets_no_mutation_and_audit_logs_for_persisted_actions(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p64-audit")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    taxonomy = _create_taxonomy(client, org["org_headers"], is_default=True)

    created = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications",
        headers=org["org_headers"],
        json={
            "taxonomy_template_id": taxonomy["id"],
            "classification_json": {"labels": [{"group_key": "human_impact", "label_key": "low_human_impact"}]},
            "justification": "audit test",
        },
    )
    assert created.status_code == 201

    before_rows = db_session.execute(select(func.count(AISystemRiskClassificationRecord.id))).scalar_one()
    before_tax_rows = db_session.execute(select(func.count(AISystemRiskClassificationTaxonomyTemplate.id))).scalar_one()
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    r1 = client.get(f"{ASSESSMENTS_BASE}/{assessment['id']}/classifications", headers=org["org_headers"])
    assert r1.status_code == 200
    r2 = client.get(f"{CLASSIFICATION_BASE}/{created.json()['id']}", headers=org["org_headers"])
    assert r2.status_code == 200
    r3 = client.get(f"{CLASSIFICATION_BASE}/summary", headers=org["org_headers"])
    assert r3.status_code == 200

    after_rows = db_session.execute(select(func.count(AISystemRiskClassificationRecord.id))).scalar_one()
    after_tax_rows = db_session.execute(select(func.count(AISystemRiskClassificationTaxonomyTemplate.id))).scalar_one()
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    assert before_rows == after_rows
    assert before_tax_rows == after_tax_rows
    assert before_audit == after_audit

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "ai_system_risk_classification_taxonomy.created" in actions
    assert "ai_system_risk_classification_record.created" in actions
