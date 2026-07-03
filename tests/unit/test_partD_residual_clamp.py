from tests.helpers.auth_org import bootstrap_org_user

RISKS_BASE = "/api/v1/risks"


def test_verify_residual_score_never_exceeds_inherent_for_factor_based_risk(client):
    org = bootstrap_org_user(client, email_prefix="partD-residual")

    # factor_based risk with LOW weighted factor impacts -> low inherent_score,
    # but standard likelihood/impact set to MAX (5,5) so a naive residual
    # (residual_likelihood * residual_impact) can reach 25 -- far above inherent.
    risk = client.post(
        RISKS_BASE,
        headers=org["org_headers"],
        json={
            "title": "Factor-based residual clamp test",
            "likelihood": 5,
            "impact": 5,
            "composite_score_method": "factor_based",
            "financial_impact": 1,
            "brand_impact": 1,
            "operational_impact": 1,
        },
    )
    print("RISK CREATE:", risk.status_code, risk.json())
    assert risk.status_code == 201, risk.text
    risk_id = risk.json()["id"]
    inherent_score = risk.json()["inherent_score"]
    print("inherent_score:", inherent_score)
    assert inherent_score < 25, "test setup assumption broken: factor_based inherent_score should be low here"

    # Directly set residual_likelihood/residual_impact to MAX via PATCH -- this is
    # exactly the manual-override path that previously produced an impossible
    # residual_score > inherent_score.
    patched = client.patch(
        f"{RISKS_BASE}/{risk_id}",
        headers=org["org_headers"],
        json={"residual_likelihood": 5, "residual_impact": 5},
    )
    print("PATCHED:", patched.status_code, patched.json())
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["residual_score"] <= body["inherent_score"], (
        f"BUG: residual_score ({body['residual_score']}) exceeds inherent_score ({body['inherent_score']})"
    )
    assert body["residual_score"] == body["inherent_score"], "expected residual to be clamped exactly to inherent_score"
