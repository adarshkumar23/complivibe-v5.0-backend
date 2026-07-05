import uuid

from tests.helpers import bootstrap_admin_org


def _create_vendor(client, headers, name, owner_user_id, risk_tier="low"):
    resp = client.post(
        "/api/v1/compliance/vendors",
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "risk_tier": risk_tier,
            "status": "active",
            "owner_user_id": owner_user_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_nth_party_risk_flag_surfaces_live_in_parent_vendor_criticality_profile(client, db_session):
    """T1-3 (nth-party propagation) -> T1-4 (business criticality) seam.

    VendorCriticalityService.build_priority_context() reads Vendor.nth_party_risk_flag
    live (not a cached/denormalized copy), so a downstream sub-vendor's sanctions hit
    that propagates an nth-party alert to a parent vendor should show up immediately in
    the parent's /criticality profile recommendation -- with no separate "recompute"
    step required for this specific signal.
    """
    admin = bootstrap_admin_org(client, email_prefix="nthchain")
    headers = admin["org_headers"]

    parent_id = _create_vendor(client, headers, "Business Critical Parent Vendor", admin["user_id"], risk_tier="low")
    sub_id = _create_vendor(client, headers, "Downstream Sanctioned Sub-Processor", admin["user_id"], risk_tier="low")

    link_resp = client.post(
        f"/api/v1/vendors/{parent_id}/supply-chain-links",
        headers=headers,
        json={"sub_vendor_id": sub_id, "relationship_type": "sub_processor"},
    )
    assert link_resp.status_code in (200, 201), link_resp.text

    # Give the parent a business-critical profile (high criticality tier) so the
    # nth-party recommendation branch actually engages.
    profile_resp = client.put(
        f"/api/v1/compliance/vendors/{parent_id}/criticality",
        headers=headers,
        json={
            "revenue_dependency_pct": "90.00",
            "data_volume_tier": "very_high",
            "operational_criticality": "critical",
            "substitutability_score": 5,
        },
    )
    assert profile_resp.status_code == 200, profile_resp.text
    before_profile = profile_resp.json()
    print("BEFORE PROFILE:", before_profile)
    assert before_profile["criticality_tier"] == "critical"
    assert before_profile["priority_context"]["nth_party_risk_flag"] is False

    # Seed a local sanctions entity matching the sub-vendor and screen it -- this
    # propagates an nth-party alert + flag to the parent (VendorSupplyChainService
    # .propagate_vendor_signal), independent of the parent's own risk_tier.
    from app.models.sanctions_entity import SanctionsEntity

    db_session.add(
        SanctionsEntity(
            id="ofac-nth-1",
            caption="Downstream Sanctioned Sub-Processor",
            schema_type="Company",
            countries=["IR"],
            datasets=["opensanctions_default"],
            properties={},
        )
    )
    db_session.commit()

    screen_resp = client.post(f"/api/v1/vendors/{sub_id}/sanctions-screen/compute", headers=headers)
    assert screen_resp.status_code == 201, screen_resp.text
    assert screen_resp.json()["match_found"] is True

    # Re-fetch the parent's criticality profile with no explicit "recompute" call --
    # it must reflect the nth-party flag immediately (read-time reactive design).
    after_resp = client.get(f"/api/v1/compliance/vendors/{parent_id}/criticality", headers=headers)
    assert after_resp.status_code == 200, after_resp.text
    after_profile = after_resp.json()
    print("AFTER PROFILE:", after_profile)

    priority_context = after_profile["priority_context"]
    assert priority_context["nth_party_risk_flag"] is True
    assert "nth-party risk flag" in priority_context["recommendation"]

    # Confirm the underlying vendor row and audit trail back this up directly.
    parent_vendor_resp = client.get(f"/api/v1/compliance/vendors/{parent_id}", headers=headers)
    assert parent_vendor_resp.json()["nth_party_risk_flag"] is True

    from app.models.audit_log import AuditLog

    rows = db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(admin["organization_id"])).all()
    actions = {r.action for r in rows}
    print("AUDIT ACTIONS:", sorted(actions))
    assert "vendor_supply_chain.nth_party_flag_updated" in actions
