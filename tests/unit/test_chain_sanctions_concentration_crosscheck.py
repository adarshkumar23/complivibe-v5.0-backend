import uuid

from tests.helpers import bootstrap_admin_org, org_headers


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


def test_sanctions_hit_escalates_risk_tier_and_recomputes_concentration(client, db_session):
    admin = bootstrap_admin_org(client, email_prefix="sanchain")
    headers = admin["org_headers"]

    # Seed a local sanctions entity matching the vendor we'll screen.
    from app.models.sanctions_entity import SanctionsEntity

    db_session.add(
        SanctionsEntity(
            id="ofac-1",
            caption="Acme Sanctioned Trading Co",
            schema_type="Company",
            countries=["RU"],
            datasets=["opensanctions_default"],
            properties={},
        )
    )
    db_session.commit()

    parent_id = _create_vendor(client, headers, "Downstream Parent Vendor", admin["user_id"], risk_tier="medium")
    target_id = _create_vendor(client, headers, "Acme Sanctioned Trading Co", admin["user_id"], risk_tier="low")

    link_resp = client.post(
        f"/api/v1/vendors/{parent_id}/supply-chain-links",
        headers=headers,
        json={"sub_vendor_id": target_id, "relationship_type": "supplier"},
    )
    assert link_resp.status_code in (200, 201), link_resp.text

    # Opt into concentration monitoring first (creates the detection row so
    # recompute_if_tracked is not a no-op).
    recompute_resp = client.post(
        "/api/v1/vendor-concentration-risk/recompute",
        headers=headers,
        json={},
    )
    assert recompute_resp.status_code == 200, recompute_resp.text
    before_detection = recompute_resp.json()["detection"]
    print("BEFORE detection:", before_detection)

    # Fire the sanctions screen against the target vendor -- should match locally.
    screen_resp = client.post(f"/api/v1/vendors/{target_id}/sanctions-screen/compute", headers=headers)
    assert screen_resp.status_code == 201, screen_resp.text
    screen_json = screen_resp.json()
    print("SCREEN RESULT:", screen_json)
    assert screen_json["match_found"] is True

    # Vendor's own risk_tier should now be escalated to critical.
    vendor_resp = client.get(f"/api/v1/compliance/vendors/{target_id}", headers=headers)
    assert vendor_resp.status_code == 200, vendor_resp.text
    print("VENDOR AFTER SCREEN:", vendor_resp.json())
    assert vendor_resp.json()["risk_tier"] == "critical"

    # Concentration detection should have recomputed to reflect the new critical vendor.
    detection_resp = client.get("/api/v1/vendor-concentration-risk", headers=headers)
    assert detection_resp.status_code == 200, detection_resp.text
    after_detection = detection_resp.json()
    print("AFTER detection:", after_detection)

    assert after_detection["critical_vendor_count"] >= before_detection["critical_vendor_count"] + 1

    # Audit trail: sanctions escalation + concentration recompute rows must exist.
    from app.models.audit_log import AuditLog

    all_rows = db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(admin["organization_id"])).all()
    print("ALL AUDIT ACTIONS:", [(r.action, r.entity_type) for r in all_rows])
    actions = {r.action for r in all_rows}
    assert "vendor.risk_tier_escalated" in actions
    assert "vendor_concentration_risk.recomputed" in actions
