from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.models.ai_content_draft import AIContentDraft
from app.models.ai_draft_revision import AIDraftRevision
from app.models.ai_inline_suggestion import AIInlineSuggestion
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.subscription_plan import SubscriptionPlan
from app.platform.services.billing_service import BillingService
from tests.helpers.auth_org import bootstrap_org_user


def _set_org_plan(db_session, org_id: UUID, plan_code: str) -> None:
    BillingService(db_session).ensure_default_plans()
    plan = db_session.execute(select(SubscriptionPlan).where(SubscriptionPlan.plan_code == plan_code)).scalar_one()
    features = dict(plan.features or {})
    features["ai_policy_drafting"] = plan_code in {"growth", "enterprise"}
    plan.features = features

    org = db_session.get(Organization, org_id)
    assert org is not None
    org.subscription_status = "active"
    org.subscription_plan = plan_code
    db_session.commit()


def test_refine_draft_real_calls_revision_history_and_org_scoping(client, db_session):
    settings = get_settings()
    assert settings.GROQ_API_KEY, "GROQ_API_KEY must be set for real integration tests"

    owner_a = bootstrap_org_user(client, email_prefix="copilot-refine-a")
    org_a = UUID(owner_a["organization_id"])
    user_a = UUID(owner_a["user_id"])
    _set_org_plan(db_session, org_a, "growth")

    now = datetime.now(UTC)
    draft = AIContentDraft(
        organization_id=org_a,
        business_unit_id=None,
        content_type="policy",
        prompt_input="Draft an access control policy for engineering systems.",
        draft_output="Initial draft: access controls are required.",
        provider_used="groq",
        used_byo_credentials=False,
        status="draft",
        linked_policy_id=None,
        created_by=user_a,
        created_at=now,
        updated_at=now,
    )
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)

    refine_1 = client.post(
        f"/api/v1/compliance/draft/{draft.id}/refine",
        headers=owner_a["org_headers"],
        json={"refinement_instruction": "Include the exact literal token THREAD_MARKER_ALPHA in the final text."},
    )
    assert refine_1.status_code == 200, refine_1.text
    body_1 = refine_1.json()
    assert body_1["revision_number"] == 1
    assert body_1["provider_used"] == "groq"
    assert body_1["revised_output"].strip()

    row_1 = db_session.get(AIDraftRevision, UUID(body_1["revision_id"]))
    assert row_1 is not None
    assert row_1.draft_id == draft.id
    assert row_1.revision_number == 1

    refine_2 = client.post(
        f"/api/v1/compliance/draft/{draft.id}/refine",
        headers=owner_a["org_headers"],
        json={
            "refinement_instruction": (
                "Keep THREAD_MARKER_ALPHA in the text and add the exact literal token THREAD_MARKER_BETA."
            )
        },
    )
    assert refine_2.status_code == 200, refine_2.text
    body_2 = refine_2.json()
    assert body_2["revision_number"] == 2
    assert body_2["provider_used"] == "groq"
    revised_2 = body_2["revised_output"]
    assert revised_2.strip()
    assert "THREAD_MARKER_ALPHA" in revised_2
    assert "THREAD_MARKER_BETA" in revised_2

    revs = client.get(f"/api/v1/compliance/draft/{draft.id}/revisions", headers=owner_a["org_headers"])
    assert revs.status_code == 200, revs.text
    rev_items = revs.json()
    assert len(rev_items) == 2
    assert rev_items[0]["revision_number"] == 2
    assert rev_items[1]["revision_number"] == 1

    owner_b = bootstrap_org_user(client, email_prefix="copilot-refine-b")
    _set_org_plan(db_session, UUID(owner_b["organization_id"]), "growth")
    cross_refine = client.post(
        f"/api/v1/compliance/draft/{draft.id}/refine",
        headers=owner_b["org_headers"],
        json={"refinement_instruction": "Cross-org attempt"},
    )
    assert cross_refine.status_code == 404
    cross_get = client.get(f"/api/v1/compliance/draft/{draft.id}/revisions", headers=owner_b["org_headers"])
    assert cross_get.status_code == 404

    refined_logs = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_a,
            AuditLog.action == "ai_content.refined",
        )
    ).scalars().all()
    assert len(refined_logs) >= 2


