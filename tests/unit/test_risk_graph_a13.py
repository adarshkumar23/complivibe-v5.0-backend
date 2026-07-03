from datetime import UTC, datetime, timedelta
import uuid

from app.models.compliance_policy import CompliancePolicy
from app.models.compliance_policy_control_link import CompliancePolicyControlLink
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.risk_evidence_link import RiskEvidenceLink
from app.models.vendor import Vendor
from app.models.vendor_control_link import VendorControlLink
from app.models.vendor_risk_score import VendorRiskScore
from tests.helpers.auth_org import bootstrap_org_user


def _graph(client, headers: dict[str, str], risk_id: str, *, depth: int = 1):
    return client.get(f"/api/v1/compliance/risks/{risk_id}/graph?depth={depth}", headers=headers)


def _seed_graph_fixture(db_session, org_id: str, owner_user_id: str):
    org_uuid = uuid.UUID(org_id)
    owner_uuid = uuid.UUID(owner_user_id)
    now = datetime.now(UTC)

    risk = Risk(
        organization_id=org_uuid,
        title="Data Processor Concentration",
        category="operational",
        severity="high",
        likelihood=4,
        impact=4,
        inherent_score=16,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=owner_uuid,
    )
    db_session.add(risk)
    db_session.flush()

    control = Control(
        organization_id=org_uuid,
        title="Quarterly Vendor Review",
        status="active",
        control_type="process",
        criticality="high",
        owner_user_id=owner_uuid,
    )
    db_session.add(control)
    db_session.flush()

    db_session.add(
        RiskControlLink(
            organization_id=org_uuid,
            risk_id=risk.id,
            control_id=control.id,
            status="active",
            link_type="mitigates",
        )
    )

    vendor = Vendor(
        organization_id=org_uuid,
        name="Vendor A",
        vendor_type="cloud",
        owner_user_id=owner_uuid,
        risk_tier="high",
        status="active",
    )
    db_session.add(vendor)
    db_session.flush()

    db_session.add(
        VendorControlLink(
            organization_id=org_uuid,
            vendor_id=vendor.id,
            control_id=control.id,
            status="active",
            linked_by_user_id=owner_uuid,
        )
    )
    db_session.add(
        VendorRiskScore(
            organization_id=org_uuid,
            vendor_id=vendor.id,
            assessment_id=None,
            likelihood="high",
            impact="high",
            inherent_risk_score=16,
            risk_level="high",
            score_explanation_json={"source": "seed"},
            scored_by_user_id=owner_uuid,
            notes="seed",
        )
    )

    framework = Framework(
        code=f"FW-{uuid.uuid4().hex[:8]}",
        name="SOC 2",
        category="security",
        jurisdiction="US",
    )
    db_session.add(framework)
    db_session.flush()

    obligation = Obligation(
        framework_id=framework.id,
        reference_code="CC1.2",
        title="Governance Obligation",
        jurisdiction="US",
        status="compliant",
    )
    db_session.add(obligation)
    db_session.flush()

    db_session.add(
        ControlObligationMapping(
            organization_id=org_uuid,
            control_id=control.id,
            obligation_id=obligation.id,
            status="active",
            mapping_type="supports",
        )
    )

    evidence = EvidenceItem(
        organization_id=org_uuid,
        title="Vendor review report",
        evidence_type="document",
        status="approved",
        valid_until=now + timedelta(days=90),
        uploaded_by_user_id=owner_uuid,
    )
    db_session.add(evidence)
    db_session.flush()

    db_session.add(
        EvidenceControlLink(
            organization_id=org_uuid,
            control_id=control.id,
            evidence_item_id=evidence.id,
            link_status="active",
        )
    )
    db_session.add(
        RiskEvidenceLink(
            organization_id=org_uuid,
            risk_id=risk.id,
            evidence_item_id=evidence.id,
            link_type="supports_assessment",
            status="active",
            linked_by_user_id=owner_uuid,
        )
    )

    policy = CompliancePolicy(
        organization_id=org_uuid,
        title="Vendor Management Policy",
        policy_type="security",
        status="approved",
        owner_user_id=owner_uuid,
        review_due_date=(now + timedelta(days=90)).date(),
    )
    db_session.add(policy)
    db_session.flush()

    db_session.add(
        CompliancePolicyControlLink(
            organization_id=org_uuid,
            policy_id=policy.id,
            control_id=control.id,
            status="active",
            linked_by_user_id=owner_uuid,
        )
    )

    db_session.commit()

    return {
        "risk_id": str(risk.id),
        "control_id": str(control.id),
        "vendor_id": str(vendor.id),
        "obligation_id": str(obligation.id),
        "evidence_id": str(evidence.id),
        "policy_id": str(policy.id),
    }


