from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.compliance_baseline_run import ComplianceBaselineRun
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from tests.helpers.auth_org import bootstrap_org_user


def _headers(token: str, org_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}


def _make_framework(db_session, code: str) -> Framework:
    framework = Framework(
        code=code,
        name=f"Framework {code}",
        version="2024",
        category="security",
        jurisdiction="US",
        authority="Test Authority",
        description="Polish test framework",
        status="active",
    )
    db_session.add(framework)
    db_session.flush()
    return framework


def _make_obligation(db_session, framework: Framework, ref: str) -> Obligation:
    obligation = Obligation(
        framework_id=framework.id,
        reference_code=ref,
        title=f"Obligation {ref}",
        description="desc",
        obligation_type="control",
        jurisdiction="US",
        status="active",
    )
    db_session.add(obligation)
    db_session.flush()
    return obligation


def test_get_baseline_run_flags_obligations_changed_since_generation(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="tv1-polish-obl-changed")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])

    framework = _make_framework(db_session, "TV1_POLISH_A")
    db_session.add(
        OrganizationFramework(
            organization_id=org_id,
            framework_id=framework.id,
            status="active",
            activated_by_user_id=user_id,
        )
    )
    now = datetime.now(UTC)
    run = ComplianceBaselineRun(
        organization_id=org_id,
        status="completed",
        selected_framework_ids_json=[str(framework.id)],
        integration_provider="github",
        gap_report_json={
            "frameworks_in_scope": [str(framework.id)],
            "obligations_total": 0,
            "context_flags": [],
        },
        started_at=now - timedelta(hours=1),
        completed_at=now - timedelta(minutes=30),
        created_by=user_id,
    )
    db_session.add(run)
    db_session.commit()

    # New obligation appears after the baseline snapshot was generated.
    _make_obligation(db_session, framework, "TV1-POLISH-1")
    db_session.commit()

    response = client.get(
        f"/api/v1/onboarding/baseline/24h/{run.id}",
        headers=_headers(ctx["access_token"], ctx["organization_id"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["obligations_changed_since_generation"] is True
    assert "obligations_changed_since_generation" in body["context_flags"]
    assert body["is_latest_completed_run"] is True
    assert body["superseded_by_run_id"] is None


def test_get_baseline_run_flags_superseded_by_newer_run(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="tv1-polish-superseded")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])

    framework = _make_framework(db_session, "TV1_POLISH_B")
    db_session.add(
        OrganizationFramework(
            organization_id=org_id,
            framework_id=framework.id,
            status="active",
            activated_by_user_id=user_id,
        )
    )
    now = datetime.now(UTC)
    older_run = ComplianceBaselineRun(
        organization_id=org_id,
        status="completed",
        selected_framework_ids_json=[str(framework.id)],
        integration_provider="github",
        gap_report_json={"frameworks_in_scope": [str(framework.id)], "obligations_total": 0, "context_flags": []},
        started_at=now - timedelta(hours=30),
        completed_at=now - timedelta(hours=29),
        created_by=user_id,
    )
    newer_run = ComplianceBaselineRun(
        organization_id=org_id,
        status="completed",
        selected_framework_ids_json=[str(framework.id)],
        integration_provider="github",
        gap_report_json={"frameworks_in_scope": [str(framework.id)], "obligations_total": 0, "context_flags": []},
        started_at=now - timedelta(hours=2),
        completed_at=now - timedelta(hours=1),
        created_by=user_id,
    )
    db_session.add_all([older_run, newer_run])
    db_session.commit()

    response = client.get(
        f"/api/v1/onboarding/baseline/24h/{older_run.id}",
        headers=_headers(ctx["access_token"], ctx["organization_id"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_latest_completed_run"] is False
    assert body["superseded_by_run_id"] == str(newer_run.id)
    assert "superseded_by_newer_run" in body["context_flags"]
    assert "run_snapshot_older_than_24h" in body["context_flags"]

    # The latest run itself should not be flagged as superseded.
    response_latest = client.get(
        f"/api/v1/onboarding/baseline/24h/{newer_run.id}",
        headers=_headers(ctx["access_token"], ctx["organization_id"]),
    )
    assert response_latest.status_code == 200, response_latest.text
    latest_body = response_latest.json()
    assert latest_body["is_latest_completed_run"] is True
    assert latest_body["superseded_by_run_id"] is None


def test_get_baseline_run_flags_failed_run(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="tv1-polish-failed")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    now = datetime.now(UTC)

    run = ComplianceBaselineRun(
        organization_id=org_id,
        status="failed",
        selected_framework_ids_json=[],
        integration_provider="github",
        gap_report_json={},
        started_at=now - timedelta(minutes=10),
        failed_at=now - timedelta(minutes=5),
        failure_reason="github repos request failed: 401",
        created_by=user_id,
    )
    db_session.add(run)
    db_session.commit()

    response = client.get(
        f"/api/v1/onboarding/baseline/24h/{run.id}",
        headers=_headers(ctx["access_token"], ctx["organization_id"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert "run_failed" in body["context_flags"]
    assert body["run_age_hours"] is not None and body["run_age_hours"] >= 0


def test_get_baseline_run_org_scoping_returns_404_for_other_org(client, db_session):
    ctx_a = bootstrap_org_user(client, email_prefix="tv1-polish-scope-a")
    ctx_b = bootstrap_org_user(client, email_prefix="tv1-polish-scope-b")
    org_a_id = uuid.UUID(ctx_a["organization_id"])
    user_a_id = uuid.UUID(ctx_a["user_id"])
    now = datetime.now(UTC)

    run = ComplianceBaselineRun(
        organization_id=org_a_id,
        status="completed",
        selected_framework_ids_json=[],
        integration_provider="github",
        gap_report_json={},
        started_at=now - timedelta(hours=1),
        completed_at=now - timedelta(minutes=30),
        created_by=user_a_id,
    )
    db_session.add(run)
    db_session.commit()

    response = client.get(
        f"/api/v1/onboarding/baseline/24h/{run.id}",
        headers=_headers(ctx_b["access_token"], ctx_b["organization_id"]),
    )
    assert response.status_code == 404
