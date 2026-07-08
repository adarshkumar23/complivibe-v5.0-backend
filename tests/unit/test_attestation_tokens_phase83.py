from datetime import UTC, datetime, timedelta
from time import sleep


def _register(client, email: str, password: str, organization_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": organization_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    response = client.get("/api/v1/organizations/me", headers=_headers(token))
    assert response.status_code == 200
    return response.json()[0]["id"]


def _completed_export_attestation(client, token: str, org_id: str) -> str:
    created = client.post(
        "/api/v1/exports/jobs",
        headers=_headers(token, org_id),
        json={"export_type": "evidence_manifest_json", "title": "Attestation Token Export"},
    )
    assert created.status_code == 201
    export_id = created.json()["id"]

    run = client.post(f"/api/v1/exports/jobs/{export_id}/run", headers=_headers(token, org_id))
    assert run.status_code == 200

    attestation = client.post(
        f"/api/v1/exports/jobs/{export_id}/attestations",
        headers=_headers(token, org_id),
        json={"attestation_type": "internal_review", "statement": "Verified"},
    )
    assert attestation.status_code == 201
    return attestation.json()["id"]


def test_attestation_token_create_validate_wrong_token_and_expiry(client):
    owner = _register(client, "t83-owner1@example.com", "Pass1234!@", "T83 Org1")
    org_id = _org_id(client, owner)
    attestation_id = _completed_export_attestation(client, owner, org_id)

    create = client.post(
        "/api/v1/attestation-tokens",
        headers=_headers(owner, org_id),
        json={
            "purpose": "auditor_portal_lookup",
            "scope": {"roles": ["auditor"], "read_only": True},
            "linked_entity_type": "export_attestation",
            "linked_entity_id": attestation_id,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=3)).isoformat(),
        },
    )
    assert create.status_code == 201
    created_body = create.json()
    assert created_body["linked_entity_type"] == "export_attestation"
    token = created_body["plaintext_token"]

    valid = client.get(f"/api/v1/attestation-tokens/{token}")
    assert valid.status_code == 200
    valid_body = valid.json()
    assert valid_body["organization_id"] == org_id
    assert valid_body["linked_entity_id"] == attestation_id
    assert valid_body["scope"] == {"roles": ["auditor"], "read_only": True}
    assert valid_body["validation_count"] >= 1

    bad_token = f"{token}x"
    wrong = client.get(f"/api/v1/attestation-tokens/{bad_token}")
    assert wrong.status_code == 401

    sleep(3.2)
    expired = client.get(f"/api/v1/attestation-tokens/{token}")
    assert expired.status_code == 410


def test_attestation_token_enforces_scoped_entity_and_no_cross_tenant_leakage(client):
    owner_a = _register(client, "t83-owner2a@example.com", "Pass1234!@", "T83 Org2A")
    owner_b = _register(client, "t83-owner2b@example.com", "Pass1234!@", "T83 Org2B")
    org_a = _org_id(client, owner_a)
    org_b = _org_id(client, owner_b)

    attestation_a = _completed_export_attestation(client, owner_a, org_a)
    attestation_b = _completed_export_attestation(client, owner_b, org_b)

    cross = client.post(
        "/api/v1/attestation-tokens",
        headers=_headers(owner_a, org_a),
        json={
            "purpose": "cross_tenant_probe",
            "scope": {"allowed_entity_ids": [attestation_b]},
            "linked_entity_type": "export_attestation",
            "linked_entity_id": attestation_b,
            "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        },
    )
    assert cross.status_code == 404

    scoped = client.post(
        "/api/v1/attestation-tokens",
        headers=_headers(owner_a, org_a),
        json={
            "purpose": "export_attestation_view",
            "scope": {"allowed_entity_ids": [attestation_a]},
            "linked_entity_type": "export_attestation",
            "linked_entity_id": attestation_a,
            "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        },
    )
    assert scoped.status_code == 201
    token = scoped.json()["plaintext_token"]

    validated = client.get(f"/api/v1/attestation-tokens/{token}")
    assert validated.status_code == 200
    body = validated.json()
    assert body["organization_id"] == org_a
    assert body["linked_entity_id"] == attestation_a
    assert body["linked_entity_id"] != attestation_b


def test_attestation_token_revoke_immediately_invalidates_and_is_idempotent(client):
    owner = _register(client, "t83-owner3@example.com", "Pass1234!@", "T83 Org3")
    org_id = _org_id(client, owner)
    attestation_id = _completed_export_attestation(client, owner, org_id)

    created = client.post(
        "/api/v1/attestation-tokens",
        headers=_headers(owner, org_id),
        json={
            "purpose": "auditor_portal_lookup",
            "scope": {},
            "linked_entity_type": "export_attestation",
            "linked_entity_id": attestation_id,
            "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        },
    )
    assert created.status_code == 201
    token_id = created.json()["token_id"]
    token = created.json()["plaintext_token"]

    valid_before = client.get(f"/api/v1/attestation-tokens/{token}")
    assert valid_before.status_code == 200

    revoked = client.post(
        f"/api/v1/attestation-tokens/{token_id}/revoke",
        headers=_headers(owner, org_id),
        json={"reason": "credential leaked in CI logs"},
    )
    assert revoked.status_code == 200
    revoked_body = revoked.json()
    assert revoked_body["status"] == "revoked"
    assert revoked_body["revoked_at"] is not None
    assert revoked_body["revocation_reason"] == "credential leaked in CI logs"

    denied = client.get(f"/api/v1/attestation-tokens/{token}")
    assert denied.status_code == 401

    # Revoking an already-revoked token is idempotent, not an error.
    revoked_again = client.post(
        f"/api/v1/attestation-tokens/{token_id}/revoke",
        headers=_headers(owner, org_id),
        json={"reason": "duplicate request"},
    )
    assert revoked_again.status_code == 200
    assert revoked_again.json()["status"] == "revoked"


def test_attestation_token_revoke_is_org_scoped_and_rejects_expired(client):
    owner_a = _register(client, "t83-owner4a@example.com", "Pass1234!@", "T83 Org4A")
    owner_b = _register(client, "t83-owner4b@example.com", "Pass1234!@", "T83 Org4B")
    org_a = _org_id(client, owner_a)
    org_b = _org_id(client, owner_b)
    attestation_a = _completed_export_attestation(client, owner_a, org_a)

    created = client.post(
        "/api/v1/attestation-tokens",
        headers=_headers(owner_a, org_a),
        json={
            "purpose": "auditor_portal_lookup",
            "scope": {},
            "linked_entity_type": "export_attestation",
            "linked_entity_id": attestation_a,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=2)).isoformat(),
        },
    )
    assert created.status_code == 201
    token_id = created.json()["token_id"]
    token = created.json()["plaintext_token"]

    cross_org_revoke = client.post(
        f"/api/v1/attestation-tokens/{token_id}/revoke",
        headers=_headers(owner_b, org_b),
        json={"reason": "not my token"},
    )
    assert cross_org_revoke.status_code == 404

    sleep(2.2)
    expired = client.get(f"/api/v1/attestation-tokens/{token}")
    assert expired.status_code == 410

    revoke_expired = client.post(
        f"/api/v1/attestation-tokens/{token_id}/revoke",
        headers=_headers(owner_a, org_a),
        json={"reason": "too late"},
    )
    assert revoke_expired.status_code == 409
