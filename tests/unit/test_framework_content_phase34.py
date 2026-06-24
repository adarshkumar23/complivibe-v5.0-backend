import uuid

from app.models.audit_log import AuditLog
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.framework_content_import import FrameworkContentImport
from app.models.framework_section import FrameworkSection
from app.models.framework_version import FrameworkVersion
from app.models.obligation_content_version import ObligationContentVersion


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _first_framework(client, token: str) -> dict:
    frameworks = client.get("/api/v1/frameworks", headers=_headers(token))
    assert frameworks.status_code == 200
    return frameworks.json()[0]


def _first_obligation(client, token: str, framework_id: str) -> dict:
    obligations = client.get(f"/api/v1/frameworks/{framework_id}/obligations", headers=_headers(token))
    assert obligations.status_code == 200
    items = obligations.json()
    assert items
    return items[0]


def _framework_with_obligation(client, token: str) -> tuple[dict, dict]:
    frameworks = client.get("/api/v1/frameworks", headers=_headers(token))
    assert frameworks.status_code == 200
    for framework in frameworks.json():
        obligations = client.get(f"/api/v1/frameworks/{framework['id']}/obligations", headers=_headers(token))
        assert obligations.status_code == 200
        items = obligations.json()
        if items:
            return framework, items[0]
    raise AssertionError("No framework with obligations found")


def test_framework_versions_and_sections_create_list_and_validate(client):
    owner = _register(client, "p34-owner1@example.com", "Pass1234!@", "P34 Org1")
    org = _org_id(client, owner)
    framework = _first_framework(client, owner)

    invalid_cov = client.post(
        f"/api/v1/frameworks/{framework['id']}/versions",
        headers=_headers(owner, org),
        json={
            "version_label": "v-bad",
            "status": "active",
            "coverage_level": "bad_level",
        },
    )
    assert invalid_cov.status_code in {400, 422}

    created_version = client.post(
        f"/api/v1/frameworks/{framework['id']}/versions",
        headers=_headers(owner, org),
        json={
            "version_label": "v-2026-06",
            "status": "active",
            "coverage_level": "starter",
        },
    )
    assert created_version.status_code == 201

    versions = client.get(f"/api/v1/frameworks/{framework['id']}/versions", headers=_headers(owner, org))
    assert versions.status_code == 200
    assert any(v["version_label"] == "v-2026-06" for v in versions.json())

    created_section = client.post(
        f"/api/v1/frameworks/{framework['id']}/sections",
        headers=_headers(owner, org),
        json={"section_code": "ART-1", "title": "Article 1", "status": "active"},
    )
    assert created_section.status_code == 201

    duplicate_section = client.post(
        f"/api/v1/frameworks/{framework['id']}/sections",
        headers=_headers(owner, org),
        json={"section_code": "ART-1", "title": "Article 1 duplicate", "status": "active"},
    )
    assert duplicate_section.status_code == 400

    sections = client.get(f"/api/v1/frameworks/{framework['id']}/sections", headers=_headers(owner, org))
    assert sections.status_code == 200
    assert any(s["section_code"] == "ART-1" for s in sections.json())


