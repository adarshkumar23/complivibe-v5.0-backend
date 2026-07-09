from __future__ import annotations

import base64
import io
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.import_job import ImportJob
from app.models.import_parity_tracking import ImportParityTracking
from app.models.business_unit import BusinessUnit
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/import"


def _build_zip_base64(files: dict[str, str]) -> str:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return base64.b64encode(payload.getvalue()).decode()


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


def test_import_csv_surfaces_unmapped_columns_in_preview_and_commit(client, db_session):
    """G9 item 6: unrecognized CSV columns must be surfaced as a warning, not
    silently dropped without the user knowing.

    NOTE (G4 item 2 fix): status/owner/last_reviewed/criticality are now
    *recognized* CSV columns -- they're parsed and actually persisted onto the
    created/updated control (see test_import_csv_persists_status_owner_criticality_last_reviewed
    below) -- so they must no longer appear here. This test now uses columns
    that genuinely have no mapping to prove the "surface as a warning" behavior
    from G9 item 6 is still intact.
    """
    org = bootstrap_org_user(client, email_prefix="import-job-unmapped")

    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": True,
            "conflict_strategy": "skip",
            "csv_content": (
                "entity_type,title,description,region,cost_center\n"
                "control,Access Control Policy,desc here,EMEA,CC-100\n"
            ),
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    preview = client.post(f"{BASE}/{job_id}/dry-run-preview", headers=org["org_headers"])
    assert preview.status_code == 200
    assert sorted(preview.json()["unmapped_columns"]) == ["cost_center", "region"]

    commit = client.post(f"{BASE}/{job_id}/commit", headers=org["org_headers"])
    assert commit.status_code == 200
    assert sorted(commit.json()["unmapped_columns"]) == ["cost_center", "region"]


def test_import_csv_persists_status_owner_criticality_last_reviewed(client, db_session):
    """G4 item 2 regression test: importing a control CSV with status/owner/
    criticality/last_reviewed columns must actually persist those fields onto
    the created Control, not silently drop them."""
    org = bootstrap_org_user(client, email_prefix="import-job-control-fields")
    owner_email = org["email"]

    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "update",
            "csv_content": (
                "entity_type,title,status,owner,criticality,last_reviewed\n"
                f"control,Imported Field Test Control,implemented,{owner_email},high,2026-06-01T00:00:00Z\n"
            ),
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    preview = client.post(f"{BASE}/{job_id}/dry-run-preview", headers=org["org_headers"])
    assert preview.status_code == 200
    assert preview.json()["unmapped_columns"] == []

    commit = client.post(f"{BASE}/{job_id}/commit", headers=org["org_headers"])
    assert commit.status_code == 200
    assert commit.json()["created"] == {"control": 1}
    assert commit.json()["unmapped_columns"] == []

    control = db_session.execute(
        select(Control).where(Control.title == "Imported Field Test Control")
    ).scalar_one()
    assert control.status == "implemented"
    assert control.criticality == "high"
    assert control.owner_user_id is not None
    assert control.last_reviewed_at is not None


