from __future__ import annotations

import uuid

from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
SUPPLY_CHAIN_BASE = "/api/v1/vendors"
CONCENTRATION_BASE = "/api/v1/vendor-concentration-risk"


def _create_vendor(client, headers, owner_user_id, *, name, risk_tier="critical"):
    response = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
            "risk_tier": risk_tier,
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _link_dependency(client, headers, *, parent_vendor_id, sub_vendor_id):
    response = client.post(
        f"{SUPPLY_CHAIN_BASE}/{parent_vendor_id}/supply-chain-links",
        headers=headers,
        json={"sub_vendor_id": sub_vendor_id, "relationship_type": "critical_dependency"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_repro_double_counted_vendor_and_risk_created_flag(client, db_session):
    """Vendor B is BOTH directly tracked as a critical vendor AND a supply-chain
    dependency of critical Vendor A. B's share should reflect ONE identity, not two.
    Deleting the A->B dependency link should not change B's share at all if B was
    correctly deduped (it's still separately critical on its own), proving B was
    being double-counted before the fix.
    """
    org = bootstrap_org_user(client, email_prefix="conc-repro")
    headers = org["org_headers"]
    owner_id = org["user_id"]

    a = _create_vendor(client, headers, owner_id, name="Concentration Vendor A", risk_tier="critical")
    b = _create_vendor(client, headers, owner_id, name="Concentration Vendor B", risk_tier="critical")

    link = _link_dependency(client, headers, parent_vendor_id=a["id"], sub_vendor_id=b["id"])

    recompute = client.post(f"{CONCENTRATION_BASE}/recompute", headers=headers, json={})
    assert recompute.status_code == 200, recompute.text
    body = recompute.json()
    print("RECOMPUTE BODY (with link):", body)

    shares_with_link = {
        row["vendor_id"]: row["share_basis_points"]
        for row in body["detection"]["evidence_json"]["vendor_shares"]
    }
    b_share_with_link = shares_with_link[b["id"]]

    # Deactivate the dependency link -- B is STILL directly critical on its own.
    delete_resp = client.delete(f"{SUPPLY_CHAIN_BASE}/supply-chain-links/{link['id']}", headers=headers)
    assert delete_resp.status_code == 200, delete_resp.text

    recompute2 = client.post(f"{CONCENTRATION_BASE}/recompute", headers=headers, json={})
    assert recompute2.status_code == 200, recompute2.text
    body2 = recompute2.json()
    print("RECOMPUTE BODY (link removed):", body2)
    shares_without_link = {
        row["vendor_id"]: row["share_basis_points"]
        for row in body2["detection"]["evidence_json"]["vendor_shares"]
    }
    b_share_without_link = shares_without_link.get(b["id"], 0)

    assert b_share_with_link == b_share_without_link, (
        f"Vendor B's share changed just from removing a dependency link to a vendor "
        f"it is ALREADY directly/critically tracked as -- double counting. "
        f"with_link={b_share_with_link} without_link={b_share_without_link}"
    )


def test_repro_risk_created_true_on_creating_call(client, db_session):
    org = bootstrap_org_user(client, email_prefix="conc-repro-rc")
    headers = org["org_headers"]
    owner_id = org["user_id"]

    a = _create_vendor(client, headers, owner_id, name="RC Vendor A", risk_tier="critical")

    recompute = client.post(f"{CONCENTRATION_BASE}/recompute", headers=headers, json={})
    assert recompute.status_code == 200, recompute.text
    body = recompute.json()
    print("RC BODY:", body)
    if body["detection"]["status"] == "breach":
        assert body["risk_created"] is True, f"expected risk_created True on the creating call, got: {body}"
        assert body["detection"]["risk_id"] is not None


def test_repro_risk_created_true_on_the_call_that_actually_crosses_breach(client, db_session):
    """First recompute call: 6 equal critical vendors -> HHI just below threshold,
    no risk. Archiving one vendor is what actually pushes the detection into
    breach for the first time (T1-4 auto-refresh on archive) -- risk_created must
    be True on *that* auto-triggered recompute (verified via its audit log entry,
    since the archive endpoint's own HTTP response doesn't echo concentration-risk
    state). A subsequent manual /recompute call correctly reports risk_created
    False since the risk already exists by then -- it didn't create anything new.
    """
    org = bootstrap_org_user(client, email_prefix="conc-repro-2nd")
    headers = org["org_headers"]
    owner_id = org["user_id"]

    vendors = [
        _create_vendor(client, headers, owner_id, name=f"Six Equal Vendor {i}", risk_tier="critical")
        for i in range(6)
    ]

    first = client.post(f"{CONCENTRATION_BASE}/recompute", headers=headers, json={})
    assert first.status_code == 200, first.text
    first_body = first.json()
    print("FIRST BODY:", first_body["detection"]["hhi_score"], first_body["detection"]["status"], first_body["risk_created"])
    assert first_body["detection"]["status"] == "below_threshold", first_body
    assert first_body["risk_created"] is False
    assert first_body["detection"]["risk_id"] is None

    archive = client.post(
        f"{VENDORS_BASE}/{vendors[0]['id']}/archive",
        headers=headers,
        json={"reason": "consolidating"},
    )
    assert archive.status_code == 200, archive.text

    from sqlalchemy import select as sa_select

    from app.models.audit_log import AuditLog

    audits = db_session.execute(
        sa_select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "vendor_concentration_risk.recomputed",
        )
    ).scalars().all()
    archive_triggered = [row for row in audits if row.metadata_json.get("source") == "vendor.archived"]
    assert archive_triggered, f"expected an auto-triggered recompute audit entry from archiving, got sources: {[a.metadata_json.get('source') for a in audits]}"
    assert archive_triggered[-1].metadata_json["risk_created"] is True, (
        f"expected risk_created True on the auto-triggered recompute that actually crossed into breach, "
        f"got metadata: {archive_triggered[-1].metadata_json}"
    )
    assert archive_triggered[-1].after_json["risk_id"] is not None

    second = client.post(f"{CONCENTRATION_BASE}/recompute", headers=headers, json={})
    assert second.status_code == 200, second.text
    second_body = second.json()
    print("SECOND BODY:", second_body["detection"]["hhi_score"], second_body["detection"]["status"], second_body["risk_created"])
    assert second_body["detection"]["status"] == "breach", second_body
    assert second_body["risk_created"] is False, "the risk already exists by this point -- this call must not claim it created it"
    assert second_body["detection"]["risk_id"] is not None
