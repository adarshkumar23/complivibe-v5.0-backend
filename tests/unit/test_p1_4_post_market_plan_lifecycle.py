"""P1.4 regression: an EU-AI-Act post-market monitoring plan draft must be
readable and editable. The activation-grade completeness gate (metrics +
reporting frequency) belongs on activate, NOT on the read path -- previously
GET/PATCH/activate all ran the getter's completeness check, 422-ing any draft
and bricking the workflow with no way out of 'draft'.
"""
from __future__ import annotations

import uuid

from app.models.ai_system import AISystem
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/ai-governance/systems"


def _make_system(db_session, org_id: str, user_id: str) -> str:
    sysm = AISystem(
        organization_id=uuid.UUID(org_id),
        name="Post-market System",
        system_type="model",
        risk_tier="high",
        created_by=uuid.UUID(user_id),
        created_by_user_id=uuid.UUID(user_id),
    )
    db_session.add(sysm)
    db_session.commit()
    return str(sysm.id)


def test_post_market_plan_draft_is_readable_editable_and_gated_on_activate(client, db_session):
    org = bootstrap_org_user(client, email_prefix="pmp")
    h = org["org_headers"]
    system_id = _make_system(db_session, org["organization_id"], org["user_id"])

    # Create a legitimate draft with no metrics yet.
    created = client.post(
        f"{BASE}/{system_id}/post-market-plan",
        headers=h,
        json={"responsible_person_id": org["user_id"], "monitoring_metrics": [], "reporting_frequency": None},
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "draft"

    # GET must return the draft, not 422.
    got = client.get(f"{BASE}/{system_id}/post-market-plan", headers=h)
    assert got.status_code == 200, f"draft GET should succeed, got {got.status_code}: {got.text}"

    # Activation must still be gated on completeness.
    activate_incomplete = client.post(f"{BASE}/{system_id}/post-market-plan/activate", headers=h)
    assert activate_incomplete.status_code == 422, activate_incomplete.text

    # PATCH must let us add the missing metrics + frequency.
    patched = client.patch(
        f"{BASE}/{system_id}/post-market-plan",
        headers=h,
        json={"monitoring_metrics": [{"name": "accuracy", "threshold": 0.9}], "reporting_frequency": "quarterly"},
    )
    assert patched.status_code == 200, f"draft PATCH should succeed, got {patched.status_code}: {patched.text}"

    # Now activation succeeds.
    activated = client.post(f"{BASE}/{system_id}/post-market-plan/activate", headers=h)
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
