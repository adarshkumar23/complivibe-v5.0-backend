"""Coverage for the risk-dependency endpoints (app/api/v1/risk_dependencies.py).

Zero prior test references. Exercises the real RiskDependencyService: create/list/
delete of pure risk-to-risk cascade edges + the dependency-graph read, risks:write /
risks:read permission enforcement, and org-scoping / cycle-detection edge cases.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

RISKS = "/api/v1/risks"


def _create_risk(client, headers, title: str) -> str:
    r = client.post(
        RISKS,
        headers=headers,
        json={"title": title, "category": "operational", "likelihood": 3, "impact": 4},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _dep_url(risk_id: str) -> str:
    return f"{RISKS}/{risk_id}/dependencies"


def test_create_list_graph_delete_dependency(client, db_session):
    org = bootstrap_org_user(client, email_prefix="rd-happy")
    h, uid = org["org_headers"], org["user_id"]
    up = _create_risk(client, h, "upstream risk")
    down = _create_risk(client, h, "downstream risk")

    created = client.post(
        _dep_url(up),
        headers=h,
        json={"downstream_risk_id": down, "relationship_type": "cascades_to", "rationale": "outage cascades"},
    )
    assert created.status_code == 201, created.text
    dep = created.json()
    assert dep["upstream_risk_id"] == up
    assert dep["downstream_risk_id"] == down
    assert dep["relationship_type"] == "cascades_to"
    assert dep["rationale"] == "outage cascades"
    assert dep["created_by_user_id"] == uid
    assert dep["organization_id"] == org["organization_id"]
    dep_id = dep["id"]

    # list from the upstream risk contains the edge
    listed = client.get(_dep_url(up), headers=h)
    assert listed.status_code == 200, listed.text
    assert any(d["id"] == dep_id for d in listed.json())

    # dependency graph reachable from either node includes both nodes + the edge
    graph = client.get(f"{RISKS}/{up}/dependency-graph", headers=h)
    assert graph.status_code == 200, graph.text
    body = graph.json()
    assert body["root_risk_id"] == up
    assert body["summary"]["total_nodes"] == 2
    assert body["summary"]["total_edges"] == 1
    assert {n["risk_id"] for n in body["nodes"]} == {up, down}
    assert body["edges"][0]["id"] == dep_id

    # delete returns the deleted edge
    deleted = client.delete(f"{_dep_url(up)}/{dep_id}", headers=h)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["id"] == dep_id
    # gone afterwards
    assert client.get(_dep_url(up), headers=h).json() == []


def test_create_dependency_requires_risks_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="rd-perm")
    h = org["org_headers"]
    up = _create_risk(client, h, "up perm")
    down = _create_risk(client, h, "down perm")

    # readonly has risks:read but NOT risks:write -> 403 on create
    ro = add_org_member(db_session, client, org["organization_id"], "rd-readonly@example.com", role_name="readonly")
    r = client.post(_dep_url(up), headers=ro, json={"downstream_risk_id": down})
    assert r.status_code == 403, r.text

    # but readonly CAN read the (empty) dependency list -- risks:read allowed
    assert client.get(_dep_url(up), headers=ro).status_code == 200


def test_create_dependency_self_reference_rejected(client, db_session):
    # A risk cannot depend on itself -> 422 (real service validation).
    org = bootstrap_org_user(client, email_prefix="rd-self")
    h = org["org_headers"]
    risk = _create_risk(client, h, "lonely risk")
    r = client.post(_dep_url(risk), headers=h, json={"downstream_risk_id": risk})
    assert r.status_code == 422, r.text


def test_list_dependencies_unknown_risk_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="rd-404")
    r = client.get(_dep_url(str(uuid.uuid4())), headers=org["org_headers"])
    assert r.status_code == 404, r.text


def test_dependency_org_scoped(client, db_session):
    # org B must not be able to reference org A's risk as a downstream target.
    org_a = bootstrap_org_user(client, email_prefix="rd-a")
    a_risk = _create_risk(client, org_a["org_headers"], "a risk")

    org_b = bootstrap_org_user(client, email_prefix="rd-b")
    b_risk = _create_risk(client, org_b["org_headers"], "b risk")

    # org B tries to make its risk cascade into org A's risk -> A's risk is not visible -> 404
    r = client.post(_dep_url(b_risk), headers=org_b["org_headers"], json={"downstream_risk_id": a_risk})
    assert r.status_code == 404, r.text
