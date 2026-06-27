from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.security import get_password_hash
from app.models.ai_system import AISystem
from app.models.eu_ai_act_classification import EUAIActClassification
from app.models.framework import Framework
from app.models.membership import Membership
from app.models.obligation import Obligation
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers


SYSTEMS_BASE = "/api/v1/ai-governance/systems"
REVIEWS_BASE = "/api/v1/ai-governance/reviews"


def _create_user_with_role(db_session, org_id: str, *, role_name: str, email: str) -> dict[str, str]:
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
    return {"id": str(user.id), "email": user.email}


def _create_system(client, headers: dict[str, str], owner_id: str, name: str = "AI System") -> str:
    res = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": "limited",
        },
    )
    assert res.status_code == 201
    return res.json()["id"]


def _full_responses_for_review(client, headers: dict[str, str], review_id: str) -> list[dict]:
    detail = client.get(f"{REVIEWS_BASE}/{review_id}", headers=headers)
    assert detail.status_code == 200
    criteria = detail.json()["criteria"]
    payload = {
        "responses": [
            {"criterion_key": row["criterion_key"], "response": "yes", "notes": "ok"}
            for row in criteria
        ]
    }
    resp = client.post(f"{REVIEWS_BASE}/{review_id}/respond", headers=headers, json=payload)
    assert resp.status_code == 200
    return criteria


