from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.compliance.services.entity_risk_score_service import EntityRiskScoreService
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.data_asset import DataAsset
from app.models.data_asset_risk_link import DataAssetRiskLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.org_risk_settings import OrgRiskSettings
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink
from app.models.risk_evidence_link import RiskEvidenceLink
from app.models.vendor import Vendor
from app.models.vendor_control_link import VendorControlLink
from tests.helpers.auth_org import bootstrap_org_user


def _create_risk(client, headers: dict[str, str], title: str, likelihood: int, impact: int) -> str:
    resp = client.post(
        "/api/v1/risks",
        headers=headers,
        json={
            "title": title,
            "category": "operational",
            "likelihood": likelihood,
            "impact": impact,
            "treatment_strategy": "mitigate",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_control(client, headers: dict[str, str], title: str) -> str:
    resp = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "process", "criticality": "high"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _link_risk_control(client, headers: dict[str, str], risk_id: str, control_id: str) -> None:
    resp = client.post(
        f"/api/v1/risks/{risk_id}/controls",
        headers=headers,
        json={"control_id": control_id, "link_type": "mitigates"},
    )
    assert resp.status_code == 200


def test_s4_p2_risk_graph_includes_evidence_nodes_and_has_evidence_edges(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p2-graph-ev")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    risk_id = _create_risk(client, org["org_headers"], "Graph risk evidence", 3, 4)
    evidence = EvidenceItem(
        organization_id=org_id,
        title="Risk Evidence",
        evidence_type="document",
        status="approved",
        uploaded_by_user_id=user_id,
    )
    db_session.add(evidence)
    db_session.flush()
    db_session.add(
        RiskEvidenceLink(
            organization_id=org_id,
            risk_id=uuid.UUID(risk_id),
            evidence_item_id=evidence.id,
            status="active",
            link_type="supports_assessment",
            linked_by_user_id=user_id,
        )
    )
    db_session.commit()

    resp = client.get(f"/api/v1/compliance/risks/{risk_id}/graph?depth=1", headers=org["org_headers"])
    assert resp.status_code == 200
    body = resp.json()
    evidence_nodes = [n for n in body["nodes"] if n["node_type"] == "evidence" and n["node_id"] == str(evidence.id)]
    assert len(evidence_nodes) == 1
    assert any(
        e["source_id"] == risk_id and e["target_id"] == str(evidence.id) and e["relationship"] == "has_evidence"
        for e in body["edges"]
    )


def test_s4_p2_risk_graph_includes_vendor_nodes_and_vendor_risk_factor_edges(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p2-graph-vendor")

    risk_id = _create_risk(client, org["org_headers"], "Graph risk vendor", 3, 3)
    control_id = _create_control(client, org["org_headers"], "Graph control")
    _link_risk_control(client, org["org_headers"], risk_id, control_id)

    vendor_resp = client.post(
        "/api/v1/compliance/vendors",
        headers=org["org_headers"],
        json={"name": "Graph Vendor", "vendor_type": "software", "owner_user_id": org["user_id"], "risk_tier": "high"},
    )
    assert vendor_resp.status_code == 201
    vendor_id = vendor_resp.json()["id"]

    link_resp = client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/links/controls",
        headers=org["org_headers"],
        json={"control_id": control_id, "link_reason": "required"},
    )
    assert link_resp.status_code == 201
    score_resp = client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/risk-scores",
        headers=org["org_headers"],
        json={"likelihood": "high", "impact": "high"},
    )
    assert score_resp.status_code == 201

    resp = client.get(f"/api/v1/compliance/risks/{risk_id}/graph?depth=1", headers=org["org_headers"])
    assert resp.status_code == 200
    body = resp.json()
    vendor_nodes = [n for n in body["nodes"] if n["node_type"] == "vendor" and n["node_id"] == vendor_id]
    assert len(vendor_nodes) == 1
    assert any(
        e["source_id"] == risk_id and e["target_id"] == vendor_id and e["relationship"] == "vendor_risk_factor"
        for e in body["edges"]
    )


def test_s4_p2_risk_graph_is_additive_with_existing_node_types(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p2-graph-additive")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    risk_id = _create_risk(client, org["org_headers"], "Graph additive risk", 4, 3)
    control_id = _create_control(client, org["org_headers"], "Graph additive control")
    _link_risk_control(client, org["org_headers"], risk_id, control_id)

    framework = Framework(code=f"FW-{uuid.uuid4().hex[:8]}", name="Graph FW", category="security", jurisdiction="US")
    db_session.add(framework)
    db_session.flush()
    obligation = Obligation(
        framework_id=framework.id,
        reference_code="A.1",
        title="Graph Obligation",
        jurisdiction="US",
        status="compliant",
    )
    db_session.add(obligation)
    db_session.flush()
    db_session.add(
        ControlObligationMapping(
            organization_id=org_id,
            control_id=uuid.UUID(control_id),
            obligation_id=obligation.id,
            status="active",
            mapping_type="supports",
        )
    )

    evidence = EvidenceItem(
        organization_id=org_id,
        title="Graph additive evidence",
        evidence_type="document",
        status="approved",
        uploaded_by_user_id=user_id,
    )
    db_session.add(evidence)
    db_session.flush()
    db_session.add(
        RiskEvidenceLink(
            organization_id=org_id,
            risk_id=uuid.UUID(risk_id),
            evidence_item_id=evidence.id,
            status="active",
            linked_by_user_id=user_id,
        )
    )
    db_session.commit()

    resp = client.get(f"/api/v1/compliance/risks/{risk_id}/graph?depth=1", headers=org["org_headers"])
    assert resp.status_code == 200
    types = {node["node_type"] for node in resp.json()["nodes"]}
    assert "control" in types
    assert "obligation" in types
    assert "evidence" in types


def test_s4_p2_risk_graph_without_evidence_or_vendor_links_returns_cleanly(client):
    org = bootstrap_org_user(client, email_prefix="s4p2-graph-empty")
    risk_id = _create_risk(client, org["org_headers"], "Graph empty risk", 2, 2)

    resp = client.get(f"/api/v1/compliance/risks/{risk_id}/graph?depth=1", headers=org["org_headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert [n for n in body["nodes"] if n["node_type"] == "evidence"] == []
    assert [n for n in body["nodes"] if n["node_type"] == "vendor"] == []


def test_s4_p2_entity_vendor_weighted_avg_uses_org_settings_weights(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p2-entity-vendor")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    db_session.add(
        OrgRiskSettings(
            organization_id=org_id,
            financial_weight=Decimal("0.800"),
            brand_weight=Decimal("0.100"),
            operational_weight=Decimal("0.100"),
            updated_by_user_id=user_id,
        )
    )

    vendor = Vendor(
        organization_id=org_id,
        name="Weighted Vendor",
        vendor_type="software",
        owner_user_id=user_id,
        risk_tier="high",
        status="active",
    )
    db_session.add(vendor)
    db_session.flush()

    r1 = Risk(
        organization_id=org_id,
        title="Weighted R1",
        category="operational",
        severity="high",
        likelihood=2,
        impact=2,
        inherent_score=4,
        financial_impact=5,
        brand_impact=1,
        operational_impact=1,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=user_id,
    )
    r2 = Risk(
        organization_id=org_id,
        title="Weighted R2",
        category="operational",
        severity="high",
        likelihood=5,
        impact=3,
        inherent_score=15,
        financial_impact=1,
        brand_impact=5,
        operational_impact=5,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=user_id,
    )
    c1 = Control(organization_id=org_id, title="WV-C1", status="active", control_type="process", criticality="high", owner_user_id=user_id)
    c2 = Control(organization_id=org_id, title="WV-C2", status="active", control_type="process", criticality="high", owner_user_id=user_id)
    db_session.add_all([r1, r2, c1, c2])
    db_session.flush()
    db_session.add_all(
        [
            RiskControlLink(organization_id=org_id, risk_id=r1.id, control_id=c1.id, status="active", link_type="mitigates"),
            RiskControlLink(organization_id=org_id, risk_id=r2.id, control_id=c2.id, status="active", link_type="mitigates"),
            VendorControlLink(organization_id=org_id, vendor_id=vendor.id, control_id=c1.id, status="active", linked_by_user_id=user_id),
            VendorControlLink(organization_id=org_id, vendor_id=vendor.id, control_id=c2.id, status="active", linked_by_user_id=user_id),
        ]
    )
    db_session.commit()

    weighted_row = EntityRiskScoreService.compute("vendor", vendor.id, org_id, "weighted_avg", db_session, user_id)
    equal_row = EntityRiskScoreService.compute("vendor", vendor.id, org_id, "equal_weight", db_session, user_id)
    db_session.commit()

    assert float(weighted_row.composite_score) != float(equal_row.composite_score)


def test_s4_p2_entity_data_asset_scoring_uses_data_asset_risk_links(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p2-entity-asset")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    asset = DataAsset(
        organization_id=org_id,
        name="Customer Warehouse",
        asset_type="database",
        owner_id=user_id,
        custodian_id=None,
        sensitivity_tier="confidential",
        classification_type="personal_data",
        classification_confidence=Decimal("0.90"),
        classification_source="manual",
        classification_confirmed=True,
        geographic_locations=[],
        permitted_regions=[],
        schema_column_names=None,
        retention_policy_days=None,
        retention_review_date=None,
        data_volume_estimate=None,
        source_system=None,
        import_source=None,
        import_key=None,
        tags=[],
        is_phi=False,
        hipaa_safeguard_required=None,
        status="active",
        created_by=user_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        deleted_at=None,
    )
    risk = Risk(
        organization_id=org_id,
        title="Asset Risk",
        category="operational",
        severity="high",
        likelihood=4,
        impact=4,
        inherent_score=16,
        treatment_strategy="mitigate",
        status="identified",
        owner_user_id=user_id,
    )
    db_session.add_all([asset, risk])
    db_session.flush()
    db_session.add(
        DataAssetRiskLink(
            organization_id=org_id,
            data_asset_id=asset.id,
            risk_id=risk.id,
            created_by=user_id,
        )
    )
    db_session.commit()

    row = EntityRiskScoreService.compute("data_asset", asset.id, org_id, "weighted_avg", db_session, user_id)
    db_session.commit()
    assert float(row.composite_score) > 0.0
    assert row.risk_count == 1


def test_s4_p2_entity_weighted_avg_creates_default_org_settings_when_missing(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p2-entity-default")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    vendor = Vendor(
        organization_id=org_id,
        name="Default Settings Vendor",
        vendor_type="software",
        owner_user_id=user_id,
        risk_tier="medium",
        status="active",
    )
    db_session.add(vendor)
    db_session.commit()

    row = EntityRiskScoreService.compute("vendor", vendor.id, org_id, "weighted_avg", db_session, user_id)
    db_session.commit()

    settings = db_session.execute(select(OrgRiskSettings).where(OrgRiskSettings.organization_id == org_id)).scalar_one_or_none()
    assert settings is not None
    assert float(row.composite_score) == 0.0


def test_s4_p2_entity_with_no_linked_risks_returns_zero_score(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s4p2-entity-zero")
    org_id = uuid.UUID(org["organization_id"])
    user_id = uuid.UUID(org["user_id"])

    vendor = Vendor(
        organization_id=org_id,
        name="No Risk Vendor",
        vendor_type="software",
        owner_user_id=user_id,
        risk_tier="low",
        status="active",
    )
    db_session.add(vendor)
    db_session.commit()

    row = EntityRiskScoreService.compute("vendor", vendor.id, org_id, "weighted_avg", db_session, user_id)
    db_session.commit()
    assert float(row.composite_score) == 0.0
    assert row.risk_count == 0
