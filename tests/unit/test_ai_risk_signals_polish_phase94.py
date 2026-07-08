from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.ai_risk_signal import AIRiskSignal
from app.models.ai_system import AISystem
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_signals_recs_diagnostics_a67_a68_a69 import SYSTEMS_BASE, _create_system


RISK_SIGNALS_BASE = "/api/v1/ai-governance/risk-signals"


def test_phase94_signal_context_enrichment_and_change_flags(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p94-signals")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "P94 Signals")

    status_change = client.post(
        f"{SYSTEMS_BASE}/{system_id}/status",
        headers=org["org_headers"],
        json={"new_status": "production"},
    )
    assert status_change.status_code == 200

    system_row = db_session.execute(
        select(AISystem).where(
            AISystem.organization_id == uuid.UUID(org["organization_id"]),
            AISystem.id == uuid.UUID(system_id),
        )
    ).scalar_one()

    signal_row = db_session.execute(
        select(AIRiskSignal).where(
            AIRiskSignal.organization_id == uuid.UUID(org["organization_id"]),
            AIRiskSignal.ai_system_id == uuid.UUID(system_id),
            AIRiskSignal.signal_type == "deployment_scope_expansion",
        )
    ).scalar_one()

    signal_row.detected_at = datetime.now(UTC) - timedelta(days=21)
    signal_row.updated_at = signal_row.detected_at
    system_row.updated_at = datetime.now(UTC)
    db_session.add(signal_row)
    db_session.add(system_row)
    db_session.commit()

    listed = client.get(f"{SYSTEMS_BASE}/{system_id}/risk-signals", headers=org["org_headers"])
    assert listed.status_code == 200
    row = next(item for item in listed.json() if item["id"] == str(signal_row.id))
    assert row["is_open"] is True
    assert row["needs_attention"] is True
    assert row["stale_signal"] is True
    assert row["signal_age_days"] >= 21
    assert row["system_deployment_status"] == "production"
    assert row["system_changed_since_detection"] is True
    assert "stale_signal" in row["context_flags"]
    assert "system_changed_since_detection" in row["context_flags"]


def test_phase94_signal_review_guards_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p94-signal-guard")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "P94 Signals Guard")

    status_change = client.post(
        f"{SYSTEMS_BASE}/{system_id}/status",
        headers=org["org_headers"],
        json={"new_status": "staging"},
    )
    assert status_change.status_code == 200

    signal_id = client.get(f"{SYSTEMS_BASE}/{system_id}/risk-signals", headers=org["org_headers"]).json()[0]["id"]

    reject_blank = client.post(
        f"{SYSTEMS_BASE}/{system_id}/risk-signals/{signal_id}/review",
        headers=org["org_headers"],
        json={"action": "dismiss", "notes": "   "},
    )
    assert reject_blank.status_code == 422

    dismissed = client.post(
        f"{SYSTEMS_BASE}/{system_id}/risk-signals/{signal_id}/review",
        headers=org["org_headers"],
        json={"action": "dismiss", "notes": "No longer relevant"},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    assert dismissed.json()["has_review_notes"] is True
    assert "review_notes_present" in dismissed.json()["context_flags"]

    terminal_block = client.post(
        f"{SYSTEMS_BASE}/{system_id}/risk-signals/{signal_id}/review",
        headers=org["org_headers"],
        json={"action": "acknowledge", "notes": "try mutate dismissed"},
    )
    assert terminal_block.status_code == 422

    audits = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "signal.reviewed",
            AuditLog.entity_id == uuid.UUID(signal_id),
        )
    ).scalars().all()
    assert len(audits) == 1


def test_phase94_signal_list_rejects_unknown_or_cross_org_system(client):
    org_a = bootstrap_org_user(client, email_prefix="p94-signal-list-a")
    org_b = bootstrap_org_user(client, email_prefix="p94-signal-list-b")
    system_b = _create_system(client, org_b["org_headers"], org_b["user_id"], "P94 Other Org")

    unknown = client.get(
        f"{RISK_SIGNALS_BASE}?system_id={uuid.uuid4()}",
        headers=org_a["org_headers"],
    )
    assert unknown.status_code == 404

    cross_org = client.get(
        f"{RISK_SIGNALS_BASE}?system_id={system_b}",
        headers=org_a["org_headers"],
    )
    assert cross_org.status_code == 404
