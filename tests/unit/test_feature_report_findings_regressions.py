"""Regressions for four findings surfaced by the feature-report code walk.

Each test pins the fixed behaviour so the original defect cannot silently return:

1. GET /api/v1/ai-governance/contracts served a manifest of the AI-governance API
   surface with no authentication dependency at all.
2. Whistleblower report bodies and thread messages were stored as plaintext, and the
   routes fell through to the loosest rate-limit bucket (api_general, 300/min).
3. AtlasAssessmentService.assess_system_exposure never read the system it was passed,
   so every AI system in every org received an identical fabricated score -- and the
   mutating POST that persists that score was gated on compliance:read.
4. GET /frameworks (and the other framework/obligation read endpoints) called
   SeedService.ensure_* and committed, so a read request wrote rows.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from app.core.rate_limiter import ENDPOINT_GROUP_DEFAULTS, CompliVibeRateLimiter
from app.models.ai_system import AISystem
from app.models.whistleblower import WhistleblowerMessage, WhistleblowerReport
from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers


def _user_with_role(db_session, organization_id: str, role_name: str) -> str:
    """Create an active member holding `role_name` and return their access token."""
    email = f"{role_name}-{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        full_name=role_name,
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()
    role = (
        db_session.query(Role)
        .filter(Role.organization_id == uuid.UUID(organization_id), Role.name == role_name)
        .one()
    )
    db_session.add(
        Membership(
            organization_id=uuid.UUID(organization_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return email


# --- 1. contracts endpoint authentication -----------------------------------------


def test_ai_governance_contracts_requires_authentication(client, db_session):
    """Previously returned 200 to a completely unauthenticated caller."""
    # Bare request: rejected before reaching the handler.
    bare = client.get("/api/v1/ai-governance/contracts")
    assert bare.status_code != 200, bare.text
    assert 400 <= bare.status_code < 500, bare.text

    # With a real organization but no credentials, this is specifically unauthorized
    # -- proving the rejection is an auth gate, not just a missing-header quirk.
    # Auth is httpOnly-cookie based, so bootstrapping leaves a live session on the
    # shared client; it has to be cleared or the request is genuinely authenticated.
    ctx = bootstrap_org_user(client)
    client.cookies.clear()
    unauthenticated = client.get(
        "/api/v1/ai-governance/contracts",
        headers={"X-Organization-ID": ctx["organization_id"]},
    )
    assert unauthenticated.status_code in (401, 403), unauthenticated.text


def test_ai_governance_contracts_served_to_permitted_caller(client, db_session):
    ctx = bootstrap_org_user(client)
    response = client.get(
        "/api/v1/ai-governance/contracts",
        headers=ctx["org_headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["pillar"].startswith("Pillar 2")


# --- 2. whistleblower encryption at rest + rate-limit bucket -----------------------


def test_whistleblower_report_body_is_encrypted_at_rest(client, db_session):
    ctx = bootstrap_org_user(client)
    disclosure = "The CFO approved a fabricated invoice on 2026-03-02."

    submit = client.post(
        "/api/v1/whistleblower/submit",
        json={
            "organization_id": ctx["organization_id"],
            "category": "fraud",
            "description": disclosure,
        },
    )
    assert submit.status_code == 201, submit.text
    tracking_code = submit.json()["tracking_code"]

    # The raw column must not contain the disclosure text.
    stored = db_session.execute(
        sa.select(WhistleblowerReport.description).where(
            WhistleblowerReport.organization_id == uuid.UUID(ctx["organization_id"])
        )
    ).scalar_one()
    assert disclosure not in stored
    assert stored != disclosure

    # ...but an authorised investigator still reads the real text back.
    report_id = db_session.execute(
        sa.select(WhistleblowerReport.id).where(
            WhistleblowerReport.organization_id == uuid.UUID(ctx["organization_id"])
        )
    ).scalar_one()
    detail = client.get(f"/api/v1/whistleblower/reports/{report_id}", headers=ctx["org_headers"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["description"] == disclosure

    # ...and so does the anonymous reporter via their tracking code.
    status_response = client.get(f"/api/v1/whistleblower/status/{tracking_code}")
    assert status_response.status_code == 200, status_response.text


def test_whistleblower_message_content_is_encrypted_at_rest(client, db_session):
    ctx = bootstrap_org_user(client)
    submit = client.post(
        "/api/v1/whistleblower/submit",
        json={
            "organization_id": ctx["organization_id"],
            "category": "harassment",
            "description": "Initial disclosure.",
        },
    )
    assert submit.status_code == 201, submit.text
    tracking_code = submit.json()["tracking_code"]

    secret_followup = "It also happened to a second named colleague."
    reply = client.post(
        f"/api/v1/whistleblower/status/{tracking_code}/reply",
        json={"content": secret_followup},
    )
    assert reply.status_code == 201, reply.text
    # The response echoes plaintext back to the reporter...
    assert reply.json()["content"] == secret_followup

    # ...while the stored column does not hold it.
    stored = db_session.execute(sa.select(WhistleblowerMessage.content)).scalars().all()
    assert stored, "expected a persisted message"
    assert all(secret_followup not in value for value in stored)

    # The reporter still reads their own thread back in plaintext.
    status_response = client.get(f"/api/v1/whistleblower/status/{tracking_code}")
    assert status_response.status_code == 200, status_response.text
    contents = [m["content"] for m in status_response.json()["messages"]]
    assert secret_followup in contents


def test_whistleblower_routes_use_the_tighter_public_rate_limit_bucket():
    """Previously fell through to api_general (300/min), the loosest bucket."""
    for path in (
        "/api/v1/whistleblower/submit",
        "/api/v1/whistleblower/status/sometrackingcode",
        "/api/v1/whistleblower/status/sometrackingcode/reply",
    ):
        assert CompliVibeRateLimiter.endpoint_group_for_path(path) == "public", path

    assert ENDPOINT_GROUP_DEFAULTS["public"] == "120/minute"
    # The bucket must stay strictly tighter than the general one.
    public_rate = int(ENDPOINT_GROUP_DEFAULTS["public"].split("/")[0])
    general_rate = int(ENDPOINT_GROUP_DEFAULTS["api_general"].split("/")[0])
    assert public_rate < general_rate


# --- 3. atlas scores the real system, and the mutating POST needs write ------------


def _make_ai_system(db_session, organization_id: str, **overrides) -> AISystem:
    defaults = dict(
        organization_id=uuid.UUID(organization_id),
        name=f"sys-{uuid.uuid4().hex[:8]}",
        system_type="model",
        lifecycle_status="active",
        deployment_status="development",
    )
    defaults.update(overrides)
    system = AISystem(**defaults)
    db_session.add(system)
    db_session.commit()
    return system


def test_atlas_score_varies_with_the_system_being_assessed(client, db_session):
    """Previously every system scored identically -- the system was never read."""
    ctx = bootstrap_org_user(client)

    low = _make_ai_system(
        db_session,
        ctx["organization_id"],
        system_type="use_case",
        deployment_status="development",
        risk_tier="minimal",
        human_oversight_level="human_in_command",
    )
    high = _make_ai_system(
        db_session,
        ctx["organization_id"],
        system_type="agent",
        deployment_status="production",
        risk_tier="high",
        human_oversight_level="full_automation",
        vendor_name="ThirdPartyCo",
        data_categories_json=["personal_data", "financial"],
    )

    low_response = client.post(
        f"/api/v1/ai-governance/systems/{low.id}/atlas-assessment", headers=ctx["org_headers"]
    )
    high_response = client.post(
        f"/api/v1/ai-governance/systems/{high.id}/atlas-assessment", headers=ctx["org_headers"]
    )
    assert low_response.status_code == 200, low_response.text
    assert high_response.status_code == 200, high_response.text

    low_score = low_response.json()["total_risk_score"]
    high_score = high_response.json()["total_risk_score"]

    # The core regression: two different systems must not score the same.
    assert low_score != high_score
    # And the ordering must be the sensible one.
    assert high_score > low_score

    # The derivation is disclosed rather than being an unexplained number.
    factors = high_response.json()["scoring_factors"]
    assert factors["system_type"] == "agent"
    assert factors["deployment_status"] == "production"
    assert factors["third_party_sourced"] is True
    assert factors["handles_declared_data"] is True

    # The persisted column reflects the computed score.
    db_session.expire_all()
    assert db_session.get(AISystem, high.id).atlas_risk_score == int(round(high_score))


def test_atlas_assessment_requires_a_write_permission(client, db_session):
    """The POST persists atlas_risk_score, so compliance:read must not be enough."""
    ctx = bootstrap_org_user(client)
    system = _make_ai_system(db_session, ctx["organization_id"])

    auditor_email = _user_with_role(db_session, ctx["organization_id"], "auditor")
    auditor_token = login_user(client, auditor_email)

    response = client.post(
        f"/api/v1/ai-governance/systems/{system.id}/atlas-assessment",
        headers=org_headers(auditor_token, ctx["organization_id"]),
    )
    assert response.status_code == 403, response.text


# --- 4. framework/obligation reads no longer write --------------------------------


def test_framework_read_endpoints_do_not_write(client, db_session):
    """GET /frameworks used to call SeedService.ensure_* and commit."""
    ctx = bootstrap_org_user(client)

    def _counts() -> tuple[int, int]:
        return (
            db_session.execute(sa.text("SELECT COUNT(*) FROM obligations")).scalar_one(),
            db_session.execute(sa.text("SELECT COUNT(*) FROM framework_versions")).scalar_one(),
        )

    # Clear the reference data the fixture seeded, then confirm a read does not
    # repopulate it -- which is exactly what the lazy seed-on-read used to do.
    db_session.execute(sa.text("DELETE FROM framework_versions"))
    db_session.execute(sa.text("DELETE FROM obligations"))
    db_session.commit()

    before = _counts()
    assert before == (0, 0)

    for path in ("/api/v1/frameworks", "/api/v1/frameworks/active"):
        response = client.get(path, headers=ctx["org_headers"])
        assert response.status_code == 200, f"{path}: {response.text}"

    db_session.expire_all()
    assert _counts() == before, "a read endpoint wrote reference rows"


def test_framework_catalog_read_still_serves_seeded_data(client, db_session, seeded_reference_data):
    """The catalogue is populated outside the read path, and reads still serve it."""
    ctx = bootstrap_org_user(client)
    response = client.get("/api/v1/frameworks", headers=ctx["org_headers"])
    assert response.status_code == 200, response.text
    assert len(response.json()) > 0, "catalogue should be seeded outside the read path"
