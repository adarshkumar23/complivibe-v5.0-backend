from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.ai_governance.services.ai_provider_service import AIProviderService
from app.core.config import get_settings
from app.models.ai_content_draft import AIContentDraft
from app.models.audit_log import AuditLog
from app.models.compliance_policy import CompliancePolicy
from app.models.organization import Organization
from app.models.organization_ai_configuration import OrganizationAIConfiguration
from app.models.subscription_plan import SubscriptionPlan
from app.platform.services.billing_service import BillingService
from tests.helpers.auth_org import bootstrap_org_user


def _set_org_plan(db_session, org_id: UUID, plan_code: str) -> None:
    BillingService(db_session).ensure_default_plans()
    plan = db_session.execute(select(SubscriptionPlan).where(SubscriptionPlan.plan_code == plan_code)).scalar_one()
    features = dict(plan.features or {})
    if plan_code == "starter":
        features["ai_policy_drafting"] = False
    else:
        features["ai_policy_drafting"] = True
    plan.features = features

    org = db_session.get(Organization, org_id)
    assert org is not None
    org.subscription_status = "active"
    org.subscription_plan = plan_code
    db_session.commit()


def test_policy_drafting_flow_with_plan_gating_and_audit(client, db_session, monkeypatch):
    growth = bootstrap_org_user(client, email_prefix="draft-growth")
    growth_org_id = UUID(growth["organization_id"])
    growth_user_id = UUID(growth["user_id"])
    _set_org_plan(db_session, growth_org_id, "growth")

    starter = bootstrap_org_user(client, email_prefix="draft-starter")
    starter_org_id = UUID(starter["organization_id"])
    _set_org_plan(db_session, starter_org_id, "starter")

    monkeypatch.setattr(
        AIProviderService,
        "draft_policy_content",
        lambda self, org_id, prompt_input, business_unit_id=None: (
            f"Generated policy draft for: {prompt_input}",
            "groq",
            False,
        ),
    )

    create_resp = client.post(
        "/api/v1/compliance/policies/draft",
        headers=growth["org_headers"],
        json={"prompt": "Draft an access control policy for engineering"},
    )
    assert create_resp.status_code == 200, create_resp.text
    draft_body = create_resp.json()
    assert "Generated policy draft" in draft_body["draft_output"]

    draft_id = UUID(draft_body["id"])
    draft_row = db_session.get(AIContentDraft, draft_id)
    assert draft_row is not None
    assert draft_row.status == "draft"

    starter_resp = client.post(
        "/api/v1/compliance/policies/draft",
        headers=starter["org_headers"],
        json={"prompt": "Draft any policy"},
    )
    assert starter_resp.status_code == 403
    assert starter_resp.json()["detail"]["error"] == "feature_not_in_plan"

    accept_resp = client.post(
        f"/api/v1/compliance/policies/draft/{draft_id}/accept",
        headers=growth["org_headers"],
        json={
            "title": "AI Drafted Access Control Policy",
            "owner_user_id": str(growth_user_id),
            "policy_type": "access_control",
            "description": "Policy accepted from draft",
        },
    )
    assert accept_resp.status_code == 200, accept_resp.text
    accept_body = accept_resp.json()
    policy_id = UUID(accept_body["linked_policy_id"])

    policy = db_session.get(CompliancePolicy, policy_id)
    assert policy is not None
    assert policy.ai_drafted is True
    assert policy.source_ai_draft_id == draft_id

    draft_row = db_session.get(AIContentDraft, draft_id)
    assert draft_row is not None
    assert draft_row.status == "accepted"
    assert draft_row.linked_policy_id == policy_id

    second_draft = client.post(
        "/api/v1/compliance/policies/draft",
        headers=growth["org_headers"],
        json={"prompt": "Draft a retention policy"},
    )
    assert second_draft.status_code == 200
    second_draft_id = UUID(second_draft.json()["id"])

    discard_resp = client.post(
        f"/api/v1/compliance/policies/draft/{second_draft_id}/discard",
        headers=growth["org_headers"],
    )
    assert discard_resp.status_code == 200

    discarded = db_session.get(AIContentDraft, second_draft_id)
    assert discarded is not None
    assert discarded.status == "discarded"

    owner_b = bootstrap_org_user(client, email_prefix="draft-other")
    _set_org_plan(db_session, UUID(owner_b["organization_id"]), "growth")

    cross_get = client.get(f"/api/v1/compliance/policies/draft/{second_draft_id}", headers=owner_b["org_headers"])
    assert cross_get.status_code == 404

    cross_accept = client.post(
        f"/api/v1/compliance/policies/draft/{second_draft_id}/accept",
        headers=owner_b["org_headers"],
        json={
            "title": "Cross Org Should Fail",
            "owner_user_id": owner_b["user_id"],
            "policy_type": "other",
        },
    )
    assert cross_accept.status_code == 404

    cross_discard = client.post(
        f"/api/v1/compliance/policies/draft/{second_draft_id}/discard",
        headers=owner_b["org_headers"],
    )
    assert cross_discard.status_code == 404

    drafted_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == growth_org_id,
            AuditLog.action == "ai_content.drafted",
        )
    ).scalars().first()
    assert drafted_audit is not None

    accepted_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == growth_org_id,
            AuditLog.action == "ai_content.accepted",
        )
    ).scalars().first()
    assert accepted_audit is not None

    discarded_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == growth_org_id,
            AuditLog.action == "ai_content.discarded",
        )
    ).scalars().first()
    assert discarded_audit is not None


