from __future__ import annotations

import uuid

from sqlalchemy import inspect, select

from app.models.framework import Framework
from app.models.framework_section import FrameworkSection
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user


def _seed_frameworks(db_session) -> None:
    SeedService.ensure_framework_catalog(db_session)
    SeedService.ensure_framework_versions(db_session)
    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()


def _framework_by_name(db_session, name: str) -> Framework:
    row = db_session.execute(select(Framework).where(Framework.name == name)).scalar_one_or_none()
    assert row is not None
    return row


def test_pci_dss_framework_seed_counts(db_session):
    _seed_frameworks(db_session)
    pci = _framework_by_name(db_session, "PCI DSS")

    obligations = db_session.execute(
        select(Obligation).where(Obligation.framework_id == pci.id)
    ).scalars().all()
    sections = db_session.execute(
        select(FrameworkSection).where(FrameworkSection.framework_id == pci.id)
    ).scalars().all()

    assert len(obligations) == 78
    assert len(sections) == 6


def test_nist_csf_framework_seed_counts(db_session):
    _seed_frameworks(db_session)
    nist = _framework_by_name(db_session, "NIST CSF")

    obligations = db_session.execute(
        select(Obligation).where(Obligation.framework_id == nist.id)
    ).scalars().all()
    sections = db_session.execute(
        select(FrameworkSection).where(FrameworkSection.framework_id == nist.id)
    ).scalars().all()

    assert len(obligations) == 108
    assert len(sections) == 6


def test_get_applicability_questions_for_pci(client, db_session):
    user = bootstrap_org_user(client, email_prefix="a1-questions")
    _seed_frameworks(db_session)
    pci = _framework_by_name(db_session, "PCI DSS")

    response = client.get(
        f"/api/v1/compliance/frameworks/{pci.id}/applicability-questions",
        headers=user["org_headers"],
    )
    assert response.status_code == 200
    keys = {row["question_key"] for row in response.json()}
    assert "processes_payment_cards" in keys
    assert "is_service_provider" in keys


def test_assess_applicability_all_true_returns_full_obligations(client, db_session):
    user = bootstrap_org_user(client, email_prefix="a1-assess")
    _seed_frameworks(db_session)
    pci = _framework_by_name(db_session, "PCI DSS")

    response = client.post(
        f"/api/v1/compliance/frameworks/{pci.id}/assess-applicability",
        headers=user["org_headers"],
        json={"answers": {"processes_payment_cards": True, "is_service_provider": True}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["applicable_obligation_count"] == 78
    assert len(body["obligations"]) == 78


def test_ig_level_column_exists_on_obligations_table(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("obligations")}
    assert "ig_level" in columns


def test_seed_idempotent_no_duplicate_framework_or_obligation_rows(db_session):
    _seed_frameworks(db_session)
    _seed_frameworks(db_session)

    pci = _framework_by_name(db_session, "PCI DSS")
    nist = _framework_by_name(db_session, "NIST CSF")

    pci_count = db_session.execute(
        select(Obligation).where(Obligation.framework_id == pci.id)
    ).scalars().all()
    nist_count = db_session.execute(
        select(Obligation).where(Obligation.framework_id == nist.id)
    ).scalars().all()

    assert len(pci_count) == 78
    assert len(nist_count) == 108


def test_org_isolation_framework_activation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a1-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a1-org-b")
    _seed_frameworks(db_session)
    pci = _framework_by_name(db_session, "PCI DSS")

    activate = client.post(
        f"/api/v1/frameworks/{pci.id}/activate",
        headers=org_a["org_headers"],
        json={},
    )
    assert activate.status_code == 200

    a_active = client.get("/api/v1/frameworks/active", headers=org_a["org_headers"])
    b_active = client.get("/api/v1/frameworks/active", headers=org_b["org_headers"])
    assert a_active.status_code == 200
    assert b_active.status_code == 200

    ids_a = {row["framework_id"] for row in a_active.json()}
    ids_b = {row["framework_id"] for row in b_active.json()}
    assert str(pci.id) in ids_a
    assert str(pci.id) not in ids_b

    rows_b = db_session.execute(
        select(OrganizationFramework).where(
            OrganizationFramework.organization_id == uuid.UUID(org_b["organization_id"]),
            OrganizationFramework.framework_id == pci.id,
            OrganizationFramework.status == "active",
        )
    ).scalars().all()
    assert rows_b == []
