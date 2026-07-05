from __future__ import annotations

import uuid
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


def test_t4_5_vendor_kyb_check_offshore_and_adverse_media_propagates_nth_party_alert(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="t4-kyb-alert")
    first_party = _create_vendor(client, org, name="Critical Payments Co", website="https://critical-pay.example")
    fourth_party = _create_vendor(client, org, name="Shell Holdings Ltd", website="https://shell-holdings.example")

    linked = client.post(
        f"{SATELLITE_BASE}/{first_party['id']}/supply-chain-links",
        headers=org["org_headers"],
        json={"sub_vendor_id": fourth_party["id"], "relationship_type": "cdn_dependency"},
    )
    assert linked.status_code == 201, linked.text

    def fake_compute(self, company_name: str) -> dict:
        return {
            "company_name": company_name,
            "signals_used": {"icij_offshore_leaks": {"status": "available", "match_count": 1, "results": [{"name": "match"}]}},
            "offshore_links_found": {"source": "icij_offshore_leaks", "found": True, "matches": [{"name": "match"}], "status": "available"},
            "ubo_data": {"source": "openownership", "status": "available", "coverage_limitation": "", "statements": []},
            "adverse_media_found": True,
        }

    monkeypatch.setattr(KYBVerificationService, "compute", fake_compute)
    computed = client.post(f"{SATELLITE_BASE}/{fourth_party['id']}/kyb-check/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text

    graph = client.get(f"{SATELLITE_BASE}/{first_party['id']}/supply-chain-graph?depth=5", headers=org["org_headers"])
    assert graph.status_code == 200
    alerts = graph.json()["open_alerts"]
    match = next((a for a in alerts if a["signal_type"] == "kyb_aml_risk_flagged"), None)
    assert match is not None, "expected kyb_aml_risk_flagged alert to propagate to first party vendor"
    assert match["severity"] == "critical"
    assert match["triggering_vendor_id"] == fourth_party["id"]

    audit_rows = db_session.execute(
        select(AuditLog).where(AuditLog.action == "vendor_supply_chain.alert_propagated")
    ).scalars().all()
    kyb_audit = [r for r in audit_rows if r.metadata_json.get("source") == "vendor.kyb_check.computed"]
    assert len(kyb_audit) >= 1
    assert kyb_audit[0].organization_id == UUID(org["organization_id"])


def test_t4_5_vendor_kyb_check_clean_result_does_not_propagate_alert(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="t4-kyb-clean")
    vendor = _create_vendor(client, org, name="Clean Co", website="https://clean.example")

    def fake_compute(self, company_name: str) -> dict:
        return {
            "company_name": company_name,
            "signals_used": {},
            "offshore_links_found": {"source": "icij_offshore_leaks", "found": False, "matches": [], "status": "available"},
            "ubo_data": {"source": "openownership", "status": "available", "coverage_limitation": "", "statements": []},
            "adverse_media_found": False,
        }

    monkeypatch.setattr(KYBVerificationService, "compute", fake_compute)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text

    audit_rows = db_session.execute(
        select(AuditLog).where(AuditLog.action == "vendor_supply_chain.alert_propagated")
    ).scalars().all()
    assert audit_rows == []


def test_t4_5_vendor_kyb_check_empty_company_name_rejected(client):
    org = bootstrap_org_user(client, email_prefix="t4-kyb-empty")
    vendor = _create_vendor(client, org, name="   ", website="https://blankname.example")
    resp = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert resp.status_code == 422, resp.text


def test_t4_5_vendor_kyb_check_archived_vendor_rejected(client):
    org = bootstrap_org_user(client, email_prefix="t4-kyb-archived")
    vendor = _create_vendor(client, org, name="Archived Co", website="https://archived.example")
    archive = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "no longer used"},
    )
    assert archive.status_code == 200, archive.text
    resp = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert resp.status_code == 400, resp.text


def test_t4_5_vendor_kyb_check_cross_org_blocked(client):
    org_a = bootstrap_org_user(client, email_prefix="t4-kyb-cross-a")
    org_b = bootstrap_org_user(client, email_prefix="t4-kyb-cross-b")
    vendor = _create_vendor(client, org_a)
    resp = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org_b["org_headers"])
    assert resp.status_code == 404, resp.text


def test_t4_5_vendor_kyb_check_malformed_vendor_id(client):
    org = bootstrap_org_user(client, email_prefix="t4-kyb-malformed")
    resp = client.post(f"{SATELLITE_BASE}/not-a-uuid/kyb-check/compute", headers=org["org_headers"])
    assert resp.status_code == 422, resp.text


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