def test_refine_draft_rejected_on_starter_plan(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="copilot-starter")
    org_id = UUID(owner["organization_id"])
    user_id = UUID(owner["user_id"])
    _set_org_plan(db_session, org_id, "starter")

    now = datetime.now(UTC)
    draft = AIContentDraft(
        organization_id=org_id,
        business_unit_id=None,
        content_type="policy",
        prompt_input="Draft policy",
        draft_output="Draft output",
        provider_used="groq",
        used_byo_credentials=False,
        status="draft",
        linked_policy_id=None,
        created_by=user_id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(draft)
    db_session.commit()
    db_session.refresh(draft)

    resp = client.post(
        f"/api/v1/compliance/draft/{draft.id}/refine",
        headers=owner["org_headers"],
        json={"refinement_instruction": "Add extra details"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "feature_not_in_plan"


def test_inline_suggestions_real_calls_for_policy_control_risk_and_status_updates(client, db_session):
    settings = get_settings()
    assert settings.GROQ_API_KEY, "GROQ_API_KEY must be set for real integration tests"

    owner = bootstrap_org_user(client, email_prefix="copilot-suggest")
    org_id = UUID(owner["organization_id"])
    _set_org_plan(db_session, org_id, "growth")

    policy_resp = client.post(
        "/api/v1/compliance/suggest",
        headers=owner["org_headers"],
        json={
            "content_type": "policy",
            "source_text": "All users should follow security policy and protect data.",
        },
    )
    assert policy_resp.status_code == 200, policy_resp.text
    policy_body = policy_resp.json()
    assert policy_body["provider_used"] == "groq"
    assert isinstance(policy_body["suggestions_json"], list)
    assert policy_body["suggestions_json"]
    first_item = policy_body["suggestions_json"][0]
    assert {"original_fragment", "suggested_replacement", "reasoning", "category"}.issubset(first_item.keys())

    control_resp = client.post(
        "/api/v1/compliance/suggest",
        headers=owner["org_headers"],
        json={
            "content_type": "control",
            "source_text": "Access reviews happen periodically.",
        },
    )
    assert control_resp.status_code == 200, control_resp.text
    assert control_resp.json()["content_type"] == "control"
    assert control_resp.json()["suggestions_json"]

    risk_resp = client.post(
        "/api/v1/compliance/suggest",
        headers=owner["org_headers"],
        json={
            "content_type": "risk",
            "source_text": "Unauthorized access could occur.",
        },
    )
    assert risk_resp.status_code == 200, risk_resp.text
    assert risk_resp.json()["content_type"] == "risk"
    assert risk_resp.json()["suggestions_json"]

    policy_suggestion_id = UUID(policy_body["id"])
    apply_resp = client.post(
        f"/api/v1/compliance/suggest/{policy_suggestion_id}/apply",
        headers=owner["org_headers"],
    )
    assert apply_resp.status_code == 200, apply_resp.text
    assert apply_resp.json()["status"] == "applied"
    applied_row = db_session.get(AIInlineSuggestion, policy_suggestion_id)
    assert applied_row is not None
    assert applied_row.status == "applied"

    control_suggestion_id = UUID(control_resp.json()["id"])
    dismiss_resp = client.post(
        f"/api/v1/compliance/suggest/{control_suggestion_id}/dismiss",
        headers=owner["org_headers"],
    )
    assert dismiss_resp.status_code == 200, dismiss_resp.text
    assert dismiss_resp.json()["status"] == "dismissed"
    dismissed_row = db_session.get(AIInlineSuggestion, control_suggestion_id)
    assert dismissed_row is not None
    assert dismissed_row.status == "dismissed"

    generated_log = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "ai_content.suggestions_generated",
        )
    ).scalars().first()
    assert generated_log is not None
    applied_log = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "ai_content.suggestion_applied",
        )
    ).scalars().first()
    assert applied_log is not None
    dismissed_log = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "ai_content.suggestion_dismissed",
        )
    ).scalars().first()
    assert dismissed_log is not None