def test_import_csv_no_unmapped_columns_when_all_recognized(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-job-all-mapped")

    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": True,
            "conflict_strategy": "skip",
            "csv_content": "entity_type,title,description\ncontrol,Fully Recognized Control,ok\n",
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    preview = client.post(f"{BASE}/{job_id}/dry-run-preview", headers=org["org_headers"])
    assert preview.status_code == 200
    assert preview.json()["unmapped_columns"] == []


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


def test_g9_import_does_not_overwrite_manually_verified_evidence_provenance(client, db_session):
    """G9 item 17: an import match against a manually-entered, checksummed evidence
    item must not silently overwrite its source/description/checksum -- a
    manually-verified record's provenance must be protected."""
    org = bootstrap_org_user(client, email_prefix="import-job-provenance-manual")
    org_id = UUID(org["organization_id"])

    manual_evidence = EvidenceItem(
        organization_id=org_id,
        title="Manually Verified SOC2 Report",
        description="Original hand-entered description",
        evidence_type="document",
        source="manual",
        status="active",
        review_status="verified",
        freshness_status="current",
        checksum_sha256="real-checksum-abc123",
        metadata_json={},
    )
    db_session.add(manual_evidence)
    db_session.commit()
    db_session.refresh(manual_evidence)

    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "update",
            "records": [
                {
                    "entity_type": "evidence",
                    "title": "Manually Verified SOC2 Report",
                    "description": "OVERWRITTEN BY AUTOMATED IMPORT",
                    "evidence_type": "document",
                }
            ],
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    commit = client.post(f"{BASE}/{job_id}/commit", headers=org["org_headers"])
    assert commit.status_code == 200, commit.text
    body = commit.json()
    assert body["updated"] == {}
    assert body["skipped"].get("evidence") == 1
    assert body["provenance_protected_count"] == 1
    assert "provenance_protected_skip" in body["context_flags"]

    db_session.refresh(manual_evidence)
    assert manual_evidence.source == "manual"
    assert manual_evidence.description == "Original hand-entered description"
    assert manual_evidence.checksum_sha256 == "real-checksum-abc123"


def test_g9_import_still_updates_evidence_without_protected_provenance(client, db_session):
    """Sanity check: the provenance protection must not block genuinely-imported
    records (source != manual, no checksum) from updating normally."""
    org = bootstrap_org_user(client, email_prefix="import-job-provenance-normal")

    first = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "evidence", "title": "Vendor SOC2 Report", "description": "v1", "evidence_type": "document"}],
        },
    )
    assert first.status_code == 201
    first_commit = client.post(f"{BASE}/{first.json()['id']}/commit", headers=org["org_headers"])
    assert first_commit.status_code == 200
    assert first_commit.json()["created"]["evidence"] == 1

    second = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "update",
            "records": [{"entity_type": "evidence", "title": "Vendor SOC2 Report", "description": "v2", "evidence_type": "document"}],
        },
    )
    assert second.status_code == 201
    second_commit = client.post(f"{BASE}/{second.json()['id']}/commit", headers=org["org_headers"])
    assert second_commit.status_code == 200, second_commit.text
    assert second_commit.json()["updated"].get("evidence") == 1
    assert second_commit.json()["provenance_protected_count"] == 0

    row = db_session.execute(
        select(EvidenceItem).where(
            EvidenceItem.organization_id == UUID(org["organization_id"]),
            EvidenceItem.title == "Vendor SOC2 Report",
        )
    ).scalar_one()
    assert row.description == "v2"
    assert row.source == "imported"


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
                    "original_created_at": "2024-05-20T08:30:00Z",
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
    assert evidence_row.original_created_at == datetime(2024, 5, 20, 8, 30)

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


def test_import_job_commit_evidence_original_created_at_falls_back_to_collected_at(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-job-evidence-fallback")
    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [
                {
                    "entity_type": "evidence",
                    "title": "Fallback Evidence",
                    "evidence_type": "document",
                    "collected_at": "2025-02-14T09:00:00Z",
                }
            ],
        },
    )
    assert create.status_code == 201
    assert client.post(f"{BASE}/{create.json()['id']}/commit", headers=org["org_headers"]).status_code == 200

    evidence_row = db_session.execute(
        select(EvidenceItem).where(
            EvidenceItem.organization_id == UUID(org["organization_id"]),
            EvidenceItem.title == "Fallback Evidence",
        )
    ).scalar_one()
    assert evidence_row.original_created_at == datetime(2025, 2, 14, 9, 0)


