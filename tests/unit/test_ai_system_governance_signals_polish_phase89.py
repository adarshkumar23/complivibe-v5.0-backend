import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.governance_signal import GovernanceSignal
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_signals_polish_phase79 import _seed_signal_flow


def test_phase89_signal_endpoints_reject_invalid_filter_choices(client):
    org = bootstrap_org_user(client, email_prefix="p89-filter")
    _seed_signal_flow(client, org["org_headers"])

    bad_list = client.get("/api/v1/ai-governance/signals?status=unknown", headers=org["org_headers"])
    assert bad_list.status_code == 400

    bad_prioritized = client.get("/api/v1/ai-governance/signals/prioritized?status=unknown", headers=org["org_headers"])
    assert bad_prioritized.status_code == 400

    bad_groups = client.get("/api/v1/ai-governance/signals/groups?status=unknown", headers=org["org_headers"])
    assert bad_groups.status_code == 400


def test_phase89_signals_expose_stale_assessment_context_and_summary_counts(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p89-stale-assessment")
    _seed_signal_flow(client, org["org_headers"])

    open_signal = db_session.execute(
        select(GovernanceSignal).where(
            GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]),
            GovernanceSignal.status == "open",
            GovernanceSignal.related_risk_assessment_id.is_not(None),
        )
    ).scalars().first()
    assert open_signal is not None
    assert open_signal.related_risk_assessment_id is not None

    assessment = db_session.get(AISystemRiskAssessment, open_signal.related_risk_assessment_id)
    assert assessment is not None
    assessment.updated_at = datetime.now(UTC) - timedelta(days=65)
    db_session.add(assessment)
    db_session.commit()

    listed = client.get("/api/v1/ai-governance/signals?status=open", headers=org["org_headers"])
    assert listed.status_code == 200
    row = next(item for item in listed.json() if item["id"] == str(open_signal.id))
    assert row["assessment_age_days"] >= 60
    assert row["stale_assessment_context"] is True
    assert row["status_age_days"] is not None
    assert "stale_assessment_context" in row["context_flags"]

    prioritized = client.get("/api/v1/ai-governance/signals/prioritized?status=open", headers=org["org_headers"])
    assert prioritized.status_code == 200
    prow = next(item for item in prioritized.json() if item["signal_id"] == str(open_signal.id))
    assert prow["assessment_age_days"] >= 60
    assert prow["stale_assessment_context"] is True
    assert prow["status_age_days"] is not None
    assert "stale_assessment_context" in prow["context_flags"]

    summary = client.get("/api/v1/ai-governance/signals/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    sbody = summary.json()
    assert sbody["open_signals_with_stale_assessment_context"] >= 1
    assert "stale_assessment_context_present" in sbody["context_flags"]
