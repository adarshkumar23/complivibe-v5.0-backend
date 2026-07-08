"""G8 item 5: vendor concentration risk (HHI) must weight by real annual
spend/contract-value exposure when captured, instead of treating every
vendor as equal-weight regardless of spend (a $10K vendor and a $9M vendor
previously contributed identically to concentration risk)."""

from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
CONCENTRATION_BASE = "/api/v1/vendor-concentration-risk"


def _create_vendor(client, headers, owner_user_id, *, name: str, annual_spend_amount=None, risk_tier="critical"):
    payload = {
        "name": name,
        "vendor_type": "software",
        "owner_user_id": owner_user_id,
        "risk_tier": risk_tier,
        "status": "active",
    }
    if annual_spend_amount is not None:
        payload["annual_spend_amount"] = annual_spend_amount
    resp = client.post(VENDORS_BASE, headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_hhi_weights_by_spend_not_headcount_when_spend_data_present(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g8-hhi-spend")
    headers = org["org_headers"]

    mega = _create_vendor(client, headers, org["user_id"], name="MegaSpend Vendor", annual_spend_amount=9_000_000)
    tiny = _create_vendor(client, headers, org["user_id"], name="TinySpend Vendor", annual_spend_amount=10_000)

    recompute = client.post(f"{CONCENTRATION_BASE}/recompute", headers=headers, json={})
    assert recompute.status_code == 200, recompute.text
    detection = recompute.json()["detection"]

    # Two equal-headcount critical vendors would have been 50/50 (HHI=5000) under
    # the old count-based model. With real spend captured, the $9M vendor must
    # dominate the share, not split evenly with the $10K vendor.
    assert detection["top_vendor_id"] == mega["id"]
    assert detection["top_vendor_share_basis_points"] > 9900
    assert detection["hhi_score"] > 9800
    assert detection["evidence_json"]["weighting_method"] == "spend_weighted"

    shares_by_vendor = {row["vendor_id"]: row for row in detection["evidence_json"]["vendor_shares"]}
    assert shares_by_vendor[mega["id"]]["annual_spend_amount"] == 9000000.0
    assert shares_by_vendor[tiny["id"]]["annual_spend_amount"] == 10000.0
    assert shares_by_vendor[mega["id"]]["share_basis_points"] > shares_by_vendor[tiny["id"]]["share_basis_points"]


def test_hhi_falls_back_to_equal_weighting_when_no_spend_data_captured(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g8-hhi-nospend")
    headers = org["org_headers"]

    _create_vendor(client, headers, org["user_id"], name="No Spend Data A")
    _create_vendor(client, headers, org["user_id"], name="No Spend Data B")

    recompute = client.post(f"{CONCENTRATION_BASE}/recompute", headers=headers, json={})
    assert recompute.status_code == 200, recompute.text
    detection = recompute.json()["detection"]

    # No vendor in scope has spend data -- must fall back to the legacy
    # equal-weighted behavior (identical result to before this fix) rather than
    # silently zeroing everyone's exposure out.
    assert detection["evidence_json"]["weighting_method"] == "equal_weighted_fallback"
    shares = detection["evidence_json"]["vendor_shares"]
    assert len(shares) == 2
    assert shares[0]["share_basis_points"] == shares[1]["share_basis_points"] == 5000
    assert detection["hhi_score"] == 5000
