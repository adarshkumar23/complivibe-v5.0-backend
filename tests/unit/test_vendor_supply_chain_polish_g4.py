from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.vendor import Vendor
from app.models.vendor_supply_chain import VendorSupplyChainAlert
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
SATELLITE_BASE = "/api/v1/vendors"


def _create_vendor(client, org: dict, *, name: str = "Example Vendor", website: str = "https://example.com") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=org["org_headers"],
        json={
            "name": name,
            "vendor_type": "software",
            "website": website,
            "owner_user_id": org["user_id"],
            "data_access": True,
            "processes_personal_data": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _link(client, org, parent, child, relationship_type="hosting"):
    response = client.post(
        f"{SATELLITE_BASE}/{parent['id']}/supply-chain-links",
        headers=org["org_headers"],
        json={"sub_vendor_id": child["id"], "relationship_type": relationship_type},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_g4_supply_chain_graph_reports_risk_summary_and_truncation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g4-supply-summary")
    a = _create_vendor(client, org, name="Root A", website="https://a.example")
    b = _create_vendor(client, org, name="Mid B", website="https://b.example")
    c = _create_vendor(client, org, name="Leaf C", website="https://c.example")
    _link(client, org, a, b)
    _link(client, org, b, c)

    # depth=1 should truncate before reaching C, and must say so explicitly.
    shallow = client.get(f"{SATELLITE_BASE}/{a['id']}/supply-chain-graph?depth=1", headers=org["org_headers"])
    assert shallow.status_code == 200, shallow.text
    shallow_body = shallow.json()
    assert len(shallow_body["nodes"]) == 2  # a, b only
    assert shallow_body["risk_summary"]["truncated"] is True

    # depth=5 reaches the full chain and is not truncated.
    full = client.get(f"{SATELLITE_BASE}/{a['id']}/supply-chain-graph?depth=5", headers=org["org_headers"])
    assert full.status_code == 200, full.text
    full_body = full.json()
    assert len(full_body["nodes"]) == 3
    assert full_body["risk_summary"]["truncated"] is False
    assert full_body["risk_summary"]["node_count"] == 3
    assert full_body["risk_summary"]["edge_count"] == 2
    assert full_body["risk_summary"]["open_alert_count"] == 0
    assert full_body["risk_summary"]["highest_open_alert_severity"] is None


def test_g4_supply_chain_graph_flags_archived_vendor_in_chain(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g4-supply-archived")
    a = _create_vendor(client, org, name="Root Vendor", website="https://root.example")
    b = _create_vendor(client, org, name="Sub Vendor", website="https://sub.example")
    _link(client, org, a, b)

    # Archive b directly via the model to simulate a vendor archived after the link
    # was created (archiving via the API would already block re-linking, but existing
    # links from before an archive must still surface as a data-quality finding).
    vendor_row = db_session.execute(select(Vendor).where(Vendor.id == uuid.UUID(b["id"]))).scalar_one()
    vendor_row.status = "archived"
    db_session.commit()

    graph = client.get(f"{SATELLITE_BASE}/{a['id']}/supply-chain-graph?depth=5", headers=org["org_headers"])
    assert graph.status_code == 200, graph.text
    body = graph.json()
    finding_types = {f["type"] for f in body["data_quality_findings"]}
    assert "archived_vendor_in_chain" in finding_types
    archived_finding = next(f for f in body["data_quality_findings"] if f["type"] == "archived_vendor_in_chain")
    assert b["id"] in archived_finding["vendor_ids"]
    assert body["risk_summary"]["archived_vendors_in_chain"] == 1


def test_g4_supply_chain_link_rejects_archived_vendor(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g4-supply-archived-link")
    a = _create_vendor(client, org, name="Active Vendor", website="https://active.example")
    b = _create_vendor(client, org, name="Retired Vendor", website="https://retired.example")

    vendor_row = db_session.execute(select(Vendor).where(Vendor.id == uuid.UUID(b["id"]))).scalar_one()
    vendor_row.status = "archived"
    db_session.commit()

    response = client.post(
        f"{SATELLITE_BASE}/{a['id']}/supply-chain-links",
        headers=org["org_headers"],
        json={"sub_vendor_id": b["id"], "relationship_type": "hosting"},
    )
    assert response.status_code == 400
    assert "Archived vendors" in response.text


def test_g4_supply_chain_open_alert_staleness_surfaced(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g4-supply-stale-alert")
    parent = _create_vendor(client, org, name="Parent Vendor", website="https://parent.example")
    triggering = _create_vendor(client, org, name="Triggering Vendor", website="https://trigger.example")
    _link(client, org, parent, triggering)

    alert = VendorSupplyChainAlert(
        organization_id=uuid.UUID(org["organization_id"]),
        parent_vendor_id=uuid.UUID(parent["id"]),
        triggering_vendor_id=uuid.UUID(triggering["id"]),
        signal_type="kyb_aml_risk_flagged",
        severity="high",
        status="open",
        explanation="manually seeded stale alert for polish test",
        detected_at=datetime.now(UTC) - timedelta(days=10),
    )
    db_session.add(alert)
    db_session.commit()

    graph = client.get(f"{SATELLITE_BASE}/{parent['id']}/supply-chain-graph?depth=5", headers=org["org_headers"])
    assert graph.status_code == 200, graph.text
    body = graph.json()
    assert len(body["open_alerts"]) == 1
    open_alert = body["open_alerts"][0]
    assert open_alert["is_stale"] is True
    assert open_alert["age_days"] >= 9.9
    assert body["risk_summary"]["stale_alert_count"] == 1
    assert body["risk_summary"]["open_alerts_by_severity"]["high"] == 1
    assert body["risk_summary"]["highest_open_alert_severity"] == "high"
