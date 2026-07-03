import uuid
from tests.helpers.auth_org import bootstrap_org_user
from app.models.risk import Risk

RISK_SCORES_BASE = "/api/v1/compliance/risk-scores"


def test_verify_business_unit_entity_risk_score_is_real(client, db_session):
    org = bootstrap_org_user(client, email_prefix="partD-bu")

    bu = client.post(
        "/api/v1/compliance/business-units",
        headers=org["org_headers"],
        json={"name": "Engineering Org", "code": "ENG"},
    )
    print("BU CREATE:", bu.status_code, bu.json())
    assert bu.status_code == 201, bu.text
    bu_id = bu.json()["id"]

    risk = client.post(
        "/api/v1/risks",
        headers=org["org_headers"],
        json={"title": "BU-linked risk", "likelihood": 5, "impact": 5},
    )
    assert risk.status_code == 201, risk.text
    risk_id = risk.json()["id"]
    inherent_score = risk.json()["inherent_score"]
    print("RISK inherent_score:", inherent_score)

    # Link the risk to the business unit directly (no API field exposes this yet)
    row = db_session.get(Risk, uuid.UUID(risk_id))
    row.business_unit_id = uuid.UUID(bu_id)
    db_session.commit()

    computed = client.post(
        f"{RISK_SCORES_BASE}/compute-entity",
        headers=org["org_headers"],
        json={"entity_type": "business_unit", "entity_id": bu_id, "score_method": "max_score"},
    )
    print("COMPUTED ENTITY SCORE:", computed.status_code, computed.json())
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["entity_label"] == "Engineering Org", "BUG: entity_label still uses raw UUID placeholder"
    assert body["risk_count"] == 1
    assert body["composite_score"] > 0.0, "BUG: business_unit entity score is a fake 0.0 stub"
