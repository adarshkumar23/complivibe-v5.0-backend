"""Coverage for the evidence-packages endpoints
(/compliance/evidence-packages). Zero prior test references.

Covers create/list/get happy path (asserting real fields), audit:write
permission enforcement, and edge cases (404 for a missing engagement,
422 when assembling an empty package, org-scoping isolation).
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

ENGAGEMENTS = "/api/v1/compliance/audit-engagements"
PACKAGES = "/api/v1/compliance/evidence-packages"


def _create_engagement(client, headers) -> str:
    r = client.post(
        ENGAGEMENTS,
        headers=headers,
        json={
            "title": "External cert engagement",
            "audit_type": "external_certification",
            "start_date": "2027-01-01",
            "end_date": "2027-06-01",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_package(client, headers, engagement_id, title="Q1 evidence bundle") -> dict:
    r = client.post(
        f"{PACKAGES}?engagement_id={engagement_id}",
        headers=headers,
        json={"title": title},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_list_get_package_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ep-happy")
    h, oid = org["org_headers"], org["organization_id"]
    eid = _create_engagement(client, h)

    pkg = _create_package(client, h, eid)
    assert pkg["title"] == "Q1 evidence bundle"
    assert pkg["audit_engagement_id"] == eid
    assert pkg["organization_id"] == oid
    assert pkg["status"] == "draft"
    assert pkg["item_count"] == 0
    # cover sheet was built from the engagement at creation time
    assert pkg["cover_sheet_data"]["audit_title"] == "External cert engagement"
    # initial custody event is recorded
    assert len(pkg["chain_of_custody"]) >= 1
    pid = pkg["id"]

    # list (org-scoped) contains it
    listed = client.get(PACKAGES, headers=h)
    assert listed.status_code == 200, listed.text
    assert any(row["id"] == pid for row in listed.json())

    # list by engagement contains it
    by_eng = client.get(f"{PACKAGES}/engagement/{eid}", headers=h)
    assert by_eng.status_code == 200, by_eng.text
    assert any(row["id"] == pid for row in by_eng.json())

    # get single
    got = client.get(f"{PACKAGES}/{pid}", headers=h)
    assert got.status_code == 200, got.text
    assert got.json()["id"] == pid

    # completeness report is reachable with no controls in scope
    comp = client.get(f"{PACKAGES}/{pid}/completeness", headers=h)
    assert comp.status_code == 200, comp.text
    assert comp.json()["package_id"] == pid


def test_create_package_requires_audit_write(client, db_session):
    # auditor role lacks audit:write -> 403 (permission enforcement).
    org = bootstrap_org_user(client, email_prefix="ep-perm")
    eid = _create_engagement(client, org["org_headers"])
    auditor = add_org_member(db_session, client, org["organization_id"], "ep-auditor@example.com", role_name="auditor")
    r = client.post(f"{PACKAGES}?engagement_id={eid}", headers=auditor, json={"title": "nope"})
    assert r.status_code == 403, r.text


def test_create_package_missing_engagement_404(client, db_session):
    # engagement_id points at a non-existent engagement -> 404 (edge case).
    org = bootstrap_org_user(client, email_prefix="ep-404")
    r = client.post(f"{PACKAGES}?engagement_id={uuid.uuid4()}", headers=org["org_headers"], json={"title": "x"})
    assert r.status_code == 404, r.text


def test_assemble_empty_package_rejected(client, db_session):
    # a draft package with zero items cannot be assembled -> 422 (edge case).
    org = bootstrap_org_user(client, email_prefix="ep-empty")
    h = org["org_headers"]
    eid = _create_engagement(client, h)
    pid = _create_package(client, h, eid)["id"]
    r = client.post(f"{PACKAGES}/{pid}/assemble", headers=h)
    assert r.status_code == 422, r.text


def test_packages_org_scoped(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="ep-a")
    eid = _create_engagement(client, org_a["org_headers"])
    pid = _create_package(client, org_a["org_headers"], eid)["id"]

    org_b = bootstrap_org_user(client, email_prefix="ep-b")
    listed_b = client.get(PACKAGES, headers=org_b["org_headers"])
    assert listed_b.status_code == 200
    assert all(row["id"] != pid for row in listed_b.json())
    got_b = client.get(f"{PACKAGES}/{pid}", headers=org_b["org_headers"])
    assert got_b.status_code == 404, got_b.text
