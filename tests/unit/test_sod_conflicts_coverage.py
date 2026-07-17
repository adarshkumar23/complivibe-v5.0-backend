"""HTTP-layer coverage for the segregation-of-duties conflicts router
(/api/v1/sod-conflicts).

The existing single test (test_sod_conflicts_t44.py) drives SodConflictService
directly (detection/dedup, no-finding-without-pair-perm, soft-deactivate + audit)
and never exercises the router, its permissions, or its error paths. This file
adds genuinely NEW coverage over HTTP: sod:manage / sod:read permission
enforcement (readonly lacks manage -> 403; a bespoke zero-permission role -> 403
on the read path since EVERY seeded role holds sod:read; compliance_manager as an
authorized non-owner persona -> 201), 404 not-found, cross-org isolation, the
409 duplicate-active-rule conflict, 422 validation (identical / unknown permission
codes), and the finding lifecycle (detect -> acknowledge -> waive) plus the
invalid transition that a waived finding cannot be acknowledged (409).

Endpoints covered: POST/GET /rules, GET/PATCH/DELETE /rules/{id},
GET /findings, POST /findings/{id}/acknowledge, POST /findings/{id}/waive,
POST /users/{id}/detect.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/sod-conflicts"
# Two real, seeded permission keys that a role can genuinely hold together.
PERM_A = "users:read"
PERM_B = "users:update_role"


def _rule_body(**over):
    body = {"permission_a": PERM_A, "permission_b": PERM_B, "severity": "high"}
    body.update(over)
    return body


def _make_zero_permission_headers(db_session, client, organization_id: str, email: str) -> dict[str, str]:
    """Every seeded role (owner/admin/compliance_manager/auditor/readonly/reviewer)
    holds sod:read, so a bespoke empty role is the only way to exercise the 403
    path on the read endpoints."""
    from app.models.role import Role

    role = Role(
        organization_id=uuid.UUID(organization_id),
        name=f"zero-perms-{uuid.uuid4().hex[:8]}",
        description="no permissions",
        is_system=False,
        is_system_role=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.commit()
    return add_org_member(db_session, client, organization_id, email, role_name=role.name)


# --- happy path -------------------------------------------------------------


def test_rule_lifecycle_over_http(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sod-life")
    h = org["org_headers"]

    created = client.post(f"{BASE}/rules", headers=h, json=_rule_body(description="admin cannot self-grant"))
    assert created.status_code == 201, created.text
    rule = created.json()
    rule_id = rule["id"]
    # canonical ordering: permissions stored sorted.
    assert [rule["permission_a"], rule["permission_b"]] == sorted([PERM_A, PERM_B])
    assert rule["severity"] == "high" and rule["active"] is True and rule["status"] == "active"

    listed = client.get(f"{BASE}/rules", headers=h)
    assert listed.status_code == 200
    assert rule_id in [row["id"] for row in listed.json()]

    got = client.get(f"{BASE}/rules/{rule_id}", headers=h)
    assert got.status_code == 200
    assert got.json()["id"] == rule_id

    patched = client.patch(f"{BASE}/rules/{rule_id}", headers=h, json={"severity": "critical"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["severity"] == "critical"

    deactivated = client.delete(f"{BASE}/rules/{rule_id}", headers=h)
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["active"] is False and deactivated.json()["status"] == "inactive"
    # deactivated rules are hidden from the default listing.
    assert rule_id not in [row["id"] for row in client.get(f"{BASE}/rules", headers=h).json()]


# --- permission enforcement -------------------------------------------------


def test_create_rule_requires_sod_manage(client, db_session):
    # readonly holds sod:read but not sod:manage.
    org = bootstrap_org_user(client, email_prefix="sod-manage-perm")
    ro = add_org_member(db_session, client, org["organization_id"], "sod-ro@example.com", role_name="readonly")
    r = client.post(f"{BASE}/rules", headers=ro, json=_rule_body())
    assert r.status_code == 403, r.text


def test_list_rules_requires_sod_read(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sod-read-perm")
    no_perms = _make_zero_permission_headers(db_session, client, org["organization_id"], "sod-noperm@example.com")
    r = client.get(f"{BASE}/rules", headers=no_perms)
    assert r.status_code == 403, r.text


def test_compliance_manager_can_create_rule(client, db_session):
    # Non-owner authorized persona: compliance_manager holds sod:manage.
    org = bootstrap_org_user(client, email_prefix="sod-cm")
    cm = add_org_member(db_session, client, org["organization_id"], "sod-cm@example.com", role_name="compliance_manager")
    r = client.post(f"{BASE}/rules", headers=cm, json=_rule_body())
    assert r.status_code == 201, r.text


# --- not-found / org-scoping ------------------------------------------------


def test_get_rule_not_found_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sod-404")
    r = client.get(f"{BASE}/rules/{uuid.uuid4()}", headers=org["org_headers"])
    assert r.status_code == 404, r.text


def test_rules_isolated_across_orgs(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="sod-iso-a")
    created = client.post(f"{BASE}/rules", headers=org_a["org_headers"], json=_rule_body())
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    org_b = bootstrap_org_user(client, email_prefix="sod-iso-b")
    # Not visible in org B's listing...
    listed_b = client.get(f"{BASE}/rules", headers=org_b["org_headers"])
    assert listed_b.status_code == 200
    assert rule_id not in [row["id"] for row in listed_b.json()]
    # ...and not directly fetchable by org B.
    leaked = client.get(f"{BASE}/rules/{rule_id}", headers=org_b["org_headers"])
    assert leaked.status_code == 404, leaked.text


# --- validation / conflict rules --------------------------------------------


def test_create_rule_rejects_identical_permissions(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sod-same")
    r = client.post(f"{BASE}/rules", headers=org["org_headers"], json=_rule_body(permission_b=PERM_A))
    assert r.status_code == 422, r.text


def test_create_rule_rejects_unknown_permission(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sod-unknown")
    r = client.post(
        f"{BASE}/rules",
        headers=org["org_headers"],
        json=_rule_body(permission_b="totally:made_up_permission"),
    )
    assert r.status_code == 422, r.text


def test_duplicate_active_rule_returns_409(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sod-dup")
    h = org["org_headers"]
    first = client.post(f"{BASE}/rules", headers=h, json=_rule_body())
    assert first.status_code == 201, first.text
    # Same permission pair (even reversed) while the first is active -> conflict.
    dup = client.post(f"{BASE}/rules", headers=h, json=_rule_body(permission_a=PERM_B, permission_b=PERM_A))
    assert dup.status_code == 409, dup.text


# --- finding lifecycle over HTTP --------------------------------------------


def test_finding_detect_acknowledge_waive_lifecycle(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sod-find")
    h = org["org_headers"]
    owner_id = org["user_id"]

    created = client.post(f"{BASE}/rules", headers=h, json=_rule_body())
    assert created.status_code == 201, created.text

    # The owner holds both conflicting permissions -> detection yields a finding.
    detected = client.post(f"{BASE}/users/{owner_id}/detect", headers=h)
    assert detected.status_code == 200, detected.text
    finding_ids = detected.json()["created_finding_ids"]
    assert len(finding_ids) == 1
    assert {PERM_A, PERM_B}.issubset(set(detected.json()["permission_codes"]))
    finding_id = finding_ids[0]

    # Finding appears in the org listing as open.
    findings = client.get(f"{BASE}/findings", headers=h)
    assert findings.status_code == 200
    match = next(f for f in findings.json() if f["id"] == finding_id)
    assert match["status"] == "open"
    assert match["severity"] == "high"

    ack = client.post(f"{BASE}/findings/{finding_id}/acknowledge", headers=h, json={"note": "reviewing"})
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "acknowledged"

    waive = client.post(f"{BASE}/findings/{finding_id}/waive", headers=h, json={"note": "break-glass approved"})
    assert waive.status_code == 200, waive.text
    assert waive.json()["status"] == "waived"

    # Invalid transition: a waived finding cannot be re-acknowledged.
    reack = client.post(f"{BASE}/findings/{finding_id}/acknowledge", headers=h, json={"note": "oops"})
    assert reack.status_code == 409, reack.text


def test_acknowledge_finding_not_found_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="sod-find404")
    r = client.post(f"{BASE}/findings/{uuid.uuid4()}/acknowledge", headers=org["org_headers"], json={})
    assert r.status_code == 404, r.text
