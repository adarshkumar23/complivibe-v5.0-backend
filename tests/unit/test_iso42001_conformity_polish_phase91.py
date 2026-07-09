from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.iso42001_conformity_tracker import ISO42001ConformityTracker
from tests.helpers.auth_org import bootstrap_org_user

ISO42001_BASE = "/api/v1/ai-governance/iso42001"


def test_phase91_iso42001_tracker_context_and_summary_alias(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p91-iso42001")

    seeded = client.get(f"{ISO42001_BASE}/conformity-tracker", headers=org["org_headers"])
    assert seeded.status_code == 200
    assert len(seeded.json()) == 30

    update = client.post(
        f"{ISO42001_BASE}/conformity-tracker/4.1/update",
        headers=org["org_headers"],
        json={"implementation_status": "in_progress", "notes": "Scope drafted"},
    )
    assert update.status_code == 200
    assert update.json()["is_completed"] is False

    row = db_session.execute(
        select(ISO42001ConformityTracker).where(
            ISO42001ConformityTracker.organization_id == uuid.UUID(org["organization_id"]),
            ISO42001ConformityTracker.clause_ref == "4.1",
        )
    ).scalar_one()
    row.updated_at = datetime.now(UTC) - timedelta(days=45)
    db_session.add(row)
    db_session.commit()

    tracker = client.get(f"{ISO42001_BASE}/conformity-tracker", headers=org["org_headers"])
    assert tracker.status_code == 200
    stale_row = next(item for item in tracker.json() if item["clause_ref"] == "4.1")
    assert stale_row["stale_tracker"] is True
    assert "stale_tracker" in stale_row["context_flags"]
    assert "missing_evidence" in stale_row["context_flags"]

    summary = client.get(f"{ISO42001_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["completed_clauses"] == 0
    assert summary_body["stale_clauses"] >= 1
    assert "work_remaining" in summary_body["context_flags"]
    assert "stale_trackers_present" in summary_body["context_flags"]

    alias_summary = client.get(f"{ISO42001_BASE}/conformity-summary", headers=org["org_headers"])
    assert alias_summary.status_code == 200
    assert alias_summary.json() == summary_body


def test_phase91_iso42001_tracker_excludes_non_seeded_rows(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p91-iso42001-scope")

    seeded = client.get(f"{ISO42001_BASE}/conformity-tracker", headers=org["org_headers"])
    assert seeded.status_code == 200
    assert len(seeded.json()) == 30

    now = datetime.now(UTC)
    rogue = ISO42001ConformityTracker(
        organization_id=uuid.UUID(org["organization_id"]),
        clause_ref="99.9",
        implementation_status="verified",
        notes="legacy rogue row",
        evidence_id=None,
        updated_by=uuid.UUID(org["user_id"]),
        created_at=now,
        updated_at=now,
    )
    db_session.add(rogue)
    db_session.commit()

    tracker = client.get(f"{ISO42001_BASE}/conformity-tracker", headers=org["org_headers"])
    assert tracker.status_code == 200
    rows = tracker.json()
    assert len(rows) == 30
    assert all(item["clause_ref"] != "99.9" for item in rows)

    summary = client.get(f"{ISO42001_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    assert summary.json()["total_clauses"] == 30
