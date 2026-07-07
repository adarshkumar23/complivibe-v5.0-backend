from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.compliance.services.entity_risk_score_service import EntityRiskScoreService
from app.core.event_bus import EventBus, EventPayload, EventType
from app.core.startup import register_event_listeners
from app.models.audit_log import AuditLog
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.entity_risk_score import EntityRiskScore
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/risk-scores"


@pytest.fixture(autouse=True)
def _reset_event_bus() -> None:
    bus = EventBus.get_instance()
    bus.clear_listeners()
    register_event_listeners()
    yield
    bus.clear_listeners()


def _create_risk(client, headers: dict[str, str], *, title: str, likelihood: int, impact: int) -> str:
    response = client.post(
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
    assert response.status_code == 201
    return response.json()["id"]


def _create_control(client, headers: dict[str, str], *, title: str) -> str:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={
            "title": title,
            "control_type": "process",
            "criticality": "high",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _link_risk_control(client, headers: dict[str, str], *, risk_id: str, control_id: str) -> None:
    response = client.post(
        f"/api/v1/risks/{risk_id}/controls",
        headers=headers,
        json={"control_id": control_id, "link_type": "mitigates"},
    )
    assert response.status_code == 200


def _create_vendor(client, headers: dict[str, str], *, owner_user_id: str, name: str = "Vendor") -> str:
    response = client.post(
        "/api/v1/compliance/vendors",
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
            "risk_tier": "high",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _link_vendor_control(client, headers: dict[str, str], *, vendor_id: str, control_id: str) -> None:
    response = client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/links/controls",
        headers=headers,
        json={"control_id": control_id, "link_reason": "required"},
    )
    assert response.status_code == 201


def _setup_vendor_with_two_linked_risks(client, headers: dict[str, str], owner_user_id: str) -> tuple[str, list[str]]:
    vendor_id = _create_vendor(client, headers, owner_user_id=owner_user_id, name="Vendor A16")

    risk_1 = _create_risk(client, headers, title="Risk 10", likelihood=2, impact=5)  # 10
    risk_2 = _create_risk(client, headers, title="Risk 20", likelihood=4, impact=5)  # 20

    control_1 = _create_control(client, headers, title="Control 1")
    control_2 = _create_control(client, headers, title="Control 2")

    _link_risk_control(client, headers, risk_id=risk_1, control_id=control_1)
    _link_risk_control(client, headers, risk_id=risk_2, control_id=control_2)

    _link_vendor_control(client, headers, vendor_id=vendor_id, control_id=control_1)
    _link_vendor_control(client, headers, vendor_id=vendor_id, control_id=control_2)

    return vendor_id, [risk_1, risk_2]


def test_a16_compute_vendor_entity_score_equal_weight_scaled(client):
    org = bootstrap_org_user(client, email_prefix="a16-vendor-eq")
    vendor_id, _ = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    response = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id, "score_method": "equal_weight"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["risk_count"] == 2
    assert body["composite_score"] == 60.0
    assert body["score_band"] == "high"


def test_a16_compute_framework_entity_score(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a16-framework")
    org_id = uuid.UUID(org["organization_id"])

    framework = Framework(
        code=f"A16-{uuid.uuid4().hex[:8]}",
        name="A16 Framework",
        category="security",
        jurisdiction="US",
        status="active",
    )
    db_session.add(framework)
    db_session.flush()

    db_session.add(
        OrganizationFramework(
            organization_id=org_id,
            framework_id=framework.id,
            status="active",
        )
    )

    obligation = Obligation(
        framework_id=framework.id,
        reference_code="A16-1",
        title="A16 Obligation",
        jurisdiction="US",
        status="active",
    )
    db_session.add(obligation)
    db_session.commit()

    risk_id = _create_risk(client, org["org_headers"], title="Framework Risk", likelihood=5, impact=5)
    control_id = _create_control(client, org["org_headers"], title="Framework Control")
    _link_risk_control(client, org["org_headers"], risk_id=risk_id, control_id=control_id)

    db_session.add(
        ControlObligationMapping(
            organization_id=org_id,
            control_id=uuid.UUID(control_id),
            obligation_id=obligation.id,
            status="active",
            mapping_type="supports",
            confidence="manual_confirmed",
        )
    )
    db_session.commit()

    response = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "framework", "entity_id": str(framework.id), "score_method": "equal_weight"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["risk_count"] == 1
    assert body["composite_score"] == 100.0
    assert body["score_band"] == "critical"


def test_a16_score_method_max_score_returns_scaled_max(client):
    org = bootstrap_org_user(client, email_prefix="a16-max")
    vendor_id, _ = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    response = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id, "score_method": "max_score"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["composite_score"] == 80.0
    assert body["score_method"] == "max_score"


def test_a16_zero_linked_risks_returns_none_band(client):
    org = bootstrap_org_user(client, email_prefix="a16-zero")
    vendor_id = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="No Links")

    response = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["composite_score"] == 0.0
    assert body["score_band"] == "none"
    assert body["risk_count"] == 0


def test_a16_score_band_boundaries():
    assert EntityRiskScoreService._score_band(75.0) == "critical"
    assert EntityRiskScoreService._score_band(50.0) == "high"
    assert EntityRiskScoreService._score_band(25.0) == "medium"
    assert EntityRiskScoreService._score_band(0.01) == "low"
    assert EntityRiskScoreService._score_band(0.0) == "none"


def test_a16_immutability_two_computes_create_two_rows(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a16-immut")
    org_id = uuid.UUID(org["organization_id"])
    vendor_id, _ = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    first = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    second = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    rows = db_session.execute(
        select(EntityRiskScore).where(
            EntityRiskScore.organization_id == org_id,
            EntityRiskScore.entity_type == "vendor",
            EntityRiskScore.entity_id == uuid.UUID(vendor_id),
        )
    ).scalars().all()
    assert len(rows) == 2


def test_a16_get_latest_history_and_all_latest(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a16-history")
    org_id = uuid.UUID(org["organization_id"])
    vendor_id, _ = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    for _ in range(3):
        resp = client.post(
            f"{BASE}/compute-entity",
            headers=org["org_headers"],
            json={"entity_type": "vendor", "entity_id": vendor_id},
        )
        assert resp.status_code == 201

    latest = EntityRiskScoreService.get_latest("vendor", uuid.UUID(vendor_id), org_id, db_session)
    assert latest is not None

    history = EntityRiskScoreService.get_history("vendor", uuid.UUID(vendor_id), org_id, db_session, limit=2)
    assert len(history) == 2
    assert history[0].computed_at >= history[1].computed_at

    all_latest = EntityRiskScoreService.get_all_latest("vendor", org_id, db_session)
    assert len(all_latest) == 1
    assert all_latest[0].entity_id == uuid.UUID(vendor_id)


def test_a16_entity_not_found_returns_404(client):
    org = bootstrap_org_user(client, email_prefix="a16-missing")

    response = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


def test_a16_entity_label_denormalized_at_compute_time(client):
    org = bootstrap_org_user(client, email_prefix="a16-label")
    vendor_id, _ = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    first = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert first.status_code == 201
    assert first.json()["entity_label"] == "Vendor A16"

    rename = client.patch(
        f"/api/v1/compliance/vendors/{vendor_id}",
        headers=org["org_headers"],
        json={"name": "Vendor Renamed"},
    )
    assert rename.status_code == 200

    second = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert second.status_code == 201
    assert second.json()["entity_label"] == "Vendor Renamed"

    history = client.get(
        f"{BASE}/by-entity",
        headers=org["org_headers"],
        params={"entity_type": "vendor", "entity_id": vendor_id, "include_history": True},
    )
    assert history.status_code == 200
    labels = [row["entity_label"] for row in history.json()]
    assert "Vendor A16" in labels
    assert "Vendor Renamed" in labels


def test_a16_component_risks_json_contains_expected_fields(client):
    org = bootstrap_org_user(client, email_prefix="a16-components")
    vendor_id, _ = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    response = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert response.status_code == 201
    components = response.json()["component_risks_json"]
    assert len(components) == 2
    for component in components:
        assert set(["risk_id", "risk_name", "score", "weight", "weighted_contribution"]).issubset(component.keys())


def test_a16_event_bus_risk_score_updated_recomputes_entity_scores(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a16-event")
    org_id = uuid.UUID(org["organization_id"])
    vendor_id, risk_ids = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    first = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert first.status_code == 201

    risk = db_session.execute(
        select(Risk).where(Risk.organization_id == org_id, Risk.id == uuid.UUID(risk_ids[0]))
    ).scalar_one()
    risk.inherent_score = 25
    db_session.commit()

    EventBus.get_instance().emit(
        EventType.RISK_SCORE_UPDATED,
        EventPayload(
            org_id=org_id,
            entity_type="risk",
            entity_id=uuid.UUID(risk_ids[0]),
            event_type=EventType.RISK_SCORE_UPDATED,
            previous_value=10,
            new_value=25,
            triggered_by="system",
            db=db_session,
        ),
    )

    rows = db_session.execute(
        select(EntityRiskScore).where(
            EntityRiskScore.organization_id == org_id,
            EntityRiskScore.entity_type == "vendor",
            EntityRiskScore.entity_id == uuid.UUID(vendor_id),
        )
    ).scalars().all()
    assert len(rows) >= 2


def test_a16_summary_endpoint_and_highest_risk_entities(client):
    org = bootstrap_org_user(client, email_prefix="a16-summary")
    vendor_1, _ = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])
    vendor_2 = _create_vendor(client, org["org_headers"], owner_user_id=org["user_id"], name="Vendor B")

    c = _create_control(client, org["org_headers"], title="Control 3")
    r = _create_risk(client, org["org_headers"], title="Risk 25", likelihood=5, impact=5)
    _link_risk_control(client, org["org_headers"], risk_id=r, control_id=c)
    _link_vendor_control(client, org["org_headers"], vendor_id=vendor_2, control_id=c)

    compute_1 = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_1},
    )
    compute_2 = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_2},
    )
    assert compute_1.status_code == 201
    assert compute_2.status_code == 201

    summary = client.get(f"{BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()

    assert body["by_entity_type"]["vendor"]["total_scored"] == 2
    assert len(body["highest_risk_entities"]) >= 1
    assert body["highest_risk_entities"][0]["composite_score"] >= body["highest_risk_entities"][-1]["composite_score"]


def test_a16_by_entity_include_history_modes(client):
    org = bootstrap_org_user(client, email_prefix="a16-by-entity")
    vendor_id, _ = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    for _ in range(2):
        resp = client.post(
            f"{BASE}/compute-entity",
            headers=org["org_headers"],
            json={"entity_type": "vendor", "entity_id": vendor_id},
        )
        assert resp.status_code == 201

    latest = client.get(
        f"{BASE}/by-entity",
        headers=org["org_headers"],
        params={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert latest.status_code == 200
    assert isinstance(latest.json(), dict)

    history = client.get(
        f"{BASE}/by-entity",
        headers=org["org_headers"],
        params={"entity_type": "vendor", "entity_id": vendor_id, "include_history": True},
    )
    assert history.status_code == 200
    assert isinstance(history.json(), list)
    assert len(history.json()) == 2


def test_a16_fresh_score_not_flagged_stale(client):
    org = bootstrap_org_user(client, email_prefix="a16-fresh")
    vendor_id, _ = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    resp = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert resp.status_code == 201

    latest = client.get(
        f"{BASE}/by-entity",
        headers=org["org_headers"],
        params={"entity_type": "vendor", "entity_id": vendor_id},
    )
    body = latest.json()
    assert body["stale"] is False
    assert body["stale_reasons"] == []


def test_a16_flagged_stale_when_component_risk_score_changes_after_computation(client):
    org = bootstrap_org_user(client, email_prefix="a16-stale-score")
    vendor_id, risk_ids = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    resp = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert resp.status_code == 201

    # Re-assess one of the component risks upward after the score snapshot was taken.
    patch_resp = client.patch(
        f"/api/v1/risks/{risk_ids[0]}",
        headers=org["org_headers"],
        json={"likelihood": 5, "impact": 5},
    )
    assert patch_resp.status_code == 200

    latest = client.get(
        f"{BASE}/by-entity",
        headers=org["org_headers"],
        params={"entity_type": "vendor", "entity_id": vendor_id},
    )
    body = latest.json()
    assert body["stale"] is True
    assert any("inherent_score changed" in reason for reason in body["stale_reasons"])


def test_a16_flagged_stale_when_new_risk_linked_after_computation(client):
    org = bootstrap_org_user(client, email_prefix="a16-stale-newrisk")
    vendor_id, risk_ids = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    resp = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert resp.status_code == 201

    new_risk = _create_risk(client, org["org_headers"], title="Risk 30", likelihood=3, impact=5)
    new_control = _create_control(client, org["org_headers"], title="Control 3")
    _link_risk_control(client, org["org_headers"], risk_id=new_risk, control_id=new_control)
    _link_vendor_control(client, org["org_headers"], vendor_id=vendor_id, control_id=new_control)

    latest = client.get(
        f"{BASE}/by-entity",
        headers=org["org_headers"],
        params={"entity_type": "vendor", "entity_id": vendor_id},
    )
    body = latest.json()
    assert body["stale"] is True
    assert any("not included in this score" in reason for reason in body["stale_reasons"])
    assert any("linked risk count changed" in reason for reason in body["stale_reasons"])

    # Recomputing clears the staleness for the new latest snapshot.
    recompute = client.post(
        f"{BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert recompute.status_code == 201
    refreshed = client.get(
        f"{BASE}/by-entity",
        headers=org["org_headers"],
        params={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert refreshed.json()["stale"] is False


def test_a16_audit_event_emitted_on_every_compute(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a16-audit")
    org_id = uuid.UUID(org["organization_id"])
    vendor_id, _ = _setup_vendor_with_two_linked_risks(client, org["org_headers"], org["user_id"])

    for _ in range(2):
        response = client.post(
            f"{BASE}/compute-entity",
            headers=org["org_headers"],
            json={"entity_type": "vendor", "entity_id": vendor_id},
        )
        assert response.status_code == 201

    rows = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.action == "entity_risk_score.computed",
        )
    ).scalars().all()
    assert len(rows) >= 2


def test_a16_tenant_isolation_between_orgs(client):
    org_a = bootstrap_org_user(client, email_prefix="a16-tenant-a")
    org_b = bootstrap_org_user(client, email_prefix="a16-tenant-b")

    vendor_id, _ = _setup_vendor_with_two_linked_risks(client, org_a["org_headers"], org_a["user_id"])
    compute = client.post(
        f"{BASE}/compute-entity",
        headers=org_a["org_headers"],
        json={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert compute.status_code == 201

    cross = client.get(
        f"{BASE}/by-entity",
        headers=org_b["org_headers"],
        params={"entity_type": "vendor", "entity_id": vendor_id},
    )
    assert cross.status_code == 404
