from __future__ import annotations

import uuid

from tests.unit.test_experience_inbox_ux4_p2d import _seed_inbox_records
from tests.helpers.auth_org import bootstrap_org_user

INBOX_URL = "/api/v1/inbox"


def test_g1_inbox_items_include_synthesized_reason(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="g1-inbox-reason")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    _seed_inbox_records(db_session, org_id, user_id, "ReasonOrg")

    resp = client.get(INBOX_URL, headers=ctx["org_headers"])
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]

    by_type = {}
    for item in items:
        by_type.setdefault(item["item_type"], []).append(item)

    overdue_task = by_type["overdue_task"][0]
    assert overdue_task["reason"] == "2 days overdue"

    approval = by_type["approval_request"][0]
    assert approval["reason"] == "Awaiting your approval decision"

    # Every item type must carry a non-empty reason -- this is the "why" the rubric wants,
    # not just a bare priority_score.
    for item in items:
        assert item["reason"], f"missing reason for {item['item_type']}"
