"""G8 item 4: a KYB result must expose per-source status so a compliance
officer can see exactly which of the 5 signals (GLEIF, OpenCorporates, ICIJ,
OpenOwnership, GDELT) actually contributed vs. silently failed/skipped --
never let an aggregate "pass" hide how thin its evidence base was."""

from app.satellites.tprm_intelligence.kyb_verification import KYBVerificationService
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
SATELLITE_BASE = "/api/v1/vendors"


def _create_vendor(client, org, *, name: str = "Example Vendor") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=org["org_headers"],
        json={"name": name, "vendor_type": "software", "owner_user_id": org["user_id"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_kyb_result_reports_per_source_status_when_only_one_of_five_succeeds(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g8-kyb-thin")
    vendor = _create_vendor(client, org, name="Thin Evidence Co")

    def fake_compute(self, company_name: str) -> dict:
        return {
            "company_name": company_name,
            "signals_used": {
                "gleif": {"status": "available", "source": "gleif", "match_count": 0, "records": []},
                "opencorporates": {"status": "skipped", "source": "opencorporates", "message": "no API key"},
                "icij_offshore_leaks": {"status": "error", "source": "icij_offshore_leaks", "message": "404"},
                "openownership": {"status": "error", "source": "openownership", "message": "403"},
                "gdelt_adverse_media": {"status": "error", "source": "gdelt", "message": "429"},
            },
            "offshore_links_found": {"source": "icij_offshore_leaks", "found": False, "matches": [], "status": "error"},
            "ubo_data": {"source": "openownership", "status": "error", "coverage_limitation": "", "statements": []},
            "adverse_media_found": False,
        }

    monkeypatch.setattr(KYBVerificationService, "compute", fake_compute)

    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()

    # The aggregate read as clean (no adverse media, no offshore links) -- but the
    # per-source breakdown must show only 1 of 5 sources actually succeeded.
    assert body["adverse_media_found"] is False
    assert "sources_checked" in body
    statuses = {row["source"]: row["status"] for row in body["sources_checked"]}
    assert statuses == {
        "gleif": "available",
        "opencorporates": "skipped",
        "icij_offshore_leaks": "error",
        "openownership": "error",
        "gdelt_adverse_media": "error",
    }
    assert body["sources_available_count"] == 1
    assert body["sources_total_count"] == 5
    assert body["insufficient_evidence"] is True


def test_kyb_result_marks_evidence_sufficient_when_most_sources_succeed(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g8-kyb-thick")
    vendor = _create_vendor(client, org, name="Thick Evidence Co")

    def fake_compute(self, company_name: str) -> dict:
        return {
            "company_name": company_name,
            "signals_used": {
                "gleif": {"status": "available", "source": "gleif", "match_count": 1, "records": []},
                "opencorporates": {"status": "available", "source": "opencorporates", "match_count": 1, "companies": []},
                "icij_offshore_leaks": {"status": "available", "source": "icij_offshore_leaks", "found": False, "matches": []},
                "openownership": {"status": "error", "source": "openownership", "message": "403"},
                "gdelt_adverse_media": {"status": "error", "source": "gdelt", "message": "429"},
            },
            "offshore_links_found": {"source": "icij_offshore_leaks", "found": False, "matches": [], "status": "available"},
            "ubo_data": {"source": "openownership", "status": "error", "coverage_limitation": "", "statements": []},
            "adverse_media_found": False,
        }

    monkeypatch.setattr(KYBVerificationService, "compute", fake_compute)

    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/kyb-check/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["sources_available_count"] == 3
    assert body["insufficient_evidence"] is False