def test_obligation_content_evidence_suggestion_questions_and_detail(client):
    owner = _register(client, "p34-owner2@example.com", "Pass1234!@", "P34 Org2")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)

    question = client.post(
        f"/api/v1/frameworks/{framework['id']}/applicability-questions",
        headers=_headers(owner, org),
        json={
            "obligation_id": obligation["id"],
            "question_key": "q1",
            "question_text": "Is this applicable?",
            "answer_type": "boolean",
            "required": True,
        },
    )
    assert question.status_code == 201

    content_v1 = client.post(
        f"/api/v1/obligations/{obligation['id']}/content-versions",
        headers=_headers(owner, org),
        json={
            "version_label": "1.0",
            "obligation_text": "Initial text",
            "coverage_level": "starter",
            "review_status": "unreviewed",
        },
    )
    assert content_v1.status_code == 201

    content_v2 = client.post(
        f"/api/v1/obligations/{obligation['id']}/content-versions",
        headers=_headers(owner, org),
        json={
            "version_label": "1.1",
            "obligation_text": "Updated text",
            "coverage_level": "partial",
            "review_status": "internal_review",
        },
    )
    assert content_v2.status_code == 201

    versions = client.get(f"/api/v1/obligations/{obligation['id']}/content-versions", headers=_headers(owner, org))
    assert versions.status_code == 200
    labels = {v["version_label"] for v in versions.json()}
    assert {"1.0", "1.1"}.issubset(labels)

    evidence_req = client.post(
        f"/api/v1/obligations/{obligation['id']}/evidence-requirements",
        headers=_headers(owner, org),
        json={
            "requirement_key": "ev-1",
            "title": "Policy doc",
            "evidence_type": "policy_document",
            "required": True,
        },
    )
    assert evidence_req.status_code == 201

    suggestion = client.post(
        f"/api/v1/obligations/{obligation['id']}/control-suggestions",
        headers=_headers(owner, org),
        json={
            "control_title": "Access review control",
            "control_description": "Review access quarterly",
            "priority": "high",
        },
    )
    assert suggestion.status_code == 201

    detail = client.get(f"/api/v1/obligations/{obligation['id']}", headers=_headers(owner, org))
    assert detail.status_code == 200
    body = detail.json()
    assert body["current_content_version"]["version_label"] == "1.1"
    assert body["coverage_level"] == "partial"
    assert len(body["evidence_requirements"]) >= 1
    assert len(body["control_suggestions"]) >= 1
    assert len(body["applicability_questions"]) >= 1


def test_apply_control_suggestion_is_org_scoped_and_idempotent(client, db_session):
    owner1 = _register(client, "p34-owner3@example.com", "Pass1234!@", "P34 Org3")
    org1 = _org_id(client, owner1)
    owner2 = _register(client, "p34-owner4@example.com", "Pass1234!@", "P34 Org4")
    org2 = _org_id(client, owner2)

    framework, obligation = _framework_with_obligation(client, owner1)

    activate = client.post(
        f"/api/v1/frameworks/{framework['id']}/activate",
        headers=_headers(owner1, org1),
        json={},
    )
    assert activate.status_code == 200

    suggestion = client.post(
        f"/api/v1/obligations/{obligation['id']}/control-suggestions",
        headers=_headers(owner1, org1),
        json={"control_title": "Suggestion to apply", "priority": "normal"},
    )
    assert suggestion.status_code == 201
    suggestion_id = suggestion.json()["id"]

    cross_tenant = client.post(
        f"/api/v1/obligations/{obligation['id']}/control-suggestions/{suggestion_id}/apply",
        headers=_headers(owner2, org2),
    )
    assert cross_tenant.status_code in {400, 404}

    apply_1 = client.post(
        f"/api/v1/obligations/{obligation['id']}/control-suggestions/{suggestion_id}/apply",
        headers=_headers(owner1, org1),
    )
    assert apply_1.status_code == 200
    control_id_1 = apply_1.json()["id"]

    apply_2 = client.post(
        f"/api/v1/obligations/{obligation['id']}/control-suggestions/{suggestion_id}/apply",
        headers=_headers(owner1, org1),
    )
    assert apply_2.status_code == 200
    assert apply_2.json()["id"] == control_id_1

    controls = db_session.query(Control).filter(Control.organization_id == uuid.UUID(org1), Control.suggestion_source_id == uuid.UUID(suggestion_id)).all()
    assert len(controls) == 1

    mappings = (
        db_session.query(ControlObligationMapping)
        .filter(
            ControlObligationMapping.organization_id == uuid.UUID(org1),
            ControlObligationMapping.control_id == uuid.UUID(control_id_1),
            ControlObligationMapping.obligation_id == uuid.UUID(obligation["id"]),
            ControlObligationMapping.status == "active",
        )
        .all()
    )
    assert len(mappings) == 1


