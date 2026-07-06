from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.import_job import ImportJob
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
