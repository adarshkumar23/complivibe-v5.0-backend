"""Regression tests for four HIGH findings from the 2026-07-19 verification pass.

1. Cross-tenant audit reminder sweep. process_schedule_reminders() took no organization
   argument and selected every active schedule in the table, while the endpoint bound and
   then discarded its authenticated organization. One tenant's admin could fire audit-prep
   emails into every other tenant, stamp their last_reminder_sent_at, and -- via the 7-day
   debounce -- suppress those tenants' own legitimate reminders for a week.

2. Evidence checksum patching. PATCH /evidence/{id} blind-setattr'd checksum_sha256,
   size_bytes, file_name and mime_type, so an evidence:write holder could upload a file,
   let a reviewer verify it, then rewrite the checksum to that of a different document.

3. Four-eyes bypass on AI governance reviews. approve_review enforced creator != approver
   and all-criteria-answered, but the conditional route (approve_with_conditions ->
   complete_conditional) reached the identical terminal "approved" state with neither.

4. Unauthenticated committing GET. GET /api/v1/find-auditor had no auth dependency, seeded
   rows, and committed -- anonymous write amplification against the primary database. It
   also returned auditor email addresses verbatim behind four filter parameters.
"""

from __future__ import annotations

import uuid

import pytest
from datetime import UTC, date, datetime, timedelta

from app.models.audit_schedule import AuditSchedule
from app.models.email_outbox import EmailOutbox
from tests.helpers.auth_org import bootstrap_org_user

pytestmark = pytest.mark.usefixtures("seeded_reference_data")

SCHEDULE_BASE = "/api/v1/compliance/audit-schedules"


