from datetime import UTC, date, datetime, timedelta
import uuid

from sqlalchemy import select

from app.compliance.services.control_exception_service import run_daily_control_exception_expiry_sweep
from app.models.control import Control
from app.models.control_exception import ControlException
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from tests.helpers.auth_org import bootstrap_org_user


def _create_control(client, headers: dict[str, str], *, title: str) -> dict:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "policy", "criticality": "medium"},
    )
    assert response.status_code == 201
    return response.json()


def _seed_framework_obligation(db_session, *, code: str, name: str, reference_code: str) -> tuple[Framework, Obligation]:
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


def test_s5_p1_scheduler_org_wide_expiry_sweep(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="s5p1-exp-a")
    org_b = bootstrap_org_user(client, email_prefix="s5p1-exp-b")
    control_a = _create_control(client, org_a["org_headers"], title="S5 P1 Expire A")
    control_b = _create_control(client, org_b["org_headers"], title="S5 P1 Expire B")

    row_a = ControlException(
        organization_id=uuid.UUID(org_a["organization_id"]),
        control_id=uuid.UUID(control_a["id"]),
        title="Expired A",
        description="desc",
        exception_type="temporary",
        risk_acceptance_reason="reason",
        requested_by_user_id=uuid.UUID(org_a["user_id"]),
        owner_user_id=uuid.UUID(org_a["user_id"]),
        status="active",
        effective_date=date.today() - timedelta(days=10),
        expiry_date=date.today() - timedelta(days=1),
    )
    row_b = ControlException(
        organization_id=uuid.UUID(org_b["organization_id"]),
        control_id=uuid.UUID(control_b["id"]),
        title="Expired B",
        description="desc",
        exception_type="temporary",
        risk_acceptance_reason="reason",
        requested_by_user_id=uuid.UUID(org_b["user_id"]),
        owner_user_id=uuid.UUID(org_b["user_id"]),
        status="active",
        effective_date=date.today() - timedelta(days=10),
        expiry_date=date.today() - timedelta(days=2),
    )
    db_session.add_all([row_a, row_b])
    db_session.commit()

    result = run_daily_control_exception_expiry_sweep(db_session)
    db_session.commit()

    assert result["expired_count"] == 2
    refreshed_a = db_session.get(ControlException, row_a.id)
    refreshed_b = db_session.get(ControlException, row_b.id)
    assert refreshed_a is not None and refreshed_a.status == "expired"
    assert refreshed_b is not None and refreshed_b.status == "expired"


def test_s5_p1_common_control_fields_backfill_defaults_and_alias(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="s5p1-cc-a")
    org_b = bootstrap_org_user(client, email_prefix="s5p1-cc-b")

    control_with_mapping = _create_control(client, org_a["org_headers"], title="Access Control Baseline")
    control_without_mapping = _create_control(client, org_a["org_headers"], title="No Mapping Control")

    fw, ob = _seed_framework_obligation(
        db_session,
        code="S5P1-FW",
        name="Sprint 5 Framework",
        reference_code="CC-1",
    )
    db_session.add(
        OrganizationFramework(
            organization_id=uuid.UUID(org_a["organization_id"]),
            framework_id=fw.id,
            status="active",
            activated_by_user_id=uuid.UUID(org_a["user_id"]),
            activated_at=datetime.now(UTC),
            deactivated_by_user_id=None,
            deactivated_at=None,
            notes="test",
        )
    )
    db_session.commit()

    create_mapping = client.post(
        "/api/v1/compliance/common-controls/mappings",
        headers=org_a["org_headers"],
        json={
            "control_id": control_with_mapping["id"],
            "framework_id": str(fw.id),
            "obligation_id": str(ob.id),
            "section_reference": "CC-1",
            "mapping_strength": "full",
        },
    )
    assert create_mapping.status_code == 201

    mapped_control = db_session.execute(
        select(Control).where(Control.id == uuid.UUID(control_with_mapping["id"]))
    ).scalar_one()
    unmapped_control = db_session.execute(
        select(Control).where(Control.id == uuid.UUID(control_without_mapping["id"]))
    ).scalar_one()

    assert mapped_control.is_common_control is True
    assert mapped_control.common_control_tag == "s5p1-fw"
    assert unmapped_control.is_common_control is False
    assert unmapped_control.common_control_tag is None

    old_route = client.get(
        f"/api/v1/compliance/common-controls/coverage/{control_with_mapping['id']}",
        headers=org_a["org_headers"],
    )
    new_alias = client.get(
        f"/api/v1/controls/{control_with_mapping['id']}/framework-coverage",
        headers=org_a["org_headers"],
    )
    assert old_route.status_code == 200
    assert new_alias.status_code == 200
    assert new_alias.json() == old_route.json()

    cross_org = client.get(
        f"/api/v1/controls/{control_with_mapping['id']}/framework-coverage",
        headers=org_b["org_headers"],
    )
    assert cross_org.status_code == 404
