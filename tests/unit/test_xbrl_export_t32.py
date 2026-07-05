import uuid

from app.models.audit_log import AuditLog
from app.models.export_job import ExportJob


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
    response = client.post("/api/v1/reports/board-scorecard", headers=_headers(token, org_id))
    assert response.status_code == 200
    return response.json()["id"]


def test_t32_xbrl_export_generates_file_job_and_audit_log(client, db_session):
    token = _register(client, "t32-owner1@example.com", "Pass1234!@", "T32 XBRL Org1")
    org_id = _org_id(client, token)
    report_id = _create_report(client, token, org_id)

    response = client.post(
        f"/api/v1/reports/{report_id}/xbrl-export",
        headers=_headers(token, org_id),
        json={
            "entity_identifier": "T32-XBRL-ORG1",
            "data_points": [
                {
                    "name": "Climate transition plan description",
                    "taxonomy_concept": "ifrs-sds:ClimaterelatedTransitionPlanExplanatory",
                    "value": "Transition plan approved by the board with annual decarbonisation milestones.",
                    "period_start": "2026-01-01T00:00:00Z",
                    "period_end": "2026-12-31T00:00:00Z",
                },
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_status"] == "valid"
    assert payload["validation_errors"] == []
    assert payload["checksum_sha256"]
    assert payload["xbrl_content"].startswith("<?xml")
    assert "ClimaterelatedTransitionPlanExplanatory" in payload["xbrl_content"]
    assert "ifrs_sds_2024-04-26.xsd" in payload["xbrl_content"]
    assert "arelle" not in str(payload).lower()

    job = db_session.query(ExportJob).filter(ExportJob.id == uuid.UUID(payload["export_job_id"])).one()
    assert job.export_type == "compliance_report_xbrl"
    assert job.source_report_id == uuid.UUID(report_id)
    assert job.checksum_sha256 == payload["checksum_sha256"]

    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org_id),
            AuditLog.action == "report.exported_xbrl",
            AuditLog.entity_id == uuid.UUID(report_id),
        )
        .one()
    )
    assert audit.after_json["export_job_id"] == payload["export_job_id"]


def test_t32_xbrl_export_reports_exact_invalid_data_points_without_brand_leak(client):
    token = _register(client, "t32-owner2@example.com", "Pass1234!@", "T32 XBRL Org2")
    org_id = _org_id(client, token)
    report_id = _create_report(client, token, org_id)

    response = client.post(
        f"/api/v1/reports/{report_id}/xbrl-export",
        headers=_headers(token, org_id),
        json={
            "entity_identifier": "T32-XBRL-ORG2",
            "data_points": [
                {
                    "name": "Invalid concept",
                    "taxonomy_concept": "Scope1GreenhouseGasEmissions",
                    "value": 10,
                    "period_start": "2026-01-01T00:00:00Z",
                    "period_end": "2026-12-31T00:00:00Z",
                },
                {
                    "name": "Bad period",
                    "taxonomy_concept": "issb:ClimateTransitionPlanDescription",
                    "value": "Plan text",
                },
            ],
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["message"] == "XBRL validation failed"
    assert {"data_point_index": 0, "field": "taxonomy_concept", "message": "Taxonomy concept must use a prefix-qualified name such as issb:ClimateRelatedRisks."} in detail[
        "validation_errors"
    ]
    assert {"data_point_index": 0, "field": "unit", "message": "Numeric data points require a unit."} in detail["validation_errors"]
    assert {"data_point_index": 1, "field": "period", "message": "Provide either instant or both period_start and period_end."} in detail[
        "validation_errors"
    ]
    assert "arelle" not in str(response.json()).lower()


def test_t32_xbrl_export_returns_service_error_when_taxonomy_source_unreachable(client):
    token = _register(client, "t32-owner3@example.com", "Pass1234!@", "T32 XBRL Org3")
    org_id = _org_id(client, token)
    report_id = _create_report(client, token, org_id)

    response = client.post(
        f"/api/v1/reports/{report_id}/xbrl-export",
        headers=_headers(token, org_id),
        json={
            "entity_identifier": "T32-XBRL-ORG3",
            "taxonomy_schema_url": "https://xbrl.ifrs.org/taxonomy/2024-04-30/issb.xsd",
            "data_points": [
                {
                    "name": "Climate transition plan description",
                    "taxonomy_concept": "ifrs-sds:ClimaterelatedTransitionPlanExplanatory",
                    "value": "Transition plan approved by the board with annual decarbonisation milestones.",
                    "period_start": "2026-01-01T00:00:00Z",
                    "period_end": "2026-12-31T00:00:00Z",
                },
            ],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["message"] == "XBRL taxonomy source unreachable"
    assert "arelle" not in str(response.json()).lower()


def test_t32_xbrl_export_rejects_internal_taxonomy_schema_url_ssrf(client):
    """taxonomy_schema_url is caller-supplied and fetched server-side; it must not be
    usable to reach loopback/private/link-local addresses (SSRF)."""
    token = _register(client, "t32-owner4@example.com", "Pass1234!@", "T32 XBRL Org4")
    org_id = _org_id(client, token)
    report_id = _create_report(client, token, org_id)

    for bad_url in [
        "http://127.0.0.1:8000/internal.xsd",
        "http://localhost/internal.xsd",
        "http://169.254.169.254/latest/meta-data/",
        "ftp://xbrl.ifrs.org/taxonomy.xsd",
    ]:
        response = client.post(
            f"/api/v1/reports/{report_id}/xbrl-export",
            headers=_headers(token, org_id),
            json={
                "entity_identifier": "T32-XBRL-ORG4",
                "taxonomy_schema_url": bad_url,
                "data_points": [
                    {
                        "name": "Climate transition plan description",
                        "taxonomy_concept": "ifrs-sds:ClimaterelatedTransitionPlanExplanatory",
                        "value": "Transition plan approved by the board.",
                        "period_start": "2026-01-01T00:00:00Z",
                        "period_end": "2026-12-31T00:00:00Z",
                    },
                ],
            },
        )
        assert response.status_code == 422, (bad_url, response.text)
        detail = response.json()["detail"]
        assert detail["message"] == "XBRL validation failed"
        assert any(err["field"] == "taxonomy_schema_url" for err in detail["validation_errors"]), (bad_url, detail)
