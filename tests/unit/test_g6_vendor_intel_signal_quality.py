"""G6 - Vendor Intelligence Signal Quality regression tests.

Covers all 4 items:
  1. Security-rating/threat-intelligence confidence field + no more fabricated
     0.0 when zero signals return real data.
  2. AML/KYB /history endpoint (mirrors security-rating/threat-intelligence).
  3. Geopolitical Risk critical signal cascades into vendor risk_tier / Risk.
  4. OT/ICS findings (and flagged multi-finding segments) create Risk entries.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.membership import Membership
from app.models.ot_ics_finding import OtIcsFinding  # noqa: F401
from app.models.ot_ics_segment_risk_detection import OtIcsSegmentRiskDetection
from app.models.permission import Permission
from app.models.risk import Risk
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.vendor import Vendor
from app.models.vendor_external_rating import VendorExternalRating
from app.models.vendor_geopolitical_exposure import VendorGeopoliticalExposure
from app.models.vendor_threat_intelligence import VendorThreatIntelligence
from app.satellites.tprm_intelligence.threat_intelligence import ThreatIntelligenceService
from app.satellites.tprm_intelligence.vendor_security_rating import VendorSecurityRatingService
from app.services.geopolitical_risk_service import GeopoliticalRiskService
from tests.helpers.auth_org import bootstrap_org_user

SATELLITE_BASE = "/api/v1/vendors"
VENDORS_BASE = "/api/v1/compliance/vendors"
GEOPOLITICAL_BASE = "/api/v1/geopolitical-risk"
OT_ICS_ASSETS_BASE = "/api/v1/ot-ics/assets"
OT_ICS_FINDINGS_INGEST = "/api/v1/ot-ics/findings/ingest"
OT_ICS_AGENTS_BASE = "/api/v1/ot-ics/agents"


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


# ---------------------------------------------------------------------------
# Item 1: confidence field + no fabricated extreme score when data is missing
# ---------------------------------------------------------------------------


def test_security_rating_all_signals_missing_yields_null_score_zero_confidence(client, db_session, monkeypatch):
    """Root-cause regression: when all 4 signals error/skip, the old code
    silently collapsed composite_score to 0.0 -- indistinguishable from "we
    checked and it's terrible". It must now be None with confidence == 0, and
    it must NOT trigger a degraded/critical alert (no data isn't a bad reading)."""
    org = bootstrap_org_user(client, email_prefix="g6-rating-nodata")
    vendor = _create_vendor(client, org, website="https://nodata.example")

    def fake_compute(self, domain: str) -> dict:
        signals = {
            "mozilla_observatory": {"status": "error", "source": "mozilla_observatory", "score": None, "message": "timeout"},
            "gdelt_adverse_media": {"status": "error", "source": "gdelt", "score": None, "message": "rate limited"},
            "abuseipdb": {"status": "skipped", "source": "abuseipdb", "score": None, "message": "no api key"},
            "hibp": {"status": "skipped", "source": "hibp", "score": None, "message": "no api key"},
        }
        return {
            "domain": domain,
            "signals_used": signals,
            "composite_score": None,
            "confidence": 0.0,
            "signals_available": 0,
            "signals_total": 4,
        }

    monkeypatch.setattr(VendorSecurityRatingService, "compute", fake_compute)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/security-rating/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["composite_score"] is None
    assert body["confidence"] == 0.0
    assert body["has_sufficient_data"] is False

    row = db_session.execute(
        select(VendorExternalRating).where(VendorExternalRating.vendor_id == uuid.UUID(vendor["id"]))
    ).scalar_one()
    assert row.composite_score is None
    assert float(row.confidence) == 0.0

    # No data must never fabricate a "degraded/critical" alert -- vendor's
    # nth_party_risk_flag must stay clean.
    db_session.refresh(row)
    vendor_row = db_session.get(Vendor, uuid.UUID(vendor["id"]))
    assert vendor_row.nth_party_risk_flag is False


def test_security_rating_partial_signals_reports_real_confidence(client, db_session, monkeypatch):
    """When some signals are available, confidence should reflect the actual
    fraction of scoring weight backed by real data, not be silently absent."""
    org = bootstrap_org_user(client, email_prefix="g6-rating-partial")
    vendor = _create_vendor(client, org, website="https://partial.example")

    def fake_compute(self, domain: str) -> dict:
        return {
            "domain": domain,
            "composite_score": 90.0,
            "confidence": 45.0,  # only mozilla_observatory (weight 0.45) available
            "signals_available": 1,
            "signals_total": 4,
            "signals_used": {
                "mozilla_observatory": {"status": "available", "source": "mozilla_observatory", "score": 90},
                "gdelt_adverse_media": {"status": "error", "source": "gdelt", "score": None, "message": "rate limited"},
                "abuseipdb": {"status": "skipped", "source": "abuseipdb", "score": None, "message": "no api key"},
                "hibp": {"status": "skipped", "source": "hibp", "score": None, "message": "no api key"},
            },
        }

    monkeypatch.setattr(VendorSecurityRatingService, "compute", fake_compute)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/security-rating/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["composite_score"] == 90.0
    assert body["confidence"] == 45.0
    assert body["has_sufficient_data"] is False  # < 50% threshold


def test_weighted_score_with_confidence_excludes_missing_signals_from_math():
    """Unit-level check of the shared scoring core: missing/errored signals must
    not pull the aggregate toward an extreme; only real signals contribute, and
    confidence reflects exactly how much weight is backed by real data."""
    from app.satellites.tprm_intelligence.vendor_security_rating import weighted_score_with_confidence

    weights = {"a": 0.5, "b": 0.3, "c": 0.2}
    signals = {
        "a": {"status": "available", "score": 100},
        "b": {"status": "error", "score": None},
        "c": {"status": "skipped", "score": None},
    }
    result = weighted_score_with_confidence(signals, weights)
    assert result["score"] == 100.0  # only "a" contributes -> untouched by b/c's absence
    assert result["confidence"] == 50.0  # 0.5 / 1.0 total weight
    assert result["signals_available"] == 1
    assert result["signals_total"] == 3

    all_missing = {
        "a": {"status": "error", "score": None},
        "b": {"status": "skipped", "score": None},
        "c": {"status": "skipped", "score": None},
    }
    result_none = weighted_score_with_confidence(all_missing, weights)
    assert result_none["score"] is None  # never a fabricated 0.0
    assert result_none["confidence"] == 0.0


def test_threat_intelligence_no_data_does_not_read_as_confirmed_clean(client, db_session, monkeypatch):
    """Mirror check for threat intelligence: since a HIGHER threat_score is worse,
    a fabricated 0.0 on zero signals would be a false negative ("confirmed
    clean"). It must be None with confidence 0 instead, and not resolve/skip an
    elevated-threat state as if verified safe."""
    org = bootstrap_org_user(client, email_prefix="g6-threat-nodata")
    vendor = _create_vendor(client, org, website="https://threat-nodata.example")

    def fake_compute(self, domain: str) -> dict:
        return {
            "domain": domain,
            "threat_score": None,
            "confidence": 0.0,
            "signals_available": 0,
            "signals_total": 3,
            "signals_used": {
                "alienvault_otx": {"status": "skipped", "source": "alienvault_otx", "score": None, "message": "no api key"},
                "abuseipdb": {"status": "skipped", "source": "abuseipdb", "score": None, "message": "no api key"},
                "gdelt_threat_media": {"status": "error", "source": "gdelt", "score": None, "message": "rate limited"},
            },
            "indicators_found": {},
        }

    monkeypatch.setattr(ThreatIntelligenceService, "compute", fake_compute)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/threat-intelligence/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["threat_score"] is None
    assert body["confidence"] == 0.0
    assert body["has_sufficient_data"] is False

    row = db_session.execute(
        select(VendorThreatIntelligence).where(VendorThreatIntelligence.vendor_id == uuid.UUID(vendor["id"]))
    ).scalar_one()
    assert row.threat_score is None


# ---------------------------------------------------------------------------
# Item 2: AML/KYB /history endpoint
# ---------------------------------------------------------------------------


def test_kyb_history_endpoint_mirrors_sibling_history_shape(client, db_session, monkeypatch):
    from app.satellites.tprm_intelligence.kyb_verification import KYBVerificationService

    org = bootstrap_org_user(client, email_prefix="g6-kyb-history")
    vendor = _create_vendor(client, org, name="History Co", website="https://history.example")

    call_results = iter(
        [
            {"adverse_media_found": False, "offshore_links_found": {"found": False}},
            {"adverse_media_found": True, "offshore_links_found": {"found": False}},
        ]
    )

    def fake_compute(self, company_name: str) -> dict:
        outcome = next(call_results)
        return {
            "company_name": company_name,
            "signals_used": {
                "gleif": {"status": "available", "source": "gleif", "match_count": 1, "records": []},
                "opencorporates": {"status": "skipped", "source": "opencorporates", "message": "no api key"},
                "icij_offshore_leaks": {"status": "available", "source": "icij_offshore_leaks", "match_count": 0, "results": []},
                "openownership": {"status": "available", "source": "openownership", "statement_count": 0, "statements": []},
                "gdelt_adverse_media": {"status": "available", "source": "gdelt", "article_count": 0, "articles": []},
            },
            "offshore_links_found": outcome["offshore_links_found"],
            "ubo_data": {"source": "openownership", "status": "available", "statements": []},
            "adverse_media_found": outcome["adverse_media_found"],
        }

    monkeypatch.setattr(KYBVerificationService, "compute", fake_compute)

    first = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert first.status_code == 201, first.text
    second = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert second.status_code == 201, second.text

    history = client.get(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/history", headers=org["org_headers"])
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["count"] == 2
    assert body["vendor_id"] == vendor["id"]
    # newest first
    assert body["history"][0]["id"] == second.json()["id"]
    assert body["history"][1]["id"] == first.json()["id"]
    assert body["latest_has_risk"] is True
    assert body["latest_severity"] == "high"
    assert body["trend"] == "escalating"
    assert "is_stale" in body


def test_kyb_history_404_when_no_checks_exist(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g6-kyb-history-empty")
    vendor = _create_vendor(client, org, website="https://empty-history.example")

    history = client.get(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/history", headers=org["org_headers"])
    assert history.status_code == 404


# ---------------------------------------------------------------------------
# Item 3: Geopolitical Risk -> vendor risk_tier / Risk cascade
# ---------------------------------------------------------------------------


_GEOPOLITICAL_PERMISSION_CODES = ("geopolitical_risk:read", "geopolitical_risk:manage")


def _grant_geo_permissions(db_session, organization_id: str) -> None:
    org_uuid = uuid.UUID(organization_id)
    role = db_session.query(Role).filter(Role.organization_id == org_uuid, Role.name == "owner").one()
    for code in _GEOPOLITICAL_PERMISSION_CODES:
        permission = db_session.query(Permission).filter(Permission.key == code).one_or_none()
        if permission is None:
            permission = Permission(key=code, description=code)
            db_session.add(permission)
            db_session.flush()
        existing = db_session.query(RolePermission).filter(
            RolePermission.role_id == role.id, RolePermission.permission_id == permission.id
        ).one_or_none()
        if existing is None:
            db_session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db_session.commit()


class _FakeGdeltClient:
    def __init__(self, articles: list[dict]) -> None:
        self._articles = articles

    def search_articles(self, region_query: str, *, max_records: int = 20) -> list[dict]:
        return self._articles


def test_critical_geopolitical_signal_escalates_vendor_risk_tier_and_creates_risk(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g6-geo-cascade")
    _grant_geo_permissions(db_session, org["organization_id"])
    vendor = _create_vendor(client, org, name="Exposed Vendor")

    exposure_response = client.post(
        f"{GEOPOLITICAL_BASE}/vendor-exposures",
        headers=org["org_headers"],
        json={"vendor_id": vendor["id"], "region": "Warzonia", "is_primary": True},
    )
    assert exposure_response.status_code == 201, exposure_response.text

    vendor_before = db_session.get(Vendor, uuid.UUID(vendor["id"]))
    assert vendor_before.risk_tier == "not_assessed"

    service = GeopoliticalRiskService(
        db_session,
        http_client=_FakeGdeltClient(
            [
                {
                    "url": "https://example.test/war",
                    "title": "War breaks out as invasion forces cross the border",
                    "seendate": "20260603T090000Z",
                }
            ]
        ),
    )
    result = service.ingest_from_gdelt(uuid.UUID(org["organization_id"]), "Warzonia", uuid.UUID(org["user_id"]))
    assert result["status"] == "ok"
    assert result["signals_created"] == 1
    assert result["signals"][0].severity == "critical"

    db_session.expire_all()
    vendor_after = db_session.get(Vendor, uuid.UUID(vendor["id"]))
    assert vendor_after.risk_tier == "critical"

    exposure = db_session.execute(
        select(VendorGeopoliticalExposure).where(VendorGeopoliticalExposure.vendor_id == uuid.UUID(vendor["id"]))
    ).scalar_one()
    assert exposure.cascaded_risk_id is not None

    risk = db_session.get(Risk, exposure.cascaded_risk_id)
    assert risk is not None
    assert risk.category == "vendor"
    assert "Warzonia" in risk.title

    # A second critical signal for the same region must not create a second Risk.
    service2 = GeopoliticalRiskService(
        db_session,
        http_client=_FakeGdeltClient(
            [
                {
                    "url": "https://example.test/war2",
                    "title": "Coup and nuclear threat escalate the invasion",
                    "seendate": "20260604T090000Z",
                }
            ]
        ),
    )
    service2.ingest_from_gdelt(uuid.UUID(org["organization_id"]), "Warzonia", uuid.UUID(org["user_id"]))
    db_session.expire_all()
    exposure_after_second = db_session.execute(
        select(VendorGeopoliticalExposure).where(VendorGeopoliticalExposure.vendor_id == uuid.UUID(vendor["id"]))
    ).scalar_one()
    assert exposure_after_second.cascaded_risk_id == exposure.cascaded_risk_id
    risk_count = db_session.execute(
        select(Risk).where(Risk.organization_id == uuid.UUID(org["organization_id"]), Risk.category == "vendor")
    ).scalars().all()
    assert len(risk_count) == 1


def test_non_critical_geopolitical_signal_does_not_cascade(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g6-geo-nocascade")
    _grant_geo_permissions(db_session, org["organization_id"])
    vendor = _create_vendor(client, org, name="Unaffected Vendor")

    exposure_response = client.post(
        f"{GEOPOLITICAL_BASE}/vendor-exposures",
        headers=org["org_headers"],
        json={"vendor_id": vendor["id"], "region": "Calmlandia", "is_primary": True},
    )
    assert exposure_response.status_code == 201, exposure_response.text

    service = GeopoliticalRiskService(
        db_session,
        http_client=_FakeGdeltClient(
            [
                {
                    "url": "https://example.test/protest",
                    "title": "Peaceful protest over new tariff policy",
                    "seendate": "20260603T090000Z",
                }
            ]
        ),
    )
    result = service.ingest_from_gdelt(uuid.UUID(org["organization_id"]), "Calmlandia", uuid.UUID(org["user_id"]))
    assert result["signals"][0].severity in ("low", "medium")

    db_session.expire_all()
    vendor_after = db_session.get(Vendor, uuid.UUID(vendor["id"]))
    assert vendor_after.risk_tier == "not_assessed"


# ---------------------------------------------------------------------------
# Item 4: OT/ICS findings -> risk-register cascade
# ---------------------------------------------------------------------------


_OT_ICS_PERMISSION_CODES = ("ot_ics_assets:read", "ot_ics_assets:manage")


def _grant_ot_ics_permissions(db_session, organization_id: str) -> None:
    org_uuid = uuid.UUID(organization_id)
    role = db_session.query(Role).filter(Role.organization_id == org_uuid, Role.name == "owner").one()
    for code in _OT_ICS_PERMISSION_CODES:
        permission = db_session.query(Permission).filter(Permission.key == code).one_or_none()
        if permission is None:
            permission = Permission(key=code, description=code)
            db_session.add(permission)
            db_session.flush()
        existing = db_session.query(RolePermission).filter(
            RolePermission.role_id == role.id, RolePermission.permission_id == permission.id
        ).one_or_none()
        if existing is None:
            db_session.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db_session.commit()


def _bootstrap_ot_ics(client, db_session, prefix: str) -> dict:
    org = bootstrap_org_user(client, email_prefix=prefix)
    _grant_ot_ics_permissions(db_session, org["organization_id"])
    return org


def _register_agent(client, org_headers_map: dict[str, str], *, name: str) -> dict:
    response = client.post(OT_ICS_AGENTS_BASE, headers=org_headers_map, json={"name": name})
    assert response.status_code == 201
    return response.json()


def _create_ot_ics_asset(client, org_headers_map: dict[str, str], *, name: str, network_segment: str = "vlan-500") -> dict:
    response = client.post(
        OT_ICS_ASSETS_BASE,
        headers=org_headers_map,
        json={"name": name, "asset_type": "plc", "criticality": "high", "network_segment": network_segment},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_critical_ot_ics_finding_creates_risk_register_entry(client, db_session):
    org = _bootstrap_ot_ics(client, db_session, "g6-otics-finding")
    agent = _register_agent(client, org["org_headers"], name="collector-1")
    asset = _create_ot_ics_asset(client, org["org_headers"], name="PLC-critical")

    ingest = client.post(
        OT_ICS_FINDINGS_INGEST,
        headers={"Authorization": f"Bearer {agent['token']}"},
        json={
            "asset_id": asset["id"],
            "finding_type": "unauthorized_network_bridge",
            "severity": "critical",
            "description": "Unauthorized bridge detected between OT and IT networks",
        },
    )
    assert ingest.status_code == 200, ingest.text
    finding_id = ingest.json()["finding_id"]

    finding = db_session.get(OtIcsFinding, uuid.UUID(finding_id))
    assert finding.risk_id is not None

    risk = db_session.get(Risk, finding.risk_id)
    assert risk is not None
    assert risk.category == "operational"
    assert "PLC-critical" in risk.title


def test_low_severity_ot_ics_finding_does_not_create_risk(client, db_session):
    org = _bootstrap_ot_ics(client, db_session, "g6-otics-lowsev")
    agent = _register_agent(client, org["org_headers"], name="collector-2")
    asset = _create_ot_ics_asset(client, org["org_headers"], name="PLC-low")

    ingest = client.post(
        OT_ICS_FINDINGS_INGEST,
        headers={"Authorization": f"Bearer {agent['token']}"},
        json={"asset_id": asset["id"], "finding_type": "anomalous_traffic", "severity": "low"},
    )
    assert ingest.status_code == 200, ingest.text
    finding = db_session.get(OtIcsFinding, uuid.UUID(ingest.json()["finding_id"]))
    assert finding.risk_id is None


def test_flagged_multi_finding_segment_creates_single_segment_risk(client, db_session):
    org = _bootstrap_ot_ics(client, db_session, "g6-otics-segment")
    agent = _register_agent(client, org["org_headers"], name="collector-3")
    asset_a = _create_ot_ics_asset(client, org["org_headers"], name="PLC-seg-A", network_segment="vlan-flagged")
    asset_b = _create_ot_ics_asset(client, org["org_headers"], name="PLC-seg-B", network_segment="vlan-flagged")

    for asset, finding_type in [(asset_a, "default_credentials"), (asset_b, "unpatched_firmware")]:
        ingest = client.post(
            OT_ICS_FINDINGS_INGEST,
            headers={"Authorization": f"Bearer {agent['token']}"},
            json={"asset_id": asset["id"], "finding_type": finding_type, "severity": "high"},
        )
        assert ingest.status_code == 200, ingest.text

    detection = db_session.execute(
        select(OtIcsSegmentRiskDetection).where(
            OtIcsSegmentRiskDetection.organization_id == uuid.UUID(org["organization_id"]),
            OtIcsSegmentRiskDetection.network_segment == "vlan-flagged",
        )
    ).scalar_one()
    assert detection.status == "flagged"
    assert detection.open_high_or_critical_count == 2
    assert detection.risk_id is not None

    segment_risk = db_session.get(Risk, detection.risk_id)
    assert segment_risk is not None
    assert "vlan-flagged" in segment_risk.title

    # A third finding on the same already-flagged segment must not create a
    # second segment-level Risk.
    asset_c = _create_ot_ics_asset(client, org["org_headers"], name="PLC-seg-C", network_segment="vlan-flagged")
    ingest_third = client.post(
        OT_ICS_FINDINGS_INGEST,
        headers={"Authorization": f"Bearer {agent['token']}"},
        json={"asset_id": asset_c["id"], "finding_type": "protocol_violation", "severity": "high"},
    )
    assert ingest_third.status_code == 200, ingest_third.text
    db_session.refresh(detection)
    assert detection.open_high_or_critical_count == 3
    assert detection.risk_id == segment_risk.id
