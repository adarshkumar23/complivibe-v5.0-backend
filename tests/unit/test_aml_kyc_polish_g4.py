from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.aml_kyc_check import AmlKycCheck
from app.satellites.tprm_intelligence.kyb_verification import KYBVerificationService
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
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _clean_result(company_name: str, signals_used: dict | None = None) -> dict:
    return {
        "company_name": company_name,
        "signals_used": signals_used or {},
        "offshore_links_found": {"source": "icij_offshore_leaks", "found": False, "matches": [], "status": "available"},
        "ubo_data": {"source": "openownership", "status": "available", "coverage_limitation": "", "statements": []},
        "adverse_media_found": False,
    }


def test_g4_kyb_check_reports_freshness(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g4-kyb-fresh")
    vendor = _create_vendor(client, org, name="Fresh Check Co", website="https://fresh-check.example")
    monkeypatch.setattr(KYBVerificationService, "compute", lambda self, name: _clean_result(name))

    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["is_stale"] is False
    assert body["days_since_checked"] is not None
    assert body["days_since_checked"] < 1
    assert body["name_changed_since_check"] is False


def test_g4_kyb_check_flags_stale_result(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g4-kyb-stale")
    vendor = _create_vendor(client, org, name="Aging Check Co", website="https://aging-check.example")
    monkeypatch.setattr(KYBVerificationService, "compute", lambda self, name: _clean_result(name))

    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    check_id = computed.json()["id"]

    row = db_session.execute(select(AmlKycCheck).where(AmlKycCheck.id == uuid.UUID(check_id))).scalar_one()
    row.checked_at = datetime.now(UTC) - timedelta(days=10)
    db_session.commit()

    latest = client.get(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check", headers=org["org_headers"])
    assert latest.status_code == 200, latest.text
    body = latest.json()
    assert body["is_stale"] is True
    assert body["days_since_checked"] >= 9.9


def test_g4_kyb_check_flags_vendor_renamed_since_check(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g4-kyb-rename")
    vendor = _create_vendor(client, org, name="Old Trading Name LLC", website="https://oldtrading.example")
    monkeypatch.setattr(KYBVerificationService, "compute", lambda self, name: _clean_result(name))

    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text

    renamed = client.patch(
        f"{VENDORS_BASE}/{vendor['id']}",
        headers=org["org_headers"],
        json={"name": "New Trading Name LLC"},
    )
    assert renamed.status_code == 200, renamed.text

    latest = client.get(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check", headers=org["org_headers"])
    assert latest.status_code == 200, latest.text
    assert latest.json()["name_changed_since_check"] is True


def test_g4_kyb_check_flags_no_verifiable_registration_as_medium_risk(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g4-kyb-shell")
    vendor = _create_vendor(client, org, name="Ghost Consulting Co", website="https://ghost-consulting.example")

    def fake_compute(self, company_name: str) -> dict:
        return _clean_result(
            company_name,
            signals_used={
                "gleif": {"status": "available", "source": "gleif", "match_count": 0, "records": []},
                "opencorporates": {"status": "available", "source": "opencorporates", "match_count": 0, "companies": []},
            },
        )

    monkeypatch.setattr(KYBVerificationService, "compute", fake_compute)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["no_verifiable_registration"] is True

    vendor_after = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=org["org_headers"])
    assert vendor_after.json()["risk_tier"] == "medium"


def test_g4_kyb_check_does_not_flag_shell_risk_when_coverage_incomplete(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g4-kyb-nocoverage")
    vendor = _create_vendor(client, org, name="Unknown Coverage Co", website="https://unknown-coverage.example")

    def fake_compute(self, company_name: str) -> dict:
        return _clean_result(
            company_name,
            signals_used={
                "gleif": {"status": "available", "source": "gleif", "match_count": 0, "records": []},
                "opencorporates": {
                    "status": "skipped",
                    "source": "opencorporates",
                    "message": "OpenCorporates signal skipped: API key not configured",
                },
            },
        )

    monkeypatch.setattr(KYBVerificationService, "compute", fake_compute)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    # Coverage is incomplete (OpenCorporates was skipped), so this must NOT be treated
    # as a confirmed "no registration found anywhere" signal.
    assert body["no_verifiable_registration"] is False

    vendor_after = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=org["org_headers"])
    assert vendor_after.json()["risk_tier"] == "not_assessed"
