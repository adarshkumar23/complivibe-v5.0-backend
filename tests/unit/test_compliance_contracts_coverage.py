"""Coverage for the compliance-contracts registry endpoint
(GET /compliance/contracts). Zero prior test references.

Covers the happy-path registry shape (asserting real contract-group fields),
compliance_policies:read permission enforcement (a zero-permission persona
-> 403), and org-scoping (registry served identically per authenticated org).
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/compliance/contracts"


def _make_zero_permission_headers(db_session, client, organization_id: str, email: str) -> dict[str, str]:
    """Create a custom role with NO permissions and a member on it.

    Every seeded role (owner/admin/compliance_manager/auditor/readonly/reviewer)
    holds compliance_policies:read, so a bespoke empty role is the only way to
    exercise the 403 path on this endpoint.
    """
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


def test_contract_registry_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ct-happy")
    r = client.get(BASE, headers=org["org_headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    groups = body["contract_groups"]

    # Known groups present with the documented shape.
    assert "compliance_policies" in groups
    assert "vendors" in groups
    policies = groups["compliance_policies"]
    assert {"method": "POST", "path": "/api/v1/compliance/policies"} in policies["endpoints"]
    assert "organization_id" in policies["protected_response_fields"]
    assert policies["invariants"] == ["tenant_scoped", "soft_delete", "audit_logged"]

    # The read-only dashboard group carries its distinct invariants.
    assert groups["compliance_dashboard"]["invariants"] == ["tenant_scoped", "read_only", "no_audit_write"]


def test_contract_registry_requires_compliance_policies_read(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ct-perm")
    no_perms = _make_zero_permission_headers(db_session, client, org["organization_id"], "ct-noperm@example.com")
    r = client.get(BASE, headers=no_perms)
    assert r.status_code == 403, r.text


def test_contract_registry_served_per_org(client, db_session):
    # Endpoint is tenant-authenticated; a second, independent org gets the same
    # (static) registry payload -- no cross-org leakage of anything org-specific.
    org_a = bootstrap_org_user(client, email_prefix="ct-a")
    org_b = bootstrap_org_user(client, email_prefix="ct-b")
    ra = client.get(BASE, headers=org_a["org_headers"])
    rb = client.get(BASE, headers=org_b["org_headers"])
    assert ra.status_code == 200 and rb.status_code == 200
    assert ra.json() == rb.json()
