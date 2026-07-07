from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.models.audit_engagement import AuditEngagement
from app.models.auditor import Auditor
from app.models.auditor_engagement import AuditorEngagement
from app.models.auditor_portal_invitation import AuditorPortalInvitation
from app.models.framework import Framework
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user


def test_v3_public_directory_filters_and_engagement_creation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="v3-auditor")

    public_resp = client.get("/api/v1/find-auditor")
    assert public_resp.status_code == 200
    auditors = public_resp.json()
    assert len(auditors) >= 2

    filtered_resp = client.get("/api/v1/find-auditor", params={"verified": True, "max_rate_usd_per_day": 1300})
    assert filtered_resp.status_code == 200
    filtered = filtered_resp.json()
    assert len(filtered) >= 1
    assert all(row["verified"] is True for row in filtered)
    assert all(float(row["rate_usd_per_day"]) <= 1300 for row in filtered)
    assert all("match_score" in row for row in filtered)
    assert all("context_flags" in row for row in filtered)

    auditor_id = filtered[0]["id"]
    SeedService.ensure_framework_catalog(db_session)
    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()
    framework = db_session.execute(select(Framework).where(Framework.code == "SOC2")).scalar_one_or_none()
    assert framework is not None

    start = datetime.now(UTC) + timedelta(days=3)
    end = start + timedelta(days=30)
    create_resp = client.post(
        "/api/v1/auditor-marketplace/engagements",
        headers=org["org_headers"],
        json={
            "auditor_id": auditor_id,
            "framework_id": str(framework.id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "title": "External readiness engagement",
            "revenue_share_fee_pct": 12.5,
            "invite_days_valid": 14,
        },
    )
    assert create_resp.status_code == 201
    payload = create_resp.json()
    assert payload["portal_token"]
    created_engagement = payload["engagement"]
    assert "context_flags" in created_engagement

    auditor_engagement_row = db_session.execute(
        select(AuditorEngagement).where(AuditorEngagement.id == UUID(created_engagement["id"]))
    ).scalar_one_or_none()
    assert auditor_engagement_row is not None
    assert float(auditor_engagement_row.revenue_share_fee_pct) == 12.5

    audit_engagement_row = db_session.execute(
        select(AuditEngagement).where(AuditEngagement.id == auditor_engagement_row.audit_engagement_id)
    ).scalar_one_or_none()
    assert audit_engagement_row is not None
    assert str(framework.id) in (audit_engagement_row.scope_framework_ids or [])

    invitation_row = db_session.execute(
        select(AuditorPortalInvitation).where(
            AuditorPortalInvitation.id == UUID(payload["portal_invitation_id"]),
            AuditorPortalInvitation.audit_engagement_id == auditor_engagement_row.audit_engagement_id,
        )
    ).scalar_one_or_none()
    assert invitation_row is not None

    list_resp = client.get("/api/v1/auditor-marketplace/engagements", headers=org["org_headers"])
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed
    assert listed[0]["schedule_start_date"] is not None
    assert listed[0]["schedule_end_date"] is not None
    assert isinstance(listed[0]["context_flags"], list)


def test_v3_revenue_share_range_validation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="v3-auditor-range")
    auditor = client.get("/api/v1/find-auditor").json()[0]
    SeedService.ensure_framework_catalog(db_session)
    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()
    framework = db_session.execute(select(Framework).where(Framework.code == "SOC2")).scalar_one_or_none()
    assert framework is not None

    start = datetime.now(UTC) + timedelta(days=1)
    end = start + timedelta(days=5)
    bad_resp = client.post(
        "/api/v1/auditor-marketplace/engagements",
        headers=org["org_headers"],
        json={
            "auditor_id": auditor["id"],
            "framework_id": str(framework.id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "title": "Bad fee",
            "revenue_share_fee_pct": 9.0,
        },
    )
    assert bad_resp.status_code == 422


def test_v3_prevents_overlapping_active_engagement_for_same_auditor_and_framework(client, db_session):
    org = bootstrap_org_user(client, email_prefix="v3-auditor-overlap")
    auditor = client.get("/api/v1/find-auditor", params={"framework": "SOC2"}).json()[0]
    SeedService.ensure_framework_catalog(db_session)
    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()
    framework = db_session.execute(select(Framework).where(Framework.code == "SOC2")).scalar_one_or_none()
    assert framework is not None

    start = datetime.now(UTC) + timedelta(days=10)
    end = start + timedelta(days=20)
    first = client.post(
        "/api/v1/auditor-marketplace/engagements",
        headers=org["org_headers"],
        json={
            "auditor_id": auditor["id"],
            "framework_id": str(framework.id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "title": "First engagement",
            "revenue_share_fee_pct": 12.0,
        },
    )
    assert first.status_code == 201, first.text

    overlapping = client.post(
        "/api/v1/auditor-marketplace/engagements",
        headers=org["org_headers"],
        json={
            "auditor_id": auditor["id"],
            "framework_id": str(framework.id),
            "start_date": (start + timedelta(days=5)).isoformat(),
            "end_date": (end + timedelta(days=5)).isoformat(),
            "title": "Overlapping engagement",
            "revenue_share_fee_pct": 12.0,
        },
    )
    assert overlapping.status_code == 409, overlapping.text
    assert "Overlapping active engagement" in overlapping.json()["detail"]


def test_v3_rejects_past_start_date_and_unavailable_auditor(client, db_session):
    org = bootstrap_org_user(client, email_prefix="v3-auditor-past")
    auditors = client.get("/api/v1/find-auditor", params={"framework": "SOC2"}).json()
    assert auditors
    auditor_id = UUID(auditors[0]["id"])

    SeedService.ensure_framework_catalog(db_session)
    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()
    framework = db_session.execute(select(Framework).where(Framework.code == "SOC2")).scalar_one_or_none()
    assert framework is not None

    past_start = datetime.now(UTC) - timedelta(days=1)
    past_resp = client.post(
        "/api/v1/auditor-marketplace/engagements",
        headers=org["org_headers"],
        json={
            "auditor_id": str(auditor_id),
            "framework_id": str(framework.id),
            "start_date": past_start.isoformat(),
            "end_date": (past_start + timedelta(days=10)).isoformat(),
            "title": "Past start date",
            "revenue_share_fee_pct": 12.0,
        },
    )
    assert past_resp.status_code == 422, past_resp.text
    assert "start_date cannot be in the past" in past_resp.json()["detail"]

    auditor_row = db_session.get(Auditor, auditor_id)
    assert auditor_row is not None
    auditor_row.availability = "unavailable"
    db_session.commit()

    future_start = datetime.now(UTC) + timedelta(days=14)
    unavailable_resp = client.post(
        "/api/v1/auditor-marketplace/engagements",
        headers=org["org_headers"],
        json={
            "auditor_id": str(auditor_id),
            "framework_id": str(framework.id),
            "start_date": future_start.isoformat(),
            "end_date": (future_start + timedelta(days=10)).isoformat(),
            "title": "Unavailable auditor",
            "revenue_share_fee_pct": 12.0,
        },
    )
    assert unavailable_resp.status_code == 422, unavailable_resp.text
    assert "not currently available" in unavailable_resp.json()["detail"]
