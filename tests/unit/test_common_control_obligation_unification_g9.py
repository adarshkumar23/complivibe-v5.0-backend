"""G9 item 18: common-controls (CommonControlMapping) and direct obligation linking
(ControlObligationMapping) are two historically disconnected data models for the
same underlying concept -- a control mapped to an obligation ONLY via
CommonControlMapping was invisible to posture-summary / framework-readiness /
trust-center coverage, silently under-counting real coverage.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, UTC
import uuid

from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from tests.helpers.auth_org import bootstrap_org_user

BASE = "/api/v1/compliance/dashboard"
COMMON_CONTROLS_BASE = "/api/v1/compliance/common-controls"


def _create_control(client, headers: dict[str, str], *, title: str) -> dict:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "policy", "criticality": "medium"},
    )
    assert response.status_code == 201
    return response.json()


def _create_framework_obligation(db_session, *, code: str, name: str, reference_code: str) -> tuple[Framework, Obligation]:
    framework = Framework(
        code=code,
        name=name,
        description=f"{name} desc",
        category="Security",
        jurisdiction="United States",
        authority="Test Authority",
        version="1.0",
        status="active",
        coverage_level="starter",
        source_url=None,
        effective_date=date.today(),
    )
    db_session.add(framework)
    db_session.flush()

    obligation = Obligation(
        framework_id=framework.id,
        framework_section_id=None,
        reference_code=reference_code,
        title=f"{reference_code} obligation",
        description="obligation",
        plain_language_summary="summary",
        obligation_type="control",
        jurisdiction="United States",
        source_url=None,
        version="1.0",
        status="active",
        effective_date=date.today(),
        parent_obligation_id=None,
    )
    db_session.add(obligation)
    db_session.flush()
    db_session.commit()
    return framework, obligation


def _activate_framework_for_org(db_session, org_id: str, framework_id: uuid.UUID, actor_user_id: str | None = None) -> None:
    row = OrganizationFramework(
        organization_id=uuid.UUID(org_id),
        framework_id=framework_id,
        status="active",
        activated_by_user_id=uuid.UUID(actor_user_id) if actor_user_id else None,
        activated_at=datetime.now(UTC),
    )
    db_session.add(row)
    db_session.commit()


def test_g9_common_control_only_mapping_counts_toward_framework_coverage(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g9-unify-coverage")
    control = _create_control(client, org["org_headers"], title="Access Review Control")

    framework, obligation_a = _create_framework_obligation(db_session, code="G9-UNIFY-A", name="Unify FW A", reference_code="REQ-1")
    # A second obligation on the same framework that will remain unmapped, so the
    # framework has a non-trivial (not 100%/0%) coverage percentage to assert on.
    obligation_b = Obligation(
        framework_id=framework.id,
        reference_code="REQ-2",
        title="REQ-2 obligation",
        description="obligation",
        plain_language_summary="summary",
        obligation_type="control",
        jurisdiction="United States",
        version="1.0",
        status="active",
        effective_date=date.today(),
    )
    db_session.add(obligation_b)
    db_session.commit()

    _activate_framework_for_org(db_session, org["organization_id"], framework.id, org["user_id"])

    # Confirm the bug first: with ZERO ControlObligationMapping rows, coverage is 0%.
    before = client.get(f"{BASE}/posture-summary", headers=org["org_headers"])
    assert before.status_code == 200
    before_row = next(item for item in before.json()["active_frameworks"]["list"] if item["framework_id"] == str(framework.id))
    assert before_row["coverage_pct"] == 0.0

    # Now link the control to obligation_a ONLY via the common-controls mechanism
    # (CommonControlMapping) -- NOT via ControlObligationMapping.
    mapping = client.post(
        f"{COMMON_CONTROLS_BASE}/mappings",
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "framework_id": str(framework.id),
            "obligation_id": str(obligation_a.id),
            "mapping_strength": "full",
        },
    )
    assert mapping.status_code == 201, mapping.text

    after = client.get(f"{BASE}/posture-summary", headers=org["org_headers"])
    assert after.status_code == 200
    after_row = next(item for item in after.json()["active_frameworks"]["list"] if item["framework_id"] == str(framework.id))
    # 1 of 2 obligations now mapped -- via CommonControlMapping alone.
    assert after_row["coverage_pct"] == 50.0

    # The trust center's public coverage must reflect the same real number (reusing
    # the same ComplianceDashboardService computation -- see G9 item 2).
    slug_resp = client.get("/api/v1/organizations/me", headers=org["headers"])
    slug = slug_resp.json()[0]["slug"]
    configure = client.post(
        "/api/v1/compliance/trust-center/configuration",
        headers=org["org_headers"],
        json={
            "is_enabled": True,
            "display_name": "Unify Trust Center",
            "show_certifications": False,
            "show_framework_coverage": True,
            "show_published_policies": False,
            "show_uptime_status": False,
            "request_access_enabled": False,
        },
    )
    assert configure.status_code == 200, configure.text

    public = client.get(f"/api/v1/trust-center/{slug}")
    assert public.status_code == 200
    coverage_rows = {row["framework_name"]: row["coverage_pct"] for row in public.json()["framework_coverage"]}
    assert coverage_rows[framework.name] == 50
