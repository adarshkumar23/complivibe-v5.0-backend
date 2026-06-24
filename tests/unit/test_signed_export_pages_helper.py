from tests.helpers.auth_org import bootstrap_org_user, org_headers
from tests.helpers.signed_export_pages import (
    generate_signed_verification_export_page,
    generate_unsigned_verification_export_page,
    remove_export_signature_field,
    replace_export_key_id,
    tamper_export_page_event,
    tamper_export_page_filters,
)


def _generate_manifest(client, token: str, org_id: str) -> dict:
    response = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(token, org_id),
        json={},
    )
    assert response.status_code == 201
    return response.json()


def _verify_manifest(client, token: str, org_id: str, manifest_id: str) -> dict:
    response = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=org_headers(token, org_id),
    )
    assert response.status_code == 200
    return response.json()


def test_signed_export_page_helpers_generate_signed_and_unsigned_pages(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p415-owner1", organization_name="P415 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, generated["manifest_id"])

    signed = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 10})
    unsigned = generate_unsigned_verification_export_page(client, org_headers(owner, org), {"limit": 10})

    assert signed["export_integrity"]["internal_signature"] is not None
    assert signed["export_integrity"]["key_id"] is not None
    assert unsigned["export_integrity"]["internal_signature"] is None
    assert unsigned["export_integrity"]["signature_algorithm"] is None


def test_signed_export_page_helpers_are_deterministic_and_non_mutating():
    original = {
        "events": [{"trusted": True, "id": "evt-1"}],
        "page": {"limit": 2},
        "export_integrity": {
            "internal_signature": "sig",
            "key_id": "key-1",
            "signature_algorithm": "HMAC-SHA256",
        },
    }

    tampered_event_first = tamper_export_page_event(original)
    tampered_event_second = tamper_export_page_event(original)
    tampered_filters_first = tamper_export_page_filters(original)
    tampered_filters_second = tamper_export_page_filters(original)
    removed = remove_export_signature_field(original, "internal_signature")
    replaced = replace_export_key_id(original, "forced-key")

    assert tampered_event_first["events"][0]["trusted"] is False
    assert tampered_event_second["events"][0]["trusted"] is False
    assert tampered_filters_first["page"]["limit"] == 3
    assert tampered_filters_second["page"]["limit"] == 3
    assert "internal_signature" not in removed["export_integrity"]
    assert replaced["export_integrity"]["key_id"] == "forced-key"

    assert original["events"][0]["trusted"] is True
    assert original["page"]["limit"] == 2
    assert original["export_integrity"]["internal_signature"] == "sig"
    assert original["export_integrity"]["key_id"] == "key-1"
