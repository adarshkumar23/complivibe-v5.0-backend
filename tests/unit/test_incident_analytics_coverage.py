"""Coverage for the incident-analytics endpoint (GET /compliance/incidents/by-category).

Zero prior test references. Exercises the real ClassificationService aggregation,
issues:read permission enforcement, and org-scoping.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.incident_classification import IncidentClassification
from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/compliance/incidents/by-category"


def _create_issue(client, headers, title: str) -> str:
    r = client.post(
        "/api/v1/compliance/issues",
        headers=headers,
        json={
            "title": title,
            "description": "seed issue for incident analytics",
            "issue_type": "custom",
            "severity": "medium",
            "owner_id": client.get("/api/v1/auth/me", headers=headers).json()["id"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _classify(db, org_id, user_id, issue_id, category, *, notify, implications):
    now = datetime.now(UTC)
    db.add(
        IncidentClassification(
            organization_id=uuid.UUID(org_id),
            issue_id=uuid.UUID(issue_id),
            category=category,
            regulatory_implications=implications,
            notification_required=notify,
            classification_by=uuid.UUID(user_id),
            classified_at=now,
            last_updated_at=now,
        )
    )
    db.commit()


def test_incidents_by_category_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="inc-an")
    h, oid, uid = org["org_headers"], org["organization_id"], org["user_id"]

    i1 = _create_issue(client, h, "breach 1")
    i2 = _create_issue(client, h, "breach 2")
    i3 = _create_issue(client, h, "access 1")
    _classify(db_session, oid, uid, i1, "security_breach", notify=True, implications=["GDPR"])
    _classify(db_session, oid, uid, i2, "security_breach", notify=True, implications=["GDPR", "DPDP"])
    _classify(db_session, oid, uid, i3, "unauthorized_access", notify=False, implications=[])

    r = client.get(BASE, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_classified"] == 3
    assert body["by_category"] == {"security_breach": 2, "unauthorized_access": 1}
    assert body["notification_required_count"] == 2
    assert body["regulatory_breakdown"] == {"GDPR": 2, "DPDP": 1}


def test_incidents_by_category_filter(client, db_session):
    org = bootstrap_org_user(client, email_prefix="inc-flt")
    h, oid, uid = org["org_headers"], org["organization_id"], org["user_id"]
    i1 = _create_issue(client, h, "b1")
    i2 = _create_issue(client, h, "a1")
    _classify(db_session, oid, uid, i1, "security_breach", notify=True, implications=["GDPR"])
    _classify(db_session, oid, uid, i2, "unauthorized_access", notify=False, implications=[])

    r = client.get(f"{BASE}?category=security_breach", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["total_classified"] == 1
    assert r.json()["by_category"] == {"security_breach": 1}


def test_incidents_by_category_requires_issues_read(client, db_session):
    # auditor role lacks issues:read -> 403 (permission enforcement).
    org = bootstrap_org_user(client, email_prefix="inc-perm")
    auditor_headers = add_org_member(db_session, client, org["organization_id"], "inc-auditor@example.com", role_name="auditor")
    r = client.get(BASE, headers=auditor_headers)
    assert r.status_code == 403, r.text


def test_incidents_by_category_org_scoped(client, db_session):
    # org A has a classification; org B (separate) must not see it.
    org_a = bootstrap_org_user(client, email_prefix="inc-a")
    ia = _create_issue(client, org_a["org_headers"], "a-breach")
    _classify(db_session, org_a["organization_id"], org_a["user_id"], ia, "security_breach", notify=True, implications=["GDPR"])

    org_b = bootstrap_org_user(client, email_prefix="inc-b")
    r = client.get(BASE, headers=org_b["org_headers"])
    assert r.status_code == 200, r.text
    assert r.json()["total_classified"] == 0
    assert r.json()["by_category"] == {}
