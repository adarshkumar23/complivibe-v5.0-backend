from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import inspect, select

from app.models.audit_log import AuditLog
from app.models.shared_report_link import SharedReportLink
from tests.helpers.auth_org import bootstrap_org_user


def test_report_sharing_end_to_end(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="share-a")
    org_b = bootstrap_org_user(client, email_prefix="share-b")

    tables = set(inspect(db_session.bind).get_table_names())
    assert "shared_report_links" in tables

    create = client.post(
        "/api/v1/reports/share",
        headers=org_a["org_headers"],
        json={
            "report_type": "compliance_summary",
            "report_params": {"framework": "iso27001"},
            "recipient_email": "recipient@example.com",
            "watermark_text": "Confidential copy",
        },
    )
    assert create.status_code == 200
    created = create.json()
    assert "share_url" in created
    assert created["token"] in created["share_url"]
    assert "expires_in_hours" in created
    assert isinstance(created["context_flags"], list)

    list_resp = client.get("/api/v1/reports/shared-links", headers=org_a["org_headers"])
    assert list_resp.status_code == 200
    assert list_resp.json()
    assert "expires_in_hours" in list_resp.json()[0]
    assert "context_flags" in list_resp.json()[0]
    assert "token" not in list_resp.json()[0]

    public_get = client.get(f"/api/v1/reports/shared/{created['token']}")
    assert public_get.status_code == 200
    assert public_get.json()["watermark"] == "Confidential copy"
    assert isinstance(public_get.json()["context_flags"], list)

    invalid = client.get("/api/v1/reports/shared/not-a-real-token")
    assert invalid.status_code == 404

    # Org B cannot see Org A links.
    b_list = client.get("/api/v1/reports/shared-links", headers=org_b["org_headers"])
    assert b_list.status_code == 200
    b_ids = {row["id"] for row in b_list.json()}
    assert str(created["share_id"]) not in b_ids


def test_report_sharing_expiry_views_password_verify_revoke_and_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="share-sec")

    no_jwt = client.post("/api/v1/reports/share", json={"report_type": "risk_register"})
    assert no_jwt.status_code == 401

    limited = client.post(
        "/api/v1/reports/share",
        headers=org["org_headers"],
        json={"report_type": "risk_register", "max_views": 2},
    )
    assert limited.status_code == 200
    limited_token = limited.json()["token"]

    first = client.get(f"/api/v1/reports/shared/{limited_token}")
    second = client.get(f"/api/v1/reports/shared/{limited_token}")
    third = client.get(f"/api/v1/reports/shared/{limited_token}")
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 410

    protected = client.post(
        "/api/v1/reports/share",
        headers=org["org_headers"],
        json={"report_type": "gdpr_article30", "password": "topsecret"},
    )
    assert protected.status_code == 200
    protected_token = protected.json()["token"]

    no_password = client.get(f"/api/v1/reports/shared/{protected_token}")
    wrong_password = client.get(f"/api/v1/reports/shared/{protected_token}?password=wrong")
    correct_password = client.get(f"/api/v1/reports/shared/{protected_token}?password=topsecret")
    assert no_password.status_code == 401
    assert wrong_password.status_code == 401
    assert correct_password.status_code == 200

    verify = client.post(
        f"/api/v1/reports/shared/{protected_token}/verify",
        json={"password": "topsecret"},
    )
    assert verify.status_code == 200
    assert verify.json() == {"valid": True}

    expiring = client.post(
        "/api/v1/reports/share",
        headers=org["org_headers"],
        json={"report_type": "framework_gap", "report_params": {"framework_id": "abc"}},
    )
    assert expiring.status_code == 200
    expiring_token = expiring.json()["token"]

    row = db_session.execute(select(SharedReportLink).where(SharedReportLink.token == expiring_token)).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.flush()

    expired = client.get(f"/api/v1/reports/shared/{expiring_token}")
    assert expired.status_code == 410
    expired_verify = client.post(
        f"/api/v1/reports/shared/{expiring_token}/verify",
        json={"password": None},
    )
    assert expired_verify.status_code == 410

    revoke = client.delete(
        f"/api/v1/reports/shared-links/{protected.json()['share_id']}",
        headers=org["org_headers"],
    )
    assert revoke.status_code == 204
    revoke_again = client.delete(
        f"/api/v1/reports/shared-links/{protected.json()['share_id']}",
        headers=org["org_headers"],
    )
    assert revoke_again.status_code == 204

    revoked_access = client.get(f"/api/v1/reports/shared/{protected_token}?password=topsecret")
    assert revoked_access.status_code == 404

    created_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "report.share_link_created",
        )
    ).scalars().first()
    revoked_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "report.share_link_revoked",
        )
    ).scalars().first()
    access_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "report.shared_accessed",
        )
    ).scalars().first()
    assert created_audit is not None
    assert revoked_audit is not None
    assert access_audit is not None
