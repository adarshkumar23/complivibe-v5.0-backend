import uuid
from datetime import UTC, datetime

from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.export_job import ExportJob
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework


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


def _create_report(client, token: str, org_id: str) -> str:
    resp = client.post("/api/v1/reports/board-scorecard", headers=_headers(token, org_id))
    assert resp.status_code == 200
    return resp.json()["id"]


def test_a72_pdf_and_docx_export_and_export_job_record(client, db_session):
    token = _register(client, "a72-owner1@example.com", "Pass1234!@", "A72 Org1")
    org_id = _org_id(client, token)
    report_id = _create_report(client, token, org_id)

    pdf_resp = client.post(f"/api/v1/reports/{report_id}/export/pdf", headers=_headers(token, org_id))
    assert pdf_resp.status_code == 200
    assert len(pdf_resp.content) > 0
    assert pdf_resp.content.startswith(b"%PDF")

    docx_resp = client.post(f"/api/v1/reports/{report_id}/export/docx", headers=_headers(token, org_id))
    assert docx_resp.status_code == 200
    assert len(docx_resp.content) > 0
    assert docx_resp.content.startswith(b"PK")

    jobs = (
        db_session.query(ExportJob)
        .filter(
            ExportJob.organization_id == uuid.UUID(org_id),
            ExportJob.source_report_id == uuid.UUID(report_id),
            ExportJob.export_type.in_(["compliance_report_pdf", "compliance_report_docx"]),
        )
        .all()
    )
    assert len(jobs) == 2
    assert all(job.checksum_sha256 for job in jobs)



def test_a72_report_export_404_for_not_found_and_other_org(client):
    token_a = _register(client, "a72-owner2a@example.com", "Pass1234!@", "A72 Org2A")
    token_b = _register(client, "a72-owner2b@example.com", "Pass1234!@", "A72 Org2B")
    org_a = _org_id(client, token_a)
    org_b = _org_id(client, token_b)

    missing_id = str(uuid.uuid4())
    missing_resp = client.post(f"/api/v1/reports/{missing_id}/export/pdf", headers=_headers(token_a, org_a))
    assert missing_resp.status_code == 404

    report_id = _create_report(client, token_a, org_a)
    other_org_resp = client.post(f"/api/v1/reports/{report_id}/export/docx", headers=_headers(token_b, org_b))
    assert other_org_resp.status_code == 404



def test_a72_report_section_mapper_titles():
    from app.compliance.renderers.report_section_mapper import ReportSectionMapper

    assert ReportSectionMapper.get_title("score") == "Compliance Score"
    assert ReportSectionMapper.get_title("unknown_custom_key") == "Unknown Custom Key"



def test_a73_custom_template_crud_generate_scope_and_isolation(client, db_session):
    token_a = _register(client, "a73-owner1a@example.com", "Pass1234!@", "A73 Org1A")
    token_b = _register(client, "a73-owner1b@example.com", "Pass1234!@", "A73 Org1B")
    org_a = _org_id(client, token_a)
    org_b = _org_id(client, token_b)

    invalid = client.post(
        "/api/v1/compliance/custom-report-templates",
        headers=_headers(token_a, org_a),
        json={
            "name": "Invalid Template",
            "sections": ["executive_summary", "not_a_real_section"],
            "date_range_days": 90,
        },
    )
    assert invalid.status_code == 422

    fw1 = Framework(code=f"A73-{uuid.uuid4().hex[:6]}", name="FW-1", category="regulatory", jurisdiction="global", status="active", coverage_level="starter")
    fw2 = Framework(code=f"A73-{uuid.uuid4().hex[:6]}", name="FW-2", category="regulatory", jurisdiction="global", status="active", coverage_level="starter")
    db_session.add_all([fw1, fw2])
    db_session.flush()

    db_session.add_all(
        [
            OrganizationFramework(organization_id=uuid.UUID(org_a), framework_id=fw1.id, status="active"),
            OrganizationFramework(organization_id=uuid.UUID(org_a), framework_id=fw2.id, status="active"),
        ]
    )

    ob1 = Obligation(framework_id=fw1.id, reference_code="FW1-REQ", title="FW1 Req", jurisdiction="global", status="active")
    ob2 = Obligation(framework_id=fw2.id, reference_code="FW2-REQ", title="FW2 Req", jurisdiction="global", status="active")
    db_session.add_all([ob1, ob2])
    db_session.flush()

    c1 = Control(organization_id=uuid.UUID(org_a), title="FW1 Control", status="implemented", control_type="process")
    c2 = Control(organization_id=uuid.UUID(org_a), title="FW2 Control", status="not_started", control_type="process")
    db_session.add_all([c1, c2])
    db_session.flush()

    db_session.add_all(
        [
            ControlObligationMapping(organization_id=uuid.UUID(org_a), control_id=c1.id, obligation_id=ob1.id, status="active"),
            ControlObligationMapping(organization_id=uuid.UUID(org_a), control_id=c2.id, obligation_id=ob2.id, status="active"),
        ]
    )
    db_session.commit()

    create_resp = client.post(
        "/api/v1/compliance/custom-report-templates",
        headers=_headers(token_a, org_a),
        json={
            "name": "A73 Template",
            "sections": ["executive_summary", "framework_readiness", "ai_governance_summary"],
            "framework_filter": [str(fw1.id)],
            "date_range_days": 90,
        },
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    list_resp = client.get("/api/v1/compliance/custom-report-templates", headers=_headers(token_a, org_a))
    assert list_resp.status_code == 200
    assert any(item["id"] == template_id for item in list_resp.json())

    generate_resp = client.post(
        f"/api/v1/compliance/custom-report-templates/{template_id}/generate",
        headers=_headers(token_a, org_a),
    )
    assert generate_resp.status_code == 200
    report_id = generate_resp.json()["report_id"]

    report_detail = client.get(f"/api/v1/reports/{report_id}", headers=_headers(token_a, org_a))
    assert report_detail.status_code == 200
    report_payload = report_detail.json()["report"]
    content = report_payload["content_json"]

    assert "executive_summary" in content
    assert "framework_readiness" in content
    assert "ai_governance_summary" in content

    readiness = content["framework_readiness"]
    assert len(readiness) == 1
    assert readiness[0]["framework_id"] == str(fw1.id)

    ai_summary = content["ai_governance_summary"]
    assert ai_summary["status"] == "not_configured"

    delete_resp = client.delete(
        f"/api/v1/compliance/custom-report-templates/{template_id}",
        headers=_headers(token_a, org_a),
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted_at"] is not None

    generate_deleted = client.post(
        f"/api/v1/compliance/custom-report-templates/{template_id}/generate",
        headers=_headers(token_a, org_a),
    )
    assert generate_deleted.status_code == 404

    isolation = client.get(
        f"/api/v1/compliance/custom-report-templates/{template_id}",
        headers=_headers(token_b, org_b),
    )
    assert isolation.status_code == 404
