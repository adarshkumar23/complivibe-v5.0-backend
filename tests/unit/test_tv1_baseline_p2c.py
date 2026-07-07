from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.models.compliance_baseline_run import ComplianceBaselineRun
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.inbound_questionnaire_item import InboundQuestionnaireItem
from app.models.organization_framework import OrganizationFramework
from app.platform.services.tv1_baseline_service import TV1BaselineService
from tests.helpers.auth_org import bootstrap_org_user


def _headers(token: str, org_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}


def test_tv1_baseline_start_generates_30_questions_collects_github_evidence(client, db_session, monkeypatch):
    ctx = bootstrap_org_user(client, email_prefix="tv1-p2c")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    token = ctx["access_token"]

    framework = Framework(
        code="SOC2_TV1",
        name="SOC2 TV1",
        version="2024",
        category="security",
        jurisdiction="US",
        authority="AICPA",
        description="TV1 framework",
        status="active",
    )
    db_session.add(framework)
    db_session.flush()
    db_session.add(
        OrganizationFramework(
            organization_id=org_id,
            framework_id=framework.id,
            status="active",
            activated_by_user_id=user_id,
        )
    )
    db_session.commit()

    generated_questions = [
        {
            "question_text": f"Question {idx + 1}: describe control coverage and evidence.",
            "question_type": "text",
            "category_tag": "baseline",
            "framework_ref": "SOC2_TV1",
        }
        for idx in range(30)
    ]

    def _fake_provider_chain(self, *, org_id, messages, failure_context):  # noqa: ANN001
        return json.dumps(generated_questions), "groq", False

    monkeypatch.setattr(AIProviderService, "_run_provider_chain", _fake_provider_chain)

    def _fake_github_get(self, *, base_url, path, token, params=None):  # noqa: ANN001
        if path.endswith("/repos"):
            return 200, [{"name": "repo-one", "default_branch": "main"}]
        if path.endswith("/branches/main/protection"):
            return 200, {"required_status_checks": {"strict": True}}
        if path.endswith("/dependabot/alerts"):
            return 200, [{"id": 1}, {"id": 2}]
        if path.endswith("/secret-scanning/alerts"):
            return 200, [{"id": 10}]
        return 200, {}

    monkeypatch.setattr(TV1BaselineService, "_github_get", _fake_github_get)

    response = client.post(
        "/api/v1/onboarding/baseline/24h/start",
        headers=_headers(token, ctx["organization_id"]),
        json={
            "framework_ids": [str(framework.id)],
            "github": {"owner": "example-org", "token": "ghp_example", "repo_limit": 5},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["integration_provider"] == "github"
    assert body["gap_report"]["intake_question_source"] in {"ai_groq", "ai_azure", "deterministic_fallback"}
    assert len(body["gap_report"]["integration_roadmap"]) == 2
    assert body["gap_report"]["github_collection_summary"]["evidence_items_created"] >= 1
    assert isinstance(body["gap_report"]["context_flags"], list)
    assert isinstance(body["context_flags"], list)
    assert "framework_coverage_summary" in body["gap_report"]
    assert "data_freshness" in body["gap_report"]
    assert "coverage_band" in body["gap_report"]
    assert "weakest_frameworks" in body["gap_report"]

    run_id = uuid.UUID(body["run_id"])
    run_row = db_session.query(ComplianceBaselineRun).filter(ComplianceBaselineRun.id == run_id).one()
    assert run_row.intake_session_id is not None

    question_count = (
        db_session.query(InboundQuestionnaireItem)
        .filter(
            InboundQuestionnaireItem.organization_id == org_id,
            InboundQuestionnaireItem.session_id == run_row.intake_session_id,
        )
        .count()
    )
    assert question_count == 30

    evidence_count = (
        db_session.query(EvidenceItem)
        .filter(
            EvidenceItem.organization_id == org_id,
            EvidenceItem.title.ilike("GitHub Security Snapshot:%"),
        )
        .count()
    )
    assert evidence_count >= 1


def test_tv1_baseline_start_rejects_missing_github_token(client):
    ctx = bootstrap_org_user(client, email_prefix="tv1-p2c-invalid")
    response = client.post(
        "/api/v1/onboarding/baseline/24h/start",
        headers={"Authorization": f"Bearer {ctx['access_token']}", "X-Organization-ID": ctx["organization_id"]},
        json={"framework_ids": [], "github": {"owner": "example-org", "token": ""}},
    )
    assert response.status_code in {422, 400}


def test_tv1_baseline_start_rejects_invalid_target_control_uuid(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="tv1-p2c-invalid-target")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])

    framework = Framework(
        code="SOC2_TV1_TARGET",
        name="SOC2 TV1 Target",
        version="2024",
        category="security",
        jurisdiction="US",
        authority="AICPA",
        description="TV1 framework target uuid",
        status="active",
    )
    db_session.add(framework)
    db_session.flush()
    db_session.add(
        OrganizationFramework(
            organization_id=org_id,
            framework_id=framework.id,
            status="active",
            activated_by_user_id=user_id,
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/onboarding/baseline/24h/start",
        headers=_headers(ctx["access_token"], ctx["organization_id"]),
        json={
            "framework_ids": [str(framework.id)],
            "github": {"owner": "example-org", "token": "ghp_example", "target_control_id": "not-a-uuid"},
        },
    )
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    if isinstance(detail, list):
        assert any(item.get("loc") == ["body", "github", "target_control_id"] for item in detail)
    else:
        assert "target_control_id" in str(detail)


def test_tv1_baseline_start_rejects_when_another_run_is_in_progress(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="tv1-p2c-running")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])

    framework = Framework(
        code="SOC2_TV1_RUNNING",
        name="SOC2 TV1 Running",
        version="2024",
        category="security",
        jurisdiction="US",
        authority="AICPA",
        description="TV1 framework running",
        status="active",
    )
    db_session.add(framework)
    db_session.flush()
    db_session.add(
        OrganizationFramework(
            organization_id=org_id,
            framework_id=framework.id,
            status="active",
            activated_by_user_id=user_id,
        )
    )
    db_session.add(
        ComplianceBaselineRun(
            organization_id=org_id,
            status="running",
            selected_framework_ids_json=[str(framework.id)],
            integration_provider="github",
            gap_report_json={},
            started_at=datetime.now(UTC),
            created_by=user_id,
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/onboarding/baseline/24h/start",
        headers=_headers(ctx["access_token"], ctx["organization_id"]),
        json={
            "framework_ids": [str(framework.id)],
            "github": {"owner": "example-org", "token": "ghp_example"},
        },
    )
    assert response.status_code == 409, response.text
    assert "already in progress" in response.json()["detail"]
