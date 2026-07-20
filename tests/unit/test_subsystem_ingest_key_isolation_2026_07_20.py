"""Regression tests for PAM/inbound-ingest key reuse (2026-07-20).

Before the fix, PAM, data-lineage, cookies, consent, security-ingest and
access-monitoring all authenticated their inbound X-CompliVibe-Key against ONE shared
key (the OpenMetadata/data-lineage integration key). A key leaked from any one (e.g. a
PAM agent) authenticated all the others for the same org.

Now each subsystem has its own key (key_type) in subsystem_ingest_keys, resolved by an
indexed hash lookup scoped to a single key_type. These tests prove the isolation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.services.subsystem_ingest_key_service import SubsystemIngestKeyService
from tests.helpers.auth_org import bootstrap_org_user

pytestmark = pytest.mark.usefixtures("seeded_reference_data")

PAM_BASE = "/api/v1/pam/sessions"
COOKIE_SCAN = "/api/v1/privacy/cookie-registry/scan-report"
LINEAGE_CONFIG = "/api/v1/data-observability/lineage/openmetadata/configure"
INGEST_KEYS = "/api/v1/integrations/ingest-keys"


def _pam_payload(external_session_id: str) -> dict:
    return {
        "external_session_id": external_session_id,
        "pam_provider": "teleport",
        "identity": "alice@example.com",
        "privileged_account": "root",
        "target_system": "prod-db-01",
        "target_resource_type": "database",
        "started_at": datetime(2026, 7, 5, 12, 0, tzinfo=UTC).isoformat(),
        "ended_at": datetime(2026, 7, 5, 12, 30, tzinfo=UTC).isoformat(),
        "raw_payload": {"event": "session.closed"},
    }


def _cookie_payload(domain: str = "example.com") -> dict:
    return {
        "domain": domain,
        "cookies": [
            {"name": "ga_cookie", "domain": domain, "category": "analytics", "is_third_party": True}
        ],
        "scanned_at": datetime(2026, 7, 5, 12, 0, tzinfo=UTC).isoformat(),
    }


def _provision(client, org_headers: dict[str, str], key_type: str) -> str:
    resp = client.post(INGEST_KEYS, headers=org_headers, json={"key_type": key_type})
    assert resp.status_code == 201, resp.text
    return resp.json()["api_key"]


def _configure_shared_openmetadata_key(client, org_headers: dict[str, str], key: str) -> str:
    resp = client.post(
        LINEAGE_CONFIG,
        headers=org_headers,
        json={"base_url": "https://metadata.example.test", "jwt_token": "jwt", "org_api_key": key},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["ingest_api_key"]


def test_shared_openmetadata_key_no_longer_authenticates_other_subsystems(client, db_session):
    """THE FLIP: the OpenMetadata/data-lineage ingest key (which pre-fix authenticated
    every inbound subsystem) is now the LINEAGE key only -- it must be rejected by PAM
    and cookie ingest."""
    org = bootstrap_org_user(client, email_prefix="sik-flip")
    shared = _configure_shared_openmetadata_key(client, org["org_headers"], "shared-omd-key-123456")

    pam = client.post(PAM_BASE, headers={"X-CompliVibe-Key": shared}, json=_pam_payload("sik-flip-1"))
    assert pam.status_code == 401, pam.text

    cookies = client.post(COOKIE_SCAN, headers={"X-CompliVibe-Key": shared}, json=_cookie_payload())
    assert cookies.status_code == 401, cookies.text

    # Over-correction guard: the same key STILL authenticates its own subsystem (lineage).
    assert SubsystemIngestKeyService(db_session).resolve_org_by_key(shared, "lineage") == uuid.UUID(
        org["organization_id"]
    )


def test_each_subsystem_key_authenticates_only_its_own_subsystem(client, db_session):
    """A key minted for one subsystem does not authenticate another (the isolation)."""
    org = bootstrap_org_user(client, email_prefix="sik-iso")
    k_pam = _provision(client, org["org_headers"], "pam")
    k_cookies = _provision(client, org["org_headers"], "cookies")

    # PAM key works on PAM, not on cookies.
    assert client.post(PAM_BASE, headers={"X-CompliVibe-Key": k_pam}, json=_pam_payload("sik-iso-1")).status_code == 201
    assert client.post(COOKIE_SCAN, headers={"X-CompliVibe-Key": k_pam}, json=_cookie_payload()).status_code == 401

    # Cookies key works on cookies, not on PAM.
    assert client.post(COOKIE_SCAN, headers={"X-CompliVibe-Key": k_cookies}, json=_cookie_payload()).status_code == 201
    assert client.post(PAM_BASE, headers={"X-CompliVibe-Key": k_cookies}, json=_pam_payload("sik-iso-2")).status_code == 401


def test_service_resolution_is_key_type_scoped_and_org_isolated(client, db_session):
    """Service-level proof: resolve_org_by_key matches only the exact (key, key_type),
    and a key never resolves a different key_type or a different org's subsystem."""
    org_a = bootstrap_org_user(client, email_prefix="sik-svc-a")
    org_b = bootstrap_org_user(client, email_prefix="sik-svc-b")
    svc = SubsystemIngestKeyService(db_session)

    k_a_pam = svc.provision_key(uuid.UUID(org_a["organization_id"]), "pam", None)
    k_b_security = svc.provision_key(uuid.UUID(org_b["organization_id"]), "security", None)
    db_session.commit()

    assert svc.resolve_org_by_key(k_a_pam, "pam") == uuid.UUID(org_a["organization_id"])
    # same key, wrong subsystem -> no match
    assert svc.resolve_org_by_key(k_a_pam, "cookies") is None
    assert svc.resolve_org_by_key(k_a_pam, "security") is None
    # org B's security key does not authenticate as org A, and not as another type
    assert svc.resolve_org_by_key(k_b_security, "security") == uuid.UUID(org_b["organization_id"])
    assert svc.resolve_org_by_key(k_b_security, "pam") is None
    # unknown / empty
    assert svc.resolve_org_by_key("not-a-key", "pam") is None
    assert svc.resolve_org_by_key("", "pam") is None


def test_rotation_invalidates_the_previous_key(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sik-rot")
    first = _provision(client, org["org_headers"], "pam")
    assert client.post(PAM_BASE, headers={"X-CompliVibe-Key": first}, json=_pam_payload("sik-rot-1")).status_code == 201

    second = _provision(client, org["org_headers"], "pam")  # rotate in place
    assert second != first
    assert client.post(PAM_BASE, headers={"X-CompliVibe-Key": second}, json=_pam_payload("sik-rot-2")).status_code == 201
    # old key no longer works
    assert client.post(PAM_BASE, headers={"X-CompliVibe-Key": first}, json=_pam_payload("sik-rot-3")).status_code == 401
