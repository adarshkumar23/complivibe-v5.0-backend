"""Coverage for the customer-commitments endpoints
(/compliance/customer-commitments). Zero prior test references.

Covers create/list/get happy path (asserting real fields), vendor:write
permission enforcement (readonly -> 403), and a 404 not-found edge case plus
org-scoping isolation.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/compliance/customer-commitments"


def _commitment_body(assigned_owner_id: str, **over) -> dict:
    body = {
        "customer_name": "Acme Corp",
        "customer_email": "dpo@acme.example.com",
        "commitment_type": "breach_notification",
        "title": "72h breach notification",
        "description": "Notify Acme within 72h of a confirmed personal-data breach.",
        "trigger_condition": "Confirmed personal data breach affecting Acme records",
        "triggering_incident_type": "data_breach",
        "notification_days_before": 7,
        "sla_hours": 72,
        "assigned_owner_id": assigned_owner_id,
    }
    body.update(over)
    return body


def test_create_list_get_commitment_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cc-happy")
    h, uid = org["org_headers"], org["user_id"]

    created = client.post(BASE, headers=h, json=_commitment_body(uid))
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["customer_name"] == "Acme Corp"
    assert row["commitment_type"] == "breach_notification"
    assert row["title"] == "72h breach notification"
    assert row["sla_hours"] == 72
    assert row["status"] == "active"
    assert row["assigned_owner_id"] == uid
    assert row["created_by"] == uid
    assert row["organization_id"] == org["organization_id"]
    commitment_id = row["id"]

    listed = client.get(BASE, headers=h)
    assert listed.status_code == 200, listed.text
    assert any(r["id"] == commitment_id for r in listed.json())

    fetched = client.get(f"{BASE}/{commitment_id}", headers=h)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == commitment_id
    assert fetched.json()["title"] == "72h breach notification"


def test_create_commitment_requires_vendor_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cc-perm")
    # readonly has vendor:read but lacks vendor:write -> 403 on create.
    ro = add_org_member(db_session, client, org["organization_id"], "cc-readonly@example.com", role_name="readonly")
    r = client.post(BASE, headers=ro, json=_commitment_body(org["user_id"]))
    assert r.status_code == 403, r.text


def test_get_commitment_not_found(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cc-404")
    r = client.get(f"{BASE}/{uuid.uuid4()}", headers=org["org_headers"])
    assert r.status_code == 404, r.text


def test_commitments_org_scoped(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="cc-a")
    created = client.post(BASE, headers=org_a["org_headers"], json=_commitment_body(org_a["user_id"]))
    assert created.status_code == 201, created.text
    commitment_id = created.json()["id"]

    org_b = bootstrap_org_user(client, email_prefix="cc-b")
    # org B cannot list org A's commitment...
    listed_b = client.get(BASE, headers=org_b["org_headers"])
    assert listed_b.status_code == 200
    assert all(r["id"] != commitment_id for r in listed_b.json())
    # ...nor fetch it directly (404, not 200).
    fetched_b = client.get(f"{BASE}/{commitment_id}", headers=org_b["org_headers"])
    assert fetched_b.status_code == 404, fetched_b.text
