from __future__ import annotations

import uuid

from app.models.shadow_ai_detection import ShadowAIDetection
from sqlalchemy import select
from tests.helpers.auth_org import bootstrap_org_user

SHADOW_BASE = "/api/v1/ai-governance/shadow-ai"


def _system_payload(org: dict, *, name: str) -> dict:
    return {
        "name": name,
        "system_type": "application",
        "owner_id": org["user_id"],
        "deployment_status": "development",
    }


def test_detection_reason_and_age_surfaced(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-shadow-reason")

    resp = client.post(
        f"{SHADOW_BASE}/report",
        headers=org["org_headers"],
        json={"detected_name": "chatgpt", "notes": "seen in slack"},
    )
    assert resp.status_code == 201
    body = resp.json()

    # INTELLIGENT: the response must explain *why* this was flagged, not just
    # dump the raw detection_method/confidence columns.
    assert "detection_reason" in body
    assert body["detection_reason"], "detection_reason must not be empty"
    assert "manual" in body["detection_reason"].lower()
    assert body["confidence"] in body["detection_reason"]
    assert body["days_since_detected"] == 0

    # Confirm the row itself is unaffected by the added response fields.
    row = db_session.execute(
        select(ShadowAIDetection).where(ShadowAIDetection.id == uuid.UUID(body["id"]))
    ).scalar_one()
    assert row.detected_name == "chatgpt"


def test_list_detections_is_paginated(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-shadow-page")

    names = [f"shadow-tool-{i}" for i in range(5)]
    for name in names:
        r = client.post(f"{SHADOW_BASE}/report", headers=org["org_headers"], json={"detected_name": name})
        assert r.status_code == 201

    page1 = client.get(f"{SHADOW_BASE}/detections?skip=0&limit=2", headers=org["org_headers"])
    assert page1.status_code == 200
    assert len(page1.json()) == 2

    page2 = client.get(f"{SHADOW_BASE}/detections?skip=2&limit=2", headers=org["org_headers"])
    assert page2.status_code == 200
    assert len(page2.json()) == 2

    # No overlap between pages.
    ids_1 = {row["id"] for row in page1.json()}
    ids_2 = {row["id"] for row in page2.json()}
    assert ids_1.isdisjoint(ids_2)

    # limit is bounded like sibling endpoints (ai_systems list: le=200).
    bad = client.get(f"{SHADOW_BASE}/detections?limit=9999", headers=org["org_headers"])
    assert bad.status_code == 422


def test_double_registration_is_rejected(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-shadow-dup")

    reported = client.post(
        f"{SHADOW_BASE}/report", headers=org["org_headers"], json={"detected_name": "midjourney"}
    )
    det_id = reported.json()["id"]

    first = client.post(
        f"{SHADOW_BASE}/detections/{det_id}/register",
        headers=org["org_headers"],
        json=_system_payload(org, name="Midjourney Tool"),
    )
    assert first.status_code == 201
    first_system_id = first.json()["id"]

    # Registering the same, already-registered detection again must be
    # rejected rather than silently creating a second duplicate AI system.
    second = client.post(
        f"{SHADOW_BASE}/detections/{det_id}/register",
        headers=org["org_headers"],
        json=_system_payload(org, name="Midjourney Tool Duplicate"),
    )
    assert second.status_code == 422

    from app.models.ai_system import AISystem

    systems = db_session.execute(
        select(AISystem).where(AISystem.organization_id == uuid.UUID(org["organization_id"]))
    ).scalars().all()
    assert len(systems) == 1
    assert str(systems[0].id) == first_system_id
