from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.models.compliance_certification import ComplianceCertification
from app.models.compliance_policy import CompliancePolicy
from app.models.trust_center_access_request import TrustCenterAccessRequest
from tests.helpers.auth_org import bootstrap_org_user


def _enable_trust_center(client, org, **overrides):
    payload = {
        "is_enabled": True,
        "display_name": "Acme Trust Center",
        "show_certifications": True,
        "show_framework_coverage": False,
        "show_published_policies": True,
        "show_uptime_status": False,
        "request_access_enabled": True,
    }
    payload.update(overrides)
    resp = client.post("/api/v1/compliance/trust-center/configuration", headers=org["org_headers"], json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _org_slug(client, org) -> str:
    orgs = client.get("/api/v1/organizations/me", headers=org["headers"])
    assert orgs.status_code == 200
    return orgs.json()[0]["slug"]


def test_public_trust_center_excludes_expired_certifications(client, db_session):
    org = bootstrap_org_user(client, email_prefix="trust-cert-expiry")
    _enable_trust_center(client, org)
    slug = _org_slug(client, org)

    org_id = UUID(org["organization_id"])
    db_session.add_all(
        [
            ComplianceCertification(
                organization_id=org_id,
                name="SOC 2 Type II",
                certification_type="soc2",
                status="active",
                valid_until=date.today() + timedelta(days=100),
            ),
            ComplianceCertification(
                organization_id=org_id,
                name="ISO 27001 (stale)",
                certification_type="iso27001",
                status="active",
                valid_until=date.today() - timedelta(days=5),
            ),
        ]
    )
    db_session.commit()

    resp = client.get(f"/api/v1/trust-center/{slug}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = {row["name"] for row in body["certifications"]}
    assert "SOC 2 Type II" in names
    assert "ISO 27001 (stale)" not in names
    assert body["expired_certifications_excluded"] == 1
    assert body["data_generated_at"]


def test_publish_policy_rejects_draft_status(client, db_session):
    """G9 item 4: a draft (unapproved) policy must never be publishable to the trust center."""
    org = bootstrap_org_user(client, email_prefix="trust-policy-draft")
    _enable_trust_center(client, org)

    org_id = UUID(org["organization_id"])
    user_id = UUID(org["user_id"])
    policy = CompliancePolicy(
        organization_id=org_id,
        title="Unapproved Draft Policy",
        policy_type="security",
        status="draft",
        owner_user_id=user_id,
    )
    db_session.add(policy)
    db_session.commit()

    publish = client.post(
        "/api/v1/compliance/trust-center/publish-policy",
        headers=org["org_headers"],
        json={"policy_id": str(policy.id), "summary": "Should not be allowed"},
    )
    assert publish.status_code == 400, publish.text
    assert "approved" in publish.json()["detail"].lower()

    listing = client.get("/api/v1/compliance/trust-center/policies", headers=org["org_headers"])
    assert listing.status_code == 200
    assert listing.json() == []


def test_admin_published_policies_listing_flags_staleness_and_archival(client, db_session):
    org = bootstrap_org_user(client, email_prefix="trust-policy-stale")
    _enable_trust_center(client, org)

    org_id = UUID(org["organization_id"])
    user_id = UUID(org["user_id"])
    policy = CompliancePolicy(
        organization_id=org_id,
        title="Information Security Policy",
        policy_type="security",
        status="approved",
        owner_user_id=user_id,
    )
    db_session.add(policy)
    db_session.commit()

    publish = client.post(
        "/api/v1/compliance/trust-center/publish-policy",
        headers=org["org_headers"],
        json={"policy_id": str(policy.id), "summary": "Initial summary"},
    )
    assert publish.status_code == 200, publish.text

    listing_before = client.get("/api/v1/compliance/trust-center/policies", headers=org["org_headers"])
    assert listing_before.status_code == 200, listing_before.text
    row_before = listing_before.json()[0]
    assert row_before["policy_updated_since_published"] is False
    assert row_before["policy_archived"] is False

    # Postgres func.now() resolves to the enclosing transaction's start time, which is
    # shared across this whole test under the test harness's transactional isolation.
    # Backdate published_at explicitly to simulate a real elapsed-time gap between
    # publish and the later policy revision.
    from app.models.trust_center_published_policy import TrustCenterPublishedPolicy

    published_row = db_session.execute(
        select(TrustCenterPublishedPolicy).where(TrustCenterPublishedPolicy.policy_id == policy.id)
    ).scalar_one()
    published_row.published_at = datetime.now(UTC) - timedelta(days=2)
    db_session.commit()

    # Simulate the underlying policy being revised after publication.
    policy.title = "Information Security Policy v2"
    policy.updated_at = datetime.now(UTC)
    db_session.commit()

    listing_after = client.get("/api/v1/compliance/trust-center/policies", headers=org["org_headers"])
    assert listing_after.status_code == 200, listing_after.text
    row_after = listing_after.json()[0]
    assert row_after["policy_updated_since_published"] is True
    assert row_after["policy_title"] == "Information Security Policy v2"


def test_trust_center_access_request_deduplicates_pending_and_auto_expires(client, db_session):
    org = bootstrap_org_user(client, email_prefix="trust-access-dup")
    _enable_trust_center(client, org)
    slug = _org_slug(client, org)

    first = client.post(
        f"/api/v1/trust-center/{slug}/request-access",
        json={"requester_name": "Jane Auditor", "requester_email": "jane@auditor.example", "requester_company": "AuditCo"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["duplicate"] is False
    first_id = first.json()["request_id"]

    second = client.post(
        f"/api/v1/trust-center/{slug}/request-access",
        json={"requester_name": "Jane Auditor", "requester_email": "jane@auditor.example", "requester_company": "AuditCo"},
    )
    assert second.status_code == 201, second.text
    assert second.json()["duplicate"] is True
    assert second.json()["request_id"] == first_id

    rows = db_session.execute(
        select(TrustCenterAccessRequest).where(TrustCenterAccessRequest.requester_email == "jane@auditor.example")
    ).scalars().all()
    assert len(rows) == 1

    # Approve then force it into the past to exercise lazy auto-expiry.
    approve = client.post(
        f"/api/v1/compliance/trust-center/access-requests/{first_id}/review",
        headers=org["org_headers"],
        json={"action": "approve"},
    )
    assert approve.status_code == 200, approve.text

    row = db_session.get(TrustCenterAccessRequest, UUID(first_id))
    assert row is not None
    row.access_expires_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()

    listing = client.get("/api/v1/compliance/trust-center/access-requests", headers=org["org_headers"])
    assert listing.status_code == 200, listing.text
    matched = [item for item in listing.json() if item["id"] == first_id]
    assert matched
    assert matched[0]["status"] == "expired"
    assert matched[0]["access_token_hash"] is None