def test_import_parity_dashboard_zero_expected_defaults_to_ready(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-parity-zero")
    response = client.get(f"{BASE}/parity-dashboard", headers=org["org_headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["threshold_pct"] == 95.0
    assert body["ready_to_switch"] is True
    assert body["generated_at"] is not None
    assert body["latest_import_job_at"] is None
    assert body["is_stale"] is False
    assert "no_expected_import_rows" in body["context_flags"]
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
    assert payload["latest_import_job_at"] is not None
    assert isinstance(payload["weakest_modules"], list)
    assert "module_parity_gaps_present" in payload["context_flags"]

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


def test_import_parity_dashboard_flags_stale_data(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-parity-stale")
    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "control", "title": "Old Control"}],
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]
    assert client.post(f"{BASE}/{job_id}/commit", headers=org["org_headers"]).status_code == 200

    job = db_session.execute(select(ImportJob).where(ImportJob.id == UUID(job_id))).scalar_one()
    old_ts = datetime.now(UTC) - timedelta(days=16)
    job.updated_at = old_ts
    db_session.flush()

    dashboard = client.get(f"{BASE}/parity-dashboard", headers=org["org_headers"])
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["is_stale"] is True
    assert body["data_age_hours"] is not None and body["data_age_hours"] >= (24 * 14)
    assert "parity_data_stale" in body["context_flags"]


def test_import_job_source_mappers_cover_all_five_sources(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-all-sources")
    org_id = UUID(org["organization_id"])

    vanta_create = client.post(
        f"{BASE}/vanta",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "source_payload": {
                "monitors": [{"name": "Vanta Monitor Control", "code": "VM-1", "description": "from monitor"}],
                "integrations": [{"name": "Vanta AWS Integration", "status": "pass"}],
                "policies": [{"name": "Vanta Policy", "policy_type": "security"}],
            },
        },
    )
    assert vanta_create.status_code == 201
    assert client.post(f"{BASE}/{vanta_create.json()['id']}/commit", headers=org["org_headers"]).status_code == 200

    drata_zip = _build_zip_base64(
        {
            "controls.csv": "name,control_code,description\nDrata Control,DR-1,from drata csv\n",
            "evidence.csv": "name,evidence_type,collected_at,created_at\nDrata Evidence,document,2026-03-10T12:00:00Z,2025-03-10T12:00:00Z\n",
            "policies.csv": "policy_name,policy_type,description\nDrata Policy,security,from drata policy export\n",
        }
    )
    drata_create = client.post(
        f"{BASE}/drata",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "source_payload": {"zip_base64": drata_zip},
        },
    )
    assert drata_create.status_code == 201
    assert client.post(f"{BASE}/{drata_create.json()['id']}/commit", headers=org["org_headers"]).status_code == 200

    sprinto_create = client.post(
        f"{BASE}/sprinto",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "csv_content": (
                "module,name,code,description\n"
                "entities,Sprinto Entity,SPR-ENG,Engineering org unit\n"
                "controls,Sprinto Access Control,SPR-C-1,Control from Sprinto export\n"
            ),
        },
    )
    assert sprinto_create.status_code == 201
    assert client.post(f"{BASE}/{sprinto_create.json()['id']}/commit", headers=org["org_headers"]).status_code == 200

    scrut_create = client.post(
        f"{BASE}/scrut",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "source_payload": {
                "entities": [{"name": "Scrut Entity", "code": "SCR-OPS"}],
                "controls": [{"name": "Scrut Control", "code": "SCR-C-1"}],
            },
        },
    )
    assert scrut_create.status_code == 201
    assert client.post(f"{BASE}/{scrut_create.json()['id']}/commit", headers=org["org_headers"]).status_code == 200

    generic_create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "policy", "title": "Generic Policy", "policy_type": "security"}],
        },
    )
    assert generic_create.status_code == 201
    assert client.post(f"{BASE}/{generic_create.json()['id']}/commit", headers=org["org_headers"]).status_code == 200

    controls = db_session.execute(select(Control).where(Control.organization_id == org_id)).scalars().all()
    policies = db_session.execute(select(CompliancePolicy).where(CompliancePolicy.organization_id == org_id)).scalars().all()
    evidence = db_session.execute(select(EvidenceItem).where(EvidenceItem.organization_id == org_id)).scalars().all()
    units = db_session.execute(select(BusinessUnit).where(BusinessUnit.organization_id == org_id)).scalars().all()

    assert {row.source_import_tool for row in controls} >= {"vanta", "drata", "sprinto", "scrut"}
    assert {row.source_import_tool for row in policies} >= {"vanta", "drata", "generic"}
    assert {row.source_import_tool for row in evidence} >= {"vanta", "drata"}
    assert {row.source_import_tool for row in units} >= {"sprinto", "scrut"}
    assert any(row.evidence_type == "technical_control_test_result" for row in evidence)


def test_import_job_drata_zip_corrupt_reports_clear_error(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-drata-zip-corrupt")
    create = client.post(
        f"{BASE}/drata",
        headers=org["org_headers"],
        json={
            "dry_run": True,
            "conflict_strategy": "skip",
            "source_payload": {"zip_base64": "not-valid-base64"},
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]
    progress = client.get(f"{BASE}/{job_id}/progress", headers=org["org_headers"])
    assert progress.status_code == 200
    assert progress.json()["job"]["status"] == "failed"
    assert "valid base64" in (progress.json()["job"]["error_summary"] or "")


def test_import_job_generic_csv_custom_column_map(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-generic-column-map")
    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "csv_content": (
                "kind,headline,details,ref_code,evidence_kind,observed_on\n"
                "evidence,CSV Named Evidence,mapped columns,E-77,screenshot,2026-02-01T00:00:00Z\n"
            ),
            "source_payload": {
                "column_map": {
                    "entity_type": "kind",
                    "title": "headline",
                    "description": "details",
                    "code": "ref_code",
                    "evidence_type": "evidence_kind",
                    "collected_at": "observed_on",
                }
            },
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]
    commit = client.post(f"{BASE}/{job_id}/commit", headers=org["org_headers"])
    assert commit.status_code == 200
    assert commit.json()["created"]["evidence"] == 1

    evidence_row = db_session.execute(
        select(EvidenceItem).where(
            EvidenceItem.organization_id == UUID(org["organization_id"]),
            EvidenceItem.title == "CSV Named Evidence",
        )
    ).scalar_one()
    assert evidence_row.evidence_type == "screenshot"