def test_byo_and_platform_credential_resolution_and_config_redaction(client, db_session, monkeypatch):
    owner = bootstrap_org_user(client, email_prefix="draft-ai-config")
    org_id = UUID(owner["organization_id"])
    user_id = UUID(owner["user_id"])
    _set_org_plan(db_session, org_id, "growth")

    put_resp = client.put(
        "/api/v1/organizations/ai-configuration",
        headers=owner["org_headers"],
        json={
            "use_byo_credentials": True,
            "groq_api_key": "groq-byo-key",
            "azure_api_key": "azure-byo-key",
            "azure_endpoint": "https://example.azure.com/openai/v1",
            "azure_deployment_name": "gpt-4o",
            "is_active": True,
        },
    )
    assert put_resp.status_code == 200, put_resp.text
    body = put_resp.json()
    assert body["groq_api_key_configured"] is True
    assert body["azure_api_key_configured"] is True
    assert "groq_api_key" not in body
    assert "azure_api_key" not in body

    get_resp = client.get("/api/v1/organizations/ai-configuration", headers=owner["org_headers"])
    assert get_resp.status_code == 200
    get_body = get_resp.json()
    assert "groq_api_key" not in get_body
    assert "azure_api_key" not in get_body

    svc = AIProviderService(db_session)
    creds = svc.resolve_credentials(org_id)
    assert creds.use_byo_credentials is True
    assert creds.groq_api_key == "groq-byo-key"
    assert creds.azure_api_key == "azure-byo-key"

    row = db_session.execute(
        select(OrganizationAIConfiguration).where(OrganizationAIConfiguration.organization_id == org_id)
    ).scalar_one()
    row.use_byo_credentials = False
    db_session.commit()

    monkeypatch.setenv("GROQ_API_KEY", "platform-groq-key")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "platform-azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://platform.azure.com/openai/v1")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")

    # Cached settings can hold old values; clear cache before reading platform defaults.
    from app.core.config import get_settings

    get_settings.cache_clear()

    creds_platform = svc.resolve_credentials(org_id)
    assert creds_platform.use_byo_credentials is False
    assert creds_platform.groq_api_key == "platform-groq-key"
    assert creds_platform.azure_api_key == "platform-azure-key"


def test_real_groq_platform_default_policy_draft(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="draft-real-groq")
    org_id = UUID(owner["organization_id"])

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.GROQ_API_KEY, "GROQ_API_KEY must be set in .env for real integration test"

    # Ensure this org uses platform credentials, not BYO.
    row = db_session.execute(
        select(OrganizationAIConfiguration).where(OrganizationAIConfiguration.organization_id == org_id)
    ).scalar_one_or_none()
    if row is None:
        ts = datetime.now(UTC)
        row = OrganizationAIConfiguration(
            organization_id=org_id,
            use_byo_credentials=False,
            is_active=True,
            created_at=ts,
            updated_at=ts,
        )
        db_session.add(row)
    else:
        row.use_byo_credentials = False
        row.is_active = True
        row.groq_api_key_encrypted = None
        row.azure_api_key_encrypted = None
        row.updated_at = datetime.now(UTC)
    db_session.commit()

    svc = AIProviderService(db_session)
    draft_output, provider_used, used_byo = svc.draft_policy_content(
        org_id=org_id,
        prompt_input="Draft a one-paragraph data retention policy statement.",
    )

    assert provider_used == "groq"
    assert used_byo is False
    assert draft_output
    assert isinstance(draft_output, str)
    assert draft_output.strip()
    assert "placeholder" not in draft_output.lower()
    print(f"GROQ_REAL_OUTPUT: {draft_output}")


