from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.aml_kyc_check import AmlKycCheck
from app.models.audit_log import AuditLog
from app.models.sanctions_entity import SanctionsEntity
from app.models.sanctions_screen_result import SanctionsScreenResult
from app.models.vendor_external_rating import VendorExternalRating
from app.models.vendor_threat_intelligence import VendorThreatIntelligence
from app.satellites.tprm_intelligence.kyb_verification import KYBVerificationService
from app.satellites.tprm_intelligence.sanctions_screening import SanctionsScreeningService, WatchmanSearchResult
from app.satellites.tprm_intelligence.threat_intelligence import ThreatIntelligenceService
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


def test_t1_2_vendor_threat_intelligence_persists_skips_and_audits(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="t1-threat")
    vendor = _create_vendor(client, org, website="https://example.org")

    def fake_compute(self, domain: str) -> dict:
        assert domain == "example.org"
        return {
            "domain": domain,
            "threat_score": 25.0,
            "signals_used": {
                "alienvault_otx": {"status": "skipped", "source": "alienvault_otx", "score": None, "message": "OTX signal skipped: no API key configured"},
                "abuseipdb": {"status": "skipped", "source": "abuseipdb", "score": None, "message": "AbuseIPDB signal skipped: API key not configured"},
                "gdelt_threat_media": {"status": "available", "source": "gdelt", "score": 25, "article_count": 2, "articles": []},
            },
            "indicators_found": {"threat_media": []},
        }

    monkeypatch.setattr(ThreatIntelligenceService, "compute", fake_compute)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/threat-intelligence/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["domain"] == "example.org"
    assert body["threat_score"] == 25.0
    assert body["signals_used"]["alienvault_otx"]["status"] == "skipped"

    latest = client.get(f"{SATELLITE_BASE}/{vendor['id']}/threat-intelligence", headers=org["org_headers"])
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]

    row = db_session.execute(
        select(VendorThreatIntelligence).where(VendorThreatIntelligence.vendor_id == UUID(vendor["id"]))
    ).scalar_one_or_none()
    assert row is not None
    assert row.indicators_found == {"threat_media": []}

    audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "vendor.threat_intelligence.computed")
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.organization_id == UUID(org["organization_id"])


def test_t4_5_vendor_kyb_check_persists_skips_and_audits(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="t4-kyb")
    vendor = _create_vendor(client, org, name="Apple Inc", website="https://apple.com")

    def fake_compute(self, company_name: str) -> dict:
        assert company_name == "Apple Inc"
        return {
            "company_name": company_name,
            "signals_used": {
                "opencorporates": {
                    "status": "skipped",
                    "source": "opencorporates",
                    "message": "OpenCorporates signal skipped: API key not configured",
                },
                "gleif": {"status": "available", "source": "gleif", "match_count": 1, "records": [{"lei": "HWUPKR0MPOU8FGXBT394"}]},
                "icij_offshore_leaks": {"status": "available", "source": "icij_offshore_leaks", "match_count": 0, "results": []},
                "openownership": {
                    "status": "available",
                    "source": "openownership",
                    "coverage_limitation": "Public register coverage is limited.",
                    "statement_count": 0,
                    "statements": [],
                },
                "gdelt_adverse_media": {"status": "available", "source": "gdelt", "article_count": 1, "articles": []},
            },
            "offshore_links_found": {"source": "icij_offshore_leaks", "found": False, "matches": [], "status": "available"},
            "ubo_data": {
                "source": "openownership",
                "status": "available",
                "coverage_limitation": "Public register coverage is limited.",
                "statements": [],
            },
            "adverse_media_found": True,
        }

    monkeypatch.setattr(KYBVerificationService, "compute", fake_compute)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["company_name"] == "Apple Inc"
    assert body["signals_used"]["opencorporates"]["status"] == "skipped"
    assert body["signals_used"]["gleif"]["records"][0]["lei"] == "HWUPKR0MPOU8FGXBT394"
    assert body["adverse_media_found"] is True

    latest = client.get(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check", headers=org["org_headers"])
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]

    row = db_session.execute(select(AmlKycCheck).where(AmlKycCheck.vendor_id == UUID(vendor["id"]))).scalar_one_or_none()
    assert row is not None
    assert row.ubo_data["source"] == "openownership"

    audit = db_session.execute(select(AuditLog).where(AuditLog.action == "vendor.kyb_check.computed")).scalar_one_or_none()
    assert audit is not None
    assert audit.organization_id == UUID(org["organization_id"])