def test_a54_review_workflow_and_four_eyes(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a54-owner")
    reviewer = _create_user_with_role(
        db_session,
        org["organization_id"],
        role_name="compliance_manager",
        email="a54-reviewer@example.com",
    )
    admin = _create_user_with_role(
        db_session,
        org["organization_id"],
        role_name="admin",
        email="a54-admin@example.com",
    )

    reviewer_headers = org_headers(login_user(client, reviewer["email"]), org["organization_id"])
    admin_headers = org_headers(login_user(client, admin["email"]), org["organization_id"])

    system_id = _create_system(client, org["org_headers"], org["user_id"], name="Review Target")

    create = client.post(
        REVIEWS_BASE,
        headers=org["org_headers"],
        json={
            "system_id": system_id,
            "review_type": "initial_approval",
            "assigned_reviewer_id": reviewer["id"],
        },
    )
    assert create.status_code == 201
    review_id = create.json()["id"]

    # Pre-populated criteria.
    detail = client.get(f"{REVIEWS_BASE}/{review_id}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert len(detail.json()["criteria"]) == 12

    # Four-eyes approval block for creator.
    same_user_approve = client.post(f"{REVIEWS_BASE}/{review_id}/approve", headers=org["org_headers"], json={})
    assert same_user_approve.status_code == 422

    # Partial response then approval blocked (all criteria required).
    first_key = detail.json()["criteria"][0]["criterion_key"]
    partial = client.post(
        f"{REVIEWS_BASE}/{review_id}/respond",
        headers=reviewer_headers,
        json={"responses": [{"criterion_key": first_key, "response": "yes", "notes": "done"}]},
    )
    assert partial.status_code == 200

    early_approve = client.post(f"{REVIEWS_BASE}/{review_id}/approve", headers=admin_headers, json={})
    assert early_approve.status_code == 422

    # Full response then approval.
    _full_responses_for_review(client, reviewer_headers, review_id)
    approved = client.post(
        f"{REVIEWS_BASE}/{review_id}/approve",
        headers=admin_headers,
        json={"decision_notes": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    # Reject path.
    review_reject = client.post(
        REVIEWS_BASE,
        headers=org["org_headers"],
        json={
            "system_id": system_id,
            "review_type": "periodic",
            "assigned_reviewer_id": reviewer["id"],
        },
    )
    assert review_reject.status_code == 201
    reject_id = review_reject.json()["id"]
    _full_responses_for_review(client, reviewer_headers, reject_id)
    rejected = client.post(
        f"{REVIEWS_BASE}/{reject_id}/reject",
        headers=admin_headers,
        json={"decision_notes": "not acceptable"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    # Conditional path.
    review_cond = client.post(
        REVIEWS_BASE,
        headers=org["org_headers"],
        json={
            "system_id": system_id,
            "review_type": "pre_deployment",
            "assigned_reviewer_id": reviewer["id"],
        },
    )
    assert review_cond.status_code == 201
    cond_id = review_cond.json()["id"]
    _full_responses_for_review(client, reviewer_headers, cond_id)
    conditional = client.post(
        f"{REVIEWS_BASE}/{cond_id}/approve-with-conditions",
        headers=admin_headers,
        json={"conditions": ["Complete DPIA", "Add human review gate"], "decision_notes": "conditional"},
    )
    assert conditional.status_code == 200
    assert conditional.json()["status"] == "conditional"
    completed = client.post(
        f"{REVIEWS_BASE}/{cond_id}/complete-conditional",
        headers=admin_headers,
        json={"notes": "conditions met"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "approved"


def test_a55_guided_and_manual_classification(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a55-owner")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="Classifier Target")

    start = client.post(f"{SYSTEMS_BASE}/{system_id}/classify/start", headers=org["org_headers"])
    assert start.status_code == 200
    assert len(start.json()["questions"]) == 9

    all_no_answers = {item["key"]: "no" for item in start.json()["questions"]}
    minimal = client.post(
        f"{SYSTEMS_BASE}/{system_id}/classify/submit",
        headers=org["org_headers"],
        json={"answers": all_no_answers},
    )
    assert minimal.status_code == 200
    assert minimal.json()["risk_tier"] == "minimal"
    assert minimal.json()["review_required_at"] is None

    high = client.post(
        f"{SYSTEMS_BASE}/{system_id}/classify/submit",
        headers=org["org_headers"],
        json={"answers": {"critical_infrastructure": "yes"}},
    )
    assert high.status_code == 200
    assert high.json()["risk_tier"] == "high"
    assert high.json()["review_required_at"] is not None

    prohibited = client.post(
        f"{SYSTEMS_BASE}/{system_id}/classify/submit",
        headers=org["org_headers"],
        json={"answers": {"manipulation": "yes"}},
    )
    assert prohibited.status_code == 200
    assert prohibited.json()["risk_tier"] == "prohibited"
    assert prohibited.json()["classification_basis"]["decision_path"]

    manual = client.post(
        f"{SYSTEMS_BASE}/{system_id}/classify/manual",
        headers=org["org_headers"],
        json={"risk_tier": "limited", "notes": "manual override"},
    )
    assert manual.status_code == 200
    assert manual.json()["risk_tier"] == "limited"
    assert manual.json()["classification_method"] == "manual"
    assert manual.json()["review_required_at"] is None

    system = db_session.execute(select(AISystem).where(AISystem.id == uuid.UUID(system_id))).scalar_one()
    assert system.risk_tier == "limited"

    get_classification = client.get(f"{SYSTEMS_BASE}/{system_id}/classification", headers=org["org_headers"])
    assert get_classification.status_code == 200

    controls = client.get(f"{SYSTEMS_BASE}/{system_id}/mandatory-controls", headers=org["org_headers"])
    assert controls.status_code == 200
    assert isinstance(controls.json()["mandatory_controls"], list)


def test_a56_eu_ai_act_classification_and_annex_seeding(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a56-owner")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="EU AI Target")

    annex = client.get(f"{SYSTEMS_BASE}/eu-act/annex-sectors", headers=org["org_headers"])
    assert annex.status_code == 200
    assert len(annex.json()) == 8

    # Seed an EU AI Act framework obligation in DB so obligations endpoint can return data.
    framework = db_session.execute(select(Framework).where(Framework.code == "EU_AI_ACT")).scalar_one_or_none()
    if framework is None:
        framework = Framework(
            code="EU_AI_ACT",
            name="EU AI Act",
            description="EU AI Act framework",
            category="AI Governance",
            jurisdiction="European Union",
            authority="EU",
            version="2024",
            status="active",
            coverage_level="starter",
        )
        db_session.add(framework)
        db_session.flush()

    ob = Obligation(
        framework_id=framework.id,
        reference_code="Art. 6",
        title="High-risk AI requirements",
        description="Requirements for high-risk systems",
        jurisdiction="European Union",
        status="active",
    )
    db_session.add(ob)
    db_session.commit()

    high_risk = client.post(
        f"{SYSTEMS_BASE}/{system_id}/eu-act-classification",
        headers=org["org_headers"],
        json={
            "article_category": "high_risk_annex3",
            "annex_reference": "III.2",
            "conformity_route": "self_assessment",
        },
    )
    assert high_risk.status_code == 200
    assert high_risk.json()["registration_required"] is True

    minimal = client.post(
        f"{SYSTEMS_BASE}/{system_id}/eu-act-classification",
        headers=org["org_headers"],
        json={"article_category": "minimal_risk"},
    )
    assert minimal.status_code == 200
    assert minimal.json()["registration_required"] is False

    # Upsert: still one row.
    count_rows = db_session.execute(
        select(func.count(EUAIActClassification.id)).where(
            EUAIActClassification.organization_id == uuid.UUID(org["organization_id"]),
            EUAIActClassification.ai_system_id == uuid.UUID(system_id),
        )
    ).scalar_one()
    assert int(count_rows) == 1

    obligations = client.get(f"{SYSTEMS_BASE}/{system_id}/eu-act-obligations", headers=org["org_headers"])
    assert obligations.status_code == 200
    assert isinstance(obligations.json(), list)

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="a56-orgb")
    iso = client.get(f"{SYSTEMS_BASE}/{system_id}/eu-act-classification", headers=org_b["org_headers"])
    assert iso.status_code == 404
