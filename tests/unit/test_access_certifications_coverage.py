"""Additional HTTP-layer coverage for the access-certifications router
(/api/v1/access-certifications).

The existing single test (test_access_certifications_t43.py) proves the campaign
CRUD+archive happy path, the my-certifications/decision/complete flow, and audit
emission. This file adds genuinely NEW coverage: recertification:read /
recertification:write permission enforcement (a role that lacks each -> 403, plus
a non-owner authorized persona -> 2xx), 404 not-found, cross-org isolation, 422
payload validation, the "reviewer/user must be an active member" business rule
(400), and the invalid-state-transition rule that an archived campaign is not open
for decisions (400).

Endpoints covered: GET/POST /campaigns, GET /campaigns/{id},
POST /items/{id}/decision.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/access-certifications"


# --- permission enforcement -------------------------------------------------


def test_list_campaigns_requires_recertification_read(client, db_session):
    # readonly is the one seeded role that lacks recertification:read.
    org = bootstrap_org_user(client, email_prefix="ac-read-perm")
    ro = add_org_member(db_session, client, org["organization_id"], "ac-ro@example.com", role_name="readonly")
    r = client.get(f"{BASE}/campaigns", headers=ro)
    assert r.status_code == 403, r.text


def test_create_campaign_requires_recertification_write(client, db_session):
    # auditor holds recertification:read but NOT recertification:write.
    org = bootstrap_org_user(client, email_prefix="ac-write-perm")
    auditor = add_org_member(db_session, client, org["organization_id"], "ac-auditor@example.com", role_name="auditor")
    r = client.post(f"{BASE}/campaigns", headers=auditor, json={"name": "Blocked campaign"})
    assert r.status_code == 403, r.text


def test_compliance_manager_can_create_and_list_campaigns(client, db_session):
    # Non-owner authorized persona: compliance_manager holds both recert perms.
    org = bootstrap_org_user(client, email_prefix="ac-cm")
    cm = add_org_member(db_session, client, org["organization_id"], "ac-cm@example.com", role_name="compliance_manager")

    created = client.post(f"{BASE}/campaigns", headers=cm, json={"name": "CM quarterly review"})
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    assert created.json()["status"] == "draft"
    assert created.json()["total_items"] == 0

    listed = client.get(f"{BASE}/campaigns", headers=cm)
    assert listed.status_code == 200
    assert campaign_id in [row["id"] for row in listed.json()]


# --- not-found / org-scoping ------------------------------------------------


def test_get_campaign_not_found_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ac-404")
    r = client.get(f"{BASE}/campaigns/{uuid.uuid4()}", headers=org["org_headers"])
    assert r.status_code == 404, r.text


def test_campaign_is_isolated_across_orgs(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="ac-iso-a")
    created = client.post(f"{BASE}/campaigns", headers=org_a["org_headers"], json={"name": "Org A campaign"})
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]

    org_b = bootstrap_org_user(client, email_prefix="ac-iso-b")
    # Org B cannot read org A's campaign (tenant-scoped get -> 404, not 200/403).
    leaked = client.get(f"{BASE}/campaigns/{campaign_id}", headers=org_b["org_headers"])
    assert leaked.status_code == 404, leaked.text
    # ...and it does not appear in org B's listing.
    listed_b = client.get(f"{BASE}/campaigns", headers=org_b["org_headers"])
    assert listed_b.status_code == 200
    assert campaign_id not in [row["id"] for row in listed_b.json()]


# --- payload validation -----------------------------------------------------


def test_create_campaign_rejects_short_name(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ac-422")
    r = client.post(f"{BASE}/campaigns", headers=org["org_headers"], json={"name": "ab"})
    assert r.status_code == 422, r.text


# --- domain business rules --------------------------------------------------


def test_create_campaign_rejects_item_for_non_member(client, db_session):
    # An item whose user_id is not an active org member is rejected with 400.
    org = bootstrap_org_user(client, email_prefix="ac-nonmember")
    r = client.post(
        f"{BASE}/campaigns",
        headers=org["org_headers"],
        json={
            "name": "Campaign with stranger",
            "status": "active",
            "items": [
                {
                    "user_id": str(uuid.uuid4()),
                    "reviewer_user_id": org["user_id"],
                    "system_key": "okta",
                    "system_name": "Okta",
                    "access_level": "admin",
                }
            ],
        },
    )
    assert r.status_code == 400, r.text
    assert "active member" in r.json()["detail"]


def test_decision_rejected_on_archived_campaign(client, db_session):
    # Invalid state transition: once a campaign is archived, its items are not
    # open for decisions (400) -- and this rule fires before the reviewer check,
    # so an owner with recertification:write still cannot decide.
    org = bootstrap_org_user(client, email_prefix="ac-archived")
    reviewer = add_org_member(db_session, client, org["organization_id"], "ac-rev@example.com", role_name="compliance_manager")

    created = client.post(
        f"{BASE}/campaigns",
        headers=org["org_headers"],
        json={
            "name": "Soon-archived campaign",
            "status": "active",
            "items": [
                {
                    "user_id": org["user_id"],
                    "reviewer_user_id": org["user_id"],
                    "system_key": "github",
                    "system_name": "GitHub",
                    "access_level": "admin",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    item_id = created.json()["items"][0]["id"]

    archived = client.delete(f"{BASE}/campaigns/{campaign_id}", headers=org["org_headers"])
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    blocked = client.post(
        f"{BASE}/items/{item_id}/decision",
        headers=org["org_headers"],
        json={"decision": "certified"},
    )
    assert blocked.status_code == 400, blocked.text
    assert "not open for decisions" in blocked.json()["detail"]
    # reviewer var kept to document that even the assigned reviewer would be blocked
    assert reviewer  # sanity: member created