def test_real_azure_fallback_policy_draft(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="draft-real-azure")
    org_id = UUID(owner["organization_id"])

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.AZURE_OPENAI_API_KEY, "AZURE_OPENAI_API_KEY must be set in .env for real integration test"
    assert settings.AZURE_OPENAI_ENDPOINT, "AZURE_OPENAI_ENDPOINT must be set in .env for real integration test"
    assert settings.AZURE_OPENAI_DEPLOYMENT_NAME, (
        "AZURE_OPENAI_DEPLOYMENT_NAME must be set in .env for real integration test"
    )

    row = db_session.execute(
        select(OrganizationAIConfiguration).where(OrganizationAIConfiguration.organization_id == org_id)
    ).scalar_one_or_none()
    if row is None:
        ts = datetime.now(UTC)
        row = OrganizationAIConfiguration(
            organization_id=org_id,
            use_byo_credentials=False,
            is_active=True,
            created_at=ts,
            updated_at=ts,
        )
        db_session.add(row)
    else:
        row.use_byo_credentials = False
        row.is_active = True
        row.updated_at = datetime.now(UTC)
    db_session.commit()

    svc = AIProviderService(db_session)
    original_groq_url = svc.GROQ_URL
    svc.GROQ_URL = "https://127.0.0.1:1/force-groq-failure"
    try:
        draft_output, provider_used, used_byo = svc.draft_policy_content(
            org_id=org_id,
            prompt_input="Draft a one-paragraph third-party risk management policy statement.",
        )
    finally:
        svc.GROQ_URL = original_groq_url

    assert provider_used == "azure"
    assert used_byo is False
    assert draft_output
    assert isinstance(draft_output, str)
    assert draft_output.strip()
    assert "placeholder" not in draft_output.lower()
    print(f"AZURE_REAL_OUTPUT: {draft_output}")


def test_real_endpoint_groq_draft_persists_generated_text(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="draft-real-endpoint")
    org_id = UUID(owner["organization_id"])
    _set_org_plan(db_session, org_id, "growth")

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.GROQ_API_KEY, "GROQ_API_KEY must be set in .env for real endpoint integration test"

    # Force platform-default credential path for this org.
    row = db_session.execute(
        select(OrganizationAIConfiguration).where(OrganizationAIConfiguration.organization_id == org_id)
    ).scalar_one_or_none()
    if row is None:
        ts = datetime.now(UTC)
        row = OrganizationAIConfiguration(
            organization_id=org_id,
            use_byo_credentials=False,
            is_active=True,
            created_at=ts,
            updated_at=ts,
        )
        db_session.add(row)
    else:
        row.use_byo_credentials = False
        row.is_active = True
        row.groq_api_key_encrypted = None
        row.azure_api_key_encrypted = None
        row.updated_at = datetime.now(UTC)
    db_session.commit()

    resp = client.post(
        "/api/v1/compliance/policies/draft",
        headers=owner["org_headers"],
        json={"prompt": "Draft a one-paragraph access control policy statement."},
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body.get("id")
    assert isinstance(body.get("draft_output"), str)
    assert body["draft_output"].strip()

    draft_id = UUID(body["id"])
    persisted = db_session.get(AIContentDraft, draft_id)
    assert persisted is not None
    assert persisted.organization_id == org_id
    assert isinstance(persisted.draft_output, str)
    assert persisted.draft_output.strip()
    assert persisted.draft_output.strip() == body["draft_output"].strip()
    print(f"ENDPOINT_REAL_PERSISTED_OUTPUT: {persisted.draft_output}")
