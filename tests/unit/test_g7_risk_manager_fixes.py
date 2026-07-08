"""G7 confirmed-bug fixes: Risk Manager (reviewer) permissions, factor-based
likelihood scoring, risk-to-risk dependency graph, and quantify schema.
"""
from __future__ import annotations

import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, org_headers, login_user


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str, password: str = "Pass1234!@") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash(password),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()
    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def _reviewer_headers(client, db_session, org_id: str, email_prefix: str):
    email = f"{email_prefix}@example.com"
    _create_active_user_with_role(db_session, org_id, email, "reviewer")
    token = login_user(client, email)
    return org_headers(token, org_id)


def test_item1_reviewer_can_create_risk(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-reviewer-risk")
    headers = _reviewer_headers(client, db_session, org["organization_id"], "g7-reviewer-risk-user")

    resp = client.post(
        "/api/v1/risks",
        headers=headers,
        json={"title": "Reviewer-created risk", "category": "operational", "likelihood": 2, "impact": 3},
    )
    assert resp.status_code == 201, resp.text


def test_item1_reviewer_can_write_risk_indicator(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-reviewer-kri")
    headers = _reviewer_headers(client, db_session, org["organization_id"], "g7-reviewer-kri-user")

    resp = client.post(
        "/api/v1/compliance/risk-indicators",
        headers=headers,
        json={
            "name": "Reviewer KRI",
            "metric_type": "custom",
            "target_value": 10,
            "warning_threshold": 20,
            "critical_threshold": 30,
            "owner_user_id": org["user_id"],
        },
    )
    assert resp.status_code == 201, resp.text


def test_item1_reviewer_can_write_risk_appetite(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-reviewer-appetite")
    headers = _reviewer_headers(client, db_session, org["organization_id"], "g7-reviewer-appetite-user")

    resp = client.post(
        "/api/v1/compliance/risk-appetite",
        headers=headers,
        json={
            "risk_category": "operational",
            "scope_type": "org",
            "max_acceptable_score": 15,
            "escalation_owner_id": org["user_id"],
        },
    )
    assert resp.status_code == 201, resp.text


def test_item2_factor_based_residual_score_uses_factor_methodology_not_plain_multiplication(client):
    """G7 item 2 regression: residual_score for a factor_based risk must use the same
    factor-based methodology as inherent_score, not the standard likelihood*impact
    multiplication.
    """
    org = bootstrap_org_user(client, email_prefix="g7-residual-factor")
    headers = org["org_headers"]

    put = client.put(
        "/api/v1/compliance/risk-settings",
        headers=headers,
        json={"financial_weight": 0.4, "brand_weight": 0.3, "operational_weight": 0.3},
    )
    assert put.status_code == 200

    created = client.post(
        "/api/v1/risks",
        headers=headers,
        json={
            "title": "Factor residual risk",
            "category": "operational",
            "likelihood": 5,
            "impact": 5,
            "composite_score_method": "factor_based",
            "financial_impact": 5,
            "brand_impact": 5,
            "operational_impact": 5,
        },
    )
    assert created.status_code == 201, created.text
    risk_id = created.json()["id"]
    inherent_score = created.json()["inherent_score"]
    assert inherent_score == 25

    control = client.post(
        "/api/v1/controls",
        headers=headers,
        json={
            "title": "Critical mitigating control",
            "control_type": "technical",
            "criticality": "critical",
        },
    )
    assert control.status_code == 201, control.text
    control_id = control.json()["id"]

    implemented = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=headers,
        json={"status": "implemented"},
    )
    assert implemented.status_code == 200, implemented.text

    linked = client.post(
        f"/api/v1/risks/{risk_id}/controls",
        headers=headers,
        json={"control_id": control_id, "link_type": "mitigates"},
    )
    assert linked.status_code == 200, linked.text

    detail = client.get(f"/api/v1/risks/{risk_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()

    # One implemented critical control reduces likelihood by 2 (5 -> 3). A plain
    # likelihood*impact residual formula would give 3*5=15. The correct factor-based
    # residual re-applies the SAME weighted factor composite (financial/brand/operational
    # are unchanged by controls) with the reduced likelihood: composite=5.0, likelihood
    # multiplier 3/3=1.0 -> raw 5.0 -> scaled 25, clamped to inherent_score=25.
    assert body["residual_likelihood"] == 3
    assert body["residual_score"] != 15, (
        "BUG: residual_score used the plain likelihood*impact formula instead of the "
        "factor-based methodology"
    )
    assert body["residual_score"] == 25


def _make_risk(client, headers, title):
    resp = client.post(
        "/api/v1/risks",
        headers=headers,
        json={"title": title, "category": "operational", "likelihood": 3, "impact": 3},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_item3_create_list_delete_risk_dependency(client):
    org = bootstrap_org_user(client, email_prefix="g7-dep-crud")
    headers = org["org_headers"]

    upstream_id = _make_risk(client, headers, "Upstream outage risk")
    downstream_id = _make_risk(client, headers, "Downstream SLA breach risk")

    created = client.post(
        f"/api/v1/risks/{upstream_id}/dependencies",
        headers=headers,
        json={"downstream_risk_id": downstream_id, "relationship_type": "cascades_to", "rationale": "Outage cascades to SLA breach"},
    )
    assert created.status_code == 201, created.text
    dependency_id = created.json()["id"]
    assert created.json()["upstream_risk_id"] == upstream_id
    assert created.json()["downstream_risk_id"] == downstream_id

    listed_upstream = client.get(f"/api/v1/risks/{upstream_id}/dependencies", headers=headers)
    assert listed_upstream.status_code == 200
    assert len(listed_upstream.json()) == 1

    # The edge should also show up from the downstream side.
    listed_downstream = client.get(f"/api/v1/risks/{downstream_id}/dependencies", headers=headers)
    assert listed_downstream.status_code == 200
    assert len(listed_downstream.json()) == 1

    deleted = client.delete(f"/api/v1/risks/{upstream_id}/dependencies/{dependency_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    listed_after_delete = client.get(f"/api/v1/risks/{upstream_id}/dependencies", headers=headers)
    assert listed_after_delete.json() == []


def test_item3_rejects_self_dependency(client):
    org = bootstrap_org_user(client, email_prefix="g7-dep-self")
    headers = org["org_headers"]
    risk_id = _make_risk(client, headers, "Self risk")

    resp = client.post(
        f"/api/v1/risks/{risk_id}/dependencies",
        headers=headers,
        json={"downstream_risk_id": risk_id, "relationship_type": "cascades_to"},
    )
    assert resp.status_code == 422, resp.text


def test_item3_rejects_duplicate_edge(client):
    org = bootstrap_org_user(client, email_prefix="g7-dep-dup")
    headers = org["org_headers"]
    a = _make_risk(client, headers, "Risk A")
    b = _make_risk(client, headers, "Risk B")

    first = client.post(
        f"/api/v1/risks/{a}/dependencies",
        headers=headers,
        json={"downstream_risk_id": b, "relationship_type": "cascades_to"},
    )
    assert first.status_code == 201

    dup = client.post(
        f"/api/v1/risks/{a}/dependencies",
        headers=headers,
        json={"downstream_risk_id": b, "relationship_type": "triggers"},
    )
    assert dup.status_code == 409, dup.text


def test_item3_rejects_cycle(client):
    """A -> B -> C exists; C -> A must be rejected since it would close a cycle."""
    org = bootstrap_org_user(client, email_prefix="g7-dep-cycle")
    headers = org["org_headers"]
    a = _make_risk(client, headers, "Risk A")
    b = _make_risk(client, headers, "Risk B")
    c = _make_risk(client, headers, "Risk C")

    assert client.post(
        f"/api/v1/risks/{a}/dependencies", headers=headers, json={"downstream_risk_id": b}
    ).status_code == 201
    assert client.post(
        f"/api/v1/risks/{b}/dependencies", headers=headers, json={"downstream_risk_id": c}
    ).status_code == 201

    cyclic = client.post(f"/api/v1/risks/{c}/dependencies", headers=headers, json={"downstream_risk_id": a})
    assert cyclic.status_code == 422, cyclic.text


def test_item3_org_scoping_enforced(client):
    org_a = bootstrap_org_user(client, email_prefix="g7-dep-org-a")
    org_b = bootstrap_org_user(client, email_prefix="g7-dep-org-b")

    risk_a = _make_risk(client, org_a["org_headers"], "Org A risk")
    risk_b = _make_risk(client, org_b["org_headers"], "Org B risk")

    # Org B cannot create a dependency using org A's risk as downstream.
    cross_org = client.post(
        f"/api/v1/risks/{risk_b}/dependencies",
        headers=org_b["org_headers"],
        json={"downstream_risk_id": risk_a},
    )
    assert cross_org.status_code == 404, cross_org.text

    # Org B cannot read org A's dependency graph/list via org A's risk id.
    graph = client.get(f"/api/v1/risks/{risk_a}/dependency-graph", headers=org_b["org_headers"])
    assert graph.status_code == 404


def test_item3_dependency_graph_surfaces_connected_component_scores(client):
    org = bootstrap_org_user(client, email_prefix="g7-dep-graph")
    headers = org["org_headers"]
    a = _make_risk(client, headers, "Root risk")
    b = _make_risk(client, headers, "Cascades from root")
    isolated = _make_risk(client, headers, "Unrelated isolated risk")

    assert client.post(
        f"/api/v1/risks/{a}/dependencies", headers=headers, json={"downstream_risk_id": b, "relationship_type": "cascades_to"}
    ).status_code == 201

    graph = client.get(f"/api/v1/risks/{a}/dependency-graph", headers=headers)
    assert graph.status_code == 200, graph.text
    body = graph.json()
    assert body["root_risk_id"] == a
    node_ids = {node["risk_id"] for node in body["nodes"]}
    assert node_ids == {a, b}
    assert isolated not in node_ids
    assert body["summary"]["total_nodes"] == 2
    assert body["summary"]["total_edges"] == 1
    # Each node surfaces current score/severity so a user can see the cascade at a glance.
    for node in body["nodes"]:
        assert "inherent_score" in node
        assert "severity" in node


def test_item3_deleting_dependency_leaves_no_orphaned_edge_when_risk_archived(client):
    org = bootstrap_org_user(client, email_prefix="g7-dep-archive")
    headers = org["org_headers"]
    a = _make_risk(client, headers, "Archived upstream")
    b = _make_risk(client, headers, "Downstream")

    assert client.post(
        f"/api/v1/risks/{a}/dependencies", headers=headers, json={"downstream_risk_id": b}
    ).status_code == 201

    archived = client.patch(f"/api/v1/risks/{a}/archive", headers=headers)
    assert archived.status_code == 200, archived.text

    # Archiving doesn't hard-delete the risk row, so the edge legitimately still exists
    # and the graph read must not crash for an archived upstream risk.
    graph = client.get(f"/api/v1/risks/{b}/dependency-graph", headers=headers)
    assert graph.status_code == 200, graph.text
    assert len(graph.json()["nodes"]) == 2


def test_item4_quantify_openapi_schema_documents_real_shape(client):
    """G7 item 4 regression: the OpenAPI schema for /quantify must document the real
    discriminated-union input shape, not an opaque dict[str, Any] blob."""
    schema = client.get("/openapi.json").json()
    body_schema = schema["paths"]["/api/v1/risks/{risk_id}/quantify"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert "oneOf" in body_schema
    assert body_schema["discriminator"]["propertyName"] == "methodology"
    mapping = body_schema["discriminator"]["mapping"]
    assert set(mapping.keys()) == {"monte_carlo", "fair", "fair_bayesian"}

    components = schema["components"]["schemas"]
    for name in (
        "MonteCarloQuantificationRequest",
        "FairQuantificationRequest",
        "FairBayesianQuantificationRequest",
        "PertTriple",
        "ProbabilityPertTriple",
        "PoissonFrequency",
        "LognormalLossMagnitude",
    ):
        assert name in components, f"{name} missing from documented OpenAPI schema"


def test_item4_quantify_wrong_payload_reports_all_problems_in_one_response(client):
    """A single call with multiple distinct problems must report ALL of them at once,
    not just the first one found (sequential 400-chasing was the confirmed bug)."""
    org = bootstrap_org_user(client, email_prefix="g7-quantify-multi")
    headers = org["org_headers"]
    risk_id = _make_risk(client, headers, "Quantify multi-error risk")

    bad_payload = {
        "methodology": "fair",
        "input_parameters": {
            "threat_event_frequency": {"min": 20, "most_likely": 5, "max": 1},  # min > max
            "vulnerability": {"min": 0.1, "most_likely": 0.3, "max": 1.5},  # > 1.0
            # primary_loss_magnitude omitted entirely
        },
        "n_iterations": 500,  # below the 1000 floor
    }
    resp = client.post(f"/api/v1/risks/{risk_id}/quantify", headers=headers, json=bad_payload)
    assert resp.status_code == 422, resp.text
    errors = resp.json()["detail"]
    assert isinstance(errors, list)
    assert len(errors) >= 4, "expected all 4 distinct problems reported in a single response"

    joined = " ".join(str(e) for e in errors)
    assert "threat_event_frequency" in joined
    assert "vulnerability" in joined
    assert "primary_loss_magnitude" in joined
    assert "n_iterations" in joined


def test_item4_quantify_empty_body_gives_pydantic_field_errors(client):
    org = bootstrap_org_user(client, email_prefix="g7-quantify-empty")
    headers = org["org_headers"]
    risk_id = _make_risk(client, headers, "Quantify empty body risk")

    resp = client.post(
        f"/api/v1/risks/{risk_id}/quantify",
        headers=headers,
        json={"methodology": "fair", "input_parameters": {}},
    )
    assert resp.status_code == 422, resp.text
    errors = resp.json()["detail"]
    # Real Pydantic "field required" errors for each missing FAIR input, not a single
    # opaque runtime string from the first field checked.
    missing_fields = {tuple(e["loc"]) for e in errors if e.get("type") == "missing"}
    assert (
        "body",
        "fair",
        "input_parameters",
        "threat_event_frequency",
    ) in missing_fields
    assert (
        "body",
        "fair",
        "input_parameters",
        "vulnerability",
    ) in missing_fields
    assert (
        "body",
        "fair",
        "input_parameters",
        "primary_loss_magnitude",
    ) in missing_fields