def test_t1_3_supply_chain_graph_detects_cycle_and_rejects_bad_links(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t1-supply-chain")
    vendor_a = _create_vendor(client, org, name="First Party A", website="https://a.example")
    vendor_b = _create_vendor(client, org, name="Fourth Party B", website="https://b.example")
    vendor_c = _create_vendor(client, org, name="Fifth Party C", website="https://c.example")

    self_link = client.post(
        f"{SATELLITE_BASE}/{vendor_a['id']}/supply-chain-links",
        headers=org["org_headers"],
        json={"sub_vendor_id": vendor_a["id"], "relationship_type": "hosting"},
    )
    assert self_link.status_code == 422
    assert "cannot depend on itself" in self_link.text

    for parent, child in [(vendor_a, vendor_b), (vendor_b, vendor_c), (vendor_c, vendor_a)]:
        response = client.post(
            f"{SATELLITE_BASE}/{parent['id']}/supply-chain-links",
            headers=org["org_headers"],
            json={"sub_vendor_id": child["id"], "relationship_type": "hosting"},
        )
        assert response.status_code == 201, response.text

    duplicate = client.post(
        f"{SATELLITE_BASE}/{vendor_a['id']}/supply-chain-links",
        headers=org["org_headers"],
        json={"sub_vendor_id": vendor_b["id"], "relationship_type": "hosting"},
    )
    assert duplicate.status_code == 409

    graph = client.get(f"{SATELLITE_BASE}/{vendor_a['id']}/supply-chain-graph?depth=5", headers=org["org_headers"])
    assert graph.status_code == 200, graph.text
    body = graph.json()
    assert len(body["nodes"]) == 3
    assert len(body["edges"]) == 3
    assert body["data_quality_findings"][0]["type"] == "cycle_detected"
    assert vendor_a["id"] in body["data_quality_findings"][0]["vendor_ids"]

    audit = db_session.execute(select(AuditLog).where(AuditLog.action == "vendor_supply_chain.link_created")).scalars().all()
    assert len(audit) == 3


def test_t1_3_supply_chain_propagates_nth_party_signal_to_first_party(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="t1-supply-chain-signal")
    first_party = _create_vendor(client, org, name="Critical SaaS", website="https://critical.example")
    fourth_party = _create_vendor(client, org, name="Platform Host", website="https://platform.example")
    fifth_party = _create_vendor(client, org, name="Risky CDN", website="https://risky.example")
    for parent, child in [(first_party, fourth_party), (fourth_party, fifth_party), (fifth_party, first_party)]:
        linked = client.post(
            f"{SATELLITE_BASE}/{parent['id']}/supply-chain-links",
            headers=org["org_headers"],
            json={"sub_vendor_id": child["id"], "relationship_type": "cdn_dependency"},
        )
        assert linked.status_code == 201, linked.text

    def degraded_rating(self, domain: str) -> dict:
        return {"domain": domain, "composite_score": 42.0, "signals_used": {"mozilla_observatory": {"status": "available", "score": 42}}}

    monkeypatch.setattr(VendorSecurityRatingService, "compute", degraded_rating)
    computed = client.post(f"{SATELLITE_BASE}/{fifth_party['id']}/security-rating/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text

    graph = client.get(f"{SATELLITE_BASE}/{first_party['id']}/supply-chain-graph?depth=5", headers=org["org_headers"])
    assert graph.status_code == 200
    body = graph.json()
    assert body["data_quality_findings"][0]["type"] == "cycle_detected"
    alerts = body["open_alerts"]
    first_party_alert = next(alert for alert in alerts if alert["parent_vendor_id"] == first_party["id"])
    assert first_party_alert["triggering_vendor_id"] == fifth_party["id"]
    assert first_party_alert["signal_type"] == "security_rating_degraded"
    assert first_party_alert["severity"] == "high"
    assert "Risky CDN" in first_party_alert["explanation"]

    flagged = client.get(f"{VENDORS_BASE}/{first_party['id']}", headers=org["org_headers"])
    assert flagged.status_code == 200
    assert flagged.json()["nth_party_risk_flag"] is True
    assert flagged.json()["nth_party_risk_severity"] == "high"
    assert flagged.json()["nth_party_risk_signal_type"] == "security_rating_degraded"

    audit = db_session.execute(select(AuditLog).where(AuditLog.action == "vendor_supply_chain.nth_party_flag_updated")).scalars().all()
    assert any(row.after_json["triggering_vendor_id"] == fifth_party["id"] and row.entity_id == uuid.UUID(first_party["id"]) for row in audit)