def test_framework_content_summary_and_import_preview_apply_idempotent_and_seed_caveat(client, db_session):
    owner = _register(client, "p34-owner5@example.com", "Pass1234!@", "P34 Org5")
    org = _org_id(client, owner)
    framework = _first_framework(client, owner)

    summary_before = client.get(f"/api/v1/frameworks/{framework['id']}/content-summary", headers=_headers(owner, org))
    assert summary_before.status_code == 200
    assert summary_before.json()["framework_id"] == framework["id"]

    payload = {
        "import_type": "starter_pack",
        "coverage_level": "starter",
        "source_name": "internal-starter",
        "source_reference": "phase34-test",
        "payload_json": {
            "sections": [{"section_code": "CH-1", "title": "Chapter 1"}],
            "obligations": [{"reference_code": "P34-OBL-1", "title": "Starter obligation", "jurisdiction": "International"}],
            "content_versions": [{"reference_code": "P34-OBL-1", "version_label": "1.0", "obligation_text": "Starter text"}],
            "evidence_requirements": [{"reference_code": "P34-OBL-1", "requirement_key": "p34-ev-1", "title": "Starter evidence", "evidence_type": "policy_document"}],
            "control_suggestions": [{"reference_code": "P34-OBL-1", "control_title": "Starter control"}],
            "applicability_questions": [{"reference_code": "P34-OBL-1", "question_key": "p34-q-1", "question_text": "Applicable?", "answer_type": "boolean"}],
        },
    }

    preview = client.post(
        f"/api/v1/frameworks/{framework['id']}/content-imports/preview",
        headers=_headers(owner, org),
        json=payload,
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is True

    apply_1 = client.post(
        f"/api/v1/frameworks/{framework['id']}/content-imports/apply",
        headers=_headers(owner, org),
        json=payload,
    )
    assert apply_1.status_code == 200
    assert apply_1.json()["valid"] is True

    apply_2 = client.post(
        f"/api/v1/frameworks/{framework['id']}/content-imports/apply",
        headers=_headers(owner, org),
        json=payload,
    )
    assert apply_2.status_code == 200

    imports = db_session.query(FrameworkContentImport).all()
    assert len(imports) >= 2

    summary_after = client.get(f"/api/v1/frameworks/{framework['id']}/content-summary", headers=_headers(owner, org))
    assert summary_after.status_code == 200
    assert summary_after.json()["total_sections"] >= summary_before.json()["total_sections"]

    versions = client.get(f"/api/v1/frameworks/{framework['id']}/versions", headers=_headers(owner, org))
    assert versions.status_code == 200
    assert all(v["coverage_level"] != "full_verified" for v in versions.json())


def test_framework_content_phase34_audit_logs_present(client, db_session):
    owner = _register(client, "p34-owner6@example.com", "Pass1234!@", "P34 Org6")
    org = _org_id(client, owner)
    framework, obligation = _framework_with_obligation(client, owner)

    client.post(
        f"/api/v1/frameworks/{framework['id']}/versions",
        headers=_headers(owner, org),
        json={"version_label": "audit-v1", "status": "active", "coverage_level": "starter"},
    )
    client.post(
        f"/api/v1/frameworks/{framework['id']}/sections",
        headers=_headers(owner, org),
        json={"section_code": "AUD-1", "title": "Audit section"},
    )
    client.post(
        f"/api/v1/obligations/{obligation['id']}/content-versions",
        headers=_headers(owner, org),
        json={"version_label": "audit-1", "obligation_text": "audit", "coverage_level": "starter", "review_status": "unreviewed"},
    )

    actions = {
        row.action
        for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()
    }
    assert "framework_version.created" in actions
    assert "framework_section.created" in actions
    assert "obligation_content_version.created" in actions
