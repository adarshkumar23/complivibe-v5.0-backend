"""G9 item 2: public trust-center framework_coverage must match the real, working
admin-side coverage numbers (posture-summary / framework-readiness), not always 0%.
"""
from __future__ import annotations

import uuid

from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from tests.helpers.auth_org import bootstrap_org_user


def _create_control(client, headers, title="Coverage Control"):
    resp = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "process", "criticality": "high", "status": "implemented"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _enable_trust_center(client, headers):
    resp = client.post(
        "/api/v1/compliance/trust-center/configuration",
        headers=headers,
        json={
            "is_enabled": True,
            "display_name": "Coverage Trust Center",
            "show_certifications": False,
            "show_framework_coverage": True,
            "show_published_policies": False,
            "show_uptime_status": False,
            "request_access_enabled": False,
        },
    )
    assert resp.status_code == 200, resp.text


def test_public_framework_coverage_matches_admin_posture_summary(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g9-trust-coverage")
    headers = org["org_headers"]
    org_id = uuid.UUID(org["organization_id"])

    _enable_trust_center(client, headers)

    framework = Framework(
        code="G9-COVERAGE-FW",
        name="G9 Coverage Framework",
        category="security",
        jurisdiction="US",
        version="1.0",
        status="active",
    )
    db_session.add(framework)
    db_session.flush()
    db_session.add(OrganizationFramework(organization_id=org_id, framework_id=framework.id, status="active"))

    obligation_a = Obligation(framework_id=framework.id, reference_code="G9-1", title="Ob A", jurisdiction="US", status="active")
    obligation_b = Obligation(framework_id=framework.id, reference_code="G9-2", title="Ob B", jurisdiction="US", status="active")
    db_session.add_all([obligation_a, obligation_b])
    db_session.commit()

    control_id = _create_control(client, headers)
    db_session.add(
        ControlObligationMapping(
            organization_id=org_id,
            control_id=uuid.UUID(control_id),
            obligation_id=obligation_a.id,
            status="active",
        )
    )
    db_session.commit()

    orgs = client.get("/api/v1/organizations/me", headers=headers)
    slug = orgs.json()[0]["slug"]

    public = client.get(f"/api/v1/trust-center/{slug}")
    assert public.status_code == 200, public.text
    coverage_rows = {row["framework_name"]: row["coverage_pct"] for row in public.json()["framework_coverage"]}
    assert coverage_rows["G9 Coverage Framework"] == 50  # 1 of 2 obligations mapped

    posture = client.get("/api/v1/compliance/dashboard/posture-summary", headers=headers)
    assert posture.status_code == 200, posture.text
    admin_rows = {row["name"]: row["coverage_pct"] for row in posture.json()["active_frameworks"]["list"]}
    assert round(admin_rows["G9 Coverage Framework"]) == coverage_rows["G9 Coverage Framework"]
