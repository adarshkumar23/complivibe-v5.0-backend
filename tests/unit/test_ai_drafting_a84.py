from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select

from app.compliance.services.ai_drafting_service import AIDraftingService
from app.core.security import get_password_hash
from app.models.draft_request import DraftRequest
from app.models.membership import Membership
from app.models.org_ai_config import OrgAIConfig
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers


DRAFT_BASE = "/api/v1/compliance/drafts"
MOCK_DRAFT = "This is a mock AI draft response for testing."


def _create_active_user_with_role(db_session, org_id: str, *, email: str, role_name: str) -> User:
    role = db_session.execute(
        select(Role).where(
            Role.organization_id == uuid.UUID(org_id),
            Role.name == role_name,
        )
    ).scalar_one()
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
            invited_by=None,
        )
    )
    db_session.commit()
    return user


def test_a84_ai_drafting_endpoints_and_service(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="a84-owner")
    service = AIDraftingService(db_session)

    # AI disabled by default.
    blocked = client.post(
        f"{DRAFT_BASE}/policy-content",
        headers=org["org_headers"],
        json={
            "policy_type": "Information Security",
            "scope_description": "All systems",
            "framework_context": "SOC 2",
        },
    )
    assert blocked.status_code == 403
    assert "AI drafting is not enabled" in blocked.json()["detail"]

    # Admin required for enable/disable; compliance_manager is not admin.
    manager = _create_active_user_with_role(
        db_session,
        org["organization_id"],
        email="a84-manager@example.com",
        role_name="compliance_manager",
    )
    manager_token = login_user(client, manager.email)
    manager_headers = org_headers(manager_token, org["organization_id"])
    enable_forbidden = client.post(f"{DRAFT_BASE}/ai-config/enable", headers=manager_headers)
    assert enable_forbidden.status_code == 403

    enabled = client.post(f"{DRAFT_BASE}/ai-config/enable", headers=org["org_headers"])
    assert enabled.status_code == 200
    assert enabled.json()["ai_drafting_enabled"] is True

    monkeypatch.setattr(
        AIDraftingService,
        "_call_azure_openai",
        lambda self, system_prompt, user_prompt: MOCK_DRAFT,
    )

    created = client.post(
        f"{DRAFT_BASE}/policy-content",
        headers=org["org_headers"],
        json={
            "policy_type": "Information Security",
            "scope_description": "Production systems",
            "framework_context": "SOC 2, ISO 27001",
        },
    )
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["draft_output"] == MOCK_DRAFT
    assert created_body["applied"] is False
    assert created_body["model_used"] is not None
    assert created_body["prompt_used"] is not None

    created_id = created_body["id"]
    stored = db_session.execute(
        select(DraftRequest).where(DraftRequest.id == uuid.UUID(created_id))
    ).scalar_one()
    assert stored.draft_output == MOCK_DRAFT
    assert stored.applied is False
    assert stored.model_used is not None
    assert stored.prompt_used is not None

    # Unknown draft type blocked at service layer.
    with_exception = False
    try:
        service.create_draft(
            uuid.UUID(org["organization_id"]),
            "unknown_type",
            {"foo": "bar"},
            uuid.UUID(org["user_id"]),
        )
    except HTTPException as exc:
        with_exception = True
        assert exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert with_exception is True

    # Apply to a nonexistent policy is rejected with 404, not silently accepted.
    apply_missing = client.post(
        f"{DRAFT_BASE}/{created_id}/apply",
        headers=org["org_headers"],
        json={"target_entity_type": "policy", "target_entity_id": str(uuid.uuid4())},
    )
    assert apply_missing.status_code == 404

    # Create a real policy to apply the draft onto.
    policy_created = client.post(
        "/api/v1/compliance/policies",
        headers=org["org_headers"],
        json={
            "title": "Information Security Policy",
            "policy_type": "acceptable_use",
            "owner_user_id": org["user_id"],
        },
    )
    assert policy_created.status_code == 201
    policy_id = policy_created.json()["id"]

    # Apply once: content must be genuinely persisted as a policy version.
    applied = client.post(
        f"{DRAFT_BASE}/{created_id}/apply",
        headers=org["org_headers"],
        json={"target_entity_type": "policy", "target_entity_id": policy_id},
    )
    assert applied.status_code == 200
    applied_body = applied.json()
    assert applied_body["applied"] is True
    assert applied_body["applied_at"] is not None
    assert applied_body["applied_by"] == org["user_id"]

    versions = client.get(f"/api/v1/compliance/policies/{policy_id}/versions", headers=org["org_headers"])
    assert versions.status_code == 200
    version_bodies = versions.json()
    assert len(version_bodies) == 1
    version_detail = client.get(
        f"/api/v1/compliance/policies/{policy_id}/versions/{version_bodies[0]['id']}",
        headers=org["org_headers"],
    )
    assert version_detail.status_code == 200
    assert version_detail.json()["content_snapshot_json"]["content"] == MOCK_DRAFT

    # Apply twice blocked.
    applied_again = client.post(
        f"{DRAFT_BASE}/{created_id}/apply",
        headers=org["org_headers"],
        json={"target_entity_type": "policy", "target_entity_id": policy_id},
    )
    assert applied_again.status_code == 422

    # Create second draft and verify list filter by applied=False.
    second = client.post(
        f"{DRAFT_BASE}/risk-description",
        headers=org["org_headers"],
        json={
            "risk_title": "Unpatched endpoint",
            "risk_category": "Security",
            "linked_control_titles": ["Patch Management"],
        },
    )
    assert second.status_code == 201
    unapplied = client.get(f"{DRAFT_BASE}?applied=false", headers=org["org_headers"])
    assert unapplied.status_code == 200
    assert all(item["applied"] is False for item in unapplied.json())

    # API error maps to 502.
    def _raise_ai_error(self, system_prompt, user_prompt):
        _ = (system_prompt, user_prompt)
        raise Exception("simulated azure failure")

    monkeypatch.setattr(AIDraftingService, "_call_azure_openai", _raise_ai_error)
    ai_error = client.post(
        f"{DRAFT_BASE}/control-description",
        headers=org["org_headers"],
        json={"control_name": "Access Control"},
    )
    assert ai_error.status_code == 502

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="a84-orgb")
    list_org_b = client.get(f"{DRAFT_BASE}", headers=org_b["org_headers"])
    assert list_org_b.status_code == 200
    assert all(item["organization_id"] == org_b["organization_id"] for item in list_org_b.json())
    get_other = client.get(f"{DRAFT_BASE}/{second.json()['id']}", headers=org_b["org_headers"])
    assert get_other.status_code == 404

    # drafts:use permission required for creation (non-member against org header).
    outsider = bootstrap_org_user(client, email_prefix="a84-outsider")
    outsider_headers = {
        "Authorization": f"Bearer {outsider['access_token']}",
        "X-Organization-ID": org["organization_id"],
    }
    forbidden_create = client.post(
        f"{DRAFT_BASE}/evidence-description",
        headers=outsider_headers,
        json={"evidence_title": "Log Export"},
    )
    assert forbidden_create.status_code == 403

    # Disable endpoint works for admin and flips flag.
    disabled = client.post(f"{DRAFT_BASE}/ai-config/disable", headers=org["org_headers"])
    assert disabled.status_code == 200
    assert disabled.json()["ai_drafting_enabled"] is False

    cfg = db_session.execute(
        select(OrgAIConfig).where(OrgAIConfig.organization_id == uuid.UUID(org["organization_id"]))
    ).scalar_one()
    assert cfg.ai_drafting_enabled is False
