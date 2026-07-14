"""Regression tests for three silent-swallow error handlers that previously
masked real failures behind a success response / misleading zeros.

1. SCIM deprovision: a failed offboarding automation must not be recorded as a
   clean success -- it must emit an honest failure-status audit entry while the
   security-critical deactivation still persists.
2. Data-asset update: a failed tier-1 reclassification must surface to the
   caller, not silently commit a stale classification with a 2xx response.
3. AI-governance dashboard: a failed aggregation query must be reported as an
   unavailable metric, not rendered as a real zero.
"""
from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.data_asset import DataAsset
from app.models.organization import Organization
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

ASSETS_BASE = "/api/v1/data-observability/assets"


# ---------------------------------------------------------------------------
# 1. SCIM offboarding failure -> honest failure audit
# ---------------------------------------------------------------------------
def _enable_scim_feature(db_session, organization_id: str) -> None:
    org = db_session.get(Organization, UUID(organization_id))
    org.subscription_status = "active"
    org.subscription_plan = "enterprise"
    db_session.commit()


def _scim_headers(raw_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_token}"}


def test_scim_offboarding_failure_writes_honest_failure_audit(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="scim-offboard-fail")
    _enable_scim_feature(db_session, org["organization_id"])
    token = client.post(
        "/api/v1/scim-tokens", headers=org["org_headers"], json={"description": "Okta"}
    )
    assert token.status_code == 201
    scim_headers = _scim_headers(token.json()["raw_token"])

    created = client.post(
        "/api/v1/scim/v2/Users",
        headers=scim_headers,
        json={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "offboard-fail@example.com",
            "name": {"givenName": "Jane", "familyName": "Smith"},
            "active": True,
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]

    # Force the offboarding automation to blow up.
    from app.compliance.services.offboarding_service import OffboardingService

    def _boom(self, **kwargs):
        raise RuntimeError("offboarding backend exploded")

    monkeypatch.setattr(OffboardingService, "run_offboarding", _boom)

    deleted = client.delete(f"/api/v1/scim/v2/Users/{user_id}", headers=scim_headers)
    # Deactivation (the security-critical part) still completes.
    assert deleted.status_code == 204
    user_row = db_session.get(User, UUID(user_id))
    assert user_row is not None
    assert user_row.is_active is False

    # An honest failure-status audit entry must exist.
    fail_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "user.scim_offboarding_failed",
        )
    ).scalar_one_or_none()
    assert fail_audit is not None, "expected an honest offboarding-failure audit entry"

    # The deprovision audit must not claim clean success for the offboarding step.
    deprov_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "user.deprovisioned_via_scim",
        )
    ).scalar_one()
    assert (deprov_audit.metadata_json or {}).get("offboarding_status") == "failed"


# ---------------------------------------------------------------------------
# 2. Data-asset reclassification failure -> surfaced, not silent stale success
# ---------------------------------------------------------------------------
def test_data_asset_reclassification_failure_surfaces_not_silent_success(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="asset-reclass-fail")
    created = client.post(
        ASSETS_BASE,
        headers=org["org_headers"],
        json={
            "name": "Customer Table",
            "asset_type": "table",
            "owner_id": org["user_id"],
            "description": "orig",
            "schema_column_names": ["email"],
        },
    )
    assert created.status_code == 201
    asset_id = created.json()["id"]

    import app.data_observability.services.data_asset_service as das

    def _boom(*args, **kwargs):
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr(das, "classify_metadata", _boom)

    # Renaming triggers reclassification; its failure must surface as an error,
    # not a 2xx that silently keeps the now-stale classification.
    resp = client.patch(
        f"{ASSETS_BASE}/{asset_id}", headers=org["org_headers"], json={"name": "Renamed Table"}
    )
    assert resp.status_code == 500, f"expected failure to surface, got {resp.status_code}"

    # No success audit for the aborted update.
    updated_audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == UUID(org["organization_id"]),
            AuditLog.action == "data_asset.updated",
            AuditLog.entity_id == UUID(asset_id),
        )
    ).scalar_one_or_none()
    assert updated_audit is None, "aborted update must not write a success audit log"


# ---------------------------------------------------------------------------
# 3. AI-governance dashboard metric failure -> unavailable, not misleading zero
# ---------------------------------------------------------------------------
def test_dashboard_metric_failures_surface_as_unavailable_not_zero():
    from app.compliance.services.ai_governance_dashboard_service import AIGovernanceDashboardService

    class _BoomSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError("db exploded")

    result = AIGovernanceDashboardService(_BoomSession()).get_dashboard(uuid.uuid4())

    assert "unavailable_metrics" in result, "dashboard must report which metrics are unavailable"
    assert set(result["unavailable_metrics"]) == {
        "ai_systems_by_tier",
        "governance_coverage_pct",
        "outstanding_reviews_count",
        "policy_violations_count",
        "shadow_ai_detected_count",
        "high_risk_systems_without_approval",
        "monitoring_alerts_by_system",
    }
