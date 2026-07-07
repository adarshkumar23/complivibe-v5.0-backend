from __future__ import annotations

from uuid import UUID

from app.models.control import Control
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/board-scorecard"


def test_g1_first_snapshot_has_no_prior_comparison(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="bsc-first")
    headers = owner["org_headers"]

    resp = client.post(f"{BASE}/generate", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    score_change = body["snapshot_data"]["score_change"]
    assert score_change["previous_score"] is None
    assert score_change["delta"] is None
    assert "first board scorecard snapshot" in score_change["narrative"]


def test_g1_second_snapshot_explains_score_delta_drivers(client, db_session):
    owner = bootstrap_org_user(client, email_prefix="bsc-delta")
    headers = owner["org_headers"]
    org_id = UUID(owner["organization_id"])
    user_id = UUID(owner["user_id"])

    first = client.post(f"{BASE}/generate", headers=headers, json={})
    assert first.status_code == 200, first.text
    first_score = first.json()["overall_compliance_score"]

    # Add new critical risks and an unverified control between snapshots -- these are the
    # kinds of concrete, already-available signals the narrative should cite.
    db_session.add_all(
        [
            Risk(
                organization_id=org_id,
                title="New critical risk",
                created_by_user_id=user_id,
                inherent_score=5,
                severity="critical",
            ),
            Risk(
                organization_id=org_id,
                title="New high risk",
                created_by_user_id=user_id,
                inherent_score=4,
                severity="high",
            ),
            Control(
                organization_id=org_id,
                title="New unverified control",
                created_by_user_id=user_id,
                status="active",
            ),
        ]
    )
    db_session.commit()

    second = client.post(f"{BASE}/generate", headers=headers, json={})
    assert second.status_code == 200, second.text
    second_body = second.json()
    score_change = second_body["snapshot_data"]["score_change"]

    assert score_change["previous_score"] == first_score
    assert score_change["previous_snapshot_id"] == first.json()["id"]
    assert score_change["delta"] == round(second_body["overall_compliance_score"] - first_score, 2)
    assert "2 more open critical/high risks" in score_change["narrative"]

    # Real DB assertion: the second row's persisted snapshot_data actually contains the
    # score_change block, not just the HTTP response.
    from app.models.board_scorecard_snapshot import BoardScorecardSnapshot

    row = db_session.get(BoardScorecardSnapshot, UUID(second_body["id"]))
    assert row is not None
    assert row.snapshot_data["score_change"]["previous_score"] == first_score
