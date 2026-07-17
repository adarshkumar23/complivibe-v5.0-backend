"""Additional coverage for the OSCAL export router (/api/v1/compliance/oscal).
Complements test_oscal_export_a23.py.

The existing a23 suite exercises the export builders, validate/download semantics,
tenant isolation, and audit events -- all as the org owner. This file adds the
untouched surface:
  * reports:read permission enforcement (a bespoke zero-permission role -> 403;
    a non-owner role that DOES hold reports:read -> authorized 2xx),
  * schema-level rejection of an unknown export_type (422),
  * GET detail for a nonexistent / cross-org job -> 404,
  * OSCAL output correctness beyond a 200: NIST metadata block (oscal-version
    1.1.2, document version, title) and the validate endpoint confirming the
    emitted SSP is structurally well-formed,
  * list-export query filtering by status and export_type.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/compliance/oscal"


def _zero_permission_headers(db_session, client, organization_id: str, email: str) -> dict[str, str]:
    """Create a custom role with NO permissions and a member on it.

    Every seeded role (owner/admin/compliance_manager/auditor/readonly/reviewer)
    holds reports:read, so a bespoke empty role is the only way to exercise the
    403 path on the OSCAL endpoints.
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


def test_export_requires_reports_read(client, db_session):
    org = bootstrap_org_user(client, email_prefix="osc-perm")
    no_perms = _zero_permission_headers(db_session, client, org["organization_id"], "osc-noperm@example.com")

    denied = client.post(f"{BASE}/export", headers=no_perms, json={"export_type": "ssp"})
    assert denied.status_code == 403, denied.text

    denied_summary = client.get(f"{BASE}/summary", headers=no_perms)
    assert denied_summary.status_code == 403, denied_summary.text

    denied_list = client.get(f"{BASE}/exports", headers=no_perms)
    assert denied_list.status_code == 403, denied_list.text


def test_non_owner_role_with_reports_read_is_authorized(client, db_session):
    """readonly holds reports:read, so a non-owner member can build an export."""
    org = bootstrap_org_user(client, email_prefix="osc-ro")
    reader = add_org_member(db_session, client, org["organization_id"], "osc-reader@example.com", role_name="readonly")

    r = client.post(f"{BASE}/export", headers=reader, json={"export_type": "ssp"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "complete"


def test_unknown_export_type_rejected_by_schema(client, db_session):
    org = bootstrap_org_user(client, email_prefix="osc-badtype")
    r = client.post(f"{BASE}/export", headers=org["org_headers"], json={"export_type": "nist_csf"})
    assert r.status_code == 422, r.text


def test_get_detail_nonexistent_and_cross_org_404(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="osc-detail-a")
    org_b = bootstrap_org_user(client, email_prefix="osc-detail-b")

    # nonexistent id in caller's own org
    missing = client.get(f"{BASE}/exports/{uuid.uuid4()}", headers=org_a["org_headers"])
    assert missing.status_code == 404, missing.text

    # a real job in org A is invisible to org B
    created = client.post(f"{BASE}/export", headers=org_a["org_headers"], json={"export_type": "ssp"})
    assert created.status_code == 200, created.text
    job_id = created.json()["id"]

    seen = client.get(f"{BASE}/exports/{job_id}", headers=org_a["org_headers"])
    assert seen.status_code == 200
    assert seen.json()["id"] == job_id

    cross = client.get(f"{BASE}/exports/{job_id}", headers=org_b["org_headers"])
    assert cross.status_code == 404, cross.text
    cross_dl = client.get(f"{BASE}/exports/{job_id}/download", headers=org_b["org_headers"])
    assert cross_dl.status_code == 404, cross_dl.text
    cross_val = client.get(f"{BASE}/exports/{job_id}/validate", headers=org_b["org_headers"])
    assert cross_val.status_code == 404, cross_val.text


def test_ssp_document_oscal_correctness_and_validate(client, db_session):
    """Beyond a 200: assert the emitted SSP carries a conformant NIST OSCAL
    metadata block and that the router's own validator confirms structural
    correctness."""
    org = bootstrap_org_user(client, email_prefix="osc-correct")

    created = client.post(f"{BASE}/export", headers=org["org_headers"], json={"export_type": "ssp"})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["oscal_version"] == "1.1.2"

    ssp = body["result_json"]["system-security-plan"]

    # Top-level OSCAL object identity is a v4 UUID.
    assert uuid.UUID(ssp["uuid"]).version == 4

    # NIST OSCAL metadata block.
    metadata = ssp["metadata"]
    assert metadata["oscal-version"] == "1.1.2"
    assert metadata["version"] == "1.0.0"
    assert "last-modified" in metadata
    assert metadata["title"].endswith("All Frameworks SSP")

    # Structural anchors required by an SSP.
    assert "system-characteristics" in ssp
    assert "control-implementation" in ssp

    # The router's validate endpoint agrees the document is well-formed.
    valid = client.get(f"{BASE}/exports/{body['id']}/validate", headers=org["org_headers"])
    assert valid.status_code == 200, valid.text
    vbody = valid.json()
    assert vbody["valid"] is True
    assert vbody["errors"] == []
    assert vbody["oscal_version"] == "1.1.2"
    assert vbody["export_type"] == "ssp"


def test_list_exports_filter_by_status_and_type(client, db_session):
    org = bootstrap_org_user(client, email_prefix="osc-filter")
    h = org["org_headers"]

    ssp = client.post(f"{BASE}/export", headers=h, json={"export_type": "ssp"})
    ap = client.post(f"{BASE}/export", headers=h, json={"export_type": "assessment_plan"})
    assert ssp.status_code == 200 and ap.status_code == 200

    # filter by export_type
    only_ssp = client.get(f"{BASE}/exports?export_type=ssp", headers=h)
    assert only_ssp.status_code == 200
    types = {row["export_type"] for row in only_ssp.json()}
    assert types == {"ssp"}

    # filter by status: both built jobs complete
    complete = client.get(f"{BASE}/exports?status=complete", headers=h)
    assert complete.status_code == 200
    assert len(complete.json()) >= 2
    assert all(row["status"] == "complete" for row in complete.json())

    # a status with no matching jobs yields an empty list
    failed = client.get(f"{BASE}/exports?status=failed", headers=h)
    assert failed.status_code == 200
    assert failed.json() == []
