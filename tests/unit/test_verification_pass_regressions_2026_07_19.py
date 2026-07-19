"""Regression tests for defects found in the 14-agent verification pass (2026-07-19).

1. DPIA approval bypass. "approved" is a member of ALLOWED_DPIA_STATUS and DPIAUpdate.status
   is an unconstrained `str | None`, so PATCH /privacy/dpias/{id} {"status": "approved"} reached
   the approved state holding only privacy:write -- skipping the privacy:approve permission and
   every gate in approve_dpia (four-eyes, assigned reviewer, fully answered checklist, DPO and
   supervisory-authority consultation) -- and landed in a state update_dpia then refuses to edit.

2. Connector-marketplace SSRF. _probe_connection fetched a tenant-supplied URL with
   follow_redirects=True and no assert_public_http_url guard, while attaching the connector's
   DECRYPTED credential as a bearer token. A tenant could point base_url at a host they control
   and harvest their own org's API key, or aim it at internal infrastructure (including the
   cloud metadata endpoint) and read the reachable/unreachable verdict as a port scanner.
"""

from __future__ import annotations

import pytest

from app.services.connector_marketplace_service import ConnectorMarketplaceService
from tests.helpers.auth_org import bootstrap_org_user

DPIA_BASE = "/api/v1/privacy/dpias"
ROPA_BASE = "/api/v1/privacy/ropa"


def _create_activity(client, headers: dict[str, str], owner_id: str):
    response = client.post(
        f"{ROPA_BASE}/activities",
        headers=headers,
        json={
            "name": "DPIA Activity",
            "description": "Processing personal data",
            "purpose": "Support operations",
            "legal_basis": "consent",
            "data_categories": ["email"],
            "special_categories": [],
            "data_subject_types": ["customers"],
            "retention_period": "1 year",
            "recipients": ["internal"],
            "international_transfers": False,
            "status": "active",
            "risk_level": "high",
            "owner_id": owner_id,
            "linked_data_asset_ids": [],
            "linked_subprocessor_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_dpia(client, headers: dict[str, str], activity_id: str):
    response = client.post(
        DPIA_BASE,
        headers=headers,
        json={
            "processing_activity_id": activity_id,
            "title": "Bypass probe",
            "nature_of_processing": "Collect and analyze user data",
            "risks_identified": ["Unauthorized access"],
            "mitigation_measures": ["Encryption"],
            "residual_risk_level": "medium",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("decision_status", ["approved", "rejected"])
def test_dpia_patch_cannot_assign_a_terminal_decision_status(client, decision_status):
    """PATCH must not be able to reach approved/rejected -- those are approve/reject only."""
    org = bootstrap_org_user(client, email_prefix="dpia-bypass")
    activity = _create_activity(client, org["org_headers"], org["user_id"])
    dpia = _create_dpia(client, org["org_headers"], activity["id"])

    response = client.patch(
        f"{DPIA_BASE}/{dpia['id']}",
        headers=org["org_headers"],
        json={"status": decision_status},
    )
    assert response.status_code == 422, response.text

    # And the DPIA is genuinely untouched, not merely reported as rejected.
    after = client.get(f"{DPIA_BASE}/{dpia['id']}", headers=org["org_headers"])
    assert after.status_code == 200, after.text
    assert after.json()["status"] != decision_status


def test_dpia_patch_still_allows_ordinary_workflow_statuses(client):
    """The guard must block only the two decisions, not normal editing."""
    org = bootstrap_org_user(client, email_prefix="dpia-workflow")
    activity = _create_activity(client, org["org_headers"], org["user_id"])
    dpia = _create_dpia(client, org["org_headers"], activity["id"])

    response = client.patch(
        f"{DPIA_BASE}/{dpia['id']}",
        headers=org["org_headers"],
        json={"status": "in_progress"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "in_progress"


@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1:8000/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "file:///etc/passwd",
    ],
)
def test_connector_probe_refuses_non_public_targets(target):
    """The probe carries a decrypted credential, so it must never reach an internal address.

    Asserting on reachable=False alone would be vacuous -- an unreachable host returns that too.
    The detail string proves the request was refused by the guard rather than attempted.
    """
    reachable, detail = ConnectorMarketplaceService._probe_connection(
        target, {"api_token": "super-secret-credential"}
    )
    assert reachable is False
    assert detail is not None
    assert "must" in detail, f"expected a guard refusal, got a network error: {detail!r}"


def test_connector_probe_does_not_follow_redirects_into_internal_addresses():
    """A pre-flight URL check alone is insufficient: a 302 would walk the credential past it."""
    import inspect

    source = inspect.getsource(ConnectorMarketplaceService._probe_connection)
    assert "follow_redirects=False" in source
    assert "assert_public_http_url" in source
