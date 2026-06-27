from __future__ import annotations

import uuid

from sqlalchemy import inspect, select

from app.ai_governance.services.shadow_ai_service import ShadowAIService
from app.models.ai_governance_event import AIGovernanceEvent
from app.models.ai_system import AISystem
from app.models.ai_use_case import AIUseCase
from app.models.shadow_ai_detection import ShadowAIDetection
from tests.helpers.auth_org import bootstrap_org_user


SYSTEMS_BASE = "/api/v1/ai-governance/systems"
SHADOW_BASE = "/api/v1/ai-governance/shadow-ai"
DASHBOARD_URL = "/api/v1/ai-governance/dashboard"
TEMPLATES_BASE = "/api/v1/compliance/questionnaire-templates"
RESPONSES_BASE = "/api/v1/compliance/questionnaire-responses"
VENDORS_BASE = "/api/v1/compliance/vendors"


def _system_payload(org: dict, *, name: str, system_type: str = "model", risk_tier: str | None = None) -> dict:
    return {
        "name": name,
        "system_type": system_type,
        "owner_id": org["user_id"],
        "description": "System description",
        "deployment_status": "development",
        "risk_tier": risk_tier,
        "purpose": "Assist security operations",
    }


def _create_vendor(client, headers: dict[str, str], *, owner_user_id: str, name: str) -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
            "risk_tier": "not_assessed",
            "status": "active",
            "data_access": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_a51_ai_system_inventory_lifecycle_and_summary(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a51-org")
    org_id = uuid.UUID(org["organization_id"])

    # All allowed system types.
    for idx, system_type in enumerate(["model", "use_case", "agent", "application", "data_pipeline"]):
        created = client.post(
            SYSTEMS_BASE,
            headers=org["org_headers"],
            json=_system_payload(org, name=f"system-{idx}", system_type=system_type),
        )
        assert created.status_code == 201
        assert created.json()["system_type"] == system_type

    invalid = client.post(
        SYSTEMS_BASE,
        headers=org["org_headers"],
        json=_system_payload(org, name="invalid-system", system_type="invalid_type"),
    )
    assert invalid.status_code == 422

    first_system_id = client.get(SYSTEMS_BASE, headers=org["org_headers"]).json()[0]["id"]

    status_update = client.post(
        f"{SYSTEMS_BASE}/{first_system_id}/status",
        headers=org["org_headers"],
        json={"new_status": "staging"},
    )
    assert status_update.status_code == 200
    assert status_update.json()["deployment_status"] == "staging"

    # Deletion only for decommissioned.
    blocked_delete = client.delete(f"{SYSTEMS_BASE}/{first_system_id}", headers=org["org_headers"])
    assert blocked_delete.status_code == 422

    decommissioned = client.post(
        f"{SYSTEMS_BASE}/{first_system_id}/status",
        headers=org["org_headers"],
        json={"new_status": "decommissioned"},
    )
    assert decommissioned.status_code == 200

    deleted = client.delete(f"{SYSTEMS_BASE}/{first_system_id}", headers=org["org_headers"])
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None

    summary = client.get(f"{SYSTEMS_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["total"] == 4
    assert isinstance(summary_body["by_system_type"], dict)
    assert isinstance(summary_body["by_deployment_status"], dict)

    # Vector-backed embedding column exists and is nullable.
    columns = {col["name"]: col for col in inspect(db_session.bind).get_columns("ai_systems")}
    assert "description_embedding" in columns
    assert columns["description_embedding"]["nullable"] is True

    # Governance event logged on create.
    created_events = db_session.execute(
        select(AIGovernanceEvent).where(
            AIGovernanceEvent.organization_id == org_id,
            AIGovernanceEvent.event_type == "system.registered",
        )
    ).scalars().all()
    assert len(created_events) >= 1

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="a51-org-b")
    list_b = client.get(SYSTEMS_BASE, headers=org_b["org_headers"])
    assert list_b.status_code == 200
    assert all(row["organization_id"] == org_b["organization_id"] for row in list_b.json())


def test_a52_shadow_ai_discovery_flows(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a52-org")
    org_id = uuid.UUID(org["organization_id"])

    manual = client.post(
        f"{SHADOW_BASE}/report",
        headers=org["org_headers"],
        json={"detected_name": "chatgpt", "notes": "Observed in business unit"},
    )
    assert manual.status_code == 201
    det_id = manual.json()["id"]
    assert manual.json()["status"] == "new"

    duplicate = client.post(
        f"{SHADOW_BASE}/report",
        headers=org["org_headers"],
        json={"detected_name": "chatgpt", "notes": "Duplicate"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == det_id

    service = ShadowAIService(db_session)
    found = service.scan_and_create(org_id, "we use chatgpt for drafts", uuid.UUID(org["user_id"]))
    assert len(found) == 0  # already reported manually, so deduped

    empty = service.scan_and_create(org_id, "no relevant tool mention here", uuid.UUID(org["user_id"]))
    assert empty == []

    second = client.post(
        f"{SHADOW_BASE}/report",
        headers=org["org_headers"],
        json={"detected_name": "claude", "notes": "Another tool"},
    )
    assert second.status_code == 201

    review = client.post(f"{SHADOW_BASE}/detections/{second.json()['id']}/review", headers=org["org_headers"])
    assert review.status_code == 200
    assert review.json()["status"] == "under_review"

    register = client.post(
        f"{SHADOW_BASE}/detections/{second.json()['id']}/register",
        headers=org["org_headers"],
        json={
            "name": "Claude Assistant",
            "system_type": "application",
            "owner_id": org["user_id"],
            "deployment_status": "development",
        },
    )
    assert register.status_code == 201
    system_id = register.json()["id"]

    reloaded_detection = db_session.execute(
        select(ShadowAIDetection).where(ShadowAIDetection.id == uuid.UUID(second.json()["id"]))
    ).scalar_one()
    assert reloaded_detection.status == "registered"
    assert reloaded_detection.registered_system_id == uuid.UUID(system_id)

    third = client.post(
        f"{SHADOW_BASE}/report",
        headers=org["org_headers"],
        json={"detected_name": "perplexity", "notes": "Dismiss this"},
    )
    assert third.status_code == 201
    dismissed = client.post(
        f"{SHADOW_BASE}/detections/{third.json()['id']}/dismiss",
        headers=org["org_headers"],
        json={"notes": "False positive"},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    filtered = client.get(f"{SHADOW_BASE}/detections?status=dismissed", headers=org["org_headers"])
    assert filtered.status_code == 200
    assert all(row["status"] == "dismissed" for row in filtered.json())


def test_a53_use_cases_and_dashboard_counts(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a53-org")

    system_a = client.post(
        SYSTEMS_BASE,
        headers=org["org_headers"],
        json=_system_payload(org, name="system-a", system_type="model", risk_tier="high"),
    )
    assert system_a.status_code == 201

    system_b = client.post(
        SYSTEMS_BASE,
        headers=org["org_headers"],
        json=_system_payload(org, name="system-b", system_type="application", risk_tier="limited"),
    )
    assert system_b.status_code == 201

    create_uc = client.post(
        f"{SYSTEMS_BASE}/{system_a.json()['id']}/use-cases",
        headers=org["org_headers"],
        json={
            "name": "Fraud triage",
            "business_owner_id": org["user_id"],
            "use_case_type": "classification",
            "is_high_stakes": True,
            "description": "Classifies suspicious behavior",
        },
    )
    assert create_uc.status_code == 201
    use_case_id = create_uc.json()["id"]

    events = db_session.execute(
        select(AIGovernanceEvent).where(
            AIGovernanceEvent.organization_id == uuid.UUID(org["organization_id"]),
            AIGovernanceEvent.event_type == "use_case.high_stakes_created",
        )
    ).scalars().all()
    assert len(events) >= 1

    listed = client.get(
        f"{SYSTEMS_BASE}/{system_a.json()['id']}/use-cases",
        headers=org["org_headers"],
    )
    assert listed.status_code == 200
    assert all(row["ai_system_id"] == system_a.json()["id"] for row in listed.json())

    updated = client.patch(
        f"{SYSTEMS_BASE}/{system_a.json()['id']}/use-cases/{use_case_id}",
        headers=org["org_headers"],
        json={"name": "Fraud triage v2"},
    )
    assert updated.status_code == 200

    deleted = client.delete(
        f"{SYSTEMS_BASE}/{system_a.json()['id']}/use-cases/{use_case_id}",
        headers=org["org_headers"],
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None

    # Wrong org gets isolation behavior.
    org_b = bootstrap_org_user(client, email_prefix="a53-org-b")
    wrong_org_fetch = client.get(
        f"{SYSTEMS_BASE}/{system_a.json()['id']}/use-cases/{use_case_id}",
        headers=org_b["org_headers"],
    )
    assert wrong_org_fetch.status_code == 404

    wrong_system_create = client.post(
        f"{SYSTEMS_BASE}/{system_a.json()['id']}/use-cases",
        headers=org_b["org_headers"],
        json={
            "name": "Invalid",
            "business_owner_id": org_b["user_id"],
            "use_case_type": "classification",
        },
    )
    assert wrong_system_create.status_code == 422

    # Dashboard now uses real ai_system and shadow-ai counts.
    shadow_new = client.post(
        f"{SHADOW_BASE}/report",
        headers=org["org_headers"],
        json={"detected_name": "chatgpt", "notes": "new detection"},
    )
    assert shadow_new.status_code == 201

    dashboard = client.get(DASHBOARD_URL, headers=org["org_headers"])
    assert dashboard.status_code == 200
    dashboard_body = dashboard.json()
    assert dashboard_body["ai_systems_by_tier"]["high"] >= 1
    assert dashboard_body["shadow_ai_detected_count"] >= 1

    # Ensure use-case row exists in DB.
    soft_deleted = db_session.execute(
        select(AIUseCase).where(AIUseCase.id == uuid.UUID(use_case_id))
    ).scalar_one()
    assert soft_deleted.deleted_at is not None

    # Detection row exists.
    detection_rows = db_session.execute(
        select(ShadowAIDetection).where(ShadowAIDetection.organization_id == uuid.UUID(org["organization_id"]))
    ).scalars().all()
    assert len(detection_rows) >= 1

    # AI systems remain org scoped.
    scoped_rows = db_session.execute(
        select(AISystem).where(AISystem.organization_id == uuid.UUID(org["organization_id"]), AISystem.deleted_at.is_(None))
    ).scalars().all()
    assert len(scoped_rows) >= 2


def test_a52_questionnaire_submit_answer_triggers_shadow_scan(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a52-q-hook")
    vendor = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Questionnaire Hook Vendor")

    templates = client.get(TEMPLATES_BASE, headers=org["org_headers"])
    assert templates.status_code == 200
    sig = next(row for row in templates.json() if row["template_type"] == "sig_lite")

    create_response = client.post(
        RESPONSES_BASE,
        headers=org["org_headers"],
        json={"vendor_id": vendor["id"], "template_id": sig["id"], "title": "Hook Run"},
    )
    assert create_response.status_code == 201
    response_id = create_response.json()["id"]

    detail = client.get(f"{RESPONSES_BASE}/{response_id}", headers=org["org_headers"])
    assert detail.status_code == 200
    first_question_id = detail.json()["answers"][0]["question_id"]

    submit = client.post(
        f"{RESPONSES_BASE}/{response_id}/answers",
        headers=org["org_headers"],
        json={
            "question_id": first_question_id,
            "answer_value": "Yes",
            "answer_text": "Our team uses chatgpt for drafting internal summaries.",
        },
    )
    assert submit.status_code == 200

    rows = db_session.execute(
        select(ShadowAIDetection).where(
            ShadowAIDetection.organization_id == uuid.UUID(org["organization_id"]),
            ShadowAIDetection.detected_name == "chatgpt",
        )
    ).scalars().all()
    assert len(rows) >= 1
