from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.control import Control
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/import"


def test_phase101_preview_and_commit_flag_duplicate_rows_and_skip_deterministically(client, db_session):
    org = bootstrap_org_user(client, email_prefix="import-p101-dup")
    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "update",
            "records": [
                {"entity_type": "control", "title": "Duplicate Control", "code": "DUP-1", "description": "first"},
                {"entity_type": "control", "title": "Duplicate Control", "code": "DUP-1", "description": "second"},
            ],
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    preview = client.post(f"{BASE}/{job_id}/dry-run-preview", headers=org["org_headers"])
    assert preview.status_code == 200
    p_body = preview.json()
    assert p_body["would_create"]["control"] == 1
    assert p_body["would_skip"]["control"] == 1
    assert "duplicate_rows_skipped" in p_body["context_flags"]
    assert p_body["insights"]["duplicate_row_count"] == 1

    commit = client.post(f"{BASE}/{job_id}/commit", headers=org["org_headers"])
    assert commit.status_code == 200
    c_body = commit.json()
    assert c_body["created"]["control"] == 1
    assert c_body["skipped"]["control"] == 1
    assert "rows_skipped" in c_body["context_flags"]
    assert c_body["insights"]["duplicate_row_count"] == 1

    controls = db_session.execute(
        select(Control).where(
            Control.organization_id == UUID(org["organization_id"]),
            Control.control_code == "DUP-1",
        )
    ).scalars().all()
    assert len(controls) == 1


def test_phase101_preview_flags_evidence_timestamp_anomaly(client):
    org = bootstrap_org_user(client, email_prefix="import-p101-time")
    create = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": True,
            "conflict_strategy": "skip",
            "records": [
                {
                    "entity_type": "evidence",
                    "title": "Anomalous Timestamp Evidence",
                    "evidence_type": "document",
                    "collected_at": "2026-01-01T00:00:00Z",
                    "original_created_at": "2026-02-01T00:00:00Z",
                }
            ],
        },
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    preview = client.post(f"{BASE}/{job_id}/dry-run-preview", headers=org["org_headers"])
    assert preview.status_code == 200
    body = preview.json()
    assert "evidence_timestamp_anomaly_detected" in body["context_flags"]
    assert body["insights"]["timestamp_anomaly_count"] == 1
    assert body["insights"]["estimated_success_rate_pct"] == 100.0


def test_phase101_commit_flags_no_material_changes_for_skip_strategy(client):
    org = bootstrap_org_user(client, email_prefix="import-p101-nochange")
    first = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "control", "title": "No Change Control", "code": "NC-1"}],
        },
    )
    assert first.status_code == 201
    assert client.post(f"{BASE}/{first.json()['id']}/commit", headers=org["org_headers"]).status_code == 200

    second = client.post(
        f"{BASE}/generic",
        headers=org["org_headers"],
        json={
            "dry_run": False,
            "conflict_strategy": "skip",
            "records": [{"entity_type": "control", "title": "No Change Control", "code": "NC-1"}],
        },
    )
    assert second.status_code == 201

    commit = client.post(f"{BASE}/{second.json()['id']}/commit", headers=org["org_headers"])
    assert commit.status_code == 200
    body = commit.json()
    assert body["created"] == {}
    assert body["updated"] == {}
    assert body["skipped"]["control"] == 1
    assert "no_material_changes" in body["context_flags"]
