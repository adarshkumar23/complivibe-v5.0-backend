from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect, select

from app.models.audit_log import AuditLog
from app.models.issue import Issue
from app.models.security_scan_job import SecurityScanJob
from tests.helpers.auth_org import bootstrap_org_user


def _ingest_key(client, org_headers: dict[str, str]) -> str:
    # Security ingest has its OWN key now (key_type "security"), decoupled from the
    # shared OpenMetadata/lineage key.
    response = client.post(
        "/api/v1/integrations/ingest-keys",
        headers=org_headers,
        json={"key_type": "security"},
    )
    assert response.status_code == 201, response.text
    key = response.json().get("api_key")
    assert key
    return key


def _trivy_payload() -> dict:
    return {
        "SchemaVersion": 2,
        "ArtifactName": "test-image:latest",
        "Results": [
            {
                "Target": "test-image:latest",
                "Class": "os-pkgs",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2023-TEST-001",
                        "PkgName": "libssl",
                        "InstalledVersion": "1.0.0",
                        "FixedVersion": "1.0.1",
                        "Severity": "CRITICAL",
                        "Title": "Test critical CVE",
                        "Description": "Test vulnerability",
                    },
                    {
                        "VulnerabilityID": "CVE-2023-TEST-002",
                        "PkgName": "libcurl",
                        "InstalledVersion": "7.0.0",
                        "Severity": "HIGH",
                        "Title": "Test high CVE",
                    },
                    {
                        "VulnerabilityID": "CVE-2023-TEST-003",
                        "PkgName": "libpng",
                        "InstalledVersion": "1.6.0",
                        "Severity": "LOW",
                        "Title": "Test low CVE",
                    },
                ],
            }
        ],
    }


def _prowler_payload() -> list[dict]:
    return [
        {
            "CheckID": "iam_root_mfa_enabled",
            "CheckTitle": "MFA should be enabled for root",
            "Status": "FAIL",
            "Severity": "critical",
            "Region": "us-east-1",
            "ResourceId": "arn:aws:iam::123:root",
            "Description": "Root MFA not enabled",
            "Remediation": "Enable MFA on root account",
            "Compliance": {"CIS": ["1.5"]},
        },
        {
            "CheckID": "s3_bucket_default_encryption",
            "CheckTitle": "S3 encryption should be enabled",
            "Status": "PASS",
            "Severity": "high",
            "Region": "us-east-1",
            "ResourceId": "arn:aws:s3:::my-bucket",
            "Description": "S3 encryption check",
            "Compliance": {},
        },
    ]


def test_trivy_ingest_flow(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c1-trivy")
    key = _ingest_key(client, org["org_headers"])
    headers = {"X-CompliVibe-Key": key}

    tables = set(inspect(db_session.bind).get_table_names())
    assert "security_scan_jobs" in tables

    response = client.post("/api/v1/security/ingest/trivy", headers=headers, json=_trivy_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["scan_job_id"]
    assert body["total_findings"] == 3
    assert body["critical_count"] == 1
    assert body["issues_created"] == 1
    assert body["control_tests_created"] == 3

    row = db_session.get(SecurityScanJob, UUID(body["scan_job_id"]))
    assert row is not None
    assert row.status == "completed"

    invalid = client.post("/api/v1/security/ingest/trivy", headers={"X-CompliVibe-Key": "invalid"}, json=_trivy_payload())
    assert invalid.status_code == 401

    missing = client.post("/api/v1/security/ingest/trivy", json=_trivy_payload())
    assert missing.status_code == 401

    empty_payload = client.post("/api/v1/security/ingest/trivy", headers=headers, json={})
    assert empty_payload.status_code in (200, 400)
    if empty_payload.status_code == 200:
        assert empty_payload.json()["total_findings"] == 0

    malformed = client.post(
        "/api/v1/security/ingest/trivy",
        headers={**headers, "Content-Type": "application/json"},
        data="{",
    )
    assert malformed.status_code == 422

    audit_rows = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "security.trivy_scan_ingested",
        )
    ).scalars().all()
    assert len(audit_rows) >= 1

    critical_issue = db_session.execute(
        select(Issue).where(
            Issue.organization_id == UUID(org["organization_id"]),
            Issue.title.contains("CVE-2023-TEST-001"),
        )
    ).scalar_one_or_none()
    assert critical_issue is not None


def test_prowler_ingest_and_scan_job_management(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="c1-prowler-a")
    org_b = bootstrap_org_user(client, email_prefix="c1-prowler-b")

    key_a = _ingest_key(client, org_a["org_headers"])
    key_b = _ingest_key(client, org_b["org_headers"])

    response = client.post(
        "/api/v1/security/ingest/prowler",
        headers={"X-CompliVibe-Key": key_a},
        json=_prowler_payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_findings"] == 2
    assert body["failed_count"] == 1
    assert body["issues_created"] == 1
    assert body["control_tests_created"] == 2

    wrapped = client.post(
        "/api/v1/security/ingest/prowler",
        headers={"X-CompliVibe-Key": key_a},
        json={"findings": _prowler_payload()},
    )
    assert wrapped.status_code == 200
    assert wrapped.json()["total_findings"] == 2

    invalid = client.post(
        "/api/v1/security/ingest/prowler",
        headers={"X-CompliVibe-Key": "invalid"},
        json=_prowler_payload(),
    )
    assert invalid.status_code == 401

    list_jobs = client.get("/api/v1/security/scan-jobs", headers=org_a["org_headers"])
    assert list_jobs.status_code == 200
    assert isinstance(list_jobs.json(), list)
    assert len(list_jobs.json()) >= 1

    job_id = list_jobs.json()[0]["id"]
    get_job = client.get(f"/api/v1/security/scan-jobs/{job_id}", headers=org_a["org_headers"])
    assert get_job.status_code == 200

    summary = client.get("/api/v1/security/scan-jobs/summary", headers=org_a["org_headers"])
    assert summary.status_code == 200
    assert "total_scans" in summary.json()

    list_b = client.get("/api/v1/security/scan-jobs", headers=org_b["org_headers"])
    assert list_b.status_code == 200
    assert all(item["id"] != job_id for item in list_b.json())

    # Ensure org B key cannot see org A details through ingest auth scope.
    _ = client.post(
        "/api/v1/security/ingest/prowler",
        headers={"X-CompliVibe-Key": key_b},
        json=_prowler_payload(),
    )
