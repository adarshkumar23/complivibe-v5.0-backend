from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.vendor_external_rating import VendorExternalRating
from app.satellites.tprm_intelligence.vendor_security_rating import VendorSecurityRatingService
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
SATELLITE_BASE = "/api/v1/vendors"


def _create_vendor(client, org: dict, *, name: str = "Example Vendor", website: str = "https://example.com") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=org["org_headers"],
        json={
            "name": name,
            "vendor_type": "software",
            "website": website,
            "owner_user_id": org["user_id"],
            "data_access": True,
            "processes_personal_data": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_t1_1_vendor_security_rating_persists_skips_and_audits(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="t1-rating")
    vendor = _create_vendor(client, org, website="https://example.com/security")

    def fake_compute(self, domain: str) -> dict:
        assert domain == "example.com"
        return {
            "domain": domain,
            "composite_score": 88.5,
            "signals_used": {
                "mozilla_observatory": {"status": "available", "source": "mozilla_observatory", "grade": "A", "score": 95},
                "gdelt_adverse_media": {"status": "available", "source": "gdelt", "score": 90, "article_count": 1},
                "abuseipdb": {"status": "skipped", "source": "abuseipdb", "score": None, "message": "AbuseIPDB signal skipped: API key not configured"},
                "hibp": {"status": "skipped", "source": "hibp", "score": None, "message": "HIBP signal skipped: no API key configured"},
            },
        }

    monkeypatch.setattr(VendorSecurityRatingService, "compute", fake_compute)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/security-rating/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["domain"] == "example.com"
    assert body["composite_score"] == 88.5
    assert body["signals_used"]["hibp"]["status"] == "skipped"

    latest = client.get(f"{SATELLITE_BASE}/{vendor['id']}/security-rating", headers=org["org_headers"])
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]

    row = db_session.execute(
        select(VendorExternalRating).where(VendorExternalRating.vendor_id == UUID(vendor["id"]))
    ).scalar_one_or_none()
    assert row is not None
    assert row.signals_used["mozilla_observatory"]["grade"] == "A"

    audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "vendor.security_rating.computed")
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.organization_id == UUID(org["organization_id"])


def test_t1_1_security_rating_cross_org_blocked(client, monkeypatch):
    org_a = bootstrap_org_user(client, email_prefix="t1-rating-a")
    org_b = bootstrap_org_user(client, email_prefix="t1-rating-b")
    vendor = _create_vendor(client, org_a)

    blocked = client.post(f"{SATELLITE_BASE}/{vendor['id']}/security-rating/compute", headers=org_b["org_headers"])
    assert blocked.status_code == 404
