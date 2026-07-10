from __future__ import annotations

from uuid import UUID

from app.mcp.read_only_queries import get_framework_status, get_obligation_counts, get_risk_summary
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user


def test_framework_status_and_obligation_counts_reflect_seeded_dpdp_framework(client, db_session):
    org = bootstrap_org_user(client, email_prefix="mcp-readonly")
    org_id = UUID(org["organization_id"])

    SeedService.ensure_dpdp_framework(db_session)
    db_session.commit()

    status = get_framework_status(db_session, org_id, "INDIA_DPDP")
    assert status["framework_code"] == "INDIA_DPDP"
    assert status["total_obligations"] >= 18

    counts = get_obligation_counts(db_session, org_id, "INDIA_DPDP")
    assert counts["total_obligations"] == status["total_obligations"]
    assert counts["framework_code"] == "INDIA_DPDP"


def test_framework_status_raises_for_unknown_framework_code(db_session):
    import pytest

    with pytest.raises(ValueError):
        get_framework_status(db_session, UUID(int=0), "NOT_A_REAL_FRAMEWORK")


def test_risk_summary_returns_org_posture(client, db_session):
    org = bootstrap_org_user(client, email_prefix="mcp-risk")
    org_id = UUID(org["organization_id"])

    summary = get_risk_summary(db_session, org_id)
    assert isinstance(summary, dict)
    assert "organization_id" in summary or len(summary) > 0