def _framework_id(client, headers: dict[str, str]) -> str:
    resp = client.get("/api/v1/frameworks", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()[0]["id"]


def _create_schedule(client, headers: dict[str, str], framework_id: str, title: str) -> dict:
    resp = client.post(
        SCHEDULE_BASE,
        headers=headers,
        json={
            "title": title,
            "audit_type": "internal_readiness",
            "framework_id": framework_id,
            "recurrence_pattern": "annual",
            "next_audit_date": (date.today() + timedelta(days=2)).isoformat(),
            "preparation_reminder_days": 7,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --------------------------------------------------------------------------------------
# 1. Cross-tenant audit reminder sweep
# --------------------------------------------------------------------------------------


def test_reminder_sweep_does_not_touch_another_organization(client, db_session):
    """Org A's sweep must not send org B's reminders nor consume B's debounce window."""
    org_a = bootstrap_org_user(client, email_prefix="sweep-a")
    org_b = bootstrap_org_user(client, email_prefix="sweep-b")

    fw_a = _framework_id(client, org_a["org_headers"])
    fw_b = _framework_id(client, org_b["org_headers"])
    _create_schedule(client, org_a["org_headers"], fw_a, "Org A schedule")
    schedule_b = _create_schedule(client, org_b["org_headers"], fw_b, "Org B schedule")

    sweep = client.post(f"{SCHEDULE_BASE}/trigger-reminder-sweep", headers=org_a["org_headers"])
    assert sweep.status_code == 200, sweep.text

    # B's schedule must be untouched: no reminder stamped, so B's own sweep still works.
    row_b = db_session.query(AuditSchedule).filter_by(id=uuid.UUID(schedule_b["id"])).one()
    db_session.refresh(row_b)
    assert row_b.last_reminder_sent_at is None, (
        "org A's sweep stamped org B's schedule, which also suppresses B's real reminders for 7 days"
    )

    # And no email was queued into B's organization.
    b_emails = (
        db_session.query(EmailOutbox)
        .filter(
            EmailOutbox.organization_id == uuid.UUID(org_b["organization_id"]),
            EmailOutbox.event_type == "audit.schedule.reminder",
        )
        .all()
    )
    assert b_emails == [], "org A's sweep queued audit reminders into org B"


def test_reminder_sweep_still_works_for_the_calling_organization(client, db_session):
    """The scoping fix must not break the legitimate same-org sweep."""
    org = bootstrap_org_user(client, email_prefix="sweep-own")
    fw = _framework_id(client, org["org_headers"])
    schedule = _create_schedule(client, org["org_headers"], fw, "Own schedule")

    sweep = client.post(f"{SCHEDULE_BASE}/trigger-reminder-sweep", headers=org["org_headers"])
    assert sweep.status_code == 200, sweep.text
    assert sweep.json()["reminders_sent"] >= 1

    row = db_session.query(AuditSchedule).filter_by(id=uuid.UUID(schedule["id"])).one()
    db_session.refresh(row)
    assert row.last_reminder_sent_at is not None


# --------------------------------------------------------------------------------------
# 2. Evidence checksum patching
# --------------------------------------------------------------------------------------


def _create_evidence(client, headers: dict[str, str]) -> dict:
    resp = client.post(
        "/api/v1/evidence",
        headers=headers,
        json={
            "title": "Integrity probe evidence",
            "description": "Recorded with a server-known checksum",
            "evidence_type": "document",
            "source": "manual_upload",
            "checksum_sha256": "a" * 64,
            "size_bytes": 1024,
            "file_name": "original.pdf",
            "mime_type": "application/pdf",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_evidence_integrity_fields_cannot_be_rewritten_by_patch(client):
    """checksum/size/file_name/mime_type describe the stored bytes and are immutable."""
    org = bootstrap_org_user(client, email_prefix="ev-integrity")
    evidence = _create_evidence(client, org["org_headers"])
    original_checksum = evidence["checksum_sha256"]
    assert original_checksum == "a" * 64

    response = client.patch(
        f"/api/v1/evidence/{evidence['id']}",
        headers=org["org_headers"],
        json={
            "title": "Renamed but same bytes",
            "checksum_sha256": "b" * 64,
            "size_bytes": 999999,
            "file_name": "swapped.pdf",
            "mime_type": "text/plain",
        },
    )
    assert response.status_code == 200, response.text

    # The editable field changed; every integrity field did not.
    body = response.json()
    assert body["title"] == "Renamed but same bytes"
    assert body["checksum_sha256"] == original_checksum, "checksum was rewritten via PATCH"
    assert body["size_bytes"] == 1024
    assert body["file_name"] == "original.pdf"
    assert body["mime_type"] == "application/pdf"

    # Confirm against a fresh read, not just the write response.
    after = client.get(f"/api/v1/evidence/{evidence['id']}", headers=org["org_headers"])
    assert after.status_code == 200, after.text
    assert after.json()["checksum_sha256"] == original_checksum


# --------------------------------------------------------------------------------------
# 3. Four-eyes bypass on AI governance reviews
# --------------------------------------------------------------------------------------


def _second_member(client, db_session, org) -> uuid.UUID:
    """Add a second active member to the same organization (no invite helper exists)."""
    from app.core.security import get_password_hash
    from app.models.membership import Membership
    from app.models.user import User

    org_id = uuid.UUID(org["organization_id"])
    existing = db_session.query(Membership).filter_by(organization_id=org_id).first()

    reviewer = User(
        email=f"four-eyes-reviewer-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("Pass1234!@"),
        full_name="Second Reviewer",
        is_active=True,
    )
    db_session.add(reviewer)
    db_session.flush()
    db_session.add(
        Membership(
            organization_id=org_id,
            user_id=reviewer.id,
            role_id=existing.role_id,
            status="active",
        )
    )
    db_session.commit()
    return reviewer.id


def test_creator_cannot_self_approve_via_the_conditional_path(client, db_session):
    """The conditional route reaches the same terminal 'approved' state as approve_review.

    Driven at the service layer: the guard is in the service, and the HTTP route needs two
    members in one organization, which the auth helpers do not provide.
    """
    from fastapi import HTTPException

    from app.ai_governance.schemas.ai_reviews import AIReviewCreateRequest
    from app.ai_governance.services.ai_review_service import AIReviewService
    from app.models.ai_review_criteria_response import AIReviewCriteriaResponse

    org = bootstrap_org_user(client, email_prefix="four-eyes")
    org_id = uuid.UUID(org["organization_id"])
    creator_id = uuid.UUID(org["user_id"])
    reviewer_id = _second_member(client, db_session, org)

    system = client.post(
        "/api/v1/ai-systems",
        headers=org["org_headers"],
        json={
            "name": "Four-eyes probe system",
            "description": "System under review",
            "system_type": "internal_model",
            "risk_tier": "limited",
            "deployment_status": "development",
        },
    )
    assert system.status_code == 201, system.text
    system_id = uuid.UUID(system.json()["id"])

    service = AIReviewService(db_session)
    review = service.create_review(
        org_id,
        system_id,
        "initial_review",
        AIReviewCreateRequest(
            system_id=system_id,
            review_type="initial_review",
            assigned_reviewer_id=reviewer_id,
        ),
        creator_id,
    )
    db_session.commit()

    # The assigned reviewer answers every criterion, moving pending -> in_review.
    criteria = (
        db_session.query(AIReviewCriteriaResponse)
        .filter_by(organization_id=org_id, review_id=review.id)
        .all()
    )
    assert criteria, "expected criteria to be seeded for the review"
    service.respond_to_criteria(
        org_id,
        review.id,
        [{"criterion_key": row.criterion_key, "response": "yes", "notes": None} for row in criteria],
        reviewer_id,
    )
    db_session.commit()
    assert review.status == "in_review"

    # The creator now tries the conditional route instead of the guarded direct one.
    with pytest.raises(HTTPException) as exc:
        service.approve_with_conditions(org_id, review.id, creator_id, ["Add monitoring"], "self-approving")
    assert exc.value.status_code == 422
    assert "own review" in str(exc.value.detail), (
        f"rejected for the wrong reason -- expected the four-eyes guard, got: {exc.value.detail}"
    )
    db_session.rollback()

    # Positive control: a different person may still take the conditional route, and the
    # creator still may not finalise it afterwards.
    service.approve_with_conditions(org_id, review.id, reviewer_id, ["Add monitoring"], "ok")
    db_session.commit()
    assert review.status == "conditional"

    with pytest.raises(HTTPException) as exc2:
        service.complete_conditional(org_id, review.id, creator_id, "finishing my own review")
    assert exc2.value.status_code == 422
    assert "own review" in str(exc2.value.detail)
    db_session.rollback()

    service.complete_conditional(org_id, review.id, reviewer_id, "done")
    db_session.commit()
    assert review.status == "approved"


# --------------------------------------------------------------------------------------
# 4. Unauthenticated committing GET on /find-auditor
# --------------------------------------------------------------------------------------


def test_find_auditor_is_anonymous_read_only_and_masks_contact(client, db_session):
    """Anonymous callers must not drive writes, and must not harvest contact addresses."""
    from app.models.auditor import Auditor

    # Ensure the catalog exists, then act as a genuinely anonymous caller.
    bootstrap_org_user(client, email_prefix="marketplace-seed")
    client.cookies.clear()

    before = db_session.query(Auditor).count()

    for _ in range(3):
        response = client.get("/api/v1/find-auditor")
        assert response.status_code == 200, response.text

    db_session.expire_all()
    after = db_session.query(Auditor).count()
    assert after == before, "anonymous GET /find-auditor created rows"

    for item in response.json():
        assert "@" in item["email"]
        assert "*" in item["email"], f"contact address returned verbatim to an anonymous caller: {item['email']}"
