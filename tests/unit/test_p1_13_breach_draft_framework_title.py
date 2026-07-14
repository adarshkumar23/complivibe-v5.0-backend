"""P1.13 regression: the breach-notification draft must reflect the breach's
actual regulatory_framework. Previously the deterministic template (and the AI
prompts) hardcoded "GDPR Article 33" even for a DPDP-framework breach, which is
wrong -- DPDP (India) reports to the Data Protection Board, not under GDPR
Article 33.
"""
from __future__ import annotations

ISSUES_BASE = "/api/v1/compliance/issues"
BREACH_BASE = "/api/v1/compliance/breach-notifications"

from tests.helpers.auth_org import bootstrap_org_user


def _breach(client, h, owner_id, framework):
    issue = client.post(
        ISSUES_BASE,
        headers=h,
        json={"title": "Breach issue", "description": "Unauthorized access to customer records",
              "issue_type": "security_incident", "severity": "high",
              "source_type": "manual", "owner_id": owner_id},
    )
    assert issue.status_code == 201, issue.text
    created = client.post(
        f"{ISSUES_BASE}/{issue.json()['id']}/breach-notification",
        headers=h,
        json={
            "breach_type": "personal_data",
            "personal_data_affected": True,
            "regulatory_notification_required": True,
            "regulatory_framework": framework,
            "regulatory_notification_hours": 72,
            "supervisory_authority": "Data Protection Board of India",
            "subject_notification_required": True,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_dpdp_breach_draft_does_not_say_gdpr(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p1-13-dpdp")
    h = org["org_headers"]
    breach_id = _breach(client, h, org["user_id"], "dpdp")

    draft = client.post(f"{BREACH_BASE}/{breach_id}/generate-article33-draft", headers=h)
    assert draft.status_code == 200, draft.text
    text = draft.json()["draft_text"]
    assert "GDPR" not in text, f"DPDP breach draft must not mention GDPR; got: {text[:120]}"
    assert "DPDP" in text or "Data Protection Board" in text, f"draft should reference DPDP; got: {text[:120]}"


def test_gdpr_breach_draft_unchanged(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p1-13-gdpr")
    h = org["org_headers"]
    breach_id = _breach(client, h, org["user_id"], "gdpr")

    draft = client.post(f"{BREACH_BASE}/{breach_id}/generate-article33-draft", headers=h)
    assert draft.status_code == 200, draft.text
    assert "GDPR Article 33 Notification Draft" in draft.json()["draft_text"]
