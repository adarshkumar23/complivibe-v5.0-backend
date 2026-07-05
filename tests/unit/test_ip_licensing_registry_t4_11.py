import uuid
from datetime import datetime, timedelta, timezone

from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/ip-assets"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _create_ai_system(client, headers: dict[str, str], *, name: str = "Fraud Agent", lifecycle_status: str = "production") -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={
            "name": name,
            "system_type": "agent",
            "lifecycle_status": lifecycle_status,
            "tags_json": ["core"],
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_asset(client, headers: dict[str, str], **overrides) -> dict:
    payload = {
        "name": "Model License A",
        "asset_type": "model_license",
        "licensor": "Acme Licensing Corp",
        "licensee": "Our Org",
    }
    payload.update(overrides)
    response = client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_list_get_update_soft_delete_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ipa-happy")
    headers = org["org_headers"]

    created = _create_asset(
        client,
        headers,
        name="Trademark - Acme Logo",
        asset_type="trademark",
        terms={"scope": "worldwide"},
    )
    assert created["name"] == "Trademark - Acme Logo"
    assert created["asset_type"] == "trademark"
    assert created["status"] == "active"
    assert created["organization_id"] == org["organization_id"]
    assert created["terms"] == {"scope": "worldwide"}

    listed = client.get(BASE, headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == created["id"]

    fetched = client.get(f"{BASE}/{created['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]

    updated = client.patch(
        f"{BASE}/{created['id']}",
        headers=headers,
        json={"licensee": "Updated Licensee", "status": "pending_renewal"},
    )
    assert updated.status_code == 200
    assert updated.json()["licensee"] == "Updated Licensee"
    assert updated.json()["status"] == "pending_renewal"

    deleted = client.delete(f"{BASE}/{created['id']}", headers=headers)
    assert deleted.status_code == 204

    # Soft-deleted assets should no longer appear in list/get.
    after_delete_list = client.get(BASE, headers=headers)
    assert after_delete_list.status_code == 200
    assert after_delete_list.json() == []

    after_delete_get = client.get(f"{BASE}/{created['id']}", headers=headers)
    assert after_delete_get.status_code == 404


def test_expiring_soon_ranks_active_ai_system_link_first(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ipa-expiring")
    headers = org["org_headers"]

    ai_system = _create_ai_system(client, headers, name="Active Production System", lifecycle_status="production")

    now = datetime.now(timezone.utc)
    soon_expiry = now + timedelta(days=10)

    linked_asset = _create_asset(
        client,
        headers,
        name="Linked License",
        asset_type="model_license",
        expiry_date=_iso(soon_expiry),
        linked_ai_system_id=ai_system["id"],
    )
    unlinked_asset = _create_asset(
        client,
        headers,
        name="Unlinked License",
        asset_type="dataset_license",
        expiry_date=_iso(soon_expiry - timedelta(days=1)),  # even sooner by date alone
    )

    response = client.get(f"{BASE}/expiring-soon", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2

    # Despite the unlinked asset expiring slightly sooner by date, the asset
    # linked to a still-active AI system must be ranked first (urgency, not
    # a flat date sort).
    assert body[0]["id"] == linked_asset["id"]
    assert body[0]["at_risk_ai_system"] is not None
    assert body[0]["at_risk_ai_system"]["id"] == ai_system["id"]
    assert body[0]["at_risk_ai_system"]["still_active"] is True

    assert body[1]["id"] == unlinked_asset["id"]
    assert body[1]["at_risk_ai_system"] is None


def test_expiring_soon_window_setting_controls_inclusion(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ipa-window")
    headers = org["org_headers"]

    # Default settings should exist / be creatable on first GET.
    settings = client.get(f"{BASE}/settings", headers=headers)
    assert settings.status_code == 200
    assert settings.json()["expiring_soon_window_days"] == 90

    now = datetime.now(timezone.utc)
    expiry_in_10_days = now + timedelta(days=10)
    asset = _create_asset(
        client,
        headers,
        name="Ten Day License",
        asset_type="patent",
        expiry_date=_iso(expiry_in_10_days),
    )

    narrowed = client.patch(f"{BASE}/settings", headers=headers, json={"expiring_soon_window_days": 5})
    assert narrowed.status_code == 200
    assert narrowed.json()["expiring_soon_window_days"] == 5

    excluded = client.get(f"{BASE}/expiring-soon", headers=headers)
    assert excluded.status_code == 200
    assert asset["id"] not in {item["id"] for item in excluded.json()}

    widened = client.patch(f"{BASE}/settings", headers=headers, json={"expiring_soon_window_days": 15})
    assert widened.status_code == 200
    assert widened.json()["expiring_soon_window_days"] == 15

    included = client.get(f"{BASE}/expiring-soon", headers=headers)
    assert included.status_code == 200
    assert asset["id"] in {item["id"] for item in included.json()}


def test_link_ai_system_from_different_org_returns_404(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="ipa-cross-a")
    org2 = bootstrap_org_user(client, email_prefix="ipa-cross-b")

    other_org_ai_system = _create_ai_system(client, org2["org_headers"], name="Other Org System")

    response = client.post(
        BASE,
        headers=org1["org_headers"],
        json={
            "name": "Cross Org License",
            "asset_type": "model_license",
            "linked_ai_system_id": other_org_ai_system["id"],
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Linked AI system not found"


def test_invalid_asset_type_returns_422(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ipa-invalid-type")
    response = client.post(
        BASE,
        headers=org["org_headers"],
        json={"name": "Bad Type Asset", "asset_type": "copyright"},
    )
    assert response.status_code == 422


def test_audit_log_rows_exist_for_create_update_delete(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ipa-audit")
    headers = org["org_headers"]

    created = _create_asset(client, headers, name="Audited Asset")
    updated = client.patch(
        f"{BASE}/{created['id']}", headers=headers, json={"licensor": "New Licensor"}
    )
    assert updated.status_code == 200
    deleted = client.delete(f"{BASE}/{created['id']}", headers=headers)
    assert deleted.status_code == 204

    logs = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.entity_id == uuid.UUID(created["id"]),
        )
        .all()
    )
    actions = {log.action for log in logs}
    assert "ip_asset.created" in actions
    assert "ip_asset.updated" in actions
    assert "ip_asset.deleted" in actions
