import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from app.models.governance_signal import GovernanceSignal
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_risk_classification_phase64 import (
    _create_ai_system,
    _create_assessment,
    _create_taxonomy,
)
from tests.unit.test_ai_system_risk_classification_review_signals_phase65 import _create_classification


def _seed_signal_flow(client, headers: dict[str, str]) -> tuple[dict, dict, dict]:
    ai = _create_ai_system(client, headers, name="P79-AI")
    assessment = _create_assessment(client, headers, ai["id"], risk_level="high")
    _create_taxonomy(client, headers, is_default=True)
    classification = _create_classification(client, headers, assessment["id"], confidence_level="low")
    submit = client.post(
        f"/api/v1/ai-governance/ai-risk/classifications/{classification['id']}/submit-for-review",
        headers=headers,
        json={},
    )
    assert submit.status_code == 200
    changes = client.post(
        f"/api/v1/ai-governance/ai-risk/classifications/{classification['id']}/request-changes",
        headers=headers,
        json={"change_request_note": "needs update"},
    )
    assert changes.status_code == 200
    rejected = client.post(
        f"/api/v1/ai-governance/ai-risk/classifications/{classification['id']}/reject",
        headers=headers,
        json={"rejection_reason": "insufficient support"},
    )
    assert rejected.status_code == 200
    return ai, assessment, classification


def test_phase79_signals_list_and_detail_include_priority_context_and_staleness(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p79-list")
    _seed_signal_flow(client, org["org_headers"])

    listed = client.get("/api/v1/ai-governance/signals?status=open", headers=org["org_headers"])
    assert listed.status_code == 200
    rows = listed.json()
    assert rows

    stale_target_id = uuid.UUID(rows[0]["id"])
    stale_row = db_session.get(GovernanceSignal, stale_target_id)
    assert stale_row is not None
    stale_row.created_at = stale_row.created_at - timedelta(days=45)
    stale_row.updated_at = stale_row.created_at
    db_session.add(stale_row)
    db_session.commit()

    listed_after = client.get("/api/v1/ai-governance/signals?status=open", headers=org["org_headers"])
    assert listed_after.status_code == 200
    body = listed_after.json()
    assert body
    for row in body:
        assert row["priority_score"] is not None
        assert row["priority_band"] in {"low", "medium", "high", "urgent"}
        assert isinstance(row["age_days"], int)
        assert isinstance(row["context_flags"], list)

    stale_body = next(row for row in body if row["id"] == str(stale_target_id))
    assert stale_body["stale_signal"] is True
    assert stale_body["age_days"] >= 45
    assert "stale_open_signal" in stale_body["context_flags"]

    detail = client.get(f"/api/v1/ai-governance/signals/{stale_target_id}", headers=org["org_headers"])
    assert detail.status_code == 200
    dbody = detail.json()
    assert dbody["priority_score"] is not None
    assert dbody["stale_signal"] is True
    assert "stale_open_signal" in dbody["context_flags"]


def test_phase79_signal_summary_includes_backlog_and_stale_context(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p79-summary")
    _seed_signal_flow(client, org["org_headers"])

    open_rows = list(
        db_session.execute(
            select(GovernanceSignal).where(
                GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]),
                GovernanceSignal.status == "open",
            )
        ).scalars()
    )
    assert open_rows
    open_rows[0].created_at = open_rows[0].created_at - timedelta(days=35)
    open_rows[0].updated_at = open_rows[0].created_at
    db_session.add(open_rows[0])
    db_session.commit()

    summary = client.get("/api/v1/ai-governance/signals/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    sbody = summary.json()
    assert sbody["open_signals"] == len(open_rows)
    assert sbody["stale_open_signals"] >= 1
    assert sbody["oldest_open_signal_age_days"] >= 35
    assert sbody["open_critical_signals"] >= 1
    assert sbody["open_high_or_urgent_priority_signals"] >= 1
    assert "stale_open_signals_present" in sbody["context_flags"]
    assert "critical_signal_backlog" in sbody["context_flags"]


def test_phase79_signal_actions_reject_blank_reason_and_trim_success_reason(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p79-reason")
    _seed_signal_flow(client, org["org_headers"])

    signal_row = db_session.execute(
        select(GovernanceSignal).where(
            GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]),
            GovernanceSignal.status == "open",
        )
    ).scalars().first()
    assert signal_row is not None
    signal_id = signal_row.id

    blank_resolve = client.post(
        f"/api/v1/ai-governance/signals/{signal_id}/resolve",
        headers=org["org_headers"],
        json={"reason": "   "},
    )
    assert blank_resolve.status_code == 400

    blank_dismiss = client.post(
        f"/api/v1/ai-governance/signals/{signal_id}/dismiss",
        headers=org["org_headers"],
        json={"reason": "\n\t"},
    )
    assert blank_dismiss.status_code == 400

    before_audit = int(
        db_session.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.organization_id == uuid.UUID(org["organization_id"]),
                AuditLog.action == "governance_signal.resolved",
            )
        ).scalar_one()
    )
    resolved = client.post(
        f"/api/v1/ai-governance/signals/{signal_id}/resolve",
        headers=org["org_headers"],
        json={"reason": "  manually addressed  "},
    )
    assert resolved.status_code == 200
    rbody = resolved.json()
    assert rbody["status"] == "resolved"
    assert rbody["resolve_reason"] == "manually addressed"

    stored = db_session.get(GovernanceSignal, signal_id)
    assert stored is not None
    assert stored.status == "resolved"
    assert stored.resolve_reason == "manually addressed"
    assert stored.resolved_at is not None
    assert stored.dismiss_reason is None
    assert stored.dismissed_at is None
    assert stored.dismissed_by_user_id is None

    after_audit = int(
        db_session.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.organization_id == uuid.UUID(org["organization_id"]),
                AuditLog.action == "governance_signal.resolved",
            )
        ).scalar_one()
    )
    assert after_audit == before_audit + 1
