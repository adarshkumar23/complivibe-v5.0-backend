from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
SUPPLY_CHAIN_BASE = "/api/v1/vendors"


def _create_vendor(client, headers, owner_user_id, *, name, risk_tier="high"):
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


def test_repro_cycle_detection(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cyc-repro")
    headers = org["org_headers"]
    owner_id = org["user_id"]

    a = _create_vendor(client, headers, owner_id, name="Vendor A")
    b = _create_vendor(client, headers, owner_id, name="Vendor B")

    _link_dependency(client, headers, parent_vendor_id=a["id"], sub_vendor_id=b["id"])
    _link_dependency(client, headers, parent_vendor_id=b["id"], sub_vendor_id=a["id"])

    graph = client.get(f"{SUPPLY_CHAIN_BASE}/{a['id']}/supply-chain-graph", headers=headers, params={"depth": 3})
    assert graph.status_code == 200, graph.text
    body = graph.json()
    print("RISK_SUMMARY:", body["risk_summary"])
    print("FINDINGS:", body["data_quality_findings"])
    assert body["risk_summary"]["cycle_count"] >= 1, f"expected cycle detected, got: {body['risk_summary']}"


def test_repro_cycle_detection_three_node(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cyc-repro3")
    headers = org["org_headers"]
    owner_id = org["user_id"]

    a = _create_vendor(client, headers, owner_id, name="Vendor A3")
    b = _create_vendor(client, headers, owner_id, name="Vendor B3")
    c = _create_vendor(client, headers, owner_id, name="Vendor C3")

    _link_dependency(client, headers, parent_vendor_id=a["id"], sub_vendor_id=b["id"])
    _link_dependency(client, headers, parent_vendor_id=b["id"], sub_vendor_id=c["id"])
    _link_dependency(client, headers, parent_vendor_id=c["id"], sub_vendor_id=a["id"])

    graph = client.get(f"{SUPPLY_CHAIN_BASE}/{a['id']}/supply-chain-graph", headers=headers, params={"depth": 5})
    assert graph.status_code == 200, graph.text
    body = graph.json()
    print("3NODE RISK_SUMMARY:", body["risk_summary"])
    assert body["risk_summary"]["cycle_count"] >= 1, f"expected cycle detected, got: {body['risk_summary']}"


def test_repro_cycle_not_including_root(client, db_session):
    org = bootstrap_org_user(client, email_prefix="cyc-reprodiamond")
    headers = org["org_headers"]
    owner_id = org["user_id"]

    root = _create_vendor(client, headers, owner_id, name="Root")
    a = _create_vendor(client, headers, owner_id, name="VendorA-diamond")
    b = _create_vendor(client, headers, owner_id, name="VendorB-diamond")
    c = _create_vendor(client, headers, owner_id, name="VendorC-diamond")

    # root -> a, root -> c -> a, a -> b -> a (cycle among a/b, reached via two paths to a)
    _link_dependency(client, headers, parent_vendor_id=root["id"], sub_vendor_id=a["id"])
    _link_dependency(client, headers, parent_vendor_id=root["id"], sub_vendor_id=c["id"])
    _link_dependency(client, headers, parent_vendor_id=c["id"], sub_vendor_id=a["id"])
    _link_dependency(client, headers, parent_vendor_id=a["id"], sub_vendor_id=b["id"])
    _link_dependency(client, headers, parent_vendor_id=b["id"], sub_vendor_id=a["id"])

    graph = client.get(f"{SUPPLY_CHAIN_BASE}/{root['id']}/supply-chain-graph", headers=headers, params={"depth": 5})
    assert graph.status_code == 200, graph.text
    body = graph.json()
    print("DIAMOND RISK_SUMMARY:", body["risk_summary"])
    assert body["risk_summary"]["cycle_count"] >= 1, f"expected cycle detected, got: {body['risk_summary']}"


def test_repro_cycle_missed_due_to_shared_edge_visited_set(client, db_session):
    """N has two incoming edges (A->N, B->N). N's back-edge N->B only closes a real
    cycle (B->N->B) when explored via B's path. If cycle detection dedupes graph
    edges in a single GLOBAL visited_edges set (rather than tracking per-branch /
    recursion-stack state), N->B gets marked visited the first time N is dequeued
    (via A's path, where B is not an ancestor) and is silently skipped the second
    time N is dequeued (via B's path, where B *is* an ancestor) -- so the real,
    persisted B->N->B cycle is never reported.
    """
    org = bootstrap_org_user(client, email_prefix="cyc-reprohidden")
    headers = org["org_headers"]
    owner_id = org["user_id"]

    root = _create_vendor(client, headers, owner_id, name="Root-hidden")
    a = _create_vendor(client, headers, owner_id, name="VendorA-hidden")
    b = _create_vendor(client, headers, owner_id, name="VendorB-hidden")
    n = _create_vendor(client, headers, owner_id, name="VendorN-hidden")

    # R -> A, R -> B (A created/linked first so BFS explores A's branch before B's)
    _link_dependency(client, headers, parent_vendor_id=root["id"], sub_vendor_id=a["id"])
    _link_dependency(client, headers, parent_vendor_id=root["id"], sub_vendor_id=b["id"])
    # A -> N, B -> N  (N reachable via two independent parents)
    _link_dependency(client, headers, parent_vendor_id=a["id"], sub_vendor_id=n["id"])
    _link_dependency(client, headers, parent_vendor_id=b["id"], sub_vendor_id=n["id"])
    # N -> B  (closes a real cycle B -> N -> B, but NOT a cycle via A's path)
    _link_dependency(client, headers, parent_vendor_id=n["id"], sub_vendor_id=b["id"])

    graph = client.get(f"{SUPPLY_CHAIN_BASE}/{root['id']}/supply-chain-graph", headers=headers, params={"depth": 5})
    assert graph.status_code == 200, graph.text
    body = graph.json()
    print("HIDDEN-CYCLE RISK_SUMMARY:", body["risk_summary"])
    print("HIDDEN-CYCLE FINDINGS:", body["data_quality_findings"])
    assert body["risk_summary"]["cycle_count"] >= 1, f"expected the real B->N->B cycle to be detected, got: {body['risk_summary']}"
