from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user

TIMELINE_URL = "/api/v1/compliance-timeline"


def _create_risks(db_session, org_id: uuid.UUID, user_id: uuid.UUID, count: int) -> None:
    now = datetime.now(UTC)
    for i in range(count):
        db_session.add(
            Risk(
                organization_id=org_id,
                title=f"Volume risk {i}",
                severity="medium",
                status="identified",
                created_by_user_id=user_id,
                created_at=now - timedelta(minutes=i),
                updated_at=now - timedelta(minutes=i),
            )
        )
    db_session.commit()


def test_g1_timeline_has_more_false_when_everything_fits(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="g1-timeline-fits")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    _create_risks(db_session, org_id, user_id, count=3)

    resp = client.get(TIMELINE_URL, params={"limit": 50}, headers=ctx["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_more"] is False
    assert body["total_events"] == 3


def test_g1_timeline_has_more_true_when_truncated_by_limit(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="g1-timeline-more")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    _create_risks(db_session, org_id, user_id, count=10)

    resp = client.get(TIMELINE_URL, params={"limit": 5}, headers=ctx["org_headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_events"] == 5
    assert body["has_more"] is True
