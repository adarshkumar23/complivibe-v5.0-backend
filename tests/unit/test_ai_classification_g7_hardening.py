from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.ai_system import AISystem
from sqlalchemy import select
from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"


def _create_system(client, headers: dict[str, str], owner_id: str, name: str = "AI System") -> str:
    response = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_guided_classification_explains_triggering_criterion(client):
    org = bootstrap_org_user(client, email_prefix="g7-class-explain")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="Guided System")

    resp = client.post(
        f"{SYSTEMS_BASE}/{system_id}/classify/submit",
        headers=org["org_headers"],
        json={"answers": {"biometric_data": "yes"}},
    )
    assert resp.status_code == 200
    body = resp.json()

    # INTELLIGENT: must say *why* it's high risk, not just "risk_tier": "high".
    assert body["risk_tier"] == "high"
    assert body["classification_explanation"] is not None
    assert "biometric" in body["classification_explanation"].lower()
    assert body["reassessment_required"] is False


def test_manual_classification_explains_from_notes(client):
    org = bootstrap_org_user(client, email_prefix="g7-class-manual")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="Manual System")

    resp = client.post(
        f"{SYSTEMS_BASE}/{system_id}/classify/manual",
        headers=org["org_headers"],
        json={"risk_tier": "high", "notes": "Legal deemed it high risk pending DPIA"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification_explanation"] is not None
    assert "DPIA" in body["classification_explanation"]


def test_reassessment_required_after_system_edited(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-class-stale")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="Stale Classify System")

    submit = client.post(
        f"{SYSTEMS_BASE}/{system_id}/classify/submit",
        headers=org["org_headers"],
        json={"answers": {"employment_decisions": "yes"}},
    )
    assert submit.status_code == 200
    assert submit.json()["reassessment_required"] is False

    # CONTEXT-CONSCIOUS: once the registered system is edited after the
    # classification was recorded, the tier must be flagged as possibly stale.
    system_row = db_session.execute(select(AISystem).where(AISystem.id == uuid.UUID(system_id))).scalar_one()
    system_row.updated_at = datetime.now(UTC) + timedelta(days=1)
    db_session.commit()

    fetched = client.get(f"{SYSTEMS_BASE}/{system_id}/classification", headers=org["org_headers"])
    assert fetched.status_code == 200
    assert fetched.json()["reassessment_required"] is True
