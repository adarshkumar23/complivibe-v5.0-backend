def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def test_t31_esg_templates_seed_filter_generate_and_remain_idempotent(client):
    token = _register(client, "t31-owner@example.com", "Pass1234!@", "T31 ESG Org")
    org_id = _org_id(client, token)

    first = client.get("/api/v1/compliance/custom-report-templates", headers=_headers(token, org_id))
    assert first.status_code == 200
    seeded = [item for item in first.json() if item["template_type"] in {"csrd_esrs", "gri", "tcfd", "issb"}]
    assert {item["template_type"] for item in seeded} == {"csrd_esrs", "gri", "tcfd", "issb"}
    assert all(item["system_template_key"] for item in seeded)
    assert all(item["sections"] == ["esg_disclosure_template"] for item in seeded)

    tcfd = client.get(
        "/api/v1/compliance/custom-report-templates?template_type=tcfd",
        headers=_headers(token, org_id),
    )
    assert tcfd.status_code == 200
    assert len(tcfd.json()) == 1
    tcfd_template = tcfd.json()[0]
    disclosure_sections = tcfd_template["disclosure_structure"]["sections"]
    assert [section["key"] for section in disclosure_sections] == [
        "governance",
        "strategy",
        "risk_management",
        "metrics_targets",
    ]
    assert any(
        point["code"] == "TCFD-MT-B" and "Scope 1" in point["expected_data"] and "Scope 3" in point["expected_data"]
        for section in disclosure_sections
        for point in section["disclosure_points"]
    )

    generated = client.post(
        f"/api/v1/compliance/custom-report-templates/{tcfd_template['id']}/generate",
        headers=_headers(token, org_id),
    )
    assert generated.status_code == 200
    report_id = generated.json()["report_id"]

    detail = client.get(f"/api/v1/reports/{report_id}", headers=_headers(token, org_id))
    assert detail.status_code == 200
    content = detail.json()["report"]["content_json"]["esg_disclosure_template"]
    assert content["template_type"] == "tcfd"
    assert content["standard"] == "TCFD"
    assert any(section["title"] == "Metrics and Targets" for section in content["sections"])

    second = client.get("/api/v1/compliance/custom-report-templates", headers=_headers(token, org_id))
    assert second.status_code == 200
    seeded_again = [item for item in second.json() if item["template_type"] in {"csrd_esrs", "gri", "tcfd", "issb"}]
    assert len(seeded_again) == 4
