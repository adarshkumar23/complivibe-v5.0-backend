import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.custom_report_template import CustomReportTemplate
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import login_user, org_headers


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


def test_t31_esg_template_seed_actor_is_deterministic_with_multiple_active_members(client, db_session):
    token = _register(client, "t31-multi-owner@example.com", "Pass1234!@", "T31 ESG Multi Org")
    org_id = _org_id(client, token)

    owner_membership = db_session.execute(
        select(Membership).join(Role, Role.id == Membership.role_id).where(
            Membership.organization_id == uuid.UUID(org_id),
            Membership.status == "active",
            Role.name == "owner",
        )
    ).scalar_one()
    admin_role = db_session.execute(
        select(Role).where(Role.organization_id == uuid.UUID(org_id), Role.name == "admin")
    ).scalar_one()
    second_user = User(
        email="t31-multi-admin@example.com",
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
    )
    db_session.add(second_user)
    db_session.flush()
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=second_user.id,
            role_id=admin_role.id,
            status="active",
            invited_by=owner_membership.user_id,
        )
    )
    db_session.commit()

    response = client.get("/api/v1/compliance/custom-report-templates", headers=_headers(token, org_id))
    assert response.status_code == 200, response.text
    seeded = [item for item in response.json() if item["template_type"] in {"csrd_esrs", "gri", "tcfd", "issb"}]
    assert len(seeded) == 4

    rows = (
        db_session.execute(
            select(CustomReportTemplate).where(
                CustomReportTemplate.organization_id == uuid.UUID(org_id),
                CustomReportTemplate.template_type.in_({"csrd_esrs", "gri", "tcfd", "issb"}),
            )
        )
        .scalars()
        .all()
    )
    assert {row.created_by for row in rows} == {owner_membership.user_id}


def test_t31_readonly_role_cannot_generate_esg_report(client, db_session):
    # /generate creates a new ComplianceReport row (a write), so it must be
    # gated on the dedicated "reports:generate" permission -- not "reports:read"
    # which readonly/auditor roles also hold. Reusing reports:read here would
    # let a read-only user trigger report generation.
    token = _register(client, "t31-rbac-owner@example.io", "Pass1234!@", "T31 RBAC Org")
    org_id = _org_id(client, token)

    listing = client.get(
        "/api/v1/compliance/custom-report-templates?template_type=gri", headers=_headers(token, org_id)
    )
    assert listing.status_code == 200, listing.text
    gri_id = listing.json()[0]["id"]

    email = "t31-rbac-readonly@example.io"
    user = User(email=email, hashed_password=get_password_hash("Pass1234!@"), status="active", is_active=True)
    db_session.add(user)
    db_session.flush()
    readonly_role = db_session.execute(
        select(Role).where(Role.organization_id == uuid.UUID(org_id), Role.name == "readonly")
    ).scalar_one()
    db_session.add(
        Membership(organization_id=uuid.UUID(org_id), user_id=user.id, role_id=readonly_role.id, status="active")
    )
    db_session.commit()

    readonly_token = login_user(client, email)
    response = client.post(
        f"/api/v1/compliance/custom-report-templates/{gri_id}/generate",
        headers=org_headers(readonly_token, org_id),
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Missing required permission: reports:generate"


def test_t31_esg_report_reflects_actual_evidence_coverage_not_a_static_echo(client, db_session):
    token = _register(client, "t31-coverage@example.io", "Pass1234!@", "T31 Coverage Org")
    org_id = _org_id(client, token)
    headers = _headers(token, org_id)

    listing = client.get(
        "/api/v1/compliance/custom-report-templates?template_type=tcfd", headers=headers
    )
    tcfd_id = listing.json()[0]["id"]

    # No evidence yet: every disclosure point should be a gap and readiness 0.
    empty_report = client.post(
        f"/api/v1/compliance/custom-report-templates/{tcfd_id}/generate", headers=headers
    )
    assert empty_report.status_code == 200, empty_report.text
    empty_detail = client.get(f"/api/v1/reports/{empty_report.json()['report_id']}", headers=headers)
    empty_esg = empty_detail.json()["report"]["content_json"]["esg_disclosure_template"]
    assert empty_esg["readiness_pct"] == 0.0
    assert empty_esg["gap_points"] == empty_esg["total_disclosure_points"] > 0

    # Add fresh evidence that plausibly documents GHG emissions disclosure.
    db_session.add(
        EvidenceItem(
            organization_id=uuid.UUID(org_id),
            title="Annual greenhouse gas emissions inventory",
            description="Scope 1 and Scope 2 emissions calculated from utility billing data.",
            evidence_type="report",
            status="active",
            valid_until=datetime.now(UTC) + timedelta(days=180),
            freshness_status="fresh",
        )
    )
    db_session.commit()

    covered_report = client.post(
        f"/api/v1/compliance/custom-report-templates/{tcfd_id}/generate", headers=headers
    )
    assert covered_report.status_code == 200, covered_report.text
    covered_detail = client.get(f"/api/v1/reports/{covered_report.json()['report_id']}", headers=headers)
    covered_esg = covered_detail.json()["report"]["content_json"]["esg_disclosure_template"]

    # The generated content now differs from the earlier run purely because of
    # the org's own evidence data -- proof this is a real analysis, not a
    # fixed echo of the static template regardless of org state.
    assert covered_esg["readiness_pct"] > empty_esg["readiness_pct"]
    assert covered_esg["covered_points"] > empty_esg["covered_points"]

    ghg_point = next(
        point
        for section in covered_esg["sections"]
        for point in section["disclosure_points"]
        if point["code"] == "TCFD-MT-B"
    )
    assert ghg_point["evidence_status"] == "covered"
    assert ghg_point["matched_evidence_count"] >= 1


def test_t31_seeded_template_content_edits_rejected_but_date_range_customization_survives_reseed(client):
    token = _register(client, "t31-guardrail@example.io", "Pass1234!@", "T31 Guardrail Org")
    org_id = _org_id(client, token)
    headers = _headers(token, org_id)

    listing = client.get(
        "/api/v1/compliance/custom-report-templates?template_type=gri", headers=headers
    )
    gri = listing.json()[0]

    for blocked_field, value in (
        ("name", "My Renamed GRI"),
        ("sections", ["executive_summary"]),
        ("disclosure_structure", [{"key": "x", "title": "X", "disclosure_points": []}]),
    ):
        response = client.patch(
            f"/api/v1/compliance/custom-report-templates/{gri['id']}",
            json={blocked_field: value},
            headers=headers,
        )
        assert response.status_code == 422, response.text
        assert "cannot be edited directly" in response.json()["detail"]

    # date_range_days is a legitimate per-org customization and must survive a
    # subsequent listing call, which re-syncs seeded templates against the
    # canonical standard definition.
    updated = client.patch(
        f"/api/v1/compliance/custom-report-templates/{gri['id']}",
        json={"date_range_days": 180},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["date_range_days"] == 180

    relisted = client.get(
        "/api/v1/compliance/custom-report-templates?template_type=gri", headers=headers
    )
    assert relisted.json()[0]["date_range_days"] == 180
