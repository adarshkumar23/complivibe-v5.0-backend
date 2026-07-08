"""G8 item 2: vendor risk-score compute must not silently overwrite a
manually-set vendor.risk_tier with zero audit trail. Every write is already
audited (AuditService), but nothing previously stopped an automated compute
from clobbering a human's explicit judgment call. Add risk_tier_source
provenance + require confirm_override=true to overwrite a manual tier."""

from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"


def _create_vendor(client, headers, owner_user_id):
    resp = client.post(
        VENDORS_BASE,
        headers=headers,
        json={"name": "Critical Vendor Co", "vendor_type": "software", "owner_user_id": owner_user_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_manual_risk_tier_blocks_silent_compute_overwrite(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g8-risktier")
    headers = org["org_headers"]
    vendor = _create_vendor(client, headers, org["user_id"])

    # Manually set risk_tier to "critical".
    manual = client.patch(f"{VENDORS_BASE}/{vendor['id']}", headers=headers, json={"risk_tier": "critical"})
    assert manual.status_code == 200
    assert manual.json()["risk_tier"] == "critical"
    assert manual.json()["risk_tier_source"] == "manual"

    # Compute a risk score that resolves to "high" (likelihood=high x impact=high -> 16 -> high).
    blocked = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/risk-scores",
        headers=headers,
        json={"likelihood": "high", "impact": "high"},
    )
    assert blocked.status_code == 409
    assert "confirm_override" in blocked.json()["detail"]

    # Tier must remain untouched -- no silent overwrite.
    unchanged = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=headers)
    assert unchanged.json()["risk_tier"] == "critical"
    assert unchanged.json()["risk_tier_source"] == "manual"

    # With explicit confirm_override, the compute path may proceed and the
    # audit trail must record before/after + who confirmed the override.
    confirmed = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/risk-scores",
        headers=headers,
        json={"likelihood": "high", "impact": "high", "confirm_override": True},
    )
    assert confirmed.status_code == 201, confirmed.text

    after = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=headers)
    assert after.json()["risk_tier"] == "high"
    assert after.json()["risk_tier_source"] == "computed"

    audit = client.get("/api/v1/audit-logs", headers=headers)
    assert audit.status_code == 200
    rows = [
        row
        for row in audit.json()
        if row["entity_id"] == vendor["id"] and row["action"] == "vendor.risk_tier.updated"
    ]
    assert rows, "expected an audit log entry for the vendor risk_tier change"
    latest = rows[0]
    assert latest["before_json"]["risk_tier"] == "critical"
    assert latest["before_json"]["risk_tier_source"] == "manual"
    assert latest["after_json"]["risk_tier"] == "high"
    assert latest["after_json"]["manual_override_confirmed"] is True


def test_computed_tier_can_be_recomputed_without_confirmation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g8-risktier-computed")
    headers = org["org_headers"]
    vendor = _create_vendor(client, headers, org["user_id"])

    # Vendor starts at default risk_tier "not_assessed" with source "computed".
    detail = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=headers)
    assert detail.json()["risk_tier_source"] == "computed"

    first = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/risk-scores",
        headers=headers,
        json={"likelihood": "low", "impact": "low"},
    )
    assert first.status_code == 201

    # A second compute recomputing an already-computed tier needs no confirmation.
    second = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/risk-scores",
        headers=headers,
        json={"likelihood": "high", "impact": "high"},
    )
    assert second.status_code == 201

    after = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=headers)
    assert after.json()["risk_tier"] == "high"
    assert after.json()["risk_tier_source"] == "computed"
