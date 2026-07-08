from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.bribery_risk_assessment import BriberyRiskAssessment
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
BRIBERY_BASE = "/api/v1/vendors"


def _create_vendor(client, headers: dict[str, str], owner_user_id: str, *, name: str = "Acme Third Party", **overrides) -> dict:
    payload = {
        "name": name,
        "vendor_type": "software",
        "owner_user_id": owner_user_id,
        "risk_tier": "not_assessed",
        "status": "active",
    }
    payload.update(overrides)
    response = client.post(VENDORS_BASE, headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _high_risk_payload(**overrides):
    payload = {
        "jurisdiction": "Country X",
        "jurisdiction_cpi_score": 20,
        "pep_exposure": "direct",
        "gift_hospitality_log": [{"date": "2026-01-01", "description": "Gift", "value_usd": 1000}],
        "industry_category": "defense",
    }
    payload.update(overrides)
    return payload


def test_high_risk_assessment_flagged_for_enhanced_due_diligence(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-polish-high")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    resp = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json=_high_risk_payload(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["risk_tier"] == "high"
    assert any("high_risk_requires_enhanced_due_diligence" in f for f in body["context_flags"])
    assert any("first_assessment_for_vendor" in f for f in body["context_flags"])
    assert any("inconsistent_with_vendor_overall_risk_tier" in f for f in body["context_flags"])


def test_score_shift_flagged_between_assessments(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-polish-shift")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    low_resp = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={
            "jurisdiction": "Country Y",
            "jurisdiction_cpi_score": 95,
            "pep_exposure": "none",
            "gift_hospitality_log": [],
            "industry_category": "software",
        },
    )
    assert low_resp.status_code == 201, low_resp.text
    assert low_resp.json()["risk_tier"] == "low"

    high_resp = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json=_high_risk_payload(),
    )
    assert high_resp.status_code == 201, high_resp.text
    body = high_resp.json()
    assert body["score_delta_from_previous"] is not None
    assert body["score_delta_from_previous"] > 0.2
    assert any("risk_score_shifted_significantly_from_prior_assessment" in f for f in body["context_flags"])

    history_resp = client.get(f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/history", headers=org["org_headers"])
    assert history_resp.status_code == 200, history_resp.text
    history = history_resp.json()
    assert len(history) == 2
    # Oldest entry has no prior assessment to compare against.
    assert history[1]["score_delta_from_previous"] is None


def test_review_overdue_flag_for_stale_high_risk_assessment(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-polish-overdue")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    resp = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json=_high_risk_payload(),
    )
    assert resp.status_code == 201, resp.text
    assessment_id = resp.json()["id"]

    db_row = db_session.get(BriberyRiskAssessment, uuid.UUID(assessment_id))
    db_row.computed_at = datetime.now(timezone.utc) - timedelta(days=200)
    db_session.commit()

    detail = client.get(f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk", headers=org["org_headers"])
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["review_overdue"] is True
    assert any("review_overdue" in f for f in body["context_flags"])


def test_archived_vendor_assessment_flagged_moot(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-polish-archived")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    resp = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json=_high_risk_payload(),
    )
    assert resp.status_code == 201, resp.text

    archive_resp = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "Contract ended"},
    )
    assert archive_resp.status_code in (200, 201), archive_resp.text

    detail = client.get(f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk", headers=org["org_headers"])
    assert detail.status_code == 200, detail.text
    assert any("vendor_archived_assessment_may_be_moot" in f for f in detail.json()["context_flags"])


def test_low_risk_assessment_has_no_escalation_flags(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-polish-low")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], risk_tier="low")

    resp = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={
            "jurisdiction": "Country Y",
            "jurisdiction_cpi_score": 95,
            "pep_exposure": "none",
            "gift_hospitality_log": [],
            "industry_category": "software",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["risk_tier"] == "low"
    assert body["review_overdue"] is False
    assert not any("high_risk_requires_enhanced_due_diligence" in f for f in body["context_flags"])
    assert not any("inconsistent_with_vendor_overall_risk_tier" in f for f in body["context_flags"])
