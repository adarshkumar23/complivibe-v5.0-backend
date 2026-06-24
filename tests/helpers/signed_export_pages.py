import copy
from typing import Any

EXPORT_ENDPOINT = "/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events/export"


def generate_signed_verification_export_page(
    client,
    org_headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_payload = dict(payload or {})
    request_payload.setdefault("include_internal_signature", True)
    response = client.post(EXPORT_ENDPOINT, headers=org_headers, json=request_payload)
    assert response.status_code == 200
    return response.json()


def generate_unsigned_verification_export_page(
    client,
    org_headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_payload = dict(payload or {})
    request_payload["include_internal_signature"] = False
    response = client.post(EXPORT_ENDPOINT, headers=org_headers, json=request_payload)
    assert response.status_code == 200
    return response.json()


def tamper_export_page_event(export_page: dict[str, Any]) -> dict[str, Any]:
    tampered = copy.deepcopy(export_page)
    events = tampered.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Cannot tamper event payload: export page has no events")
    event = events[0]
    if not isinstance(event, dict):
        raise ValueError("Cannot tamper event payload: first event must be an object")
    event["trusted"] = not bool(event.get("trusted"))
    return tampered


def tamper_export_page_filters(export_page: dict[str, Any]) -> dict[str, Any]:
    tampered = copy.deepcopy(export_page)
    page = tampered.get("page")
    if not isinstance(page, dict):
        raise ValueError("Cannot tamper page metadata: page must be an object")
    current_limit = page.get("limit")
    page["limit"] = (int(current_limit) + 1) if isinstance(current_limit, int) else 1
    return tampered


def remove_export_signature_field(export_page: dict[str, Any], field_name: str) -> dict[str, Any]:
    tampered = copy.deepcopy(export_page)
    integrity = tampered.get("export_integrity")
    if not isinstance(integrity, dict):
        raise ValueError("Cannot remove signature field: export_integrity must be an object")
    integrity.pop(field_name, None)
    return tampered


def replace_export_key_id(export_page: dict[str, Any], key_id: str) -> dict[str, Any]:
    tampered = copy.deepcopy(export_page)
    integrity = tampered.get("export_integrity")
    if not isinstance(integrity, dict):
        raise ValueError("Cannot replace key_id: export_integrity must be an object")
    integrity["key_id"] = key_id
    return tampered
