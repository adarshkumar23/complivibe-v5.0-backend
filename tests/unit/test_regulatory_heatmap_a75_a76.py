import uuid
from datetime import UTC, datetime, timedelta

from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.framework_section import FrameworkSection
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _seed_framework_with_org(db_session, org_id: str, *, name: str, code_prefix: str = "FW") -> Framework:
    fw = Framework(
        code=f"{code_prefix}-{uuid.uuid4().hex[:6]}",
        name=name,
        category="regulatory",
        jurisdiction="global",
        status="active",
        coverage_level="starter",
    )
    db_session.add(fw)
    db_session.flush()
    db_session.add(OrganizationFramework(organization_id=uuid.UUID(org_id), framework_id=fw.id, status="active"))
    db_session.commit()
    return fw


def test_a75_regulatory_builders_and_storage(client, db_session):
    token = _register(client, "a75-owner@example.com", "Pass1234!@", "A75 Org")
    org_id = _org_id(client, token)

    # SOC2
    soc2 = _seed_framework_with_org(db_session, org_id, name="SOC 2 Type II", code_prefix="SOC2")
    ob_soc_ready = Obligation(framework_id=soc2.id, reference_code="CC6.1", title="MFA", jurisdiction="global", status="active")
    ob_soc_partial = Obligation(framework_id=soc2.id, reference_code="CC7.1", title="Monitoring", jurisdiction="global", status="active")
    db_session.add_all([ob_soc_ready, ob_soc_partial])
    db_session.flush()
    db_session.add_all(
        [
            OrganizationObligationState(
                organization_id=uuid.UUID(org_id),
                obligation_id=ob_soc_ready.id,
                applicability_status="applicable",
                implementation_status="met",
            ),
            OrganizationObligationState(
                organization_id=uuid.UUID(org_id),
                obligation_id=ob_soc_partial.id,
                applicability_status="applicable",
                implementation_status="not_started",
            ),
        ]
    )
    c = Control(organization_id=uuid.UUID(org_id), title="MFA Control", status="implemented", control_type="technical")
    db_session.add(c)
    db_session.flush()
    db_session.add(ControlObligationMapping(organization_id=uuid.UUID(org_id), control_id=c.id, obligation_id=ob_soc_ready.id, status="active"))
    e = EvidenceItem(
        organization_id=uuid.UUID(org_id),
        title="MFA Proof",
        evidence_type="screenshot",
        source="manual",
        status="active",
        review_status="verified",
        valid_until=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(e)
    db_session.flush()
    db_session.add(EvidenceControlLink(organization_id=uuid.UUID(org_id), evidence_item_id=e.id, control_id=c.id, link_status="active"))
    db_session.commit()

    resp_soc = client.post("/api/v1/reports/regulatory/soc2_readiness", headers=_headers(token, org_id))
    assert resp_soc.status_code == 200
    assert resp_soc.json()["report_type"] == "soc2_readiness"
    detail = client.get(f"/api/v1/reports/{resp_soc.json()['id']}", headers=_headers(token, org_id)).json()
    payload = next(s for s in detail["sections"] if s["section_key"] == "soc2_readiness")["data_json"]
    assert payload["categories"]
    assert payload["summary"]["readiness_pct"] >= 0

    # GDPR stub
    resp_gdpr = client.post("/api/v1/reports/regulatory/gdpr_ropa", headers=_headers(token, org_id))
    assert resp_gdpr.status_code == 200
    detail_gdpr = client.get(f"/api/v1/reports/{resp_gdpr.json()['id']}", headers=_headers(token, org_id)).json()
    gdpr_payload = next(s for s in detail_gdpr["sections"] if s["section_key"] == "gdpr_ropa")["data_json"]
    assert gdpr_payload["status"] == "empty"
    assert isinstance(gdpr_payload["activities"], list)

    # ISO
    iso = _seed_framework_with_org(db_session, org_id, name="ISO 27001:2022", code_prefix="ISO")
    db_session.add_all(
        [
            Obligation(framework_id=iso.id, reference_code="A.9.1.1", title="Access policy", jurisdiction="global", status="active", description="desc"),
            Obligation(framework_id=iso.id, reference_code="A.10.1", title="Crypto policy", jurisdiction="global", status="active", description="desc"),
        ]
    )
    db_session.commit()
    resp_iso = client.post("/api/v1/reports/regulatory/iso27001_soa", headers=_headers(token, org_id))
    assert resp_iso.status_code == 200
    detail_iso = client.get(f"/api/v1/reports/{resp_iso.json()['id']}", headers=_headers(token, org_id)).json()
    iso_payload = next(s for s in detail_iso["sections"] if s["section_key"] == "iso27001_soa")["data_json"]
    assert iso_payload["domains"]

    # NIST AI RMF
    nist = _seed_framework_with_org(db_session, org_id, name="NIST AI RMF", code_prefix="NISTAI")
    for ref in ["GOVERN-1", "MAP-1", "MEASURE-1", "MANAGE-1"]:
        db_session.add(Obligation(framework_id=nist.id, reference_code=ref, title=ref, jurisdiction="global", status="active"))
    db_session.commit()
    resp_nist = client.post("/api/v1/reports/regulatory/nist_ai_rmf_summary", headers=_headers(token, org_id))
    assert resp_nist.status_code == 200
    detail_nist = client.get(f"/api/v1/reports/{resp_nist.json()['id']}", headers=_headers(token, org_id)).json()
    nist_payload = next(s for s in detail_nist["sections"] if s["section_key"] == "nist_ai_rmf_summary")["data_json"]
    assert len(nist_payload["functions"]) == 4

    # EU AI Act
    eu = _seed_framework_with_org(db_session, org_id, name="EU AI Act", code_prefix="EUAI")
    db_session.add_all(
        [
            Obligation(framework_id=eu.id, reference_code="Art. 5", title="Prohibited", jurisdiction="eu", status="active"),
            Obligation(framework_id=eu.id, reference_code="Art. 6", title="High risk", jurisdiction="eu", status="active"),
            Obligation(framework_id=eu.id, reference_code="Art. 52", title="Limited", jurisdiction="eu", status="active"),
            Obligation(framework_id=eu.id, reference_code="Art. 53", title="Minimal", jurisdiction="eu", status="active"),
        ]
    )
    db_session.commit()
    resp_eu = client.post("/api/v1/reports/regulatory/eu_ai_act_conformity", headers=_headers(token, org_id))
    assert resp_eu.status_code == 200
    detail_eu = client.get(f"/api/v1/reports/{resp_eu.json()['id']}", headers=_headers(token, org_id)).json()
    eu_payload = next(s for s in detail_eu["sections"] if s["section_key"] == "eu_ai_act_conformity")["data_json"]
    assert eu_payload["risk_tiers"]

    # Unknown type
    unknown = client.post("/api/v1/reports/regulatory/unknown_type", headers=_headers(token, org_id))
    assert unknown.status_code == 422



def test_a75_soc2_not_configured_and_org_isolation(client):
    token_a = _register(client, "a75-owner-a@example.com", "Pass1234!@", "A75 Org A")
    token_b = _register(client, "a75-owner-b@example.com", "Pass1234!@", "A75 Org B")
    org_a = _org_id(client, token_a)
    org_b = _org_id(client, token_b)

    resp = client.post("/api/v1/reports/regulatory/soc2_readiness", headers=_headers(token_a, org_a))
    assert resp.status_code == 200
    report_id = resp.json()["id"]

    detail_a = client.get(f"/api/v1/reports/{report_id}", headers=_headers(token_a, org_a)).json()
    payload = next(s for s in detail_a["sections"] if s["section_key"] == "soc2_readiness")["data_json"]
    assert payload["status"] == "not_applicable"

    detail_b = client.get(f"/api/v1/reports/{report_id}", headers=_headers(token_b, org_b))
    assert detail_b.status_code == 404



def test_a76_framework_coverage_matrix_statuses_and_grouping(client, db_session):
    token = _register(client, "a76-owner@example.com", "Pass1234!@", "A76 Org")
    org_id = _org_id(client, token)

    fw = _seed_framework_with_org(db_session, org_id, name="Coverage Framework", code_prefix="COV")
    section_a = FrameworkSection(framework_id=fw.id, section_code="SEC-A", title="Section A", status="active")
    section_b = FrameworkSection(framework_id=fw.id, section_code="SEC-B", title="Section B", status="active")
    db_session.add_all([section_a, section_b])
    db_session.flush()

    ob_covered = Obligation(framework_id=fw.id, framework_section_id=section_a.id, reference_code="CC6.1", title="Covered Obligation", jurisdiction="global", status="active")
    ob_partial = Obligation(framework_id=fw.id, framework_section_id=section_a.id, reference_code="CC6.2", title="Partial Obligation", jurisdiction="global", status="active")
    ob_uncovered = Obligation(framework_id=fw.id, framework_section_id=section_b.id, reference_code="CC6.3", title="Uncovered Obligation", jurisdiction="global", status="active")
    ob_expired = Obligation(framework_id=fw.id, framework_section_id=section_b.id, reference_code="CC6.4", title="Expired Evidence Obligation", jurisdiction="global", status="active")
    db_session.add_all([ob_covered, ob_partial, ob_uncovered, ob_expired])
    db_session.flush()

    c_cov = Control(organization_id=uuid.UUID(org_id), title="Control Covered", status="implemented", control_type="technical")
    c_par = Control(organization_id=uuid.UUID(org_id), title="Control Partial", status="implemented", control_type="technical")
    c_exp = Control(organization_id=uuid.UUID(org_id), title="Control Expired", status="implemented", control_type="technical")
    db_session.add_all([c_cov, c_par, c_exp])
    db_session.flush()

    db_session.add_all(
        [
            ControlObligationMapping(organization_id=uuid.UUID(org_id), control_id=c_cov.id, obligation_id=ob_covered.id, status="active"),
            ControlObligationMapping(organization_id=uuid.UUID(org_id), control_id=c_par.id, obligation_id=ob_partial.id, status="active"),
            ControlObligationMapping(organization_id=uuid.UUID(org_id), control_id=c_exp.id, obligation_id=ob_expired.id, status="active"),
        ]
    )

    e_cov = EvidenceItem(
        organization_id=uuid.UUID(org_id),
        title="Evidence Covered",
        evidence_type="doc",
        source="manual",
        status="active",
        review_status="verified",
        valid_until=datetime.now(UTC) + timedelta(days=10),
    )
    e_exp = EvidenceItem(
        organization_id=uuid.UUID(org_id),
        title="Evidence Expired",
        evidence_type="doc",
        source="manual",
        status="active",
        review_status="verified",
        valid_until=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add_all([e_cov, e_exp])
    db_session.flush()
    db_session.add_all(
        [
            EvidenceControlLink(organization_id=uuid.UUID(org_id), evidence_item_id=e_cov.id, control_id=c_cov.id, link_status="active"),
            EvidenceControlLink(organization_id=uuid.UUID(org_id), evidence_item_id=e_exp.id, control_id=c_exp.id, link_status="active"),
        ]
    )
    db_session.commit()

    matrix = client.get(f"/api/v1/reports/framework-coverage-matrix?framework_id={fw.id}", headers=_headers(token, org_id))
    assert matrix.status_code == 200
    payload = matrix.json()

    assert payload["total_obligations"] == 4
    assert payload["covered"] == 1
    assert payload["partial"] == 2
    assert payload["uncovered"] == 1
    assert payload["coverage_pct"] == 25.0

    all_obs = [ob for sec in payload["sections"] for ob in sec["obligations"]]
    by_ref = {ob["reference"]: ob["coverage_status"] for ob in all_obs}
    assert by_ref["CC6.1"] == "covered"
    assert by_ref["CC6.2"] == "partial"
    assert by_ref["CC6.3"] == "uncovered"
    assert by_ref["CC6.4"] == "partial"

    assert len(payload["sections"]) >= 2

    missing = client.get("/api/v1/reports/framework-coverage-matrix", headers=_headers(token, org_id))
    assert missing.status_code == 422

    unknown = client.get(f"/api/v1/reports/framework-coverage-matrix?framework_id={uuid.uuid4()}", headers=_headers(token, org_id))
    assert unknown.status_code == 404
