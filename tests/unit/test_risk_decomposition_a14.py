import uuid

from app.compliance.services.risk_scoring_service import RiskScoringService
from app.models.org_risk_settings import OrgRiskSettings
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user


def _create_risk(client, headers: dict[str, str], *, title: str = "Risk", likelihood: int = 2, impact: int = 2):
    return client.post(
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


def test_a14_standard_method_unchanged_likelihood_times_impact(client):
    org = bootstrap_org_user(client, email_prefix="a14-standard")

    created = _create_risk(client, org["org_headers"], title="Standard", likelihood=3, impact=4)
    assert created.status_code == 201
    assert created.json()["inherent_score"] == 12
    assert created.json()["composite_score_method"] == "standard"


def test_a14_factor_based_weighted_sum_and_scaling(client):
    org = bootstrap_org_user(client, email_prefix="a14-factor")

    put = client.put(
        "/api/v1/compliance/risk-settings",
        headers=org["org_headers"],
        json={"financial_weight": 0.4, "brand_weight": 0.3, "operational_weight": 0.3},
    )
    assert put.status_code == 200

    created = _create_risk(client, org["org_headers"], title="Factor", likelihood=2, impact=2)
    assert created.status_code == 201

    patched = client.patch(
        f"/api/v1/risks/{created.json()['id']}",
        headers=org["org_headers"],
        json={
            "composite_score_method": "factor_based",
            "financial_impact": 4,
            "brand_impact": 3,
            "operational_impact": 5,
        },
    )
    assert patched.status_code == 200
    assert patched.json()["inherent_score"] == 19
    assert patched.json()["composite_score_method"] == "factor_based"


def test_a14_factor_based_missing_impact_field_returns_422(client):
    org = bootstrap_org_user(client, email_prefix="a14-missing")
    created = _create_risk(client, org["org_headers"], title="Missing")
    assert created.status_code == 201

    patched = client.patch(
        f"/api/v1/risks/{created.json()['id']}",
        headers=org["org_headers"],
        json={
            "composite_score_method": "factor_based",
            "financial_impact": 4,
            "brand_impact": 3,
        },
    )
    assert patched.status_code == 422
    assert "Factor-based scoring requires" in patched.json()["detail"]


def test_a14_weight_sum_validation_rejects_non_1_0(client):
    org = bootstrap_org_user(client, email_prefix="a14-sum-reject")

    resp = client.put(
        "/api/v1/compliance/risk-settings",
        headers=org["org_headers"],
        json={"financial_weight": 0.4, "brand_weight": 0.3, "operational_weight": 0.4},
    )
    assert resp.status_code == 422
    assert "Weights must sum to 1.0." in resp.json()["detail"]


def test_a14_weight_sum_1_0_is_accepted(client):
    org = bootstrap_org_user(client, email_prefix="a14-sum-ok")

    resp = client.put(
        "/api/v1/compliance/risk-settings",
        headers=org["org_headers"],
        json={"financial_weight": 0.4, "brand_weight": 0.3, "operational_weight": 0.3},
    )
    assert resp.status_code == 200
    assert resp.json()["financial_weight"] == 0.4


def test_a14_get_or_create_org_settings_creates_defaults_when_missing(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a14-goc-create")
    org_id = uuid.UUID(org["organization_id"])

    row = RiskScoringService.get_or_create_org_settings(org_id, db_session)
    db_session.commit()

    assert float(row.financial_weight) == 0.4
    assert float(row.brand_weight) == 0.3
    assert float(row.operational_weight) == 0.3
    assert db_session.query(OrgRiskSettings).filter(OrgRiskSettings.organization_id == org_id).count() == 1


def test_a14_get_or_create_org_settings_returns_existing_without_duplicate(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a14-goc-existing")
    org_id = uuid.UUID(org["organization_id"])

    existing = OrgRiskSettings(
        organization_id=org_id,
        financial_weight=0.5,
        brand_weight=0.2,
        operational_weight=0.3,
    )
    db_session.add(existing)
    db_session.commit()

    row = RiskScoringService.get_or_create_org_settings(org_id, db_session)
    db_session.commit()

    assert row.id == existing.id
    assert db_session.query(OrgRiskSettings).filter(OrgRiskSettings.organization_id == org_id).count() == 1


def test_a14_score_breakdown_endpoint_factor_based(client):
    org = bootstrap_org_user(client, email_prefix="a14-breakdown-factor")

    put = client.put(
        "/api/v1/compliance/risk-settings",
        headers=org["org_headers"],
        json={"financial_weight": 0.4, "brand_weight": 0.3, "operational_weight": 0.3},
    )
    assert put.status_code == 200

    created = _create_risk(client, org["org_headers"], title="Breakdown Factor")
    assert created.status_code == 201

    patched = client.patch(
        f"/api/v1/risks/{created.json()['id']}",
        headers=org["org_headers"],
        json={
            "composite_score_method": "factor_based",
            "financial_impact": 4,
            "brand_impact": 3,
            "operational_impact": 5,
        },
    )
    assert patched.status_code == 200

    breakdown = client.get(
        f"/api/v1/compliance/risks/{created.json()['id']}/score-breakdown",
        headers=org["org_headers"],
    )
    assert breakdown.status_code == 200
    body = breakdown.json()
    assert body["method"] == "factor_based"
    assert body["scaled_score"] == 19
    assert body["factors"]["financial"]["impact_value"] == 4
    assert body["factors"]["financial"]["weight"] == 0.4


def test_a14_score_breakdown_endpoint_standard(client):
    org = bootstrap_org_user(client, email_prefix="a14-breakdown-standard")

    created = _create_risk(client, org["org_headers"], title="Breakdown Standard", likelihood=4, impact=2)
    assert created.status_code == 201

    breakdown = client.get(
        f"/api/v1/compliance/risks/{created.json()['id']}/score-breakdown",
        headers=org["org_headers"],
    )
    assert breakdown.status_code == 200
    body = breakdown.json()
    assert body == {"method": "standard", "likelihood": 4, "impact": 2, "score": 8}


def test_a14_score_auto_recomputes_on_risk_patch_when_factor_changes(client):
    org = bootstrap_org_user(client, email_prefix="a14-recompute")

    put = client.put(
        "/api/v1/compliance/risk-settings",
        headers=org["org_headers"],
        json={"financial_weight": 0.4, "brand_weight": 0.3, "operational_weight": 0.3},
    )
    assert put.status_code == 200

    created = _create_risk(client, org["org_headers"], title="Recompute")
    assert created.status_code == 201

    first = client.patch(
        f"/api/v1/risks/{created.json()['id']}",
        headers=org["org_headers"],
        json={
            "composite_score_method": "factor_based",
            "financial_impact": 4,
            "brand_impact": 3,
            "operational_impact": 5,
        },
    )
    assert first.status_code == 200
    assert first.json()["inherent_score"] == 19

    second = client.patch(
        f"/api/v1/risks/{created.json()['id']}",
        headers=org["org_headers"],
        json={"operational_impact": 2},
    )
    assert second.status_code == 200
    assert second.json()["inherent_score"] == 16


def test_a14_risk_settings_put_creates_new_settings(client):
    org = bootstrap_org_user(client, email_prefix="a14-put-create")

    resp = client.put(
        "/api/v1/compliance/risk-settings",
        headers=org["org_headers"],
        json={"financial_weight": 0.5, "brand_weight": 0.2, "operational_weight": 0.3},
    )
    assert resp.status_code == 200
    assert resp.json() == {"financial_weight": 0.5, "brand_weight": 0.2, "operational_weight": 0.3}


def test_a14_risk_settings_put_updates_existing_settings(client):
    org = bootstrap_org_user(client, email_prefix="a14-put-update")

    first = client.put(
        "/api/v1/compliance/risk-settings",
        headers=org["org_headers"],
        json={"financial_weight": 0.5, "brand_weight": 0.2, "operational_weight": 0.3},
    )
    assert first.status_code == 200

    second = client.put(
        "/api/v1/compliance/risk-settings",
        headers=org["org_headers"],
        json={"financial_weight": 0.4, "brand_weight": 0.3, "operational_weight": 0.3},
    )
    assert second.status_code == 200
    assert second.json()["financial_weight"] == 0.4


def test_a14_risk_settings_get_returns_defaults_without_creating_record(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a14-get-defaults")
    org_id = uuid.UUID(org["organization_id"])

    resp = client.get("/api/v1/compliance/risk-settings", headers=org["org_headers"])
    assert resp.status_code == 200
    assert resp.json() == {"financial_weight": 0.4, "brand_weight": 0.3, "operational_weight": 0.3}

    count = db_session.query(OrgRiskSettings).filter(OrgRiskSettings.organization_id == org_id).count()
    assert count == 0


def test_a14_org_risk_settings_updated_audit_event_context(client):
    org = bootstrap_org_user(client, email_prefix="a14-audit-settings")

    update = client.put(
        "/api/v1/compliance/risk-settings",
        headers=org["org_headers"],
        json={"financial_weight": 0.4, "brand_weight": 0.3, "operational_weight": 0.3},
    )
    assert update.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    rows = [row for row in logs.json() if row["action"] == "org_risk_settings.updated"]
    assert len(rows) >= 1
    context = rows[0]["metadata_json"]["context_json"]
    assert context["new_weights"] == {"financial": 0.4, "brand": 0.3, "operational": 0.3}
    assert context["updated_by_user_id"] == org["user_id"]


def test_a14_risk_score_method_changed_audit_event(client):
    org = bootstrap_org_user(client, email_prefix="a14-audit-method")

    created = _create_risk(client, org["org_headers"], title="Audit Method")
    assert created.status_code == 201

    changed = client.patch(
        f"/api/v1/risks/{created.json()['id']}",
        headers=org["org_headers"],
        json={
            "composite_score_method": "factor_based",
            "financial_impact": 4,
            "brand_impact": 3,
            "operational_impact": 5,
        },
    )
    assert changed.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    rows = [row for row in logs.json() if row["action"] == "risk.score_method_changed"]
    assert len(rows) >= 1
    context = rows[0]["metadata_json"]["context_json"]
    assert context["risk_id"] == created.json()["id"]
    assert context["previous_method"] == "standard"
    assert context["new_method"] == "factor_based"


def test_a14_tenant_isolation_org_settings_do_not_affect_other_org_scores(client):
    org_a = bootstrap_org_user(client, email_prefix="a14-tenant-a")
    org_b = bootstrap_org_user(client, email_prefix="a14-tenant-b")

    put_a = client.put(
        "/api/v1/compliance/risk-settings",
        headers=org_a["org_headers"],
        json={"financial_weight": 0.8, "brand_weight": 0.1, "operational_weight": 0.1},
    )
    assert put_a.status_code == 200

    risk_a = _create_risk(client, org_a["org_headers"], title="Org A")
    risk_b = _create_risk(client, org_b["org_headers"], title="Org B")
    assert risk_a.status_code == 201
    assert risk_b.status_code == 201

    patch_a = client.patch(
        f"/api/v1/risks/{risk_a.json()['id']}",
        headers=org_a["org_headers"],
        json={
            "composite_score_method": "factor_based",
            "financial_impact": 5,
            "brand_impact": 1,
            "operational_impact": 1,
        },
    )
    patch_b = client.patch(
        f"/api/v1/risks/{risk_b.json()['id']}",
        headers=org_b["org_headers"],
        json={
            "composite_score_method": "factor_based",
            "financial_impact": 5,
            "brand_impact": 1,
            "operational_impact": 1,
        },
    )
    assert patch_a.status_code == 200
    assert patch_b.status_code == 200

    assert patch_a.json()["inherent_score"] == 21
    assert patch_b.json()["inherent_score"] == 13


def test_a14_score_breakdown_404_for_risk_outside_org(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a14-breakdown-404-a")
    org_b = bootstrap_org_user(client, email_prefix="a14-breakdown-404-b")

    risk = _create_risk(client, org_a["org_headers"], title="Private")
    assert risk.status_code == 201

    forbidden = client.get(
        f"/api/v1/compliance/risks/{risk.json()['id']}/score-breakdown",
        headers=org_b["org_headers"],
    )
    assert forbidden.status_code == 404


def test_a14_direct_compute_score_standard_and_factor_based(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a14-direct")
    org_id = uuid.UUID(org["organization_id"])

    settings = RiskScoringService.get_or_create_org_settings(org_id, db_session)

    standard = Risk(
        organization_id=org_id,
        title="Std",
        category="operational",
        severity="low",
        likelihood=3,
        impact=4,
        inherent_score=1,
        treatment_strategy="mitigate",
        status="identified",
    )
    factor = Risk(
        organization_id=org_id,
        title="Fact",
        category="operational",
        severity="low",
        likelihood=1,
        impact=1,
        inherent_score=1,
        financial_impact=4,
        brand_impact=3,
        operational_impact=5,
        composite_score_method="factor_based",
        treatment_strategy="mitigate",
        status="identified",
    )

    assert RiskScoringService.compute_score(standard, settings) == 12
    assert RiskScoringService.compute_score(factor, settings) == 19
