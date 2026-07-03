from __future__ import annotations

from sqlalchemy import inspect, select

from app.models.atlas_technique import AtlasTechnique
from tests.helpers.auth_org import bootstrap_org_user

ATLAS_BASE = "/api/v1/ai-governance/atlas"
SYSTEMS_BASE = "/api/v1/ai-governance/systems"


def _create_system(client, headers: dict[str, str], owner_id: str, name: str) -> str:
    response = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": "limited",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_atlas_table_seed_and_endpoints(client, db_session):
    org = bootstrap_org_user(client, email_prefix="atlas-f1")

    tables = set(inspect(db_session.bind).get_table_names())
    assert "atlas_techniques" in tables

    all_techniques = client.get(f"{ATLAS_BASE}/techniques", headers=org["org_headers"])
    assert all_techniques.status_code == 200
    rows = all_techniques.json()
    assert len(rows) >= 20

    sub_count = sum(1 for item in rows if item["is_subtechnique"])
    top_count = sum(1 for item in rows if not item["is_subtechnique"])
    assert sub_count >= 5
    assert top_count >= 15

    tactics = client.get(f"{ATLAS_BASE}/tactics", headers=org["org_headers"])
    assert tactics.status_code == 200
    tactic_rows = tactics.json()
    assert len(tactic_rows) == 6

    ml_attack_only = client.get(
        f"{ATLAS_BASE}/techniques?tactic_code=ATLAS-ML-ATK",
        headers=org["org_headers"],
    )
    assert ml_attack_only.status_code == 200
    ml_rows = ml_attack_only.json()
    assert ml_rows
    assert all(item["tactic_code"] == "ATLAS-ML-ATK" for item in ml_rows)

    seeded_t0010 = db_session.execute(select(AtlasTechnique).where(AtlasTechnique.atlas_id == "AML.T0010")).scalar_one()
    seeded_t0020 = db_session.execute(select(AtlasTechnique).where(AtlasTechnique.atlas_id == "AML.T0020")).scalar_one()
    assert seeded_t0010.severity_indicator == "critical"
    assert seeded_t0020.severity_indicator == "critical"

    sub = db_session.execute(select(AtlasTechnique).where(AtlasTechnique.atlas_id == "AML.T0043.000")).scalar_one()
    parent = db_session.execute(select(AtlasTechnique).where(AtlasTechnique.id == sub.parent_id)).scalar_one()
    assert parent.atlas_id == "AML.T0043"

    detail = client.get(f"{ATLAS_BASE}/techniques/{seeded_t0010.id}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert isinstance(detail.json()["mitigations"], list)


def test_atlas_assessment_mitigations_and_org_isolation(client):
    org_a = bootstrap_org_user(client, email_prefix="atlas-a")
    org_b = bootstrap_org_user(client, email_prefix="atlas-b")

    client.get(f"{ATLAS_BASE}/techniques", headers=org_a["org_headers"])

    system_a = _create_system(client, org_a["org_headers"], org_a["user_id"], "Atlas System A")

    assessment = client.post(
        f"{SYSTEMS_BASE}/{system_a}/atlas-assessment",
        headers=org_a["org_headers"],
    )
    assert assessment.status_code == 200
    payload = assessment.json()
    assert "total_risk_score" in payload
    assert payload["risk_level"] in {"low", "medium", "high", "critical"}

    mitigations = client.get(
        f"{SYSTEMS_BASE}/{system_a}/atlas-mitigations",
        headers=org_a["org_headers"],
    )
    assert mitigations.status_code == 200
    mitigations_body = mitigations.json()
    assert isinstance(mitigations_body["mitigations"], list)
    assert mitigations_body["mitigations"]
    assert mitigations_body["total_mitigations"] == len(set(mitigations_body["mitigations"]))

    cross_org = client.post(
        f"{SYSTEMS_BASE}/{system_a}/atlas-assessment",
        headers=org_b["org_headers"],
    )
    assert cross_org.status_code == 404