def _seed_sberbank_entity(db_session):
    row = SanctionsEntity(
        id="NK-SBERBANK-EUROPE-AG",
        caption="Sberbank Europe AG",
        schema_type="Company",
        countries=["at"],
        datasets=["us_ofac_sdn", "eu_fsf"],
        properties={
            "target": True,
            "topics": ["sanction"],
            "name": ["Sberbank Europe AG"],
            "sourceUrl": ["https://data.opensanctions.org/datasets/latest/default/entities.ftm.json"],
        },
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_t4_6_vendor_sanctions_screen_local_dataset_match_clear_and_audit(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="t4-sanctions")
    vendor = _create_vendor(client, org, name="Sberbank Europe AG", website="https://sberbank.example")
    _seed_sberbank_entity(db_session)

    def unavailable_watchman(self, name: str, *, limit: int = 10) -> WatchmanSearchResult:
        assert name == "Sberbank Europe AG"
        return WatchmanSearchResult(available=False, matches=[], error="docker unavailable in test")

    monkeypatch.setattr(SanctionsScreeningService, "_watchman_search", unavailable_watchman)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["match_found"] is True
    assert body["match_details"]["source"] == "local_opensanctions"
    assert body["match_details"]["matches"][0]["caption"] == "Sberbank Europe AG"
    assert body["match_details"]["matches"][0]["score"] == 1.0

    latest = client.get(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen", headers=org["org_headers"])
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]

    row = db_session.execute(
        select(SanctionsScreenResult).where(SanctionsScreenResult.vendor_id == UUID(vendor["id"]))
    ).scalar_one_or_none()
    assert row is not None
    assert row.match_found is True
    assert row.match_details["matches"][0]["datasets"] == ["us_ofac_sdn", "eu_fsf"]

    compute_audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "vendor.sanctions_screen.computed")
    ).scalar_one_or_none()
    assert compute_audit is not None
    assert compute_audit.organization_id == UUID(org["organization_id"])

    cleared = client.post(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen/{body['id']}/clear", headers=org["org_headers"])
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["cleared_by"] == org["user_id"]
    assert cleared.json()["cleared_at"] is not None

    clear_audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "vendor.sanctions_screen.cleared")
    ).scalar_one_or_none()
    assert clear_audit is not None
    assert clear_audit.organization_id == UUID(org["organization_id"])


def test_t4_6_vendor_sanctions_screen_unrelated_name_no_false_match(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="t4-sanctions-clean")
    vendor = _create_vendor(client, org, name="Blue Garden Bakery LLC", website="https://blue-garden.example")
    _seed_sberbank_entity(db_session)

    monkeypatch.setattr(
        SanctionsScreeningService,
        "_watchman_search",
        lambda self, name, *, limit=10: WatchmanSearchResult(available=False, matches=[], error="docker unavailable in test"),
    )
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["match_found"] is False
    assert body["top_score"] == 0.0
    assert body["match_details"]["matches"] == []


def test_t4_6_vendor_sanctions_screen_cross_org_blocked(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="t4-sanctions-a")
    org_b = bootstrap_org_user(client, email_prefix="t4-sanctions-b")
    vendor = _create_vendor(client, org_a, name="Sberbank Europe AG")
    _seed_sberbank_entity(db_session)

    blocked = client.post(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen/compute", headers=org_b["org_headers"])
    assert blocked.status_code == 404


def test_t4_6_organization_sanctions_threshold_is_configurable_and_audited(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t4-sanctions-threshold")

    updated = client.patch(
        f"/api/v1/organizations/{org['organization_id']}",
        headers=org["org_headers"],
        json={"sanctions_match_threshold": 0.92},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["organization"]["sanctions_match_threshold"] == 0.92

    audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "organization.updated")
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.after_json["sanctions_match_threshold"] == 0.92
