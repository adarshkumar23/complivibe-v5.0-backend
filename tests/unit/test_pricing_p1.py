from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.competitor_pricing_entry import CompetitorPricingEntry
from app.models.competitor_pricing_version import CompetitorPricingVersion
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user


def test_public_pricing_endpoint_returns_latest_snapshot(client, db_session):
    response = client.get("/api/v1/pricing")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version_id"]
    assert payload["last_updated"]
    assert payload["total_competitors"] >= 6
    assert "context_flags" in payload
    assert {row["competitor_key"] for row in payload["entries"]} == {
        "vanta",
        "drata",
        "sprinto",
        "scrut",
        "onetrust",
        "credo_ai",
    }

    version = db_session.execute(select(CompetitorPricingVersion)).scalar_one_or_none()
    assert version is not None


def test_pricing_refresh_requires_platform_admin_and_writes_versioned_records(client, db_session):
    org = bootstrap_org_user(client, email_prefix="pricing-refresh")
    org_id = UUID(org["organization_id"])

    # A regular org owner (with pricing:manage and all org permissions) must NOT
    # be able to overwrite the global pricing snapshot.
    before_versions = db_session.execute(select(CompetitorPricingVersion)).scalars().all()
    before_count = len(before_versions)

    denied = client.post(
        "/api/v1/pricing/refresh",
        headers=org["org_headers"],
        json={
            "source_note": "Unauthorized market refresh",
            "entries": [
                {
                    "competitor_key": "drata",
                    "competitor_name": "Drata",
                    "pricing_model": "tiered_quote",
                    "public_pricing_available": False,
                    "pricing_summary": "Tiered packaging with quote-led commercial process.",
                    "source_url": "https://drata.com/plans",
                    "source_excerpt": "Plans and pricing page",
                    "currency": None,
                    "starting_price_amount": None,
                    "starting_price_unit": None,
                    "last_verified_at": "2026-07-06T00:00:00Z",
                    "metadata_json": {"capture": "manual"},
                }
            ],
        },
    )
    assert denied.status_code == 403, denied.text
    assert "Platform administrator" in denied.json()["detail"]

    versions_after_denial = db_session.execute(select(CompetitorPricingVersion)).scalars().all()
    assert len(versions_after_denial) == before_count

    # Promote the same user to platform staff via the existing is_superuser flag.
    user = db_session.get(User, UUID(org["user_id"]))
    assert user is not None
    user.is_superuser = True
    db_session.commit()

    response = client.post(
        "/api/v1/pricing/refresh",
        headers=org["org_headers"],
        json={
            "source_note": "Manual market refresh",
            "entries": [
                {
                    "competitor_key": "drata",
                    "competitor_name": "Drata",
                    "pricing_model": "tiered_quote",
                    "public_pricing_available": False,
                    "pricing_summary": "Tiered packaging with quote-led commercial process.",
                    "source_url": "https://drata.com/plans",
                    "source_excerpt": "Plans and pricing page",
                    "currency": None,
                    "starting_price_amount": None,
                    "starting_price_unit": None,
                    "last_verified_at": "2026-07-06T00:00:00Z",
                    "metadata_json": {"capture": "manual"},
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["source_note"] == "Manual market refresh"
    assert len(payload["entries"]) == 1
    assert payload["total_competitors"] == 1
    assert "competitor_coverage_partial" in payload["context_flags"]

    after_versions = db_session.execute(select(CompetitorPricingVersion)).scalars().all()
    assert len(after_versions) == before_count + 1

    latest_id = UUID(payload["version_id"])
    latest_entries = db_session.execute(
        select(CompetitorPricingEntry).where(CompetitorPricingEntry.version_id == latest_id)
    ).scalars().all()
    assert len(latest_entries) == 1
    assert latest_entries[0].competitor_key == "drata"

    audit_rows = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action.in_(["pricing.snapshot_created", "pricing.entry_created"]),
        )
    ).scalars().all()
    assert len(audit_rows) >= 2
    snapshot_audit = [row for row in audit_rows if row.action == "pricing.snapshot_created"][0]
    assert snapshot_audit.metadata_json.get("actor_is_superuser") is True


def test_pricing_refresh_rejects_duplicate_competitor_key(client, db_session):
    org = bootstrap_org_user(client, email_prefix="pricing-dup")
    user = db_session.get(User, UUID(org["user_id"]))
    assert user is not None
    user.is_superuser = True
    db_session.commit()

    response = client.post(
        "/api/v1/pricing/refresh",
        headers=org["org_headers"],
        json={
            "source_note": "Bad duplicate payload",
            "entries": [
                {
                    "competitor_key": "drata",
                    "competitor_name": "Drata",
                    "pricing_model": "tiered_quote",
                    "public_pricing_available": False,
                    "pricing_summary": "Tiered packaging with quote-led commercial process.",
                    "source_url": "https://drata.com/plans",
                    "source_excerpt": "Plans and pricing page",
                    "currency": None,
                    "starting_price_amount": None,
                    "starting_price_unit": None,
                    "last_verified_at": "2026-07-06T00:00:00Z",
                    "metadata_json": {"capture": "manual"},
                },
                {
                    "competitor_key": "drata",
                    "competitor_name": "Drata",
                    "pricing_model": "tiered_quote",
                    "public_pricing_available": False,
                    "pricing_summary": "Second duplicate row.",
                    "source_url": "https://drata.com/plans",
                    "source_excerpt": "Plans and pricing page",
                    "currency": None,
                    "starting_price_amount": None,
                    "starting_price_unit": None,
                    "last_verified_at": "2026-07-06T00:00:00Z",
                    "metadata_json": {"capture": "manual"},
                },
            ],
        },
    )
    assert response.status_code == 422, response.text
    assert "Duplicate competitor_key" in response.json()["detail"]


def test_onboarding_select_plan_and_trust_center_public_include_competitor_pricing(client, db_session):
    org = bootstrap_org_user(client, email_prefix="pricing-onboarding")
    orgs = client.get("/api/v1/organizations/me", headers=org["headers"])
    assert orgs.status_code == 200
    org_slug = orgs.json()[0]["slug"]

    select_plan = client.get("/api/v1/onboarding/select-plan")
    assert select_plan.status_code == 200
    select_payload = select_plan.json()
    assert select_payload["available_plans"]
    assert len(select_payload["competitor_pricing"]["entries"]) >= 6

    upsert_config = client.post(
        "/api/v1/compliance/trust-center/configuration",
        headers=org["org_headers"],
        json={
            "is_enabled": True,
            "display_name": "Pricing Trust Center",
            "show_certifications": False,
            "show_framework_coverage": False,
            "show_published_policies": False,
            "show_uptime_status": False,
            "request_access_enabled": True,
        },
    )
    assert upsert_config.status_code == 200, upsert_config.text

    public = client.get(f"/api/v1/trust-center/{org_slug}")
    assert public.status_code == 200
    public_payload = public.json()
    assert public_payload["competitor_pricing"]
    assert public_payload["competitor_pricing_last_updated"]
    assert any(row["competitor_name"] == "Drata" for row in public_payload["competitor_pricing"])


def test_pricing_refresh_requires_auth(client):
    response = client.post(
        "/api/v1/pricing/refresh",
        json={
            "entries": [
                {
                    "competitor_key": "vanta",
                    "competitor_name": "Vanta",
                    "pricing_model": "contact_sales",
                    "public_pricing_available": False,
                    "pricing_summary": "Demo-led pricing.",
                    "source_url": "https://www.vanta.com/",
                    "source_excerpt": "Get demo",
                    "last_verified_at": datetime.now(UTC).isoformat(),
                    "metadata_json": {},
                }
            ]
        },
    )
    assert response.status_code in (400, 401, 403)
