"""Regression guard: every source_type the DB permits must be serializable by IssueRead.

Background: critical data-incident escalation (and other internal paths) construct the
Issue model directly with source_type='data_incident', which the ck_issues_source_type
CHECK constraint allows. IssueRead's source_type pattern had drifted and omitted it, so
GET /api/v1/compliance/issues 500'd once such an issue existed. This test inserts an
issue for each DB-allowed source_type and asserts the list endpoint stays 200 and the
row appears — so no auto-issue creation path can ever escape to a 500 on list again.
"""
from __future__ import annotations

import uuid

from app.models.issue import Issue
from app.schemas.issue import ISSUE_SOURCE_TYPES
from tests.helpers.auth_org import bootstrap_org_user

ISSUES_BASE = "/api/v1/compliance/issues"


def _insert_issue(db_session, org_id: str, owner_id: str, source_type: str) -> uuid.UUID:
    """Mirror incident_detection_service: build the Issue model directly."""
    issue = Issue(
        organization_id=uuid.UUID(org_id),
        title=f"[{source_type}] escalated issue",
        description="auto-created issue",
        issue_type="unauthorized_access",
        severity="critical",
        source_type=source_type,
        source_id=uuid.uuid4(),
        status="open",
        owner_id=uuid.UUID(owner_id),
        assigned_to=None,
        created_by=uuid.UUID(owner_id),
    )
    db_session.add(issue)
    db_session.flush()
    return issue.id


def test_list_issues_serializes_every_db_allowed_source_type(client, db_session):
    org = bootstrap_org_user(client, email_prefix="issue-src")
    org_id = org["organization_id"]
    owner_id = org["user_id"]

    inserted: dict[str, str] = {}
    for source_type in ISSUE_SOURCE_TYPES:
        issue_id = _insert_issue(db_session, org_id, owner_id, source_type)
        inserted[source_type] = str(issue_id)
    db_session.commit()

    resp = client.get(ISSUES_BASE, headers=org["org_headers"])
    assert resp.status_code == 200, resp.text

    rows = resp.json()
    by_source = {r["source_type"] for r in rows}
    for source_type in ISSUE_SOURCE_TYPES:
        assert source_type in by_source, f"{source_type} missing from issues list"

    ids = {r["id"] for r in rows}
    assert set(inserted.values()).issubset(ids)


def test_list_issues_with_data_incident_does_not_500(client, db_session):
    """The exact escaped defect: a data_incident-sourced issue must not 500 the list."""
    org = bootstrap_org_user(client, email_prefix="issue-dataincident")
    _insert_issue(db_session, org["organization_id"], org["user_id"], "data_incident")
    db_session.commit()

    resp = client.get(ISSUES_BASE, headers=org["org_headers"])
    assert resp.status_code == 200, resp.text
    assert any(r["source_type"] == "data_incident" for r in resp.json())
