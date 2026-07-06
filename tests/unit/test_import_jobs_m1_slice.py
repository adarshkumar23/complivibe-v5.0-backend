from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.import_job import ImportJob
from app.models.import_parity_tracking import ImportParityTracking
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/import"


def test_import_job_create_preview_and_row_level_parse_errors(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-job-preview")

    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": True,
            "conflict_strategy": "skip",
            "csv_content": "entity_type,title,description\ncontrol,Valid Control,ok\ncontrol,,missing title\n",
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    progress = client.get(f"{BASE}/{job_id}/progress", headers=org["org_headers"])
    assert progress.status_code == 200
    assert progress.json()["job"]["status"] == "failed"
    assert "row 3" in (progress.json()["job"]["error_summary"] or "")

    preview = client.post(f"{BASE}/{job_id}/dry-run-preview", headers=org["org_headers"])
    assert preview.status_code == 200
    body = preview.json()
    assert body["parsed_rows"] == 1
    assert len(body["row_errors"]) == 1
    assert body["row_errors"][0]["row"] == 3
    assert "Missing title/name" in body["row_errors"][0]["error"]


def test_import_job_commit_conflict_resolution_update(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-job-conflict")

    first = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "control", "code": "C-101", "title": "Access Control", "description": "v1"}],
        },
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    first_commit = client.post(f"{BASE}/{first_id}/commit", headers=org["org_headers"])
    assert first_commit.status_code == 200
    assert first_commit.json()["created"]["control"] == 1

    second = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "update",
            "records": [{"entity_type": "control", "code": "C-101", "title": "Access Control", "description": "v2"}],
        },
    )
    assert second.status_code == 201
    second_id = second.json()["id"]

    second_commit = client.post(f"{BASE}/{second_id}/commit", headers=org["org_headers"])
    assert second_commit.status_code == 200
    assert second_commit.json()["updated"]["control"] == 1

    row = db_session.execute(
        select(Control).where(
            Control.organization_id == UUID(org["organization_id"]),
            Control.control_code == "C-101",
        )
    ).scalar_one()
    assert row.description == "v2"
    assert row.source_import_tool == "generic"


def test_import_job_commit_evidence_uses_existing_evidence_table_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-job-evidence")
    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [
                {
                    "entity_type": "evidence",
                    "title": "SOC2 report",
                    "description": "Imported artifact",
                    "evidence_type": "document",
                    "collected_at": "2026-01-01T10:00:00Z",
                }
            ],
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    commit = client.post(f"{BASE}/{job_id}/commit", headers=org["org_headers"])
    assert commit.status_code == 200
    assert commit.json()["created"]["evidence"] == 1

    job_row = db_session.execute(
        select(ImportJob).where(
            ImportJob.id == UUID(job_id),
            ImportJob.organization_id == UUID(org["organization_id"]),
        )
    ).scalar_one()
    assert job_row.status == "completed"

    evidence_row = db_session.execute(
        select(EvidenceItem).where(
            EvidenceItem.organization_id == UUID(org["organization_id"]),
            EvidenceItem.title == "SOC2 report",
        )
    ).scalar_one()
    assert evidence_row.source == "imported"
    assert evidence_row.source_import_tool == "generic"

    audit_row = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "import.evidence.created",
        )
    ).scalar_one_or_none()
    assert audit_row is not None


def test_import_job_requires_auth(client):
    response = client.post(
        f"{BASE}/generic",
        json={
            "dry_run": True,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "control", "title": "X"}],
        },
    )
    assert response.status_code in (401, 403)