def test_a13_graph_returns_expected_node_types(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-types")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    response = _graph(client, org["org_headers"], fixture["risk_id"], depth=1)
    assert response.status_code == 200
    body = response.json()

    types = {node["node_type"] for node in body["nodes"]}
    assert {"control", "vendor", "obligation", "evidence", "policy"}.issubset(types)
    edges = {(edge["source_id"], edge["target_id"], edge["relationship"]) for edge in body["edges"]}
    assert (fixture["risk_id"], fixture["evidence_id"], "has_evidence") in edges
    assert (fixture["risk_id"], fixture["vendor_id"], "vendor_risk_factor") in edges


def test_a13_depth1_returns_only_direct_links(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-d1")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    response = _graph(client, org["org_headers"], fixture["risk_id"], depth=1)
    assert response.status_code == 200
    body = response.json()

    assert all(edge["source_id"] == fixture["risk_id"] for edge in body["edges"])


def test_a13_depth2_returns_second_degree_links_from_controls(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-d2")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    response = _graph(client, org["org_headers"], fixture["risk_id"], depth=2)
    assert response.status_code == 200
    body = response.json()

    second_degree_edges = [e for e in body["edges"] if e["source_id"] == fixture["control_id"]]
    assert len(second_degree_edges) >= 1
    assert body["summary"]["depth_reached"] == 2


def test_a13_depth2_deduplicates_nodes_seen_at_both_levels(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-dedup")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    response = _graph(client, org["org_headers"], fixture["risk_id"], depth=2)
    assert response.status_code == 200
    body = response.json()

    vendor_nodes = [n for n in body["nodes"] if n["node_id"] == fixture["vendor_id"]]
    assert len(vendor_nodes) == 1

    risk_edge = [
        e
        for e in body["edges"]
        if e["source_id"] == fixture["risk_id"] and e["target_id"] == fixture["vendor_id"] and e["relationship"] == "affects"
    ]
    control_edge = [
        e
        for e in body["edges"]
        if e["source_id"] == fixture["control_id"] and e["target_id"] == fixture["vendor_id"]
    ]
    assert len(risk_edge) == 1
    assert len(control_edge) == 1


def test_a13_health_control_healthy_active_with_approved_evidence(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-hc-healthy")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    body = _graph(client, org["org_headers"], fixture["risk_id"], depth=1).json()
    control = next(node for node in body["nodes"] if node["node_type"] == "control")
    assert control["health"] == "healthy"


def test_a13_health_control_degraded_active_with_expiring_evidence(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-hc-degraded")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    evidence = db_session.query(EvidenceItem).filter(EvidenceItem.id == uuid.UUID(fixture["evidence_id"])).one()
    evidence.valid_until = datetime.now(UTC) + timedelta(days=7)
    db_session.commit()

    body = _graph(client, org["org_headers"], fixture["risk_id"], depth=1).json()
    control = next(node for node in body["nodes"] if node["node_type"] == "control")
    assert control["health"] == "degraded"


def test_a13_health_control_critical_inactive(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-hc-critical")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    control = db_session.query(Control).filter(Control.id == uuid.UUID(fixture["control_id"])).one()
    control.status = "inactive"
    db_session.commit()

    body = _graph(client, org["org_headers"], fixture["risk_id"], depth=1).json()
    control_node = next(node for node in body["nodes"] if node["node_type"] == "control")
    assert control_node["health"] == "critical"


def test_a13_health_evidence_critical_expired(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-he-critical")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    evidence = db_session.query(EvidenceItem).filter(EvidenceItem.id == uuid.UUID(fixture["evidence_id"])).one()
    evidence.valid_until = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()

    body = _graph(client, org["org_headers"], fixture["risk_id"], depth=1).json()
    evidence_node = next(node for node in body["nodes"] if node["node_type"] == "evidence")
    assert evidence_node["health"] == "critical"


def test_a13_health_policy_degraded_approved_review_due_soon(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-hp-degraded")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    policy = db_session.query(CompliancePolicy).filter(CompliancePolicy.id == uuid.UUID(fixture["policy_id"])).one()
    policy.review_due_date = (datetime.now(UTC) + timedelta(days=10)).date()
    db_session.commit()

    body = _graph(client, org["org_headers"], fixture["risk_id"], depth=1).json()
    policy_node = next(node for node in body["nodes"] if node["node_type"] == "policy")
    assert policy_node["health"] == "degraded"


def test_a13_risk_with_no_links_returns_empty_graph_with_zero_summary(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-empty")
    org_uuid = uuid.UUID(org["organization_id"])
    owner_uuid = uuid.UUID(org["user_id"])

    risk = Risk(
        organization_id=org_uuid,
        title="Isolated Risk",
        category="operational",
        severity="medium",
        likelihood=2,
        impact=2,
        inherent_score=4,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=owner_uuid,
    )
    db_session.add(risk)
    db_session.commit()

    response = _graph(client, org["org_headers"], str(risk.id), depth=1)
    assert response.status_code == 200
    body = response.json()

    assert body["nodes"] == []
    assert body["edges"] == []
    assert body["summary"]["total_nodes"] == 0
    assert body["summary"]["by_type"]["control"] == 0
    assert body["summary"]["by_health"]["healthy"] == 0


def test_a13_risk_not_in_org_returns_404(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a13-404-a")
    org2 = bootstrap_org_user(client, email_prefix="a13-404-b")
    fixture = _seed_graph_fixture(db_session, org1["organization_id"], org1["user_id"])

    response = _graph(client, org2["org_headers"], fixture["risk_id"], depth=1)
    assert response.status_code == 404


def test_a13_invalid_depth_returns_422(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-depth-val")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    too_low = client.get(f"/api/v1/compliance/risks/{fixture['risk_id']}/graph?depth=0", headers=org["org_headers"])
    assert too_low.status_code == 422

    too_high = client.get(f"/api/v1/compliance/risks/{fixture['risk_id']}/graph?depth=3", headers=org["org_headers"])
    assert too_high.status_code == 422


def test_a13_summary_counts_match_nodes_and_edges_reference_real_ids(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a13-summary")
    fixture = _seed_graph_fixture(db_session, org["organization_id"], org["user_id"])

    response = _graph(client, org["org_headers"], fixture["risk_id"], depth=2)
    assert response.status_code == 200
    body = response.json()

    nodes = body["nodes"]
    summary = body["summary"]
    assert summary["total_nodes"] == len(nodes)

    calculated_by_type: dict[str, int] = {}
    calculated_by_health: dict[str, int] = {}
    node_ids = {n["node_id"] for n in nodes}

    for node in nodes:
        calculated_by_type[node["node_type"]] = calculated_by_type.get(node["node_type"], 0) + 1
        calculated_by_health[node["health"]] = calculated_by_health.get(node["health"], 0) + 1

    for key, value in calculated_by_type.items():
        assert summary["by_type"][key] == value
    for key, value in calculated_by_health.items():
        assert summary["by_health"][key] == value

    assert str(body["risk"]["id"]) == fixture["risk_id"]
    valid_sources = {fixture["risk_id"]} | node_ids
    for edge in body["edges"]:
        assert edge["source_id"] in valid_sources
        assert edge["target_id"] in node_ids


def test_a13_tenant_isolation_cannot_access_other_org_graph(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a13-tenant-a")
    org2 = bootstrap_org_user(client, email_prefix="a13-tenant-b")

    fixture = _seed_graph_fixture(db_session, org1["organization_id"], org1["user_id"])

    response = _graph(client, org2["org_headers"], fixture["risk_id"], depth=2)
    assert response.status_code == 404