def test_import_job_preview_handles_non_object_source_rows_with_row_error(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-job-malformed")

    create = client.post(
        f"{BASE}/drata",
        headers=org["org_headers"],
        json={
            "dry_run": True,
            "conflict_strategy": "update",
            "source_payload": {
                "controls": [{"title": "Access Review", "code": "AC-01"}],
                "evidence": ["not-an-object"],
                "policies": [{"title": "Policy One", "policy_type": "security"}],
            },
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    preview = client.post(f"{BASE}/{job_id}/dry-run-preview", headers=org["org_headers"])
    assert preview.status_code == 200
    body = preview.json()
    assert body["parsed_rows"] == 2
    assert len(body["row_errors"]) == 1
    assert body["row_errors"][0]["error"] == "Drata evidence row must be an object"

    job = db_session.execute(select(ImportJob).where(ImportJob.id == UUID(job_id))).scalar_one()
    assert job.status == "failed"
    assert "Drata evidence row must be an object" in (job.error_summary or "")


def test_import_parity_dashboard_zero_expected_defaults_to_ready(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-parity-zero")
    response = client.get(f"{BASE}/parity-dashboard", headers=org["org_headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["threshold_pct"] == 95.0
    assert body["ready_to_switch"] is True
    assert body["overall"]["expected_count"] == 0
    assert body["overall"]["verified_count"] == 0
    assert body["overall"]["parity_pct"] == 100.0
    assert {row["entity_type"] for row in body["modules"]} == {"control", "evidence", "policy", "business_unit"}


def test_import_parity_dashboard_mixed_modules_uses_real_counts(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-parity-mixed")
    org_id = UUID(org["organization_id"])

    drata_job = client.post(
        f"{BASE}/drata",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "update",
            "source_payload": {
                "controls": [{"title": "Access Review", "code": "AC-01"}],
                "evidence": [{"title": "Access Review Evidence", "evidence_type": "document"}],
                "policies": [{"title": "Access Policy", "policy_type": "access_control"}],
            },
        },
    )
    assert drata_job.status_code == 201
    assert client.post(f"{BASE}/{drata_job.json()['id']}/commit", headers=org["org_headers"]).status_code == 200

    generic_job = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [
                {"entity_type": "control", "title": "Asset Inventory", "code": "ASSET-01"},
                {"entity_type": "business_unit", "title": "Engineering", "code": "ENG"},
            ],
        },
    )
    assert generic_job.status_code == 201
    assert client.post(f"{BASE}/{generic_job.json()['id']}/commit", headers=org["org_headers"]).status_code == 200

    evidence = db_session.execute(
        select(EvidenceItem).where(
            EvidenceItem.organization_id == org_id,
            EvidenceItem.title == "Access Review Evidence",
        )
    ).scalar_one()
    evidence.review_status = "verified"
    policy = db_session.execute(
        select(CompliancePolicy).where(
            CompliancePolicy.organization_id == org_id,
            CompliancePolicy.title == "Access Policy",
        )
    ).scalar_one()
    policy.status = "approved"
    db_session.flush()

    dashboard = client.get(f"{BASE}/parity-dashboard", headers=org["org_headers"])
    assert dashboard.status_code == 200
    payload = dashboard.json()

    module_map = {row["entity_type"]: row for row in payload["modules"]}
    assert module_map["control"]["expected_count"] == 2
    assert module_map["control"]["verified_count"] == 0
    assert module_map["evidence"]["expected_count"] == 1
    assert module_map["evidence"]["verified_count"] == 1
    assert module_map["policy"]["expected_count"] == 1
    assert module_map["policy"]["verified_count"] == 1
    assert module_map["business_unit"]["expected_count"] == 1
    assert module_map["business_unit"]["verified_count"] == 1

    assert payload["overall"]["expected_count"] == 5
    assert payload["overall"]["verified_count"] == 3
    assert payload["overall"]["parity_pct"] == 60.0
    assert payload["ready_to_switch"] is False

    tracking_rows = db_session.execute(
        select(ImportParityTracking).where(ImportParityTracking.organization_id == org_id)
    ).scalars().all()
    assert len(tracking_rows) >= 8

    parity_audits = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.entity_type == "import_parity_tracking",
            AuditLog.action.in_(["import.parity_tracking.created", "import.parity_tracking.updated"]),
        )
    ).scalars().all()
    assert parity_audits


def test_import_parity_dashboard_threshold_override(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-parity-threshold")
    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "control", "title": "Control Without Verified Evidence"}],
        },
    )
    assert create.status_code == 201
    assert client.post(f"{BASE}/{create.json()['id']}/commit", headers=org["org_headers"]).status_code == 200

    default_threshold = client.get(f"{BASE}/parity-dashboard", headers=org["org_headers"])
    assert default_threshold.status_code == 200
    assert default_threshold.json()["overall"]["parity_pct"] == 0.0
    assert default_threshold.json()["ready_to_switch"] is False

    lowered_threshold = client.get(f"{BASE}/parity-dashboard?threshold_pct=0", headers=org["org_headers"])
    assert lowered_threshold.status_code == 200
    assert lowered_threshold.json()["threshold_pct"] == 0.0
    assert lowered_threshold.json()["ready_to_switch"] is True
